"""DSH（DeepSeek Harness）适配器占位实现。

Phase 0 依据 docs/interfaces.md 与 hal/contract_tests 完成。
"""
from __future__ import annotations

from hal.interface import HarnessAdapter


class DSHAdapter:
    """DeepSeek Harness 适配实现（占位）。"""

    def capabilities(self) -> dict:
        # Phase 0：真实探测后返回；此处为占位默认值
        return {
            "trajectory_fork": True,
            "preset_patch": True,
            "subagent": True,
            "mcp": True,
            "session_log_export": True,
        }


# 保留导入以便静态检查 Protocol 兼容性
_ = HarnessAdapter
