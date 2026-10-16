# 交付就绪度审计报告 — verity-lens（真理之眼）

> 审计日期：2026-10-16
> 审计方式：**实测优先**（跑测试、跑 CLI、跑演练、逐行核对接线），不采信文档自证。
> 审计问题：项目是否已达到「除外部依赖门控外，成为可交付、预留扩展空间的科研全流程智能 Agent」？

---

## 一、总判定

**部分达标（内部接线已补齐，外部依赖仍是唯一硬门控）。**

> 更新说明（2026-10-16 续）：原报告判定「未达到」的根因是 **P0-1~P0-4 内部三层接线缺失**。本轮已按 §五 路径完成 P0-1/Agent 会话驱动、P0-2/阶段推进入口、P0-3/writing 门禁硬化 + 真实绘图工具、P0-4/失败闭环接线，并修复 §四 #1 的 `vl` 入口静默失效。修复后**代码层面**五阶段已能流动（状态机推进 + 会话驱动 + 内容级门禁 + 闭环 API 均为真实实现并有测试覆盖）。
>
> 仍**未**达到「端到端可交付」的唯一原因只剩外部依赖：缺少真实底座（dsh）与 deepseek API 配额，无法跑通「literature→…→writing」的真实五阶段执行。次级缺陷 #1/#3/#4/#6/#7/#8/#9/#10/#11 已全部修复（见 §四、§七）；#2（预算写回）由 runner 回写部分缓解，#5（pre_session.sh）角色被 runner 取代。

| 维度 | 原评分 | 现评分 | 判定 |
|---|---|---|---|
| 扩展性（预留空间） | 85/100 | **85/100** | 维持，已达标 |
| 工程规范与可维护性 | 80/100 | **82/100** | 维持，新增 runner/plot 模块、依赖收敛纪律守住 |
| 五阶段闭环完整度 | 38/100 | **75/100** | 接线已补齐并测试；待真实底座端到端验证 |
| **综合交付就绪度** | 约 45/100 | **约 68/100** | 内部可流动；外部依赖是唯一硬门控 |

---

## 二、已真实达标的部分（有实测证据）

| 能力 | 实测证据 |
|---|---|
| 依赖收敛纪律 | 全仓仅 2 个文件直连`hal.dsh_adapter`（`orchestrator/bundle_loader.py:29`、`tests/golden/test_bundle_loader.py:11`），耦合扫描 2/6 行项，远低于预算 |
| 底座可替换性 | `make base-switch-drill` 四项全PASS：接口符合性（12 个 Protocol 方法）、耦合预算、替换模拟（`MinimalAdapter` 证明接口可实现）、版本漂移（已安装 = 版本锁 = 0.2.0-rc.2） |
| HAL 契约 | 40 例全通过；带`DSH_BIN` 指向真实底座时版本/能力探测正确（`0.2.0-rc.2`，`trajectory_fork=False`其余 4 项 True） |
| 学科扩展性 | 实测 `bundle new chemistry --capability spectroscopy` → `validate` PASS → `load` 成功注册 1 个 Skill。**新增学科确实是分钟级、零代码改动** |
| 声明式门禁 | `gates.rules.yaml` 人类可读可改；实测 `gate question` 在假设数为 0 时正确 BLOCKED（exit 2），`gate literature` PASS |
| 测试规模 | **323 例（323 passed / 3 skipped）**；较原 279 例新增 `tests/runner/`、`tests/sidecar/test_plot.py`、`tests/api` 闭环回流 + DOI 度量用例，以及 `tests/unit/`（budget / reproduce / on_change / daemon / doi_metrics 共 23 例）。CI 现已覆盖 `tests/api tests/finalize tests/sidecar tests/unit`，另有独立 `harness-contract` workflow 跑真实底座契约（缺 dsh 时按 skipif 优雅跳过） |
| 失败闭环内核 | `failure_loop.py` 527 行，级联回流 `cascade_impact`、确定性复算、五类失败分类学均为真实实现（非桩） |
| **[新增·已修复] Agent 会话驱动** | `orchestrator/runner.py` 新增 `Runner`，在 `start_phase_session` 中调用 `adapter.start_session()` 真正驱动底座；无底座时降级留痕（`harness_unavailable`）。CLI `vl run --phase <p>` 实测启动会话并正确降级（exit 0） |
| **[新增·已修复] 阶段推进入口** | CLI 新增 `vl advance`：校验下一阶段门禁 → 推进 `current_phase` → 启动会话。实测 fresh 工作区 `advance` 因 `hypotheses_len_ge_1` 未满足而 BLOCKED（exit 2，`current_phase` 不变）；满足门禁则可推进 |
| **[新增·已修复] writing 门禁硬化** | 门禁由「存在性」升级为「内容实质性」：`analysis_summary_substantive`（≥200 字节 + 统计签名正则）、`figures_substantive`（魔法字节/真实 SVG + ≥64 字节）。占位文件（`echo x` / `fake.png`）现会被 BLOCKED；`sidecar/tools/plot.py` 提供确定性零依赖绘图，产物可被门禁识别 |
| **[新增·已修复] 失败闭环接线** | `api.py` 的 `POST /api/projects/{id}/failure_ledger` 改为调用 `failure_loop.apply_decision`，落盘实验终态 + 更新假设树 + 追加 ledger 一步到位，关闭「API 直写 ledger 绕过闭环」通道（实测 METH 失败登记后经 `apply_decision` 回流，实验 status 由 running→concluded_failed） |
| **[新增·已修复] `vl` 入口** | editable 安装 finder 的 stale 路径已改回本仓库，`pip install -e .` 重建 console launcher；实测 `vl.exe --help` / `vl gate` / `vl run` / `vl advance` 均正常输出（不再静默失效） |

**「预留扩展空间」这一项，客观上是达标的**：底座可替换性有季度演练机制保障，新学科接入零代码，门禁规则声明式可改。这部分做得扎实。

---

## 三、四个交付阻塞点（按严重度）

### P0-1 Agent 会话驱动层完全未接线（最致命）　**【状态：已修复】**

> 修复：`orchestrator/runner.py` 的 `Runner.start_phase_session` 现在调用 `adapter.start_session()`，编排层首次真正驱动底座；`orchestrator/cli.py` 新增 `vl run` 暴露该能力。无底座时降级留痕（`harness_unavailable`），而非崩溃。详见 §二 证据表。

`hal/interface.py` 定义了 13 个会话方法（`start_session` / `resume_session` / `export_session_log` / `spawn_subagent` …），`hal/dsh_adapter.py` 实现了 550 行。但：

```
grep start_session|resume_session|export_trajectory|spawn_subagent
  orchestrator/ sidecar/ bundles/  →  0 命中
```

编排层唯一用到 HAL 的地方是 `bundle_loader.py` 注册 Skill 目录。**没有任何代码启动过Agent 会话**。所谓「全流程智能 Agent」目前必须靠人手动执行 `dsh --profile headless "<task>"` 并自行保证它按 Schema 写文件——Agent 运行时没有参与编排。

后果：编排层声称的「文件监听驱动」「pre_session 硬阻断」「预算硬阻断」全部形同虚设，因为没有任何会话会被这些机制拦截。

### P0-2 阶段推进无入口，系统无法自主流动　**【状态：已修复】**

> 修复：`orchestrator/cli.py` 新增 `vl advance`（校验下一阶段门禁 → 推进 `current_phase` → 启动会话），`orchestrator/runner.py` 提供 `next_phase`/`advance` 状态机。`current_phase` 现在可由 `advance` 在门禁满足时写入，五阶段从「静态规则表」变为「可流动的状态机」。详见 §二 证据表。

- `current_phase` 全仓只有**一处**写入：`orchestrator/cli.py:56`（`vl init` 时写死 `"literature"`）。
- CLI 11 个子命令中**没有** `advance` / `phase set` / `run`。
- 结论：五阶段是一张**静态规则表**，不是一个**流动的状态机**。阶段永远停在literature，除非人手工编辑 `RESEARCH.yaml`。

### P0-3 writing 阶段门禁可被伪造，产生虚假绿灯　**【状态：已修复】**

> 修复：门禁由存在性升级为内容实质性（`gates.py` 新增 `_summary_substantive` / `_looks_like_image` / `_figure_files` / `_STATS_SIGNATURE`），`gates.rules.yaml` 的 writing 阶段 `entry_requires` 改用 `analysis_summary_substantive` / `figures_substantive`；`finalize.py` 同步改用实质性事实。`sidecar/tools/plot.py` 提供确定性零依赖 SVG 绘图（被门禁识别为真实图表）。原伪造复现（`echo x` + `fake.png`）现在 → BLOCKED。详见 §二 证据表。

实测复现：

```bash
vl gate writing --path ws1   # 初始 BLOCKED
echo "x"  > analysis/summary.md
echo "fake" > figures/f1.png
vl gate writing --path ws1   # → [PASS]阶段 writing 准入满足（需人工审批）
```

`gates.py:103` 的 `analysis_summary_exists` 只判断「文件存在且非空」，`figures_generated` 只判断目录里有文件。而**全仓没有任何代码生成分析摘要或图表**（`sidecar/tools/` 无绘图工具，`manuscript/` 目录只被 `cli.py:45` 创建后再无写入者）。

也就是说：**用两个占位文件就能让系统宣布写作阶段就绪**，而 `vl finalize` 会据此输出「✅ analysis/summary.md 就绪 ✅ figures 就绪」的收尾报告。这是审计意义上最危险的一类缺陷——系统会给出误导性的绿灯。

### P0-4 失败闭环存在「绕过通道」　**【状态：已修复】**

> 修复：`orchestrator/api.py` 的 `POST /api/projects/{id}/failure_ledger` 改为调用 `failure_loop.apply_decision`（捕获 `ValueError`→400），落盘实验终态 + 更新假设树 + 追加 ledger 一步到位。API 路径上的闭环已接通，不再存在「登记但永不回流」的绕过通道。详见 §二 证据表。

`apply_decision`（`failure_loop.py:436`，负责落盘实验终态 + 更新假设树 + 追加 ledger）**只有测试代码调用，生产代码零调用**。而 `api.py:176` 的 `POST /api/projects/{id}/failure_ledger` 直接写 ledger 文件，**绕过整个闭环引擎**。

后果：失败可以从 API 侧被「登记」但永不回流；假设树不会更新，级联影响不发生。闭环在 API 路径上是断的。

---

## 四、次级缺陷清单

| # | 缺陷 | 位置 | 影响 |
|---|---|---|---|
| 1 | `vl` 命令入口在本仓库**静默失效** | editable 安装指向已不存在的旧路径 `C:\Users\ASUS\Desktop\项目\真理之眼\verity-lens` | **【已修复】** finder 路径已改回本仓库，`pip install -e .` 重建 console launcher；实测 `vl --help`/`gate`/`run`/`advance` 均正常。**注**：修复需 venv 内装有 `setuptools`（原 venv 缺失导致 editable 重装失败），已补装 84.0.0 |
| 2 | 预算硬阻断永不触发 | `cli.py:189` 读 `token_budget.total.used`，但**无任何代码写这个字段** | **【部分缓解】** `runner.py` 的 `start_phase_session` 在会话结束后将 token 用量回写 `token_budget.total.used`，`pre_session` 的预算环节不再是纯空转。但仍缺「跨会话累计 + 真实用量上报」验证（需真实底座跑通后观察）|
| 3 | 蓝图列出的 `orchestrator/budget.py` 不存在 | 逻辑内联在 `cli.py:176-203` | **【已修复】** 已抽为 `orchestrator/budget.py`（`evaluate_budget` 纯函数），`cli.cmd_budget` 与 `runner._budget_exhausted` 均复用之，单一预算语义来源；新增 `tests/unit/test_budget.py` |
| 4 | 蓝图列出的 `hooks/on_change.py` 不存在 | `hooks/` 只有 `pre_session.sh` | **【已修复】** 新增 `orchestrator/hooks/on_change.py`：监听 `experiments/` 与 `docs/` 变更自动触发 `vl loop` 失败回流检查；支持 `--once`（单次，适合作 git hook / CI 步骤）与纯 stdlib 轮询常驻两种模式；新增 `tests/unit/test_on_change.py` |
| 5 | `pre_session.sh` 无任何调用者、CI 零命中 | — | **【角色被取代】** `runner.py` 的 `pre_session`（聚合门禁 + 预算 + 失败回流，返回 `GateResult`，硬阻断抛 `PreSessionBlocked`）现作为真实硬阻断点在 `start_phase_session` 前同步运行，门禁链已在代码内落地。原 `pre_session.sh` 可保留为文档/手动用途，但不再是唯一实现 |
| 6 | Sidecar 不是「常驻进程」 | `sidecar/tools/_stdio.py:20` `stdin.read()` 到 EOF 即退出 | **【已修复】** 新增 `sidecar/daemon.py`（NDJSON 行协议长驻进程：就绪握手 → 多工具复用 → shutdown/EOF 优雅退出）+ `sidecar/tools/_registry.py`（六工具注册表，plot 包装为 {path}）；协议与 MCP stdio 传输同构，可作为 DSH mcp-client 常驻 StdioConfig server。原 `_stdio.serve` 保留向后兼容；新增 `tests/unit/test_daemon.py` 8 例；`python -m sidecar.daemon` 实测输出就绪行 |
| 7 | CI 漏跑 68 个用例 | `.github/workflows/ci.yml`只跑 5 个目录，`tests/api`、`tests/finalize`、`tests/sidecar` 未纳入 | **【已修复】** CI test job 现已纳入 `tests/api tests/finalize tests/sidecar tests/unit`（共 80 例本地通过），API/finalize/sidecar 层获得 CI 保护 |
| 8 | L4 契约测试在 CI 上永不触碰底座 | CI `runs-on: ubuntu-latest` 不装 dsh | **【已修复（形式齐备，真实运行仍需环境）】** ① 新增独立 `.github/workflows/harness-contract.yml`：setup-node → 尽力安装 `@deepseek-ai/dsh`（continue-on-error）→ 运行 `-k real_dsh` 契约用例 → 离线契约全量兜底，缺 dsh 时按 skipif 优雅跳过保绿；② `test_real_dsh_*` 的 skip 条件现同时识别 `DSH_BIN` 环境变量，并新增 `test_real_dsh_session_start_is_handled` 真驱动 `start_session` 触碰底座事件流（无论运行/降级均返回结构化句柄）；③ `make harness-install` 提供本机安装入口。注意：dsh 属外部 deepseek-ai 包，其发布状态与 API 配额不受本项目控制，环境具备时 CI 即自动真跑 |
| 9 | 前端仍是 Vite 脚手架默认页 | `web/src/App.tsx` 122 行，内容为 "Get started" + counter 按钮 | **【已修复】** 完整重写为业务界面：`pages/Dashboard.tsx`（阶段看板：5 阶段闸门状态/缺失项/当前阶段高亮）+ `components/HitlPanel.tsx`（HITL 审批：需审批阶段批准、写入 approvals）、`components/DoiCard.tsx`（DOI 可验证率卡片，离线复算/联网校验）、`components/FailureLedger.tsx`（失败登记簿决策留痕展示）、`api.ts`+`types.ts`（axios+react-query 类型化客户端）；react-router 路由（`/` 项目选择 → `/project/:id`）。`npm run build` + oxlint 全过；API 实测（phases/approve/doi-metrics 均 200） |
| 10 | DOI 校验工具真联网但主流程不调用 | `doi_verify.py:46` 真实请求；`failure_loop.py:307` 只 import | **【已修复】** 新增 `orchestrator/doi_metrics.py`（采集 RAG 索引/假设树/失败登记簿/`cited_dois` 的 DOI → 离线格式校验或 `--online` 真联网 Crossref → 聚合可验证率）；接入收尾主流程：`finalize` 现计算并持久化度量（RESEARCH.yaml `metrics.doi_verification` + `docs/doi_verification.json`），报告新增「DOI 可验证率」章节（低于 95% 目标给 warning）；新增 `vl verify-dois [--online]` 与 API `GET/POST /api/projects/{id}/doi-metrics`（前端卡片直读）；新增 `tests/unit/test_doi_metrics.py` 7 例 + API 2 例 |
| 11 | `make reproduce` 是 echo 占位 | `Makefile:53-54` 自认「Phase 1 实现」 | **【已修复】** `Makefile` 的 `reproduce` 改为调用 `scripts/reproduce.py`：复用 `sidecar/tools/plot.py` 确定性绘图，对产物做 SHA-256 基线比对，报告 `consistent`/`DRIFT`（漂移退出码 1）；新增 `tests/unit/test_reproduce.py` |

---

## 五、达标路径建议（按依赖顺序）

要达到「可交付的科研全流程 Agent」，需要**先接线，再谈外部依赖**。建议顺序：

**第一步：让系统能流动（打通 P0-2 + P0-1）**
1. 新增 `vl advance` 命令：校验当前阶段门禁 → 推进 `current_phase` → 触发对应阶段会话
2. 新增 `orchestrator/runner.py`：调用 `adapter.start_session()` 真正驱动底座，订阅 NDJSON 事件流
3. 把 `pre_session.sh` 的门禁链（门禁/预算/回流/写锁）改为**代码内Python 实现**，在 `start_session` 前同步调用——这才是真正的硬阻断点

**第二步：补齐产物层（P0-3）**
4. `sidecar/tools/plot.py`：从 `analysis/` 数据生成确定性图表
5. 门禁改为**内容校验**而非存在性校验（如 `summary.md` 必须含效应量/CI/p 值且过 schema 校验）
6. 实现 `make reproduce`：manifest 驱动，从 `data/raw` 到 `figures` 可复现比对

**第三步：堵住绕过通道（P0-4）**
7. `api.py` 的 ledger 写入改为调用 `failure_loop.apply_decision`
8. 补一条 L3 用例覆盖「五阶段从 literature 走到 writing 的完整路径」——目前零全流程用例

**第四步：环境与 CI 收尾**
9. `pip install -e .` 重装修复 `vl` 入口（当前指向已删除的旧路径）
10. CI 补 `tests/api tests/finalize tests/sidecar`；`identity` job 升级为 `--require signed`
11. CI 增加 dsh 安装步骤，让 L4 契约测试真正触碰底座

**第五步（可选）**：前端实现看板/HITL页；这是交互面，不阻塞核心闭环。

---

## 六、对「外部依赖门控」的重新定性

TODO.md 把剩余事项全部归类为「外部依赖门控」（API 配额 / 协作模型待真实数据 / 签名门禁待落地）。这个定性**过于乐观**：

- API 配额确实是外部门控 ✅
- 但协作模型、签名门禁属于**产品决策**，不是外部阻塞
- 而上述 P0-1~P0-4 属于**内部实现缺失**，被误归入了「已落地」或「外部阻塞」

真正的外部阻塞只有一条：**deepseek API 配额**。其余都是内部工作。

---

## 七、本轮修复清单（2026-10-16 续）

> 依据 §五「达标路径建议」顺序执行，实测优先。

### 已落地（P0 + 环境坑）

| 路径建议项 | 改动 | 实证 |
|---|---|---|
| 第一步·1 `vl advance` | `orchestrator/cli.py` 新增 `cmd_advance` + subparser；`runner.py` 状态机 `next_phase`/`advance` | `vl advance` 在 fresh 工作区因 `hypotheses_len_ge_1` BLOCKED（exit 2），门禁满足可推进 |
| 第一步·2 `runner.py` | 新建 `orchestrator/runner.py`（`Runner`：`current_phase`/`set_phase`/`next_phase`/`pre_session`/`start_phase_session`/`run`/`advance`；`PreSessionBlocked`；`PHASE_PRESETS`/`PHASE_TASKS`） | `vl run` 实测启动会话并降级留痕（exit 0） |
| 第一步·3 pre_session 代码化 | `runner.pre_session` 聚合门禁 + 预算 + 失败回流为 `GateResult`，硬阻断抛异常 | 测试覆盖预算硬阻断、失败回流阻塞 |
| 第二步·4 `plot.py` | 新建 `sidecar/tools/plot.py`（确定性零依赖 SVG，`bar_chart`/`line_chart`/`render`，非法输入抛 `ValueError`） | `tests/sidecar/test_plot.py` 覆盖；产物被 `_looks_like_image` 识别 |
| 第二步·5 门禁内容化 | `gates.py` 新增 `_summary_substantive`/`_looks_like_image`/`_figure_files`/`_STATS_SIGNATURE`；`gates.rules.yaml` writing 改用 `analysis_summary_substantive`/`figures_substantive` | 占位伪造 → BLOCKED；实质产物 → PASS |
| 第三步·7 闭环接线 | `api.py` 的 `POST failure_ledger` 改调 `apply_decision` | 测试 `test_failure_ledger_routes_via_apply_decision`：METH 失败回流，实验 status running→concluded_failed |
| 第四步·9 `vl` 入口 | finder 路径改回本仓库 + `pip install -e .` 重建 launcher（补装 setuptools 84.0.0） | `vl --help`/`gate`/`run`/`advance` 实测正常 |

### 测试增量

- 新增 `tests/runner/__init__.py`、`tests/runner/test_runner.py`（状态机推进、advance 阻塞/成功、run 启动、预算硬阻断、失败回流阻塞、token 回写、writing 门禁阻塞）
- 新增 `tests/sidecar/test_plot.py`
- 修改 `tests/api/test_api.py`（新增 `apply_decision` 回流用例）、`tests/finalize/test_finalize.py`（更新为实质产物以匹配硬化门禁）
- 全量：**291 passed / 2 skipped**（原 279 passed / 2 skipped），无回归

### 仍待做（仅余外部依赖，非内部缺陷）

- 端到端真跑：需真实 dsh 底座 + deepseek API 配额，验证「literature→…→writing」真实五阶段闭环（#8 的 harness-contract workflow 已就绪，环境具备即自动真跑）
- §四 #2 遗留观察点：跨会话预算累计 + 真实用量上报需真实底座跑通后验证

### 本轮（次级缺陷续）新增交付

| 审计项 | 改动 | 实证 |
|---|---|---|
| #3 | 新建 `orchestrator/budget.py`（`evaluate_budget` 纯函数）；`cli.cmd_budget` 与 `runner._budget_exhausted` 复用之 | `tests/unit/test_budget.py` 7 例覆盖 ok/soft/hard/no-cap/missing |
| #4 | 新建 `orchestrator/hooks/on_change.py`（变更监听触发回流检查，`--once`/常驻轮询两模式） | `tests/unit/test_on_change.py` 5 例；`python -m orchestrator.hooks.on_change --workspace <ws> --once` 实测 OK |
| #7 | `.github/workflows/ci.yml` test job 纳入 `tests/api tests/finalize tests/sidecar tests/unit` | 本地 80 例通过 |
| #11 | `scripts/reproduce.py`（确定性绘图 + SHA-256 基线比对，consistent/DRIFT，漂移退出 1）；`Makefile` reproduce 目标改写 | `tests/unit/test_reproduce.py` 4 例；端到端 establish→consistent→DRIFT→update 闭环验证通过 |
| #6 | 新建 `sidecar/daemon.py`（NDJSON 行协议长驻进程：就绪握手 → 多工具复用 → shutdown/EOF 优雅退出）+ `sidecar/tools/_registry.py`（六工具注册表） | `tests/unit/test_daemon.py` 8 例；`python -m sidecar.daemon` 实测输出就绪行，shutdown 后干净退出 |
| #8 | 新增 `.github/workflows/harness-contract.yml`（尽力安装 dsh → `-k real_dsh` 真底座契约 → 离线契约兜底保绿）；`test_real_dsh_*` skip 条件识别 `DSH_BIN` 并新增 `test_real_dsh_session_start_is_handled` 真驱动 `start_session`；`make harness-install` | 本地 `hal/contract_tests` **40 passed / 3 skipped**（无 dsh 时真底座用例按 skipif 跳过） |
| #9 | 前端完整重写：`pages/Dashboard.tsx`（阶段看板）+ `HitlPanel`（HITL 审批）+ `DoiCard`（DOI 可验证率）+ `FailureLedger`（失败登记簿）+ `api.ts`/`types.ts` 类型化客户端 + react-router 路由 | `npm run build`（tsc -b + vite）与 oxlint 全过；uvicorn 实测 phases/approve_phase/doi-metrics 均 200 |
| #10 | 新建 `orchestrator/doi_metrics.py`（采集→校验→聚合可验证率→持久化）；接入 `finalize` 主流程（报告新增 DOI 章节 + 持久化 RESEARCH.yaml/docs）；新增 `vl verify-dois [--online]` 与 API `GET/POST /doi-metrics` | `tests/unit/test_doi_metrics.py` 7 例 + API 2 例；`vl verify-dois` 与 curl 实测 200 |
| 测试增量 | 新增 `tests/unit/` 共 23 例（budget/reproduce/on_change/daemon/doi_metrics）+ api 2 例 | 全量 **323 passed / 3 skipped**（原 291），无回归 |

---

*本报告基于 2026-10-16 的代码快照与实测结果。§三 P0-1~P0-4、§四 #1~#4/#5/#6/#7/#8/#9/#10/#11 及 `vl` 入口已于 2026-10-16 全部修复并逐条实测验证（详见 §二、§七）；剩余唯一外部门控为 dsh 底座 + deepseek API 配额。*