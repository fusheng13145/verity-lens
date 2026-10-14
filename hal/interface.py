"""HAL：Harness 适配层抽象接口。

全项目唯一允许直接依赖运行底座（当前：DeepSeek Harness）的模块。
详见 docs/interfaces.md 与 design-blueprint.md §2.1。
"""
from __future__ import annotations

from typing import Iterator, Literal, Protocol, runtime_checkable


@runtime_checkable
class HarnessAdapter(Protocol):
    # 会话生命周期
    def start_session(self, preset: str, workspace: str, task: str): ...
    def resume_session(self, handle): ...
    def stop_session(self, handle, graceful: bool = True) -> None: ...

    # 轨迹与可追溯性
    def export_session_log(self, handle) -> Iterator[dict]: ...
    def fork_trajectory(self, handle, at_event: str): ...

    # Skill / 工具注册
    def register_skills(self, skill_dirs: list[str]) -> None: ...
    def register_tools(self, tools: list) -> None: ...
    def declare_mcp_servers(self, config: dict) -> None: ...

    # 权限与 Preset
    def apply_preset_patch(self, patch) -> None: ...
    def set_permission(self, scope: str, level: Literal["read", "workspace_write", "none"]) -> None: ...

    # 子代理
    def spawn_subagent(self, spec) -> None: ...

    # 能力探测
    def capabilities(self) -> dict:
        """返回 {'trajectory_fork': bool, 'preset_patch': bool,
        'subagent': bool, 'mcp': bool, 'session_log_export': bool}"""
