# 测试与验收

**目的**：定义分层质量门禁，覆盖 Schema、轨迹、科研正确性与底座契约。失败闭环纳入回归。

## 1. 四层测试体系

| 层 | 内容 | 自动化 | 通过标准 |
|----|------|--------|----------|
| L1 Schema 校验 | 全部声明式文件 schema 校验（每次 commit） | 全自动 | 100% 通过、零警告 |
| L2 Golden 轨迹 | 固定输入→轨迹比对；HITL 触发；子代理权限；**含 METH/HYP 失败闭环用例各 3 例**（每日 CI + 底座升级） | 全自动 | 事件序列 edit distance ≤2 |
| L3 科研正确性 | 统计值 sidecar 复算一致；DOI 引用 ≥95% 可验证；图表数据一致；**每条 refuted 假设均有完整证据链、每条 failed 实验均有 failure_ledger 条目**（周级） | 半自动 | 数值 100% / 引用 ≥95% |
| L4 HAL 契约 | HAL 接口行为 + 能力探测准确性 + 降级路径（底座升级时） | 全自动 | 100% 通过 |

## 2. 检查项明细

- **L1**：RESEARCH.yaml 强制字段齐全；hypothesis_tree 节点合法无环；experiment success_criteria 格式；failure_ledger evidence 指针有效；refuted 节点必附 `justified_by`；abandoned 必附 failure_ref。
- **L2**：阶段顺序正确；HITL 门禁正确触发/等待；检索类子代理无写操作；Session Log 无未验证断言；失败闭环用例走通"归因→决策→假设修订"。
- **L3**：p 值 sidecar 复算容差 ±1e-6；引用 HTTP 200 + 元数据匹配；图表与原始文件数值一致；实验参数（种子/版本）在 Session Log 可追溯。
- **L4**：HAL 接口签名/行为一致；`capabilities()` 与实测一致；降级路径在特性 false 时不抛异常。

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
