# 协作与制品管理

> 对应设计蓝图 `docs/design-blueprint.md` §2.5。VerityLens 的协作以**制品（文件与实验产物）
> 为单位，而非会话**——会话永远是单人的，协作通过 Git + 制品写锁 + 审阅批注完成。

## 1. 协作边界（明确声明）

| 场景 | 支持 | 机制 |
|------|------|------|
| 单人单项目 | 完全支持 | 原生 |
| 小组并行研究（不同假设/实验分支） | 支持 | Git 分支 = 假设分支：`hypothesis/H1`、`hypothesis/H2` 各自推进，merge 前过 `vl gate` |
| 多人共同写作（串行交接） | 支持 | 制品写锁 + Git PR + review |
| 多人同时编辑同一文件 | **不支持（非目标）** | — |
| 多人共享同一 Agent 会话 | **不支持（非目标）** | — |

## 2. 制品写锁（vl lock）

防止写作阶段并发覆盖（蓝图 E15）。锁写在 `RESEARCH.yaml` 的 `locks` 字段，超时自动失效（默认 48h，防死锁 E4）。

```bash
vl lock acquire manuscript --holder researcher_b --ttl 86400   # 获取 manuscript 写锁（1 天）
vl lock check --json                                         # 机器可读的当前锁状态
vl lock release manuscript --holder researcher_b             # 释放
```

- 同一制品已有他人未过期锁时，`acquire` 被拒绝（退出码 2，先到先得）。
- `pre_session` 钩子在 `writing` 阶段检测：若他人持有写锁，则以**只读模式**启动（退出码 4）。

> ⚠️ pre_session 钩子的写锁自动检查需要改动会话启动钩子，已在本仓库 `orchestrator/hooks/pre_session.sh`
> 预留第④步注释位。若需启用，请将 `docs/collab.md` 末尾的片段粘贴到该钩子第④步。

## 3. Git 假设分支协作流（vl branch）

并行推进不同假设时，每个假设一条分支，互不干扰；合回 main 前强制就绪检查。

```bash
vl branch create H1          # 从 main 切出 hypothesis/H1 分支
# ……在该分支推进实验 / 写作……
vl branch status             # 查看就绪状态（无未处理 failed + 门禁通过？）
vl branch merge              # 就绪后 --no-ff 合并回 main
```

`vl branch merge` 的硬约束（详见 `orchestrator/collab.py`）：
1. 不存在停留在临时态 `failed` 的实验（否则先 `vl loop` 回流）；
2. 当前阶段门禁通过（`vl gate <current_phase>`）；
3. 当前不在 `main`/`master`。

## 4. 分支保护建议（Git 服务端）

- `main` 设为受保护分支：禁止直接 push，必须经 PR + review。
- 假设分支允许各自推送，但合入 main 需 code review（含对 failure_ledger 与假设树变更的审阅）。
- 大文件（原始数据、模型权重）不入库：走对象存储（MinIO/S3）+ 引用，Git 仅存小文件与元数据。

## 5. 制品归属与审计

每个实验目录附带 `manifest.yaml`：记录模型版本、token 消耗、输入数据 hash、随机种子、执行环境。
`make reproduce` 依赖 manifest 完成从 raw 到 figures 的复现。失败登记簿与 refuted 节点强制留痕，
构成不可篡改的科研诚信证据链。

## 6. pre_session 钩子写锁检查片段（可选启用）

`orchestrator/hooks/pre_session.sh` 第④步当前为预留注释。若要在会话启动前自动按写锁
以只读模式启动，可将以下片段粘贴到该步：

```bash
# ④ 写锁检查（写作阶段）：若他人持有 manuscript 写锁，则只读模式启动
if [ "${PHASE}" = "writing" ]; then
  LOCK_JSON="$(vl lock check --json 2>/dev/null)"
  if [ -n "${LOCK_JSON}" ]; then
    HELD_BY="$(printf '%s' "${LOCK_JSON}" | python -c "import sys,json; d=json.load(sys.stdin); print(','.join(e.get('holder','') for e in d.get('active',{}).values()))" 2>/dev/null)"
    if [ -n "${HELD_BY}" ] && [ "${HELD_BY}" != "${VL_USER:-}" ]; then
      echo "[READ_ONLY] 写锁由 ${HELD_BY} 持有（非当前用户 ${VL_USER:-未设置}），以只读模式启动"
      exit 4
    fi
  fi
fi
```

> 该片段会修改会话启动时的自动执行行为；启用前请确保团队已约定 `VL_USER` 环境变量
> （标识当前会话用户）的注入方式。
