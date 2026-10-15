"""Bundle 工厂测试（Phase 2 / Phase 4a）。

覆盖：L0 骨架生成、占位符替换、空目录/模板目录占位保留、
重复创建拒绝、已有 Bundle 结构校验、第二学科可生成并校验（换 Bundle 即切换学科）。
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

REPO_ROOT = Path(__file__).resolve().parents[2]


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


def test_factory_supports_multiple_disciplines(tmp_path):
    """换 Bundle 即切换学科：不同学科均可由同一模板生成并通过结构校验。"""
    d1 = new_bundle("chem", tmp_path, capability="spectro")
    d2 = new_bundle("physics", tmp_path, capability="sim")
    assert validate_bundle(d1) == []
    assert validate_bundle(d2) == []
    assert (d1 / "skills" / "chem-spectro" / "SKILL.md").exists()
    assert (d2 / "skills" / "physics-sim" / "SKILL.md").exists()


def test_materials_bundle_validates():
    """锁定仓库内已交付的 materials L2 Bundle 结构合规。"""
    materials = REPO_ROOT / "bundles" / "materials"
    problems = validate_bundle(materials)
    assert problems == [], problems


def test_three_disciplines_coexist():
    """Phase 4b→4c：biomed / materials / compsci 三学科并存、均达 L2、结构合规。"""
    # Phase 4e：biomed / compsci 需要功效分析（METH 归因硬证据），materials 不需要
    stats_servers = {"verity-stat-test", "verity-doi-verify"}
    disciplines = {
        "biomed": ("L2", {"biomed-stats", "biomed-literature"}, stats_servers | {"verity-power-analysis"}),
        "materials": ("L2", {"materials-characterization", "materials-literature"}, stats_servers),
        "compsci": ("L2", {"compsci-computation", "compsci-literature"}, stats_servers | {"verity-power-analysis"}),
    }
    seen_disciplines: set[str] = set()
    for name, (level, skills, servers) in disciplines.items():
        d = REPO_ROOT / "bundles" / name
        problems = validate_bundle(d)
        assert problems == [], f"{name}: {problems}"
        data = yaml.safe_load((d / "bundle.yml").read_text(encoding="utf-8"))
        assert data["discipline"] == name
        assert data["level"] == level
        # L2 三要素齐备
        assert data["preset_patch"]["preset"] == "verity-research"
        assert {s["name"] for s in data["mcp"]["servers"]} == servers, name
        assert len(data["golden_cases"]) >= 1
        skill_dirs = {p.parent.name for p in d.glob("skills/*/SKILL.md")}
        assert skill_dirs == skills, f"{name}: {skill_dirs}"
        seen_disciplines.add(name)
    # 三个不同学科，互不重名
    assert seen_disciplines == {"biomed", "materials", "compsci"}


def test_validate_l2_requires_preset_mcp_golden(tmp_path):
    """L2 三要素（preset_patch / mcp / golden_cases）缺一不可。"""
    d = tmp_path / "l2bad"
    (d / "skills" / "l2bad-core").mkdir(parents=True)
    (d / "skills" / "l2bad-core" / "SKILL.md").write_text("# x", encoding="utf-8")
    (d / "bundle.yml").write_text(
        'name: "l2bad"\nlevel: "L2"\ndiscipline: "l2bad"\n'
        "skills:/n  - skills/l2bad-core/SKILL.md\n",
        encoding="utf-8",
    )
    problems = validate_bundle(d)
    assert any("preset_patch" in p for p in problems)
    assert any("mcp" in p for p in problems)
    assert any("golden_cases" in p for p in problems)


def test_validate_l2_bad_mcp_server(tmp_path):
    d = tmp_path / "l2mcp"
    (d / "skills" / "l2mcp-core").mkdir(parents=True)
    (d / "skills" / "l2mcp-core" / "SKILL.md").write_text("# x", encoding="utf-8")
    (d / "bundle.yml").write_text(
        'name: "l2mcp"\nlevel: "L2"\ndiscipline: "l2mcp"\n'
        "skills:/n  - skills/l2mcp-core/SKILL.md\n"
        "preset_patch:/n  preset: p\n"
        "mcp:/n  servers:/n    - transport: stdio\n"
        "golden_cases:/n  - golden/x.input.json\n",
        encoding="utf-8",
    )
    problems = validate_bundle(d)
    assert any("mcp.servers[0] 缺少 name" in p for p in problems)
    assert any("mcp.servers[0] 缺少 command/url" in p for p in problems)
    assert any("golden_cases 文件不存在" in p for p in problems)


def test_l0_l1_may_omit_l2_fields(tmp_path):
    """L0/L1 不强制 preset_patch / mcp / golden_cases（渐进升级）。"""
    d = new_bundle("chem", tmp_path, capability="spectro")
    assert validate_bundle(d) == []


def test_validate_l2_requires_preset_mcp_golden(tmp_path):
    """L2 三要素（preset_patch / mcp / golden_cases）缺一不可。"""
    d = tmp_path / "l2bad"
    (d / "skills" / "l2bad-core").mkdir(parents=True)
    (d / "skills" / "l2bad-core" / "SKILL.md").write_text("# x", encoding="utf-8")
    (d / "bundle.yml").write_text(
        'name: "l2bad"\nlevel: "L2"\ndiscipline: "l2bad"\n'
        "skills:\n  - skills/l2bad-core/SKILL.md\n",
        encoding="utf-8",
    )
    problems = validate_bundle(d)
    assert any("preset_patch" in p for p in problems)
    assert any("mcp" in p for p in problems)
    assert any("golden_cases" in p for p in problems)


def test_validate_l2_bad_mcp_server(tmp_path):
    d = tmp_path / "l2mcp"
    (d / "skills" / "l2mcp-core").mkdir(parents=True)
    (d / "skills" / "l2mcp-core" / "SKILL.md").write_text("# x", encoding="utf-8")
    (d / "bundle.yml").write_text(
        'name: "l2mcp"\nlevel: "L2"\ndiscipline: "l2mcp"\n'
        "skills:\n  - skills/l2mcp-core/SKILL.md\n"
        "preset_patch:\n  preset: p\n"
        "mcp:\n  servers:\n    - transport: stdio\n"
        "golden_cases:\n  - golden/x.input.json\n",
        encoding="utf-8",
    )
    problems = validate_bundle(d)
    assert any("mcp.servers[0] 缺少 name" in p for p in problems)
    assert any("mcp.servers[0] 缺少 command/url" in p for p in problems)
    assert any("golden_cases 文件不存在" in p for p in problems)


def test_l0_l1_may_omit_l2_fields(tmp_path):
    """L0/L1 不强制 preset_patch / mcp / golden_cases（渐进升级）。"""
    d = new_bundle("chem", tmp_path, capability="spectro")
    assert validate_bundle(d) == []
