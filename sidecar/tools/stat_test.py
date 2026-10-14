"""Sidecar 工具：统计检验（确定性）。

工程纪律（design-blueprint.md §2.8 / tool-calling.md）：
- 所有被报告的数值（p 值、效应量、置信区间）必须由本工具计算，模型不得自行产出；
- 相同输入必须得到相同输出（确定性黑盒）；
- 依赖缺失时给出明确错误，而非静默返回。
"""
from __future__ import annotations

import math

import numpy as np
from scipy import stats  # type: ignore

TOOL_SPEC = {
    "name": "stat_test",
    "description": "统计检验：两组比较，返回 p 值、效应量(Cohen's d)、95% 置信区间",
    "input_schema": {
        "type": "object",
        "properties": {
            "group_a": {"type": "array", "items": {"type": "number"}},
            "group_b": {"type": "array", "items": {"type": "number"}},
            "test": {"type": "string", "enum": ["t-test", "welch", "mann-whitney"]},
            "alpha": {"type": "number", "default": 0.05},
        },
        "required": ["group_a", "group_b"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "metric": {"type": "string"},
            "mean_difference": {"type": "number"},
            "effect_size": {"type": "number"},
            "ci_95": {"type": "array", "items": {"type": "number"}},
            "p_value": {"type": "number"},
            "test_used": {"type": "string"},
            "significant": {"type": "boolean"},
            "n_a": {"type": "integer"},
            "n_b": {"type": "integer"},
        },
    },
}


def _cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """Cohen's d（合并标准差）。"""
    n_a, n_b = len(a), len(b)
    if n_a + n_b <= 2:
        return float("nan")
    pooled_var = (
        ((n_a - 1) * np.var(a, ddof=1)) + ((n_b - 1) * np.var(b, ddof=1))
    ) / (n_a + n_b - 2)
    pooled_sd = math.sqrt(float(pooled_var))
    if pooled_sd == 0:
        return float("nan")
    return float((np.mean(a) - np.mean(b)) / pooled_sd)


def _ci_mean_diff(a: np.ndarray, b: np.ndarray, alpha: float) -> list[float]:
    """均值差 (a-b) 的 95% 置信区间（Welch）。"""
    n_a, n_b = len(a), len(b)
    mean_diff = float(np.mean(a) - np.mean(b))
    se = math.sqrt(float(np.var(a, ddof=1) / n_a + np.var(b, ddof=1) / n_b))
    if se == 0:
        return [mean_diff, mean_diff]
    df = (np.var(a, ddof=1) / n_a + np.var(b, ddof=1) / n_b) ** 2 / (
        (np.var(a, ddof=1) / n_a) ** 2 / (n_a - 1)
        + (np.var(b, ddof=1) / n_b) ** 2 / (n_b - 1)
    )
    t_crit = float(stats.t.ppf(1 - alpha / 2, df))
    return [mean_diff - t_crit * se, mean_diff + t_crit * se]


def run(group_a, group_b, test: str = "t-test", alpha: float = 0.05) -> dict:
    """执行两组比较检验，返回可报告结构化结果。"""
    a = np.asarray(group_a, dtype=float)
    b = np.asarray(group_b, dtype=float)
    if len(a) < 2 or len(b) < 2:
        raise ValueError("每组至少需要 2 个样本")

    if test == "mann-whitney":
        stat, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        return {
            "metric": "rank_biserial",
            "mean_difference": float(np.mean(a) - np.mean(b)),
            "effect_size": None,  # 非参数：不报告 Cohen's d
            "ci_95": [None, None],
            "p_value": float(p),
            "test_used": "mann-whitney",
            "significant": bool(p < alpha),
            "n_a": len(a),
            "n_b": len(b),
        }

    equal_var = test == "t-test"
    t_stat, p = stats.ttest_ind(a, b, equal_var=equal_var)
    return {
        "metric": "mean_difference",
        "mean_difference": float(np.mean(a) - np.mean(b)),
        "effect_size": _cohens_d(a, b),
        "ci_95": _ci_mean_diff(a, b, alpha),
        "p_value": float(p),
        "test_used": "t-test" if equal_var else "welch",
        "significant": bool(p < alpha),
        "n_a": len(a),
        "n_b": len(b),
    }
