# 模块说明

**目的**：逐模块描述职责、公开接口、依赖与耦合边界，落实"高内聚、低耦合、可测试"。每个模块对应架构分层中的一个职责单元。

---

## 1. HAL（Harness Adapter Layer）`hal/`
- **职责**：把对运行底座的全部依赖收敛到单一目录；提供抽象接口 + DSH 实现 + 能力探测 + 版本锁。
- **公开接口**：`HarnessAdapter`（会话生命周期、Skill/工具注册、轨迹导出、Preset/权限、子代理、capabilities）。详见 `interfaces.md`。
- **依赖**：仅依赖底座（DSH）。被编排层、领域层加载逻辑依赖。
- **耦合边界**：全项目唯一允许 import 底座的模块；其余模块只 import `hal.interface`。
- **可测试性**：单测覆盖率 100%；`contract_tests/` 锁定每个接口行为 + 降级路径。

## 2. Orchestrator Lite（编排内核）`orchestrator/`
- **职责**：无状态事件处理器，提供阶段门禁、失败回流、预算硬阻断、状态机推进与会话驱动、DOI 可验证率度量。
- **公开接口**：CLI `vl init/gate/loop/budget/lock/bundle/finalize/identity/rag/run/advance/verify-dois`；纯函数 `gates.py`（规则来自 `gates.rules.yaml`）；`runner.py`（`Runner`：`pre_session` 硬阻断链 = 门禁+预算+失败回流，`start_phase_session` 经 HAL 驱动底座，`advance` 推进 `current_phase`）；`budget.py`（`evaluate_budget` 纯函数，CLI 与 runner 共用的单一预算语义来源）；`doi_metrics.py`（DOI 可验证率采集/校验/聚合/持久化）；`hooks/on_change.py`（文件变更监听自动触发 `vl loop` 回流检查，`--once`/常驻轮询两模式）。
- **依赖**：`hal`（仅 `bundle_loader.py` 与 `runner.py` 两处，依赖收敛纪律的显式例外）、Workspace 文件（真相源）、Sidecar 工具（归因复核与 DOI 校验）。
- **耦合边界**：不持有状态、不建数据库；规则来自 `gates.rules.yaml`（声明式，专家可改）。
- **可测试性**：门禁为纯函数，可直接单测；Golden 轨迹回归覆盖端到端；`tests/runner/` 覆盖状态机/硬阻断/降级留痕，`tests/unit/` 覆盖 budget / on_change / doi_metrics。

## 3. 失败驱动迭代模块（Failure Loop，属编排层）`orchestrator/failure_loop.py`
- **职责**：扫描 failed 实验，强制归因登记与分类路由，驱动假设树迭代。
- **公开接口**：`vl loop`；内部消费 `failure_ledger.json`。
- **依赖**：failure_ledger schema、Sidecar 功效分析（复核）、假设树。
- **耦合边界**：不自动改写假设树，只生成"回流建议包"由人确认。

## 4. Bundle 工厂 + 加载器（领域包体系）`orchestrator/bundle_factory.py` + `orchestrator/bundle_loader.py` + `bundles/`
- **职责**：半自动生成学科 Bundle（L0/L1/L2）；把 bundle.yml 声明注册到运行底座。
- **公开接口**：`vl bundle new <discipline>`；`vl bundle validate <dir>`；`vl bundle load <dir>`；`_template/` 骨架。
- **依赖**：编排层加载逻辑（bundle_loader → HAL `register_skills` / `declare_mcp_servers` / `apply_preset_patch`）；通用 `skills/`。
- **耦合边界**：bundle.yml 只声明 Skill/Preset Patch/MCP/golden_cases，不直接调用底座内核；能力缺失（mcp/preset_patch）必须显式降级并记录，禁止静默失败（design-blueprint.md §2.1 降级表）。

## 5. 侧车层（Sidecar）`sidecar/`
- **职责**：确定性计算与外部对接（RAG/DOI/统计/功效/图表/脱敏/HPC）。
- **公开接口**：注册为底座 tool 或 MCP Server（见 `tool-calling.md`）；每工具 stdio 一次性入口 `python -m sidecar.tools.<tool>`；**常驻守护进程** `python -m sidecar.daemon`（NDJSON 行协议单进程多工具，见 `interfaces.md` §4；工具注册表 `sidecar/tools/_registry.py`）。
- **依赖**：经 HAL `register_tools` / `declare_mcp_servers` 注册；不感知底座内部。
- **耦合边界**：纯函数/常驻进程，资源隔离，无 AI 推断。

## 6. 领域 Skills `skills/` + `bundles/*/skills/`
- **职责**：方法论约束（影响模型"怎么想/怎么写"）。
- **公开接口**：`SKILL.md`（触发条件/流程/输出 Schema/参考文件）+ 引用脚本。
- **依赖**：被 HAL `register_skills` 加载；知识走检索，不硬编码。

## 7. 协作与制品管理（属编排层 + Git）
- **职责**：Git 分支=假设分支、制品写锁、审阅批注。
- **公开接口**：`vl lock <acquire|release>`；`RESEARCH.yaml.locks`。
- **依赖**：Git；pre_session hook 检查冲突。

---

## 模块依赖关系图（简化）

```
hal/  ←── orchestrator/ ──→ sidecar/ (注册)
  ↑          ↑                  ↑
  │          └──→ bundles/ ─────┘
  │               skills/
  └── DSH(底座)
```

**耦合纪律**：箭头方向不可逆（上层依赖下层抽象，下层不反向依赖上层）；HAL 是唯一穿透到底座的边。
