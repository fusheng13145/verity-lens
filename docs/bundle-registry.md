# Bundle 注册表（Bundle Registry）

**目的**：登记全部学科 Bundle 的级别、版本、校验状态与分发方式，作为领域包生态的单一台账。新增 Bundle 必须在此登记（防文档漂移）。

## 1. Bundle 台账

| Bundle | 级别 | 版本 | 状态 | Golden 用例 | 负责人 | 备注 |
|--------|------|------|------|-------------|--------|------|
| biomed | L0（目标 L1） | 0.1.0 | 规划中（Phase 1） | 待建 | 待定 | 首个学科，端到端闭环载体 |
| materials | — | — | 未启动 | — | — | Phase 2 候选 |
| compsci | — | — | 未启动 | — | — | Phase 2 候选 |

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
