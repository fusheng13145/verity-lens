# verity-lens（真理之眼）

> 科研全能 Agent 系统 —— 以 Agent 运行时（DeepSeek Harness）为底座，通过工程化约束（可复现、可审计、失败闭环）让 AI 可靠地参与"文献 → 假设 → 实验 → 分析 → 写作"全流程。

- 定位：实验室内部科研助手原型（1–10 人团队），单机优先，非 SaaS。
- 核心价值：**失败闭环**（结构化归因与假设迭代）、**可追溯**（声明式文件即状态）、**方法论可工程化**（Schema + SKILL 约束 + 确定性工具）。
- 完整设计：见 [`docs/`](docs/README.md)（`design-blueprint.md` 为权威蓝图）。

## 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 运行底座 | DeepSeek Harness（DSH） | agent loop / 子代理 / 会话日志 / 沙箱；经 `hal/` 适配层隔离 |
| 后端 | Python ≥3.11（FastAPI + argparse） | 编排层（Orchestrator Lite）、HAL 适配层、Sidecar 确定性工具 |
| 前端 | React 18 + Vite + TypeScript | 阶段看板 / HITL 审批页 / 失败登记簿（扩展交互面，对接 Headless API） |
| 协作 | Git（假设分支 + 制品写锁 + PR review） | 多人并行研究，非实时共享会话 |
| 文档 | Markdown 文档体系（`docs/`） | 架构 / 模块 / 接口 / 角色 / 数据 / 部署 / 前端规范 |

## 仓库结构

```
verity-lens/
├── AGENTS.md            # AI 编码代理硬规则入口
├── README.md            # 本文件（项目简介与快速开始）
├── CHANGELOG.md         # 版本更新记录
├── TODO.md              # 开发计划与当前进度
├── pyproject.toml       # Python 包与依赖声明
├── hal/                 # 适配层（唯一依赖底座的模块）
├── orchestrator/        # 编排层（无状态事件处理器）
├── sidecar/             # 确定性工具与外部对接（RAG/统计/脱敏/HPC）
├── bundles/             # 学科包（L0/L1/L2）+ _template
├── skills/              # 跨学科通用 Skills
├── tests/               # L1-L4 测试（含 HAL 契约）
├── web/                 # 前端（React + Vite + TS）
└── docs/                # 文档体系（导航见 docs/README.md）
```

## 快速开始

### 后端

```bash
# 1. 虚拟环境
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. 安装依赖
pip install -e .

# 3. 验证 CLI
vl            # 打印全部子命令与用法
```

### CLI 命令一览

| 命令 | 作用 | 退出码 |
|------|------|--------|
| `vl init <discipline>` | 生成 Workspace 脚手架 + 挂载学科 Bundle | 0/1 |
| `vl gate <phase>` | 校验阶段准入，输出缺失清单 | 0(放行)/2(阻塞) |
| `vl loop` | 扫描 failed 实验，校验/执行失败回流 | 0/2 |
| `vl budget check` | 读 token_budget，超限报 HARD_BLOCK | 0/3(硬阻断) |
| `vl lock <acquire\|release\|check> <artifact>` | 管理制品写锁（先到先得 + 超时失效） | 0/2(冲突) |
| `vl bundle new <discipline> [--capability <cap>]` | 生成 L0 学科 Bundle 骨架 | 0/1 |
| `vl bundle validate <bundle_dir>` | 校验 Bundle 结构合规（L2 强制 preset_patch/mcp/golden_cases） | 0/2 |
| `vl bundle load <bundle_dir>` | 加载 Bundle 到运行底座（Skill/MCP/Preset 注册，能力缺失显式降级） | 0/2 |
| `vl finalize --path <ws>` | 收尾校验 + 生成 finalize_report.md（含 AI 贡献声明草稿） | 0(ready)/2(blocked) |
| `vl sandbox <project_id>` | 生成/校验容器沙箱 compose | 0/2 |
| `vl branch <create\|merge\|status>` | Git 假设分支协作流 | 0/2 |

> 完整契约见 [`docs/interfaces.md`](docs/interfaces.md)。

### 前端

```bash
cd web
npm install                  # 首次安装（已随脚手架完成）
npm run dev                  # http://localhost:5173
```

前端在开发期通过 Vite proxy 将 `/api` 转发到后端 `localhost:8000`（Headless API，FastAPI）。
前端规范与 API 契约见 [`docs/frontend.md`](docs/frontend.md)。

### 运行底座接入

底座（DSH）经 `hal/` 接入；已验证版本与能力集见 `hal/version_lock.yml`。
升级底座须修改版本锁并过 `make hal-contract-test`（契约测试见 `tests/hal_contract/`）。

## 开发约定

- 分支：`main`（需 PR）+ `hypothesis/Hx`（假设分支）。
- 硬规则：除 `hal/` 外禁止 import 底座内部 API；跨模块交互先登记 `docs/interfaces.md`。
- 文档同步：接口变更必改 `docs/interfaces.md` + `docs/modules.md`；新学科 Bundle 必在 `docs/bundle-registry.md` 登记。
- 完整规范见 [`docs/dev-conventions.md`](docs/dev-conventions.md) 与 [`AGENTS.md`](AGENTS.md)。

## 状态

- 当前阶段：**核心闭环已落地（Phase 0–4c 部分）** —— 文件即状态门禁、失败驱动迭代、学科包化（biomed / materials / compsci 三学科均 **L2**：Preset Patch + MCP 声明 + Golden 用例，`vl bundle load` 一键加载）、容器沙箱、RAG 侧车、制品写锁、Git 协作流、`vl finalize` 收尾闭环。详见 [`TODO.md`](TODO.md) 与 [`CHANGELOG.md`](CHANGELOG.md)。
- 下一步（Phase 4c 收尾）：DSH 底座真实化后的端到端联调（真实 `dsh` 接入 + L2 轨迹回归 edit distance ≤2）+ 协作模型按真实痛点重评估。
- 功能范围与成功指标见 [`docs/project-spec.md`](docs/project-spec.md)。
