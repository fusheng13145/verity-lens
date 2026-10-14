"""VerityLens 编排层 CLI 入口（Orchestrator Lite）。

仅依赖标准库，保证在未安装第三方依赖时也能打印帮助。
已实现（Phase 0）：init / gate
按路线图待实现（Phase 1-3）：loop / budget / lock / bundle（Phase 2）/ finalize
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PHASES: tuple[str, ...] = ("literature", "question", "experiment", "analysis", "writing")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BLOCKED = 2


# ── 子命令实现 ────────────────────────────────────────────────────────

def cmd_init(args) -> int:
    """生成 Workspace 脚手架并挂载 L0 Bundle 骨架。"""
    workspace = Path(args.path) / args.project_id
    if workspace.exists() and any(workspace.iterdir()):
        print(f"[ERROR] Workspace 已存在且非空: {workspace}")
        return EXIT_ERROR

    dirs = [
        "docs",
        "experiments",
        "data/raw",
        "data/processed",
        "figures",
        "manuscript",
        "analysis",
    ]
    for d in dirs:
        (workspace / d).mkdir(parents=True, exist_ok=True)

    research = f"""project_id: "{args.project_id}"
discipline: "{args.discipline}"
title: ""
research_question: ""
current_phase: "literature"

approvals:
  question:
    approved_by: null
    approved_at: null
    note: null
  writing:
    approved_by: null
    approved_at: null
    note: null

locks: {{}}

degraded_features: []

hypotheses: []

model_config:
  primary: "deepseek-chat-v4-pro"
  fallback: "deepseek-chat-v4-flash"

token_budget:
  total:
    cap: 500000
    used: 0
  per_phase:
    literature: {{ cap: 100000, used: 0 }}
    question: {{ cap: 50000, used: 0 }}
    experiment: {{ cap: 200000, used: 0 }}
    analysis: {{ cap: 100000, used: 0 }}
    writing: {{ cap: 50000, used: 0 }}
"""
    (workspace / "RESEARCH.yaml").write_text(research, encoding="utf-8")

    (workspace / "docs" / "literature_notes.md").write_text(
        f"# 文献笔记 — {args.project_id}\n\n_待补充_\n", encoding="utf-8"
    )
    (workspace / "docs" / "hypothesis_tree.json").write_text(
        json.dumps(
            {
                "root_question": "",
                "nodes": [],
                "metadata": {"created_at": None, "updated_at": None, "version": 0},
        },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (workspace / "docs" / "failure_ledger.json").write_text(
        json.dumps({"entries": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (workspace / "docs" / "lessons.md").write_text(
        "# 失败模式库\n\n_由 failure_ledger 渲染_\n", encoding="utf-8"
    )
    (workspace / "analysis" / "summary.md").touch()

    print(f"[init] 已生成 Workspace: {workspace}")
    print("[init] 目录: docs/ experiments/ data/ figures/ manuscript/ analysis/")
    print("[init] 已挂载 L0 骨架（hypothesis_tree.json / failure_ledger.json）")
    return EXIT_OK


def cmd_gate(args) -> int:
    """校验阶段准入条件，输出三段式缺失清单。"""
    from orchestrator.gates import check_gate as _check

    workspace = Path(args.path)
    try:
        result = _check(args.phase, workspace)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return EXIT_ERROR

    print(result.render())
    return EXIT_OK if result.ok else EXIT_BLOCKED


def cmd_loop(args) -> int:
    """失败回流检查（Phase 1 实现）。"""
    print("[loop] 失败回流检查：Phase 1 待实现")
    return EXIT_OK


def cmd_budget(args) -> int:
    """预算硬阻断检查（Phase 1 实现）。"""
    print("[budget] 预算检查：Phase 1 待实现")
    return EXIT_OK


def cmd_lock(args) -> int:
    """制品写锁（Phase 3 实现）。"""
    print(f"[lock] {args.action} {args.artifact}：Phase 3 待实现")
    return EXIT_OK


def cmd_bundle(args) -> int:
    """Bundle 生成（Phase 2 实现）。"""
    print(f"[bundle] {args.action} {args.discipline}：Phase 2 待实现")
    return EXIT_OK


def cmd_finalize(args) -> int:
    """收尾导出（Phase 1 实现）。"""
    print("[finalize] 收尾导出：Phase 1 待实现")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vl", description="VerityLens 编排层 CLI")
    sub = p.add_subparsers(dest="command")

    sp = sub.add_parser("init", help="生成 Workspace 脚手架")
    sp.add_argument("project_id")
    sp.add_argument("discipline")
    sp.add_argument("--path", default="workspaces", help="Workspace 根目录")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("gate", help="阶段门禁校验")
    sp.add_argument("phase", choices=list(PHASES))
    sp.add_argument("--path", default=".", help="Workspace 目录")
    sp.set_defaults(func=cmd_gate)

    sp = sub.add_parser("loop", help="失败回流检查")
    sp.set_defaults(func=cmd_loop)

    sp = sub.add_parser("budget", help="预算硬阻断检查")
    sp.add_argument("action", nargs="?", default="check")
    sp.set_defaults(func=cmd_budget)

    sp = sub.add_parser("lock", help="制品写锁")
    sp.add_argument("action", choices=["acquire", "release"])
    sp.add_argument("artifact")
    sp.set_defaults(func=cmd_lock)

    sp = sub.add_parser("bundle", help="生成学科 Bundle")
    sp.add_argument("action", nargs="?", default="new")
    sp.add_argument("discipline")
    sp.set_defaults(func=cmd_bundle)

    sp = sub.add_parser("finalize", help="收尾导出")
    sp.set_defaults(func=cmd_finalize)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_OK
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
