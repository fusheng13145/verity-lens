"""集成测试：Sidecar 工具的「stdio 边界」与「进程内模块」输出必须逐字节等价。

项目立身之本（design-blueprint.md §2.8）：关键数值必经确定性工具复算。
工具同时提供两条通道：
  - 编排层 `from sidecar.tools.x import run; run(**params)`（verify_with_sidecar 走的路）
  - HAL 经 MCP 以 `python -m sidecar.tools.x` 子进程调用（真实部署走的路）

两条通道共用同一个 `run()`，但此前没有任何测试证明它们产出一致。
本测试把每个工具当作 HAL 那样用子进程拉起，喂相同输入，断言 stdio 输出
与进程内 `run(**params)` 完全等价——确保「边界保真」，HAL 看到的数值就是
编排层复算的数值。

数值比对用容差（abs=1e-9 / rel=1e-6），规避跨进程 BLAS 多线程浮点归并顺序差异。
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable  # 当前 venv 解释器，保证与待测代码同一套 numpy/scipy


def _run_stdio(module: str, payload: dict) -> dict:
    """像 HAL 那样以子进程拉起工具，返回 stdout 解析出的 JSON 结果。"""
    proc = subprocess.run(
        [PY, "-m", f"sidecar.tools.{module}"],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, f"{module} 异常退出: {proc.stderr}"
    return json.loads(proc.stdout)


def _approx_equal(a, b, abs_tol=1e-9, rel_tol=1e-6) -> bool:
    """递归近似相等：数值用容差，其余严格相等。"""
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return False
        return all(_approx_equal(a[k], b[k], abs_tol, rel_tol) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_approx_equal(x, y, abs_tol, rel_tol) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None:
            return a == b
        return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))
    return a == b


# ── stat_test ──────────────────────────────────────────────────────────
def test_stat_test_stdio_matches_module():
    from sidecar.tools.stat_test import run

    payload = {
        "group_a": [5.1, 4.9, 5.0, 5.2, 4.8, 5.0, 4.9, 5.1, 5.0, 4.9],
        "group_b": [4.7, 4.6, 4.8, 4.5, 4.9, 4.7, 4.6, 4.8, 4.7, 4.5],
        "test": "welch",
        "alpha": 0.05,
    }
    expected = run(**payload)
    got = _run_stdio("stat_test", payload)
    assert _approx_equal(got, expected), f"\nstdio={got}\nmodule={expected}"


# ── power_analysis ─────────────────────────────────────────────────────
def test_power_analysis_prior_stdio_matches_module():
    from sidecar.tools.power_analysis import run

    payload = {"mode": "prior", "effect_size": 0.5}
    assert _approx_equal(_run_stdio("power_analysis", payload), run(**payload))


def test_power_analysis_post_stdio_matches_module():
    from sidecar.tools.power_analysis import run

    payload = {"mode": "post", "effect_size": 0.2, "n_per_group": 20}
    assert _approx_equal(_run_stdio("power_analysis", payload), run(**payload))


# ── desensitize ────────────────────────────────────────────────────────
def test_desensitize_field_mask_hash_stdio_matches_module():
    from sidecar.tools.desensitize import run

    payload = {
        "mode": "field_mask",
        "records": [{"name": "张三", "age": 34}, {"name": "李四", "age": 29}],
        "fields": ["name"],
        "strategy": "hash",
        "salt": "s1",
    }
    assert _approx_equal(_run_stdio("desensitize", payload), run(**payload))


def test_desensitize_k_anonymity_stdio_matches_module():
    from sidecar.tools.desensitize import run

    payload = {
        "mode": "k_anonymity",
        "records": [
            {"sex": "M", "age": 34, "v": 1},
            {"sex": "F", "age": 29, "v": 2},
            {"sex": "F", "age": 29, "v": 3},
            {"sex": "F", "age": 29, "v": 4},
            {"sex": "M", "age": 40, "v": 5},
        ],
        "quasi_identifiers": ["sex", "age"],
        "k": 3,
    }
    assert _approx_equal(_run_stdio("desensitize", payload), run(**payload))


def test_desensitize_dp_aggregate_seed_stdio_matches_module():
    from sidecar.tools.desensitize import run

    payload = {"mode": "dp_aggregate", "values": [1, 2, 3, 4, 5],
               "epsilon": 1.0, "statistic": "mean", "seed": 42}
    assert _approx_equal(_run_stdio("desensitize", payload), run(**payload))


def test_desensitize_scan_text_stdio_matches_module():
    from sidecar.tools.desensitize import run

    payload = {"mode": "scan_text",
               "text": "联系 zhang@hospital.org 或手机 13800138000"}
    assert _approx_equal(_run_stdio("desensitize", payload), run(**payload))


# ── hpc_submit ─────────────────────────────────────────────────────────
def test_hpc_submit_dry_run_stdio_matches_module():
    from sidecar.tools.hpc_submit import run

    with tempfile.TemporaryDirectory() as sd_a, tempfile.TemporaryDirectory() as sd_b:
        payload = {
            "mode": "submit",
            "command": "python train.py --epochs 10",
            "resources": {"cpus": 4, "memory_gb": 16, "walltime_min": 60},
            "backend": "dry_run",
        }
        expected = run(**payload, state_dir=sd_a)
        # dry_run 绝不实际执行，state 必须 completed / executed=False
        assert expected["state"] == "completed" and expected["executed"] is False
        got = _run_stdio("hpc_submit", {**payload, "state_dir": sd_b})
        # submitted_at 是两次独立调用的墙钟时间，必然不同——只比对确定性字段
        got.pop("submitted_at", None)
        expected.pop("submitted_at", None)
        assert _approx_equal(got, expected), f"\nstdio={got}\nmodule={expected}"


def test_hpc_submit_mock_lifecycle_via_stdio():
    """mock backend 的完整生命周期走通 stdio 边界：pending→running→completed。"""
    with tempfile.TemporaryDirectory() as sd:
        submit = _run_stdio("hpc_submit", {
            "mode": "submit", "command": "echo hi",
            "resources": {"cpus": 1, "memory_gb": 1, "walltime_min": 1},
            "backend": "mock", "state_dir": sd,
        })
        assert submit["state"] == "pending"
        jid = submit["job_id"]

        s1 = _run_stdio("hpc_submit",
                        {"mode": "status", "job_id": jid, "state_dir": sd})
        s2 = _run_stdio("hpc_submit",
                        {"mode": "status", "job_id": jid, "state_dir": sd})
        assert s1["state"] == "running"
        assert s2["state"] == "completed" and s2["executed"] is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
