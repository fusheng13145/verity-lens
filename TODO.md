# TODO.md — 项目开发计划与当前进度

> 进度总览文档，路线图依据见 `docs/design-blueprint.md` 第七部分。完成一项即勾选并注明日期。

## 当前状态

- **当前阶段**：Phase 4 进行中（扩展评估）
  - Phase 4a ✅ 2026-10-15：materials 学科包（L0→L1）+ `vl finalize` 真实收尾闭环 + 实验可复现元数据
  - Phase 4b ✅ 2026-10-15：compsci 第三学科（L0→L1）+ biomed 正式升 L1 + README 命名统一为 verity-lens
  - Phase 4c ✅ 2026-10-15：三学科升 L2（preset_patch + MCP 声明 + Golden 用例）+ `vl bundle load` 加载器 + numpy/scipy 补装
  - Phase 4d ✅ 2026-10-15：**HAL 契约对齐真实 DSH**（deepseek-ai/deepseek-harness 官方 CLI/mcp-client 键；本机实测 0.1.5-rc.2；版本特性门控 + 显式降级）
  - Phase 4e ✅ 2026-10-15：**科研正确性闭环**——power_analysis 工具落地 + verify_with_sidecar 真复算（p↔CI 自洽性 / 功效）+ L3 测试层从空目录变为 16 例
  - Phase 4f ✅ 2026-10-15：**敏感数据脱敏工具落地**——`desensitize`（field_mask / k_anonymity / dp_aggregate[ε=1.0] / scan_text[E10 守卫]）+ biomed/compsci 注册 verity-desensitize MCP
  - Phase 4g ✅ 2026-10-15：**HPC 长任务提交工具落地**——`hpc_submit`（可插拔 backend：dry_run/mock/slurm/pbs；dry_run/mock 确定性、不实际执行，slurm/pbs 显式降级）+ 三学科注册 verity-hpc-submit MCP
  - Phase 4h ✅ 2026-10-16：**底座升级 0.2.0-rc.2 + 事件流/session 接管联调**——npm 装 `@deepseek-ai/dsh@0.2.0-rc.2`（全局目录 EPERM，改装用户级 prefix）；真实底座验证 `--json` NDJSON 事件流可被 `parse_event_stream` 解析、`--session-id` 已知 id 接管成功/未知 id 报 `does not exist`、`--dump-config-schema` 输出 Cordis JSON Schema；`hal/version_lock.yml` verified_version 钉到 0.2.0-rc.2；契约测试 40 例全过（修正 Makefile `hal-contract-test` 指向错误目录 `tests/hal_contract`→`hal/contract_tests`）。完整 headless 运行仅因 deepseek API QUOTA 失败（外部账户）
  - Phase 4i ✅ 2026-10-16：**协作模型重评估信号补齐**——在 1.13.3 opt-in 埋点基础上补 §7.3 剩余两类信号：① `vl branch merge` 成功时比对 `VL_USER` 与 git committer 精确检测身份误配（`identity_mismatch`，`orchestrator/collab.py` 新增 `current_committer()`）；② RAG 共享索引写入观测钩子（`sidecar/rag/literature_rag.py` 加 `write_observer` 回调 + `collab_telemetry.rag_write_observer` 工厂，`rag_index_write` 事件，能力就绪待编排层接线）。仍为纯观测、不改协作模型；全量 217 通过
  - Phase 4j ✅ 2026-10-16：**P0 身份可信化**——`orchestrator/identity.py`（`resolve_identity` 可信度分级 `unverified`/`self_attested`/`mismatch`/`signed_verified` + `commit_signature_status` 读 GPG/SSH 签名作密码学锚点）+ `vl identity` 命令（`--require {set,coherent,signed}` CI 强制门禁）+ `scripts/check-identity.sh`（含 `--allowed-email-domain`）+ `.github/workflows/ci.yml` + Makefile `identity-check`；全量 233 通过。身份从「口头约定」升级为「可分级、可强制、可密码学锚定」，但不改变协作模型本身
  - Phase 4k ✅ 2026-10-16：**preset patch 机读校验 + DSH schema 钉固**（Backlog C）——`orchestrator/patch_schema.py`（`validate_preset_patch` 按 JSON Schema 严格校验 preset_patch 声明 + `pin_dsh_schema` 把真实 DSH 配置 schema 钉到 `.verity/dsh-config-schema.json` 作契约参考；实测 0.2.0-rc.2 schema 为 Cordis 风格 root array，故校验针对 verity 契约而非 DSH schema）+ `DSHAdapter.dump_config_schema()`（0.2.x 特性门控）+ `vl bundle load --check-patch-schema`（默认关闭，可选增强）+ `docs/bundle-registry.md` §3 说明；全量 247 通过。诚实边界：verity preset_patch 尚未映射为 DSH 真正的 Cordis 叠加层（patch 文件格式官方未公开）
  - Phase 4l ✅ 2026-10-16：**RAG 侧车接入编排 CLI + 写入埋点激活**（Backlog C ①）——`vl rag index/query`（`cmd_rag`：目录/文件分片索引 + 检索，`--glob`/`--top-k`/`--min-score`/`--reset`/`--json`/`--force-citation-only`）+ 索引持久化（`literature_rag.save_index/load_index` 落盘 `.verity/rag-index.json`，跨进程共享，按 chunk_id 去重防重复索引膨胀）+ `rag_write_observer` 接线（opt-in 开启即记 `rag_index_write`，关闭零副作用）+ 离线阈值修正（`OFFLINE_SCORE_THRESHOLD=0.05`：hash 嵌入器相似度量级 0.5~0.85 低于真实稠密嵌入的蓝图阈值 0.72，`--min-score` 可显式覆盖）；实测索引 docs/ 18 文件 → 92 分片、检索正确命中 collab.md 相关分片；全量 260 通过
  - Phase 4m ✅ 2026-10-16：**季度切换演练自动化**（Backlog C ②）——`hal/switch_drill.py`（接口符合性 12 方法签名级核验 / 耦合扫描 2/6 行项预算 / 替换模拟 MinimalAdapter 证明接口可实现 / 版本漂移检测 / 可选契约回归）+ `scripts/base-switch-drill.py` CLI（`--skip-contract-tests`/`--budget`/`--json`）+ Makefile `base-switch-drill`；**首跑即抓到真实问题**：本机旧全局 dsh（D:/Node.js，0.1.5-rc.2）在 PATH 遮蔽用户级新装 0.2.0-rc.2（`shutil.which` 解析到旧版 → `--json`/`--session-id` 将静默降级而版本锁却声称已验证）；`dsh_adapter` 据此支持 `DSH_BIN` 环境变量覆盖（多版本共存标准解法），指向正确版本后演练全 PASS；测试 +19（演练 17 + DSH_BIN 2），全量 279 通过
  - Phase 4n ✅ 2026-10-16：**交付审计修复（P0 接线 + 次级缺陷全部清零）**——依据 `DELIVERY-READINESS-AUDIT.md` 三轮修复：① P0 四项（`orchestrator/runner.py` 状态机+会话驱动+pre_session 硬阻断链、`vl run`/`vl advance` 阶段推进入口、writing 门禁硬化为内容实质性+`sidecar/tools/plot.py` 确定性绘图、API 失败闭环改经 `apply_decision`）+ `vl` 入口重建（editable stale 路径 + setuptools）；② 次级 #3 budget 抽模块 / #4 `hooks/on_change.py` 回流触发 / #7 CI 补 api/finalize/sidecar/unit / #11 `make reproduce` 真实化；③ 次级 #6 `sidecar/daemon.py` 常驻守护进程（NDJSON 行协议）/ #8 `harness-contract` CI 真底座契约 + `make harness-install` / #9 前端真实看板+HITL 页 / #10 `doi_metrics.py` DOI 可验证率接入 finalize 主流程 + `vl verify-dois` + API 端点；文档同步 interfaces/modules/README/CHANGELOG；全量 **323 passed / 3 skipped**（原 279）
- **下一步**：仅余外部依赖门控——完整 headless 端到端运行需 dsh 底座 + deepseek API 配额（CI `harness-contract` workflow 与 `make harness-install` 已就绪，环境具备即真跑）；协作模型最终是否调整待 1–10 人团队真实痛点数据（opt-in 埋点就绪）；团队启用提交签名后 CI 门禁升级 `--require signed`；季度切换演练周期性执行（`make base-switch-drill`）

## 待完成事项（Backlog）

> 当前路线图（Phase 0–4 + L4 集成测试）已全部落地，项目进入"按需增强 / 等待真实反馈"阶段。
> 下列为真实待办，按性质分组，避免与上方已勾选的 Phase 明细混淆。

### A. 待发布（需用户本地操作）
- [x] **推送领先提交到 GitHub**：2026-10-16 全部同步完成（远端 main HEAD = `0d36a90`，与本地一致；含 Phase 4g–4m：hpc_submit / L4 集成测试 / 底座升级 / 协作重评估框架与埋点 / P0 身份可信化 / preset patch 校验 / RAG 接线 / 季度切换演练）。后续提交仍须本地推送（本环境沙箱拦截外发，且出口对 github.com 不可达）。

### B. 外部依赖阻塞（非本项目缺陷）
- [ ] **deepseek API 配额**：完整 headless 端到端运行目前在模型调用处因 `QUOTA`（余额不足）失败。补齐配额后 `dsh --profile headless --json "<task>"` 即可跑通——底座、契约、适配器（`parse_event_stream` / `--session-id` 接管 / `--dump-config-schema`）均已用真实 `0.2.0-rc.2` 验证可用。
- [ ] **协作模型重评估**：蓝图第七部分明确"不预设方案"，须待 1–10 人团队真实使用、收集协作痛点后再决策。
  - [x] 2026-10-16 建重评估框架（`docs/collab.md` §7）：当前模型能力三档诚实分级（已实现并强制 / 已实现但默认未启用 / 明确非目标）、真实 gap 清单、待采集信号、决策阈值、候选演进方向（非承诺）。**最终是否调整模型仍待真实团队数据**。
  - [x] 2026-10-16 加 **opt-in 埋点**（见 §7.7）：`orchestrator/collab_telemetry.py` + `cmd_lock`/`cmd_branch` 接线；默认关闭零副作用；落盘 `.verity/collab-audit.jsonl`（已 gitignore，不泄露身份）。
  - [x] 2026-10-16 补齐 §7.3 剩余信号：① committer 精确身份误配（`identity_mismatch`，`vl branch merge` 比对 `VL_USER` vs git committer）；② RAG 共享索引写入观测（`rag_index_write`，`rag_write_observer` 工厂 + `write_observer` 回调，能力就绪待编排层接线）。见 CHANGELOG 1.13.4。
  - [x] **2026-10-16 P0 身份可信化落地**（见 CHANGELOG 1.13.5 / §7.8）：`orchestrator/identity.py` 身份解析与可信度分级（`resolve_identity` / `commit_signature_status`）+ `vl identity` 命令（`--require {set,coherent,signed}` 强制门禁）；`scripts/check-identity.sh` 可移植 CI 门禁 + `.github/workflows/ci.yml` 接线 + Makefile `identity-check` 目标。身份从「口头约定」升级为「可分级、可强制、可密码学锚定」（签名密钥不可伪造）。
  - [ ] 待办：② 收集真实团队（1–10 人）使用痛点，按 7.3 / 7.7 信号命中 7.4 阈值后，启动模型变更设计（从真实痛点出发，不预设方案）。
  - [ ] 待办：③ 团队启用 GPG/SSH 提交签名后，将 CI 门禁从 `--require set`（当前演示）升级为 `--require signed` 强校验（P0 已支持，待团队签名落地）。

### C. 可选增强（非阻塞，按需）
- [x] **preset patch 机读校验**（2026-10-16 落地，见 CHANGELOG 1.13.6）：`orchestrator/patch_schema.py` 严格 JSON Schema 校验 preset_patch 声明 + `vl bundle load --check-patch-schema` 钉固真实 DSH 配置 schema 作契约参考；默认关闭，可选增强。
- [x] **RAG 写入埋点接线**（2026-10-16 落地，见 CHANGELOG 1.13.7）：`vl rag index/query` CLI 入口（`orchestrator/cli.py` `cmd_rag`）+ `sidecar/rag` 索引持久化（`save_index`/`load_index`，落盘 `.verity/rag-index.json`）；实例化 `LiteratureIndex` 时注入 `rag_write_observer(workspace)`，opt-in 开启即自动采集 `rag_index_write` 事件；离线 hash 嵌入器相似度量级低于真实稠密嵌入，查询默认放宽阈值（`OFFLINE_SCORE_THRESHOLD`，`--min-score` 可显式覆盖）。
- [x] **季度切换演练**（2026-10-16 落地，见 CHANGELOG 1.13.8）：`python scripts/base-switch-drill.py`（或 `make base-switch-drill`）四项检查（接口符合性 / 耦合预算 / 替换模拟 / 版本漂移）+ 契约回归；季度执行或每次升级 deepseek-harness 后执行。**首跑即发现本机旧全局 dsh 遮蔽新版**（已支持 `DSH_BIN` 覆盖；机器侧清理旧全局安装待用户决定，见 version_lock.yml known_differences）。

### C2. 本机环境（2026-10-16 全部处置完成 ✅）
- [x] **旧全局 dsh 清理**：`D:\Node.js` 下的 dsh@0.1.5-rc.2（含 shims 与包目录）已由用户以管理员权限删除；npm 全局 prefix 已对齐用户目录 `C:\Users\ASUS\.npm-global`（未来 `npm i -g` 不再需要管理员）；`.npm-global` 已追加到用户级 PATH。`dsh --version` 现解析为 **0.2.0-rc.2**（= 版本锁 verified_version），季度演练 5/5 全 PASS（版本漂移已消）。`DSH_BIN` 环境变量保留作为多版本共存的标准出口（当前不需要）。

---

## Phase 4：扩展评估（按需）

- [x] **Phase 4a** — 学科扩展 + 收尾闭环（2026-10-15）
  - [x] 第二学科 materials：由 `vl bundle new` 生成 L0，补 characterization（L1 验证脚本）/ literature SKILL + 术语表，升 L1，`vl bundle validate` 通过
  - [x] 实验可复现元数据：`experiment.schema.json` 新增可选 `reproducibility` 对象
  - [x] `vl finalize` 真实实现：终态/无未处理失败/analysis·figures 就绪 + 可复现元数据完整度 + 生成 finalize_report.md（含 AI 贡献声明草稿）
  - [x] 测试：100 个用例通过（新增 8）
- [x] **Phase 4b** — 第三学科 + 命名统一（2026-10-15）
  - [x] 第三学科 compsci：由 `vl bundle new compsci --capability computation` 生成 L0，补 computation（L1 验证脚本：固定种子 / n≥3 / 环境 / 哈希 / 基线差异）/ literature SKILL + 术语表，升 L1，`vl bundle validate` 通过
  - [x] biomed 正式升 L1（`bundle.yml` level 字段同步；L1 校验脚本与 literature 早已具备）
  - [x] README 项目名统一为 kebab-case `verity-lens（真理之眼）`，与包名/目录一致
  - [x] 测试：101 个用例通过（新增第三学科共存校验 1）
- [x] **Phase 4c**（2026-10-15 完成）
  - [x] biomed / materials / compsci 升 L2：补 Preset Patch + MCP 声明 + Golden 用例（每学科 3 例，`vl bundle validate` 强制三要素）
  - [x] Bundle 加载器 `orchestrator/bundle_loader.py` + `vl bundle load`：bundle.yml → HAL 注册 Skill/MCP/Preset，能力缺失显式降级（不静默）
  - [x] sidecar 工具 stdio 入口（`python -m sidecar.tools.<tool>`，stdin/stdout JSON）：MCP 声明可执行，非纸面配置
  - [x] numpy 2.5.4 / scipy 1.18.1 补装（Phase 0 遗留）：stat_test 真实统计路径生效
- [x] **Phase 4d** — HAL 契约对齐真实 DSH（2026-10-15）
  - [x] 依据官方 deepseek-ai/deepseek-harness 文档重写 `hal/dsh_adapter.py`：profile / `--patch` / `headless --json` / `--session-id` 真实命令行
  - [x] 版本锁去虚构化：`verified_version` 由编造的 2.4.0 更正为本机实测 0.1.5-rc.2，并记录 `contract_baseline` 0.2.1-alpha.3 与来源 URL
  - [x] 版本特性门控 `VERSION_FEATURE_MIN`：`--json`/`--session-id`/`--dump-config-schema` 属 0.2.x，底版本自动丢弃并写 `degraded` 事件
  - [x] MCP 声明映射到 mcp-client 真实 `StdioConfig`（serverName 正则 / command+args / 工具名 `mcp__<server>__<raw>`）
  - [x] Windows 兼容：`shutil.which` 解析 npm `.cmd` shim + 非 UTF-8 输出容错解码
  - [x] HAL 契约测试重写为真实命令行形状 + 版本降级（39 例），并含真实 dsh 实测用例
  - [x] 底座升级至 ≥0.2 后：NDJSON 事件流 / session 接管联调 + patch schema 机读校验（`--dump-config-schema`）（2026-10-16 实测 0.2.0-rc.2 完成；完整运行受 deepseek API QUOTA 限制）
- [x] **Phase 4e** — 科研正确性闭环（2026-10-15）
  - [x] `sidecar/tools/power_analysis.py`：先验样本量 / 事后功效（正态近似双侧），带 TOOL_SPEC + stdio 入口
  - [x] `verify_with_sidecar` 由「仅探测工具可用」升级为真实复算：组统计量完整复算 + p↔CI 交叉复算 + 功效复算；不一致报 mismatch
  - [x] `failure_ledger.schema.json` 新增可选 `reported_metrics`（复算的唯一输入）
  - [x] L3 层落地：`tests/correctness/` 由空目录变为 16 例真实抽检（含与 scipy 独立 API 对齐）
  - [x] 修正 biomed 金样例的统计不自洽（p=0.023 与 CI[0.31,0.93] 蕴含 p≈9e-5，被 L3 交叉复算查出）
  - [x] biomed / compsci 注册 `verity-power-analysis` MCP 服务
- [x] **Phase 4f** — 敏感数据脱敏工具落地（2026-10-15）
  - [x] `sidecar/tools/desensitize.py`：field_mask（hash 令牌/redact/generalize）+ k_anonymity（QI 抑制至≥k）+ dp_aggregate（Laplace，ε=1.0，seed 可复现）+ scan_text（PHI/PII 正则扫描，E10 守卫）
  - [x] biomed / compsci 注册 `verity-desensitize` MCP（materials 不需要）；tool_whitelist 同步
  - [x] 测试：12 例（确定性断言 + stdio 入口），全量新增 18 例
- [x] **Phase 4g** — HPC 长任务提交工具落地（2026-10-15）
  - [x] `sidecar/tools/hpc_submit.py`：submit/status/cancel 三模式；backend 可插拔（dry_run 默认 / mock / slurm / pbs）
  - [x] dry_run/mock 确定性（job_id 由规格哈希确定）、绝不实际执行；slurm/pbs best-effort 调用并显式降级（scheduler 不可达不崩溃）
  - [x] 三学科注册 `verity-hpc-submit` MCP（通用长任务提交能力，E13 规避终端关闭中断；materials 不注册 power/desensitize 的学科差异不变）
- [x] **L4 边界保真集成测试**（2026-10-15，v1.13.1）——`tests/integration/test_stdio_boundary.py`：证明 Sidecar 工具经 `python -m`（HAL/MCP 真实路径）与进程内 `run(**params)`（编排层内部路径）产出逐字段等价；`make integration` 单独跑
- [x] 协作模型重评估框架 + opt-in 信号埋点（含 committer 身份误配 / RAG 写入，2026-10-16 落地）；最终模型变更仍待 1–10 人团队真实数据（见 docs/collab.md §7、Backlog B）

## Phase 3：健壮性与协作 ✅ 2026-10-15

- [x] 容器沙箱：`docker/sandbox-compose.yml`（no-new-privileges / cap_drop / network_mode none / read_only / tmpfs / 资源硬限）+ `orchestrator/sandbox.py` 生成器（按 PROJECT_ID 渲染 + 安全基线校验）+ `vl sandbox` 命令 + `docker/sandbox.md` 敏感数据治理管道
- [x] RAG 侧车完整版：`sidecar/rag/literature_rag.py` 重写（分片/可插拔嵌入/向量检索/MMR 去重/会话缓存 LRU/token 预算/citation-only 降级/auto-archive），离线可测
- [x] 制品写锁：`orchestrator/lock.py`（acquire/release/check + 超时失效 + 冲突检测）+ `vl lock` 命令 + `research.schema.json` 结构约束
- [x] Git 分支协作流：`orchestrator/collab.py`（假设分支创建 / 合并前就绪检查 / --no-ff 合并）+ `vl branch` 命令 + `docs/collab.md`
- [x] 测试：92 个用例全通过（含 lock / rag / sandbox / collab 新增）

## Phase 2：领域包化 + 失败闭环完备 ✅ 2026-10-15

- [x] 重构 `orchestrator/bundle_factory.py`：
  - [x] `new_bundle(discipline, target, capability)` 生成 L0 骨架（复制模板 + 占位符替换 + Skill 目录重命名）
  - [x] `validate_bundle(dir)` 结构校验（必填字段 / level 枚举 / Skill 存在性）
  - [x] `INTERVIEW_TEMPLATE` 领域专家访谈提纲
- [x] L0 模板 `bundles/_template/`（bundle.yml + skills/capability/SKILL.md）
- [x] biomed 升 **L1**：新增 `skills/biomed-stats/scripts/validate_report.py`（确定性校验：必填字段 / CI 合法性 / p 值范围 / 需 CI 的指标）
- [x] 级联回流：`cascade_impact()` 沿 children 链传播（根证伪 → 派生假设 revised / 实验 abandoned，写 cascade_note）
- [x] 测试：65 个用例全通过

## Phase 1：单学科端到端闭环 ✅ 2026-10-15

- [x] 失败驱动迭代模块：`orchestrator/failure_loop.py`
  - [x] 五类失败分类学（EXEC/DATA/METH/HYP/EPIS）与路由
  - [x] failure_ledger 条目 Schema 校验（含 evidence 指针）
  - [x] 确定性工具复核（功效/效应量/p 值，依赖缺失时降级）
  - [x] 落盘：实验转终态 + 假设树置信度/状态更新 + ledger 追加 + lessons.md 渲染
  - [x] 硬约束：未批准不回流；refuted 不可删；新假设须引用 F-xxx
- [x] biomed L0 Bundle（bundle.yml + stats/literature SKILL + 术语表）
- [x] CLI：`vl loop` 与 `vl budget check` 真实实现
- [x] 测试：53 个用例全通过

## Phase 0：底座 + HAL 立桩（1–2 周）✅ 2026-10-15

- [x] 搭建工程骨架（`hal/` `orchestrator/` `sidecar/` `bundles/_template/` 目录）
- [x] 实现 `hal/interface.py` 抽象接口（含 `CAPABILITY_KEYS`）+ `dsh_adapter.py`
- [x] 实现能力探测 `capability_probe.py` + `version_lock.yml`
- [x] 编写 HAL 契约测试（`hal/contract_tests/`，11 个用例覆盖接口与降级）
- [x] 最小 Skill（literature）+ 最小 sidecar 工具（stat_test / doi_verify）
- [x] 四大 JSON Schema：`research` / `hypothesis_tree` / `experiment` / `failure_ledger`
- [x] 编排层门禁引擎：`orchestrator/gates.py` 纯函数 + `vl init` / `vl gate`
- [x] Headless API：`orchestrator/api.py`（供前端）
- [x] 前端骨架：`web/`（React + Vite + TS + Tailwind + `/api` proxy）
- [x] 验证：36 个测试全通过

**遗留**：`numpy` / `scipy` 因网络慢未安装（仅 `stat_test` 需要，Phase 1 用到时再装）。

---

> **历史路线图草稿（已落地，保留备查）**：下方为 2026-10-14 初版路线图的分阶段待办草稿，
> 现已全部落地于上方对应 Phase 的勾选项（Phase 0–4 + L4 集成测试），不再作为待办。

## 文档体系（已完成）

- [x] 完整设计方案 `docs/design-blueprint.md`（2026-10-14）
- [x] 12 篇结构化文档 + README 导航（2026-10-14）
- [x] 蓝图重命名 design-blueprint.md（2026-10-14）
- [x] 补齐 project-spec / bundle-registry / interaction-design / AGENTS / CHANGELOG / TODO（2026-10-14）
