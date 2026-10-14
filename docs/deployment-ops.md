# 部署与运维说明

**目的**：指导系统落地、运行与灾备，落实"可维护性"。底座经 HAL 接入，单机优先，算力密集任务走工具侧远程提交。

## 1. 环境要求

- OS：Linux / macOS（Windows 经 WSL）；Python 3.11+。
- 运行底座：DeepSeek Harness（版本须与 `hal/version_lock.yml` 一致）。
- 容器：Docker（沙箱隔离）；可选 HPC 集群（Sidecar 提交）。

## 2. 安装步骤

```
git clone <repo> && cd verity-lens
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# 安装并验证底座
vl init <discipline>            # 生成首个 Workspace，挂载 L0 Bundle
make hal-contract-test         # 验证 HAL 与当前底座版本兼容
```

## 3. 底座接入与版本锁

- `hal/version_lock.yml` 记录已验证底座版本 + 能力集 + 已知差异。
- 升级：改版本锁 → CI 跑 `hal-contract` + L1/L2 Golden → 通过才生效；失败由 HAL 适配修复。
- 切换演练：每季度评估备选底座接入成本（HAL 接口不变则低成本）。

## 4. 沙箱配置（安全隔离）

- `docker/sandbox-compose.yml`：`cap_drop: ALL`、`network_mode: none`、`read_only: true`、`tmpfs`。
- 挂载按读写粒度：`data/raw:ro`、`data/processed|figures|manuscript:rw`。
- 资源限制：`cpus:4 / memory:8g / pids:100`。

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
| 底座升级 | `make hal-contract` | 100% |
| 周级 | `make correctness`（L3） | 数值100%/引用≥95% |

## 7. 监控与告警

- 预算：编排层在 `token_budget.used` 达 70% 软告警、100% 硬阻断。
- 长任务：HPC 作业状态经 `hpc_status` MCP 轮询；本地 headless 进程用 tmux/systemd 守护。
- 会话中断：长任务不依赖 Web UI 常驻，断点经 Session Log 恢复（`dsh resume`）。

## 8. 灾备与恢复

- 编排层崩溃：无状态，重启即从 Workspace 文件恢复（无需修复）。
- 硬阻断恢复：暂停会话 → 导出 Session Log → 通知（追加预算/降级模型/人工接管）→ `dsh resume` 断点续跑。
- 底座数据：Workspace 全量 Git 管理；大文件走 MinIO/S3 + 引用计数。

## 9. 运维边界声明

- 当前版本非多租户、非 SaaS；运维对象为单/少量实验室实例。
- 多人协作经 Git 流 + 写锁，非实时共享会话（见 `architecture.md` 协作边界）。
