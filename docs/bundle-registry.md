# Bundle 注册表（Bundle Registry）

**目的**：登记全部学科 Bundle 的级别、版本、校验状态与分发方式，作为领域包生态的单一台账。新增 Bundle 必须在此登记（防文档漂移）。

## 1. Bundle 台账

| Bundle | 级别 | 版本 | 状态 | Golden 用例 | 负责人 | 备注 |
|--------|------|------|------|-------------|--------|------|
| biomed | **L1** | 0.2.0 | ✅ 已交付（Phase 1–2，2026-10-15；level 字段 Phase 4b 正式升 L1） | 待建 | 待定 | 首个学科；stats + literature 两个 SKILL，含 L1 验证脚本，无 Preset Patch / MCP |
| materials | **L1** | 0.1.0 | ✅ 已交付（Phase 4a，2026-10-15） | 待建 | 待定 | 第二学科；characterization（L1 验证脚本：不确定度 / n≥3 / 单位 / 仪器）+ literature；由 `vl bundle new` 生成 L0 后升 L1，验证"换 Bundle 即切换学科" |
| compsci | **L1** | 0.1.0 | ✅ 已交付（Phase 4b，2026-10-15） | 待建 | 待定 | 第三学科；computation（L1 验证脚本：固定种子 / n≥3 / 环境 / 数据·代码哈希 / 基线统计差异）+ literature；由 `vl bundle new` 生成 L0 后升 L1 |

**biomed**：`bundle.yml` + `skills/biomed-stats/SKILL.md`（效应量 + 95% CI + p 值强制规范）+ `skills/biomed-literature/SKILL.md`（证据等级 + 诊断效能指标）+ `skills/biomed-stats/scripts/validate_report.py` + `references/biomed_terminology.json`。

**materials（L0→L1）**：`bundle.yml` + `skills/materials-characterization/SKILL.md`（表征不确定度规范：不确定度必报 / n≥3 / 单位 / 仪器 / XRD·BET·Tauc 约束）+ `skills/materials-literature/SKILL.md`（实验 vs 计算证据 / 测试条件对齐）+ `skills/materials-characterization/scripts/validate_report.py` + `references/materials_terminology.json`。

**compsci（L0→L1）**：`bundle.yml` + `skills/compsci-computation/SKILL.md`（可复现计算实验：固定种子 / n≥3 重复 / 环境记录 / 数据·代码哈希 / 均值±标准差 / 基线统计差异）+ `skills/compsci-literature/SKILL.md`（证据等级 L1–L3 / SOTA 溯源）+ `skills/compsci-computation/scripts/validate_experiment.py` + `references/compsci_terminology.json`。

级别定义见 `design-blueprint.md` §Bundle 工厂（L0 骨架 / L1 可用 / L2 完备）。

## 2. 注册流程

1. `vl bundle new <discipline>` 生成 L0 骨架（基于 `bundles/_template/`）。
2. 专家完成 SKILL.md 访谈内容填充，Markdown diff 评审。
3. 工程师补验证脚本（L0→L1）、Golden 用例（L1→L2）。
4. 提交 PR：`bundles/<discipline>/` + 本台账更新一行（级别/版本/状态/Golden 数/负责人）。
5. CI 校验：结构一致性（目录/命名/schema 引用）+ L1 Schema 校验通过。

## 3. 校验要求

- 结构：bundle.yml 仅声明 Skill 路径 / Preset Patch（可选）/ MCP 配置（可选），禁止直接调用底座内核。
- 命名：`<discipline>-<capability>`；SKILL.md 必含触发条件/方法论约束/输出 Schema/参考文件四节。
- 验证：产出必须通过对应 JSON Schema；关键数值经 Sidecar 确定性工具复核。

## 4. 分发与版本

- 分发方式：随仓库分发（`bundles/` 目录），经编排层加载（复制到 HAL 注册接口），不做独立包管理器。
- 版本规则：`MAJOR.MINOR.PATCH`；方法论约束变更 = MINOR；验证脚本缺陷修复 = PATCH。
- 升级要求：版本变更须同步 Golden 用例并通过 L2 轨迹回归（edit distance ≤2）。
