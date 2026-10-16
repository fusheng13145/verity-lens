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
| `vl identity [--require {set\|coherent\|signed}]` | 身份解析与可信度分级（VL_USER vs git committer + 提交签名锚点，CI 强制门禁） | 0/1 |
| `vl rag index <dir\|file>` / `vl rag query --query "..."` | 文献 RAG 索引与检索（持久化 `.verity/rag-index.json`；写入动作接入 opt-in 埋点） | 0 |
| `vl run --phase <p>` | pre_session 硬阻断链（门禁+预算+失败回流）通过后启动该阶段 Agent 会话；无底座时降级留痕 | 0/2(阻断) |
| `vl advance [--no-start]` | 校验下一阶段门禁 → 推进 `current_phase` → 启动会话（五阶段流动唯一入口） | 0/2(阻塞) |
| `vl verify-dois [--online]` | DOI 可验证率度量（采集→校验→持久化；`--online` 真联网 Crossref） | 0/1 |

> 完整契约见 [`docs/interfaces.md`](docs/interfaces.md)。

### 前端

```bash
make api                     # 后端 Headless API（uvicorn，:8000）
cd web && npm run dev        # 前端开发服务器（:5173）
```

前端为真实业务界面（React + react-query + Tailwind）：`/` 选择项目 → `/project/<id>` 看板
——**阶段看板**（5 阶段闸门状态/缺失项/当前阶段高亮）、**HITL 审批**（批准需人工确认的阶段门禁，
写入 `approvals[phase]`）、**DOI 可验证率卡片**（离线复算 / 联网 Crossref 校验）、
**失败登记簿**（决策与批准人留痕）。开发期经 Vite proxy 将 `/api` 转发到后端 `:8000`。
前端规范与 API 契约见 [`docs/frontend.md`](docs/frontend.md)。

### 运行底座接入

底座（DSH）经 `hal/` 接入；已验证版本与能力集见 `hal/version_lock.yml`。
升级底座须修改版本锁并过 `make hal-contract-test`（契约测试见 `hal/contract_tests/`）。
本机安装底座：`make harness-install`（`npm i -g @deepseek-ai/dsh`，多版本共存用 `DSH_BIN` 环境变量）；
CI 有独立 `harness-contract` workflow，环境有 dsh 时自动真跑真底座契约，缺失时按 skipif 优雅跳过。

## 开发约定

- 分支：`main`（需 PR）+ `hypothesis/Hx`（假设分支）。
- 硬规则：除 `hal/` 外禁止 import 底座内部 API；跨模块交互先登记 `docs/interfaces.md`。
- 文档同步：接口变更必改 `docs/interfaces.md` + `docs/modules.md`；新学科 Bundle 必在 `docs/bundle-registry.md` 登记。
- 完整规范见 [`docs/dev-conventions.md`](docs/dev-conventions.md) 与 [`AGENTS.md`](AGENTS.md)。

## 状态

- 当前阶段：**全流程可运行（Phase 0–4 + 交付审计修复完成）** —— 文件即状态门禁、失败驱动迭代、学科包化（biomed / materials / compsci 三学科均 **L2**）、容器沙箱、RAG 侧车、制品写锁、Git 协作流、`vl finalize` 收尾闭环（含 DOI 可验证率自度量）；HAL 契约对齐真实底座 [deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)（本机实测 0.2.0-rc.2）；**状态机 + 会话驱动**（`vl run` / `vl advance`：pre_session 硬阻断链 → 启动 Agent 会话，无底座显式降级留痕）；writing 门禁硬化（占位文件不可伪造）；失败闭环经 API 亦不可绕过；Sidecar 常驻守护进程（NDJSON 行协议）；`make reproduce` 真实可复现比对；前端真实看板 + HITL 审批页。全量测试 **323 passed / 3 skipped**。详见 [`DELIVERY-READINESS-AUDIT.md`](DELIVERY-READINESS-AUDIT.md)、[`TODO.md`](TODO.md) 与 [`CHANGELOG.md`](CHANGELOG.md)。
- 下一步（仅余外部依赖）：完整 headless 端到端运行待 dsh 底座 + deepseek API 配额到位（CI `harness-contract` 与 `make harness-install` 已就绪，环境具备即真跑）；协作模型最终是否调整待 1–10 人团队真实痛点反馈。
- 功能范围与成功指标见 [`docs/project-spec.md`](docs/project-spec.md)。
