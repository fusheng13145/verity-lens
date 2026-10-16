"""底座切换季度演练单元测试（hal/switch_drill.py）。

覆盖：接口符合性（真实适配器通过 / 缺方法 / 缺参数 / 多余必选参数）、
耦合扫描（行级判定 + 合成树 + 真实仓库预算内）、替换模拟、版本漂移
（漂移/一致/离线 skip）、run_drill 聚合退出码、报告渲染。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hal.interface import CAPABILITY_KEYS, HarnessAdapter
from hal.switch_drill import (
    _MinimalAdapter,
    _line_imports_base,
    check_interface_conformance,
    check_version_drift,
    render_report,
    run_drill,
    scan_coupling,
    simulate_swap,
)


# ── 接口符合性 ───────────────────────────────────────────────────────

def test_conformance_passes_on_real_adapter():
    result = check_interface_conformance()
    assert result["ok"], f"真实 DSHAdapter 应通过 Protocol 符合性: {result['problems']}"
    assert len(result["checked"]) >= 11  # Protocol 全部公开方法


def test_conformance_detects_missing_method():
    class Broken:
        def start_session(self, preset, workspace, task): ...

    result = check_interface_conformance(adapter_cls=Broken)
    assert result["ok"] is False
    assert any("fork_trajectory" in p for p in result["problems"])


def test_conformance_detects_missing_param():
    class Narrow:
        def register_skills(self): ...  # 缺 skill_dirs

        def start_session(self, preset, workspace, task): ...

        def resume_session(self, handle): ...

        def stop_session(self, handle, graceful=True): ...

        def export_session_log(self, handle): ...

        def fork_trajectory(self, handle, at_event): ...

        def register_tools(self, tools): ...

        def declare_mcp_servers(self, config): ...

        def apply_preset_patch(self, patch): ...

        def set_permission(self, scope, level): ...

        def spawn_subagent(self, spec): ...

        def capabilities(self): ...

    result = check_interface_conformance(adapter_cls=Narrow)
    assert result["ok"] is False
    assert any("register_skills" in p and "skill_dirs" in p for p in result["problems"])


def test_conformance_allows_extra_optional_params():
    class Extends(_MinimalAdapter):
        def start_session(self, preset, workspace, task, timeout=30.0):  # 新增可选参数合法
            return super().start_session(preset, workspace, task)

    result = check_interface_conformance(adapter_cls=Extends)
    assert result["ok"], result["problems"]


def test_conformance_rejects_new_required_param():
    class DemandsMore(_MinimalAdapter):
        def start_session(self, preset, workspace, task, api_key):  # 新增必选参数不合法
            return super().start_session(preset, workspace, task)

    result = check_interface_conformance(adapter_cls=DemandsMore)
    assert result["ok"] is False
    assert any("api_key" in p for p in result["problems"])


# ── 耦合扫描 ─────────────────────────────────────────────────────────

def test_line_imports_base_variants():
    assert _line_imports_base("from hal.dsh_adapter import DSHAdapter") == "hal.dsh_adapter"
    assert _line_imports_base("from hal import dsh_adapter") == "hal.dsh_adapter"
    assert _line_imports_base("import hal.dsh_adapter") == "hal.dsh_adapter"
    assert _line_imports_base("from hal.interface import CAPABILITY_KEYS") is None
    assert _line_imports_base("from hal.switch_drill import run_drill") is None
    assert _line_imports_base("import orchestrator.cli") is None
    assert _line_imports_base("x = 'from hal.dsh_adapter import DSHAdapter'") is None  # 非导入行


def test_scan_coupling_synthetic_tree(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "direct.py").write_text("from hal.dsh_adapter import DSHAdapter\n", encoding="utf-8")
    (tmp_path / "pkg" / "clean.py").write_text("from hal.interface import CAPABILITY_KEYS\n", encoding="utf-8")
    result = scan_coupling(tmp_path, budget=5, roots=("pkg",))
    assert result["ok"] and result["count"] == 1
    assert result["hits"][0]["file"] == "pkg/direct.py"

    over = scan_coupling(tmp_path, budget=0, roots=("pkg",))
    assert over["ok"] is False and over["problems"]


def test_scan_coupling_real_repo_under_budget():
    result = scan_coupling()
    assert result["ok"], f"真实仓库直连超预算: {result['hits']}"
    files = {h["file"] for h in result["hits"]}
    assert "orchestrator/bundle_loader.py" in files  # 已知直连被如实列出（换底座成本清单）


# ── 替换模拟 ─────────────────────────────────────────────────────────

def test_swap_simulation_passes():
    result = simulate_swap()
    assert result["ok"], result["problems"]
    assert isinstance(_MinimalAdapter(), HarnessAdapter)
    assert set(CAPABILITY_KEYS) <= set(_MinimalAdapter().capabilities())


# ── 版本漂移 ─────────────────────────────────────────────────────────

class _FakeBase:
    def __init__(self, available=True, installed="0.2.0-rc.2", locked="0.2.0-rc.2", raise_on_version=False):
        self._available = available
        self._installed = installed
        self._locked = locked
        self._raise = raise_on_version

    def available(self):
        return self._available

    def installed_version(self):
        if self._raise:
            raise RuntimeError("dsh --version 失败")
        return self._installed

    def locked_version(self):
        return self._locked


def test_version_drift_detected():
    r = check_version_drift(adapter=_FakeBase(installed="0.3.0"))
    assert r["ok"] is False and r["status"] == "fail"
    assert "版本漂移" in r["problems"][0]


def test_version_drift_same_version_ok():
    r = check_version_drift(adapter=_FakeBase())
    assert r["ok"] and r["status"] == "ok"


def test_version_drift_unavailable_skips():
    r = check_version_drift(adapter=_FakeBase(available=False))
    assert r["ok"] and r["status"] == "skip"


def test_version_drift_probe_error_skips():
    r = check_version_drift(adapter=_FakeBase(raise_on_version=True))
    assert r["ok"] and r["status"] == "skip"


# ── run_drill 聚合与报告 ─────────────────────────────────────────────

def test_run_drill_healthy_repo_exits_zero(tmp_path):
    # 注入不可用 adapter → 版本漂移记 skip（测试封闭，不依赖本机 dsh 状态）
    report, code = run_drill(with_contract_tests=False, adapter=_FakeBase(available=False))
    assert code == 0 and report["ok"]
    names = [c["name"] for c in report["checks"]]
    assert names == ["interface_conformance", "coupling_scan", "swap_simulation", "version_drift"]


def test_run_drill_aggregates_failure(tmp_path):
    # 预算 0 → 真实仓库的已知直连（2 项）必然超预算 → 演练整体 FAIL
    report, code = run_drill(with_contract_tests=False, coupling_budget=0, adapter=_FakeBase(available=False))
    assert code == 1 and report["ok"] is False
    coupling = next(c for c in report["checks"] if c["name"] == "coupling_scan")
    assert coupling["ok"] is False


def test_render_report_sections():
    report, _ = run_drill(with_contract_tests=False, adapter=_FakeBase(available=False))
    text = render_report(report)
    assert "底座切换季度演练" in text
    for name in ("interface_conformance", "coupling_scan", "swap_simulation", "version_drift"):
        assert name in text
    assert "[PASS] 演练结论" in text


def test_drill_report_is_json_serializable():
    report, _ = run_drill(with_contract_tests=False, adapter=_FakeBase(available=False))
    data = json.loads(json.dumps(report, ensure_ascii=False))
    assert data["exit_code"] == 0
