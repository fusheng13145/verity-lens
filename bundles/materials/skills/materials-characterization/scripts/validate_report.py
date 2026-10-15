"""materials 领域验证脚本：表征报告合规校验。

确定性校验，不依赖模型判断。用于：
- Layer1 Schema 校验之外的领域语义校验
- Layer3 科研正确性抽检
- 失败归因（METH 类）复核

用法（作为 sidecar / 脚本）：
    from bundles.materials.skills.materials_characterization.scripts.validate_report import validate
    ok, problems = validate(report)
"""
from __future__ import annotations

REQUIRED_FIELDS = (
    "sample_id",
    "method",
    "value",
    "uncertainty",
    "unit",
    "instrument",
    "n_repeats",
)

# 至少须报告不确定度的指标类型（与 biomed NEEDS_CI 思路一致）
NEEDS_UNCERTAINTY = {"value"}

MIN_REPEATS = 3


def validate(report: dict) -> tuple[bool, list[str]]:
    """校验一份材料表征报告是否满足报告规范。"""
    problems: list[str] = []

    if not isinstance(report, dict):
        return False, ["报告必须是对象"]

    for field in REQUIRED_FIELDS:
        if field not in report or report[field] is None:
            problems.append(f"缺少必填字段: {field}")

    if problems:
        return False, problems

    # 数值字段合法性
    try:
        value = float(report["value"])
    except (TypeError, ValueError):
        problems.append(f"value 不是合法数值: {report['value']!r}")
        value = None

    try:
        uncertainty = float(report["uncertainty"])
    except (TypeError, ValueError):
        problems.append(f"uncertainty 不是合法数值: {report['uncertainty']!r}")
        uncertainty = None

    if value is not None and uncertainty is not None:
        if uncertainty < 0:
            problems.append("uncertainty 不得为负")
        # 不确定度大于量值本身通常意味着测量无意义
        if uncertainty > abs(value) and abs(value) > 0:
            problems.append(
                f"uncertainty({uncertainty}) 大于量值({value})，请复核测量"
            )

    # 重复样本量
    n = report.get("n_repeats")
    try:
        n_int = int(n)
    except (TypeError, ValueError):
        problems.append(f"n_repeats 不是合法整数: {n!r}")
        n_int = None
    if n_int is not None and n_int < MIN_REPEATS:
        problems.append(f"n_repeats({n_int}) < {MIN_REPEATS}，重复测量不足")

    # 单位不得为空字符串
    unit = str(report.get("unit") or "").strip()
    if not unit:
        problems.append("unit 不得为空")

    method = str(report.get("method") or "").strip().lower()
    if not method:
        problems.append("method 不得为空")

    return (not problems), problems
