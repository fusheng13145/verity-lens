# SKILL: compsci-literature（L1 · 计算实验文献）

> 计算机科学文献检索与证据分级。配合 `sidecar/rag` 与 `doi_verify` 使用。

## 触发条件
当执行以下任务时自动激活：
- 检索某方法 / 基准 / 数据集的已有工作与复现情况
- 为实验设计定位基线（baseline）与对照
- 评估某结论的证据强度（是否已独立复现）

## 方法论约束（必须遵守）
1. **区分证据等级**：
   - L1 独立复现：第三方在相同 / 不同环境下成功复现结论。
   - L2 元分析 / 多工作汇总：≥3 篇一致结论。
   - L3 单篇声明：仅原作者在原始实验中声称（含未复现的 SOTA 声明）。
2. **SOTA 声明须溯源**：任何 "state-of-the-art" 结论必须给出基准名称、数据集与可验证来源；未独立复现的 SOTA 须标注 "声明级（L3）"。
3. 引用须经 `doi_verify` 校验后方可写入（预印本 / 撤稿须标注）。
4. 检索命中须走 `sidecar/rag` 的 citation-only 降级路径，禁止编造文献。

## 输出 Schema（文献条目）
```json
{
  "title": "On the Reproducibility of X",
  "doi": "10.xxxx/xxxxx",
  "venue": "NeurIPS 2025",
  "evidence_level": "L1",
  "reproduced": true,
  "note": "第三方在 2 个独立代码库复现"
}
```

## 参考文件
- ./references/compsci_terminology.json

## 注意事项
- 知识走参考文件与检索，不硬编码进提示词。
- 优先引用已复现工作作为基线，降低采纳未验证声明的风险。
