# AGENTS.md — 项目协作与代码开发规范（AI 编码代理入口）

> 本文件面向在本仓库中工作的 **AI 编码代理**（Codex / Cursor / Claude Code 等），是代理可读的硬规则入口。人类团队规范详见 `docs/dev-conventions.md`（本文件不重复其内容，只做收敛引用）。

## 1. 仓库地图

```
verity-lens/
├── AGENTS.md              # 本文件（代理硬规则入口）
├── README.md              # 项目简介与快速开始（已完成）
├── CHANGELOG.md           # 版本更新记录
├── TODO.md                # 开发计划与当前进度
└── docs/                  # 文档体系（导航：docs/README.md）
    ├── design-blueprint.md        # 权威设计蓝图（先读）
    ├── architecture.md / modules.md / interfaces.md
    ├── data-schema.md / agent-roles-prompts.md / orchestration-flows.md
    ├── tool-calling.md / testing.md / deployment-ops.md
    ├── dev-conventions.md / glossary.md
    └── project-spec.md / bundle-registry.md / interaction-design.md
```

## 2. 硬规则（违反 = 提交被打回）

1. **依赖收敛**：除 `hal/` 外，任何模块禁止 import 运行底座（DSH）内部 API。
2. **契约先行**：跨模块交互必须先在 `docs/interfaces.md` 登记，再写实现。
3. **文档同步**：接口变更必改 `docs/interfaces.md` + `docs/modules.md`；新学科 Bundle 必在 `docs/bundle-registry.md` 登记。
4. **提示词纪律**：领域知识不进提示词（走 SKILL 参考文件 + 检索）；关键数值必经确定性 Sidecar 工具复算。
5. **状态落盘**：项目状态只写声明式文件（`data-schema.md`），不建独立状态库。
6. **失败必留痕**：`failed` 是临时态，必须走 failure_loop 归因登记，不允许静默忽略。

## 3. 常用命令

```
make schema-check        # L1 Schema 校验（每次提交前必跑）
make golden              # L2 轨迹回归
make hal-contract-test   # 底座升级时必跑
vl gate <phase>          # 阶段门禁校验
vl loop                  # 失败回流检查
```

## 4. 提交约定

- 前缀：`feat/hal:` `fix/gate:` `docs/bundle:` `test/golden:` + 简述。
- 底座（DSH）升级提交必含 `hal/version_lock.yml` 变更 + `make hal-contract-test` 通过记录。
