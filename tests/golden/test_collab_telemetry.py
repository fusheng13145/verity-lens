"""协作观测埋点单元测试（orchestrator/collab_telemetry.py）。

核心保证：opt-in 默认零副作用（不建文件、不抛异常）；开启后才写 JSONL；
观测失败（OSError）静默吞掉，绝不干扰主流程。同时覆盖 cli 层 wiring。
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from orchestrator.collab_telemetry import is_enabled, record


def _now() -> datetime:
    return datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_disabled_by_default_no_file(tmp_path):
    sink = tmp_path / "audit.jsonl"
    ok = record(tmp_path, "x", {"k": 1}, enabled=False, sink=sink)
    assert ok is False
    assert not sink.exists()


def test_enabled_writes_jsonl(tmp_path):
    sink = tmp_path / "audit.jsonl"
    ok = record(
        tmp_path,
        "lock_acquire",
        {"artifact": "manuscript", "holder": "a", "outcome": "granted"},
        now=_now(),
        enabled=True,
        sink=sink,
    )
    assert ok is True
    lines = _read_jsonl(sink)
    assert len(lines) == 1
    entry = lines[0]
    assert entry["ts"] == _now().isoformat()
    assert entry["event"] == "lock_acquire"
    assert entry["artifact"] == "manuscript"
    assert entry["holder"] == "a"
    assert entry["outcome"] == "granted"
    # vl_user 缺省为 None（未设环境变量）
    assert entry["vl_user"] is None


def test_env_enabled(monkeypatch):
    monkeypatch.setenv("VL_TELEMETRY", "1")
    assert is_enabled(None) is True
    monkeypatch.setenv("VL_TELEMETRY", "0")
    assert is_enabled(None) is False


def test_research_config_enabled():
    assert is_enabled({"collab_telemetry": True}) is True
    assert is_enabled({}) is False
    assert is_enabled(None) is False


def test_vl_user_captured(tmp_path, monkeypatch):
    monkeypatch.setenv("VL_USER", "researcher_b")
    sink = tmp_path / "audit.jsonl"
    record(tmp_path, "e", {"x": 1}, enabled=True, sink=sink)
    entry = _read_jsonl(sink)[0]
    assert entry["vl_user"] == "researcher_b"


def test_oserror_swallowed(tmp_path):
    # 让 sink 的父路径是一个文件 → mkdir 触发 OSError（子类），应静默返回 False
    blocker = tmp_path / "afile"
    blocker.write_text("x", encoding="utf-8")
    sink = blocker / "nested" / "audit.jsonl"
    ok = record(tmp_path, "e", {"x": 1}, enabled=True, sink=sink)
    assert ok is False  # 不抛异常


def _ns(**kw):
    return type("A", (), kw)()


def _init_workspace(tmp_path: Path) -> Path:
    import orchestrator.cli as cli

    cli.cmd_init(_ns(project_id="proj_tel", discipline="biomed", path=str(tmp_path)))
    return tmp_path / "proj_tel"


def test_cli_lock_wiring_records_when_enabled(tmp_path, monkeypatch):
    import orchestrator.cli as cli

    monkeypatch.setenv("VL_TELEMETRY", "1")
    ws = _init_workspace(tmp_path)

    # a 获取锁 → granted
    cli.cmd_lock(_ns(action="acquire", artifact="manuscript", holder="a", ttl=3600, json=False, path=str(ws)))
    # b 再获取 → rejected_conflict
    cli.cmd_lock(_ns(action="acquire", artifact="manuscript", holder="b", ttl=3600, json=False, path=str(ws)))
    # a 释放
    cli.cmd_lock(_ns(action="release", artifact="manuscript", holder="a", ttl=3600, json=False, path=str(ws)))

    audit = ws / ".verity" / "collab-audit.jsonl"
    assert audit.exists()
    events = _read_jsonl(audit)
    outcomes = [(e["event"], e.get("outcome")) for e in events]
    assert ("lock_acquire", "granted") in outcomes
    assert ("lock_acquire", "rejected_conflict") in outcomes
    assert ("lock_release", None) in outcomes  # release 无 outcome 字段
    # 冲突事件的 existing_holder 应记录为 a（被 b 撞见）
    conflict = next(e for e in events if e.get("outcome") == "rejected_conflict")
    assert conflict["existing_holder"] == "a"


def test_cli_lock_no_side_effect_when_disabled(tmp_path, monkeypatch):
    import orchestrator.cli as cli

    monkeypatch.delenv("VL_TELEMETRY", raising=False)
    ws = _init_workspace(tmp_path)
    cli.cmd_lock(_ns(action="acquire", artifact="m", holder="a", ttl=3600, json=False, path=str(ws)))
    assert not (ws / ".verity").exists()
