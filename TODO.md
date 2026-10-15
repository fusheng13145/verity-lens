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
- **下一步**：底座 ≥0.2 升级后补事件流/session 接管联调 + patch schema 机读校验（`--dump-config-schema`）；协作模型按真实痛点重评估（不预设方案）

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
  - [ ] 底座升级至 ≥0.2 后：NDJSON 事件流 / session 接管联调 + patch schema 机读校验（`--dump-config-schema`）
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
- [ ] 协作模型按真实痛点重评估（蓝图明确"不预设方案"，待 1–10 人团队实际协作反馈）

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

## Phase 1：单学科端到端闭环（3–6 周）

- [ ] biomed L0 Bundle（SKILL.md + 通用验证脚本）
- [ ] Orchestrator Lite：`vl init/gate/budget` + pre_session hook
- [ ] failure_ledger schema + 回流引擎 v1（EXEC/METH 两类）
- [ ] Golden 测试集 5–10 用例
- [ ] 验收：检索→写作跑通；METH 类失败走通"归因→修订→再实验"

## Phase 2：领域包化 + 失败闭环完备（7–12 周）

- [ ] Bundle 工厂（`vl bundle new` + `_template/`）
- [ ] L1 Bundle ×2；HYP/EPIS 回流；假设树 refuted/revised
- [ ] Golden 集扩充（含失败闭环用例 METH/HYP 各 3 例）

## Phase 3：健壮性与协作（4–6 月）

- [ ] 容器沙箱（sandbox-compose）
- [ ] RAG 侧车完整版（缓存/防膨胀/citation-only）
- [ ] 制品写锁 + Git 分支协作流

## Phase 4：扩展评估（按需）

- [ ] L2 Bundle；3+ 学科在用后评估扩展与协作模型

## 文档体系（已完成）

- [x] 完整设计方案 `docs/design-blueprint.md`（2026-10-14）
- [x] 12 篇结构化文档 + README 导航（2026-10-14）
- [x] 蓝图重命名 design-blueprint.md（2026-10-14）
- [x] 补齐 project-spec / bundle-registry / interaction-design / AGENTS / CHANGELOG / TODO（2026-10-14）
