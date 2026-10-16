# 协作与制品管理

> 对应设计蓝图 `docs/design-blueprint.md` §2.5。verity-lens 的协作以**制品（文件与实验产物）
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

---

## 7. 协作模型重评估框架（数据驱动，待真实反馈）

> 蓝图第七部分将"协作模型按实际需求重新评估"列为 Phase 4 退出项，并明确**不预设方案、待真实协作反馈**。
> 本节把"重评估"从一句口号变成**可量化、可执行的流程**：先诚实盘点当前模型真实状态，再定义要采集什么信号、
> 达到什么阈值才触发模型变更。最终是否调整协作模型，**仍由真实团队（1–10 人）的使用数据决定**，本框架不做决策。

### 7.1 当前协作模型真实状态（三档分级）

| 能力 | 机制 | 当前状态 | 说明 |
|------|------|----------|------|
| 假设分支并行 | `vl branch create/merge/status` + `check_merge_readiness` | ✅ 已实现并强制 | merge 前强制无未处理 failed + 阶段门禁；`--no-ff` |
| 制品写锁（手动） | `vl lock acquire/release/check` → `RESEARCH.yaml.locks` | ✅ 已实现；先到先得、超时 48h 失效 | 冲突拒绝（退出码 2） |
| 写锁会话期自动只读 | `pre_session.sh` 第④步 | ⚠️ **已实现但默认未启用** | 需手动粘贴片段 + 团队约定 `VL_USER` 注入；当前互斥靠人工纪律 |
| 制品归属与审计 | `manifest.yaml` + `failure_ledger` + refuted 留痕 | ✅ 已实现 | per-experiment 证据链 |
| 分支保护（main 需 PR） | Git 服务端配置 | ⚠️ **建议项，本仓库不强制** | 依赖外部 Git 平台设置 |
| 多用户身份 | `holder` 自由字符串 + `VL_USER` 环境变量 | ⚠️ **口头约定，无强制身份/认证** | 错配会导致锁语义失效 |
| 多人共享同一 Agent 会话 | — | ❌ 明确非目标 | 会话恒为单人 |
| 多人同时编辑同一文件 | — | ❌ 明确非目标 | 需串行交接 |

### 7.2 真实已知局限（gap，来自代码/文档核查）

1. **写锁会话期强制检查未启用**：`docs/collab.md` 自承 `pre_session` 第④步为"预留注释位"，默认不生效。
   即"并行写作强制写锁"目前依赖使用者自觉，不是系统强制。
2. **身份是弱约定**：锁持有者仅为自由字符串，`VL_USER` 由团队口头约定注入；无认证/身份服务，
   错配会使写锁互斥语义失真（A 误标自己为 B 即可绕过）。
3. **共享会话 / 同文件并发是硬缺口**：若真实团队确实需要"多人同会话"或"同文件并发编辑"，
   当前模型明确不支持，需重新设计（非小修）。
4. **RAG 文献库共享的并发写入协议未定义**：`sidecar/rag` 支持共享索引，但多人同时归档/检索的写入一致性无约定。
5. **无内建审阅批注结构**：审阅依赖 Git PR review，项目内无结构化的 review annotation（如针对某假设/某实验的批注留痕）。
6. **无角色/权限**：谁能 merge、谁能批准假设（refuted/revised）无内建角色区分，全靠 Git 平台权限。

### 7.3 重评估待采集信号（何时才"有数据"）

| 信号 | 含义 | 采集方式（建议） | 来源 |
|------|------|----------------|------|
| 锁竞争事件 | 同一制品并发 acquire 被拒 / 超时未 release | opt-in 埋点（`vl lock` 记 audit 行） | 写锁 |
| 写锁绕过实例 | 未持锁却改了被锁制品 | Git diff 比对 holder vs committer | 写锁 |
| 假设分支数量 / 合并周期 | 并行度与合回延迟 | `git` 日志统计 | 分支流 |
| merge 冲突次数 | 并行写作/实验的真实冲突 | Git 日志 | 分支流 |
| 身份误配 | `VL_USER` 与 committer 不一致 | opt-in 埋点 | 身份 |
| 共享会话/同文件并发请求 | 团队是否真的需要非目标能力 | 人工访谈 / 使用日志 | 非目标项 |
| RAG 并发写入冲突 | 共享文献库一致性问题 | opt-in 埋点 | RAG |

> 埋点为 **opt-in**：默认关闭，仅当团队同意观测时开启，避免把"协作监控"强加给单人用户。

### 7.4 触发模型变更的决策阈值（示例，非承诺）

仅当以下**任一类**被真实数据证实，才启动模型变更设计（届时仍按蓝图"不预设方案"从痛点出发）：

- **写锁不可靠**：opt-in 数据显示锁竞争事件频繁且多次出现"绕过实例" → 需把会话期强制检查设为默认 + 强化身份。
- **非目标能力被真实需要**：多团队明确需要"共享会话"或"同文件并发"且频次高 → 需重新评估协作边界（§2.5.1）。
- **RAG 并发冲突频发**：共享文献库出现写入冲突/索引损坏 → 需定义并发写入协议或加锁。
- **审阅留痕缺失导致返工**：人工访谈显示 review 信息散落 Git、难追溯 → 需内建 review annotation。

### 7.5 候选演进方向（仅列举，未经真实数据验证，非承诺方案）

若触发变更，可能考虑（不预设、不从列表里直接选）：细粒度锁（按 section 而非整制品）、
共享会话模式、内建 review 批注结构、轻量身份/角色服务、RAG 写入一致性协议。
**这些一律待 7.3 信号 + 7.4 阈值命中后才进入设计。**

### 7.6 下一步

1. 决定是否为写锁/分支流加 **opt-in 埋点**（见 7.3），使信号可量化。
2. 在 1–10 人真实团队中使用 verity-lens，按 7.3 采集信号。
3. 信号命中 7.4 阈值 → 启动模型变更设计（从真实痛点出发，不预设方案）。
