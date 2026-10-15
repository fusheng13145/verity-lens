"""收尾导出模块（Finalize）—— 端到端闭环的最后一环。

设计依据（design-blueprint.md §3.1 步骤 11 / §2.5.3 / §4.5）：
- 收尾前必须确认：全部实验已转终态、无未处理失败实验、analysis/figures 就绪；
- 终态（completed）实验必须带有可复现元数据（reproducibility：model / data_hash /
  random_seed 等），否则阻断收尾（科研诚信：没有 manifest 无法复现）；
- 产出 finalize_report.md：门禁状态 / 可复现性完整度 / AI 贡献声明草稿 / 遗留项。

退出语义：ready → 允许收尾；blocked → 列出缺失项，须补齐后重跑。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from orchestrator.failure_loop import find_unresolved_failures
from orchestrator.gates import compute_facts, load_project

# 终态实验中，completed（产出结果）必须带齐的可复现字段
REPRO_REQUIRED_FOR_COMPLETED = ("model", "data_hash", "random_seed")

TERMINAL_STATES = {"completed", "concluded_failed", "abandoned"}


@dataclass
class FinalizeReport:
    """收尾校验结果。"""

    status: str                                   # "ready" | "blocked"
    gate_ok: bool
    no_unresolved_failures: bool
    analysis_exists: bool
    figures_generated: bool
    experiments_total: int
    experiments_terminal: int
    reproducibility_missing: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report_text: str = ""

    @property
    def ready(self) -> bool:
        return self.status == "ready"


def _load_experiments(workspace: Path) -> list[tuple[str, dict]]:
    exp_dir = workspace / "experiments"
    out: list[tuple[str, dict]] = []
    if not exp_dir.exists():
        return out
    for f in sorted(exp_dir.glob("exp_*.yaml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
        exp_id = data.get("experiment_id") or f.stem
        out.append((exp_id, data))
    return out


def run_finalize(workspace: Path, write_report: bool = True) -> FinalizeReport:
    """执行收尾校验并生成报告。

    :param workspace: 项目 Workspace 目录
    :param write_report: 是否将报告写入 <workspace>/finalize_report.md
    :return: FinalizeReport
    """
    workspace = Path(workspace)
    try:
        project = load_project(workspace)
    except FileNotFoundError:
        project = {}

    facts = compute_facts(project, workspace)
    all_terminal = bool(facts.get("all_experiments_terminal"))
    analysis_exists = bool(facts.get("analysis_summary_exists"))
    figures_generated = bool(facts.get("figures_generated"))

    unresolved = find_unresolved_failures(workspace)
    no_unresolved = not unresolved

    experiments = _load_experiments(workspace)
    experiments_total = len(experiments)
    experiments_terminal = sum(
        1 for _, d in experiments if d.get("status") in TERMINAL_STATES
    )

    # 可复现性完整度：completed 实验必须带齐必填字段
    repro_missing: list[str] = []
    for exp_id, d in experiments:
        if d.get("status") == "completed":
            repro = d.get("reproducibility") or {}
            missing = [k for k in REPRO_REQUIRED_FOR_COMPLETED if not repro.get(k)]
            if missing:
                repro_missing.append(f"{exp_id}（缺: {', '.join(missing)}）")

    # 汇总 blocker
    blockers: list[str] = []
    if experiments_total and not all_terminal:
        blockers.append(
            f"存在非终态实验（共 {experiments_total} 个，仅 {experiments_terminal} 个终态）；"
            "failed 须经 vl loop 转终态"
        )
    if unresolved:
        blockers.append(
            f"存在未处理失败实验（{len(unresolved)} 个）：{', '.join(unresolved)}；须登记 failure_ledger 并审批"
        )
    if not analysis_exists:
        blockers.append("analysis/summary.md 为空或不存在，writing 阶段产物缺失")
    if not figures_generated:
        blockers.append("figures/ 目录为空或无产出图，writing 阶段图表缺失")
    if repro_missing:
        blockers.append(
            f"{len(repro_missing)} 个 completed 实验缺少可复现元数据：{'; '.join(repro_missing)}"
        )

    gate_ok = all_terminal and analysis_exists and figures_generated
    status = "blocked" if blockers else "ready"

    report = _render_report(
        workspace=workspace,
        status=status,
        gate_ok=gate_ok,
        no_unresolved=no_unresolved,
        analysis_exists=analysis_exists,
        figures_generated=figures_generated,
        experiments_total=experiments_total,
        experiments_terminal=experiments_terminal,
        repro_missing=repro_missing,
        blockers=blockers,
    )

    if write_report:
        (workspace / "finalize_report.md").write_text(report, encoding="utf-8")

    return FinalizeReport(
        status=status,
        gate_ok=gate_ok,
        no_unresolved_failures=no_unresolved,
        analysis_exists=analysis_exists,
        figures_generated=figures_generated,
        experiments_total=experiments_total,
        experiments_terminal=experiments_terminal,
        reproducibility_missing=repro_missing,
        blockers=blockers,
        warnings=[],
        report_text=report,
    )


def _render_report(
    *,
    workspace: Path,
    status: str,
    gate_ok: bool,
    no_unresolved: bool,
    analysis_exists: bool,
    figures_generated: bool,
    experiments_total: int,
    experiments_terminal: int,
    repro_missing: list[str],
    blockers: list[str],
) -> str:
    lines: list[str] = []
    lines.append(f"# 收尾报告 — {workspace.name}")
    lines.append("")
    lines.append(f"> 生成时间：{_now()}")
    lines.append("")
    lines.append(
        f"**结论**：{'✅ 可以收尾（ready）' if status == 'ready' else '⛔ 暂不可收尾（blocked）'}"
    )
    lines.append("")

    lines.append("## 1. 门禁状态")
    lines.append("")
    lines.append("| 检查项 | 结果 |")
    lines.append("|--------|------|")
    lines.append(f"| 全部实验终态 | {'✅' if experiments_total and experiments_terminal == experiments_total else ('—' if experiments_total == 0 else '❌')}（{experiments_terminal}/{experiments_total}） |")
    lines.append(f"| 无未处理失败实验 | {'✅' if no_unresolved else '❌'} |")
    lines.append(f"| analysis/summary.md 就绪 | {'✅' if analysis_exists else '❌'} |")
    lines.append(f"| figures 就绪 | {'✅' if figures_generated else '❌'} |")
    lines.append("")

    lines.append("## 2. 可复现性完整度")
    lines.append("")
    if experiments_total == 0:
        lines.append("_无实验记录。_")
    elif not repro_missing:
        lines.append(
            f"全部 {experiments_terminal} 个终态实验均带有可复现元数据（model / data_hash / random_seed）。"
        )
    else:
        lines.append(f"以下 completed 实验缺少可复现元数据，无法从 raw 复现：")
        for m in repro_missing:
            lines.append(f"  - {m}")
    lines.append("")

    lines.append("## 3. AI 贡献声明草稿")
    lines.append("")
    lines.append(
        "本研究在 verity-lens（真理之眼）科研 Agent 辅助下完成。AI 参与了"
        "文献检索与综述起草、实验设计门禁校验、统计与表征数值的确定性复算、"
        "失败归因与假设迭代建议。**所有结论的最终科学判断、数据解释与发表决策"
        "均由人类研究者（PI）负责。** 模型版本、token 消耗与随机种子见各实验"
        "的 reproducibility 元数据，以支持复现。"
    )
    lines.append("")

    lines.append("## 4. 遗留项 / 阻塞项")
    lines.append("")
    if not blockers:
        lines.append("_无。所有收尾前置条件已满足，可导出并发布。_")
    else:
        for i, b in enumerate(blockers, 1):
            lines.append(f"  {i}. {b}")
    lines.append("")

    return "\n".join(lines)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")
