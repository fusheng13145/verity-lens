"""DOI 可验证率度量（审计 #10）：把「引用 DOI 可验证」从纸面指标变成系统自度量。

设计约束（docs / project-spec.md）：引用有效性目标 ≥95%；此前 ``doi_verify`` 工具虽存在
且真联网，但主流程从不调用，系统自身不度量该指标。本模块：

- ``collect_dois``：从 Workspace 内结构化来源（RAG 索引分片 metadata.doi、假设树 /
  失败登记簿中的 doi 字段、RESEARCH.yaml 的 cited_dois）采集并去重；
- ``verify_dois``：离线做格式校验，或在 ``online=True`` 时调用 ``doi_verify`` 真联网校验；
- ``compute_doi_metric``：聚合并返回度量（总数 / 唯一数 / 格式合法 / 已验证 / 可验证率）；
- ``persist_doi_metric``：写入 RESEARCH.yaml 的 ``metrics.doi_verification`` 与
  ``docs/doi_verification.json``，使前端看板与 API 可直接读取。

不静默通过：网络不可用时 verified=0、unverifiable=N，由调用方（finalize / HITL）决定是否阻断。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from sidecar.tools.doi_verify import is_valid_format, normalize, run as doi_verify_run

_RAG_INDEX = ".verity/rag-index.json"
_HYPOTHESIS_TREE = "docs/hypothesis_tree.json"
_FAILURE_LEDGER = "docs/failure_ledger.json"
_DOI_VERIFICATION_JSON = "docs/doi_verification.json"
_DOI_KEY_RE = re.compile(r"^doi$", re.IGNORECASE)


def _walk_doi(obj: Any, out: list[str]) -> None:
    """递归收集 JSON/YAML 结构中所有 ``doi`` 键对应的字符串值。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _DOI_KEY_RE.match(str(k)) and isinstance(v, str) and v.strip():
                out.append(v)
            else:
                _walk_doi(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _walk_doi(item, out)


def collect_dois(workspace: Path) -> list[str]:
    """从 Workspace 结构化来源采集 DOI（去重、归一化）。"""
    found: list[str] = []

    # ① RAG 索引分片 metadata.doi
    rag = workspace / _RAG_INDEX
    if rag.exists():
        try:
            data = yaml.safe_load(rag.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
        for chunk in data.get("chunks", []) or []:
            meta = (chunk or {}).get("metadata") or {}
            d = meta.get("doi")
            if isinstance(d, str) and d.strip():
                found.append(d)

    # ② 假设树 / 失败登记簿 中的 doi 字段
    for rel in (_HYPOTHESIS_TREE, _FAILURE_LEDGER):
        p = workspace / rel
        if p.exists():
            try:
                _walk_doi(yaml.safe_load(p.read_text(encoding="utf-8")) or {}, found)
            except Exception:
                continue

    # ③ RESEARCH.yaml 显式声明的 cited_dois
    research = workspace / "RESEARCH.yaml"
    if research.exists():
        try:
            proj = yaml.safe_load(research.read_text(encoding="utf-8")) or {}
        except Exception:
            proj = {}
        for d in (proj.get("cited_dois") or []):
            if isinstance(d, str) and d.strip():
                found.append(d)

    seen: set[str] = set()
    unique: list[str] = []
    for d in found:
        nd = normalize(d)
        if nd and nd not in seen:
            seen.add(nd)
            unique.append(nd)
    return unique


def verify_dois(
    dois: list[str], *, online: bool = False, timeout: float = 10.0
) -> list[dict]:
    """逐个校验 DOI。离线仅做格式校验；online 调用 ``doi_verify`` 真联网。"""
    results: list[dict] = []
    for d in dois:
        nd = normalize(d)
        entry = {"doi": nd, "valid_format": is_valid_format(nd)}
        if online and entry["valid_format"]:
            try:
                res = doi_verify_run(nd, timeout=timeout)
                entry["exists"] = bool(res.get("exists"))
                entry["error"] = res.get("error")
            except Exception as exc:  # 单条失败不影响整体聚合
                entry["exists"] = False
                entry["error"] = f"{type(exc).__name__}: {exc}"
        results.append(entry)
    return results


def compute_doi_metric(
    workspace: Path, *, online: bool = False, timeout: float = 10.0
) -> dict:
    """采集 → 校验 → 聚合为可验证率度量 dict。"""
    dois = collect_dois(workspace)
    checks = verify_dois(dois, online=online, timeout=timeout)
    total = len(dois)
    valid_format = sum(1 for c in checks if c["valid_format"])
    if online:
        verified = sum(1 for c in checks if c.get("exists"))
        unverifiable = sum(1 for c in checks if c["valid_format"] and not c.get("exists"))
        rate = (verified / total) if total else 0.0
    else:
        verified = 0
        unverifiable = 0
        rate = (valid_format / total) if total else 0.0
    return {
        "total": total,
        "unique": total,
        "valid_format": valid_format,
        "verified": verified,
        "unverifiable": unverifiable,
        "verification_rate": round(rate, 4),
        "online": online,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def persist_doi_metric(research_path: Path, metric: dict) -> None:
    """将度量写入 RESEARCH.yaml 的 metrics.doi_verification，并落 docs/doi_verification.json。"""
    project = yaml.safe_load(research_path.read_text(encoding="utf-8")) or {}
    metrics = project.setdefault("metrics", {})
    metrics["doi_verification"] = metric
    research_path.write_text(
        yaml.safe_dump(project, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    json_path = research_path.parent / _DOI_VERIFICATION_JSON
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        __import__("json").dumps(metric, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
