"""Bundle Golden 用例回归（L1→L2，Phase 4c）。

口径（design-blueprint.md §2.6 / bundle-registry.md §4）：
- 每个 L2 Bundle 在 bundle.yml 声明 golden_cases（输入/期望输出对）；
- 回归 = 用 Bundle 自带的 L1 确定性验证脚本跑 golden 输入，
  实际问题列表必须与期望**完全一致**（集合相等，消息文本逐字匹配）；
- 验证脚本行为变化（方法论约束变更）必须同步更新 golden 期望，
  防止"脚本悄悄放水"。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLES_DIR = REPO_ROOT / "bundles"
DISCIPLINES = ("biomed", "materials", "compsci")


def _load_manifest(bundle_dir: Path) -> dict:
    return yaml.safe_load((bundle_dir / "bundle.yml").read_text(encoding="utf-8")) or {}


def _find_validator(bundle_dir: Path) -> Path:
    """定位 Bundle 的 L1 验证脚本（skills/*/scripts/validate*.py）。"""
    scripts = sorted(bundle_dir.glob("skills/*/scripts/validate*.py"))
    assert scripts, f"{bundle_dir.name} 缺少 L1 验证脚本"
    return scripts[0]


def _load_validator_module(script: Path):
    spec = importlib.util.spec_from_file_location(script.stem, script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_validator(module, payload: dict) -> list[str]:
    """兼容两种验证脚本接口：validate() -> (ok, problems) / validate_report() -> errors。"""
    if hasattr(module, "validate"):
        _ok, problems = module.validate(payload)
        return list(problems)
    errors = module.validate_report(payload)
    return list(errors)


def _cases(bundle_dir: Path) -> list[tuple[str, Path, list[str]]]:
    """展开 bundle.yml 声明的 golden_cases → (用例名, 输入文件, 期望问题列表)。"""
    manifest = _load_manifest(bundle_dir)
    cases = []
    for rel in manifest.get("golden_cases") or []:
        inp = bundle_dir / rel
        exp = inp.with_name(inp.name.replace(".input.json", ".expected.json"))
        assert inp.exists(), f"golden 输入不存在: {inp}"
        assert exp.exists(), f"golden 期望不存在: {exp}"
        expected = json.loads(exp.read_text(encoding="utf-8"))["problems"]
        cases.append((inp.stem, inp, expected))
    return cases


@pytest.mark.parametrize("discipline", DISCIPLINES)
class TestBundleGolden:
    def test_all_cases_declared(self, discipline):
        bundle_dir = BUNDLES_DIR / discipline
        cases = _cases(bundle_dir)
        assert cases, f"{discipline} 未声明 golden_cases"

    @pytest.mark.parametrize("idx", range(3))
    def test_case_matches_expected(self, discipline, idx):
        bundle_dir = BUNDLES_DIR / discipline
        cases = _cases(bundle_dir)
        name, inp, expected = cases[idx]
        module = _load_validator_module(_find_validator(bundle_dir))
        payload = json.loads(inp.read_text(encoding="utf-8"))
        actual = _run_validator(module, payload)
        assert sorted(actual) == sorted(expected), (
            f"{discipline}/{name} golden 漂移：实际 {actual} != 期望 {expected}"
        )
