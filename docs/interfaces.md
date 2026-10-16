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

### 1.1 DSH 实现映射（hal/dsh_adapter.py）

底座 = [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)（MIT，developer preview）。
契约基线取自官方 `docs/cli-help.md` / `docs/config-catalog.md` / `docs/capability-seams.md`；
本机实测版本见 `hal/version_lock.yml`（当前 `verified_version = 0.2.0-rc.2`，2026-10-16 实测；
`--json` / `--session-id` / `--dump-config-schema` 已在真实底座验证，上表 ≥0.2 接口均已激活）。

| HAL 接口 | DSH 真实表面 | 版本要求 |
|----------|---------------|----------|
| `start_session` | `dsh --profile headless [--patch <p>] [--json] [--session-id <id>] "<task>"` | `--json` / `--session-id` ≥0.2 |
| `export_session_log` | 解析 `headless --json` 的 NDJSON 事件流 | ≥0.2（更低版本退化为最终消息） |
| `resume_session` | `dsh --profile headless --session-id <id>` 接管已持久化 Session | ≥0.2 |
| `fork_trajectory` | launcher 无此命令 → **恒定降级**为 `replay_to`（会话内前缀分叉属 `ctx.subagents`，HAL 不穿透） | — |
| `register_skills` | 发现 `skills/**/SKILL.md`；注入由 `ctx.skills` / skill-filesystem 在会话目录内完成 | — |
| `declare_mcp_servers` | `@deepseek-ai/dsh-mcp-client` `StdioConfig`：`transport/serverName/command/args/env/cwd/toolCallTimeoutMs/failOnStartupError`；工具名 `mcp__<serverName>__<rawName>` | — |
| `apply_preset_patch` | 物化为 patch-list 叠加层文件 → `--patch <path>`（可重复） | ≥0.1 |
| `spawn_subagent` | 会话内 `ctx.subagents` / tool-subagent 委派；launcher 不代跑，HAL 仅登记 | — |
| `set_permission` | 语义对齐 `ctx.sandboxPolicy`（`read-only` / `workspace-write`） | — |
| `capabilities()` | 版本锁结论 ∩ 运行期版本特性探测（`VERSION_FEATURE_MIN`） | — |

降级口径：底座不在 PATH → 全 False + `degraded:harness_unavailable`；版本过低 → 丢弃未知 flag +
`degraded:unsupported_flag`；MCP/patch 能力不可用 → `vl bundle load` 打印 `[DEGRADED]`。

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
| `vl finalize` | `--path <ws>` | 收尾校验：全实验终态 + 无未处理失败 + analysis/figures 就绪 + 可复现元数据完整度 + DOI 可验证率度量；生成 finalize_report.md | 0(ready)/2(blocked) |
| `vl sandbox` | `<project_id>` | 生成/校验容器沙箱 compose | 0/2 |
| `vl branch` | `<create\|merge\|status>` | Git 假设分支协作 | 0/2 |
| `vl identity` | `--require {set,coherent,signed}` | 身份解析与可信度检查（CI 门禁） | 0/2 |
| `vl rag` | `<index\|query>` | 文献 RAG 索引/检索（索引落盘 `.verity/rag-index.json`） | 0/1 |
| `vl run` | `--phase <p>` | pre_session 硬阻断链（门禁+预算+失败回流）通过后启动该阶段 Agent 会话；无底座时降级留痕 `harness_unavailable` | 0/2(阻断) |
| `vl advance` | `--no-start` | 校验下一阶段门禁 → 推进 `current_phase` → 启动会话 | 0/2(阻塞) |
| `vl verify-dois` | `--online` | DOI 可验证率度量：采集（RAG 索引/假设树/`cited_dois`）→ 校验 → 持久化（RESEARCH.yaml `metrics.doi_verification` + `docs/doi_verification.json`） | 0/1 |

实现状态：Phase 0 实现 `init` / `gate`；Phase 1 实现 `loop` / `budget`；Phase 2 实现 `bundle`（工厂 + 校验）；Phase 3 实现 `lock` / `sandbox` / `branch`；Phase 4a 实现 `finalize`（真实收尾闭环）；Phase 4c 实现 `bundle load`；Phase 4l 实现 `rag`；Phase 4j 实现 `identity`。状态机与会话驱动（`orchestrator/runner.py`）实现 `run` / `advance`：`vl advance` 是五阶段流动的唯一入口，`pre_session` 聚合门禁 + 预算 + 失败回流为硬阻断链。`verify-dois` 为 DOI 可验证率度量入口（系统自度量「≥95% DOI 可验证」）。

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
| POST | `/api/projects/{project_id}/failure_ledger` | 登记失败条目并驱动回流闭环（经 `failure_loop.apply_decision`：校验 → 路由 → 更新实验/假设树 → 追加 ledger → 渲染 lessons；HITL 强制：`decision.approved_by` 非空，违反返回 400） |
| GET | `/api/projects/{project_id}/doi-metrics` | DOI 可验证率度量（读取持久化结果；无则现算离线度量，不落盘） |
| POST | `/api/projects/{project_id}/doi-metrics` | 触发度量并持久化（body `{online: bool}`；`online=true` 真联网 Crossref） |

类型契约以 `orchestrator/schemas/*.json` 为单一真相；前端 `src/types/` 由其生成。

## 3. Sidecar 工具契约（注册为底座 tool）

每个工具 MUST 提供：
- `name`、`description`、`input_schema`（JSON Schema）、`output_schema`。
- 确定性：相同输入相同输出；耗时长任务走 HPC 提交并返回 job_id 轮询。

关键工具（已实现者标注 stdio 入口 `python -m sidecar.tools.<name>`）：
- `stat_test`：两组比较（t-test / Welch / Mann-Whitney）→ 输出 `{p_value, effect_size, ci_95, test_used}`。✅
- `power_analysis`（✅ Phase 4e）：先验样本量 / 事后功效 → 输出 `{required_n, power, underpowered, post_hoc_warning}`；
  正态近似双侧口径（d=0.5 → 63/组；精确非中心 t 检验为 64，临界样本量建议用 G*Power 复核）。
- `doi_verify`：输入 DOI → 输出 `{exists, metadata_match, error}`。✅
- `desensitize`（✅ Phase 4f）：敏感数据脱敏 + PHI 扫描守卫，四种 mode：`field_mask`（hash 令牌/redact/generalize）、
  `k_anonymity`（QI 抑制至 ≥k）、`dp_aggregate`（Laplace，ε=1.0，seed 可复现）、`scan_text`（E10 prompt 守卫）。
- `hpc_submit`（✅ Phase 4g）：长任务远程提交 + 状态轮询 → 输出 `{job_id, state, status_endpoint}`；可插拔 backend（`dry_run` 默认 / `mock` / `slurm` / `pbs`），`dry_run`/`mock` 确定性、不实际执行，规避终端关闭中断（E13）；`slurm`/`pbs` best-effort 调用并显式降级。
- `plot`（✅ 交付审计轮）：确定性零依赖 SVG 图表（bar / line），`render(csv_path, out_path, *, kind, title)`；相同输入逐字节一致，产物可被 writing 门禁 `_looks_like_image` 识别（供 `figures_substantive` 与 `scripts/reproduce.py` 复现比对）。

## 4. MCP Server 契约

- 标准 MCP 协议；Bundle 侧声明在各 `bundles/<discipline>/bundle.yml` 的 `mcp.servers`（name / transport / command / tools），由 `vl bundle load` 经 HAL `declare_mcp_servers` 注册。
- sidecar 确定性工具提供 stdio 入口：`python -m sidecar.tools.<tool>`（stdin JSON 参数 → stdout JSON 结果，见 `sidecar/tools/_stdio.py`），使 MCP 声明可执行而非纸面配置。
- **常驻守护进程**（✅ 交付审计轮）：`python -m sidecar.daemon`（`sidecar/daemon.py`）——单进程长驻处理多工具调用，NDJSON 行协议（与 MCP stdio 传输同构）：
  - 启动输出 `{"type":"ready","tools":[...],"protocol":"ndjson-line"}`；
  - 请求 `{"id":<any>,"tool":"plot","params":{...}}` → 响应 `{"id","ok":true,"result":{...}}` 或 `{"id","ok":false,"error":"..."}`；
  - `{"type":"shutdown"}` 或 stdin EOF 优雅退出；SIGTERM/SIGINT 优雅退出；单行错误隔离不崩进程；
  - 工具注册表 `sidecar/tools/_registry.py`（新增工具登记一处即可）。需要复用导入/降低冷启动时以 daemon 替代每调用一进程的一次性 `_stdio.serve`（后者保留向后兼容）。
- 适用：需长期运行、多客户端、标准协议的外部服务（OpenAlex/PubMed、HPC 状态）。
- 注册经 HAL `declare_mcp_servers`。

## 5. 数据契约（声明式文件）

所有文件 schema 见 `data-schema.md` 与 `orchestrator/schemas/`。核心契约：
- `RESEARCH.yaml`：项目唯一元数据真相源；`metrics.doi_verification`（✅ 交付审计轮）为 DOI 可验证率度量（`{total, valid_format, verified, verification_rate, online, checked_at}`，`vl verify-dois` / `vl finalize` / API POST 写入）。
- `docs/doi_verification.json`（✅ 交付审计轮）：同一度量的 JSON 落盘（前端看板 DoiCard 数据源）。
- `hypothesis_tree.json`：假设节点 `parent_id` 不得成环。
- `failure_ledger.json`：每条 failed 实验必关联 entry；refuted 节点必附 `justified_by`；API 直写通道已关闭（必经 `apply_decision` 回流闭环）。
- `experiments/exp_NNN.yaml`：终态集合 `{completed, concluded_failed, suspended, abandoned}`，`failed` 为临时态。
