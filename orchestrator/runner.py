"""科研全流程运行器（Runner）—— 把阶段推进、Agent 会话启动、门禁硬阻断串成真实闭环。

对应审计 P0-1 / P0-2：此前编排层从未调用 HAL 启动会话，五阶段是静态规则表而非状态机。
本模块提供：

- ``pre_session``：会话启动前同步跑硬阻断链（①阶段门禁 ②预算 ③失败回流），替代无人调用的
  ``hooks/pre_session.sh``，让门禁/预算/回流检查真正在会话启动前生效；
- ``start_phase_session``：经 HAL 接口（``harness.HarnessAdapter`` Protocol）真正驱动底座
  （``adapter.start_session``）；底座缺失/失败降级为留痕句柄，**不静默失败**；
- ``advance``：校验下一阶段门禁 → 推进 ``current_phase`` → 启动该阶段会话；
- ``run``：启动当前（或指定）阶段会话，不改变 ``current_phase``。

依赖收敛（AGENTS.md 硬规则 1）：仅本模块与 ``bundle_loader`` 允许 import ``hal``。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from hal.dsh_adapter import DSHAdapter
from orchestrator.budget import evaluate_budget
from orchestrator.failure_loop import find_unresolved_failures
from orchestrator.gates import (
    PHASES,
    GateResult,
    check_gate,
    load_project,
    save_project,
)

# 每个阶段使用的 DSH preset 名（与 bundle_loader 的 verity-research 一致）
PHASE_PRESETS: dict[str, str] = {p: "verity-research" for p in PHASES}

# 每个阶段的会话任务描述（驱动底座的 task 参数；提示模型本阶段应产出的声明式制品）
PHASE_TASKS: dict[str, str] = {
    "literature": (
        "检索并阅读文献，产出 docs/literature_notes.md 与 docs/hypothesis_tree.json"
        "（含至少 1 条研究假设）"
    ),
    "question": "基于文献笔记提炼研究问题，补全 hypothesis_tree.json 的根问题与节点",
    "experiment": (
        "设计并通过确定性工具执行实验，落盘 experiments/exp_*.yaml"
        "（status=completed 或 concluded_failed，failed 为临时态须回流）"
    ),
    "analysis": (
        "用 sidecar 确定性工具复算关键数值，产出 analysis/summary.md"
        "（须含效应量 / 95% CI / p 值等统计结论）"
    ),
    "writing": (
        "基于 analysis/summary.md 与 figures/ 撰写 manuscript/ 草稿，"
        "人工审批后运行 vl finalize 收尾"
    ),
}


class PreSessionBlocked(Exception):
    """pre_session 硬阻断链未通过，禁止启动会话。"""

    def __init__(self, gate: GateResult):
        self.gate = gate
        super().__init__("pre_session 未通过: " + "; ".join(gate.missing))


class Runner:
    """科研全流程运行器。

    :param adapter: HAL 适配器（默认 ``DSHAdapter``）；测试可注入实现 ``HarnessAdapter`` 的桩。
    :param skill_dirs: 会话启动前注册到底座的 Skill 目录（如已加载 Bundle 的 skills 目录）。
    """

    def __init__(
        self,
        adapter: Optional[DSHAdapter] = None,
        *,
        skill_dirs: Optional[list[str]] = None,
    ):
        self.adapter = adapter or DSHAdapter()
        self.skill_dirs = skill_dirs or []

    # ── 状态机 ────────────────────────────────────────────────────────

    def current_phase(self, workspace: Path) -> str:
        try:
            return str(load_project(workspace).get("current_phase") or PHASES[0])
        except FileNotFoundError:
            return PHASES[0]

    def set_phase(self, workspace: Path, phase: str) -> None:
        if phase not in PHASES:
            raise ValueError(f"未知阶段: {phase}，可选: {', '.join(PHASES)}")
        project = load_project(workspace)
        project["current_phase"] = phase
        save_project(workspace, project)

    def next_phase(self, workspace: Path) -> Optional[str]:
        cur = self.current_phase(workspace)
        if cur not in PHASES:
            return PHASES[0]
        idx = PHASES.index(cur)
        return None if idx + 1 >= len(PHASES) else PHASES[idx + 1]

    # ── pre_session 硬阻断链 ──────────────────────────────────────────

    def pre_session(self, workspace: Path, phase: str) -> GateResult:
        """会话启动前的硬阻断链：①阶段门禁 ②预算硬阻断 ③失败回流检查。

        聚合为单一 ``GateResult``，任一阻塞即 ``ok=False``。原先这些检查散落在无人调用的
        ``hooks/pre_session.sh``，此处收为代码内同步调用，成为真正的硬阻断点。
        """
        gate = check_gate(phase, workspace)
        missing = list(gate.missing)

        # ② 预算硬阻断（token_budget.total.used >= cap 时暂停）
        if self._budget_exhausted(workspace):
            missing.append(
                "预算已耗尽（token_budget.total.used >= cap），暂停会话；"
                "恢复选项：追加预算 / 切换廉价模型 / 人工介入"
            )

        # ③ 失败回流检查（failed 为临时态，不得停留）
        try:
            unresolved = find_unresolved_failures(workspace)
        except Exception:
            unresolved = []
        if unresolved:
            missing.append(
                f"存在未处理的 failed 实验（{len(unresolved)} 项）："
                "须先登记 failure_ledger 并人工批准回流"
            )

        return GateResult(
            phase=phase,
            ok=not missing,
            missing=tuple(missing),
            hitl_required=gate.hitl_required or bool(unresolved),
        )

    def _budget_exhausted(self, workspace: Path) -> bool:
        try:
            project = load_project(workspace)
        except FileNotFoundError:
            return False
        return evaluate_budget(project).level == "hard"

    # ── 启动阶段会话 ──────────────────────────────────────────────────

    def start_phase_session(self, workspace: Path, phase: str, *, session_id=None):
        """经 HAL 真正启动该阶段会话；pre_session 未通过则抛 ``PreSessionBlocked``。"""
        gate = self.pre_session(workspace, phase)
        if not gate.ok:
            raise PreSessionBlocked(gate)

        preset = PHASE_PRESETS.get(phase, "verity-research")
        task = PHASE_TASKS.get(phase, f"执行 {phase} 阶段任务")
        if self.skill_dirs:
            self.adapter.register_skills(self.skill_dirs)

        handle = self.adapter.start_session(
            preset, str(workspace), task, session_id=session_id
        )
        # 会话结束后把可见 token 用量写回 RESEARCH.yaml，让预算硬阻断真正生效
        self._record_session(workspace, handle)
        return handle

    def _record_session(self, workspace: Path, handle) -> None:
        events = getattr(handle, "events", []) or []
        used = 0
        for ev in events:
            if isinstance(ev, dict):
                used += int((ev.get("usage") or {}).get("total_tokens", 0) or 0)
        if used <= 0:
            return
        try:
            project = load_project(workspace)
        except FileNotFoundError:
            return
        total = project.setdefault("token_budget", {}).setdefault("total", {})
        total["used"] = float(total.get("used") or 0) + used
        save_project(workspace, project)

    # ── 入口命令 ──────────────────────────────────────────────────────

    def run(self, workspace: Path, phase: Optional[str] = None, *, session_id=None) -> dict:
        """启动当前（或指定）阶段会话，不改变 ``current_phase``。"""
        phase = phase or self.current_phase(workspace)
        handle = self.start_phase_session(workspace, phase, session_id=session_id)
        return {
            "phase": phase,
            "handle": handle,
            "degraded": bool(getattr(handle, "degraded", False)),
        }

    def advance(self, workspace: Path, *, start_session: bool = True) -> dict:
        """校验下一阶段门禁 → 推进 ``current_phase`` → 启动该阶段会话。

        :return: 报告 dict。``advanced=False`` 时含 ``reason`` 与（若适用）``gate``。
        """
        cur = self.current_phase(workspace)
        nxt = self.next_phase(workspace)
        if nxt is None:
            return {
                "advanced": False,
                "current": cur,
                "next": None,
                "reason": "已处于终态 writing，没有后续阶段；请运行 vl finalize 收尾",
                "gate": None,
            }

        gate = self.pre_session(workspace, nxt)
        if not gate.ok:
            return {
                "advanced": False,
                "current": cur,
                "next": nxt,
                "reason": "下一阶段门禁 / 硬阻断未满足",
                "gate": gate,
            }

        self.set_phase(workspace, nxt)
        handle = None
        if start_session:
            handle = self.start_phase_session(workspace, nxt)
        return {
            "advanced": True,
            "current": cur,
            "next": nxt,
            "gate": gate,
            "handle": handle,
            "degraded": bool(getattr(handle, "degraded", False)) if handle else False,
        }
