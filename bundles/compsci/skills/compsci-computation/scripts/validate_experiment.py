#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L1 确定性校验：可复现计算实验报告。

compsci Bundle 的 computation Skill 强制规范。蓝图 §2.5（方法论可工程化）：
  R1 随机种子必须固定且记录（random_seed 为非负整数）
  R2 每个实验须 >=3 次独立重复（n_runs >= 3），禁止仅报单次最优
  R3 运行环境必须记录（environment 非空）
  R4 数据与代码可溯源（data_hash 或 code_hash 至少其一非空）
  R5 数值结论须带不确定度（std >= 0 必填），禁止只报点估计
  R6 基线对比须有统计差异（baseline 须含 delta 或 p）

用法：
  python validate_experiment.py <report.json|report.yaml>
  python validate_experiment.py --check <report>   # 同义

退出码：0 = 全部通过；1 = 存在校验错误。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None


MIN_RUNS = 3


def _load(path: str) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    if path.endswith((".yaml", ".yml")):
        if yaml is None:
            raise SystemExit("[validate] 需要 PyYAML 解析 yaml 报告")
        return yaml.safe_load(text) or {}
    return json.loads(text)


def validate_report(report: dict) -> list[str]:
    """返回错误列表（空 = 通过）。纯函数，确定性。"""
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["report 必须是对象（dict）"]

    # R1 随机种子
    seed = report.get("random_seed")
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        errors.append("R1 随机种子 random_seed 必须是非负整数")

    # R2 重复次数
    n = report.get("n_runs")
    if not isinstance(n, int) or isinstance(n, bool) or n < MIN_RUNS:
        errors.append(f"R2 n_runs 必须为整数且 >= {MIN_RUNS}（当前：{n!r}）")

    # R3 环境
    env = report.get("environment")
    if not isinstance(env, str) or not env.strip():
        errors.append("R3 environment 必须非空（框架/依赖/硬件/确定性设置）")

    # R4 哈希溯源
    dh = report.get("data_hash")
    ch = report.get("code_hash")
    if not (isinstance(dh, str) and dh.strip()) and not (isinstance(ch, str) and ch.strip()):
        errors.append("R4 data_hash 或 code_hash 至少其一非空")

    # R5 不确定度
    value = report.get("value")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append("R5 value 必须是数值")
    std = report.get("std")
    if not isinstance(std, (int, float)) or isinstance(std, bool) or std < 0:
        errors.append("R5 std 必须是 >=0 的数值（禁止只报点估计）")

    # R6 基线对比
    base = report.get("baseline")
    if base is not None:
        if not isinstance(base, dict):
            errors.append("R6 baseline 必须是对象")
        else:
            has_delta = "baseline_delta" in base
            has_p = "baseline_p" in base
            if not (has_delta or has_p):
                errors.append("R6 基线对比须含 baseline_delta 或 baseline_p")

    return errors


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if a != "--check"]
    if len(args) != 1:
        sys.stderr.write("用法: python validate_experiment.py <report.json|report.yaml>\n")
        return 2
    try:
        report = _load(args[0])
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"[validate] 读取失败: {exc}\n")
        return 2
    errors = validate_report(report)
    if errors:
        for e in errors:
            print(f"  [FAIL] {e}")
        print(f"[validate] 失败：{len(errors)} 项未通过")
        return 1
    print("[validate] 通过：可复现计算实验报告满足 compsci L1 规范")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
