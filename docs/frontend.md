# 前端设计规范（Frontend）

**目的**：定义 Web 前端（`web/`，React + Vite + TypeScript）的技术栈、目录结构、与后端 Headless API 的契约。本前端是设计的**扩展交互面**（阶段看板 / HITL 审批页 / 失败登记簿查看），不替代 CLI，也不重新设计 DSH 原生 Web UI。CLI 输出与 HITL 交互规范见 `interaction-design.md`。

## 1. 技术栈

| 关注点 | 选型 |
|--------|------|
| 框架/构建 | React 18 + Vite + TypeScript |
| 路由 | react-router-dom |
| 数据请求 | axios + @tanstack/react-query（缓存/重试/失效） |
| 样式 | tailwindcss（轻量，不引入重组件库） |
| 状态 | react-query 服务端状态 + 局部 Context（UI 状态） |

## 2. 目录结构

```
web/
├── src/
│   ├── pages/        # Dashboard / PhaseGate / FailureLedger / HypothesisTree / Experiments
│   ├── components/   # 通用组件（缺失清单卡、审批四要素卡、状态徽标）
│   ├── api/          # axios 实例 + 端点封装（仅调 Headless API）
│   ├── types/        # TS 类型（由 orchestrator/schemas/*.json 生成，禁止手写漂移）
│   └── store/        # react-query hooks
├── vite.config.ts    # dev proxy /api → http://localhost:8000
└── tailwind.config.js
```

## 3. 与后端契约（Headless API）

前端**只**经 Headless API 与系统交互，不得直连底座或读写 Workspace 文件系统。建议端点：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects/{id}` | 项目元数据（RESEARCH.yaml：阶段/审批/预算/写锁） |
| GET | `/api/projects/{id}/phases` | 阶段与门禁状态（通过项/阻塞项缺失清单） |
| POST | `/api/projects/{id}/approve_phase` | HITL 审批（写 approvals + Git commit） |
| GET | `/api/projects/{id}/hypothesis_tree` | 假设树（含 refuted/revised + 证据链） |
| GET | `/api/projects/{id}/experiments` | 实验列表与状态 |
| GET/POST | `/api/projects/{id}/failure_ledger` | 查看 / 登记失败（POST 须经 HITL） |

类型契约以 `orchestrator/schemas/*.json` 为单一真相；前端用 `openapi-typescript` 或脚本由后端 OpenAPI 生成 `src/types/`。

## 4. 关键交互

- **阶段看板**：展示 `current_phase` + 门禁通过项 / 阻塞项，沿用 `interaction-design.md` §1 的三段式缺失清单格式。
- **HITL 审批页**：必须呈现四要素（产出摘要含证据引用 / 下一阶段准入条件 / 风险提示含预算使用率与未终态实验数 / 明确确认动作），禁止无上下文"是否继续"。
- **失败登记簿页**：按 `failure_ledger` 渲染，支持按失败分类（EXEC/DATA/METH/HYP/EPIS）筛选，展示 evidence 指针与 lessons。
- **降级/阻断透传**：API 返回的结构化字段（`degraded_features` / `budget_blocked` / `low_confidence`）按 `interaction-design.md` §3 统一呈现，数值结论标注来源工具。

## 5. 构建与联调

- 开发：`vite.config.ts` 配置 `server.proxy['/api'] = 'http://localhost:8000'`；`npm run dev`（默认 5173）。
- 后端：`uvicorn orchestrator.api:app --port 8000`（FastAPI，见 `interfaces.md` 与后端初始化步骤）。
- 构建：`npm run build` 产出静态文件，可由 Headless API 托管或独立部署（Nginx / 静态托管）。

## 6. 非目标

- 不重新设计 DSH 原生 Web UI 的视觉风格；
- 不在 Web 前端实现复杂 Agent 会话操作（复杂任务仍走 CLI / DSH 原生 UI）；
- 不直连底座或绕过 Headless API 读写 Workspace 文件。
