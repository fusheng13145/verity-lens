# 工具调用规范

**目的**：明确 Skill / MCP / Sidecar 三类"工具"的边界与选型决策，落实 Agent 应用开发的"工具调用"思想。错误的归属会导致能力重复、维护翻倍。

## 1. 决策矩阵

| 能力类型 | 归属 | 判断依据 | 示例 |
|----------|------|----------|------|
| 方法论约束/流程规范 | **DSH Skill** | 影响模型"怎么想/怎么写"，需模型理解遵循 | IMRAD 结构、CONSORT、文献综述结构 |
| 结构化查询/跨系统对接 | **MCP Server** | 外部服务长期运行、多客户端、标准协议 | OpenAlex/PubMed、HPC 状态 |
| 确定性计算/长任务 | **Sidecar Tool** | 无歧义算法、可能耗时、需资源隔离 | 统计检验、功效分析、分子对接、图像分析 |
| 一次性脚本/领域参考 | **Skill 附带文件** | 模型偶尔参考的小脚本/模板 | 数据清洗示例、配色、LaTeX 模板 |

## 2. 判断口诀

- 需模型**阅读并理解** → Skill（SKILL.md 给人/模型看）
- 需模型**调用外部系统** → MCP（标准协议连接外部服务）
- 不需模型理解、只给**结果** → Sidecar Tool（确定性黑盒）

## 3. 注册方式（经 HAL，不直接依赖底座）

- Skill：`hal.register_skills([...])`，目录含 `SKILL.md` + 引用文件，热加载。
- MCP：`hal.declare_mcp_servers(config)`，声明在 `bundles/*/mcp/*.yml` 或 `sidecar/mcp/`。
- Sidecar Tool：`hal.register_tools([ToolSpec])`，ToolSpec 含 `input_schema/output_schema`，确定性实现。

## 4. 确定性工具清单（Sidecar）

| 工具 | 输入 | 输出 | 说明 |
|------|------|------|------|
| stat_test | 数据 + 检验类型 | p/effect_size/ci_95/test | 数值复算，禁止模型自算 |
| power_analysis | mode(prior/post)/design/effect_size/α/n | required_n/power/underpowered | 失败归因复核（METH 功效不足须给复算证据） |
| doi_verify | DOI | exists/metadata_match | 引用有效性 ≥95% |
| hpc_submit | 命令+资源 | job_id/status_endpoint | 长任务远程提交+轮询（未实现） |
| desensitize | 原始数据 | 脱敏数据 | k-匿名/PHI/DP(ε=1.0) |

## 5. 安全约束

- 敏感数据绝不进模型上下文（`never_in_context`：患者身份/未发表数据/密钥/内部评审）。
- 子代理权限按 `config/subagent_policy.yaml` 隔离；检索类禁写。
- 所有被引用数值结论 MUST 经确定性工具复核，提示词不产出最终统计值。

## 6. 反模式

- 把"确定性计算"写进 Skill 让模型执行 → 应 Sidecar。
- 把"外部查询"硬编码进提示词 → 应 MCP。
- 在多个 Bundle 重复实现同一验证脚本 → 提到通用 `skills/` 层。
