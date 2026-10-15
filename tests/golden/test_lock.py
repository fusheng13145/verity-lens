"""制品写锁单元测试（orchestrator/lock.py）。"""
from datetime import datetime, timedelta, timezone

from orchestrator.lock import (
    acquire_lock,
    check_locks,
    conflict_for_holder,
    is_expired,
    release_lock,
)


def _now() -> datetime:
    return datetime(2026, 10, 15, 0, 0, 0, tzinfo=timezone.utc)


def test_acquire_then_conflict_by_other():
    now = _now()
    research = {"project_id": "p", "locks": {}}
    new_r, err = acquire_lock(research, "manuscript", "a", ttl_seconds=3600, now=now)
    assert err is None
    assert new_r["locks"]["manuscript"]["holder"] == "a"

    # 他人再获取 → 冲突
    _, err2 = acquire_lock(new_r, "manuscript", "b", ttl_seconds=3600, now=now)
    assert err2 is not None
    assert "researcher" not in err2  # 错误信息含 a，不误报 b


def test_same_holder_renews():
    now = _now()
    r1, _ = acquire_lock({"locks": {}}, "m", "a", ttl_seconds=3600, now=now)
    r2, err = acquire_lock(r1, "m", "a", ttl_seconds=7200, now=now)
    assert err is None
    exp = datetime.fromisoformat(r2["locks"]["m"]["expires_at"])
    assert exp == now + timedelta(seconds=7200)


def test_expired_lock_allows_takeover():
    now = _now()
    past = now - timedelta(seconds=10)
    expired_entry = {
        "holder": "a",
        "acquired_at": past.isoformat(),
        "expires_at": (past + timedelta(seconds=1)).isoformat(),
    }
    research = {"locks": {"m": expired_entry}}
    assert is_expired(expired_entry, now=now) is True
    r, err = acquire_lock(research, "m", "b", ttl_seconds=3600, now=now)
    assert err is None  # 过期锁可被他人接管
    assert r["locks"]["m"]["holder"] == "b"


def test_release_respects_holder():
    now = _now()
    r, _ = acquire_lock({"locks": {}}, "m", "a", ttl_seconds=3600, now=now)
    # b 不能释放 a 的锁
    r2 = release_lock(r, "m", holder="b")
    assert "m" in r2["locks"]
    # a 释放成功
    r3 = release_lock(r, "m", holder="a")
    assert "m" not in r3.get("locks", {})


def test_check_locks_splits_active_expired():
    now = _now()
    future = (now + timedelta(hours=1)).isoformat()
    stale = (now - timedelta(hours=1)).isoformat()
    research = {
        "locks": {
            "m": {"holder": "a", "acquired_at": now.isoformat(), "expires_at": future},
            "fig": {"holder": "b", "acquired_at": now.isoformat(), "expires_at": stale},
        }
    }
    state = check_locks(research, now=now)
    assert set(state["active"]) == {"m"}
    assert set(state["expired"]) == {"fig"}


def test_conflict_for_holder_none_when_free():
    now = _now()
    research = {"locks": {}}
    assert conflict_for_holder(research, "m", "a", now=now) is None
