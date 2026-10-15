# 容器沙箱与敏感数据治理

> 对应设计蓝图 `docs/design-blueprint.md` §2.8.2。本文说明科研代码执行沙箱的
> 安全基线、生成方式，以及敏感数据从采集到推理的全链路治理管道。

## 1. 沙箱是什么

Agent 在 `experiment` / `analysis` 阶段会生成并执行科研代码（统计、绘图、预处理）。
这些代码运行在 **强隔离容器** 中，而非直接在主环境执行，目的是把"模型可能写出危险代码"
的爆炸半径压到最小。

安全基线（`docker/sandbox-compose.yml`，由 `orchestrator/sandbox.py` 按项目渲染）：

| 控制项 | 设置 | 作用 |
|--------|------|------|
| 禁止提权 | `no-new-privileges:true` | 容器内无法 `sudo`/`setuid` 提权 |
| 能力收敛 | `cap_drop: [ALL]` + 仅 `cap_add: [CHOWN]` | 丢弃全部 Linux capabilities |
| 网络隔离 | `network_mode: "none"` | 默认不出网；需拉依赖时临时放开 |
| 只读根 | `read_only: true` + `tmpfs` | 根文件系统不可写，仅 `/tmp`、`/var/tmp` 可写 |
| 资源硬限 | `cpus:4 / memory:8g / pids:100` | 防资源耗尽型失控 |
| 卷挂载 | `data/raw` 只读，`processed/figures/...` 可写 | 原始数据不暴露给可写层 |

## 2. 生成方式

```bash
# 生成项目专属 compose（PROJECT_ID 内联，免去环境变量）
vl sandbox gen proj_20261014_001

# 仅校验安全基线是否符合最小要求（CI 可调用）
vl sandbox gen proj_20261014_001 --check
```

生成文件位于 `docker/sandbox-compose.<project_id>.yml`，可直接：

```bash
docker compose -f docker/sandbox-compose.proj_20261014_001.yml up --abort-on-container-exit
```

## 3. 敏感数据治理管道（五步）

科研数据常含 PHI（受保护健康信息）、未发表合作者数据、商业机密等。管道确保这类
数据**永不进入模型上下文**（蓝图 `never_in_context` 清单）：

```
① 原始敏感数据存 data/raw/（容器外，底座/HAL 无访问权限）
        │
② Sidecar 脱敏（k-匿名 / 字段屏蔽 / DP 聚合 ε=1.0）
        │   sidecar/security/desensitize.py
③ 脱敏版写入 data/processed/（沙箱与底座可读）
        │
④ Agent 仅基于脱敏数据推理（沙箱挂载 data/processed 为 rw，data/raw 为 ro）
        │
⑤ 涉及个体的结论必须经人工审核（HITL，不可自动外发）
```

`never_in_context` 清单：患者身份、未发表合作者数据、商业机密、API 密钥、机构内部评审信息。
任何脚本/提示词若尝试将以上信息注入上下文，应在提交前被正则扫描告警（见 `orchestrator/hooks`）。

## 4. 与编排层的关系

- 沙箱只负责"执行代码"，不持有项目状态；项目状态仍在 `RESEARCH.yaml` 等声明式文件中。
- 代码执行前需通过 pre_session 门禁链（`vl gate` / `vl budget` / `vl loop` / 写锁）。
- 失败代码执行（EXEC 类）按 `orchestrator/failure_loop.py` 走回流，沙箱本身无状态。
