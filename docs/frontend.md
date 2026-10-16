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

## 2. 目录结构（已实现，交付审计轮）

```
web/
├── src/
│   ├── pages/        # Dashboard（项目看板：阶段/HITL/DOI/失败登记簿）
│   ├── components/   # PhasePipeline / HitlPanel / DoiCard / FailureLedger
│   ├── api.ts        # axios 实例 + 端点封装（仅调 Headless API）
│   ├── types.ts      # TS 类型（与 Headless API 返回结构对应）
│   ├── App.tsx       # QueryClientProvider + react-router（/ 项目选择 → /project/:id 看板）
│   └── main.tsx
├── vite.config.ts    # dev proxy /api → http://localhost:8000（Tailwind v4 经 @tailwindcss/vite 插件）
└── package.json
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
| GET/POST | `/api/projects/{id}/failure_ledger` | 查看 / 登记失败（POST 经 `apply_decision` 回流闭环，HITL 强制） |
| GET/POST | `/api/projects/{id}/doi-metrics` | DOI 可验证率度量（POST 触发度量并持久化，`{online}` 可选真联网） |

类型契约以 `orchestrator/schemas/*.json` 为单一真相；前端用 `openapi-typescript` 或脚本由后端 OpenAPI 生成 `src/types/`。

## 4. 关键交互（实现状态：交付审计轮已落地核心三页）

- **阶段看板** ✅（`PhasePipeline`）：展示 `current_phase` + 各阶段闸门状态（通过 / 待 HITL / 未就绪 + 缺失清单）。
- **HITL 审批** ✅（`HitlPanel`）：需人工审批的阶段门禁批准动作（写入 `approvals[phase]`）。
  四要素完整卡片（产出摘要含证据引用 / 风险提示含预算使用率）可按 `interaction-design.md` §2 后续增强。
- **失败登记簿** ✅（`FailureLedger`，只读）：渲染条目（分类徽标 EXEC/DATA/METH/HYP/EPIS、
  决策与批准人、lessons）；按分类筛选可后续增强。
- **DOI 可验证率** ✅（`DoiCard`）：可验证率进度条 + 离线复算 / 联网 Crossref 校验按钮（≥95% 目标）。
- **降级/阻断透传**：API 返回的结构化字段（`degraded_features` / `budget_blocked` / `low_confidence`）
  按 `interaction-design.md` §3 统一呈现，数值结论标注来源工具（后续增强）。

## 5. 构建与联调

- 开发：`vite.config.ts` 配置 `server.proxy['/api'] = 'http://localhost:8000'`；`npm run dev`（默认 5173）。
- 后端：`uvicorn orchestrator.api:app --port 8000`（FastAPI，见 `interfaces.md` 与后端初始化步骤）。
- 构建：`npm run build` 产出静态文件，可由 Headless API 托管或独立部署（Nginx / 静态托管）。

## 6. 非目标

- 不重新设计 DSH 原生 Web UI 的视觉风格；
- 不在 Web 前端实现复杂 Agent 会话操作（复杂任务仍走 CLI / DSH 原生 UI）；
- 不直连底座或绕过 Headless API 读写 Workspace 文件。
