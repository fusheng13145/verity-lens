# SKILL: materials-stats（L0 模板）

> 由 `vl bundle new` 生成。请领域专家填写带 TODO 的部分。

## 触发条件
当执行以下任务时自动激活：
- TODO: 列出 2-4 个触发场景

## 方法论约束（必须遵守）
1. TODO: 该学科必须报告的指标（如效应量 + 95% CI + p 值）
2. 所有数值结论须由 sidecar 确定性工具计算，模型不得自行产出
3. 引用须经 `doi_verify` 校验后方可写入
4. TODO: 学科特有的禁令（如禁止仅报 p 值）

## 输出 Schema
```json
{
  "metric": "TODO",
  "value": 0.0,
  "ci_95": [0.0, 0.0],
  "p_value": 0.0,
  "source_tool": "sidecar.tools.stat_test"
}
```

## 参考文件
- TODO: ./references/<规范>.json

## 注意事项
- 知识走参考文件与检索，不硬编码进提示词
- 引用有效性 ≥95%；预印本/撤稿须标注
