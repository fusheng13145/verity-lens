# 交互设计规范（Interaction Design）

**目的**：统一交互层（CLI / Web UI / Headless API）的输出格式、门禁交互与错误呈现规范。保证人机协作（HITL）体验一致、信息可信可追溯。视觉层依赖底座自带 Web UI，本文件约束的是 VerityLens 自有交互面（以 CLI 为主）。

## 1. CLI 输出规范

- 每条命令输出三段式：**结果状态行 → 明细列表 → 下一步建议**。
- 阻塞类命令（gate/loop/budget/lock）必须输出**缺失清单**（逐条：缺失文件 / 不满足条件 / 修复建议）。
- 退出码契约见 `interfaces.md` §2（0 成功 / 1 错误 / 2 阻塞 / 3 硬阻断 / 4 锁冲突）。

示例（`vl gate experiment` 阻塞输出）：

```
[BLOCKED] 阶段 experiment 准入未满足（2 项）：
  1. approvals.question.approved_by 为空 → 请 PI 在 RESEARCH.yaml 记录审批
  2. experiments/ 下无有效 exp_*.yaml → 运行 vl init-exp 或手动创建
下一步：完成上述项后重新运行 vl gate experiment
```

## 2. HITL 审批交互

审批呈现必须包含四要素（缺一不可）：
1. 当前阶段产出摘要（含关键证据的文件+行号引用）；
2. 拟推进的下一阶段及准入条件；
3. 风险提示（预算使用率、未终态实验数、降级特性）；
4. 明确的确认动作（编辑 RESEARCH.yaml.approvals + Git commit）。

禁止：仅展示"是否继续？"式无上下文确认。

## 3. 错误与降级呈现

- 底座能力缺失（HAL 探测）→ 显式标注 `[降级] <特性> 不可用，已切换 <降级路径>`，写 `RESEARCH.yaml.degraded_features`。
- 预算硬阻断 → 输出三选项（追加预算 / 切换 flash 模型 / 人工接管）及各选项的代价说明。
- 失败归因置信度 <0.6 → 标注 `[需人工确认]`，不自动路由。

## 4. 进度与可追溯性

- 长任务（HPC/批量）显示 job_id 与轮询状态来源，不展示假进度条。
- 所有输出中的数值结论标注来源工具（如 `power_analysis`），未经复算的数值标注 `[未验证]`。
- Session/轨迹引用格式统一：`<file>#L<n>` 或 `evt_<id>`。

## 5. 非目标

- 不重新设计底座 Web UI 的视觉风格（复用 DSH 原生界面）；
- 不在 Web 前端实现复杂 Agent 会话操作（复杂任务仍走 CLI / DSH 原生 UI）。

## 6. Web 前端交互（React，扩展交互面）

Web 前端（`web/`，React + Vite + TS）是 CLI 之外的补充交互面，仅用于**阶段看板、HITL 审批页、失败登记簿查看**；不替代 CLI，也不重新设计 DSH 原生 UI。

- **唯一入口：Headless API**。前端只经 `orchestrator.api`（FastAPI）与系统交互，不得直连底座或读写 Workspace 文件系统。
- **契约单一真相**：后端 `orchestrator/schemas/*.json` 为接口类型真相，前端 `src/types/` 由其生成（见 `frontend.md`）。
- **复用三段式与四要素**：看板展示门禁通过/阻塞项沿用 §1 缺失清单格式；审批页沿用 §2 四要素。
- **降级信息透传**：底座能力缺失、预算硬阻断、归因低置信度等状态，由 API 以结构化字段返回，前端按 §3 规范统一呈现。
- 详细前端规范见 `frontend.md`。
