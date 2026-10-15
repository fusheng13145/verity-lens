"""制品写锁协议（orchestrator/lock.py）。

设计要点（依据 design-blueprint.md §2.5.2 / 边界 E4/E15）：
- 写锁写在 RESEARCH.yaml 的 ``locks`` 字段，key 为制品名（如 ``manuscript``）。
- 每个锁条目含 holder / acquired_at / expires_at；**超时自动失效**，防止死锁。
- 同一制品已有他人未过期锁时，acquire 冲突被拒绝（先到先得）。
- 纯函数优先：本模块以"research 字典"为输入/输出，文件读写由调用方负责，便于单测。
- 时间使用带时区的 UTC；now 可注入以支持确定性测试。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

DEFAULT_TTL_SECONDS = 48 * 3600  # 默认 48 小时，与蓝图 E4 超时失效一致


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    # 兼容 ISO-8601（含 Z 与偏移）
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def is_expired(entry: dict[str, Any], now: datetime | None = None) -> bool:
    """锁条目是否已过期（expires_at 早于 now）。"""
    now = now or _now()
    exp = _parse(entry.get("expires_at"))
    if exp is None:
        # 缺 expires_at 视为立即失效，避免永久死锁
        return True
    return exp <= now


def active_locks(locks: dict[str, Any], now: datetime | None = None) -> dict[str, dict]:
    """返回未过期的锁（剔除已过期条目）。"""
    now = now or _now()
    return {
        name: entry
        for name, entry in (locks or {}).items()
        if not is_expired(entry, now)
    }


def acquire_lock(
    research: dict[str, Any],
    artifact: str,
    holder: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: datetime | None = None,
) -> tuple[dict[str, Any], str | None]:
    """尝试为 holder 获取 artifact 的写锁。

    返回 (新的 research, 冲突信息)。冲突信息为 None 表示成功获取/续期。
    若已有他人未过期锁，则拒绝并返回冲突提示（不修改 research）。
    """
    if not artifact or not holder:
        raise ValueError("artifact 与 holder 均不可为空")
    now = now or _now()
    locks = dict(research.get("locks") or {})
    existing = locks.get(artifact)
    if existing is not None and not is_expired(existing, now):
        if existing.get("holder") != holder:
            return research, (
                f"冲突：{artifact} 已被 {existing.get('holder')} 持有"
                f"（至 {existing.get('expires_at')}）"
            )
        # 同一 holder 续期（覆盖）
    acquired_at = now.isoformat()
    expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()
    new_entry = {
        "holder": holder,
        "acquired_at": acquired_at,
        "expires_at": expires_at,
        "artifact": artifact,
    }
    new_locks = {**locks, artifact: new_entry}
    new_research = {**research, "locks": new_locks}
    return new_research, None


def release_lock(
    research: dict[str, Any],
    artifact: str,
    holder: str | None = None,
) -> dict[str, Any]:
    """释放 artifact 的写锁。若指定 holder，仅当持有人匹配才释放（避免误释放他人锁）。"""
    locks = dict(research.get("locks") or {})
    existing = locks.get(artifact)
    if existing is None:
        return research
    if holder is not None and existing.get("holder") != holder:
        # 不允许释放他人锁；返回原样
        return research
    locks.pop(artifact, None)
    return {**research, "locks": locks}


def check_locks(
    research: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """汇总当前锁状态：active（有效）、expired（已失效待清理）。

    冲突判断依赖具体 holder，使用 :func:`conflict_for_holder`。
    """
    now = now or _now()
    locks = research.get("locks") or {}
    active: dict[str, dict] = {}
    expired: dict[str, dict] = {}
    for name, entry in locks.items():
        if is_expired(entry, now):
            expired[name] = entry
        else:
            active[name] = entry
    return {"active": active, "expired": expired}


def conflict_for_holder(
    research: dict[str, Any],
    artifact: str,
    holder: str,
    now: datetime | None = None,
) -> str | None:
    """判断 holder 能否安全写入 artifact：若有效锁由他人持有则报冲突。"""
    now = now or _now()
    existing = (research.get("locks") or {}).get(artifact)
    if existing is None or is_expired(existing, now):
        return None
    if existing.get("holder") != holder:
        return (
            f"冲突：{artifact} 已被 {existing.get('holder')} 持有"
            f"（至 {existing.get('expires_at')}）"
        )
    return None
