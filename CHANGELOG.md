# CHANGELOG.md — 版本更新记录

> 遵循 Keep a Changelog 风格，版本号 `MAJOR.MINOR.PATCH`。

## [1.7.0] - 2026-10-15 — Phase 4a（学科扩展 + 收尾闭环）

### Added
- **第二学科 Bundle：materials（材料科学）L0→L1**：
  - 由 `vl bundle new materials --capability characterization` 生成 L0 骨架，验证"换 Bundle 即切换学科"；
  - 填充 `materials-characterization` SKILL.md（表征不确定度规范：不确定度必报 / n≥3 / 单位 / 仪器 / XRD·BET·Tauc 约束）+ `materials-literature` SKILL.md（实验 vs 计算证据、测试条件对齐）；
  - L1 验证脚本 `scripts/validate_report.py`（确定性：不确定度合法、n≥3、单位非空、方法非空）；
  - 术语表 `references/materials_terminology.json`；`bundle.yml` 升 L1 并声明两个 Skill；`vl bundle validate` 通过。
- **实验可复现元数据**：`experiment.schema.json` 新增可选 `reproducibility` 对象（model / tokens_used / random_seed / data_hash / environment / generated_at），支撑 manifest 概念（蓝图 §2.5.3 / §4.5）。
- **`vl finalize` 真实收尾闭环** `orchestrator/finalize.py`：
  - 收尾前置校验：全部实验终态 + 无未处理失败实验 + analysis/summary.md 就绪 + figures 就绪；
  - 可复现性完整度：completed 实验须带齐 model / data_hash / random_seed，否则阻断（科研诚信：无 manifest 无法复现）；
  - 生成 `finalize_report.md`（门禁状态 / 可复现性 / AI 贡献声明草稿 / 遗留项）；就绪退出码 0，阻塞退出码 2。

### Changed
- `orchestrator/cli.py`：`cmd_finalize` 由占位桩替换为真实实现，并补 `--path` 参数。
- `docs/bundle-registry.md`：materials 登记为 L1 已交付；biomed 标注为 L1。
- `docs/interfaces.md`：CLI 契约表补全 `lock` / `bundle validate` / `finalize` / `sandbox` / `branch`，并标注各命令实现状态。

### Tests
- `tests/schema/test_bundle_factory.py`：新增"第二学科可生成并校验" + 锁定 materials Bundle 结构合规（共 +2）。
- `tests/finalize/test_finalize.py`：新增 6 例（ready / 缺 summary / 缺 figure / 未处理 failed / 缺可复现元数据 / 报告落盘）。
- 全量 **100 个用例**通过（原 92 + 新增 8）。

## [1.6.0] - 2026-10-15 — Phase 3 完成（健壮性与协作）

### Added
- **容器沙箱**：`docker/sandbox-compose.yml`（no-new-privileges / cap_drop ALL / network_mode none
  / read_only / tmpfs / cpus·memory·pids 资源硬限；data/raw 只读、data/processed 可写）+ 生成器
  `orchestrator/sandbox.py`（按 PROJECT_ID 渲染 + `validate_compose` 安全基线静态校验）+ `vl sandbox` 命令。
- **RAG 侧车完整版** `sidecar/rag/literature_rag.py` 重写：语义分片（字符窗口 + overlap）、可插拔嵌入
  （默认离线确定性 hash 向量）、向量检索 + 分数阈值、MMR 多样性重排、会话缓存（LRU）、token 预算
  （软告警 / 硬上限触发 citation-only 降级）、auto-archive（超龄分片仅留元数据）。
- **制品写锁** `orchestrator/lock.py`：acquire/release/check + 超时自动失效（默认 48h）+ 冲突检测
  （先到先得，他人未过期锁拒绝接管）；`vl lock acquire/release/check`；`research.schema.json` 约束
  `locks` 结构（holder/acquired_at/expires_at）。
- **Git 分支协作流** `orchestrator/collab.py`：假设分支创建（`hypothesis/<id>`）+ 合并前就绪检查
  （无未处理 failed 实验 + 阶段门禁通过）+ `--no-ff` 合并；`vl branch create/merge/status`；
  `docs/collab.md` 写明协作边界、写锁协议、分支保护建议。
- **文档**：新增 `docs/collab.md`、`docker/sandbox.md`。
- **测试**：92 个用例全通过（新增 lock / rag / sandbox / collab 共 27 例）。

### Changed
- `orchestrator/gates.py` 新增 `save_project(workspace, data)`（保留中文与字段序写回 RESEARCH.yaml）。
- `orchestrator/cli.py` 文档字符串更新为已实现的命令集。

### Note
- `pre_session.sh` 第④步写锁自动检查因安全审查未自动写入会话启动钩子；推荐片段已记录在
  `docs/collab.md` §6，供团队按需启用。

## [1.5.0] - 2026-10-15 — Phase 2 完成（领域包化 + 级联回流）

### Added
- **Bundle 工厂** `orchestrator/bundle_factory.py`（由占位改为可用）：
  - `new_bundle(discipline, target_dir, capability)`：复制 `_template/`、替换
    `${DISCIPLINE}` / `${CAPABILITY}` 占位符、重命名 Skill 目录为 `<discipline>-<capability>`
  - `validate_bundle(dir)`：结构校验（必填字段 / level 枚举 / 声明 Skill 存在性）
  - `INTERVIEW_TEMPLATE`：领域专家访谈提纲（新增 `vl bundle --interview` 输出）
- **L0 模板** `bundles/_template/`：bundle.yml + `skills/capability/SKILL.md`（含 TODO 占位）。
- **biomed 升级至 L1**：新增 `skills/biomed-stats/scripts/validate_report.py`
  确定性校验（缺失字段 / CI 区间合法性 / p 值 0–1 / 需 CI 指标）。
- **级联回流** `cascade_impact()`：根假设证伪/放弃时，沿 children 链传播——
  派生假设置 `revised`、其下实验置 `abandoned`，并写 `cascade_note` 留存影响来源。
- **测试**：65 个用例全通过（新增 12 个：Bundle 工厂 + 级联回流）。

## [1.4.0] - 2026-10-15 — Phase 1 完成（失败驱动迭代闭环）

### Added
- **失败驱动迭代模块** `orchestrator/failure_loop.py`：
  - 未处理 failed 检测（`find_unresolved_failures` / `check_loop`，阻塞后续阶段）
  - 条目 Schema 校验（`validate_entry`，对齐 failure_ledger.schema.json）
  - 确定性工具复核（`verify_with_sidecar`，依赖缺失时降级为 skipped）
  - 五类路由（`route`）：EXEC→自动重试(≤3，超限升级 HITL)；DATA→补充数据+挂起；
    METH→修订实验 exp_N+1；HYP→refuted/revised；EPIS→修订前提
  - 决策落盘（`apply_decision`）：实验转终态 + 假设树状态/置信度更新 +
    证据链写入 provenance.justified_by + ledger 追加 + lessons.md 渲染
- **biomed L0 Bundle**：`bundles/biomed/`（bundle.yml + biomed-stats / biomed-literature
  两份 SKILL.md + `references/biomed_terminology.json`）。
- **CLI**：`vl loop`（扫描未处理失败，阻塞退出码 2，支持 `--route` 生成路由建议）
  与 `vl budget check`（≥100% 硬阻断退出码 3，≥70% 告警）真实实现。
- **测试**：53 个用例全通过（含五类路由、低置信度强制 HITL、重试上限升级、落盘一致性）。

## [1.3.0] - 2026-10-15 — Phase 0 完成

### Added
- **HAL 适配层实现**：`hal/interface.py`（`HarnessAdapter` Protocol + `CAPABILITY_KEYS`）、
  `hal/dsh_adapter.py`（`SessionHandle` / `ToolSpec` / `PresetPatch` / `SubagentSpec` + 子进程封装与优雅降级）、
  `hal/capability_probe.py`（读 version_lock 探测能力）。
- **数据 Schema**：`orchestrator/schemas/` 下四大 JSON Schema（research / hypothesis_tree / experiment / failure_ledger），
  含假设树无环注解与终态枚举。
- **编排层门禁引擎**：`orchestrator/gates.py` 纯函数（`load_project` / `compute_facts` / `check_file` / `check_gate` / `validate_acyclic`），
  声明式命名事实 + 三段式缺失清单输出；CLI 实现 `vl init` / `vl gate`（含退出码 0/1/2）。
- **Headless API**：`orchestrator/api.py`（FastAPI），供 Web 前端读取项目/阶段/假设树/实验/失败登记簿，
  并支持 HITL 审批与失败登记（强制 `decision.approved_by`）。
- **通用 Skill**：`skills/literature/SKILL.md`（含方法论约束与输出 Schema）。
- **确定性工具**：`sidecar/tools/stat_test.py`（t 检验 / Welch / Mann-Whitney + Cohen's d + 95% CI）、
  `sidecar/tools/doi_verify.py`（DOI 归一化 + Crossref 校验 + 网络降级）。
- **测试**：36 个用例全通过（Layer1 Schema 校验 + Layer4 HAL 契约 + API 契约 + 门禁引擎）。
- **工程**：`Makefile`（schema-check / golden / hal-contract-test / correctness / test / api / web）、
  `pyproject.toml` 增加 pytest 配置（testpaths = tests, hal/contract_tests）。

### Known Issues
- `numpy` / `scipy` 未安装（网络慢），仅影响 `stat_test` 导入，Phase 1 前补装。

## [1.2.1] - 2026-10-14

### Added
- 初始化项目骨架并推送到 `git@github.com:fusheng13145/verity-lens.git`（commit b6d30e6）：后端 Python 骨架（`pyproject.toml` + hal/orchestrator/sidecar/bundles/skills/tests）、前端 `web/`（React+Vite+TS + tailwind v4 + `/api` proxy）、根目录 README/AGENTS/TODO/CHANGELOG、`.gitignore`/`.gitattributes`。
- 根目录 `README.md`：项目简介、技术栈、仓库结构、后端/前端快速开始。

## [1.2.0] - 2026-10-14

### Added
- 新增 Web 前端（React + Vite + TS）作为扩展交互面：阶段看板 / HITL 审批页 / 失败登记簿查看，对接 Headless API。
- 新增 `docs/frontend.md`：前端技术栈、目录、Headless API 契约、关键交互、构建联调。
- `project-spec.md` 将 Web 前端移入 In Scope；`interaction-design.md` §5 非目标改写 + §6 Web 前端交互小节；README 类型清单登记 `frontend.md`。

## [1.1.1] - 2026-10-14

### Changed
- 原完整设计方案重命名为 `docs/design-blueprint.md`，同步更新全部引用。

## [1.1.0] - 2026-10-14

### Added
- 文档体系补全（12 篇）：`docs/README.md` 体系总览、architecture、modules、interfaces、data-schema、agent-roles-prompts、orchestration-flows、tool-calling、deployment-ops、dev-conventions、testing、glossary。
- 对照通用项目文档结构补齐：`AGENTS.md`、`TODO.md`、`docs/project-spec.md`、`docs/bundle-registry.md`、`docs/interaction-design.md`。

## [1.0.0] - 2026-10-14

### Added
- 首个完整版设计方案：`docs/design-blueprint.md`。
  - 总体架构：五层 + 侧车，HAL 依赖收敛、文件即状态、失败一等公民。
  - 核心模块：HAL、Orchestrator Lite、失败驱动迭代（failure_ledger + 五类失败分类学）、Bundle 工厂（L0/L1/L2）、协作写锁、侧车层、成本与安全。
  - 数据设计：RESEARCH.yaml / hypothesis_tree / failure_ledger / experiment 四大 Schema。
  - 边界情况 E1–E15、四层测试体系、Phase 0–4 路线图、风险应对、SaaS 评估。
- 取消 V1/V2 阶段性版本拆分，合并为单次自包含完整版。

### Removed
- V1 中对底座内部特性的散落依赖（收敛至 HAL）；OT/CRDT 实时协作承诺（改为按需评估）。
