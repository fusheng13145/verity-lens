"""biomed 领域验证脚本：统计报告合规校验。

确定性校验，不依赖模型判断。用于：
- Layer1 Schema 校验之外的领域语义校验
- Layer3 科研正确性抽检
- 失败归因（METH/HYP）复核

用法（作为 sidecar tool）：
    from bundles.biomed.skills.biomed_stats.scripts.validate_report import validate
    ok, problems = validate(report)
"""
from __future__ import annotations

REQUIRED_FIELDS = ("comparison", "metric", "effect_size", "ci_95", "p_value", "test_used")

# 必报效应量相关的指标 -> 需要 CI
NEEDS_CI_METRICS = {
    "mean_difference",
    "cohens_d",
    "odds_ratio",
    "risk_ratio",
    "hazard_ratio",
    "auc",
}


def validate(report: dict) -> tuple[bool, list[str]]:
    """校验一份统计报告是否满足生物医学报告规范。"""
    problems: list[str] = []

    if not isinstance(report, dict):
        return False, ["报告必须是对象"]

    for field in REQUIRED_FIELDS:
        if field not in report or report[field] is None:
            problems.append(f"缺少必填字段: {field}")

    if problems:
        return False, problems

    # 置信区间必须是 [下界, 上界] 且下界 <= 上界
    ci = report.get("ci_95")
    if isinstance(ci, (list, tuple)):
        if len(ci) != 2:
            problems.append("ci_95 必须是长度为 2 的数组")
        elif ci[0] is None or ci[1] is None:
            problems.append("ci_95 不得为 null")
        elif float(ci[0]) > float(ci[1]):
            problems.append("ci_95 下界不得大于上界")
    else:
        problems.append("ci_95 必须是数组")

    p = report.get("p_value")
    if p is not None and not (0.0 <= float(p) <= 1.0):
        problems.append(f"p_value 越界（应在 0–1）: {p}")

    metric = str(report.get("metric") or "")
    if metric in NEEDS_CI_METRICS and (not ci or ci[0] is None):
        problems.append(f"指标 {metric} 必须报告 95% 置信区间")

    return (not problems), problems
