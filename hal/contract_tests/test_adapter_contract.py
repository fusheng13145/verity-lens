"""HAL 契约测试（Layer 4）。

锁定 HarnessAdapter 接口行为 + 能力缺失时的降级路径
（底座可替换性的核心保障，design-blueprint.md §2.1）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hal.capability_probe import load_capabilities
from hal.dsh_adapter import (
    DSHAdapter,
    PresetPatch,
    SessionHandle,
    SubagentSpec,
    ToolSpec,
)
from hal.interface import CAPABILITY_KEYS


@pytest.fixture
def adapter():
    return DSHAdapter()


# ── 能力探测 ──────────────────────────────────────────────────────────

def test_capabilities_keys_complete(adapter):
    assert set(adapter.capabilities()) == set(CAPABILITY_KEYS)


def test_capabilities_values_are_bool(adapter):
    assert all(isinstance(v, bool) for v in adapter.capabilities().values())


def test_capabilities_degrades_when_harness_missing(monkeypatch):
    """底座缺失时不得抛异常，返回全 False 以便调用方降级。"""
    monkeypatch.setattr("hal.dsh_adapter.shutil.which", lambda _: None)
    assert all(v is False for v in DSHAdapter().capabilities().values())


def test_version_lock_has_all_keys():
    caps = load_capabilities()
    assert isinstance(caps, dict)
    assert set(caps) == set(CAPABILITY_KEYS)


# ── 会话生命周期 ────────────────────────────────────────────────────

def test_session_lifecycle(adapter, tmp_path):
    h = adapter.start_session("review", str(tmp_path), "task-1")
    assert isinstance(h, SessionHandle) and h.preset == "review"
    assert adapter.resume_session(h) is h
    adapter.stop_session(h)
    assert h.events[-1]["type"] == "session_stop"


def test_start_session_creates_workspace(adapter, tmp_path):
    target = tmp_path / "auto_created"
    adapter.start_session("review", str(target), "t")
    assert target.exists()


# ── 轨迹与可追溯性 ──────────────────────────────────────────────────

def test_export_session_log_has_events(adapter, tmp_path):
    h = adapter.start_session("review", str(tmp_path), "task")
    events = list(adapter.export_session_log(h))
    assert events and events[0]["type"] == "session_start"


def test_fork_degrades_to_replay_when_unavailable(adapter, tmp_path, monkeypatch):
    """分叉为可选能力；不可用时降级为重放，不得抛异常。"""
    monkeypatch.setattr(
        DSHAdapter, "capabilities", lambda self: dict.fromkeys(CAPABILITY_KEYS, False)
    )
    h = adapter.start_session("review", str(tmp_path), "task")
    forked = adapter.fork_trajectory(h, "evt_none")
    assert isinstance(forked, SessionHandle)
    assert forked.session_id != h.session_id
    assert any(e.get("type") == "replay_to" for e in forked.events)


def test_replay_to_is_deterministic(adapter, tmp_path):
    h = adapter.start_session("review", str(tmp_path), "task")
    h.events.append({"id": "e1", "type": "tool_call"})
    assert [e for e in adapter.replay_to(h, "e1").events if e.get("id") == "e1"] == [
        e for e in adapter.replay_to(h, "e1").events if e.get("id") == "e1"
    ]


# ── Skill / 工具注册 ───────────────────────────────────────────────

def test_register_skills_finds_skill_md(adapter, tmp_path):
    skill = tmp_path / "skills" / "literature" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# SKILL\n", encoding="utf-8")
    assert any(f.name == "SKILL.md" for f in adapter.register_skills([str(tmp_path / "skills")]))


def test_register_tools_rejects_incomplete_spec(adapter):
    bad = ToolSpec(name="x", description="", input_schema={}, output_schema={})
    with pytest.raises(ValueError):
        adapter.register_tools([bad])


def test_register_tools_accepts_complete_spec(adapter):
    ok = ToolSpec(
        name="stat_test",
        description="d",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    assert adapter.register_tools([ok])[0].name == "stat_test"


# ── 权限与 Preset / 子代理 ─────────────────────────────────────────

def test_set_permission_rejects_bad_level(adapter):
    with pytest.raises(ValueError):
        adapter.set_permission("manuscript", "root")


def test_apply_preset_patch_requires_name(adapter):
    with pytest.raises(ValueError):
        adapter.apply_preset_patch(PresetPatch(preset=""))


def test_spawn_subagent_isolates_permission(adapter):
    spec = SubagentSpec(role="retrieval", task="search", permission="read")
    assert adapter.spawn_subagent(spec).events[0]["permission"] == "read"


def test_subagent_context_is_bounded(adapter):
    assert SubagentSpec(role="retrieval", task="search").max_context_tokens <= 2000
