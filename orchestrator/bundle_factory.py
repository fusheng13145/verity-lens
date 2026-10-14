"""Bundle 工厂占位（Phase 2 实现）。

依据 docs/bundle-registry.md 与 design-blueprint.md §2.6：
`vl bundle new <discipline>` 基于 bundles/_template 生成 L0 骨架。
"""
from __future__ import annotations

import shutil
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent.parent / "bundles" / "_template"


def new_bundle(discipline: str, target_dir: Path) -> Path:
    """基于 _template 生成 L0 Bundle 骨架（占位实现）。"""
    dest = target_dir / discipline
    if dest.exists():
        raise FileExistsError(f"Bundle 已存在: {dest}")
    shutil.copytree(TEMPLATE_DIR, dest)
    return dest
