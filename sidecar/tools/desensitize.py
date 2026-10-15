"""Sidecar 工具：敏感数据脱敏（确定性，离线可用）。

设计蓝图 design-blueprint.md：
- §2.7 侧车工具目录：desensitize.py — 敏感数据脱敏（k-匿名 / PHI 屏蔽 / DP 聚合）
- 数据治理管道：k-匿名 / PHI 屏蔽 / DP 聚合（ε=1.0）；敏感数据永不进模型上下文
- E10 风险条目：敏感数据误入上下文 → 脱敏管道在容器外完成；`never_in_context` 清单 + 正则扫描 prompt 告警

四种操作（mode 分发，run(mode, **params)）：
1. field_mask   : 字段级屏蔽（hash 令牌化 / redact 置空 / generalize 数值泛化）
2. k_anonymity  : 准标识符（QI）抑制，使每个 QI 组合出现 ≥ k 次
3. dp_aggregate : 差分隐私聚合（Laplace 噪声，默认 ε=1.0；seed 给定则可复现）
4. scan_text    : 正则扫描文本中的 PHI/PII（E10 守卫），返回命中类型与风险等级

除 DP 加噪（可 seed 复现）外均为确定性；模型不得自行脱敏或判定是否含敏感信息。
"""
from __future__ import annotations

import hashlib
import math
import random
import re
from collections import Counter
from typing import Any


# PHI / PII 正则（高精确优先；顺序影响去重时的保留）
_PHI_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("cn_mobile", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("cn_id_card", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("credit_card", re.compile(r"(?<!\d)(?:\d[ \-]?){15}\d(?!\d)")),
    ("date_of_birth", re.compile(r"\b(?:19|20)\d{2}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01])\b")),
]

# never_in_context 风险等级：出现这些 → high；其余 PHI → medium
_HIGH_RISK_TYPES = {"email", "cn_mobile", "cn_id_card", "credit_card"}


TOOL_SPEC = {
    "name": "desensitize",
    "description": "敏感数据脱敏：字段屏蔽 / k-匿名抑制 / 差分隐私聚合 / PHI 文本扫描（E10 守卫）",
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["field_mask", "k_anonymity", "dp_aggregate", "scan_text"],
                "description": "操作类型",
            },
            "records": {"type": "array", "items": {"type": "object"},
                        "description": "field_mask / k_anonymity：待处理记录列表（dict）"},
            "fields": {"type": "array", "items": {"type": "string"},
                       "description": "field_mask：需屏蔽的字段名"},
            "strategy": {"type": "string", "enum": ["hash", "redact", "generalize"],
                         "default": "hash", "description": "field_mask：hash 令牌化 / redact 置空 / generalize 数值泛化"},
            "salt": {"type": "string", "description": "field_mask：hash 盐（留空则用空盐，仍确定性）"},
            "quasi_identifiers": {"type": "array", "items": {"type": "string"},
                                  "description": "k_anonymity：准标识符字段"},
            "k": {"type": "integer", "minimum": 2, "default": 3,
                  "description": "k_anonymity：每个 QI 组合最小出现次数"},
            "values": {"type": "array", "items": {"type": "number"},
                       "description": "dp_aggregate：原始数值"},
            "epsilon": {"type": "number", "exclusiveMinimum": 0, "default": 1.0,
                        "description": "dp_aggregate：隐私预算 ε（蓝图默认 1.0）"},
            "statistic": {"type": "string", "enum": ["mean", "sum", "count"], "default": "mean",
                          "description": "dp_aggregate：聚合统计量"},
            "bounds": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2,
                       "description": "dp_aggregate：可选 [min,max] 夹紧范围（不传则用数据自身范围）"},
            "seed": {"type": "integer", "description": "dp_aggregate：随机种子（给定则噪声可复现）"},
            "text": {"type": "string", "description": "scan_text：待扫描文本"},
        },
        "required": ["mode"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string"},
            "masked_records": {"type": "array"},
            "suppressed_count": {"type": "integer"},
            "k_satisfied": {"type": "boolean"},
            "raw_value": {"type": "number"},
            "noisy_value": {"type": "number"},
            "hits": {"type": "array"},
            "has_phi": {"type": "boolean"},
            "risk_level": {"type": "string"},
        },
    },
}


# --------------------------------------------------------------------------- #
# 1. field_mask — 字段级屏蔽
# --------------------------------------------------------------------------- #
def _mask_value(value: Any, strategy: str, salt: str) -> str:
    s = "" if value is None else str(value)
    if strategy == "redact":
        return "[REDACTED]"
    if strategy == "hash":
        h = hashlib.sha256((salt or "").encode("utf-8") + s.encode("utf-8")).hexdigest()
        return "h_" + h[:16]
    if strategy == "generalize":
        if re.fullmatch(r"-?\d+(?:\.\d+)?", s):
            n = float(s)
            if n == 0:
                return "0-"
            base = 10 ** max(0, int(math.log10(abs(n))) - 1)
            lo = int(n // base * base)
            return f"{lo}-"
        # 非数值：保留首字符，其余掩码
        return s[0] + "*" * (len(s) - 1) if len(s) > 1 else s
    raise ValueError(f"未知 strategy: {strategy}")


def field_mask(records: list[dict], fields: list[str], strategy: str = "hash",
               salt: str | None = None) -> dict:
    """对 records 中指定 fields 做屏蔽。"""
    if not fields:
        raise ValueError("fields 不能为空")
    masked: list[dict] = []
    for r in records:
        nr = dict(r)
        for f in fields:
            if f in nr:
                nr[f] = _mask_value(nr[f], strategy, salt or "")
        masked.append(nr)
    return {
        "mode": "field_mask",
        "masked_records": masked,
        "masked_fields": list(fields),
        "strategy": strategy,
        "salt_used": bool(salt),
    }


# --------------------------------------------------------------------------- #
# 2. k_anonymity — 准标识符抑制
# --------------------------------------------------------------------------- #
def k_anonymity(records: list[dict], quasi_identifiers: list[str], k: int = 3,
                suppress_token: str = "[SUPPRESSED]") -> dict:
    """抑制 QI 唯一（出现 < k 次）的记录：其 QI 字段置为抑制标记，使同组合并达标。

    采用泛化-抑制框架中的「抑制」策略：被抑制行仍保留但 QI 全置标记，
    所有被抑制行因此共享同一 QI 元组，自动聚成一组（≥ 彼此数量）。
    """
    if not quasi_identifiers:
        raise ValueError("quasi_identifiers 不能为空")
    if k < 2:
        raise ValueError("k 必须 >= 2")
    keys = [tuple(r.get(q) for q in quasi_identifiers) for r in records]
    counts = Counter(keys)
    out: list[dict] = []
    suppressed = 0
    for r, key in zip(records, keys):
        if counts[key] < k:
            suppressed += 1
            nr = dict(r)
            for q in quasi_identifiers:
                nr[q] = suppress_token
            out.append(nr)
        else:
            out.append(dict(r))
    return {
        "mode": "k_anonymity",
        "anonymized_records": out,
        "suppressed_count": suppressed,
        "k": k,
        "k_satisfied": bool(suppressed == 0),
        "unique_qi_groups": len(counts),
        "total_records": len(records),
    }


# --------------------------------------------------------------------------- #
# 3. dp_aggregate — 差分隐私聚合（Laplace）
# --------------------------------------------------------------------------- #
def dp_aggregate(values: list[float], epsilon: float = 1.0, statistic: str = "mean",
                 seed: int | None = None, bounds: list[float] | None = None) -> dict:
    """对 values 做 DP 加噪聚合。ε 默认 1.0（蓝图）。seed 给定则噪声可复现。

    敏感度口径：先夹紧到 [lo, hi]（不传 bounds 则用数据自身 min/max），
    再按统计量定敏感度 Δ：mean → (hi-lo)/n；sum → (hi-lo)；count → 1。
    噪声 ~ Laplace(0, Δ/ε)，由 random.Random(seed) 生成（seed=None 用系统熵）。
    """
    vals = [float(v) for v in values]
    n = len(vals)
    if n == 0:
        raise ValueError("values 不能为空")
    if epsilon <= 0:
        raise ValueError("epsilon 必须 > 0")

    if statistic == "mean":
        raw = sum(vals) / n
        lo, hi = (bounds[0], bounds[1]) if bounds else (min(vals), max(vals))
        sensitivity = (hi - lo) / n
    elif statistic == "sum":
        raw = sum(vals)
        lo, hi = (bounds[0], bounds[1]) if bounds else (min(vals), max(vals))
        sensitivity = hi - lo
    elif statistic == "count":
        raw = float(n)
        sensitivity = 1.0
    else:
        raise ValueError(f"未知 statistic: {statistic}")

    scale = sensitivity / epsilon
    rng = random.Random(seed)
    u = rng.random()
    # Laplace 逆 CDF：symmetrized log
    noise = -scale * (1 if u >= 0.5 else -1) * math.log(1 - 2 * abs(u - 0.5))
    return {
        "mode": "dp_aggregate",
        "statistic": statistic,
        "raw_value": raw,
        "noisy_value": raw + noise,
        "epsilon": epsilon,
        "sensitivity": sensitivity,
        "noise_scale": scale,
        "n": n,
        "seed": seed,
    }


# --------------------------------------------------------------------------- #
# 4. scan_text — PHI/PII 正则扫描（E10 守卫）
# --------------------------------------------------------------------------- #
def scan_text(text: str) -> dict:
    """扫描文本中的 PHI/PII，返回命中与风险等级。供 pre-session/prompt 守卫调用。"""
    hits: list[dict] = []
    for ptype, pat in _PHI_PATTERNS:
        for m in pat.finditer(text):
            hits.append({"type": ptype, "match": m.group(0), "span": [m.start(), m.end()]})
    # 去重重叠命中（保留较早/较长者）
    hits.sort(key=lambda h: (h["span"][0], -(h["span"][1] - h["span"][0])))
    cleaned: list[dict] = []
    last_end = -1
    for h in hits:
        if h["span"][0] >= last_end:
            cleaned.append(h)
            last_end = h["span"][1]
    risk = "none"
    if cleaned:
        risk = "high" if any(h["type"] in _HIGH_RISK_TYPES for h in cleaned) else "medium"
    return {
        "mode": "scan_text",
        "hits": cleaned,
        "has_phi": bool(cleaned),
        "risk_level": risk,
    }


# --------------------------------------------------------------------------- #
# 入口分发
# --------------------------------------------------------------------------- #
def run(mode: str, **params: Any) -> dict:
    if mode == "field_mask":
        return field_mask(
            params.get("records") or [],
            params.get("fields") or [],
            params.get("strategy", "hash"),
            params.get("salt"),
        )
    if mode == "k_anonymity":
        return k_anonymity(
            params.get("records") or [],
            params.get("quasi_identifiers") or [],
            int(params.get("k", 3)),
        )
    if mode == "dp_aggregate":
        return dp_aggregate(
            params.get("values") or [],
            float(params.get("epsilon", 1.0)),
            params.get("statistic", "mean"),
            params.get("seed"),
            params.get("bounds"),
        )
    if mode == "scan_text":
        return scan_text(params.get("text") or "")
    raise ValueError(f"未知 mode: {mode}")


if __name__ == "__main__":
    import sys

    from sidecar.tools._stdio import serve

    sys.exit(serve(run))
