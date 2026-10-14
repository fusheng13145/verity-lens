"""Sidecar 工具：敏感数据脱敏占位。

k-匿名 / PHI 屏蔽 / 差分隐私（ε=1.0）。脱敏管道详见 design-blueprint.md §2.8.2。
敏感数据永不进入模型上下文（never_in_context 清单见 docs/tool-calling.md）。
"""
from __future__ import annotations

TOOL_SPEC = {
    "name": "desensitize",
    "description": "对原始敏感数据执行脱敏（k-匿名 / PHI 屏蔽 / 差分隐私）",
    "input_schema": {
        "type": "object",
        "properties": {
            "source": {"type": "string"},
            "method": {"type": "string", "enum": ["k_anonymity", "mask_phi", "dp_aggregate"]},
        },
        "required": ["source", "method"],
    },
    "output_schema": {"type": "object", "properties": {"output_path": {"type": "string"}}},
}


def run(source: str, method: str) -> dict:
    # Phase 3 实现
    return {"output_path": f"{source}.desensitized"}
