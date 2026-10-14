"""HAL 能力探测与版本锁加载。"""
from __future__ import annotations

import yaml
from pathlib import Path

VERSION_LOCK = Path(__file__).parent / "version_lock.yml"


def load_capabilities() -> dict:
    """读取 version_lock.yml 中已验证的能力集；缺失时返回全 False。"""
    if not VERSION_LOCK.exists():
        return {
            "trajectory_fork": False,
            "preset_patch": False,
            "subagent": False,
            "mcp": False,
            "session_log_export": False,
        }
    data = yaml.safe_load(VERSION_LOCK.read_text(encoding="utf-8")) or {}
    return data.get("capabilities", {})
