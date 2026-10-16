"""Git 分支协作流（orchestrator/collab.py）。

依据 design-blueprint.md §2.5.1 / 协作边界：
- 小组并行研究 → Git 分支 = 假设分支（``hypothesis/H1``、``hypothesis/H2``）各自推进。
- 合并回 main 前必须过 ``vl gate`` 且不存在未处理 failed 实验（防止半成品合入）。
- main 受 PR/分支保护（由 Git 服务端配置），本模块只负责本地分支管理与就绪检查。

git 调用通过 ``git_runner`` 注入，便于单测（无需真实仓库）。
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Optional

DEFAULT_BASE = "main"


def _real_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


def current_branch(cwd: Path, git_runner: Callable = _real_git) -> Optional[str]:
    res = git_runner(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    if res.returncode != 0:
        return None
    return res.stdout.strip() or None


def create_hypothesis_branch(
    hypothesis_id: str,
    cwd: Path,
    base: str = DEFAULT_BASE,
    git_runner: Callable = _real_git,
) -> tuple[bool, str]:
    """创建/切换到 ``hypothesis/<id>`` 分支（从 base 切出）。"""
    if not hypothesis_id:
        return False, "hypothesis_id 不可为空"
    branch = f"hypothesis/{hypothesis_id}"
    res = git_runner(["checkout", "-B", branch, base], cwd=cwd)
    if res.returncode != 0:
        return False, res.stderr.strip() or "git checkout 失败"
    return True, branch


def _read_current_phase(workspace: Path) -> Optional[str]:
    try:
        from orchestrator.gates import load_project

        data = load_project(workspace)
        return data.get("current_phase")
    except Exception:
        return None


def check_merge_readiness(
    workspace: Path,
    gate_phase: Optional[str] = None,
    git_runner: Callable = _real_git,
) -> dict:
    """合并前就绪检查：未处理 failed 实验 + 阶段门禁。

    返回 {"ready": bool, "branch": str, "reasons": list}。
    ``ready`` 仅被硬阻断因素（未处理失败 / 门禁未过）影响；当前在 main 不算阻塞。
    """
    from orchestrator.failure_loop import find_unresolved_failures
    from orchestrator.gates import check_gate

    branch = current_branch(workspace, git_runner=git_runner)
    reasons: list[str] = []
    blockers: list[str] = []

    unresolved = find_unresolved_failures(workspace)
    if unresolved:
        msg = f"存在未处理 failed 实验: {unresolved}"
        reasons.append(msg)
        blockers.append(msg)

    phase = gate_phase or _read_current_phase(workspace)
    if phase:
        try:
            result = check_gate(phase, workspace)
            if not result.ok:
                msg = f"阶段门禁未通过（{phase}）"
                reasons.append(msg)
                blockers.append(msg)
        except Exception as exc:  # 门禁异常视为需人工介入
            msg = f"门禁检查异常: {exc}"
            reasons.append(msg)
            blockers.append(msg)

    if branch in ("main", "master"):
        reasons.append("当前在 main（无需合并就绪检查，直接提交即可）")

    return {
        "ready": len(blockers) == 0,
        "branch": branch,
        "reasons": reasons,
    }


def merge_to_main(
    workspace: Path,
    git_runner: Callable = _real_git,
) -> tuple[bool, str]:
    """将当前假设分支合并进 main（--no-ff）。合并前强制就绪检查。"""
    readiness = check_merge_readiness(workspace, git_runner=git_runner)
    if not readiness["ready"]:
        return False, "；".join(readiness["reasons"])

    branch = readiness["branch"]
    if branch in ("main", "master", None):
        return False, "当前已在 main/master，无需合并"

    res = git_runner(["checkout", DEFAULT_BASE], cwd=workspace)
    if res.returncode != 0:
        return False, res.stderr.strip() or "切换到 main 失败"
    res = git_runner(
        ["merge", "--no-ff", branch, "-m", f"merge {branch} into main"],
        cwd=workspace,
    )
    if res.returncode != 0:
        git_runner(["merge", "--abort"], cwd=workspace)
        return False, res.stderr.strip() or "合并冲突，已中止（请手动解决）"
    return True, branch


def current_committer(
    cwd: Path,
    git_runner: Callable = _real_git,
) -> Optional[dict]:
    """读取当前 git 提交者身份（user.name / user.email）。

    用于与 ``VL_USER`` 比对，检测身份误配（协作文档 §7.2 gap② / §7.3 身份误配信号）。
    读取失败（非仓库 / 未配置）返回 ``None``。
    """
    name_res = git_runner(["config", "user.name"], cwd=cwd)
    email_res = git_runner(["config", "user.email"], cwd=cwd)
    if name_res.returncode != 0 and email_res.returncode != 0:
        return None
    return {
        "name": name_res.stdout.strip() or None,
        "email": email_res.stdout.strip() or None,
    }
