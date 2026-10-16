"""协作观测埋点（opt-in，默认关闭）。

依据 ``docs/collab.md`` §7.3：重评估信号采集。仅当团队显式开启时才记录，
默认零副作用（不建文件、不影响命令结果、不抛异常）。

开启方式（任一即可）：
- 环境变量 ``VL_TELEMETRY=1``（或 true/yes/on）
- ``RESEARCH.yaml`` 置 ``collab_telemetry: true``

记录到 ``<workspace>/.verity/collab-audit.jsonl``（JSONL，每行一条事件）。
观测失败（权限/磁盘）一律静默吞掉，绝不干扰主流程。

**范围**：覆盖写锁（acquire/release 冲突与授予）、Git 假设分支（create/merge）、
merge 时的 committer 身份误配（``identity_mismatch``），以及 RAG 共享索引写入
（``rag_index_write``，通过 ``rag_write_observer`` 由编排层在实例化 RAG 时注入）。
对应 §7.3 的「锁竞争事件 / 写锁绕过实例 / merge 冲突 / 身份误配 / RAG 并发写入」。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUDIT_DIRNAME = ".verity"
AUDIT_FILENAME = "collab-audit.jsonl"


def is_enabled(research: dict[str, Any] | None = None) -> bool:
    """是否开启协作观测：环境变量优先，其次 RESEARCH.yaml 配置。"""
    env = (os.environ.get("VL_TELEMETRY") or "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if research and research.get("collab_telemetry") is True:
        return True
    return False


def _default_sink(workspace: Path) -> Path:
    return workspace / AUDIT_DIRNAME / AUDIT_FILENAME


def record(
    workspace: Path,
    event: str,
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
    enabled: bool | None = None,
    research: dict[str, Any] | None = None,
    sink: Path | None = None,
) -> bool:
    """记录一条协作事件到审计日志（opt-in）。

    参数：
    - ``workspace``：项目（workspace）目录。
    - ``event``：事件名（如 ``lock_acquire`` / ``branch_merge``）。
    - ``payload``：事件附带字段（artifact / holder / outcome 等）。
    - ``enabled``：显式覆盖开关（测试注入）；默认按 ``is_enabled(research)`` 判定。
    - ``research``：RESEARCH.yaml 字典，用于读取 ``collab_telemetry`` 配置。
    - ``sink``：审计文件路径（测试注入）；默认 ``<workspace>/.verity/collab-audit.jsonl``。

    返回是否实际写入；未开启或写入失败均返回 False 且不抛异常。
    """
    on = enabled if enabled is not None else is_enabled(research)
    if not on:
        return False
    now = now or datetime.now(timezone.utc)
    vl_user = os.environ.get("VL_USER") or None
    entry = {
        "ts": now.isoformat(),
        "event": event,
        "vl_user": vl_user,
        **payload,
    }
    target = sink or _default_sink(workspace)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except OSError:
        # 观测失败绝不阻塞主流程
        return False


def rag_write_observer(
    workspace: Path,
    research: dict[str, Any] | None = None,
) -> Callable[[str, dict[str, Any]], None]:
    """返回供 ``LiteratureIndex`` / ``LiteratureRAG`` 注入的写入观测回调（opt-in 透明）。

    编排层在实例化 RAG 时传入此回调，即可在 opt-in 开启时记录 ``rag_index_write`` 事件，
    默认（未开启）回调内部 ``record`` 直接返回，零副作用、不依赖 orchestrator 之外的任何东西。

    用法::

        from orchestrator.collab_telemetry import rag_write_observer
        idx = LiteratureIndex(write_observer=rag_write_observer(workspace))

    事件 ``rag_index_write`` payload：``op``（``add`` / ``archive``）+ 写入分片数 / doi 等。
    """
    def _obs(op: str, meta: dict[str, Any]) -> None:
        record(workspace, "rag_index_write", {"op": op, **meta}, research=research)
    return _obs
