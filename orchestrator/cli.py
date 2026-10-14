"""VerityLens 编排层 CLI 入口（Orchestrator Lite）。

仅依赖标准库，保证在未安装第三方依赖时也能打印帮助。
已实现（Phase 0）：init / gate
按路线图待实现（Phase 1-3）：loop / budget / lock / bundle（Phase 2）/ finalize
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PHASES: tuple[str, ...] = ("literature", "question", "experiment", "analysis", "writing")
CATEGORIES: tuple[str, ...] = ("EXEC", "DATA", "METH", "HYP", "EPIS")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BLOCKED = 2
EXIT_HARD_BLOCK = 3


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
    """扫描未处理的 failed 实验；存在则阻塞（退出码 2）。"""
    from orchestrator.failure_loop import find_unresolved_failures, route, validate_entry

    workspace = Path(args.path)
    if not workspace.exists():
        print(f"[ERROR] Workspace 不存在: {workspace}")
        return EXIT_ERROR

    unresolved = find_unresolved_failures(workspace)
    if not unresolved:
        print("[loop] 无未处理的失败实验，允许继续")
        return EXIT_OK

    print(f"[BLOCKED] 存在未处理的 failed 实验（{len(unresolved)} 项）：")
    for i, exp_id in enumerate(unresolved, 1):
        print(f"  {i}. {exp_id} → 需生成归因条目并人工批准后转终态")
    if args.route:
        print("\n路由建议：")
        for exp_id in unresolved:
            draft = {
                "id": "F-000",
                "experiment_id": exp_id,
                "hypothesis_id": "UNKNOWN",
                "phase": "experiment",
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "classification": {
                    "category": args.route,
                    "code": f"{args.route}-AUTO",
                    "confidence": 0.5,
                },
                "decision": {"type": "retry_execution"},
            }
            errs = validate_entry(draft)
            tag = "草稿有效" if not errs else f"草稿待补字段: {errs}"
            print(f"  - {exp_id} [{args.route}] {tag}")
    print("\n下一步：运行 vl loop 前先登记 failure_ledger 条目")
    return EXIT_BLOCKED


def cmd_budget(args) -> int:
    """预算硬阻断检查；超限退出码 3，≥70% 告警。"""
    from orchestrator.gates import load_project

    workspace = Path(args.path)
    try:
        project = load_project(workspace)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        return EXIT_ERROR

    budget = project.get("token_budget") or {}
    total = budget.get("total") or {}
    cap = float(total.get("cap") or 0)
    used = float(total.get("used") or 0)
    ratio = (used / cap) if cap else 0.0

    if cap and used >= cap:
        print("[HARD_BLOCK] 预算已耗尽，暂停会话；恢复选项：")
        print("  A. 人工批准追加预算（+20%）")
        print("  B. 切换廉价模型继续（质量可能下降）")
        print("  C. 手动介入完成剩余工作")
        return EXIT_HARD_BLOCK
    if ratio >= 0.7:
        print(f"[SOFT_WARNING] 预算使用率 {ratio:.0%}（{used:.0f}/{cap:.0f}）")
        return EXIT_OK
    print(f"[budget] 使用率 {ratio:.0%}（{used:.0f}/{cap:.0f}），正常")
    return EXIT_OK


def cmd_lock(args) -> int:
    """制品写锁（Phase 3 实现）。"""
    print(f"[lock] {args.action} {args.artifact}：Phase 3 待实现")
    return EXIT_OK


def cmd_bundle(args) -> int:
    """生成学科 L0 Bundle 骨架，或校验已有 Bundle 结构。"""
    from orchestrator.bundle_factory import (
        BundleExistsError,
        INTERVIEW_TEMPLATE,
        new_bundle,
        validate_bundle,
    )

    if args.interview:
        print(INTERVIEW_TEMPLATE)
        return EXIT_OK

    if args.action == "validate":
        problems = validate_bundle(Path(args.discipline))
        if problems:
            print(f"[BLOCKED] Bundle 结构不合规（{len(problems)} 项）：")
            for i, msg in enumerate(problems, 1):
                print(f"  {i}. {msg}")
            return EXIT_BLOCKED
        print("[PASS] Bundle 结构合规")
        return EXIT_OK

    # action == new
    try:
        dest = new_bundle(args.discipline, args.path, capability=args.capability)
    except (BundleExistsError, FileNotFoundError) as exc:
        print(f"[ERROR] {exc}")
        return EXIT_ERROR
    print(f"[bundle] 已生成 L0 骨架: {dest}")
    print(f"[bundle] Skill: {dest / 'skills' / (args.discipline + '-' + args.capability) / 'SKILL.md'}")
    print("下一步：请领域专家填写 SKILL.md 中的 TODO 部分")
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
    sp.add_argument("--path", default=".", help="Workspace 目录")
    sp.add_argument(
        "--route",
        choices=list(CATEGORIES),
        help="按指定失败分类生成路由建议（用于草稿验证）",
    )
    sp.set_defaults(func=cmd_loop)

    sp = sub.add_parser("budget", help="预算硬阻断检查")
    sp.add_argument("action", nargs="?", default="check")
    sp.add_argument("--path", default=".", help="Workspace 目录")
    sp.set_defaults(func=cmd_budget)

    sp = sub.add_parser("lock", help="制品写锁")
    sp.add_argument("action", choices=["acquire", "release"])
    sp.add_argument("artifact")
    sp.set_defaults(func=cmd_lock)

    sp = sub.add_parser("bundle", help="生成 / 校验学科 Bundle")
    sp.add_argument(
        "action",
        nargs="?",
        default="new",
        choices=["new", "validate"],
        help="new=生成 L0 骨架；validate=校验结构",
    )
    sp.add_argument(
        "discipline",
        nargs="?",
        help="学科标识；validate 时传 Bundle 目录路径（--interview 时可省略）",
    )
    sp.add_argument("--path", default="bundles", help="Bundle 根目录（new 时）")
    sp.add_argument("--capability", default="core", help="首个 Skill 的能力名（new 时）")
    sp.add_argument("--interview", action="store_true", help="输出领域专家访谈提纲")
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
