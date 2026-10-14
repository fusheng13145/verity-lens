# CHANGELOG.md — 版本更新记录

> 遵循 Keep a Changelog 风格，版本号 `MAJOR.MINOR.PATCH`。

## [1.3.0] - 2026-10-15 — Phase 0 完成

### Added
- **HAL 适配层实现**：`hal/interface.py`（`HarnessAdapter` Protocol + `CAPABILITY_KEYS`）、
  `hal/dsh_adapter.py`（`SessionHandle` / `ToolSpec` / `PresetPatch` / `SubagentSpec` + 子进程封装与优雅降级）、
  `hal/capability_probe.py`（读 version_lock 探测能力）。
- **数据 Schema**：`orchestrator/schemas/` 下四大 JSON Schema（research / hypothesis_tree / experiment / failure_ledger），
  含假设树无环注解与终态枚举。
- **编排层门禁引擎**：`orchestrator/gates.py` 纯函数（`load_project` / `compute_facts` / `check_file` / `check_gate` / `validate_acyclic`），
  声明式命名事实 + 三段式缺失清单输出；CLI 实现 `vl init` / `vl gate`（含退出码 0/1/2）。
- **Headless API**：`orchestrator/api.py`（FastAPI），供 Web 前端读取项目/阶段/假设树/实验/失败登记簿，
  并支持 HITL 审批与失败登记（强制 `decision.approved_by`）。
- **通用 Skill**：`skills/literature/SKILL.md`（含方法论约束与输出 Schema）。
- **确定性工具**：`sidecar/tools/stat_test.py`（t 检验 / Welch / Mann-Whitney + Cohen's d + 95% CI）、
  `sidecar/tools/doi_verify.py`（DOI 归一化 + Crossref 校验 + 网络降级）。
- **测试**：36 个用例全通过（Layer1 Schema 校验 + Layer4 HAL 契约 + API 契约 + 门禁引擎）。
- **工程**：`Makefile`（schema-check / golden / hal-contract-test / correctness / test / api / web）、
  `pyproject.toml` 增加 pytest 配置（testpaths = tests, hal/contract_tests）。

### Known Issues
- `numpy` / `scipy` 未安装（网络慢），仅影响 `stat_test` 导入，Phase 1 前补装。

## [1.2.1] - 2026-10-14

### Added
- 初始化项目骨架并推送到 `git@github.com:fusheng13145/verity-lens.git`（commit b6d30e6）：后端 Python 骨架（`pyproject.toml` + hal/orchestrator/sidecar/bundles/skills/tests）、前端 `web/`（React+Vite+TS + tailwind v4 + `/api` proxy）、根目录 README/AGENTS/TODO/CHANGELOG、`.gitignore`/`.gitattributes`。
- 根目录 `README.md`：项目简介、技术栈、仓库结构、后端/前端快速开始。

## [1.2.0] - 2026-10-14

### Added
- 新增 Web 前端（React + Vite + TS）作为扩展交互面：阶段看板 / HITL 审批页 / 失败登记簿查看，对接 Headless API。
- 新增 `docs/frontend.md`：前端技术栈、目录、Headless API 契约、关键交互、构建联调。
- `project-spec.md` 将 Web 前端移入 In Scope；`interaction-design.md` §5 非目标改写 + §6 Web 前端交互小节；README 类型清单登记 `frontend.md`。

## [1.1.1] - 2026-10-14

### Changed
- 原完整设计方案重命名为 `docs/design-blueprint.md`，同步更新全部引用。

## [1.1.0] - 2026-10-14

### Added
- 文档体系补全（12 篇）：`docs/README.md` 体系总览、architecture、modules、interfaces、data-schema、agent-roles-prompts、orchestration-flows、tool-calling、deployment-ops、dev-conventions、testing、glossary。
- 对照通用项目文档结构补齐：`AGENTS.md`、`TODO.md`、`docs/project-spec.md`、`docs/bundle-registry.md`、`docs/interaction-design.md`。

## [1.0.0] - 2026-10-14

### Added
- 首个完整版设计方案：`docs/design-blueprint.md`。
  - 总体架构：五层 + 侧车，HAL 依赖收敛、文件即状态、失败一等公民。
  - 核心模块：HAL、Orchestrator Lite、失败驱动迭代（failure_ledger + 五类失败分类学）、Bundle 工厂（L0/L1/L2）、协作写锁、侧车层、成本与安全。
  - 数据设计：RESEARCH.yaml / hypothesis_tree / failure_ledger / experiment 四大 Schema。
  - 边界情况 E1–E15、四层测试体系、Phase 0–4 路线图、风险应对、SaaS 评估。
- 取消 V1/V2 阶段性版本拆分，合并为单次自包含完整版。

### Removed
- V1 中对底座内部特性的散落依赖（收敛至 HAL）；OT/CRDT 实时协作承诺（改为按需评估）。
