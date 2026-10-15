# 数据设计与 Schema

**目的**：定义系统的"记忆与上下文管理"载体——长期记忆（项目状态/假设/失败）、短期上下文（RAG 注入）、可复现元数据。所有状态以声明式文件落盘，便于审计与恢复。

## 1. Workspace 文件清单（Git 管理）

| 文件 | 职责 | 写入者 |
|------|------|--------|
| `RESEARCH.yaml` | 项目元数据/阶段/审批/写锁/预算 | 人 + 统计脚本 |
| `docs/hypothesis_tree.json` | 假设树（含 refuted/revised + 证据链） | 底座(经 HITL) |
| `docs/failure_ledger.json` | 失败登记簿 | 底座起草 + 人批准 |
| `experiments/exp_NNN.yaml` | 实验配置与状态 | 底座 + 人 |
| `analysis/summary.md`、`figures/`、`manuscript/` | 分析与产出 | 底座 |
| `lessons.md` | 失败模式库（由 ledger 渲染） | 自动 |
| `manifest.yaml`（每实验） | 可复现元数据 | 自动 |

## 2. RESEARCH.yaml（完整字段）

```yaml
project_id: "proj_20261014_001"
discipline: "biomed"
research_question: "AlphaFold2 预测的构象差异能否作为 AD 早期生物标志物？"
current_phase: "experiment"
approvals:
  question: { approved_by: "researcher_pi", approved_at: "2026-10-15T10:00:00Z", note: "H1/H2 通过评审" }
  writing:  { approved_by: null, approved_at: null, note: null }
locks: {}                                # 写作阶段写锁
degraded_features: []                    # 底座不支持的特性（HAL 探测写入）
hypotheses:
  - { id: H1, status: testing, confidence: 0.55 }
  - { id: H2, status: proposed, confidence: null }
model_config: { primary: "deepseek-chat-v4-pro", fallback: "deepseek-chat-v4-flash" }
token_budget:
  total:      { cap: 500000, used: 42300 }
  per_phase:  { literature:{cap:100000,used:42300}, question:{cap:50000,used:0},
                experiment:{cap:200000,used:0}, analysis:{cap:100000,used:0}, writing:{cap:50000,used:0} }
```

## 3. hypothesis_tree.json（扩展字段）

```json
{
  "id": "H1.1",
  "parent_id": "H1",
  "type": "hypothesis",
  "content": "AD 组与对照组的 Aβ 寡聚体构象 RMSD 差异在 n=250 下可检出（d≥0.5）",
  "status": "testing",
  "confidence": 0.45,
  "children": ["E3"],
  "provenance": { "derived_from": "H1", "justified_by": ["F-001"], "version": 4 }
}
```
**约束**：`parent_id` 不得成环；`refuted`/`revised` 节点必带 `provenance.justified_by` 指向 failure_ledger 条目。

## 4. failure_ledger.json（失败登记簿）

```json
{
  "entries": [{
    "id": "F-001",
    "experiment_id": "exp_001",
    "hypothesis_id": "H1",
    "phase": "experiment",
    "detected_at": "2026-10-20T14:00:00Z",
    "classification": { "category": "METH", "code": "METH-POWER-LOW", "confidence": 0.8,
                        "rationale": "p=0.12, d=0.35, power=0.41<0.8" },
    "evidence": [ { "path": "data/processed/exp_001/stats_report.json", "locator": "$.power" } ],
    "reported_metrics": {
      "group_stats": { "mean_a": 12.4, "sd_a": 3.1, "n_a": 100,
                       "mean_b": 11.3, "sd_b": 2.9, "n_b": 100 },
      "test": "welch", "p_value": 0.12, "effect_size": 0.35,
      "n_per_group": 100, "power": 0.41
    },
    "decision": { "type": "revise_experiment", "action": "exp_002",
                  "changes": ["num_samples: 100 -> 250"], "approved_by": "researcher_pi" },
    "lesson": "小样本效应量可能被高估；设计前先做功效分析",
    "tags": ["power-analysis"]
  }]
}
```

**`reported_metrics`（Phase 4e 新增，可选）**：条目主张的关键数值，是 `failure_loop.verify_with_sidecar`
做确定性复算的唯一输入——没有它，复算只能返回 `skipped`（不算"已验证"）。

| 字段 | 复算方式 |
|------|----------|
| `group_stats`（mean/sd/n ×2） | **完整复算**：stat_test 重算 p、效应量、95% CI |
| `effect_size` + `ci_95` | **相容性交叉复算**：由 CI 反推 se → z → 复算 p 与主张值比对（容差 max(0.002, 10%·p)） |
| `effect_size` + `n_per_group`（± `power`） | power_analysis 复算事后功效（容差 0.02），并强制附带 `post_hoc_warning` 科研诚信提示 |

对不上时 `verify_with_sidecar` 返回 `status=mismatch`，METH/HYP 归因必须先解释差异，不得直接进入决策落盘。

## 5. experiment.yaml（关键字段）

```yaml
status: "concluded_failed"   # 状态机：draft→running→completed / failed(临时)→concluded_failed|suspended|abandoned
retry_count: 1
failure_ref: "F-001"         # 关联失败登记簿（终态必填）
superseded_by: "exp_002"     # 被修订实验接替
```

## 6. 上下文/记忆分层

- **长期记忆**：上述声明式文件（人/Agent 可审计、可复现）。
- **短期上下文**：RAG 侧车按 `max_context_tokens_per_turn=4000` 注入，超预算转 `citation_only_mode`；会话缓存 LRU 50 条，session 级 TTL。
- **轨迹记忆**：底座 Session Log（`.dsh/`），支持分叉/回放（HAL 能力）。

## 7. Schema 校验（CI 强制，Layer1）

校验项：字段齐全、枚举合法、无循环引用、路径存在、evidence 指针有效、refuted 节点必附证据链、abandoned 必附 failure_ledger 引用。工具：`pydantic v2` + `jsonschema`。通过标准 100%。
