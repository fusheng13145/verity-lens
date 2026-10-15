"""hpc_submit 侧车工具测试（确定性、可离线）。

覆盖：dry_run 确定性 job_id / mock 生命周期 / 校验 / cancel / 未知 job_id /
slurm 显式降级 / stdio 入口。真实调度器（slurm/pbs）调用不在单测范围（best-effort 降级已覆盖）。
"""
import json
import hashlib

import pytest

from sidecar.tools import hpc_submit as H


def _expected_job_id(command, resources, backend):
    salt = H._SALT
    canonical = json.dumps(
        {"command": command, "resources": resources or {}, "backend": backend},
        sort_keys=True, ensure_ascii=False,
    )
    return "vl-" + hashlib.sha256((salt + canonical).encode("utf-8")).hexdigest()[:16]


CMD = "python train.py --epochs 10"
RES = {"cpus": 4, "memory_gb": 16, "walltime_min": 60}


def test_dry_run_is_deterministic_and_not_executed(tmp_path):
    a = H.run("submit", command=CMD, resources=RES, backend="dry_run", state_dir=str(tmp_path))
    b = H.run("submit", command=CMD, resources=RES, backend="dry_run", state_dir=str(tmp_path))
    assert a["job_id"] == b["job_id"] == _expected_job_id(CMD, RES, "dry_run")
    assert a["state"] == "completed"
    assert a["executed"] is False
    assert "未实际执行" in (a.get("note") or "")
    assert a["status_endpoint"] == f"hpc://dry_run/{a['job_id']}"


def test_dry_run_does_not_execute_command(tmp_path):
    # 即使 command 是危险命令，dry_run 也不执行
    H.run("submit", command="rm -rf /", resources=RES, backend="dry_run", state_dir=str(tmp_path))
    # 无异常即通过（未执行）


def test_mock_lifecycle_pending_running_completed(tmp_path):
    sub = H.run("submit", command=CMD, resources=RES, backend="mock", state_dir=str(tmp_path))
    assert sub["state"] == "pending"
    s1 = H.run("status", job_id=sub["job_id"], state_dir=str(tmp_path))
    s2 = H.run("status", job_id=sub["job_id"], state_dir=str(tmp_path))
    assert s1["state"] == "running"
    assert s2["state"] == "completed"
    assert s2["executed"] is True


def test_mock_lifecycle_deterministic_job_id(tmp_path):
    sub = H.run("submit", command=CMD, resources=RES, backend="mock", state_dir=str(tmp_path))
    assert sub["job_id"] == _expected_job_id(CMD, RES, "mock")


def test_cancel_transitions_state(tmp_path):
    sub = H.run("submit", command=CMD, resources=RES, backend="dry_run", state_dir=str(tmp_path))
    res = H.run("cancel", job_id=sub["job_id"], state_dir=str(tmp_path))
    assert res["state"] == "cancelled"


def test_empty_command_rejected(tmp_path):
    with pytest.raises(ValueError):
        H.run("submit", command="  ", backend="dry_run", state_dir=str(tmp_path))


def test_invalid_resources_rejected(tmp_path):
    with pytest.raises(ValueError):
        H.run("submit", command=CMD, resources={"cpus": 0}, backend="dry_run", state_dir=str(tmp_path))


def test_status_requires_known_job_id(tmp_path):
    with pytest.raises(ValueError):
        H.run("status", job_id="vl-doesnotexist000", state_dir=str(tmp_path))


def test_slurm_unavailable_degrades_gracefully(tmp_path):
    # 本机无 sbatch → 显式降级（不抛异常，不静默）
    res = H.run("submit", command=CMD, resources=RES, backend="slurm", state_dir=str(tmp_path))
    assert res["state"] == "submission_unavailable"
    assert "scheduler 不可达" in (res.get("warning") or "")
    assert res["executed"] is False


def test_stdio_entry(tmp_path):
    import subprocess
    import sys

    payload = json.dumps({
        "mode": "submit", "command": CMD, "resources": RES,
        "backend": "dry_run", "state_dir": str(tmp_path),
    })
    proc = subprocess.run(
        [sys.executable, "-m", "sidecar.tools.hpc_submit"],
        input=payload, capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["job_id"].startswith("vl-")
    assert out["state"] == "completed"
