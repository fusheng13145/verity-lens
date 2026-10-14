# TODO.md — 项目开发计划与当前进度

> 进度总览文档，路线图依据见 `docs/design-blueprint.md` 第七部分。完成一项即勾选并注明日期。

## 当前状态

- **当前阶段**：Phase 0 已完成（HAL 实现 + 契约测试 + 门禁引擎 + 脚手架 + 前端骨架）
- **下一步**：Phase 1 —— 失败驱动迭代模块（failure_loop 真实实现）+ biomed L0 Bundle

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
