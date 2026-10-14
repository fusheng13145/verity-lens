"""HAL 版本锁冒烟测试（Phase 0 契约测试起点）。"""
from pathlib import Path
import sys
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hal.capability_probe import load_capabilities


def test_version_lock_parses():
    caps = load_capabilities()
    for key in ("trajectory_fork", "preset_patch", "subagent", "mcp", "session_log_export"):
        assert key in caps, f"缺失能力键: {key}"
