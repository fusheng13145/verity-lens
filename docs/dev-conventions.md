# 开发规范与协作

**目的**：统一团队开发约定，保障模块化与长期可维护性。配合 Git 流与制品写锁实现 1–10 人协作。

## 1. 分支模型

- `main`：稳定，需 PR + review 合并。
- `hypothesis/Hx`：假设分支，各自推进实验/分析，merge 前过 `vl gate`。
- `feature/*`：工程功能；`bundle/<discipline>`：学科包。
- 协作边界：多人并行研究走不同假设分支；共同写作走写锁（先到先得，超时自动失效）。

## 2. Code Review 硬规则

- 除 `hal/` 外，import 底座内部 API → 阻断。
- 新增跨模块交互未补 `interfaces.md` 契约 → 阻断。
- 修改 `gates.rules.yaml` 须说明对阶段流转的影响。
- Skill/MCP/Sidecar 归属不符 `tool-calling.md` 决策矩阵 → 打回。

## 3. 命名与目录

- 模块目录见 `architecture.md` 工程布局；实验 `exp_NNN.yaml`（NNN 递增）。
- Bundle 分级 L0/L1/L2；命名 `<discipline>-<capability>`。
- 确定性工具纯函数化，输出经 `output_schema` 校验。

## 4. 版本锁与底座变更

- `hal/version_lock.yml` 是底座兼容的唯一真相；变更须 PR 并过 `hal-contract`。
- 季度切换演练记录于 `deployment-ops.md`。

## 5. 文档标准

- 文档与代码同步：接口变更必改 `interfaces.md` + 对应 `modules.md`。
- 新增 Bundle/学科在 `README.md` 类型清单登记，防文档漂移。
- 文档与契约冲突以 `interfaces.md` 为准；契约与实现冲突，实现须改或契约升版评审。

## 6. 记忆与上下文纪律

- 长期状态只落声明式文件，不写散落笔记。
- 提示词不硬编码领域知识（走 SKILL 参考文件 + 检索）。
- 关键数值必经确定性工具，提示词不产出最终统计值。

## 7. 提交信息约定

- `feat/hal:` `fix/gate:` `docs/bundle:` `test/golden:` 前缀 + 简述。
- 失败闭环相关提交附 failure_ledger 关联（如有）。

## 8. 协作非目标（明确不做）

- 不做多人实时共享同一会话、不做 OT/CRDT（需求超出现有能力，Phase 4 按需评估）。
- 不做企业级多租户/SSO（见完整方案附录 A）。
