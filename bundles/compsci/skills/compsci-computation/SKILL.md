# SKILL: compsci-computation（L1 · 可复现计算实验）

> 计算机科学 / 计算实验的强制方法论约束。所有数值结论须由 sidecar 确定性工具复算，模型不得自行产出。

## 触发条件
当执行以下任务时自动激活：
- 设计或报告计算实验（模型训练、基准评测、算法复现、消融实验）
- 校验实验结论是否满足可复现性门槛（种子 / 重复 / 环境 / 哈希）
- 撰写对比基线的统计显著性结论

## 方法论约束（必须遵守）
1. **随机种子必须固定且记录**：`reproducibility.random_seed` 为非负整数，且实验中实际生效（不得隐式随机）。
2. **≥3 次独立重复**：每个实验须 `n_runs >= 3`，报告 **均值 ± 标准差**，禁止仅报单次最优或单跑结果。
3. **运行环境必须记录**：`reproducibility.environment` 非空，含框架版本、关键依赖、硬件（GPU/CPU）与确定性设置（如 cudnn deterministic）。
4. **数据与代码可溯源**：`reproducibility.data_hash` 或 `code_hash`（或 commit sha）至少其一非空。
5. **结论须带不确定度**：任何主指标必须同时给出 `std`（或置信区间），禁止只报点估计（如仅 "accuracy=0.92"）。
6. **基线对比须有统计差异**：与基线的差异须报告 `baseline_delta` 与显著性 `baseline_p`（或效应量 + 区间），禁止仅声称 "SOTA"。
7. 引用须经 `doi_verify` 校验后方可写入；预印本 / 撤稿须标注。

## 输出 Schema（分析报告）
```json
{
  "metric": "accuracy",
  "value": 0.921,
  "std": 0.004,
  "n_runs": 5,
  "random_seed": 42,
  "environment": "pytorch 2.2 / cuda 12.1 / A100 / cudnn_deterministic=true",
  "data_hash": "sha256:9f2c...",
  "code_hash": "git:ab12cd34",
  "baseline": { "name": "ResNet-50", "value": 0.904, "baseline_delta": 0.017, "baseline_p": 0.003 },
  "source_tool": "sidecar.tools.stat_test"
}
```

## 参考文件
- ./references/compsci_terminology.json

## 注意事项
- 知识走参考文件与检索，不硬编码进提示词。
- 不确定度与显著性须由 `sidecar.tools.stat_test` 确定性复算（功效 / 效应量 / p 值）。
- 复现失败的声明（"未能复现原论文结果"）同样是有价值结论，须如实登记，不得掩盖。
