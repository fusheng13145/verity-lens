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
    """制品写锁：acquire / release / check。

    写锁写在 RESEARCH.yaml 的 locks 字段；acquire 冲突（他人未过期锁）时退出码 2。
    """
    from orchestrator.gates import load_project, save_project
    from orchestrator.lock import (
        acquire_lock,
        check_locks,
        conflict_for_holder,
        release_lock,
    )

    workspace = Path(args.path)
    try:
        research = load_project(workspace)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        return EXIT_ERROR

    if args.action == "check":
        state = check_locks(research)
        if args.json:
            print(json.dumps(state, ensure_ascii=False))
            return EXIT_OK
        if state["active"]:
            print(f"[lock] 有效写锁（{len(state['active'])}）：")
            for name, e in state["active"].items():
                print(f"  - {name}: holder={e.get('holder')} expires={e.get('expires_at')}")
        else:
            print("[lock] 无有效写锁")
        if state["expired"]:
            print(f"[lock] 已过期待清理（{len(state['expired'])}）：{list(state['expired'])}")
        return EXIT_OK

    holder = args.holder
    if not holder:
        print("[ERROR] acquire/release 需要 --holder")
        return EXIT_ERROR

    if args.action == "acquire":
        conflict = conflict_for_holder(research, args.artifact, holder)
        if conflict:
            print(f"[BLOCKED] {conflict}")
            return EXIT_BLOCKED
        new_research, err = acquire_lock(
            research, args.artifact, holder, ttl_seconds=args.ttl
        )
        if err:
            print(f"[BLOCKED] {err}")
            return EXIT_BLOCKED
        save_project(workspace, new_research)
        print(f"[lock] {args.artifact} 已锁定 by {holder}（TTL={args.ttl}s）")
        return EXIT_OK

    # action == release
    new_research = release_lock(research, args.artifact, holder=holder)
    save_project(workspace, new_research)
    print(f"[lock] {args.artifact} 已释放（by {holder}）")
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


def cmd_branch(args) -> int:
    """Git 假设分支协作：create / merge / status。"""
    from orchestrator.collab import (
        check_merge_readiness,
        create_hypothesis_branch,
        current_branch,
        merge_to_main,
    )

    workspace = Path(args.path)
    if args.action == "create":
        ok, info = create_hypothesis_branch(args.hypothesis_id, workspace)
        if not ok:
            print(f"[ERROR] {info}")
            return EXIT_ERROR
        print(f"[branch] 已切出假设分支: {info}")
        return EXIT_OK

    if args.action == "status":
        state = check_merge_readiness(workspace)
        print(f"[branch] 当前分支: {state['branch']} | 就绪: {state['ready']}")
        for r in state["reasons"]:
            print(f"  - {r}")
        return EXIT_OK if state["ready"] else EXIT_BLOCKED

    # action == merge
    ok, info = merge_to_main(workspace)
    if not ok:
        print(f"[BLOCKED] 合并未完成: {info}")
        return EXIT_BLOCKED
    print(f"[branch] 已合并 {info} → main（--no-ff）")
    return EXIT_OK


def cmd_sandbox(args) -> int:
    """生成项目专属沙箱 compose（依据 design-blueprint.md §2.8.2）。"""
    from orchestrator.sandbox import (
        generate,
        missing_host_dirs,
        render_compose,
        validate_compose,
    )

    project_id = args.project_id
    if args.check:
        text = render_compose(project_id, workspace_root=args.workspace_root)
        problems = validate_compose(text)
        if problems:
            print(f"[BLOCKED] 沙箱基线缺失（{len(problems)}）：")
            for i, m in enumerate(problems, 1):
                print(f"  {i}. {m}")
            return EXIT_BLOCKED
        print("[PASS] 沙箱 compose 满足最小安全基线")
        return EXIT_OK

    dest = generate(project_id, workspace_root=args.workspace_root, out_dir=args.out_dir)
    print(f"[sandbox] 已生成: {dest}")
    missing = missing_host_dirs(project_id, workspace_root=args.workspace_root)
    if missing:
        print(f"[WARN] 宿主目录缺失（沙箱运行前需创建）：{missing}")
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
    sp.add_argument("action", choices=["acquire", "release", "check"])
    sp.add_argument("artifact", nargs="?", default=None, help="制品名（check 时可省略）")
    sp.add_argument("--holder", default=None, help="持有者标识（如 researcher_b）")
    sp.add_argument("--ttl", type=int, default=48 * 3600, help="锁有效期（秒），默认 48h")
    sp.add_argument("--json", action="store_true", help="check：输出 JSON（供 hook 解析）")
    sp.add_argument("--path", default=".", help="Workspace 目录")
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

    sp = sub.add_parser("sandbox", help="生成容器沙箱 compose")
    sp.add_argument("project_id")
    sp.add_argument("--workspace-root", default="workspaces", help="Workspace 根目录")
    sp.add_argument("--out-dir", default="docker", help="compose 输出目录")
    sp.add_argument("--check", action="store_true", help="仅校验安全基线，不写文件")
    sp.set_defaults(func=cmd_sandbox)

    sp = sub.add_parser("branch", help="Git 假设分支协作")
    sp.add_argument("action", choices=["create", "merge", "status"])
    sp.add_argument("hypothesis_id", nargs="?", default=None, help="假设 ID（create 时必填）")
    sp.add_argument("--path", default=".", help="项目（Git 仓库）目录")
    sp.set_defaults(func=cmd_branch)

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
