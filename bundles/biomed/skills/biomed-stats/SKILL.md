# SKILL: biomed-stats（生物医学统计报告）

## 触发条件
当执行以下任务时自动激活：
- 分析临床试验 / 队列研究数据
- 报告组间比较结果
- 生成生存分析图表
- 撰写论文的 Results 章节
- 复核实验失败归因（功效/效应量相关）

## 方法论约束（必须遵守）
1. 所有效应量必须报告具体数值及 95% 置信区间
2. 连续变量：正态用均值±标准差，非正态用中位数[IQR]
3. 分类变量：报告频数(百分比)
4. P 值报告精确值（如 p=0.023），禁止仅报告 p<0.05
5. 多重比较必须说明校正方法（Bonferroni / Benjamini-Hochberg FDR）
6. 生存分析必须报告 HR 及其 95% CI
7. 样本量 < 30 时必须说明正态性检验结果
8. 所有统计值须由 sidecar `stat_test` / `power_analysis` 计算，模型不得自行给出数值

## 输出 Schema
```json
{
  "comparison": "组A vs 组B",
  "metric": "mean_difference",
  "effect_size": 1.23,
  "ci_95": [0.45, 2.01],
  "p_value": 0.003,
  "test_used": "two-sample t-test",
  "multiple_testing_correction": "Benjamini-Hochberg FDR",
  "source_tool": "sidecar.tools.stat_test"
}
```

## 参考文件
- CONSORT 2010 Statement（临床试验）
- STROBE Statement（观察性研究）
- ./references/biomed_terminology.json

## 注意事项
- 禁止仅报告 p 值而不报告效应量
- 禁止使用"显著"一词替代具体数值
- 数值一致性：与原始数据文件比对须完全一致（容差 1e-6）
