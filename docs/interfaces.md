# 接口文档

**目的**：定义模块间契约（低耦合的关键）。所有跨模块交互必须经本文档定义的接口；实现可替换，契约不可随意破坏。

---

## 1. HAL 抽象接口（唯一依赖底座的契约）

```python
class HarnessAdapter(Protocol):
    # 会话生命周期
    def start_session(self, preset: str, workspace: str, task: str) -> "SessionHandle": ...
    def resume_session(self, handle: "SessionHandle") -> "SessionHandle": ...
    def stop_session(self, handle: "SessionHandle", graceful: bool = True) -> None: ...

    # 轨迹与可追溯性
    def export_session_log(self, handle: "SessionHandle") -> Iterator[dict]: ...
    def fork_trajectory(self, handle: "SessionHandle", at_event: str) -> "SessionHandle": ...

    # Skill / 工具注册
    def register_skills(self, skill_dirs: list[str]) -> None: ...
    def register_tools(self, tools: list["ToolSpec"]) -> None: ...
    def declare_mcp_servers(self, config: dict) -> None: ...

    # 权限与 Preset
    def apply_preset_patch(self, patch: "PresetPatch") -> None: ...
    def set_permission(self, scope: str, level: Literal["read", "workspace_write", "none"]) -> None: ...

    # 子代理
    def spawn_subagent(self, spec: "SubagentSpec") -> "SubagentHandle": ...

    # 能力探测
    def capabilities(self) -> dict: ...
```

**契约规则**：
- `capabilities()` 返回键固定：`trajectory_fork / preset_patch / subagent / mcp / session_log_export`（bool）。
- 任何特性为 false 时，调用方 MUST 走降级路径，不得抛未捕获异常。
- 接口变更须同步 `hal/contract_tests/` 并升版。

## 2. CLI 命令契约（`vl`）

| 命令 | 参数 | 行为 | 退出码 |
|------|------|------|--------|
| `vl init` | `<discipline>` | 生成 Workspace 脚手架 + 挂载 L0 Bundle | 0/1 |
| `vl gate` | `<phase>` | 校验阶段准入，输出缺失清单 | 0(放行)/2(阻塞) |
| `vl loop` | — | 扫描 failed 实验，校验/执行回流 | 0/2 |
| `vl budget check` | — | 读 token_budget，超限报 HARD_BLOCK | 0/3(硬阻断) |
| `vl lock` | `<acquire\|release\|check> <artifact>` | 管理制品写锁 | 0/2(冲突) |
| `vl bundle new` | `<discipline>` | 生成 L0 Bundle 骨架 | 0/1 |
| `vl bundle validate` | `<bundle_dir>` | 校验 Bundle 结构合规（L2 追加 preset_patch/mcp/golden_cases 三要素） | 0/2 |
| `vl bundle load` | `<bundle_dir>` | 加载 Bundle 到运行底座：HAL 注册 Skill / MCP / Preset Patch；能力缺失显式降级并输出 | 0/2 |
| `vl finalize` | `--path <ws>` | 收尾校验：全实验终态 + 无未处理失败 + analysis/figures 就绪 + 可复现元数据完整度；生成 finalize_report.md | 0(ready)/2(blocked) |
| `vl sandbox` | `<project_id>` | 生成/校验容器沙箱 compose | 0/2 |
| `vl branch` | `<create\|merge\|status>` | Git 假设分支协作 | 0/2 |

实现状态：Phase 0 实现 `init` / `gate`；Phase 1 实现 `loop` / `budget`；Phase 2 实现 `bundle`（工厂 + 校验）；Phase 3 实现 `lock` / `sandbox` / `branch`；Phase 4a 实现 `finalize`（真实收尾闭环，含可复现元数据校验）；Phase 4c 实现 `bundle load`（bundle.yml → HAL 注册，能力缺失显式降级）。

## 2.1 Headless API 契约（供 Web 前端）

前端（`web/`）**只**经 Headless API 与系统交互，不得直连底座或读写 Workspace 文件系统。启动：`uvicorn orchestrator.api:app --port 8000`；前端开发期经 Vite proxy 将 `/api` 转发到 `:8000`。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects/{project_id}` | 项目元数据（RESEARCH.yaml：阶段/审批/预算/写锁/降级特性） |
| GET | `/api/projects/{project_id}/phases` | 各阶段门禁状态 + 命名事实（阶段看板数据源） |
| POST | `/api/projects/{project_id}/approve_phase` | HITL 审批，写入 `approvals[phase]`（approver + UTC 时间戳） |
| GET | `/api/projects/{project_id}/hypothesis_tree` | 假设树（含 refuted/revised + provenance 证据链） |
| GET | `/api/projects/{project_id}/experiments` | 实验列表与状态 |
| GET | `/api/projects/{project_id}/failure_ledger` | 查看失败登记簿 |
| POST | `/api/projects/{project_id}/failure_ledger` | 登记失败条目（HITL 强制：`decision.approved_by` 非空） |

类型契约以 `orchestrator/schemas/*.json` 为单一真相；前端 `src/types/` 由其生成。

## 3. Sidecar 工具契约（注册为底座 tool）

每个工具 MUST 提供：
- `name`、`description`、`input_schema`（JSON Schema）、`output_schema`。
- 确定性：相同输入相同输出；耗时长任务走 HPC 提交并返回 job_id 轮询。

关键工具：
- `stat_test`：t/ANOVA/非参数/多重校正 → 输出 `{p_value, effect_size, ci_95, test_used}`。
- `power_analysis`：先验/事后功效 → 输出 `{power, required_n}`，承担失败归因复核。
- `doi_verify`：输入 DOI → 输出 `{exists, metadata_match}`。
- `hpc_submit`：输入命令+资源 → 输出 `{job_id, status_endpoint}`。

## 4. MCP Server 契约

- 标准 MCP 协议；Bundle 侧声明在各 `bundles/<discipline>/bundle.yml` 的 `mcp.servers`（name / transport / command / tools），由 `vl bundle load` 经 HAL `declare_mcp_servers` 注册。
- sidecar 确定性工具提供 stdio 入口：`python -m sidecar.tools.<tool>`（stdin JSON 参数 → stdout JSON 结果，见 `sidecar/tools/_stdio.py`），使 MCP 声明可执行而非纸面配置。
- 适用：需长期运行、多客户端、标准协议的外部服务（OpenAlex/PubMed、HPC 状态）。
- 注册经 HAL `declare_mcp_servers`。

## 5. 数据契约（声明式文件）

所有文件 schema 见 `data-schema.md` 与 `orchestrator/schemas/`。核心契约：
- `RESEARCH.yaml`：项目唯一元数据真相源。
- `hypothesis_tree.json`：假设节点 `parent_id` 不得成环。
- `failure_ledger.json`：每条 failed 实验必关联 entry；refuted 节点必附 `justified_by`。
- `experiments/exp_NNN.yaml`：终态集合 `{completed, concluded_failed, suspended, abandoned}`，`failed` 为临时态。
