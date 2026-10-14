# SKILL: literature（通用文献综述）

## 触发条件
当执行以下任务时自动激活：
- 进行文献检索与筛选
- 撰写或更新 `docs/literature_notes.md`
- 为假设树提供支撑证据引用
- 撰写综述（review）类内容

## 方法论约束（必须遵守）
1. 每条笔记必须可溯源到唯一文献标识（优先 DOI，其次 PMID / arXiv ID / 官方链接）。
2. 引用须经 `doi_verify` 工具校验存在性后再写入笔记；不可凭记忆编造 DOI。
3. 笔记结构统一为：**结论 → 证据（原文要点）→ 方法/样本 → 局限 → 与本项目的关系**。
4. 区分"作者结论"与"你的推断"，后者必须显式标注为推断。
5. 不得仅凭摘要下结论；关键结论需回看方法/结果章节。
6. 记录检索式、数据库、检索日期（可复现性要求）。

## 输出 Schema
```json
{
  "notes": [
    {
      "id": "L001",
      "doi": "10.xxxx/yyyy",
      "verified": true,
      "claim": "作者结论摘要",
      "evidence": "结果章节关键数据",
      "method": "研究设计与样本量",
      "limitations": "局限",
      "relevance": "与本项目的关系",
      "inference": null
    }
  ],
  "query_log": [
    { "db": "OpenAlex", "query": "...", "date": "2026-10-14" }
  ]
}
```

## 参考文件
- `bundles/<discipline>/skills/*/references/`（学科本体与术语表）
- 报告规范：CONSORT（临床试验）/ STROBE（观察性研究）/ PRISMA（系统综述）

## 注意事项
- 领域知识走参考文件与检索，不硬编码进提示词。
- 所有引用在写入前必须 `doi_verify`；有效性目标 ≥95%。
- 若文献为预印本/已撤稿，须显式标注（允许 ≤5% 例外）。
