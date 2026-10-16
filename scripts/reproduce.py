#!/usr/bin/env python
"""reproduce —— 从 data/raw 经分析到 figures 的可复现比对。

设计（消除审计 #11 的 echo 占位）：
- 复用 ``sidecar/tools/plot.py`` 的**确定性**绘图（相同输入 → 相同 SVG 字节）；
- 对每个产物计算 SHA-256，与 ``.verity/reproduce_baseline.json`` 中记录的基线比对；
- 报告每幅图：``baseline established`` / ``consistent``（可复现）/ ``DRIFT``（复现漂移，需排查）；
- 任一幅漂移且非 ``--update`` 模式时退出码 1（复现性被破坏）。

manifest 格式（``<workspace>/reproduce_manifest.yaml``，可选）：
    figures:
      - csv: data/raw/expr1.csv
        out: figures/expr1.svg
        kind: bar          # bar | line
        title: "Expr 1"
未提供 manifest 时，自动发现 ``data/raw`` 与 ``data/processed`` 下的 *.csv，
默认以 bar 图渲染到 ``figures/<stem>.svg``。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - 正常环境 PyYAML 已声明
    yaml = None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _discover_csv_specs(workspace: Path) -> list[dict]:
    specs: list[dict] = []
    for raw_dir in ("data/raw", "data/processed"):
        root = workspace / raw_dir
        if not root.exists():
            continue
        for csv_path in sorted(root.rglob("*.csv")):
            stem = csv_path.stem
            specs.append(
                {
                    "csv": str(csv_path.relative_to(workspace)).replace("\\", "/"),
                    "out": f"figures/{stem}.svg",
                    "kind": "bar",
                    "title": stem,
                }
            )
    return specs


def _load_manifest(workspace: Path, manifest_path: Path | None) -> list[dict]:
    if manifest_path and manifest_path.exists():
        if yaml is None:
            print(f"[reproduce] 需要 PyYAML 解析 manifest {manifest_path}，但不可用；跳过")
            return []
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        specs = data.get("figures") or []
        if not isinstance(specs, list):
            raise SystemExit(f"[reproduce] manifest 格式错误：figures 应为列表（{manifest_path}）")
        return specs
    return _discover_csv_specs(workspace)


def run(workspace: Path, manifest_path: Path | None, baseline_path: Path, *, update: bool) -> int:
    from sidecar.tools.plot import render

    specs = _load_manifest(workspace, manifest_path)
    if not specs:
        print("[reproduce] 无待复现图表（无 manifest 且无 data/*/*.csv），跳过")
        return 0

    baseline: dict = {}
    if baseline_path.exists():
        try:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8")) or {}
        except (json.JSONDecodeError, OSError):
            baseline = {}

    results: list[tuple[str, str]] = []  # (out, status)
    next_baseline: dict = dict(baseline)
    drift = False

    for spec in specs:
        csv_rel = spec.get("csv")
        out_rel = spec.get("out")
        if not csv_rel or not out_rel:
            print(f"[reproduce] 跳过非法条目（缺 csv/out）：{spec}")
            continue
        csv_path = workspace / csv_rel
        out_path = workspace / out_rel
        if not csv_path.exists():
            print(f"[reproduce] 跳过：输入不存在 {csv_rel}")
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            render(
                csv_path,
                out_path,
                kind=spec.get("kind", "bar"),
                title=spec.get("title", out_path.stem),
            )
        except ValueError as exc:
            print(f"[reproduce] 绘图失败 {out_rel}：{exc}")
            drift = True
            continue

        digest = _sha256(out_path)
        prev = baseline.get(out_rel)
        if prev is None:
            status = "baseline established"
        elif prev == digest:
            status = "consistent"
        else:
            status = "DRIFT"
            drift = True
        results.append((out_rel, status))
        next_baseline[out_rel] = digest
        print(f"[reproduce] {out_rel}: {status}")

    if update:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(next_baseline, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"[reproduce] 基线已更新：{baseline_path}（{len(next_baseline)} 项）")
        return 0

    # 普通模式：持久化基线（首次建立，后续可比），但漂移仍判失败
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(next_baseline, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if drift:
        print(f"[reproduce] 存在漂移，复现性被破坏（基线：{baseline_path}）")
        return 1
    print(f"[reproduce] 全部一致，复现通过（{len(results)} 项）")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从 data/raw 到 figures 的可复现比对")
    parser.add_argument("--workspace", default=".", help="Workspace 目录")
    parser.add_argument("--manifest", default=None, help="manifest 路径（默认 <workspace>/reproduce_manifest.yaml）")
    parser.add_argument("--baseline", default=None, help="基线 JSON 路径（默认 <workspace>/.verity/reproduce_baseline.json）")
    parser.add_argument("--update", action="store_true", help="用当前产物刷新基线（不判定漂移）")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else (workspace / "reproduce_manifest.yaml")
    baseline_path = Path(args.baseline).resolve() if args.baseline else (workspace / ".verity" / "reproduce_baseline.json")
    return run(workspace, manifest_path, baseline_path, update=args.update)


if __name__ == "__main__":
    sys.exit(main())
