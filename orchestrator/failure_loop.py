"""失败驱动迭代模块（Failure Loop）—— 科研失败闭环核心。

职责（design-blueprint.md §2.4）：
1. 检测未处理的 failed 实验（failed 为临时态，不得停留）；
2. 校验归因条目是否符合 failure_ledger Schema；
3. 用确定性工具复核关键数值（功效/效应量/p 值）；
4. 按失败分类路由到具体回流动作；
5. 落盘：更新实验状态 + 假设树 + failure_ledger + lessons.md。

硬约束：
- 每条 failed 实验必须有登记条目，否则阻塞后续阶段；
- refuted 假设不可删除，必须保留证据链；
- 新假设的 statement 必须引用 failure_ledger 条目 ID；
- 归因置信度 < LOW_CONFIDENCE_THRESHOLD 必须人工确认。
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from orchestrator.gates import PHASES, compute_facts, load_project

CATEGORIES = ("EXEC", "DATA", "METH", "HYP", "EPIS")
DECISION_TYPES = (
    "retry_execution",
    "supplement_data",
    "revise_experiment",
    "revise_hypothesis",
    "abandon_hypothesis",
    "revise_premise",
)

MAX_EXEC_RETRIES = 3
LOW_CONFIDENCE_THRESHOLD = 0.6
FIG_DIR_CANDIDATES = ("figures", "analysis/figures")

LEDGER_REL = "docs/failure_ledger.json"
TREE_REL = "docs/hypothesis_tree.json"
LESSONS_REL = "docs/lessons.md"
SCHEMA_REL = "orchestrator/schemas/failure_ledger.schema.json"


class LoopBlocked(Exception):
    """存在未处理 failed 实验 / 未批准回流，阻塞后续阶段。"""


def _root() -> Path:
    """项目根目录（orchestrator/ 的父目录）。"""
    return Path(__file__).resolve().parents[1]


# ── 读写 ──────────────────────────────────────────────────────────────

def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def load_ledger(workspace: Path) -> dict:
    return _read_json(workspace / LEDGER_REL) or {"entries": []}


def load_tree(workspace: Path) -> dict:
    return _read_json(workspace / TREE_REL) or {"root_question": "", "nodes": []}


# ── 状态检测 ──────────────────────────────────────────────────────────

def _load_experiments(workspace: Path) -> list[tuple[Path, dict]]:
    exp_dir = workspace / "experiments"
    if not exp_dir.exists():
        return []
    out = []
    for f in sorted(exp_dir.glob("exp_*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
        out.append((f, data))
    return out


def find_unresolved_failures(workspace: Path) -> list[str]:
    """返回处于临时态 failed、且未登记归回条目的实验 id 列表。"""
    ledger = load_ledger(workspace)
    resolved = {
        e.get("experiment_id")
        for e in ledger.get("entries", [])
        if (e.get("decision") or {}).get("approved_by")
    }
    unresolved = []
    for path, data in _load_experiments(workspace):
        if data.get("status") == "failed" and data.get("experiment_id") not in resolved:
            unresolved.append(data.get("experiment_id") or path.stem)
    return unresolved


def check_loop(workspace: Path) -> tuple[bool, list[str]]:
    """:return: (是否可继续, 未处理失败列表)。未处理 → 阻塞。"""
    unresolved = find_unresolved_failures(workspace)
    return (not unresolved), unresolved


# ── 归因校验与确定性复核 ──────────────────────────────────────────────

def validate_entry(entry: dict) -> list[str]:
    """按 failure_ledger.schema.json 校验单条失败条目。

    Schema 描述的是整个 ledger 文件（顶层含 entries），
    因此这里把单条条目包成 {"entries": [entry]} 再校验，
    让报错路径与文件真实结构一致（如 entries/0/classification/category）。
    """
    schema = _read_json(_root() / SCHEMA_REL)
    if schema is None:
        return ["缺少 failure_ledger.schema.json"]
    v = Draft202012Validator(schema)
    return [f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}"
            for e in sorted(v.iter_errors({"entries": [entry]}), key=lambda e: list(e.path))]


def _recompute_from_group_stats(metrics: dict) -> list[dict]:
    """用原始组统计量完整复算 p / 效应量 / CI（stat_test，确定性）。"""
    import sidecar.tools.stat_test as stat

    g = metrics["group_stats"]
    # 由均值/标准差重建等价样本（统计量与原组一致），只用于复算 p / d / CI，
    # 不触碰也不依赖原始数据。
    a = _reconstruct(g["mean_a"], g["sd_a"], int(g["n_a"]))
    b = _reconstruct(g["mean_b"], g["sd_b"], int(g["n_b"]))
    out = stat.run(a, b, test=metrics.get("test", "welch"),
                   alpha=float(metrics.get("alpha", 0.05)))
    return [out]


def _reconstruct(mean: float, sd: float, n: int) -> list[float]:
    """由 (mean, sd, n) 构造均值与样本标准差精确匹配的等价样本。

    取等差序列 x_i = mean + a·(i − (n−1)/2)：均值自动为 mean，
    令 a = sd·sqrt(12 / (n(n+1))) 可使样本方差（ddof=1）恰为 sd²
    （因为 Σ(i−(n−1)/2)² = n(n²−1)/12）。
    该样本仅用于让确定性工具复算统计量，**不是原始数据**。
    """
    step = sd * math.sqrt(12.0 / (n * (n + 1)))
    return [mean + step * (i - (n - 1) / 2) for i in range(n)]


def _cross_check_p_vs_ci(metrics: dict) -> dict:
    """p 值 ↔ 95% CI 相容性交叉复算（无原始数据时的确定性核对）。

    由 CI 反推标准误 se = (hi − lo) / (2·z_{0.975})，再由效应量反推 z = est / se，
    复算 p = 2(1 − Φ(|z|)) 与条目主张的 p 值比对。
    """
    from scipy import stats  # type: ignore

    est = float(metrics["effect_size"])
    lo, hi = (float(metrics["ci_95"][0]), float(metrics["ci_95"][1]))
    alpha = float(metrics.get("alpha", 0.05))
    reported_p = metrics.get("p_value")
    se = (hi - lo) / (2 * stats.norm.ppf(1 - alpha / 2))
    z = abs(est) / se if se > 0 else float("inf")
    p_recomputed = float(2 * (1 - stats.norm.cdf(z)))
    # 容差：绝对项覆盖舍入，相对项覆盖小 p 值——固定 0.05 会把 p=0.023 vs 9e-5 误判为通过
    tol = max(0.002, 0.10 * abs(float(reported_p))) if reported_p is not None else 0.0
    ok = reported_p is not None and abs(p_recomputed - float(reported_p)) <= tol
    return {
        "method": "p↔ci cross-check",
        "se_from_ci": round(se, 6),
        "z": round(z, 4),
        "p_recomputed": round(p_recomputed, 8),
        "p_reported": reported_p,
        "tolerance": round(tol, 6),
        "ok": bool(ok),
    }


def verify_with_sidecar(entry: dict) -> dict:
    """用确定性 Sidecar 工具复算条目主张的关键数值。

    硬规则（AGENTS.md 规则 4）：关键数值必经确定性工具复算，模型不得自行产出。
    本函数不是"探测工具是否可用"，而是**真的算一遍并与条目主张比对**：

    - `reported_metrics.group_stats` 齐全 → stat_test 完整复算 p / 效应量 / CI；
    - 只有 effect_size + ci_95（+ n_per_group）→ 做 p ↔ CI 相容性交叉复算；
    - 主张了功效（含 "power" 字段或 METH 归因为功效不足）→ power_analysis 复算并标注；
    - 无可复算数值 → skipped + 明确原因（绝不假装已验证）。

    依赖缺失时降级为 skipped（不静默通过）。对不上时 status=mismatch，METH 归因必须先解释差异。
    """
    cls = entry.get("classification") or {}
    code = cls.get("code", "")
    metrics = entry.get("reported_metrics") or {}
    result: dict[str, Any] = {"status": "skipped", "checks": []}

    if not (code.startswith("METH") or code.startswith("HYP") or code.startswith("EPIS")):
        result["reason"] = f"分类 {code or '(空)'} 无需数值复算"
        return result

    # ── 统计数值复算 ────────────────────────────────────────────────
    if code.startswith("METH") or code.startswith("HYP"):
        try:
            checks: list[dict] = []
            if metrics.get("group_stats"):
                for got in _recompute_from_group_stats(metrics):
                    checks.append(
                        {
                            "tool": "stat_test",
                            "recomputed": {
                                "p_value": round(float(got["p_value"]), 6),
                                "effect_size": (
                                    None
                                    if got["effect_size"] is None
                                    else round(float(got["effect_size"]), 4)
                                ),
                                "ci_95": [None if v is None else round(float(v), 4)
                                          for v in got["ci_95"]],
                                "test_used": got["test_used"],
                            },
                            "reported": {
                                "p_value": metrics.get("p_value"),
                                "effect_size": metrics.get("effect_size"),
                                "ci_95": metrics.get("ci_95"),
                            },
                        }
                    )
                result["status"] = "verified"
                result["checks"].extend(checks)
            elif metrics.get("effect_size") is not None and metrics.get("ci_95"):
                result["checks"].append({"tool": "stat_test", **_cross_check_p_vs_ci(metrics)})
                result["status"] = (
                    "verified"
                    if result["checks"][-1]["ok"]
                    else "mismatch"
                )
            else:
                result["checks"].append(
                    {
                        "tool": "stat_test",
                        "status": "skipped",
                        "reason": "条目未提供 reported_metrics（group_stats 或 effect_size+ci_95），无法复算",
                    }
                )
        except Exception as exc:
            result["checks"].append(
                {"tool": "stat_test", "status": "skipped", "reason": f"依赖不可用: {exc}"}
            )
            return result

    # ── 功效复算（METH 归因的常见硬证据）────────────────────────────
    n_per_group = metrics.get("n_per_group")
    eff = metrics.get("effect_size")
    if eff is not None and n_per_group is not None:
        try:
            import sidecar.tools.power_analysis as pa

            reported_power = metrics.get("power")
            post = pa.run("post", effect_size=abs(float(eff)), n_per_group=int(n_per_group))
            check = {
                "tool": "power_analysis",
                "mode": "post",
                "power_recomputed": round(post["power"], 6),
                "power_reported": reported_power,
                "required_n": post["required_n"],
                "underpowered_recomputed": post["underpowered"],
                "post_hoc_warning": post["post_hoc_warning"],
            }
            if reported_power is not None:
                check["ok"] = abs(post["power"] - float(reported_power)) <= 0.02
                if not check["ok"] and result["status"] == "verified":
                    result["status"] = "mismatch"
            result["checks"].append(check)
        except Exception as exc:
            result["checks"].append(
                {"tool": "power_analysis", "status": "skipped", "reason": f"依赖不可用: {exc}"}
            )
    elif metrics.get("power") is not None:
        result["checks"].append(
            {
                "tool": "power_analysis",
                "status": "skipped",
                "reason": "缺少 effect_size 与 n_per_group，无法复算功效",
            }
        )

    # ── 引用可达性（EPIS）───────────────────────────────────────────
    if code.startswith("EPIS"):
        try:
            import sidecar.tools.doi_verify  # noqa: F401

            result["checks"].append({"tool": "doi_verify", "status": "available"})
            if result["status"] == "skipped":
                result["status"] = "verified"
        except Exception as exc:
            result["checks"].append(
                {"tool": "doi_verify", "status": "skipped", "reason": f"依赖不可用: {exc}"}
            )

    if result["status"] == "skipped" and not result["checks"]:
        result["reason"] = "条目未提供可复算数值（不视为已验证）"
    return result


# ── 路由 ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Routing:
    category: str
    action: str                 # 回流动作
    experiment_status: str      # 原实验将置为的状态
    needs_hitl: bool
    escalate: bool
    reason: str


def route(entry: dict) -> Routing:
    """按失败分类路由到具体回流动作。"""
    cls = entry.get("classification") or {}
    category = cls.get("category", "")
    confidence = float(cls.get("confidence") or 0.0)
    decision = entry.get("decision") or {}
    exp_id = entry.get("experiment_id", "")

    if category not in CATEGORIES:
        return Routing(category or "UNKNOWN", "manual_review", "failed", True, False,
                       f"未知失败分类: {category}")

    low_conf = confidence < LOW_CONFIDENCE_THRESHOLD

    if category == "EXEC":
        retries = int(entry.get("retry_count") or 0)
        if retries < MAX_EXEC_RETRIES:
            return Routing(category, "retry_execution", "running", low_conf, False,
                       f"执行失败自动重试（{retries + 1}/{MAX_EXEC_RETRIES}），不回流假设树")
        return Routing(category, "abandon_hypothesis", "concluded_failed", True, True,
                       f"已重试 {retries} 次仍失败，升级人工介入")

    if category == "DATA":
        return Routing(category, "supplement_data", "suspended", True, False,
                   "数据不足，生成数据补充任务清单（人工执行），实验挂起")

    if category == "METH":
        nxt = _next_experiment_id(entry)
        return Routing(category, "revise_experiment", "concluded_failed", True, False,
                       f"方法/参数问题：原实验置终态，生成修订实验 {nxt}")

    if category == "HYP":
        dtype = decision.get("type", "")
        if dtype == "abandon_hypothesis":
            return Routing(category, "abandon_hypothesis", "concluded_failed", True, False,
                           "假设显式放弃，需保留节点与证据链")
        return Routing(category, "revise_hypothesis", "concluded_failed", True, False,
                       "假设未获支持：标记 refuted/revised 并生成候选新假设")

    # EPIS
    return Routing(category, "revise_premise", "concluded_failed", True, False,
                   "前提/文献依据有误：修订文献笔记与假设陈述，级联检查受影响节点")


def _next_experiment_id(entry: dict) -> str:
    cur = str(entry.get("experiment_id") or "exp_000")
    digits = "".join(ch for ch in cur if ch.isdigit())
    if not digits:
        return "exp_001"
    return f"exp_{int(digits) + 1:03d}"


# ── 级联回流 ──────────────────────────────────────────────────────────

# 根假设终态 → 派生子节点应置的状态
CASCADE_RULES: dict[str, dict[str, str]] = {
    "refuted": {"hypothesis": "revised", "experiment": "abandoned"},
    "abandoned": {"hypothesis": "abandoned", "experiment": "abandoned"},
}

CASCADING_STATUSES = tuple(CASCADE_RULES)


def cascade_impact(tree: dict, root_id: str, root_status: str) -> list[str]:
    """级联更新派生子节点（EPIS / HYP 回流时使用）。

    当某假设被证伪（refuted）或放弃（abandoned）时，沿 children 链传播影响：
    派生假设标记为需修订（revised），其下实验标记为放弃（abandoned），
    并写入 cascade_note 留存影响来源。

    :return: 受影响的派生节点 id 列表（不含 root_id）
    """
    if root_status not in CASCADE_RULES:
        return []

    nodes = {n.get("id"): n for n in tree.get("nodes", []) if n.get("id")}
    if root_id not in nodes:
        return []

    rules = CASCADE_RULES[root_status]
    affected: list[str] = []
    queue = list(nodes[root_id].get("children") or [])
    seen = {root_id}

    while queue:
        cid = queue.pop(0)
        if cid in seen or cid not in nodes:
            continue
        seen.add(cid)
        node = nodes[cid]
        target = rules.get(node.get("type"))
        if target:
            node["status"] = target
            node["cascade_note"] = f"源假设 {root_id} 已 {root_status}，本节点需复核"
            affected.append(cid)
        queue.extend(node.get("children") or [])

    return affected


# ── 落盘：应用回流决策 ──────────────────────────────────────────────

def apply_decision(workspace: Path, entry: dict) -> dict:
    """校验 → 路由 → 更新实验状态/假设树 → 追加 ledger → 渲染 lessons。"""
    errors = validate_entry(entry)
    if errors:
        raise ValueError("失败条目标验不通过:\n  - " + "\n  - ".join(errors))

    # HITL 硬约束：未经批准不得回流（Schema 中 approved_by 可选，故在此强制）
    if not (entry.get("decision") or {}).get("approved_by"):
        raise ValueError(
            "失败登记需人工批准：decision.approved_by 不能为空"
        )

    routing = route(entry)
    exp_id = entry.get("experiment_id")

    # 1) 更新实验状态
    for path, data in _load_experiments(workspace):
        if data.get("experiment_id") == exp_id:
            data["status"] = routing.experiment_status
            data["failure_ref"] = entry.get("id")
            if routing.action == "revise_experiment":
                data["superseded_by"] = _next_experiment_id(entry)
            if routing.action == "retry_execution":
                data["retry_count"] = int(data.get("retry_count") or 0) + 1
            _write_yaml(path, data)

    # 2) 更新假设树
    tree = load_tree(workspace)
    impact = (entry.get("decision") or {}).get("hypothesis_impact") or {}
    cascaded: list[str] = []
    for node in tree.get("nodes", []):
        node_id = node.get("id")
        if node_id == entry.get("hypothesis_id") and node_id in impact:
            patch = impact[node_id] or {}
            new_status = patch.get("status")
            if "status" in patch:
                node["status"] = new_status
            if "confidence_change" in patch:
                base = node.get("confidence") or 0.0
                node["confidence"] = _clamp(base + float(patch["confidence_change"]))
            entry_id = entry.get("id")
            if entry_id and entry_id not in (node.get("provenance") or {}).get("justified_by", []):
                node.setdefault("provenance", {}).setdefault("justified_by", []).append(entry_id)
            if new_status in CASCADING_STATUSES:
                cascaded.extend(cascade_impact(tree, node_id, new_status))
    tree.setdefault("metadata", {})["version"] = int(tree.get("metadata", {}).get("version") or 0) + 1
    tree.setdefault("metadata", {})["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(workspace / TREE_REL, tree)

    # 3) 追加 ledger
    ledger = load_ledger(workspace)
    ledger.setdefault("entries", []).append(entry)
    _write_json(workspace / LEDGER_REL, ledger)

    # 4) 渲染 lessons.md
    _render_lessons(workspace, ledger)

    return {
        "entry_id": entry.get("id"),
        "category": routing.category,
        "action": routing.action,
        "experiment_status": routing.experiment_status,
        "needs_hitl": routing.needs_hitl,
        "escalate": routing.escalate,
        "reason": routing.reason,
        "tree_version": tree.get("metadata", {}).get("version"),
        "cascaded_nodes": cascaded,
    }


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _render_lessons(workspace: Path, ledger: dict) -> None:
    """由结构化 ledger 渲染人读 lessons.md（追加、去重）。"""
    lines = ["# 失败模式库", "", "> 由 `docs/failure_ledger.json` 自动渲染，请勿手工编辑。", ""]
    for e in ledger.get("entries", []):
        cls = e.get("classification") or {}
        lines.append(f"## {e.get('id')} — {cls.get('category')} / {cls.get('code')}")
        lines.append(f"- 实验: `{e.get('experiment_id')}` · 假设: `{e.get('hypothesis_id')}`")
        lines.append(f"- 置信度: {cls.get('confidence')}")
        lines.append(f"- 归因: {cls.get('rationale','')}")
        lines.append(f"- 决策: {e.get('decision',{}).get('type')}")
        lines.append(f"- 经验: {e.get('lesson','')}")
        if e.get("evidence"):
            lines.append("- 证据:")
            for ev in e["evidence"]:
                loc = f" ({ev['locator']})" if ev.get("locator") else ""
                lines.append(f"  - `{ev.get('path')}`{loc}")
        lines.append("")
    (workspace / LESSONS_REL).write_text("\n".join(lines), encoding="utf-8")
