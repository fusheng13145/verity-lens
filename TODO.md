# TODO.md — 项目开发计划与当前进度

> 进度总览文档，路线图依据见 `docs/design-blueprint.md` 第七部分。完成一项即勾选并注明日期。

## 当前状态

- **当前阶段**：Phase 2 已完成（Bundle 工厂 + biomed 升 L1 + HYP/EPIS 级联回流）
- **下一步**：Phase 3 —— 容器沙箱 + RAG 侧车完整版 + 制品写锁 + Git 分支协作流

## Phase 2：领域包化 + 失败闭环完备 ✅ 2026-10-15

- [x] 重构 `orchestrator/bundle_factory.py`：
  - [x] `new_bundle(discipline, target, capability)` 生成 L0 骨架（复制模板 + 占位符替换 + Skill 目录重命名）
  - [x] `validate_bundle(dir)` 结构校验（必填字段 / level 枚举 / Skill 存在性）
  - [x] `INTERVIEW_TEMPLATE` 领域专家访谈提纲
- [x] L0 模板 `bundles/_template/`（bundle.yml + skills/capability/SKILL.md）
- [x] biomed 升 **L1**：新增 `skills/biomed-stats/scripts/validate_report.py`（确定性校验：必填字段 / CI 合法性 / p 值范围 / 需 CI 的指标）
- [x] 级联回流：`cascade_impact()` 沿 children 链传播（根证伪 → 派生假设 revised / 实验 abandoned，写 cascade_note）
- [x] 测试：65 个用例全通过

## Phase 1：单学科端到端闭环 ✅ 2026-10-15

- [x] 失败驱动迭代模块：`orchestrator/failure_loop.py`
  - [x] 五类失败分类学（EXEC/DATA/METH/HYP/EPIS）与路由
  - [x] failure_ledger 条目 Schema 校验（含 evidence 指针）
  - [x] 确定性工具复核（功效/效应量/p 值，依赖缺失时降级）
  - [x] 落盘：实验转终态 + 假设树置信度/状态更新 + ledger 追加 + lessons.md 渲染
  - [x] 硬约束：未批准不回流；refuted 不可删；新假设须引用 F-xxx
- [x] biomed L0 Bundle（bundle.yml + stats/literature SKILL + 术语表）
- [x] CLI：`vl loop` 与 `vl budget check` 真实实现
- [x] 测试：53 个用例全通过

## Phase 0：底座 + HAL 立桩（1–2 周）✅ 2026-10-15

- [x] 搭建工程骨架（`hal/` `orchestrator/` `sidecar/` `bundles/_template/` 目录）
- [x] 实现 `hal/interface.py` 抽象接口（含 `CAPABILITY_KEYS`）+ `dsh_adapter.py`
- [x] 实现能力探测 `capability_probe.py` + `version_lock.yml`
- [x] 编写 HAL 契约测试（`hal/contract_tests/`，11 个用例覆盖接口与降级）
- [x] 最小 Skill（literature）+ 最小 sidecar 工具（stat_test / doi_verify）
- [x] 四大 JSON Schema：`research` / `hypothesis_tree` / `experiment` / `failure_ledger`
- [x] 编排层门禁引擎：`orchestrator/gates.py` 纯函数 + `vl init` / `vl gate`
- [x] Headless API：`orchestrator/api.py`（供前端）
- [x] 前端骨架：`web/`（React + Vite + TS + Tailwind + `/api` proxy）
- [x] 验证：36 个测试全通过

**遗留**：`numpy` / `scipy` 因网络慢未安装（仅 `stat_test` 需要，Phase 1 用到时再装）。

## Phase 1：单学科端到端闭环（3–6 周）

- [ ] biomed L0 Bundle（SKILL.md + 通用验证脚本）
- [ ] Orchestrator Lite：`vl init/gate/budget` + pre_session hook
- [ ] failure_ledger schema + 回流引擎 v1（EXEC/METH 两类）
- [ ] Golden 测试集 5–10 用例
- [ ] 验收：检索→写作跑通；METH 类失败走通"归因→修订→再实验"

## Phase 2：领域包化 + 失败闭环完备（7–12 周）

- [ ] Bundle 工厂（`vl bundle new` + `_template/`）
- [ ] L1 Bundle ×2；HYP/EPIS 回流；假设树 refuted/revised
- [ ] Golden 集扩充（含失败闭环用例 METH/HYP 各 3 例）

## Phase 3：健壮性与协作（4–6 月）

- [ ] 容器沙箱（sandbox-compose）
- [ ] RAG 侧车完整版（缓存/防膨胀/citation-only）
- [ ] 制品写锁 + Git 分支协作流

## Phase 4：扩展评估（按需）

- [ ] L2 Bundle；3+ 学科在用后评估扩展与协作模型

## 文档体系（已完成）

- [x] 完整设计方案 `docs/design-blueprint.md`（2026-10-14）
- [x] 12 篇结构化文档 + README 导航（2026-10-14）
- [x] 蓝图重命名 design-blueprint.md（2026-10-14）
- [x] 补齐 project-spec / bundle-registry / interaction-design / AGENTS / CHANGELOG / TODO（2026-10-14）
