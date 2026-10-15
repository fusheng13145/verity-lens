# Agent 角色与提示词设计

**目的**：定义系统中每个 Agent / 子代理的**角色**（职责+权限）、**任务编排入口**与**提示词工程规范**。落实 Agent 应用开发的"角色定义"与"提示词即配置"。

---

## 1. 角色模型总览

| 角色 | 职责 | 权限级别 | 提示词载体 |
|------|------|----------|-----------|
| 主研究 Agent（per Workspace） | 执行当前阶段任务 | Workspace Write（按阶段限目录） | Preset 系统提示 + 阶段 SKILL |
| 检索子代理 | 文献/代码检索 | Read Only（禁写） | SKILL + 检索规范 |
| 分析子代理 | 统计/数据处理 | Workspace Write（仅 `data/processed/`） | SKILL + 输出 Schema |
| 写作子代理 | 论文撰写 | Workspace Write（仅 `manuscript/`） | IMRAD 规范 SKILL |
| 评审子代理 | 质量/合规审查 | Read Only + 可写 `review/` 批注 | 审查清单 SKILL |
| 归因 Agent（失败闭环） | 起草失败归因 | Read Only + 写 failure_ledger 草案 | 分类学提示词 |

**角色 = 权限 + 职责 + 提示词** 三位一体；权限由 HAL `set_permission` + 子代理策略强制，不靠提示词软约束。

## 2. 系统提示词结构（主 Agent）

```
[身份] 你是 verity-lens 科研助手，服务于 <discipline> 领域的 <research_question>。
[约束] 仅基于脱敏数据推理；禁止无来源断言；结论须可追溯至文件+行号。
[阶段] 当前阶段=<current_phase>；阶段目标与产出见对应 SKILL。
[工具] 可用工具白名单经 HAL 注入；长任务走 sidecar 提交。
[输出] 结构化输出须符合 data-schema.md 的 JSON Schema。
[合规] 统计报告必报效应量+95%CI+p 值；禁仅报"显著"。
```

## 3. SKILL.md 模板（领域方法论约束）

```markdown
# SKILL: <学科>-<能力>
## 触发条件
- 当执行 <任务> 时自动激活
## 方法论约束（必须遵守）
1. 所有效应量须报告数值及 95% CI
2. p 值报告精确值，禁仅报 p<0.05
3. 样本量<30 须说明正态性检验
## 输出 Schema
{ "comparison": "...", "effect_size": 1.23, "ci_95": [0.45,2.01], "p_value": 0.003 }
## 参考文件
- ./references/<规范>.json
## 注意事项
- 禁仅报 p 值不报效应量
```

## 4. 子代理调用策略（`config/subagent_policy.yaml`）

```yaml
创建条件: [明确输入输出 schema, 需不同权限, 需隔离上下文, 预计耗时<主会话超时]
权限隔离:
  检索类: "Read Only"
  分析类: "Workspace Write (data/processed/)"
  写作类: "Workspace Write (manuscript/)"
  评审类: "Read Only + review/ 写批注"
上下文裁剪:
  禁止: "传入完整 Session History"
  允许: "主会话当前 turn ±3 轮"
  最大上下文: "2000 tokens"
结果校验:
  强制: "JSON Schema 验证返回结构"
  关键: "经确定性工具二次验证（如统计值 sidecar 复算）"
失败重试:
  最大重试: 3
  3次失败: "上报编排层触发 HITL，记入 lessons.md"
```

## 5. HITL 提示词规范

门禁审批（question/writing 阶段）须向研究者呈现：
- 当前阶段产出摘要与关键证据引用；
- 拟推进到的下一阶段及准入条件；
- 风险提示（预算使用率、未完成实验）。
研究者确认后写 `RESEARCH.yaml.approvals[phase]`（带 `approved_by` / `approved_at`）。

## 6. 失败归因提示词（Failure Loop）

```
[任务] 基于 exp_NNN 产物与 Session Log，对失败做归因分类。
[分类学] EXEC/DATA/METH/HYP/EPIS（编码见 data-schema / 失败分类学）。
[要求] 必须给出 classification.code + rationale + evidence 指针；
       置信度<0.6 须显式标注"需人工确认"；
       数值结论（如 power）由 power_analysis 工具复算后填入。
[输出] 严格符合 failure_ledger.json 的 entry Schema。
```

**要点**：提示词只描述"做什么/约束/输出结构"，不硬编码领域知识（知识走 SKILL 参考文件与检索）；所有关键数值经确定性工具复核，避免提示词驱动幻觉。
