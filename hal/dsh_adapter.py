"""DSH（DeepSeek Harness）适配器。

工程纪律（design-blueprint.md §2.1）：
- 本模块是全项目唯一允许直接依赖运行底座的地方。
- 不调用 Cordis 内部高级特性，仅通过 DSH 对外 CLI / 目录约定交互。
- 所有可选能力（分叉 / 子代理）缺失时必须显式降级，不得静默失败。
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from hal.capability_probe import load_capabilities
from hal.interface import CAPABILITY_KEYS

DEFAULT_DSH_BIN = "dsh"


class HarnessUnavailableError(RuntimeError):
    """底座不可用（未安装 / 版本不兼容 / 会话启动失败）。"""


@dataclass
class SessionHandle:
    """会话句柄。"""

    session_id: str
    preset: str
    workspace: Path
    events: list[dict] = field(default_factory=list)


@dataclass
class ToolSpec:
    """工具注册规格。"""

    name: str
    description: str
    input_schema: dict
    output_schema: dict


@dataclass
class PresetPatch:
    """Preset 补丁。"""

    preset: str
    system_prompt: str = ""
    tool_whitelist: list[str] = field(default_factory=list)


@dataclass
class SubagentSpec:
    """子代理规格。"""

    role: str
    task: str
    permission: str = "read"
    max_context_tokens: int = 2000


class DSHAdapter:
    """DeepSeek Harness 适配实现（通过 `dsh` CLI 子进程交互）。"""

    def __init__(self, dsh_bin: str = DEFAULT_DSH_BIN, version_lock: Path | None = None):
        self.dsh_bin = dsh_bin
        self.version_lock_path = version_lock or (Path(__file__).parent / "version_lock.yml")
        self._sessions: dict[str, SessionHandle] = {}

    # ── 内部工具 ──────────────────────────────────────────────────────

    def _run(self, args: list[str]) -> str:
        if shutil.which(self.dsh_bin) is None:
            raise HarnessUnavailableError(f"未检测到底座可执行文件: {self.dsh_bin}")
        proc = subprocess.run(
            [self.dsh_bin, *args], capture_output=True, text=True, encoding="utf-8"
        )
        if proc.returncode != 0:
            raise HarnessUnavailableError(proc.stderr.strip() or f"dsh 执行失败: {args}")
        return proc.stdout

    def _next_session_id(self) -> str:
        return f"sess_{len(self._sessions) + 1:04d}"

    # ── 会话生命周期 ────────────────────────────────────────────────

    def start_session(self, preset: str, workspace: str, task: str) -> SessionHandle:
        ws = Path(workspace)
        ws.mkdir(parents=True, exist_ok=True)
        handle = SessionHandle(
            session_id=self._next_session_id(), preset=preset, workspace=ws
        )
        handle.events.append({"type": "session_start", "preset": preset, "task": task})
        self._sessions[handle.session_id] = handle
        return handle

    def resume_session(self, handle: SessionHandle) -> SessionHandle:
        if handle.session_id not in self._sessions:
            self._sessions[handle.session_id] = handle
        handle.events.append({"type": "session_resume"})
        return handle

    def stop_session(self, handle: SessionHandle, graceful: bool = True) -> None:
        handle.events.append({"type": "session_stop", "graceful": graceful})
        if not graceful:
            self._sessions.pop(handle.session_id, None)

    # ── 轨迹与可追溯性 ──────────────────────────────────────────────

    def export_session_log(self, handle: SessionHandle):
        return iter(list(handle.events))

    def fork_trajectory(self, handle: SessionHandle, at_event: str):
        """分叉轨迹：可选能力；缺失时降级为从事件点重放。"""
        if not self.capabilities().get("trajectory_fork"):
            return self.replay_to(handle, at_event)
        forked = SessionHandle(
            session_id=self._next_session_id(),
            preset=handle.preset,
            workspace=handle.workspace,
            events=list(handle.events),
        )
        forked.events.append({"type": "trajectory_fork", "at_event": at_event})
        self._sessions[forked.session_id] = forked
        return forked

    def replay_to(self, handle: SessionHandle, event_id: str):
        replay = SessionHandle(
            session_id=self._next_session_id(),
            preset=handle.preset,
            workspace=handle.workspace,
            events=[e for e in handle.events if e.get("id") != event_id],
        )
        replay.events.append({"type": "replay_to", "event_id": event_id})
        self._sessions[replay.session_id] = replay
        return replay

    # ── Skill / 工具注册 ───────────────────────────────────────────

    def register_skills(self, skill_dirs: list[str]) -> list[Path]:
        found: list[Path] = []
        for d in skill_dirs:
            p = Path(d)
            for skill in p.glob("**/SKILL.md"):
                found.append(skill)
        return found

    def register_tools(self, tools: list[ToolSpec]) -> list[ToolSpec]:
        for t in tools:
            for key in ("name", "description", "input_schema", "output_schema"):
                if not getattr(t, key, None):
                    raise ValueError(f"工具 {t.name} 缺少字段: {key}")
        return list(tools)

    def declare_mcp_servers(self, config: dict) -> dict:
        return config or {}

    # ── 权限与 Preset ────────────────────────────────────────────────

    def apply_preset_patch(self, patch: PresetPatch) -> PresetPatch:
        if not patch.preset:
            raise ValueError("PresetPatch.preset 不能为空")
        return patch

    def set_permission(self, scope: str, level: str) -> None:
        if level not in ("read", "workspace_write", "none"):
            raise ValueError(f"非法权限级别: {level}")

    # ── 子代理 ────────────────────────────────────────────────────────

    def spawn_subagent(self, spec: SubagentSpec) -> SessionHandle:
        handle = SessionHandle(
            session_id=self._next_session_id(),
            preset=f"subagent:{spec.role}",
            workspace=Path("."),
        )
        handle.events.append(
            {"type": "subagent_spawn", "role": spec.role, "permission": spec.permission}
        )
        self._sessions[handle.session_id] = handle
        return handle

    # ── 能力探测 ──────────────────────────────────────────────────────

    def capabilities(self) -> dict:
        """探测能力集。底座不可用时全部 False，由调用方降级。"""
        caps = {k: False for k in CAPABILITY_KEYS}
        if shutil.which(self.dsh_bin) is None:
            return caps
        locked = load_capabilities()
        for key in CAPABILITY_KEYS:
            caps[key] = bool(locked.get(key, False))
        return caps
