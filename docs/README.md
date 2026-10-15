# VerityLens 文档体系总览

> 本文件是项目文档的**导航与体系说明**。它定义"应该有哪些文档、各自的目的与结构"，并指向具体文档。设计目标是：**模块化、高内聚低耦合、可维护性**（软件工程）与**清晰的角色定义、任务编排、工具调用、记忆/上下文管理**（Agent 应用开发）。

## 一、设计原则在文档上的体现

| 原则 | 文档体现 |
|------|----------|
| 模块化 | 每个模块独立一篇 `modules/*.md`，单一职责、边界清晰 |
| 高内聚低耦合 | 模块间只通过 `interfaces.md` 定义的契约交互；HAL 是唯一允许依赖底座的边界 |
| 可维护性 | 文档分层（蓝图→模块→接口→运维）、版本锁定、变更可追溯 |
| 角色定义 | `agent-roles-prompts.md` 定义每个 Agent/子代理的角色、权限、提示词 |
| 任务编排 | `orchestration-flows.md` 描述阶段门禁、失败回流、会话钩子 |
| 工具调用 | `tool-calling.md` 规定 Skill / MCP / Sidecar 的边界决策矩阵 |
| 记忆与上下文管理 | `data-schema.md` + RAG 侧车配置，定义短期/长期记忆与上下文预算 |

## 二、文档类型清单（标题 · 目的 · 结构 · 要点）

| # | 文档 | 标题 | 目的 | 内容结构 | 要点 |
|---|------|------|------|----------|------|
| 0 | `README.md` | 文档体系总览 | 导航与体系说明 | 原则映射表 / 类型清单 / 阅读路径 / 维护约定 | 单一入口，所有文档可索引 |
| 1 | `architecture.md` | 总体架构设计 | 系统分层与依赖关系 | 设计原则 / 分层图 / 核心分工 / 依赖收敛 / 演进约束 | 以 HAL 隔离底座，文件即状态 |
| 2 | `modules.md` | 模块说明 | 各模块职责、接口、边界 | 逐模块：职责 / 公开接口 / 依赖 / 耦合边界 / 可测试性 | 高内聚低耦合，单测边界清晰 |
| 3 | `interfaces.md` | 接口文档 | 模块间契约（低耦合关键） | HAL 接口 / CLI 命令 / Sidecar 工具 / MCP / 数据契约 | 契约先行，实现可替换 |
| 4 | `data-schema.md` | 数据设计与 Schema | 记忆/上下文/状态载体 | Workspace 文件清单 / RESEARCH.yaml / hypothesis_tree / failure_ledger / experiment / 校验 | 声明式、可复现、可审计 |
| 5 | `agent-roles-prompts.md` | Agent 角色与提示词设计 | 角色定义与提示词工程 | 角色清单 / 系统提示 / SKILL.md 模板 / 子代理策略 / HITL 提示 | 角色=权限+职责+提示词 |
| 6 | `orchestration-flows.md` | 任务编排与流程 | 跨阶段流转与门禁 | 端到端流程 / 失败回流 / 会话前门禁 / 升级回归 | 编排层无状态，规则声明式 |
| 7 | `tool-calling.md` | 工具调用规范 | Skill/MCP/Sidecar 边界 | 决策矩阵 / 注册方式 / 确定性工具清单 / 安全约束 | 需要理解→Skill；调用系统→MCP；纯计算→Sidecar |
| 8 | `deployment-ops.md` | 部署与运维说明 | 落地、运行、灾备 | 环境 / 安装 / 底座接入 / 沙箱 / CI / 监控 / 恢复 | 底座经 HAL 接入，单机优先 |
| 9 | `dev-conventions.md` | 开发规范与协作 | 团队协作与可维护性 | 分支模型 / Code Review / 命名 / 版本锁 / 文档标准 | 写锁+PR，HAL 变更阻断项 |
| 10 | `testing.md` | 测试与验收 | 质量门禁 | L1-L4 分层 / Golden / 正确性抽检 / 通过标准 | 失败闭环纳入回归用例 |
| 11 | `glossary.md` | 术语表 | 统一语言 | 术语 / 缩略语 / 中英对照 | 跨团队协作的词汇基线 |
| 12 | `project-spec.md` | 项目规格 | 定义定位、目标与功能范围 | 定位 / 用户画像 / In-Out Scope / 成功指标 | 需求基线，与蓝图（技术侧）互补 |
| 13 | `bundle-registry.md` | Bundle 注册表 | 领域包生态台账 | 台账 / 注册流程 / 校验要求 / 分发版本 | 新 Bundle 必须登记，防漂移 |
| 14 | `interaction-design.md` | 交互设计规范 | 统一 CLI/HITL 交互 | CLI 输出 / HITL 要素 / 错误降级呈现 / 可追溯性 | 阻塞必附缺失清单，数值必标来源 |
| 15 | `frontend.md` | 前端设计规范 | React 前端技术栈/目录/API 契约 | 技术栈 / 目录 / Headless API 契约 / 关键交互 / 构建联调 | 仅经 Headless API 交互，类型由 schemas 生成 |
| 16 | `collab.md` | 协作与制品管理 | 写锁 + Git 假设分支 + 分支保护 | 协作边界 / 制品写锁 / 假设分支流 / 分支保护 / pre_session 片段 | 以制品为协作单位，先到先得 + 超时失效 |
| 17 | `docker/sandbox.md` | 容器沙箱与敏感数据治理 | 代码执行隔离 + 数据脱敏管道 | 安全基线 / 生成方式 / 五步治理管道 / 与编排层关系 | never_in_context：敏感数据永不进上下文 |

### 根目录文件（面向日常协作与变更管理）

| 文件 | 目的 | 要点 |
|------|------|------|
| `../AGENTS.md` | AI 编码代理硬规则入口 | 依赖收敛/契约先行/文档同步等 6 条硬规则 + 常用命令 |
| `../CHANGELOG.md` | 版本更新记录 | Keep a Changelog 风格 |
| `../TODO.md` | 开发计划与当前进度 | 按 Phase 0–4 拆解的任务清单，随进度勾选 |

> 附：总体设计蓝图的权威完整版见 `design-blueprint.md`（含架构、模块、流程、数据、边界情况、路线图、风险），本目录是对其的**结构化拆分与运维补全**，二者以本文档为索引保持一致。

## 三、推荐阅读路径

- **新人 onboarding**：README → `project-spec` → architecture → modules → agent-roles-prompts
- **开发某模块**：对应 `modules.md` 章节 → `interfaces.md` 契约 → `dev-conventions.md`
- **接一个新学科**：`project-spec.md` 范围确认 → `tool-calling.md` 决策矩阵 → `agent-roles-prompts.md` SKILL 模板 → `bundle-registry.md` 登记
- **上线/排障**：`deployment-ops.md` → `interaction-design.md`（CLI 退出码） → `frontend.md`（API 契约） → `testing.md` → `glossary.md`
- **接手进度**：`../TODO.md` → `../CHANGELOG.md`

## 四、文档维护约定

- 任何模块公开接口变更，须同步改 `interfaces.md` 与对应 `modules.md`，并在 PR 说明中标注。
- 底座（DSH）版本升级，须更新 `deployment-ops.md` 的版本锁章节与 `interfaces.md` 的能力差异。
- 新增学科 Bundle，须在本 README 类型清单的"领域层"下登记，避免文档漂移。
- 文档与代码冲突时，以 `interfaces.md`（契约）为准；契约与实现冲突时，实现须改或契约须升版并经评审。
