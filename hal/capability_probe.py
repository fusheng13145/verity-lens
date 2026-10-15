"""HAL 能力探测与版本锁加载。

版本锁（hal/version_lock.yml）记录"针对某底座版本验证过的能力"，
证据来自 deepseek-ai/deepseek-harness 官方文档（见该文件头注释）。
底座升级流程：改 version_lock.yml → `make hal-contract-test` → 通过才更新。
"""
from __future__ import annotations

from pathlib import Path

import yaml

from hal.interface import CAPABILITY_KEYS

VERSION_LOCK = Path(__file__).parent / "version_lock.yml"


def load_version_lock(path: Path | None = None) -> dict:
    """读取完整版本锁；文件缺失时返回空字典。"""
    p = path or VERSION_LOCK
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def load_capabilities(path: Path | None = None) -> dict:
    """读取版本锁中已验证的能力集；缺失时返回全 False（缺一不可）。"""
    data = load_version_lock(path).get("capabilities", {})
    return {k: bool(data.get(k, False)) for k in CAPABILITY_KEYS}
