#!/usr/bin/env bash
# pre_session hook：会话启动前的门禁链（详见 docs/interfaces.md / orchestration-flows.md）
# 任一环节阻塞即返回非 0，阻止底座会话启动。
set -euo pipefail

PHASE="${VL_CURRENT_PHASE:-literature}"

echo "[pre_session] 阶段=${PHASE}"

# ① 阶段门禁
vl gate "${PHASE}" || { echo "[BLOCKED] 阶段门禁未通过"; exit 2; }

# ② 预算硬阻断
vl budget check || { echo "[HARD_BLOCK] 预算超限"; exit 3; }

# ③ 失败回流检查
vl loop || { echo "[BLOCKED] 存在未处理 failed 实验/未批准回流"; exit 2; }

# ④ 写锁检查（写作阶段）
# ⑤ HAL 能力探测（由底座会话内部完成）

echo "[pre_session] 通过，允许启动"
