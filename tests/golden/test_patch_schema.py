"""Preset Patch 机读校验 + DSH schema 钉固测试（Backlog C / 可选增强）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from orchestrator.bundle_loader import load_bundle
from orchestrator.patch_schema import (
    PINNED_SCHEMA_PATH,
    pin_dsh_schema,
    validate_preset_patch,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLES_DIR = REPO_ROOT / "bundles"


# ── 1. verity 契约严格校验 ────────────────────────────────────────────
def test_validate_preset_patch_good():
    problems = validate_preset_patch(
        {"preset": "verity-research", "system_prompt": "x", "tool_whitelist": ["a", "b"]}
    )
    assert problems == []


def test_validate_missing_preset():
    problems = validate_preset_patch({"system_prompt": "x"})
    assert any("preset" in m for m in problems)


def test_validate_empty_preset():
    problems = validate_preset_patch({"preset": "", "tool_whitelist": []})
    assert any("preset" in m for m in problems)


def test_validate_unknown_key_is_error():
    problems = validate_preset_patch({"preset": "x", "bogus_key": 1})
    assert any("未知字段" in m for m in problems)


def test_validate_tool_whitelist_wrong_type():
    problems = validate_preset_patch({"preset": "x", "tool_whitelist": "not-a-list"})
    assert any("类型错误" in m for m in problems)


def test_validate_tool_whitelist_non_string_items():
    problems = validate_preset_patch({"preset": "x", "tool_whitelist": [1, 2]})
    assert any("每项必须为字符串" in m for m in problems)


def test_validate_system_prompt_wrong_type():
    problems = validate_preset_patch({"preset": "x", "system_prompt": 123})
    assert any("类型错误" in m for m in problems)


def test_validate_non_dict():
    assert validate_preset_patch("not-a-dict") == ["preset_patch 必须为映射"]


# ── 2. DSH schema 钉固 ────────────────────────────────────────────────
class _SchemaAdapter:
    def __init__(self, schema):
        self._schema = schema

    def dump_config_schema(self, profile: str = "headless"):
        return self._schema


def test_pin_dsh_schema_writes_file(tmp_path):
    out = tmp_path / "schema.json"
    res = pin_dsh_schema(_SchemaAdapter({"$defs": {"loaderExpression": {}}}), out_path=out)
    assert res == out
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "$defs" in data


def test_pin_dsh_schema_none_when_unavailable():
    assert pin_dsh_schema(_SchemaAdapter(None)) is None


# ── 3. 接入 load_bundle（check_patch_schema 默认关闭，符合「可选增强」） ──
class _FakeAdapter:
    """最小假适配器：复刻 load_bundle 所需接口，apply_preset_patch 不落盘。"""

    def __init__(self, caps: dict, schema=None):
        self._caps = caps
        self._schema = schema

    def capabilities(self):
        return self._caps

    def register_skills(self, skill_dirs):
        found = []
        for d in skill_dirs:
            for p in Path(d).glob("**/SKILL.md"):
                found.append(p)
        return found

    def declare_mcp_servers(self, config):
        return config

    def apply_preset_patch(self, patch):
        return patch

    def dump_config_schema(self, profile: str = "headless"):
        return self._schema


def test_load_default_does_not_pin_schema():
    adapter = _FakeAdapter(
        caps={"preset_patch": True, "mcp": True, "subagent": True,
              "trajectory_fork": True, "session_log_export": True}
    )
    report = load_bundle(BUNDLES_DIR / "biomed", adapter=adapter, check_patch_schema=False)
    assert report.ok, report.problems
    assert not PINNED_SCHEMA_PATH.exists()


def test_load_check_patch_schema_passes_and_pins(tmp_path, monkeypatch):
    # 指向临时钉固路径，避免写仓库
    monkeypatch.setattr(
        "orchestrator.patch_schema.PINNED_SCHEMA_PATH", tmp_path / "dsh-config-schema.json"
    )
    adapter = _FakeAdapter(
        caps={"preset_patch": True, "mcp": True, "subagent": True,
              "trajectory_fork": True, "session_log_export": True},
        schema={"$defs": {"loaderExpression": {}}},
    )
    report = load_bundle(BUNDLES_DIR / "biomed", adapter=adapter, check_patch_schema=True)
    assert report.ok, report.problems
    assert report.warnings == []
    assert report.preset == "verity-research"
    assert (tmp_path / "dsh-config-schema.json").exists()


def test_load_check_patch_schema_warns_when_schema_unavailable():
    adapter = _FakeAdapter(
        caps={"preset_patch": True, "mcp": True, "subagent": True,
              "trajectory_fork": True, "session_log_export": True},
        schema=None,  # 底座不支持 / 不可用
    )
    report = load_bundle(BUNDLES_DIR / "biomed", adapter=adapter, check_patch_schema=True)
    assert report.ok
    assert any("DSH 配置 schema" in w for w in report.warnings)


def test_load_check_patch_schema_blocks_bad_patch(tmp_path):
    d = tmp_path / "broken"
    (d / "skills" / "broken-core").mkdir(parents=True)
    (d / "skills" / "broken-core" / "SKILL.md").write_text("# x", encoding="utf-8")
    (d / "golden").mkdir()
    (d / "golden" / "g.input.json").write_text("{}", encoding="utf-8")
    (d / "bundle.yml").write_text(
        'name: "broken"\nlevel: "L2"\ndiscipline: "broken"\n'
        "skills:\n  - skills/broken-core/SKILL.md\n"
        "preset_patch:\n"
        "  preset: \"verity-research\"\n"
        "  bogus_key: 1\n"  # 未知字段 → 严格校验应拦下
        "mcp:\n"
        "  servers:\n"
        "    - name: \"verity-stat-test\"\n"
        "      command: [\"python\", \"-m\", \"sidecar.tools.stat_test\"]\n"
        "      tools: [\"stat_test\"]\n"
        "golden_cases:\n  - golden/g.input.json\n",
        encoding="utf-8",
    )
    adapter = _FakeAdapter(
        caps={"preset_patch": True, "mcp": True, "subagent": True,
              "trajectory_fork": True, "session_log_export": True}
    )
    report = load_bundle(d, adapter=adapter, check_patch_schema=True)
    assert not report.ok
    assert any("未知字段" in p for p in report.problems)
