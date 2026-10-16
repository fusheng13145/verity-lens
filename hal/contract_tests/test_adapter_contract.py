"""HAL 契约测试（Layer 4）。

锁定 HarnessAdapter 接口行为 + **真实 DSH 命令行形状** + 能力缺失/版本过低时的降级路径
（底座可替换性的核心保障，design-blueprint.md §2.1）。

契约基线：deepseek-ai/deepseek-harness docs/cli-help.md
    dsh [--profile] <name> [options] [app-args...]   --patch / --json / --session-id
本文件用**假 dsh 桩**（python 脚本）保证测试离线可重复；真实 dsh 存在时另有实测用例。
"""
from __future__ import annotations


import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hal.capability_probe import load_capabilities, load_version_lock
from hal.dsh_adapter import (
    DSHAdapter,
    PresetPatch,
    SessionHandle,
    SubagentSpec,
    ToolSpec,
    model_tool_name,
    parse_version,
)
from hal.interface import CAPABILITY_KEYS, CAPABILITY_KEYS as KEYS_FROM_INTERFACE

STUB_BODY = '''# -*- coding: utf-8 -*-
"""假 dsh：复刻真实 CLI 的最小表面（--version / --profile + --json 事件流）。"""
import json, sys

VERSION = "{version}"
args = sys.argv[1:]

if "--version" in args or "-V" in args:
    print(VERSION)
    sys.exit(0)

if "--help" in args:
    print("Usage: dsh [--profile] <name> [options] [app-args...]")
    sys.exit(0)

if "--dump-config-schema" in args:
    sys.stderr.write("unknown option '--dump-config-schema'\\n")
    sys.exit(2)

events = [
    {{"type": "session_start", "id": "e1", "profile": "headless"}},
    {{"type": "assistant_message", "id": "e2", "text": "done"}},
]
if "--json" in args:
    for e in events:
        print(json.dumps(e))
else:
    print("done")
'''


def _stub_argv(tmp_path: Path, version: str = "0.2.1-alpha.3") -> tuple[str, ...]:
    """生成假 dsh 的命令前缀（python + 脚本），等价于 npx 式前缀调用。"""
    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    script = bindir / "dsh_stub.py"
    script.write_text(STUB_BODY.format(version=version), encoding="utf-8")
    return (sys.executable, str(script))


def _adapter_with_stub(monkeypatch, tmp_path, version: str) -> DSHAdapter:
    argv = _stub_argv(tmp_path, version)
    resolved = shutil.which(argv[0]) or argv[0]
    monkeypatch.setattr(
        "hal.dsh_adapter.shutil.which", lambda name: resolved if name == argv[0] else None
    )
    return DSHAdapter(dsh_bin=argv)


@pytest.fixture
def stub_adapter(monkeypatch, tmp_path):
    """PATH 中放置假 dsh 桩（0.2.x 特性齐全）。"""
    return _adapter_with_stub(monkeypatch, tmp_path, "0.2.1-alpha.3")


@pytest.fixture
def old_stub_adapter(monkeypatch, tmp_path):
    """PATH 中放置假 dsh 桩，版本 0.1.5-rc.2（无 --json / --session-id）。"""
    return _adapter_with_stub(monkeypatch, tmp_path, "0.1.5-rc.2")


@pytest.fixture
def offline_adapter(monkeypatch):
    monkeypatch.setattr("hal.dsh_adapter.shutil.which", lambda name: None)
    return DSHAdapter()


# ── 版本锁 ──────────────────────────────────────────────────────────

def test_capability_keys_agree():
    assert CAPABILITY_KEYS == KEYS_FROM_INTERFACE


def test_version_lock_has_all_keys():
    assert set(load_capabilities()) == set(CAPABILITY_KEYS)


def test_version_lock_records_real_source():
    lock = load_version_lock()
    assert lock["source"] == "https://github.com/deepseek-ai/deepseek-harness"
    assert lock["verified_version"]
    assert lock["contract_baseline"]


def test_trajectory_fork_is_locked_off():
    """launcher 无轨迹分叉命令 → 版本锁必须显式为 false（不得乐观假设）。"""
    assert load_capabilities()["trajectory_fork"] is False


# ── 版本解析与特性门控 ──────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [("0.1.5-rc.2", (0, 1, 5)), ("0.2.1-alpha.3", (0, 2, 1)), ("", (0, 0, 0))],
)
def test_parse_version(raw, expected):
    assert parse_version(raw) == expected


def test_features_enabled_on_0_2(stub_adapter):
    assert stub_adapter.features()["json_events"] is True
    assert stub_adapter.features()["session_adopt"] is True


def test_features_disabled_on_0_1(old_stub_adapter):
    feats = old_stub_adapter.features()
    assert feats["json_events"] is False
    assert feats["session_adopt"] is False
    assert feats["patch_overlay"] is True  # --patch 在 0.1.x 就有


def test_capabilities_narrowed_by_runtime_version(old_stub_adapter):
    """版本锁为上限，运行期按底座版本收窄（session_log_export 需 ≥0.2）。"""
    caps = old_stub_adapter.capabilities()
    assert caps["preset_patch"] is True
    assert caps["session_log_export"] is False


def test_capabilities_all_false_when_harness_missing(offline_adapter):
    assert all(v is False for v in offline_adapter.capabilities().values())


# ── 命令行形状（真实 DSH 契约）─────────────────────────────────────

def test_build_run_argv_matches_official_shape(stub_adapter):
    argv = stub_adapter.build_run_argv("headless", "run the tests")
    assert argv == ["--profile", "headless", "--json", "run the tests"]


def test_build_run_argv_with_patch_and_session(stub_adapter, tmp_path):
    patch = tmp_path / "p.yml"
    argv = stub_adapter.build_run_argv(
        "tui", "go", session_id="session-1", patch_paths=(patch,)
    )
    assert argv == [
        "--profile", "tui", "--patch", str(patch), "--json",
        "--session-id", "session-1", "go",
    ]


def test_build_run_argv_drops_unsupported_flags(old_stub_adapter):
    """旧底座：不得发出未知选项，否则底座直接报 unknown option。"""
    argv = old_stub_adapter.build_run_argv("headless", "t", session_id="s1")
    assert argv == ["--profile", "headless", "t"]
    assert old_stub_adapter.dropped_flags(json_events=True, session_id="s1") == [
        "--json", "--session-id",
    ]


# ── 会话生命周期 ────────────────────────────────────────────────────

def test_session_lifecycle(stub_adapter, tmp_path):
    h = stub_adapter.start_session("headless", str(tmp_path), "task-1")
    assert isinstance(h, SessionHandle) and h.preset == "headless"
    assert stub_adapter.resume_session(h) is h
    stub_adapter.stop_session(h)
    assert h.events[-1]["type"] == "session_stop"


def test_start_session_creates_workspace(stub_adapter, tmp_path):
    target = tmp_path / "auto_created"
    stub_adapter.start_session("headless", str(target), "t")
    assert target.exists()


def test_start_session_parses_event_stream(stub_adapter, tmp_path):
    """--json 的 NDJSON 事件流必须被解析为结构化事件（可追溯性基础）。"""
    h = stub_adapter.start_session("headless", str(tmp_path), "task")
    assert [e.get("type") for e in h.events] == ["session_start", "assistant_message"]
    assert h.events[0]["id"] == "e1"


def test_start_session_records_flag_degradation(old_stub_adapter, tmp_path):
    h = old_stub_adapter.start_session("headless", str(tmp_path), "t")
    reasons = {e.get("reason") for e in h.events if e.get("type") == "degraded"}
    assert "unsupported_flag" in reasons
    assert h.degraded is True


def test_start_session_degrades_when_harness_missing(offline_adapter, tmp_path):
    """底座缺失：显式降级留痕，不抛异常、不假装跑过（失败必留痕硬规则）。"""
    h = offline_adapter.start_session("headless", str(tmp_path), "task")
    assert h.degraded is True
    assert h.events[0]["type"] == "degraded"
    assert h.events[0]["reason"] == "harness_unavailable"


def test_export_session_log_has_events(stub_adapter, tmp_path):
    h = stub_adapter.start_session("headless", str(tmp_path), "task")
    events = list(stub_adapter.export_session_log(h))
    assert events and events[0]["type"] == "session_start"


# ── 轨迹与可追溯性 ──────────────────────────────────────────────────

def test_fork_degrades_to_replay(offline_adapter, tmp_path):
    """分叉为可选能力；launcher 无此能力，恒定降级为重放。"""
    h = offline_adapter.start_session("headless", str(tmp_path), "task")
    forked = offline_adapter.fork_trajectory(h, "e1")
    assert isinstance(forked, SessionHandle)
    assert forked.session_id != h.session_id
    assert any(e.get("type") == "replay_to" for e in forked.events)


def test_replay_to_is_deterministic(offline_adapter, tmp_path):
    h = offline_adapter.start_session("headless", str(tmp_path), "task")
    assert [e for e in offline_adapter.replay_to(h, "e1").events if e.get("id") == "e1"] == [
        e for e in offline_adapter.replay_to(h, "e1").events if e.get("id") == "e1"
    ]


# ── Skill / 工具注册 ───────────────────────────────────────────────

def test_register_skills_finds_skill_md(stub_adapter, tmp_path):
    skill = tmp_path / "skills" / "literature" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# SKILL\n", encoding="utf-8")
    found = stub_adapter.register_skills([str(tmp_path / "skills")])
    assert any(f.name == "SKILL.md" for f in found)


def test_register_tools_rejects_incomplete_spec(stub_adapter):
    bad = ToolSpec(name="x", description="", input_schema={}, output_schema={})
    with pytest.raises(ValueError):
        stub_adapter.register_tools([bad])


def test_register_tools_accepts_complete_spec(stub_adapter):
    ok = ToolSpec(
        name="stat_test", description="d",
        input_schema={"type": "object"}, output_schema={"type": "object"},
    )
    assert stub_adapter.register_tools([ok])[0].name == "stat_test"


# ── MCP 声明（DSH mcp-client StdioConfig 真实键）────────────────────

def test_declare_mcp_normalizes_real_stdio_config(stub_adapter):
    out = stub_adapter.declare_mcp_servers(
        {
            "servers": [
                {
                    "transport": "stdio",
                    "serverName": "verity-stat-test",
                    "command": "python",
                    "args": ["-m", "sidecar.tools.stat_test"],
                }
            ]
        }
    )
    srv = out["servers"][0]
    assert srv["serverName"] == "verity-stat-test"
    assert srv["command"] == "python"
    assert srv["args"] == ["-m", "sidecar.tools.stat_test"]
    assert srv["toolCallTimeoutMs"] > 0
    assert srv["failOnStartupError"] is True


@pytest.mark.parametrize(
    "bad,msg",
    [
        ({"servers": [{"serverName": "x" * 33, "command": "python"}]}, "serverName"),
        ({"servers": [{"serverName": "ok_name", "command": ""}]}, "command"),
        ({"servers": [{"serverName": "ok_name", "command": "p", "args": [1]}]}, "args"),
        ({"servers": [{"serverName": "n", "command": "p", "transport": "http"}]}, "transport"),
    ],
)
def test_declare_mcp_rejects_invalid(stub_adapter, bad, msg):
    with pytest.raises(ValueError, match=msg):
        stub_adapter.declare_mcp_servers(bad)


def test_model_tool_name_convention():
    assert model_tool_name("verity-stat-test", "stat_test") == "mcp__verity-stat-test__stat_test"


def test_model_tool_name_rejects_bad_server_name():
    with pytest.raises(ValueError):
        model_tool_name("bad name!", "x")


# ── 权限与 Preset / 子代理 ─────────────────────────────────────────

def test_set_permission_rejects_bad_level(stub_adapter):
    with pytest.raises(ValueError):
        stub_adapter.set_permission("manuscript", "root")


def test_apply_preset_patch_requires_name(stub_adapter):
    with pytest.raises(ValueError):
        stub_adapter.apply_preset_patch(PresetPatch(preset=""))


def test_apply_preset_patch_materializes_overlay_file(tmp_path):
    """Preset Patch 物化为 `--patch <path>` 可指向的叠加层文件。"""
    lock = tmp_path / "version_lock.yml"
    lock.write_text("verified_version: '0.2.1-alpha.3'\n", encoding="utf-8")
    adapter = DSHAdapter(version_lock=lock)
    patch = adapter.apply_preset_patch(
        PresetPatch(preset="verity-research", system_prompt="规范", tool_whitelist=["stat_test"])
    )
    assert patch.path and patch.path.exists()
    text = patch.path.read_text(encoding="utf-8")
    assert "verity-research" in text and "stat_test" in text
    assert patch.path in adapter._pending_patches


def test_spawn_subagent_isolates_permission(stub_adapter):
    spec = SubagentSpec(role="retrieval", task="search", permission="read")
    assert stub_adapter.spawn_subagent(spec).events[0]["permission"] == "read"


def test_subagent_context_is_bounded(stub_adapter):
    assert SubagentSpec(role="retrieval", task="search").max_context_tokens <= 2000


# ── 真实底座实测（存在 dsh 时跑；不触发模型调用）────────────────────

@pytest.mark.skipif(shutil.which("dsh") is None, reason="本机未安装 dsh")
def test_real_dsh_version_is_parseable():
    ad = DSHAdapter()
    assert parse_version(ad.installed_version()) > (0, 0, 0)


@pytest.mark.skipif(shutil.which("dsh") is None, reason="本机未安装 dsh")
def test_real_dsh_capabilities_do_not_raise():
    caps = DSHAdapter().capabilities()
    assert set(caps) == set(CAPABILITY_KEYS)
    assert caps["trajectory_fork"] is False  # launcher 无此能力，恒 false


def test_preset_patch_scopes_do_not_collide(tmp_path):
    """三学科共用 preset 名时，叠加层文件按 scope 隔离，不得互相覆盖。"""
    lock = tmp_path / "version_lock.yml"
    lock.write_text("verified_version: '0.2.1-alpha.3'\n", encoding="utf-8")
    adapter = DSHAdapter(version_lock=lock)
    a = adapter.apply_preset_patch(
        PresetPatch(preset="verity-research", system_prompt="biomed", scope="biomed")
    )
    b = adapter.apply_preset_patch(
        PresetPatch(preset="verity-research", system_prompt="materials", scope="materials")
    )
    assert a.path != b.path
    assert "biomed" in a.path.read_text(encoding="utf-8")
    assert "materials" in b.path.read_text(encoding="utf-8")


# ── DSH_BIN 环境变量覆盖（多版本共存 / 旧版遮蔽场景，Backlog C ②演练发现）──

def test_dsh_bin_env_override(monkeypatch):
    """未显式传 dsh_bin 时，DSH_BIN 环境变量生效（指向正确版本的全路径）。"""
    monkeypatch.setenv("DSH_BIN", "C:/fake/prefix/dsh.cmd")
    a = DSHAdapter()
    assert a.argv_prefix == ("C:/fake/prefix/dsh.cmd",)

    monkeypatch.delenv("DSH_BIN", raising=False)
    b = DSHAdapter()
    assert b.dsh_bin == "dsh"  # 未设置 → 回退裸名


def test_dsh_bin_explicit_arg_wins_over_env(monkeypatch):
    """显式参数优先于环境变量（测试桩 / 调用方需要确定性时不受环境污染）。"""
    monkeypatch.setenv("DSH_BIN", "C:/fake/prefix/dsh.cmd")
    a = DSHAdapter(dsh_bin="explicit-dsh")
    assert a.dsh_bin == "explicit-dsh"
