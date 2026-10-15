"""Bundle 加载器测试（Phase 4c）：bundle.yml → HAL 注册 + 能力缺失显式降级。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hal.dsh_adapter import DSHAdapter
from orchestrator.bundle_loader import BundleLoadError, load_bundle, load_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLES_DIR = REPO_ROOT / "bundles"


@pytest.fixture()
def adapter():
    return DSHAdapter(dsh_bin="definitely-not-installed-dsh")


def test_load_biomed_registers_everything(adapter):
    report = load_bundle(BUNDLES_DIR / "biomed", adapter=adapter)
    assert report.ok, report.problems
    assert report.level == "L2"
    assert len(report.skills) == 2  # biomed-stats + biomed-literature
    # dsh 不存在 → 能力全 False → MCP / preset_patch 必须显式降级（不静默）
    assert report.mcp_servers == []
    assert report.preset == ""
    assert len(report.degradations) == 2
    assert any("mcp" in d for d in report.degradations)
    assert any("preset_patch" in d for d in report.degradations)


def test_load_with_full_capabilities(adapter, monkeypatch):
    monkeypatch.setattr(
        adapter, "capabilities",
        lambda: {"trajectory_fork": True, "preset_patch": True, "subagent": True,
                 "mcp": True, "session_log_export": True},
    )
    report = load_bundle(BUNDLES_DIR / "compsci", adapter=adapter)
    assert report.ok
    assert report.degradations == []
    assert report.mcp_servers == ["verity-stat-test", "verity-doi-verify"]
    assert report.preset == "verity-research"


def test_load_all_three_disciplines(adapter):
    for name in ("biomed", "materials", "compsci"):
        report = load_bundle(BUNDLES_DIR / name, adapter=adapter)
        assert report.ok, f"{name}: {report.problems}"
        assert report.level == "L2"


def test_load_missing_manifest(tmp_path):
    """缺 bundle.yml → 不抛异常，返回带 problems 的报告（与 vl bundle validate 口径一致）。"""
    report = load_bundle(tmp_path / "nope", adapter=DSHAdapter())
    assert not report.ok
    assert any("缺少 bundle.yml" in p for p in report.problems)


def test_load_manifest_missing_raises(tmp_path):
    with pytest.raises(BundleLoadError):
        load_manifest(tmp_path / "nope")


def test_load_broken_l2_bundle(tmp_path):
    """L2 缺 preset_patch / mcp / golden_cases → 加载被阻断并列出问题。"""
    d = tmp_path / "fake"
    (d / "skills" / "fake-core").mkdir(parents=True)
    (d / "skills" / "fake-core" / "SKILL.md").write_text("# fake", encoding="utf-8")
    (d / "bundle.yml").write_text(
        'name: "fake"\nlevel: "L2"\ndiscipline: "fake"\n'
        "skills:\n  - skills/fake-core/SKILL.md\n",
        encoding="utf-8",
    )
    report = load_bundle(d, adapter=DSHAdapter())
    assert not report.ok
    assert any("preset_patch" in p for p in report.problems)
    assert any("mcp" in p for p in report.problems)
    assert any("golden_cases" in p for p in report.problems)


def test_load_manifest_parses_fields():
    data = load_manifest(BUNDLES_DIR / "materials")
    assert data["level"] == "L2"
    assert data["preset_patch"]["preset"] == "verity-research"
    assert {s["name"] for s in data["mcp"]["servers"]} == {
        "verity-stat-test", "verity-doi-verify"
    }
