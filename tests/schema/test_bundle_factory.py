"""Bundle 工厂测试（Phase 2）。

覆盖：L0 骨架生成、占位符替换、空目录/模板目录占位保留、
重复创建拒绝、已有 Bundle 结构校验。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from orchestrator.bundle_factory import (
    TEMPLATE_DIR,
    BundleExistsError,
    new_bundle,
    validate_bundle,
)


def test_template_exists():
    assert TEMPLATE_DIR.is_dir()
    assert (TEMPLATE_DIR / "bundle.yml").exists()
    assert (TEMPLATE_DIR / "skills" / "capability" / "SKILL.md").exists()


def test_new_bundle_creates_skeleton(tmp_path):
    dest = new_bundle("testdisc", tmp_path, capability="stats")
    assert dest.is_dir()
    assert (dest / "bundle.yml").exists()
    skill = dest / "skills" / "testdisc-stats" / "SKILL.md"
    assert skill.exists()


def test_new_bundle_substitutes_placeholders(tmp_path):
    dest = new_bundle("testdisc", tmp_path, capability="stats")
    manifest = yaml.safe_load((dest / "bundle.yml").read_text(encoding="utf-8"))
    assert manifest["name"] == "testdisc"
    assert manifest["level"] == "L0"
    assert manifest["skills"] == ["skills/testdisc-stats/SKILL.md"]

    skill_text = (dest / "skills" / "testdisc-stats" / "SKILL.md").read_text(encoding="utf-8")
    assert "${DISCIPLINE}" not in skill_text
    assert "${CAPABILITY}" not in skill_text
    assert "testdisc-stats" in skill_text


def test_new_bundle_renames_skill_dir(tmp_path):
    dest = new_bundle("testdisc", tmp_path, capability="stats")
    # 占位目录 capability 应已被重命名
    assert not (dest / "skills" / "capability").exists()
    assert (dest / "skills" / "testdisc-stats").exists()


def test_new_bundle_rejects_duplicate(tmp_path):
    new_bundle("testdisc", tmp_path)
    with pytest.raises(BundleExistsError):
        new_bundle("testdisc", tmp_path)


def test_validate_bundle_ok(tmp_path):
    dest = new_bundle("testdisc", tmp_path)
    assert validate_bundle(dest) == []


def test_validate_bundle_missing_manifest(tmp_path):
    (tmp_path / "empty").mkdir()
    problems = validate_bundle(tmp_path / "empty")
    assert problems and "bundle.yml" in problems[0]


def test_validate_bundle_missing_skill(tmp_path):
    dest = new_bundle("testdisc", tmp_path)
    # 删掉 Skill 文件，使 bundle.yml 声明落空
    for p in (dest / "skills").rglob("SKILL.md"):
        p.unlink()
    problems = validate_bundle(dest)
    assert any("Skill 不存在" in m for m in problems)


def test_validate_bundle_bad_level(tmp_path):
    dest = new_bundle("testdisc", tmp_path)
    m = dest / "bundle.yml"
    data = yaml.safe_load(m.read_text(encoding="utf-8"))
    data["level"] = "L9"
    m.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    assert any("level 非法" in x for x in validate_bundle(dest))
