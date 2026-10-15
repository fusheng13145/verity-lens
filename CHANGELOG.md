# CHANGELOG.md — 版本更新记录

> 遵循 Keep a Changelog 风格，版本号 `MAJOR.MINOR.PATCH`。

## [1.13.0] - 2026-10-15 — Phase 4g（HPC 长任务提交工具）

### Added
- **`sidecar/tools/hpc_submit.py`**（蓝图 §2.7 / tool-calling.md 已列但此前未实现）：
  - 三模式 `submit` / `status` / `cancel`；可插拔 backend：`dry_run`（默认）/ `mock` / `slurm` / `pbs`；
  - `dry_run` / `mock` 确定性（job_id 由 命令+资源+backend 规格哈希确定）、**绝不实际执行**；`slurm`(`--wrap`) / `pbs`(`bash -c`) 把命令作单参数传入（避免 shell 注入），best-effort 调用并显式降级（scheduler 不可达 → `submission_unavailable`，不崩溃）；
  - 所有提交完整落本地账本（command + resources）可审计，呼应 E13（长任务走 Sidecar 远程提交，规避终端关闭中断）。
- 三学科注册 `verity-hpc-submit` MCP（biomed / materials / compsci；长任务提交是通用基础设施能力，与 stat_test/doi_verify 一致；materials 不注册 power_analysis/desensitize 的学科差异不变）。

### Tests
- `tests/sidecar/test_hpc_submit.py`：10 例（dry_run 确定性 / mock 生命周期 / 校验 / cancel / 未知 job_id / slurm 降级 / stdio 入口）。

### Docs
- 更新 `interfaces.md` / `tool-calling.md` / `bundle-registry.md` / `TODO` / `README`（`hpc_submit` 从"未实现"移除）。

## [1.12.0] - 2026-10-15 — Phase 4f（敏感数据脱敏工具 + E10 扫描守卫）

### Added
- **`sidecar/tools/desensitize.py`**（蓝图 §2.7 承诺、tool-calling.md 已列但此前未实现）：
  - `field_mask`：字段级屏蔽（hash 令牌化 / redact 置空 / generalize 数值泛化），hash 带盐且确定性；
  - `k_anonymity`：准标识符（QI）抑制，使每个 QI 组合出现 ≥ k 次（唯一组合标记抑制，非 QI 字段保留以审计）；
  - `dp_aggregate`：差分隐私聚合（Laplace，默认 ε=1.0，敏感度按统计量定），`seed` 给定则噪声可复现；
  - `scan_text`：**E10 风险守卫**——正则扫描文本中的 PHI/PII（email / 手机号 / 身份证 / 银行卡 / 生日），返回命中类型与风险等级（high/medium/none）。
  - 带 `TOOL_SPEC` + stdio 入口（`python -m sidecar.tools.desensitize`），非法输入显式报错（退出码 1）。
- **MCP 注册**：biomed / compsci 增加 `verity-desensitize` 服务并纳入 `tool_whitelist`（materials 不处理个人敏感数据，无需）。
- 测试：新增 `tests/sidecar/test_desensitize.py` 12 例（确定性断言 + stdio 入口），覆盖四种 mode 与错误路径。

### Changed
- 文档同步：`interfaces.md`（关键工具清单标注 ✅ Phase 4f）、`tool-calling.md`（desensitize 行标注已落地 + mode）、`bundle-registry.md`（biomed/compsci MCP 集更新）；`modules.md` 早先的 `budget.py` 漂移已在 4e 修正。

## [1.11.0] - 2026-10-15 — Phase 4e（科研正确性闭环：功效工具 + 真实复算 + L3 落地）

### Added
- **`sidecar/tools/power_analysis.py`**（Phase 0 起文档已承诺但一直缺失的关键工具）：
  - `mode=prior` 达到目标功效所需样本量；`mode=post` 观测样本量下的实际功效 + `underpowered` 判定；
  - 两样本 / 单样本，正态近似双侧口径；样本量与经典值对齐（d=0.5→63、d=0.2→393、d=0.8→25；精确非中心 t 检验为 64/394/26）；
  - 强制附带 `post_hoc_warning`（事后功效不能替代 p 值、不构成事后检验正当性）——科研诚信提示随输出走，不可被静默丢弃；
  - 带 `TOOL_SPEC` + stdio 入口（`python -m sidecar.tools.power_analysis`），非法输入显式报错（退出码 1）。
- **L3 科研正确性层落地**：`tests/correctness/` 此前是**空目录**（`make correctness` 假绿），现为 16 例真实抽检：
  p↔CI 统计自洽性、组统计量完整复算（与 scipy `ttest_ind_from_stats` 对齐到 1e-9）、功效样本量对照、stat_test 确定性、三学科金样例数值合理性。
- **MCP 注册**：biomed / compsci 增加 `verity-power-analysis` 服务并纳入 `tool_whitelist`（materials 不做假设检验，无需）。
- `failure_ledger.schema.json` 新增可选 `reported_metrics`（group_stats / p_value / effect_size / ci_95 / n_per_group / power）——确定性复算的唯一输入。

### Changed
- **`verify_with_sidecar` 由"探测工具是否可用"升级为真实数值复算**（此前只要能 import 就标 `verified`，等于放行一切未复算的数字）：
  - `group_stats` 齐全 → stat_test 完整复算 p / 效应量 / CI；
  - 仅 `effect_size`+`ci_95` → 相容性交叉复算（由 CI 反推 se → z → 复算 p，容差 `max(0.002, 10%·p)`）；
  - `effect_size`+`n_per_group` → power_analysis 复算事后功效（容差 0.02）；
  - 对不上 → `status=mismatch`（METH/HYP 归因必须先解释差异）；无可复算数值 → `skipped` 且**不算已验证**。
- `_reconstruct` 修正：等差序列步长改为 `sd·sqrt(12/(n(n+1)))`，使重建样本的样本方差精确等于 sd²（此前方差被缩小 n/12 倍，复算结果全错）。

### Fixed
- **biomed 金样例统计不自洽**（被新 L3 层查出）：`stats_ok` 原声明 `p=0.023` 与 `CI=[0.31,0.93]`（蕴含 z≈3.92 → p≈9e-5）互相矛盾；已改为 `p=0.0001`、样本量注记 n=31/组，与 CI 自洽。域校验输出不变（仍为合规样例）。
- `docs/modules.md` 文档漂移：声称存在 `budget.py`，实际预算检查在 `cli.py:cmd_budget`。

### Tests
- 新增 L3 层 16 例 + stdio 用例 2 例；更新三学科并存/加载器用例以支持逐学科 MCP 集合。
- 全量 **167 个用例**通过（原 149 + 新增 18）。

## [1.10.0] - 2026-10-15 — Phase 4d（HAL 契约对齐真实 DSH）

### Fixed
- **HAL 的 DSH 契约此前是虚构的**：版本锁写 `verified_version: 2.4.0`、能力全开、
  命令行形状（`dsh` 裸命令）从未与真实底座核对。现按官方仓库
  [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)
  （MIT，developer preview）的 `docs/cli-help.md` / `config-catalog.md` / `capability-seams.md`
  全面重写，`verified_version` 更正为本机实测 **0.1.5-rc.2**，并登记
  `contract_baseline: 0.2.1-alpha.3` 与来源 URL。
- **`trajectory_fork` 由 true 更正为 false**：launcher CLI 未暴露轨迹分叉命令；
  DSH 会话内的"已完成前缀分叉"属 `ctx.subagents` 的 forkProvider（tool-subagent 委派），
  HAL 不穿透 → 恒定降级为 `replay_to`（此前是乐观假设）。
- **Windows 无法启动底座**：`subprocess` 传裸名 `dsh`（npm 装的是无扩展名 sh 脚本）→ WinError 2。
  改为经 `shutil.which` 解析真实 `.cmd` shim 后再启动，并对非 UTF-8（本机 GBK 代码页）输出容错解码。
- **Preset Patch 同名覆盖**：三学科共用 `verity-research` 时叠加层文件互相覆盖；
  现按 `<discipline>-<preset>` 隔离，且 `hal/patches/` 加入 .gitignore（运行时产物）。

### Added
- **真实 DSH 命令行契约**（`build_run_argv` / 契约测试锁定）：
  `dsh --profile <p> [--patch <f>]… [--json] [--session-id <id>] "<task>"`；
  出厂 profile web/headless/sdk/sdk-minimal/acp；支持命令前缀调用
  （等价 `npx @deepseek-ai/dsh`）。
- **版本特性门控** `VERSION_FEATURE_MIN`：按 `dsh --version` 判定，
  `--json` / `--session-id` / `--dump-config-schema` 属 0.2.x；底座版本更低时
  **不发出未知选项**（否则底座直接报 unknown option），改写 `degraded:unsupported_flag` 事件。
  `capabilities()` = 版本锁结论 ∩ 运行期特性探测（运行期只收窄不放宽）。
- **MCP 声明映射到真实 `StdioConfig`**：`serverName`（`[A-Za-z0-9_-]{1,32}`）/ `command`+`args` /
  `toolCallTimeoutMs` / `failOnStartupError`；模型可见工具名 `mcp__<serverName>__<rawName>`
  （`vl bundle load` 现在会打印这些名字）。
- `load_version_lock()` + `parse_version()` + `DSHAdapter.features()` / `resolved_bin()`。

### Docs
- `docs/deployment-ops.md`：DSH 安装（Node 前置 / npx 入口 / 全局安装）、真实 CLI 表面、
  能力矩阵与降级行为表、Session 续跑按版本区分。
- `docs/interfaces.md` 新增 §1.1「DSH 实现映射」：HAL 接口 ↔ DSH 真实表面 ↔ 版本要求。
- `docs/bundle-registry.md`：L2 的 preset_patch 物化路径与 MCP 映射说明。

### Tests
- `hal/contract_tests/test_adapter_contract.py` 重写：假 dsh 桩锁定真实命令行形状、
  0.1/0.2 版本特性门控、NDJSON 事件流解析、底座缺失/版本过低降级、
  `StdioConfig` 校验、Preset Patch 物化与 scope 隔离；含真实 dsh 存在时的实测用例。
- 全量 **149 个用例**通过（原 125 + 新增 24）。

> 注：底座 ≥0.2 的 NDJSON 事件流 / `--session-id` 接管 / patch schema 机读校验
> （`--dump-config-schema`）待本机底座升级后联调；当前 0.1.5-rc.2 下这些能力按契约自动降级。

## [1.9.0] - 2026-10-15 — Phase 4c（三学科升 L2 + Bundle 加载器）

### Added
- **三学科 Bundle 升 L2**（biomed 0.3.0 / materials 0.2.0 / compsci 0.2.0）：
  - `preset_patch`：preset `verity-research` + 由 SKILL.md 蒸馏的学科 system_prompt + tool_whitelist（stat_test / doi_verify）；
  - `mcp.servers`：sidecar 确定性工具声明（`verity-stat-test` / `verity-doi-verify`，stdio）；
  - `golden_cases`：每学科 3 例（合规通过 / 典型违规 ×2），`tests/golden/test_bundle_golden.py` 回归，实际问题列表与期望逐字一致（防验证脚本放水）。
- **Bundle 加载器** `orchestrator/bundle_loader.py` + CLI `vl bundle load <dir>`：bundle.yml → HAL `register_skills` / `declare_mcp_servers` / `apply_preset_patch`；能力缺失显式降级并输出（mcp 缺失 → 编排层直连 sidecar；preset_patch 缺失 → 启动参数注入），禁止静默失败（蓝图 §2.1 降级表）。
- **sidecar 工具 stdio 入口** `sidecar/tools/_stdio.py`：`python -m sidecar.tools.stat_test|doi_verify`，stdin JSON 参数 → stdout JSON 结果；MCP 声明从此可执行，非纸面配置。
- **L2 校验规则**：`validate_bundle` 对 L2 强制 preset_patch / mcp / golden_cases 三要素（结构 + 文件存在性）；L0/L1 不强制（渐进升级）。

### Fixed
- **numpy 2.5.4 / scipy 1.18.1 补装**（Phase 0 遗留）：`stat_test` 真实统计路径生效（此前依赖缺失时降级为 skipped）；pyproject 核心依赖声明与 .venv 实际状态一致。

### Tests
- 新增 `tests/golden/test_bundle_golden.py`（9 例：三学科 golden 回归）、`tests/golden/test_bundle_loader.py`（6 例：注册/降级/阻断）、`tests/sidecar/test_stdio_entry.py`（2 例：stdio 入口）、`tests/schema/test_bundle_factory.py` 追加 L2 规则 3 例。
- 全量 **125 个用例**通过（原 101 + 新增 24）。

> 注：L2 的端到端联调（真实 `dsh` 二进制接入后的"换 Bundle 即切换学科"演练 + 轨迹回归 edit distance ≤2）留待底座真实化；当前 HAL 适配器在底座缺失时已按契约全量降级并有测试锁定。

## [1.8.0] - 2026-10-15 — Phase 4b（第三学科 + 命名统一）

### Added
- **第三学科 Bundle：compsci（计算机科学）L0→L1**：
  - 由 `vl bundle new compsci --capability computation` 生成 L0 骨架，与 materials 对称；
  - 填充 `compsci-computation` SKILL.md（可复现计算实验：固定随机种子 / n≥3 重复 / 环境记录 / 数据·代码哈希 / 均值±标准差 / 基线统计差异）+ `compsci-literature` SKILL.md（证据等级 L1–L3 / SOTA 溯源）；
  - L1 验证脚本 `scripts/validate_experiment.py`（确定性：R1 种子 / R2 n≥3 / R3 环境 / R4 哈希 / R5 不确定度 / R6 基线差异）；
  - 术语表 `references/compsci_terminology.json`；`bundle.yml` 升 L1 并声明两个 Skill；`vl bundle validate` 通过。
- **biomed 正式升 L1**：`bundle.yml` level 字段由 L0 改为 L1（L1 校验脚本与 literature 早已具备，此前仅 level 字段未同步）。

### Changed
- `README.md`：项目名统一为 kebab-case `verity-lens（真理之眼）`，与包名 `pyproject.toml` 及目录一致。
- `docs/bundle-registry.md`：compsci 登记为 L1 已交付；biomed 注明 Phase 4b 正式升 L1。

### Tests
- `tests/schema/test_bundle_factory.py`：新增 `test_three_disciplines_coexist`（biomed / materials / compsci 三学科并存、互不污染、结构合规）。
- 全量 **101 个用例**通过（原 100 + 新增 1）。

> 注：L2（专用 MCP 声明 + Preset Patch + Golden 用例）因运行底座（DSH）仍为骨架，留待底座真实化后推进；协作模型按蓝图"不预设方案"，待真实团队痛点反馈。

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
