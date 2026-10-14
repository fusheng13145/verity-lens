# VerityLens（真理之眼）科研全能 Agent 系统 — 完整设计方案

**文档版本**：1.0（完整交付版，自包含）
**最后更新**：2026-10-14
**目标定位**：面向实验室内部科研助手原型（1–10 人团队）。核心目标为"可复现、可审计、可持续演进"，所有设计均围绕此目标收敛。企业级多租户 SaaS 不在本方案范围（评估见附录 A）。
**底座选型**：以 DeepSeek Harness（DSH）为当前运行底座，但通过适配层隔离，使其可替换为其他同类 Harness。

---

## 第一部分：总体架构

### 1.1 设计原则

1. **依赖收敛原则**：全项目只允许 `hal/` 目录直接感知运行底座（DSH）的模块与目录约定（`.dsh/`、Skill 目录、Preset 格式）。其余模块只面向 HAL 定义的抽象接口编程。HAL 在启动时执行**能力探测（capability probe）**：检测当前底座版本支持哪些特性，不支持的能力显式降级或报错，绝不静默失败。
2. **文件即状态原则**：项目状态完全由 Workspace 内的声明式文件（RESEARCH.yaml、hypothesis_tree.json、failure_ledger.json、experiments/*.yaml）表达。编排层是无状态的事件处理器，监听文件变更并执行规则。编排层崩溃后重启即从文件恢复，无需独立数据库与状态重建逻辑。
3. **失败是一等公民原则**：失败不是异常分支，而是研究生命周期的一等状态。每次失败必须结构化登记（归因分类 + 证据 + 决策），并强制走回流协议——要么生成新假设、要么修订实验参数、要么显式放弃假设。不允许"失败了但什么都没发生"。
4. **方法论进 Schema，不进提示词原则**：学科差异的可工程化部分 = 输出结构、必填字段、验证脚本。模型行为靠 SKILL.md 约束，产出靠 JSON Schema 验证，验证靠确定性脚本执行。三者分离，使学科包可以渐进交付。
5. **协作以制品为单位，不以会话为单位原则**：多人协作的对象是文件与实验制品，不是 Agent 会话。会话永远是单人的；协作通过 Git + 制品写锁 + 审阅批注完成。

### 1.2 架构分层

```
┌─────────────────────────────────────────────────────────────────┐
│  交互层（A）                                                     │
│  CLI（首选入口 vl） / DSH Web UI / Headless API                  │
│  一个科研项目 = 一个 Workspace 目录 = 一条 Git 历史               │
├─────────────────────────────────────────────────────────────────┤
│  编排层（C）Orchestrator Lite —— 自研，无状态事件处理器          │
│  ① 阶段门禁与 HITL   ② 失败回流引擎   ③ 预算硬阻断              │
│  （制品库 = 文件系统约定；状态同步 = 文件监听，不建独立服务）      │
├─────────────────────────────────────────────────────────────────┤
│  适配层（H）HAL: Harness Adapter Layer —— 自研，依赖收敛点        │
│  · 会话生命周期接口   · Skill/工具注册接口   · 轨迹导出接口       │
│  · Preset/权限接口    · 子代理接口          · 版本能力探测        │
├─────────────────────────────────────────────────────────────────┤
│  底座层（B）运行底座（当前实现：DeepSeek Harness）                │
│  Cordis 微内核 / Session Log / Trajectory 分叉 / 沙箱             │
├─────────────────────────────────────────────────────────────────┤
│  领域层（D）学科 Bundle（L0/L1/L2 分级）                          │
│  SKILL.md 方法论约束 + 验证脚本 + （可选）MCP 声明                │
├─────────────────────────────────────────────────────────────────┤
│  侧车层（E）Python 常驻进程                                       │
│  文献 RAG / DOI 校验 / 统计检验 / 功效分析 / 图表渲染 / 脱敏 / HPC │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 核心分工

| 职责 | 归属 |
|------|------|
| 让模型读写文件、调工具、持续干活、留痕迹 | 运行底座（DSH） |
| 跨阶段门禁、失败回流、资源与成本管控、制品协作 | 编排层（Orchestrator Lite） |
| 把底座依赖收敛到单一接口、版本适配与降级 | 适配层（HAL） |
| 学科差异（术语、规范、验证、可视化模板） | 领域层（Bundle） |
| 确定性计算、长任务执行、外部系统对接 | 侧车层（Sidecar） |

### 1.4 工程目录结构（落地即用的完整布局）

```
verity-lens/
├── hal/                              # Harness 适配层（唯一直接依赖底座的模块）
│   ├── __init__.py
│   ├── interface.py                  #   抽象接口定义（HarnessAdapter Protocol）
│   ├── dsh_adapter.py                #   DSH 实现
│   ├── capability_probe.py           #   能力探测与降级
│   ├── version_lock.yml              #   已验证底座版本与已知差异
│   └── contract_tests/               #   契约测试（每个接口 + 降级路径）
├── orchestrator/                     # Orchestrator Lite（无状态事件处理器）
│   ├── cli.py                        #   vl 命令入口（init/gate/loop/budget/lock/bundle/finalize）
│   ├── gates.py                      #   阶段门禁纯函数
│   ├── gates.rules.yaml              #   声明式门禁规则表（专家可读可改）
│   ├── failure_loop.py               #   失败回流引擎
│   ├── budget.py                     #   预算硬阻断
│   ├── bundle_factory.py             #   Bundle 生成器
│   ├── hooks/
│   │   ├── pre_session.sh            #   会话启动前：门禁+预算+回流+锁检查（硬阻断点）
│   │   └── on_change.py              #   文件监听：实验状态变更 → 触发回流检查
│   └── schemas/                      #   JSON Schema 集（RESEARCH/hypothesis_tree/experiment/failure_ledger）
├── bundles/                          # 学科包（L0/L1/L2）
│   ├── _template/                    #   Bundle 工厂模板（L0 骨架样例）
│   ├── biomed/
│   ├── materials/
│   └── compsci/
├── skills/                           # 跨学科通用 Skills
│   ├── literature/  statistics/  plotting/  reproducibility/
├── sidecar/
│   ├── tools/                        #   注册为底座 tool 的确定性工具
│   │   ├── stat_test.py              #   统计检验
│   │   ├── power_analysis.py         #   事后/先验功效分析（失败归因复核）
│   │   ├── doi_verify.py             #   DOI 校验
│   │   └── hpc_submit.py             #   HPC 作业提交
│   ├── rag/                          #   文献 RAG（分片/缓存/召回/防膨胀）
│   │   ├── literature_rag.py
│   │   └── code_rag.py
│   └── security/
│       └── desensitize.py            #   敏感数据脱敏（k-匿名 / PHI 屏蔽 / DP 聚合）
├── workspaces/<project-id>/          # 每 Git 仓库一个项目
│   ├── RESEARCH.yaml                 #   项目元数据/阶段/审批/写锁/预算
│   ├── docs/
│   │   ├── literature_notes.md
│   │   ├── hypothesis_tree.json
│   │   ├── failure_ledger.json       #   失败登记簿
│   │   └── lessons.md                #   由 failure_ledger 渲染的人读层
│   ├── experiments/exp_NNN.yaml      # + 各实验 manifest.yaml
│   ├── data/raw/（只读）  data/processed/
│   ├── figures/
│   ├── manuscript/
│   └── analysis/
└── tests/
    ├── golden/                       # 轨迹回归用例（含失败闭环用例）
    ├── correctness/                  # 科研正确性抽检
    └── hal_contract/                 # 适配层契约测试
```

---

## 第二部分：核心功能模块

### 2.1 HAL：Harness 适配层

#### 2.1.1 接口定义（全项目唯一直接感知底座的模块）

```python
# hal/interface.py
from typing import Protocol, Iterator, Literal

class HarnessAdapter(Protocol):
    # 会话生命周期
    def start_session(self, preset: str, workspace: str, task: str) -> "SessionHandle": ...
    def resume_session(self, handle: "SessionHandle") -> "SessionHandle": ...
    def stop_session(self, handle: "SessionHandle", graceful: bool = True) -> None: ...

    # 轨迹与可追溯性
    def export_session_log(self, handle: "SessionHandle") -> Iterator[dict]: ...
    def fork_trajectory(self, handle: "SessionHandle", at_event: str) -> "SessionHandle": ...
    def replay_to(self, handle: "SessionHandle", event_id: str) -> None: ...

    # Skill / 工具注册
    def register_skills(self, skill_dirs: list[str]) -> None: ...
    def register_tools(self, tools: list["ToolSpec"]) -> None: ...
    def declare_mcp_servers(self, config: dict) -> None: ...

    # 权限与 Preset
    def apply_preset_patch(self, patch: "PresetPatch") -> None: ...
    def set_permission(self, scope: str, level: Literal["read", "workspace_write", "none"]) -> None: ...

    # 子代理
    def spawn_subagent(self, spec: "SubagentSpec") -> "SubagentHandle": ...

    # 能力探测
    def capabilities(self) -> dict:
        """返回当前底座支持的特性集合，如
        {'trajectory_fork': True, 'preset_patch': True,
         'subagent': True, 'mcp': True, 'session_log_export': True}"""
```

#### 2.1.2 依赖面清单（Dependency Surface）

除下表外，任何模块 import 底座内部 API 视为 Code Review 阻断项：

| 依赖点 | 用途 | 降级策略 |
|--------|------|----------|
| Skill 目录规范（SKILL.md + 引用文件） | 方法论注入 | 若格式变更，HAL 内做格式转换器 |
| Preset / Preset Patch | 阶段化配置 | 降级为启动参数注入系统提示 |
| Session Log 导出 | 审计与恢复 | 最低限度：要求能导出文本日志 |
| Trajectory 分叉 | 假设分支实验 | **可选能力**：不支持时禁用"平行假设对照"，不影响主流程 |
| 子代理 | 上下文隔离 | **可选能力**：不支持时主会话串行执行并压缩上下文 |
| MCP 客户端 | 外部数据服务 | 可替换为 Sidecar 直接 HTTP 调用 |

#### 2.1.3 能力探测与版本锁

```yaml
# hal/version_lock.yml
verified_version: "2.4.0"
capabilities:
  trajectory_fork: true
  preset_patch: true
  subagent: true
  mcp: true
  session_log_export: true
known_differences: []
# 升级流程：改 version_lock.yml → CI 跑 hal_contract 测试 → 通过则更新；失败则 HAL 修复
```

**工程纪律**：`hal/` 单测覆盖率 100%；每次底座版本升级先跑 `make hal-contract-test`，再跑 Golden 回归；每季度做一次"切换演练"评估备选底座接入成本。

### 2.2 Orchestrator Lite：轻量编排内核

#### 2.2.1 形态：工具集 + 钩子，而非常驻服务

```
orchestrator/cli.py  →  vl <command>
  vl init <discipline>          # 生成 Workspace 脚手架 + 挂载 L0 Bundle
  vl gate <phase>               # 阶段门禁纯函数校验
  vl loop                       # 失败回流检查/执行
  vl budget check               # 预算硬阻断校验
  vl lock <acquire|release>     # 制品写锁管理
  vl bundle new <discipline>    # Bundle 生成器
  vl finalize                   # 收尾：manifest + reproduce + 导出
```

**MVP 能力边界（只做三件事）**：

| 能力 | 实现方式 | 明确不做 |
|------|----------|----------|
| 阶段门禁 | `vl gate <phase>` 纯函数校验 Workspace 文件；由 pre_session hook 在每次启动会话前调用 | 不做常驻审批 API；HITL = 在 RESEARCH.yaml 写 approval 记录 + Git commit |
| 失败回流 | `vl loop` 扫描 experiments 中 status=failed，校验是否已按 §2.4 完成归因与决策 | 不自动改写假设树；生成"回流建议包"由研究者确认 |
| 预算硬阻断 | `vl budget check` 读 token_budget，会话前估算，超限即拒绝启动 + 输出恢复选项 | 不做运行中逐 turn 拦截（依赖 HAL 能力探测，可用则启用） |

**状态机（单一定义）**：

```
literature ──► question ──► experiment ──► analysis ──► writing
                  ▲             │ failed        │
                  │             ▼               │
                  └────── [ failure_loop ] ◄────┘
           （归因 → 假设修订/参数调整 → 回到 experiment；
             显式放弃假设 → 回到 question）
```

阶段推进的唯一写入口是编辑 RESEARCH.yaml（需通过 `vl gate` 校验后 commit）——天然幂等、可审计、可恢复，无独立状态库。

### 2.3 研究生命周期与阶段门禁

五阶段：`literature → question → experiment → analysis → writing`。门禁规则为**声明式规则表**（降低开发量，专家可读可改）：

```yaml
# orchestrator/gates.rules.yaml
gates:
  literature:
    entry_requires: []
  question:
    entry_requires:
      - file: docs/literature_notes.md
        check: non_empty
      - file: docs/hypothesis_tree.json
        check: schema_valid
      - condition: "hypotheses.len >= 1 and all(h.statement != '')"
    hitl_required: true          # 需在 RESEARCH.yaml.approvals 有记录
  experiment:
    entry_requires:
      - condition: "current_phase == 'question'"
      - condition: "approvals.question.approved_by != null"
      - file: experiments/exp_*.yaml
        check: "count >= 1 and schema_valid"
  analysis:
    entry_requires:
      - condition: "all(experiments.status in ['completed','concluded_failed','abandoned'])"
        # 注意：failed 不是合法停留状态，必须经 failure_loop 转为终态
  writing:
    entry_requires:
      - file: analysis/summary.md
        check: non_empty
      - condition: "all(figures.generated)"
    hitl_required: true
```

### 2.4 失败驱动迭代模块（核心业务闭环）

#### 2.4.1 失败分类学（Failure Taxonomy）

| 大类 | 编码 | 子类示例 | 回流动作 |
|------|------|----------|----------|
| 执行失败 | EXEC | 资源不足 / 超时 / 环境错误 / 代码 bug | 修复执行环境，**不回流假设树**，重跑同一实验（重试上限 3 次） |
| 数据失败 | DATA | 数据缺失 / 质量不足 / 样本量不够 | 生成"数据补充任务"，实验挂起（suspended） |
| 方法失败 | METH | 统计功效不足 / 方法假设不成立 / 参数敏感 | **回流**：修订实验参数或替换方法，生成 exp_NNN+1 |
| 假设失败 | HYP | 结果与假设方向相反 / 效应量不显著 | **回流**：假设树节点 refuted/revised，触发新假设生成 |
| 认知失败 | EPIS | 前提假设（文献依据）错误 | **回流**：修订相关文献笔记与假设陈述，可能级联修订多个节点 |

#### 2.4.2 failure_ledger.json 数据 Schema（必填，结构化）

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "entries": [
    {
      "id": "F-001",
      "experiment_id": "exp_001",
      "hypothesis_id": "H1",
      "phase": "experiment",
      "detected_at": "2026-10-20T14:00:00Z",
      "classification": {
        "category": "METH",
        "code": "METH-POWER-LOW",
        "confidence": 0.8,
        "rationale": "p=0.12，效应量 d=0.35，事后功效分析 power=0.41 < 0.8，样本量不足以检出该效应"
      },
      "evidence": [
        {"path": "data/processed/exp_001/stats_report.json", "locator": "$.power"},
        {"path": ".dsh/session_log", "event": "evt_0341"}
      ],
      "decision": {
        "type": "revise_experiment",
        "action": "exp_002",
        "changes": ["num_samples: 100 -> 250", "改用单侧检验"],
        "hypothesis_impact": {"H1": {"status": "testing", "confidence_change": -0.1}},
        "approved_by": "researcher_pi",
        "approved_at": "2026-10-20T16:30:00Z"
      },
      "lesson": "小样本下 AF2 构象差异效应量可能被高估；后续实验设计前先做功效分析",
      "tags": ["power-analysis", "sample-size"]
    }
  ]
}
```

#### 2.4.3 回流流程（关键流程）

```
实验结束 status=failed
   │
   ▼
vl loop 校验：是否已登记 failure_ledger 条目？
   │ 否 → 阻塞，要求会话生成归因草案（附实验产物 + Session Log 片段）
   ▼ 是
归因分类（Agent 起草 → 确定性工具复核：事后功效分析由 power_analysis 复算）
   │
   ▼
按分类路由：
   ├─ EXEC → 自动重试（≤3 次）；超限升级 HITL
   ├─ DATA → 生成数据补充任务清单（人工执行），实验挂起
   ├─ METH → 生成 exp_NNN+1 修订草案（参数 diff + 理由）→ HITL 审批 → 回 experiment
   ├─ HYP  → 更新假设树：H_x.status → refuted / revised
   │          → Agent 生成 2-3 个候选新假设（引用 failure_ledger 证据）
   │          → HITL 审批 → 挂入假设树 → 回 experiment 或 question
   └─ EPIS → 修订文献笔记 + 假设陈述（级联检查受影响节点）→ 回 question
   │
   ▼
lessons.md 自动追加（从结构化 entry 渲染，保留人读摘要层）
```

#### 2.4.4 假设树与实验状态机

```
hypothesis status:
  proposed → testing → supported
           ├→ refuted（被 HYP/EPIS 类失败证伪，终态，保留证据链）
           ├→ revised（修订后生成 H_x.1 新节点，原节点保留，parent 链可追溯）
           └→ abandoned（PI 显式放弃，需附 failure_ledger 引用）

experiment status:
  draft → running → completed
        ├→ failed（临时态，必须经 failure_loop 处理）
        ├→ concluded_failed（归因完成、决策已批准的终态）
        ├→ suspended（等待数据/资源）
        └→ abandoned
```

**硬约束（由 `vl gate` 强制）**：
1. 任何 experiment 停留在 `failed` 超过一次会话周期即阻塞后续阶段推进；
2. `refuted` 假设不可直接删除，必须保留节点与证据链（科研诚信）；
3. 新假设（revised 产物）的 statement 必须引用 failure_ledger 条目 ID 作为依据。

### 2.5 协作与制品管理

#### 2.5.1 协作边界（明确声明）

| 场景 | 支持 | 机制 |
|------|------|------|
| 单人单项目 | 完全支持 | 原生 |
| 小组并行研究（不同假设/实验分支） | 支持 | Git 分支 = 假设分支：`hypothesis/H1`、`hypothesis/H2` 各自推进，merge 前过 `vl gate` |
| 多人共同写作（串行交接） | 支持 | 制品写锁 + Git PR + review |
| 多人同时编辑同一文件 | **不支持，明确为非目标** | — |
| 多人共享同一 Agent 会话 | **不支持，明确为非目标** | — |

#### 2.5.2 制品写锁协议

```yaml
# RESEARCH.yaml 中
locks:
  manuscript:
    holder: "researcher_b"
    acquired_at: "2026-10-14T09:00:00Z"
    expires_at: "2026-10-16T09:00:00Z"   # 超时自动失效，防止死锁
```

写锁由 `vl lock acquire/release` 管理，`pre_session.sh` 检查冲突。与 Git 分支保护（main 需 PR）配合，覆盖 1–10 人团队的真实协作强度。

#### 2.5.3 制品归属与审计

每个实验目录附带 `manifest.yaml`：记录模型版本、token 消耗、输入数据 hash、随机种子、执行环境。`make reproduce` 依赖 manifest 完成从 raw 数据到 figures 的复现。大文件（权重、原始数据）走 MinIO/S3 + 引用计数，Git 只存小文件与元数据。

### 2.6 Bundle 工厂（学科包体系）

#### 2.6.1 三级 Bundle 分级标准

| 级别 | 内容 | 交付成本 | 能力 |
|------|------|----------|------|
| **L0 骨架** | bundle.yml + 1 个 SKILL.md（方法论约束 + 输出 Schema）+ 复用通用验证脚本 | 专家 0.5–1 天访谈 + 工程师 0.5 天 | 阶段流程可跑，产出结构合规 |
| **L1 可用** | + 2–3 个领域专用验证脚本 + 领域术语表 | 专家 2–3 天 + 工程师 2 天 | 产出可通过领域正确性抽检 |
| **L2 完备** | + 专用 MCP 声明 + Preset Patch + Golden 用例 | 专家 1 周 + 工程师 1 周 | 完整学科闭环，换 Bundle 即切换学科 |

**关键规则：新学科一律从 L0 起步，禁止一次性追求 L2。** 通用层（statistics、plotting、reproducibility skills + 通用验证脚本）覆盖 70% 需求，Bundle 只沉淀真正的领域差异。

#### 2.6.2 Bundle 生成器流程（半自动）

```
领域专家访谈提纲（预置问卷：术语/规范/必报指标/常见错误/参考标准）
   │
   ▼
vl bundle new <discipline>  → 按 _template/ 与访谈回答自动产出 L0 骨架
   （bundle.yml / SKILL.md 草稿 / 引用通用 schema / 验证脚本占位）
   ▼
专家评审 SKILL.md 草稿（Markdown diff，非工程工具）
   ▼
工程师补验证脚本（L0→L1）→ Golden 用例（L1→L2）
```

生成器保证结构一致性（目录、命名、schema 引用标准化），专家只需提供领域知识内容。

#### 2.6.3 Bundle 与 HAL 解耦

bundle.yml 只声明：Skill 路径、Preset Patch（可选）、MCP 配置（可选）。**加载逻辑由编排层实现**（复制到 HAL 注册接口），不直接调用任何底座内部机制——底座内核变更只需改 HAL 一处，Bundle 体系不受影响。

### 2.7 侧车层（确定性计算与外部对接）

| 工具 | 职责 | 备注 |
|------|------|------|
| 文献 RAG | 语义分片 / MMR 去重 / 会话缓存 / token 预算 / citation-only 降级 / auto-archive | 见 §2.7.1 |
| DOI 校验 | 文献引用逐一验证存在性（HTTP 200 + 元数据匹配） | 引用有效性 ≥95% |
| 统计检验 | t 检验 / ANOVA / 非参数 / 多重校正 | 数值确定性复算 |
| 功效分析 | 先验/事后功效分析 | 承担失败归因复核（METH 类） |
| 图表渲染 | 学科可视化模板 | 数据与原始文件一致性比对 |
| 脱敏 | k-匿名 / PHI 屏蔽 / DP 聚合（ε=1.0） | 敏感数据永不进模型上下文 |
| HPC 提交 | 长任务远程提交 + 状态轮询 | 规避终端关闭即中断 |

#### 2.7.1 文献 RAG 侧车配置（可直接使用）

```python
# sidecar/rag/literature_rag.py（配置摘要）
CHUNKING_CONFIG = {"method":"semantic","max_chunk_size":1024,"overlap":128,
                   "metadata_fields":["doi","year","journal","section_title","authors","pub_type"],
                   "chunk_by_section":True}
INDEXING_CONFIG = {"embeddings_model":"text-embedding-3-small","vector_dim":1536,
                   "index_type":"HNSW","update_trigger":"on_new_bib_entry","dedup_by":"doi"}
RETRIEVAL_CONFIG = {"top_k":8,"score_threshold":0.72,"diversity_penalty":0.3}
CACHE_CONFIG = {"per_session_limit":50,"ttl":"session","eviction_policy":"LRU"}
TOKEN_BUDGET_CONFIG = {"max_context_tokens_per_turn":4000,"overflow_strategy":"truncate_oldest",
                       "warning_threshold":0.7,"hard_limit":6000}
ANTI_BLOAT_CONFIG = {"auto_archive":{"trigger":"项目 > 3 个月未活动","restore":"用户明确引用时按需拉回"}}
```

调用流程：研究者提问 → 编排层查 token 预算 → 充足则 RAG 检索（缓存命中→返回；否则向量检索→相似度过滤>0.72→MMR 去重→top-k）→ 计算注入 token → 超预算则触发 citation_only_mode（仅返回引用元数据）→ 组装注入底座上下文 → Session Log 记录引用 → 更新预算。

### 2.8 成本与安全

#### 2.8.1 预算模型

```yaml
# config/cost_control.yaml
budget_hierarchy:
  instance_level: { monthly_cap: 2000000 }
  project_level:
    total_cap: 500000
    per_phase_cap: { literature:100000, question:50000, experiment:200000, analysis:100000, writing:50000 }
  turn_level: { max_tokens_per_turn: 8000, max_subagent_calls: 5 }
model_tier:
  tier1_pro:  { model:"deepseek-chat-v4-pro",   cost_multiplier:1.0,  use_for:["复杂推理","假设生成","论文撰写","评审回复"] }
  tier2_flash: { model:"deepseek-chat-v4-flash", cost_multiplier:0.15, use_for:["文献抽取","格式化","批量参数生成","摘要"] }
```

执行策略：全局月度/项目总预算≥100% → **HARD_BLOCK**；阶段预算≥100% → HARD_BLOCK，≥70% → SOFT_WARNING；单轮估算超限 → **AUTO_DOWNGRADE**（pro→flash、RAG citation-only、关闭非必要子代理）。批量任务分片（normal batch_size=10/interval=60s，high=3/120s），每批执行前查预算，硬阻断时暂停队列等人工介入。

硬阻断恢复：编排层暂停当前阶段所有会话 → 导出 Session Log → 通知研究者（预算使用率/已完成产物/恢复选项）→ 研究者选 A 追加预算(+20%) / B 切廉价模型 / C 手动接管 → `dsh resume` 从断点继续。

#### 2.8.2 沙箱安全

```yaml
# docker/sandbox-compose.yml（要点）
services:
  dsh-sandbox:
    security_opt: [no-new-privileges:true, seccomp=unconfined]
    cap_drop: [ALL]; cap_add: [CHOWN]
    network_mode: "none"; read_only: true
    tmpfs: [/tmp:size=1g, /var/tmp:size=512m]
    volumes:
      - ./workspaces/${PROJECT_ID}/data/raw:/workspace/data/raw:ro
      - ./workspaces/${PROJECT_ID}/data/processed:/workspace/data/processed:rw
      - ./workspaces/${PROJECT_ID}/figures:/workspace/figures:rw
      - ./workspaces/${PROJECT_ID}/manuscript:/workspace/manuscript:rw
    resources: { limits: { cpus:"4", memory:"8g", pids:100 } }
    environment: [DSH_WORKSPACE=/workspace, DSH_PERMISSION=workspace_write]
```

敏感数据治理管道：① 原始敏感数据存 data/raw/（容器外，底座无访问权限）② Sidecar 脱敏（k-匿名/差分隐私/字段屏蔽）③ 脱敏版写入 data/processed/（底座可读）④ Agent 仅基于脱敏数据推理 ⑤ 涉及个体的结论必须经人工审核。`never_in_context`：患者身份、未发表合作者数据、商业机密、API 密钥、机构内部评审信息。

---

## 第三部分：关键流程

### 3.1 端到端研究流程（正常路径）

```
1. vl init <discipline>          → 生成 Workspace 脚手架 + 挂载 L0 Bundle
2. literature 阶段会话           → 底座 + 文献 RAG 检索 → literature_notes.md
3. vl gate question              → 校验笔记与假设树初稿 → HITL：PI 在 RESEARCH.yaml 记录 approval
4. question 阶段会话             → 假设树细化（每条假设带 evidence 引用）
5. vl gate experiment            → 校验实验配置 schema
6. experiment 阶段会话           → 实验配置 → Sidecar 提交 HPC/本地 → 结果回写
7. 实验结束：completed → analysis；failed → §3.2 失败回流
8. vl gate analysis              → 所有实验处于终态
9. analysis 阶段会话             → 统计汇总（sidecar 复算）→ 图表 → summary.md
10. vl gate writing（HITL）      → writing 阶段会话 → 论文草稿（含 AI 贡献声明）
11. vl finalize                  → manifest 汇总 + make reproduce 校验 + 导出
```

### 3.2 失败回流流程

```
exp 失败 → vl loop 强制归因登记（sidecar 复核）
  → EXEC: 自动重试 ≤3 → 超限 HITL
  → DATA: 数据补充任务，挂起
  → METH: 修订实验 exp_N+1（HITL）→ 重跑
  → HYP:  假设 refuted/revised → 新假设生成（HITL）→ 挂树 → 重跑或回 question
  → EPIS: 修订文献与假设前提（级联检查）→ 回 question
最终：failure_ledger 留痕 + lessons.md 渲染 + 假设树版本 +1
```

### 3.3 会话启动前门禁（每次底座会话必经）

```
pre_session.sh:
  ① vl gate <current_phase>     → 不通过：输出缺失清单，拒绝启动
  ② vl budget check             → HARD_BLOCK：暂停并输出恢复选项
  ③ vl loop check               → 有未处理 failed 实验或未批准回流：拒绝启动
  ④ vl lock check               → 写锁冲突（写作阶段）：只读模式启动
  ⑤ HAL capabilities 探测       → 特性缺失时显式降级并记录
```

### 3.4 底座升级回归流程

```
底座新版本发布 → 修改 hal/version_lock.yml
  → CI: hal_contract 测试（100% 通过）
  → CI: Layer1 Schema 校验 + Layer2 Golden 轨迹回归（edit distance ≤ 2）
  → 通过：更新版本锁；失败：HAL 适配修复后重跑
```

---

## 第四部分：数据设计

### 4.1 数据文件总览（Workspace 内，Git 管理）

| 文件 | 职责 | 写入者 |
|------|------|--------|
| `RESEARCH.yaml` | 项目元数据/阶段/假设索引/审批/写锁/token 预算 | 人 + 统计脚本 |
| `docs/hypothesis_tree.json` | 假设树（含 refuted/revised 状态与证据链） | 底座（经 HITL） |
| `docs/failure_ledger.json` | 失败登记簿 | 底座起草 + 人批准 |
| `experiments/exp_NNN.yaml` | 实验配置与结果状态 | 底座 + 人 |
| `analysis/summary.md`、`figures/`、`manuscript/` | 分析与产出 | 底座 |
| `lessons.md` | 失败模式库（由 failure_ledger 渲染） | 自动生成 |
| `manifest.yaml`（每实验） | 可复现性元数据 | 自动 |

### 4.2 RESEARCH.yaml（完整字段）

```yaml
project_id: "proj_20261014_001"
discipline: "biomed"
research_question: "AlphaFold2 预测的构象差异能否作为 AD 早期生物标志物？"
current_phase: "experiment"

approvals:
  question: { approved_by: "researcher_pi", approved_at: "2026-10-15T10:00:00Z", note: "H1/H2 通过评审" }
  writing:  { approved_by: null, approved_at: null, note: null }

locks: {}                                # 写作阶段写锁记录

degraded_features: []                    # 如 ["trajectory_fork"]（底座版本不支持时）

hypotheses:
  - { id: H1, status: testing, confidence: 0.55 }
  - { id: H2, status: proposed, confidence: null }

model_config:
  primary: "deepseek-chat-v4-pro"
  fallback: "deepseek-chat-v4-flash"

token_budget:
  total:      { cap: 500000, used: 42300 }
  per_phase:
    literature: { cap: 100000, used: 42300 }
    question:   { cap: 50000,  used: 0 }
    experiment: { cap: 200000, used: 0 }
    analysis:   { cap: 100000, used: 0 }
    writing:    { cap: 50000,  used: 0 }
```

### 4.3 hypothesis_tree.json（扩展字段）

```json
{
  "id": "H1.1",
  "parent_id": "H1",
  "type": "hypothesis",
  "content": "AD 组与对照组的 Aβ 寡聚体构象 RMSD 差异在 n=250 下可检出（d≥0.5）",
  "status": "testing",
  "confidence": 0.45,
  "children": ["E3"],
  "provenance": { "derived_from": "H1", "justified_by": ["F-001"], "version": 4 }
}
```

### 4.4 experiment.yaml（扩展字段）

```yaml
status: "concluded_failed"     # 状态机见 §2.4.4
retry_count: 1
failure_ref: "F-001"           # 关联失败登记簿
superseded_by: "exp_002"       # 被哪个修订实验接替
```

### 4.5 Schema 校验（CI 强制）

全部文件配 JSON Schema（`orchestrator/schemas/`）。Layer1 校验项：字段齐全、枚举合法、无循环引用、路径存在、failure_ledger 的 evidence 指针有效、refuted 节点必附证据链、abandoned 必附 failure_ledger 引用。

---

## 第五部分：边界情况与异常处理

| # | 边界/异常 | 处理规则 |
|---|-----------|----------|
| E1 | 实验 `failed`，研究者未做归因就尝试进入下一阶段 | `vl gate` 检测到存在 status=failed 实验 → 阻塞；必须先 `vl loop` 完成归因并转终态 |
| E2 | 假设被证伪后新假设无证据支撑 | revised 节点的 `justified_by` 必须引用 failure_ledger ID，否则 `vl gate` 拒绝 |
| E3 | 重试 3 次仍 EXEC 失败 | 升级 HITL，记录于 lessons.md，禁止无限重试 |
| E4 | 写锁持有者失联（未 release） | `expires_at` 超时自动失效；pre_session 检查冲突，避免死锁 |
| E5 | 同一文件两人并行改（Git 冲突） | 仅 main 分支需 PR + review；并行写作强制写锁，先到先得 |
| E6 | RAG token 注入超预算 | 触发 citation_only_mode（仅引用元数据），不注入全文 |
| E7 | 底座版本破坏性变更 | HAL 契约测试在 CI 拦截；季度切换演练评估备选底座 |
| E8 | 子代理/分叉能力缺失 | `capabilities()` 探测为 false → 主会话串行执行 + 上下文压缩，功能不报错降级 |
| E9 | 预算硬阻断（HARD_BLOCK） | 暂停会话、导出 Session Log、通知研究者三选项（追加/降级/接管） |
| E10 | 敏感数据误入上下文 | 脱敏管道在容器外完成；`never_in_context` 清单 + 正则扫描 prompt 告警 |
| E11 | 引用 DOI 无法验证 | 允许 ≤5% 预印本/撤稿论文例外；其余强制补全或删除引用 |
| E12 | 编排层崩溃 | 无状态设计：重启即从 Workspace 文件恢复，无需修复 |
| E13 | 长任务终端关闭 | 长任务走 Sidecar 远程提交，底座仅轮询状态；本地用 tmux/systemd 守护 headless 进程 |
| E14 | 假设树循环依赖 | Layer1 Schema 校验拒绝（parent_id 不得成环） |
| E15 | 多人同时持有写锁 | `vl lock acquire` 检查现有未过期锁，冲突则拒绝并提示持有人 |

---

## 第六部分：测试与验收

| 层 | 内容 | 通过标准 |
|----|------|----------|
| L1 Schema 校验（每次 commit） | 全部声明式文件 schema 校验 | 100% 通过 |
| L2 Golden 轨迹回归（每日 CI + 底座升级） | 固定输入 → 轨迹比对；HITL 触发；子代理权限；**含 METH/HYP 两类失败闭环用例各 3 例** | 事件序列 edit distance ≤ 2 |
| L3 科研正确性（周级 review） | 统计值 sidecar 复算一致；DOI ≥95% 可验证；图表数据一致；**每条 refuted 假设均有完整证据链、每条 failed 实验均有 failure_ledger 条目** | 100% / ≥95% |
| L4 HAL 契约测试（底座升级时） | HAL 接口行为 + 能力探测准确性 + 降级路径 | 100% 通过 |

**科研 Agent 验收维度总结**：Schema 完整性（全自动 100%）、轨迹合理性（全自动 ≤2）、数值正确性（全自动复算一致）、引用有效性（全自动 ≥95%）、方法论合规（半自动专家评审）、可复现性（`make reproduce` 从 raw 到 figures 完全一致，全自动）。

---

## 第七部分：实施路线图

| Phase | 时间 | 目标 | 交付物 | 退出标准 |
|-------|------|------|--------|----------|
| Phase 0 | 1–2 周 | 底座 + HAL 立桩 | HAL 接口 + DSH Adapter + 契约测试 + 版本锁；最小 Skill + sidecar 工具 | 同一任务轨迹可复现；**人为模拟底座破坏性变更，CI 能准确定位失效点** |
| Phase 1 | 3–6 周 | 单学科端到端闭环（含失败闭环） | biomed L0 Bundle；Orchestrator Lite（门禁/预算）；failure_ledger + 回流引擎 | 一个学科检索→写作跑通；**构造 METH 类失败用例走通"归因→修订→再实验"全链路** |
| Phase 2 | 7–12 周 | 领域包化 + 失败闭环完备 | Bundle 工厂 + L1 Bundle ×2；HYP/EPIS 回流；假设树 refuted/revised；Golden 扩充 | 换 Bundle 切换方法论；假设失败可自动产出合格新假设草案（审批通过率 ≥50%） |
| Phase 3 | 4–6 月 | 健壮性与协作 | 容器沙箱 + RAG 侧车 + 制品写锁 + Git 分支协作流 | >1000 篇文献稳定召回；2 人并行分支协作无冲突事故 |
| Phase 4 | 按需 | 扩展评估 | L2 Bundle；更多学科；**协作模型按实际需求重新评估（不预设方案）** | 3+ 学科 Bundle 在用；扩展决策有数据支撑 |

---

## 第八部分：风险与应对

| 风险 | 概率 | 应对 |
|------|------|------|
| 底座预览版破坏性变更 | 高 | HAL 依赖面清单 + 契约测试 + 版本锁；可选能力均有降级路径；季度切换演练 |
| 失败归因质量差 | 中 | 确定性工具复核；分类 confidence<0.6 强制 HITL；分类编码收敛 |
| 失败闭环变官僚流程拖慢迭代 | 中 | EXEC 类自动重试不经审批；回流决策包一次审批；重试计数自动管理 |
| 编排层再次膨胀 | 中 | 硬约束：不引入常驻服务与数据库；新需求进 gates.rules.yaml 声明式优先 |
| Bundle 专家投入不足 | 高 | L0 骨架把单学科启动压到 1–2 天；通用层兜底；访谈式生成器 |
| 协作需求超出 Git 流 | 低 | 写锁 + 分支保护覆盖 1–10 人；若不足 Phase 4 基于真实痛点重设计 |
| 幻觉污染科研产出 | 高 | DOI 强制校验、数值确定性复算、结论溯源到文件行号、写作 Preset 禁止无来源断言 |
| 成本失控 | 中 | 四级预算 + 硬阻断 + 自动降级；RAG citation-only 兜底 |
| 学术诚信 | 中 | manifest 记录模型/token/改动范围；AI 贡献声明自动生成；refuted 与失败记录强制留痕（同时增强诚信） |

---

## 附录 A：企业级 SaaS 可行性评估

| 维度 | 当前能力 | SaaS 所需 | 差距 |
|------|----------|-----------|------|
| 用户模型 | 单用户、本地优先 | 多租户、RBAC、SSO | 需从头搭建 |
| 并发 | 串行单会话 | 高并发、负载均衡 | 需 headless 集群化 |
| 沙箱 | Docker 单机 | 租户级强隔离（gVisor/Kata） | 需替换沙箱 |
| 审计 | 本地 Session Log | WORM 存储、不可篡改、合规报告 | 需独立审计服务 |
| 计费 | 粗略 token 统计 | 细粒度计费、用量报表、发票 | 需计费引擎 |
| 运维 | 无 | 监控、告警、SLA、灾备 | 需完整运维体系 |

**结论**：当前方案不适合作为企业级 SaaS 直接发布。SaaS 化需额外 6–12 个月专项投入（租户隔离层、身份权限、沙箱升级、审计合规、计费引擎、运维体系）。建议先在实验室内部打磨成熟（Phase 0–3），形成可验证的产品原型，再评估 SaaS 化。

## 附录 B：落地三条建议

1. **先把 HAL 立起来，再谈其他。** 把全部底座依赖压到一个目录、一份清单、一套契约测试里，决定底座升级是"改一个文件"还是"全项目返工"。
2. **失败闭环是科研 Agent 的核心竞争力。** 通用 LLM 已很会"做成功的实验"；系统价值在于如何系统性对待失败——归因可信、决策留痕、假设可迭代。必须作为基础交付，而非后期补丁。
3. **用分级和模板对抗生态成本。** Bundle 从 L0 起步、通用层兜底、访谈式生成，把"每个学科都要专家深度驻场"变成"每个学科专家投入 1–2 天"。宁可十个能跑的 L0，不要一个姗姗来迟的 L2。
