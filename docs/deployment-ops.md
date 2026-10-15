# 部署与运维说明

**目的**：指导系统落地、运行与灾备，落实"可维护性"。底座经 HAL 接入，单机优先，算力密集任务走工具侧远程提交。

## 1. 环境要求

- OS：Linux / macOS（Windows 可直接运行，底座 shim 走 `.cmd`）；Python 3.11+。
- 运行底座：DeepSeek Harness（版本须与 `hal/version_lock.yml` 一致）。
- 底座前置：Node.js `^20.19 || >=22`（官方 README 要求）；从源码构建需 pnpm。
- 容器：Docker（沙箱隔离）；可选 HPC 集群（Sidecar 提交）。

## 2. 安装步骤

```bash
git clone <repo> && cd verity-lens
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .

# 安装并验证底座（二选一）
npx @deepseek-ai/dsh web                              # 零安装入口，Web UI :3080
npm i -g @deepseek-ai/dsh                              # 全局安装，命令行可用 dsh

dsh --version                                         # 打印版本号 → 填入 version_lock.yml
vl init <discipline>                                   # 生成首个 Workspace，挂载 L0 Bundle
make hal-contract-test                                 # 验证 HAL 与当前底座版本兼容
```

## 3. 底座接入与版本锁

- `hal/version_lock.yml` 记录：证据来源仓库、`verified_version`（本机实测版本）、`contract_baseline`（官方 CLI 契约基线）、能力集、已知差异。
- 升级：改版本锁 → `make hal-contract-test` → 通过才生效；失败由 HAL 适配修复。
- **能力集 = 版本锁结论 ∩ 运行期特性探测**（`DSHAdapter.capabilities()`）：运行期按 `dsh --version` 收窄，避免对旧底座发出未知选项。
- 特性版本门控（`VERSION_FEATURE_MIN`）：`--patch` ≥0.1；`--json` / `--session-id` / `--dump-config-schema` ≥0.2。底座不支持时自动丢弃该 flag 并写 `degraded` 事件。

### 3.1 HAL 使用的真实 DSH CLI 表面

```
dsh [--profile] <name> [options] [app-args...]
  --profile <name>                启动 $DSH_HOME/profiles 下的 profile（出厂：web/headless/sdk/sdk-minimal/acp）
  --patch <path>                  profile 层之上的 patch-list 叠加层（可重复）← verity-lens Preset Patch
  --dump-config / --dump-default-config / --dump-config-schema(≥0.2)

dsh --profile headless --json "<task>"            NDJSON 运行事件流（≥0.2）
dsh --profile headless --session-id <id> "..."    接管已持久化 Session（≥0.2，未知 id 报错）
```

MCP 服务按 `@deepseek-ai/dsh-mcp-client` 的 `StdioConfig` 声明：
`transport: stdio` / `serverName`（`[A-Za-z0-9_-]{1,32}`）/ `command` / `args[]` / `env?` / `cwd?` /
`toolCallTimeoutMs` / `failOnStartupError`；模型可见工具名为 `mcp__<serverName>__<rawName>`。
Bundle 的声明格式到该配置的映射在 `orchestrator/bundle_loader.py:to_dsh_mcp_config`。

### 3.2 底座不可用 / 版本过低时的行为

| 情形 | 行为 |
|------|------|
| `dsh` 不在 PATH | `capabilities()` 全 False；`start_session` 写 `degraded:harness_unavailable` 事件 |
| 底座 < 0.2 | 丢弃 `--json` / `--session-id`，写 `degraded:unsupported_flag`，退化为最终消息流 |
| MCP / patch 能力不可用 | `vl bundle load` 输出 `[DEGRADED]`，改为编排层直连 sidecar / 启动参数注入系统提示 |

## 4. 沙箱配置（安全隔离）

- `docker/sandbox-compose.yml`：`cap_drop: ALL`、`network_mode: none`、`read_only: true`、`tmpfs`。
- 挂载按读写粒度：`data/raw:ro`、`data/processed|figures|manuscript:rw`。
- 资源限制：`cpus:4 / memory:8g / pids:100`。
- 底座自带沙箱（`ctx.sandbox` / `sandbox-local`、`bash-sandbox`、`fs-sandbox`）可与本 compose 二选一或叠加；
  权限语义对齐 `workspace-write` / `read-only`。

## 5. 敏感数据治理管道

```
原始敏感数据(data/raw, 容器外) → sidecar 脱敏 → 脱敏版(data/processed, 底座可读) → Agent 仅基于脱敏推理 → 个体结论人工审核
```
`never_in_context` 清单见 `tool-calling.md` 第 5 节。

## 6. CI / 自动化

| 阶段 | 命令 | 门禁 |
|------|------|------|
| commit | `make schema-check`（L1） | 100% 通过 |
| daily | `make golden`（L2 轨迹） | edit distance ≤2 |
| 底座升级 | `make hal-contract-test` | 100% |
| 周级 | `make correctness`（L3） | 数值100%/引用≥95% |

## 7. 监控与告警

- 预算：编排层在 `token_budget.used` 达 70% 软告警、100% 硬阻断。
- 长任务：HPC 作业状态经 `hpc_status` MCP 轮询；本地 headless 进程用 tmux/systemd 守护。
- 会话中断：底座 ≥0.2 用 `dsh --profile headless --session-id <id>` 断点续跑；
  <0.2 无 session 接管能力，只能重跑任务（Session 落盘仍由 `ctx.sessionPersistence` 保证）。

## 8. 灾备与恢复

- 编排层崩溃：无状态，重启即从 Workspace 文件恢复（无需修复）。
- 硬阻断恢复：暂停会话 → 导出 Session Log → 通知（追加预算/降级模型/人工接管）→ 断点续跑。
- 底座数据：Workspace 全量 Git 管理；大文件走 MinIO/S3 + 引用计数。

## 9. 运维边界声明

- 当前版本非多租户、非 SaaS；运维对象为单/少量实验室实例。
- 多人协作经 Git 流 + 写锁，非实时共享会话（见 `architecture.md` 协作边界）。
- 底座处于 developer preview：官方明示会有破坏性变更，升级前先看 `known_differences`。
