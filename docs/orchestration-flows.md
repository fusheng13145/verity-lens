# 任务编排与流程

**目的**：描述跨阶段的任务编排、门禁与失败回流，落实 Agent 应用开发的"任务编排"思想。编排层为无状态事件处理器，规则声明式。

## 1. 状态机（单一定义）

```
literature → question → experiment → analysis → writing
                ↑           │ failed        │
                │           ▼               │
                └───── [ failure_loop ] ◄───┘
        （归因 → 假设修订/参数调整 → 回 experiment；显式放弃 → 回 question）
```

## 2. 阶段门禁（声明式）

规则表 `gates.rules.yaml`：`entry_requires` 含文件检查 + 条件表达式 + `hitl_required`。由 `vl gate <phase>` 在每次会话启动前（pre_session hook）执行。不通过输出缺失清单，退出码 2 拒绝启动。

关键门禁：experiment 准入需 `approvals.question` 已批；analysis 准入需所有实验处于终态（failed 非终态，须先回流）；writing 准入需 `analysis/summary.md` + 全部 figures，且 `hitl_required`。

## 3. 端到端流程（正常路径）

```
vl init → literature会话 → vl gate question(HITL) → question会话
→ vl gate experiment → experiment会话(sidecar提交) → 完成则 analysis
→ vl gate analysis → analysis会话(sidecar复算) → summary.md
→ vl gate writing(HITL) → writing会话 → vl finalize(manifest+reproduce)
```

## 4. 失败回流流程（核心闭环）

```
exp 失败 → vl loop 校验是否登记 failure_ledger
  → 否：阻塞，要求归因草案
  → 是：分类(Agent起草→sidecar复核)
  → EXEC: 自动重试≤3 → 超限 HITL
  → DATA: 数据补充任务，suspended
  → METH: 生成 exp_N+1 修订(HITL) → 重跑
  → HYP:  假设 refuted/revised → 新假设生成(HITL) → 挂树
  → EPIS: 修订文献与假设前提(级联) → 回 question
最终：failure_ledger 留痕 + lessons.md 渲染 + 假设树 version+1
```

## 5. 会话启动前门禁（pre_session.sh 顺序）

```
① vl gate <phase>        不通过→拒绝
② vl budget check        HARD_BLOCK→暂停+恢复选项
③ vl loop check          未处理 failed/未批准回流→拒绝
④ vl lock check          写锁冲突→只读模式
⑤ HAL capabilities 探测   特性缺失→降级+记录
```

## 6. 底座升级回归流程

```
底座新版本 → 改 hal/version_lock.yml → CI: hal_contract(100%) → CI: L1+L2 Golden(edit≤2)
  通过→更新锁；失败→HAL 修复重跑
```

**要点**：编排不持有状态、不建库；阶段推进唯一写入口是 `vl gate` 校验后编辑 RESEARCH.yaml，天然幂等可恢复。
