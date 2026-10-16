"""协作观测埋点（opt-in，默认关闭）。

依据 ``docs/collab.md`` §7.3：重评估信号采集。仅当团队显式开启时才记录，
默认零副作用（不建文件、不影响命令结果、不抛异常）。

开启方式（任一即可）：
- 环境变量 ``VL_TELEMETRY=1``（或 true/yes/on）
- ``RESEARCH.yaml`` 置 ``collab_telemetry: true``

记录到 ``<workspace>/.verity/collab-audit.jsonl``（JSONL，每行一条事件）。
观测失败（权限/磁盘）一律静默吞掉，绝不干扰主流程。

**范围**：本次仅覆盖写锁（acquire/release 冲突与授予）与 Git 假设分支（create/merge），
对应 §7.3 的「锁竞争事件 / 写锁绕过实例（holder vs vl_user 代理检测）/ merge 冲突」。
RAG 并发写入、精确的「VL_USER vs git committer」身份误配为后续扩展。
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
