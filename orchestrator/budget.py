"""预算硬阻断评估（声明式、纯函数）。

从 ``RESEARCH.yaml`` 的 ``token_budget`` 读取 total / per_phase 用量，计算使用率，
判定是否硬阻断（已耗尽）或软告警（>=70%）。

逻辑原内联于 ``cli.py:cmd_budget``，抽出后便于单测复用，也呼应蓝图声称的
``orchestrator/budget.py`` 模块化（原审计 #3）。

设计纪律：
- 纯函数，输入为已加载的 project dict（由 ``gates.load_project`` 提供），不触碰 IO；
- 不依赖 ``hal``（依赖收敛：仅 ``bundle_loader`` 与 ``runner`` 允许 import 运行底座）。
"""
from __future__ import annotations

from dataclasses import dataclass


# 软告警阈值：使用率达到该比例即告警（不阻断）
SOFT_WARN_RATIO = 0.70


@dataclass(frozen=True)
class BudgetStatus:
    """预算评估结果。"""

    cap: float
    used: float
    ratio: float
    level: str  # "ok" | "soft" | "hard"
    message: str

    def as_dict(self) -> dict:
        return {
            "cap": self.cap,
            "used": self.used,
            "ratio": self.ratio,
            "level": self.level,
            "message": self.message,
        }


def evaluate_budget(project: dict) -> BudgetStatus:
    """评估 token 预算硬阻断状态。

    - 无 cap 或 cap 为 0：视为未设上限，``level="ok"``（ratio=0）；
    - used >= cap：``level="hard"``（硬阻断）；
    - ratio >= SOFT_WARN_RATIO：``level="soft"``（软告警）；
    - 否则：``level="ok"``。
    """
    budget = project.get("token_budget") or {}
    total = budget.get("total") or {}
    cap = float(total.get("cap") or 0)
    used = float(total.get("used") or 0)
    ratio = (used / cap) if cap else 0.0

    if cap and used >= cap:
        return BudgetStatus(
            cap=cap,
            used=used,
            ratio=ratio,
            level="hard",
            message=(
                f"预算已耗尽（{used:.0f}/{cap:.0f}）。暂停会话；恢复选项："
                "A. 人工批准追加预算（+20%） B. 切换廉价模型继续 C. 手动介入完成剩余工作"
            ),
        )
    if ratio >= SOFT_WARN_RATIO:
        return BudgetStatus(
            cap=cap,
            used=used,
            ratio=ratio,
            level="soft",
            message=f"预算使用率 {ratio:.0%}（{used:.0f}/{cap:.0f}），接近上限",
        )
    return BudgetStatus(
        cap=cap,
        used=used,
        ratio=ratio,
        level="ok",
        message=f"预算使用率 {ratio:.0%}（{used:.0f}/{cap:.0f}），正常",
    )
