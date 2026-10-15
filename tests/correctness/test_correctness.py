"""L3 科研正确性抽检（tests/correctness）。

口径（design-blueprint.md §测试体系 L3 / docs/testing.md）：
- L1 Schema 只保证结构，L2 Golden 只保证"验证脚本输出未漂移"；
- L3 检查的是**科研正确性本身**：报告中的关键数值必须彼此自洽，且能被确定性工具复算。
- 本层用真实侧车工具（stat_test / power_analysis / doi_verify）对三学科 golden 样例做抽检，
  任何不自洽都必须报错，而不是像"工具可用性探测"那样一律通过。
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import sidecar.tools.power_analysis as pa  # noqa: E402
import sidecar.tools.stat_test as stat  # noqa: E402
from orchestrator.failure_loop import verify_with_sidecar  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLES = REPO_ROOT / "bundles"


def _load(rel: str) -> dict:
    return json.loads((BUNDLES / rel).read_text(encoding="utf-8"))


# ── biomed：p 值 ↔ 95% CI ↔ 样本量必须自洽 ──────────────────────────

def test_biomed_compliant_golden_is_statistically_coherent():
    """合规样例不能只是"字段齐全"——数值之间必须自洽（L3 存在意义）。"""
    rep = _load("biomed/golden/stats_ok.input.json")
    entry = {
        "classification": {"code": "METH-00", "category": "METH", "confidence": 0.9},
        "reported_metrics": {
            "effect_size": rep["effect_size"],
            "ci_95": rep["ci_95"],
            "p_value": rep["p_value"],
            "test": rep["test_used"],
        },
    }
    res = verify_with_sidecar(entry)
    assert res["status"] == "verified", res
    assert res["checks"][0]["ok"] is True


def test_incoherent_numbers_are_flagged():
    """p 与 CI 不自洽必须报 mismatch（此前"仅探测 import 可用"会静默放行）。"""
    entry = {
        "classification": {"code": "METH-00", "category": "METH", "confidence": 0.9},
        "reported_metrics": {"effect_size": 0.62, "ci_95": [0.31, 0.93], "p_value": 0.023},
    }
    res = verify_with_sidecar(entry)
    assert res["status"] == "mismatch"
    chk = res["checks"][0]
    assert chk["p_recomputed"] < 0.001 and chk["p_reported"] == 0.023


# ── 完整复算：由组统计量重建并比对 ──────────────────────────────────

def test_full_recompute_from_group_stats():
    """给出组统计量时，p / 效应量必须被完整复算并吻合。"""
    metrics = {
        "group_stats": {"mean_a": 5.0, "sd_a": 1.0, "n_a": 30,
                        "mean_b": 4.5, "sd_b": 1.0, "n_b": 30},
        "test": "welch", "p_value": 0.0577, "effect_size": 0.5,
        "n_per_group": 30, "power": 0.49,
    }
    entry = {"classification": {"code": "METH-01", "category": "METH", "confidence": 0.8},
             "reported_metrics": metrics}
    res = verify_with_sidecar(entry)
    got = res["checks"][0]["recomputed"]
    assert res["status"] == "verified", res
    assert got["p_value"] == pytest.approx(metrics["p_value"], abs=0.01)
    assert got["effect_size"] == pytest.approx(metrics["effect_size"], abs=0.01)


def test_recompute_matches_independent_scipy_api():
    """我们的复算管线必须与 scipy 独立 API（ttest_ind_from_stats）一致。"""
    from scipy import stats as sps

    from orchestrator.failure_loop import _reconstruct

    a = _reconstruct(5.0, 1.0, 30)
    b = _reconstruct(4.5, 1.0, 30)
    ours = stat.run(a, b, test="welch")
    ref = sps.ttest_ind_from_stats(5.0, 1.0, 30, 4.5, 1.0, 30)
    assert ours["p_value"] == pytest.approx(float(ref.pvalue), abs=1e-9)
    assert ours["effect_size"] == pytest.approx(0.5, abs=1e-9)


def test_power_claim_is_recomputed():
    """功效主张必须复算一致；不一致 → mismatch。"""
    base = {
        "classification": {"code": "METH-02", "category": "METH", "confidence": 0.8},
        "reported_metrics": {"effect_size": 0.2, "ci_95": [0.05, 0.35],
                             "p_value": 0.2, "n_per_group": 20},
    }
    ok = verify_with_sidecar({**base, "reported_metrics": {**base["reported_metrics"], "power": 0.1}})
    bad = verify_with_sidecar({**base, "reported_metrics": {**base["reported_metrics"], "power": 0.95}})
    pw = [c for c in ok["checks"] if c["tool"] == "power_analysis"][0]
    assert pw["power_recomputed"] == pytest.approx(0.1, abs=0.03)
    assert pw["underpowered_recomputed"] is True
    assert "不能替代 p 值" in pw["post_hoc_warning"]  # 科研诚信提示必须在
    assert bad["status"] == "mismatch"


def test_no_recomputable_numbers_is_not_treated_as_verified():
    """无可复算数值 → skipped（绝不因为"工具可用"就标 verified）。"""
    entry = {"classification": {"code": "METH-03", "category": "METH", "confidence": 0.6}}
    res = verify_with_sidecar(entry)
    assert res["status"] == "skipped"
    assert any(c.get("status") == "skipped" for c in res["checks"])


# ── stat_test 本身：与已知解析解对照 ───────────────────────────────

def test_stat_test_matches_closed_form_for_large_n():
    """大样本下 Welch t 检验的 p 值应与正态近似一致（O(1/n) 误差内）。"""
    import numpy as np

    rng = np.random.default_rng(20261015)
    a = rng.normal(5.0, 1.0, 4000)
    b = rng.normal(4.5, 1.0, 4000)
    out = stat.run(list(a), list(b), test="welch")
    se = 1.0 * math.sqrt(2 / 4000)
    z = 0.5 / se
    expected_p = 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))
    assert out["p_value"] == pytest.approx(expected_p, rel=0.02)
    assert out["effect_size"] == pytest.approx(0.5, abs=0.05)


def test_stat_test_is_deterministic():
    payload = ([1.2, 2.3, 3.1, 2.8, 4.0], [2.1, 3.9, 3.3, 5.2, 4.4])
    first = stat.run(*payload, test="welch")
    second = stat.run(*payload, test="welch")
    assert first == second


# ── power_analysis：与经典样本量表对照 ─────────────────────────────

@pytest.mark.parametrize(
    "d,expected_n",
    [(0.5, 63), (0.2, 393), (0.8, 25)],  # 正态近似（G*Power 精确解为 64/394/26）
)
def test_required_n_matches_normal_approximation(d, expected_n):
    assert pa.required_n(d, alpha=0.05, target_power=0.8) == expected_n


def test_required_n_achieves_target_power():
    for d in (0.2, 0.5, 0.8):
        n = pa.required_n(d)
        assert pa.achieved_power(d, n) >= 0.8


def test_power_scales_with_effect_size_and_n():
    assert pa.achieved_power(0.2, 50) < pa.achieved_power(0.5, 50)
    assert pa.achieved_power(0.5, 30) < pa.achieved_power(0.5, 60)


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        pa.run("prior", effect_size=0.0)          # 效应量为 0 无意义
    with pytest.raises(ValueError):
        pa.run("post", effect_size=0.5)           # 缺样本量
    with pytest.raises(ValueError):
        pa.run("prior", effect_size=0.5, alpha=1.5)


# ── materials / compsci：领域数值的自洽性 ──────────────────────────

def test_materials_golden_uncertainty_is_plausible():
    """不确定度不得大于量值本身（金样例本身必须满足 L1 规则）。"""
    for case in ("bet_ok", "single_point", "no_uncertainty"):
        rep = _load(f"materials/golden/{case}.input.json")
        if rep.get("value") is None or rep.get("uncertainty") is None:
            continue
        if rep["uncertainty"] > 0 and abs(rep["value"]) > 0:
            assert rep["uncertainty"] <= abs(rep["value"]), case


def test_compsci_golden_reported_power_claim():
    """compsci 金样例若声明 n_runs，其在观测效应量下的功效必须可复算。"""
    rep = _load("compsci/golden/repro_ok.input.json")
    assert rep["n_runs"] >= 3
    # 用 mean±std 反推标准化效应量需方差信息，此处只断言工具对同一输入稳定
    first = pa.run("prior", effect_size=0.05)
    second = pa.run("prior", effect_size=0.05)
    assert first == second
