"""verity-lens 编排层 CLI 入口（Orchestrator Lite）。

仅依赖标准库，保证在未安装第三方依赖时也能打印帮助。
已实现（Phase 0）：init / gate
Phase 1：loop / budget
Phase 2：bundle（工厂 + 校验）
Phase 3：lock / sandbox / branch
Phase 4：finalize（真实收尾闭环，含可复现元数据校验）
Phase 4c：bundle load（bundle.yml → HAL 注册，能力缺失显式降级）
Phase 4l：rag（文献 RAG 索引/检索接入编排 CLI，激活 rag_index_write 观测）
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from orchestrator.collab_telemetry import record

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
            record(
                workspace,
                "lock_acquire",
                {
                    "artifact": args.artifact,
                    "holder": holder,
                    "outcome": "rejected_conflict",
                    "existing_holder": (research.get("locks") or {})
                    .get(args.artifact, {})
                    .get("holder"),
                },
                research=research,
            )
            return EXIT_BLOCKED
        new_research, err = acquire_lock(
            research, args.artifact, holder, ttl_seconds=args.ttl
        )
        if err:
            print(f"[BLOCKED] {err}")
            record(
                workspace,
                "lock_acquire",
                {"artifact": args.artifact, "holder": holder, "outcome": "error"},
                research=research,
            )
            return EXIT_BLOCKED
        save_project(workspace, new_research)
        print(f"[lock] {args.artifact} 已锁定 by {holder}（TTL={args.ttl}s）")
        record(
            workspace,
            "lock_acquire",
            {"artifact": args.artifact, "holder": holder, "outcome": "granted"},
            research=research,
        )
        return EXIT_OK

    # action == release
    new_research = release_lock(research, args.artifact, holder=holder)
    save_project(workspace, new_research)
    print(f"[lock] {args.artifact} 已释放（by {holder}）")
    record(
        workspace,
        "lock_release",
        {"artifact": args.artifact, "holder": holder, "attempted": True},
        research=research,
    )
    return EXIT_OK


def cmd_bundle(args) -> int:
    """生成学科 L0 Bundle 骨架 / 校验结构 / 加载到运行底座。"""
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

    if args.action == "load":
        from orchestrator.bundle_loader import BundleLoadError, load_bundle

        try:
            report = load_bundle(Path(args.discipline), check_patch_schema=args.check_patch_schema)
        except BundleLoadError as exc:
            print(f"[ERROR] {exc}")
            return EXIT_ERROR
        if not report.ok:
            print(f"[BLOCKED] Bundle 加载失败（{len(report.problems)} 项）：")
            for i, msg in enumerate(report.problems, 1):
                print(f"  {i}. {msg}")
            return EXIT_BLOCKED
        print(f"[bundle] 已加载 {report.bundle}（{report.level}）")
        print(f"[bundle] Skill 注册: {len(report.skills)} 个")
        if report.mcp_servers:
            print(f"[bundle] MCP 声明: {', '.join(report.mcp_servers)}")
        if report.model_tools:
            print(f"[bundle] 模型可见工具: {', '.join(report.model_tools)}")
        if report.preset:
            print(f"[bundle] Preset 补丁: {report.preset}"
                  + (f" → {report.patch_path}" if report.patch_path else ""))
        for msg in report.degradations:
            print(f"[DEGRADED] {msg}")
        for msg in report.warnings:
            print(f"[WARN] {msg}")
        if args.check_patch_schema and not report.warnings:
            print("[bundle] preset_patch 机读校验通过（DSH 配置 schema 已钉固）")
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
    """收尾校验与导出：门禁终态 + 可复现元数据完整度 + AI 贡献声明。

    就绪退出码 0；存在阻塞项退出码 2（便于 pre_session / CI 判定）。
    """
    from orchestrator.finalize import run_finalize

    workspace = Path(args.path)
    report = run_finalize(workspace, write_report=True)
    print(report.report_text)
    if report.ready:
        print(f"\n[finalize] 已生成 finalize_report.md（status=ready）")
        return EXIT_OK
    print(f"\n[BLOCKED] 收尾前置条件未满足（{len(report.blockers)} 项），见上方「遗留项」")
    return EXIT_BLOCKED


def _load_research_safe(workspace: Path) -> dict | None:
    """安全加载 RESEARCH.yaml（用于读取 collab_telemetry 配置）；失败返回 None。"""
    try:
        from orchestrator.gates import load_project

        return load_project(workspace)
    except Exception:
        return None


def cmd_branch(args) -> int:
    """Git 假设分支协作：create / merge / status。"""
    import os

    from orchestrator.collab import (
        check_merge_readiness,
        create_hypothesis_branch,
        current_branch,
        current_committer,
        merge_to_main,
    )
    from orchestrator.collab_telemetry import is_enabled, record

    workspace = Path(args.path)
    if args.action == "create":
        ok, info = create_hypothesis_branch(args.hypothesis_id, workspace)
        if not ok:
            print(f"[ERROR] {info}")
            return EXIT_ERROR
        print(f"[branch] 已切出假设分支: {info}")
        record(
            workspace,
            "branch_create",
            {"hypothesis_id": args.hypothesis_id, "branch": info},
            research=_load_research_safe(workspace),
        )
        return EXIT_OK

    if args.action == "status":
        state = check_merge_readiness(workspace)
        print(f"[branch] 当前分支: {state['branch']} | 就绪: {state['ready']}")
        for r in state["reasons"]:
            print(f"  - {r}")
        return EXIT_OK if state["ready"] else EXIT_BLOCKED

    # action == merge
    ok, info = merge_to_main(workspace)
    record(
        workspace,
        "branch_merge",
        {
            "outcome": "merged" if ok else "blocked",
            "branch": info if ok else None,
            "detail": None if ok else info,
        },
        research=_load_research_safe(workspace),
    )
    if not ok:
        print(f"[BLOCKED] 合并未完成: {info}")
        return EXIT_BLOCKED

    # 身份误配检测（§7.2 gap② / §7.3 身份误配信号）：committer vs VL_USER
    if is_enabled(_load_research_safe(workspace)):
        vl_user = os.environ.get("VL_USER")
        committer = current_committer(workspace)
        git_user = (committer or {}).get("name") if committer else None
        match = bool(vl_user) and bool(git_user) and vl_user == git_user
        record(
            workspace,
            "identity_mismatch",
            {
                "vl_user": vl_user,
                "git_user": git_user,
                "git_email": (committer or {}).get("email") if committer else None,
                "match": match,
                "context": "branch_merge",
            },
            research=_load_research_safe(workspace),
        )
    print(f"[branch] 已合并 {info} → main（--no-ff）")
    return EXIT_OK


def cmd_identity(args) -> int:
    """身份解析与可信度检查（协作重评估 P0：身份可信化，见 docs/collab.md §7.8）。

    解析 ``VL_USER`` 与 git committer 的一致性，并读取最新提交签名状态。
    ``--require`` 提供 CI 强制级别（set / coherent / signed），不满足时退出码 1。
    """
    from orchestrator import identity

    workspace = Path(args.path)
    ident = identity.resolve_identity(workspace)

    if args.json:
        print(json.dumps(ident.to_dict(), ensure_ascii=False))
    else:
        print(identity.render_report(ident))

    if args.require == "set":
        if not ident.vl_user:
            print("[FAIL] --require set: VL_USER 未设置（无法标识当前用户）")
            return EXIT_ERROR
    elif args.require == "coherent":
        if not ident.coherent:
            print("[FAIL] --require coherent: VL_USER 与 git committer 不一致（身份无法对应）")
            return EXIT_ERROR
    elif args.require == "signed":
        if ident.signature.get("status") != "G":
            print("[FAIL] --require signed: 最新提交未通过 GPG/SSH 签名校验（status="
                  + str(ident.signature.get("status")) + "）")
            return EXIT_ERROR
    return EXIT_OK


def _collect_rag_files(source: Path, patterns: list[str]) -> list[Path]:
    """递归收集匹配的文本文件；``source`` 为文件时直接返回该文件。"""
    if source.is_file():
        return [source]
    if not source.is_dir():
        return []
    out: list[Path] = []
    for pat in patterns:
        out.extend(source.rglob(pat))
    return sorted(set(out))


def _read_rag_text(fp: Path) -> str:
    """读取文本文件；剥离 YAML frontmatter（``--- ... ---``），避免把元数据当正文。"""
    try:
        raw = fp.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            raw = raw[end + 4:]
    return raw


def _rag_result_to_dict(result) -> dict:
    """将 RetrievalResult 转为可 JSON 序列化的 dict（供 --json）。"""
    return {
        "mode": result.mode,
        "warning": result.warning,
        "tokens_used": result.tokens_used,
        "citations": result.citations,
        "chunks": [
            {
                "chunk_id": c.chunk.chunk_id,
                "score": round(c.score, 4),
                "text": c.chunk.text,
                "metadata": c.chunk.metadata,
            }
            for c in result.chunks
        ],
    }


def _print_rag_result(result) -> None:
    print(
        f"[rag] 模式={result.mode} 命中={len(result.chunks)} 引用={len(result.citations)} "
        f"tokens={result.tokens_used}" + (" [软告警]" if result.warning else "")
    )
    if result.mode == "citation_only":
        print("[rag] 已达 token 硬上限，仅返回引用（citation-only 降级）：")
        for c in result.citations:
            print(f"  - {c.get('doi')} (score={c.get('score')}, chunk={c.get('chunk_id')})")
        return
    for i, sc in enumerate(result.chunks, 1):
        snippet = sc.chunk.text[:120].replace("\n", " ")
        print(f"  {i}. [{sc.score:.3f}] {sc.chunk.metadata.get('doi', '')}")
        print(f"     {snippet}")


def cmd_rag(args) -> int:
    """文献 RAG 索引与检索（sidecar 接入编排层，Backlog C ①）。

    - ``index``：把本地文献（目录递归 / 单文件）分片嵌入，持久化到
      ``<workspace>/.verity/rag-index.json``（跨进程共享）。实例化 ``LiteratureIndex`` 时
      注入 ``rag_write_observer(workspace)``，opt-in 开启时自动记录 ``rag_index_write`` 事件
      （见 docs/collab.md §7.7）。
    - ``query``：从持久化索引检索，输出命中（或 token 超硬上限时 citation-only 降级）。

    不改变协作模型本身——仅为已就绪的 RAG 埋点提供真实可用的 CLI 入口。
    """
    from orchestrator.collab_telemetry import rag_write_observer
    from sidecar.rag.literature_rag import (
        LiteratureIndex,
        LiteratureRAG,
        chunk_document,
        load_index,
        save_index,
    )

    workspace = Path(args.path)
    index_path = workspace / ".verity" / "rag-index.json"

    if args.action == "index":
        if not args.target:
            print("[ERROR] index 需要提供目录或文件：vl rag index <目录或文件>")
            return EXIT_ERROR
        source = Path(args.target)
        if not source.exists():
            print(f"[ERROR] 索引源不存在: {source}")
            return EXIT_ERROR
        patterns = [p.strip() for p in args.glob.split(",") if p.strip()]
        files = _collect_rag_files(source, patterns)
        if not files:
            print(f"[WARN] 未匹配到可索引文本文件: {source} (patterns={patterns})")
            return EXIT_OK

        existing = (
            None
            if args.reset
            else load_index(index_path, write_observer=rag_write_observer(workspace))
        )
        index = existing or LiteratureIndex(write_observer=rag_write_observer(workspace))

        known_ids = {c.chunk_id for c in index._chunks}
        added_files = 0
        added_chunks = 0
        for fp in files:
            text = _read_rag_text(fp)
            if not text.strip():
                continue
            doc_id = fp.resolve().as_posix()
            chunks = chunk_document(
                text, metadata={"doi": doc_id, "source": str(fp), "doc_path": str(fp)}
            )
            fresh = [c for c in chunks if c.chunk_id not in known_ids]
            if fresh:
                index.add(fresh)
                known_ids.update(c.chunk_id for c in fresh)
                added_chunks += len(fresh)
            added_files += 1
        save_index(index, index_path)
        print(
            f"[rag] 已处理 {added_files}/{len(files)} 个文件，新增 {added_chunks} 个分片"
            f"（索引共 {index.size} 分片）→ {index_path}"
        )
        return EXIT_OK

    # action == query
    if not args.query:
        print("[ERROR] query 需要提供检索语句：vl rag query --query \"...\"")
        return EXIT_ERROR
    index = load_index(index_path)
    if index is None or index.size == 0:
        print("[rag] 索引为空，请先运行 `vl rag index <目录或文件>`")
        return EXIT_OK

    from copy import deepcopy

    from sidecar.rag.literature_rag import CONFIG, OFFLINE_SCORE_THRESHOLD

    cfg = deepcopy(CONFIG)
    # 离线默认 hash 嵌入器相似度量级低于真实稠密嵌入：未显式指定阈值时用放宽值保证可用
    cfg["retrieval"]["score_threshold"] = (
        args.min_score if args.min_score is not None else OFFLINE_SCORE_THRESHOLD
    )
    rag = LiteratureRAG(index=index, config=cfg)
    result = rag.retrieve(
        args.query, top_k=args.top_k, force_citation_only=args.force_citation_only
    )
    if args.json:
        print(json.dumps(_rag_result_to_dict(result), ensure_ascii=False))
    else:
        _print_rag_result(result)
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
    p = argparse.ArgumentParser(prog="vl", description="verity-lens 编排层 CLI")
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

    sp = sub.add_parser("bundle", help="生成 / 校验 / 加载学科 Bundle")
    sp.add_argument(
        "action",
        nargs="?",
        default="new",
        choices=["new", "validate", "load"],
        help="new=生成 L0 骨架；validate=校验结构；load=加载到运行底座（HAL 注册）",
    )
    sp.add_argument(
        "discipline",
        nargs="?",
        help="学科标识；validate/load 时传 Bundle 目录路径（--interview 时可省略）",
    )
    sp.add_argument("--path", default="bundles", help="Bundle 根目录（new 时）")
    sp.add_argument("--capability", default="core", help="首个 Skill 的能力名（new 时）")
    sp.add_argument("--interview", action="store_true", help="输出领域专家访谈提纲")
    sp.add_argument(
        "--check-patch-schema",
        action="store_true",
        help="load 时：对 preset_patch 做严格 JSON Schema 机读校验，并钉固真实 DSH 配置 schema（可选增强，默认关闭）",
    )
    sp.set_defaults(func=cmd_bundle)

    sp = sub.add_parser("finalize", help="收尾校验与导出")
    sp.add_argument("--path", default=".", help="Workspace 目录")
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

    sp = sub.add_parser("identity", help="身份解析与可信度检查（P0 身份可信化）")
    sp.add_argument("--path", default=".", help="Git 仓库目录")
    sp.add_argument(
        "--require",
        choices=["set", "coherent", "signed"],
        default=None,
        help="CI 强制级别：set=必须设 VL_USER；coherent=VL_USER 须匹配 git committer；"
             "signed=最新提交须通过 GPG/SSH 签名校验",
    )
    sp.add_argument("--json", action="store_true", help="输出 JSON（供 CI/hook 解析）")
    sp.set_defaults(func=cmd_identity)

    sp = sub.add_parser("rag", help="文献 RAG 索引与检索（sidecar 接入，Backlog C ①）")
    sp.add_argument("action", choices=["index", "query"])
    sp.add_argument("target", nargs="?", default=None, help="index：待索引的目录或文件")
    sp.add_argument("--query", default=None, help="query：检索语句")
    sp.add_argument("--path", default=".", help="Workspace 目录（索引落盘根）")
    sp.add_argument(
        "--glob",
        default="*.md,*.txt,*.rst,*.tex",
        help="index：递归匹配的文件模式（逗号分隔，默认 *.md,*.txt,*.rst,*.tex）",
    )
    sp.add_argument("--top-k", type=int, default=None, help="query：返回条数（默认 CONFIG top_k=8）")
    sp.add_argument(
        "--min-score",
        type=float,
        default=None,
        help="query：最低相似度阈值（默认自动：离线 hash 嵌入器放宽为 0.05；接入真实嵌入模型后可显式指定，如 0.72）",
    )
    sp.add_argument("--reset", action="store_true", help="index：清空已有索引后重建")
    sp.add_argument("--json", action="store_true", help="query：输出 JSON")
    sp.add_argument(
        "--force-citation-only",
        action="store_true",
        help="query：强制 citation-only 降级（仅返回引用，不注入全文）",
    )
    sp.set_defaults(func=cmd_rag)

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
