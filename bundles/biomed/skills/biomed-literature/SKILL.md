# SKILL: biomed-literature（生物医学文献综述）

## 触发条件
当执行以下任务时自动激活（继承通用 `skills/literature`）：
- 检索 PubMed / OpenAlex 等生物医学数据库
- 撰写疾病机制 / 诊断标志物 / 药物靶点相关综述
- 为 AD 等具体疾病的假设提供证据支撑

## 方法论约束（必须遵守）
1. 检索须记录数据库、检索式、检索日期（可复现性）
2. 每条结论必须溯源到 DOI/PMID，且经 `doi_verify` 校验
3. 明确区分"作者结论"与"推断"，推断须显式标注
4. 涉及诊断效能时须报告敏感度/特异度/AUC 及 CI
5. 优先纳入系统综述 / Meta 分析 / 前瞻性队列（证据等级标注）
6. 动物实验结论外推到人须明确标注局限

## 输出 Schema
```json
{
  "notes": [
    {
      "id": "L001",
      "doi": "10.xxxx/yyyy",
      "verified": true,
      "evidence_level": "meta-analysis",
      "claim": "作者结论",
      "evidence": "关键数据",
      "method": "设计与样本量",
      "limitations": "局限",
      "relevance": "与本项目关系",
      "inference": null
    }
  ]
}
```

## 参考文件
- ./references/biomed_terminology.json（领域术语与本体）
- PRISMA（系统综述报告规范）

## 注意事项
- 知识走参考文件与检索，不硬编码进提示词
- 引用有效性 ≥95%；预印本/撤稿须标注（≤5% 例外）
