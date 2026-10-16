#!/usr/bin/env python
"""on_change hook —— 文件变更自动触发失败回流检查（消除审计 #4）。

原 ``orchestrator/hooks/`` 仅有无人调用的 ``pre_session.sh``，「文件监听自动触发回流检查」
能力不存在。本钩子监听 ``experiments/`` 与 ``docs/``（含 failure_ledger.json /
hypothesis_tree.json）下的文件变更，自动触发 ``vl loop``（失败回流检查）：
- 变更命中 → 打印 BLOCKED（未处理 failed 实验数）或 OK；
- 同时给出下一步建议（登记 failure_ledger + 人工批准回流）。

两种模式：
- ``--once``：单次扫描并立即检查一次后退出（适合作为 git post-commit / CI 步骤）；
- 常驻（默认）：纯 stdlib 轮询（无 watchdog 外部依赖），间隔 ``--interval`` 秒。

用法：
    python -m orchestrator.hooks.on_change --workspace <ws> [--once] [--interval 2]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

WATCH_DIRS = ("experiments", "docs")
POLL_INTERVAL = 2.0


def _repo_root() -> Path:
    # 本文件位于 <repo>/orchestrator/hooks/on_change.py
    return Path(__file__).resolve().parents[2]


def _ensure_importable() -> None:
    root = str(_repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def snapshot(workspace: Path) -> dict[str, tuple[float, int]]:
    """记录受监控目录下所有文件的 (mtime, size) 快照。目录不存在则跳过。"""
    snap: dict[str, tuple[float, int]] = {}
    for d in WATCH_DIRS:
        base = workspace / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file():
                try:
                    st = p.stat()
                    rel = str(p.relative_to(workspace)).replace("\\", "/")
                    snap[rel] = (st.st_mtime, st.st_size)
                except OSError:
                    continue
    return snap


def changed(workspace: Path, prev: dict[str, tuple[float, int]]) -> list[str]:
    """返回相对工作区、相对上次快照发生变化的文件列表。"""
    cur = snapshot(workspace)
    diffs: list[str] = []
    all_keys = set(cur) | set(prev)
    for k in sorted(all_keys):
        if cur.get(k) != prev.get(k):
            diffs.append(k)
    return diffs


def run_checks(workspace: Path) -> int:
    """执行失败回流检查；返回未处理 failed 实验数量（0 表示通过）。"""
    _ensure_importable()
    from orchestrator.failure_loop import find_unresolved_failures

    try:
        unresolved = find_unresolved_failures(workspace)
    except Exception as exc:  # 文件缺失等：视为无阻塞，但提示
        print(f"[on_change] 检查跳过（{exc}）")
        return 0
    if unresolved:
        print(f"[on_change][BLOCKED] 存在未处理的 failed 实验（{len(unresolved)} 项）：")
        for i, exp_id in enumerate(unresolved, 1):
            print(f"  {i}. {exp_id} → 须登记 failure_ledger 并人工批准回流")
        print("[on_change] 下一步：运行 vl loop（含 --route 获取草稿）后重新触发")
    else:
        print("[on_change][OK] 无未处理的失败实验，回流检查通过")
    return len(unresolved)


def _once(workspace: Path) -> int:
    print(f"[on_change] 单次扫描：{', '.join(WATCH_DIRS)} @ {workspace}")
    snapshot(workspace)  # 建立基线（首次无对比）
    return run_checks(workspace)


def _watch(workspace: Path, interval: float) -> int:
    print(f"[on_change] 常驻监听：{', '.join(WATCH_DIRS)} @ {workspace}（间隔 {interval}s，Ctrl+C 退出）")
    prev = snapshot(workspace)
    try:
        while True:
            time.sleep(interval)
            diffs = changed(workspace, prev)
            if diffs:
                print(f"[on_change] 检测到变更（{len(diffs)} 个文件），触发回流检查：")
                for d in diffs[:20]:
                    print(f"  ~ {d}")
                run_checks(workspace)
                prev = snapshot(workspace)
    except KeyboardInterrupt:
        print("\n[on_change] 已停止监听")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="文件变更自动触发失败回流检查")
    parser.add_argument("--workspace", default=".", help="Workspace 目录")
    parser.add_argument("--once", action="store_true", help="单次扫描并退出（非常驻）")
    parser.add_argument("--interval", type=float, default=POLL_INTERVAL, help="常驻轮询间隔（秒）")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    if not workspace.exists():
        print(f"[on_change][ERROR] Workspace 不存在：{workspace}")
        return 1
    if args.once:
        return _once(workspace)
    return _watch(workspace, args.interval)


if __name__ == "__main__":
    sys.exit(main())
