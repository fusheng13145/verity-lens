# SKILL: materials-literature（材料文献综述）

## 触发条件
当执行以下任务时自动激活（继承通用 `skills/literature`）：
- 检索 Web of Science / Scopus / arXiv / Materials Project 等材料数据库
- 撰写合成路线 / 结构—性能关系 / 失效机制相关综述
- 为具体材料体系（如钙钛矿、MOF、二维材料）的假设提供证据支撑

## 方法论约束（必须遵守）
1. 检索须记录数据库、检索式、检索日期（可复现性）
2. 每条结论必须溯源到 DOI，且经 `doi_verify` 校验
3. 明确区分"实验合成"与"计算预测"的证据类型，外推须标注局限
4. 涉及性能对比时须标注测试条件（温度、气氛、基准），否则对比无效
5. 优先纳入同行评审期刊，预印本须显式标注（≤5% 例外）
6. 区分"作者报道值"与"本项目推断"，推断须显式标注

## 输出 Schema
```json
{
  "notes": [
    {
      "id": "L001",
      "doi": "10.xxxx/yyyy",
      "verified": true,
      "evidence_type": "experimental",
      "claim": "作者结论",
      "evidence": "关键数据",
      "method": "合成/表征方法",
      "conditions": "测试条件",
      "limitations": "局限",
      "relevance": "与本项目关系",
      "inference": null
    }
  ]
}
```

## 参考文件
- ./references/materials_terminology.json（领域术语与本体）
- PRISMA（系统综述报告规范）

## 注意事项
- 知识走参考文件与检索，不硬编码进提示词
- 引用有效性 ≥95%；预印本/撤稿须标注（≤5% 例外）
