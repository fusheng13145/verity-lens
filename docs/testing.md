# 测试与验收

**目的**：定义分层质量门禁，覆盖 Schema、轨迹、科研正确性与底座契约。失败闭环纳入回归。

## 1. 四层测试体系

| 层 | 内容 | 自动化 | 通过标准 |
|----|------|--------|----------|
| L1 Schema 校验 | 全部声明式文件 schema 校验（每次 commit） | 全自动 | 100% 通过、零警告 |
| L2 Golden 轨迹 | 固定输入→轨迹比对；HITL 触发；子代理权限；**含 METH/HYP 失败闭环用例各 3 例**（每日 CI + 底座升级） | 全自动 | 事件序列 edit distance ≤2 |
| L3 科研正确性 | 统计值 sidecar 复算一致；DOI 引用 ≥95% 可验证；图表数据一致；**每条 refuted 假设均有完整证据链、每条 failed 实验均有 failure_ledger 条目**（周级） | 半自动 | 数值 100% / 引用 ≥95% |
| L4 HAL 契约 | HAL 接口行为 + 能力探测准确性 + 降级路径（底座升级时） + **Sidecar 双通道边界保真**（stdio ↔ 进程内模块输出等价） | 全自动 | 100% 通过 |

## 2. 检查项明细

- **L1**：RESEARCH.yaml 强制字段齐全；hypothesis_tree 节点合法无环；experiment success_criteria 格式；failure_ledger evidence 指针有效；refuted 节点必附 `justified_by`；abandoned 必附 failure_ref。
- **L2**：阶段顺序正确；HITL 门禁正确触发/等待；检索类子代理无写操作；Session Log 无未验证断言；失败闭环用例走通"归因→决策→假设修订"；Bundle Golden（验证脚本输出逐字比对，防"悄悄放水"）。
- **L3**（`tests/correctness/`，Phase 4e 起非空）：p 值与 95% CI 的**统计自洽性**（由 CI 反推 z 复算 p）、组统计量的完整复算（与 scipy `ttest_ind_from_stats` 对齐）、功效样本量与经典值对照（d=0.5→63、d=0.2→393）、引用 HTTP 200 + 元数据匹配、图表与原始文件数值一致。
- **L4**：HAL 接口签名/行为一致；`capabilities()` 与实测一致；降级路径在特性 false 时不抛异常；**Sidecar 双通道边界保真**（`tests/integration/test_stdio_boundary.py`）：每个工具经 `python -m sidecar.tools.<x>` 子进程（HAL 真实调用路径）的输出，必须与编排层 `from sidecar.tools.x import run; run(**params)`（verify_with_sidecar 走的内部路径）逐字段等价——确保"关键数值必经确定性工具"在两种调用通道下产出完全一致。

> 复算口径提醒：`verify_with_sidecar` 返回 `skipped` 表示"无可复算数值"，**不等于已验证**；
> 返回 `mismatch` 表示条目数值对不上，METH/HYP 归因必须先解释差异。

## 3. 科研 Agent 验收维度总结

| 维度 | 标准 | 自动化 |
|------|------|--------|
| Schema 完整性 | 100% 字段齐全/类型正确 | 全自动 |
| 轨迹合理性 | edit distance ≤2 | 全自动 |
| 数值正确性 | 独立性工具复算一致 | 全自动 |
| 引用有效性 | ≥95% DOI 可验证 | 全自动 |
| 方法论合规 | 专家评审（如报告 CI） | 半自动 |
| 可复现性 | `make reproduce` 从 raw 到 figures 完全一致 | 全自动 |

## 4. CI 配置建议

```
commit:  make schema-check (L1)
daily:   make golden (L2)  +  correctness sample (L3 抽检)
upgrade: make hal-contract (L4) + golden
```
通过标准不降级；L3 专家评审为人工周会项，不阻塞合并但阻塞发布。
