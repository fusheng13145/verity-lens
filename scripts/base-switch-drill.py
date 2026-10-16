#!/usr/bin/env python
"""底座切换季度演练入口（Backlog C ②）。

用法：
    python scripts/base-switch-drill.py [--skip-contract-tests] [--budget N] [--json]

执行时机：每季度一次（design-blueprint 底座可替换性保障）；或每次升级
deepseek-harness 后、更新 version_lock.yml 之前。

结论解读：
    exit 0 → 底座可替换性健康（接口符合、耦合在预算内、接口可被第三方实现、无版本漂移）；
    exit 1 → 存在 FAIL 项——先按报告修复（补齐接口 / 收敛直连 / 复验契约 / 更新版本锁），
             再考虑底座升级或切换。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hal.switch_drill import COUPLING_BUDGET, render_report, run_drill


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="base-switch-drill", description="底座切换季度演练（可替换性体检）"
    )
    p.add_argument(
        "--skip-contract-tests",
        action="store_true",
        help="跳过 hal/contract_tests 契约回归（快速模式，仅做结构体检）",
    )
    p.add_argument("--budget", type=int, default=COUPLING_BUDGET, help="直连行项预算")
    p.add_argument("--json", action="store_true", help="输出 JSON 报告（供 CI/工具解析）")
    args = p.parse_args(argv)

    report, code = run_drill(
        with_contract_tests=not args.skip_contract_tests,
        coupling_budget=args.budget,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render_report(report))
    return code


if __name__ == "__main__":
    sys.exit(main())
