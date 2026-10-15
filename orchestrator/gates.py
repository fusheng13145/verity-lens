"""阶段门禁纯函数引擎。

设计要点（design-blueprint.md §2.2 / §2.3）：
- 无状态：输入 = Workspace 声明式文件，输出 = 是否放行 + 缺失清单。
- 声明式：规则来自 gates.rules.yaml 的命名事实（condition），
  不使用表达式求值，避免注入与安全风险。
- 幂等：重复调用结果一致，编排层崩溃重启即可恢复。
"""
from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

PHASES: tuple[str, ...] = ("literature", "question", "experiment", "analysis", "writing")

# 实验终态集合（failed / running 为临时态，不得停在 analysis 阶段）
TERMINAL_EXPERIMENT_STATES = {"completed", "concluded_failed", "abandoned"}

GATES_RULES_PATH = Path(__file__).parent / "gates.rules.yaml"
SCHEMAS_DIR = Path(__file__).parent / "schemas"


@dataclass(frozen=True)
class GateResult:
    """门禁校验结果。"""

    phase: str
    ok: bool
    missing: tuple[str, ...] = ()
    hitl_required: bool = False

    def render(self) -> str:
        """按 interaction-design.md §1 三段式输出。"""
        head = f"[{'PASS' if self.ok else 'BLOCKED'}] 阶段 {self.phase}"
        if self.ok:
            extra = "（需人工审批）" if self.hitl_required else ""
            return f"{head} 准入满足{extra}\n下一步：可启动该阶段会话"
        lines = [f"{head} 准入未满足（{len(self.missing)} 项）："]
        for i, msg in enumerate(self.missing, 1):
            lines.append(f"  {i}. {msg}")
        lines.append("下一步：完成上述项后重新运行 vl gate <phase>")
        return "\n".join(lines)


def load_project(workspace: Path) -> dict:
    """读取 RESEARCH.yaml（项目唯一真相源）。"""
    path = workspace / "RESEARCH.yaml"
    if not path.exists():
        raise FileNotFoundError(f"缺少 RESEARCH.yaml: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def save_project(workspace: Path, data: dict) -> None:
    """写回 RESEARCH.yaml（保留中文与 YAML 字段顺序）。"""
    path = workspace / "RESEARCH.yaml"
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    path.write_text(text, encoding="utf-8")


def load_rules(path: Path | None = None) -> dict:
    """读取声明式门禁规则表。"""
    p = path or GATES_RULES_PATH
    if not p.exists():
        raise FileNotFoundError(f"缺少门禁规则表: {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _experiment_statuses(workspace: Path) -> list[str | None]:
    exp_dir = workspace / "experiments"
    if not exp_dir.exists():
        return []
    out: list[str | None] = []
    for f in sorted(exp_dir.glob("exp_*.yaml")):
        try:
            d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            out.append(d.get("status"))
        except Exception:
            out.append(None)
    return out


def compute_facts(project: dict, workspace: Path) -> dict[str, bool]:
    """由项目状态推导命名事实（供 rules 的 condition 引用）。"""
    hypotheses = project.get("hypotheses") or []
    approvals = project.get("approvals") or {}
    question_approval = approvals.get("question") or {}

    statuses = _experiment_statuses(workspace)
    figures_dir = workspace / "figures"
    summary_path = workspace / "analysis" / "summary.md"

    return {
        "hypotheses_len_ge_1": len(hypotheses) >= 1,
        "approvals_question_approved": bool(question_approval.get("approved_by")),
        "all_experiments_terminal": bool(statuses)
        and all(s in TERMINAL_EXPERIMENT_STATES for s in statuses),
        "analysis_summary_exists": summary_path.exists() and summary_path.stat().st_size > 0,
        "figures_generated": figures_dir.exists() and any(figures_dir.iterdir()),
    }


def validate_acyclic(tree: dict) -> bool:
    """校验假设树 parent_id 无环（Layer1 硬约束）。"""
    nodes = {n["id"]: n for n in tree.get("nodes", []) if "id" in n}
    for start in nodes:
        seen: set[str] = set()
        cur: str | None = start
        while cur is not None:
            if cur in seen:
                return False
            seen.add(cur)
            cur = (nodes.get(cur) or {}).get("parent_id")
    return True


def _load_schema(name: str) -> dict:
    return json.loads((SCHEMAS_DIR / name).read_text(encoding="utf-8"))


def _parse_doc(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _schema_for(relpath: str, bindings: dict) -> str | None:
    """按 schema_bindings 为文件匹配 Schema（支持通配）。"""
    for pattern, schema_name in bindings.items():
        if fnmatch.fnmatch(relpath, pattern):
            return schema_name
    return None


def check_file(workspace: Path, relpath: str, check: str, bindings: dict) -> tuple[bool, str]:
    """执行单条 file 检查，返回 (是否通过, 描述)。"""
    matches = sorted(workspace.glob(relpath))
    if not matches:
        return False, f"{relpath} 不存在"

    if check == "non_empty":
        for m in matches:
            if not m.is_file() or m.stat().st_size == 0:
                return False, f"{m.relative_to(workspace)} 为空"
        return True, f"{relpath} 非空"

    if check == "schema_valid":
        schema_name = _schema_for(relpath, bindings)
        if not schema_name:
            return False, f"{relpath} 未绑定 Schema"
        validator = Draft202012Validator(_load_schema(schema_name))
        for m in matches:
            try:
                data = _parse_doc(m)
            except Exception as exc:
                return False, f"{m.relative_to(workspace)} 解析失败: {exc}"
            errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
            if errors:
                return False, f"{m.relative_to(workspace)} Schema 校验失败: {errors[0].message}"
        return True, f"{relpath} Schema 校验通过"

    if check == "present_and_schema_valid":
        ok, msg = check_file(workspace, relpath, "schema_valid", bindings)
        return ok, msg

    return False, f"未知 check 类型: {check}"


def check_gate(phase: str, workspace: Path, rules_path: Path | None = None) -> GateResult:
    """校验指定阶段的准入条件。

    :param phase: 目标阶段名
    :param workspace: 项目 Workspace 目录
    :param rules_path: 规则表路径（默认 gates.rules.yaml）
    """
    if phase not in PHASES:
        raise ValueError(f"未知阶段: {phase}，可选: {', '.join(PHASES)}")

    rules = load_rules(rules_path)
    gate = (rules.get("gates") or {}).get(phase) or {}
    bindings = (rules.get("schema_bindings") or {}) or {}

    missing: list[str] = []

    if workspace.exists():
        try:
            project = load_project(workspace)
        except FileNotFoundError as exc:
            project = {}
            missing.append(str(exc))
        facts = compute_facts(project, workspace)
    else:
        project = {}
        facts = compute_facts(project, workspace)
        missing.append(f"Workspace 不存在: {workspace}")

    for req in gate.get("entry_requires") or []:
        if "file" in req:
            ok, msg = check_file(workspace, req["file"], req.get("check", "non_empty"), bindings)
            if not ok:
                missing.append(msg)
        elif "condition" in req:
            name = req["condition"]
            if name not in facts:
                missing.append(f"未知门禁事实: {name}")
            elif not facts[name]:
                missing.append(f"条件未满足: {name}")

    return GateResult(
        phase=phase,
        ok=not missing,
        missing=tuple(missing),
        hitl_required=bool(gate.get("hitl_required", False)),
    )
