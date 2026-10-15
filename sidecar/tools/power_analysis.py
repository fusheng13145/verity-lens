"""Sidecar 工具：功效分析（确定性）。

用途（design-blueprint.md §2.7 / tool-calling.md）：
- 先验功效：给定效应量、α、目标功效 → 每组所需样本量；
- 事后功效：给定观测效应量与样本量 → 实际功效（用于 METH 类失败归因："功效不足"必须可复算）；
- 与 stat_test 一样，相同输入必须得到相同输出，模型不得自行产出功效数值。

方法学口径：正态近似（normal approximation），双侧检验。
- 两样本：n_per_group = 2 (z_{1-α/2} + z_{1-β})² / d²
- 单样本：n_total    = (z_{1-α/2} + z_{1-β})² / d²
- 功效：power = Φ(λ − z_{1-α/2}) + Φ(−λ − z_{1-α/2})，
  其中两样本 λ = |d|·sqrt(n/2)、单样本 λ = |d|·sqrt(n)

注意（科研诚信）：事后功效只是观测数据的性质，不等于 p 值的补充证据；
工具输出中 `post_hoc_warning` 字段固定给出该提示，避免被当作"事后检验正当性"。
"""
from __future__ import annotations

import math

from scipy import stats  # type: ignore

TOOL_SPEC = {
    "name": "power_analysis",
    "description": "功效分析：先验样本量 / 事后功效（两样本或单样本，正态近似）",
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["prior", "post"], "default": "prior"},
            "design": {"type": "string", "enum": ["two-sample", "one-sample"],
                       "default": "two-sample"},
            "effect_size": {"type": "number", "description": "标准化效应量 Cohen's d（绝对值）"},
            "alpha": {"type": "number", "default": 0.05},
            "target_power": {"type": "number", "default": 0.8},
            "n_per_group": {"type": "integer", "minimum": 2,
                            "description": "mode=post（两样本）时必填"},
            "n_total": {"type": "integer", "minimum": 2,
                        "description": "mode=post（单样本）时必填"},
        },
        "required": ["effect_size"],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string"},
            "design": {"type": "string"},
            "effect_size": {"type": "number"},
            "alpha": {"type": "number"},
            "target_power": {"type": "number"},
            "required_n": {"type": "integer"},
            "power": {"type": "number"},
            "underpowered": {"type": "boolean", "description": "实际功效 < 目标功效"},
            "method": {"type": "string"},
            "post_hoc_warning": {"type": "string"},
        },
    },
}

POST_HOC_WARNING = (
    "事后功效是观测数据的性质，不能替代 p 值，也不构成事后检验的正当性依据；"
    "解释须谨慎（不要把功效当作非显著结果的免责理由）。"
)


def _ncp(d: float, n_per_group: float, design: str) -> float:
    """非中心化参数（两样本用 n/2，单样本用 n）。"""
    return abs(d) * math.sqrt(n_per_group / 2 if design == "two-sample" else n_per_group)


def required_n(effect_size: float, alpha: float = 0.05, target_power: float = 0.8,
               design: str = "two-sample") -> int:
    """达到目标功效所需样本量（两样本=每组，单样本=总数）。"""
    d = abs(float(effect_size))
    if d <= 0:
        raise ValueError("effect_size 必须为非零（标准化效应量）")
    if not 0 < alpha < 1:
        raise ValueError("alpha 必须在 (0,1) 内")
    if not 0 < target_power < 1:
        raise ValueError("target_power 必须在 (0,1) 内")
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(target_power)
    base = ((z_a + z_b) ** 2) / (d ** 2)
    # 两样本：λ = d·sqrt(n/2) ≥ z_a+z_b  ⇒  n_per_group ≥ 2·base
    # 单样本：λ = d·sqrt(n)   ≥ z_a+z_b  ⇒  n_total    ≥ base
    n = math.ceil(base) if design == "one-sample" else math.ceil(2 * base)
    return max(n, 2)


def achieved_power(effect_size: float, n_per_group: int, alpha: float = 0.05,
                   design: str = "two-sample") -> float:
    """给定效应量与样本量的实际功效（双侧，正态近似）。"""
    d = abs(float(effect_size))
    if d <= 0:
        raise ValueError("effect_size 必须为非零（标准化效应量）")
    if n_per_group < 2:
        raise ValueError("n_per_group 必须 >= 2")
    z_a = stats.norm.ppf(1 - alpha / 2)
    lam = _ncp(d, n_per_group, design)
    power = stats.norm.cdf(lam - z_a) + stats.norm.cdf(-lam - z_a)
    return float(min(1.0, max(0.0, power)))


def run(mode: str = "prior", design: str = "two-sample", effect_size: float = 0.0,
        alpha: float = 0.05, target_power: float = 0.8,
        n_per_group: int | None = None, n_total: int | None = None) -> dict:
    """功效分析入口。

    mode=prior：返回达到 target_power 所需样本量（required_n）；
    mode=post ：返回观测样本量下的实际功效（power），并标注 underpowered。
    """
    if mode not in ("prior", "post"):
        raise ValueError("mode 须为 prior 或 post")
    if design not in ("two-sample", "one-sample"):
        raise ValueError("design 须为 two-sample 或 one-sample")

    out: dict = {
        "mode": mode,
        "design": design,
        "effect_size": abs(float(effect_size)),
        "alpha": float(alpha),
        "target_power": float(target_power),
        "method": "normal approximation (two-sided)",
    }

    if mode == "prior":
        n_req = required_n(effect_size, alpha, target_power, design)
        out["required_n"] = n_req
        out["power"] = achieved_power(
            effect_size, n_req if design == "two-sample" else n_req,
            alpha, design,
        )
        out["underpowered"] = False
        return out

    # post hoc
    n = n_per_group if design == "two-sample" else n_total
    if n is None:
        raise ValueError("mode=post 时必须提供 n_per_group（两样本）或 n_total（单样本）")
    power = achieved_power(effect_size, int(n), alpha, design)
    out["power"] = power
    out["required_n"] = required_n(effect_size, alpha, target_power, design)
    out["underpowered"] = bool(power < target_power)
    out["post_hoc_warning"] = POST_HOC_WARNING
    return out


if __name__ == "__main__":
    import sys

    from sidecar.tools._stdio import serve

    sys.exit(serve(run))
