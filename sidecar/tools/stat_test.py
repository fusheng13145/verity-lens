"""Sidecar 工具：统计检验占位。

注册为底座 tool（详见 docs/tool-calling.md）。
Phase 1 实现 t/ANOVA/非参数/多重校正，输出 {p_value, effect_size, ci_95, test_used}。
"""
from __future__ import annotations


TOOL_SPEC = {
    "name": "stat_test",
    "description": "统计检验：组间比较，返回 p 值、效应量、95% 置信区间",
    "input_schema": {
        "type": "object",
        "properties": {
            "data": {"type": "array", "items": {"type": "number"}},
            "test": {"type": "string", "enum": ["t-test", "anova", "mann-whitney"]},
        },
        "required": ["data", "test"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "p_value": {"type": "number"},
            "effect_size": {"type": "number"},
            "ci_95": {"type": "array", "items": {"type": "number"}},
            "test_used": {"type": "string"},
        },
    },
}


def run(data, test: str) -> dict:
    # Phase 1 实现；占位返回结构
    return {"p_value": None, "effect_size": None, "ci_95": [None, None], "test_used": test}
