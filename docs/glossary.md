# 术语表

**目的**：统一项目词汇，作为跨团队协作的语言基线。遇到歧义以本表为准。

## 核心术语

| 术语 | 英文/缩写 | 含义 |
|------|-----------|------|
| 真理之眼 | verity-lens（VerityLens） | 本项目名；英文 slug 为 `verity-lens`，VerityLens 为同义品牌写法 |
| 运行底座 | Harness / Base | 提供 agent loop、子代理、会话日志的运行时；当前实现为 DSH |
| 适配层 | HAL | Harness Adapter Layer，唯一允许依赖底座的模块 |
| 编排层 | Orchestrator Lite | 无状态事件处理器，负责门禁/失败回流/预算 |
| 领域包 | Bundle | 学科方法论封装（L0/L1/L2） |
| 侧车 | Sidecar | 常驻 Python 进程，提供确定性工具与外部对接 |
| 失败登记簿 | failure_ledger | 结构化记录每次实验失败归因与决策的 JSON |
| 失败闭环 | Failure Loop | 实验失败→归因→假设/参数调整→再实验的回流机制 |
| 制品写锁 | artifact lock | 多人写作时的文件级写锁，超时自动失效 |
| 门禁 | gate / HITL | 阶段切换准入检查，部分需人工审批 |
| 轨迹分叉 | trajectory fork | 底座支持的假设分支实验能力（可选） |
| 能力探测 | capability probe | HAL 启动时检测底座支持的特性集 |
| 版本锁 | version lock | 记录已验证底座版本与差异的配置文件 |

## 失败分类学编码

| 编码 | 含义 | 回流动作 |
|------|------|----------|
| EXEC | 执行失败（资源/超时/环境/bug） | 自动重试 ≤3 |
| DATA | 数据失败（缺失/质量/样本） | 数据补充，挂起 |
| METH | 方法失败（功效/假设/参数） | 修订实验 exp_N+1 |
| HYP | 假设失败（方向相反/不显著） | 假设 refuted/revised |
| EPIS | 认知失败（前提/文献错误） | 修订文献与假设前提 |

## 缩略语

| 缩写 | 全称 |
|------|------|
| DSH | DeepSeek Harness |
| HITL | Human-in-the-Loop 人机协作 |
| RAG | Retrieval-Augmented Generation |
| MCP | Model Context Protocol |
| CI | Continuous Integration |
| DOI | Digital Object Identifier |
| CI(统计) | Confidence Interval 置信区间 |
| DP | Differential Privacy 差分隐私 |
| PHI | Protected Health Information 受保护健康信息 |
| SaaS | Software as a Service |
| WORM | Write Once Read Many 一次写多次读（审计存储） |

## 状态枚举

- **假设**：`proposed / testing / supported / refuted / revised / abandoned`
- **实验**：`draft / running / completed / failed(临时) / concluded_failed / suspended / abandoned`
- **阶段**：`literature / question / experiment / analysis / writing`
