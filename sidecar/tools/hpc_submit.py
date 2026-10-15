"""Sidecar 工具：HPC 长任务提交 + 状态轮询（可插拔 backend）。

用途（design-blueprint.md §2.7 / tool-calling.md / E13）：
- 长任务远程提交，规避"终端关闭即中断"；底座仅轮询状态，不阻塞会话；
- 与 stat_test / power_analysis 一样，相同输入必须得到相同输出（dry_run/mock 确定性）。

backend 可插拔（纯标准库，可离线测试）：
- `dry_run`（默认）：仅校验规格 + 在本地账本登记，不实际执行；job_id 由规格哈希确定 → 完全确定、安全；
- `mock`：模拟生命周期 pending→running→completed（按轮询次数推进，确定性）；
- `slurm`：best-effort 调用 `sbatch --wrap=...`，调度器不可达时显式降级（不崩溃、给出 warning + 构造命令）；
- `pbs`：best-effort 调用 `qsub`（同理）。

安全：
- dry_run / mock 绝不执行命令；
- slurm 经 `--wrap`、pbs 经 `bash -c` 把命令作为**单参数**传入（不拼接 shell，避免注入）；
- 所有提交完整落账本（command + resources）可审计。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any

TOOL_SPEC = {
    "name": "hpc_submit",
    "description": (
        "长任务远程提交 + 状态轮询（可插拔 backend：dry_run/mock/slurm/pbs）；"
        "dry_run/mock 确定性、不实际执行，规避终端关闭中断（E13）"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["submit", "status", "cancel"], "default": "submit"},
            "backend": {"type": "string", "enum": ["dry_run", "mock", "slurm", "pbs"], "default": "dry_run"},
            "command": {"type": "string", "description": "要执行的命令（submit 模式必填）"},
            "resources": {
                "type": "object",
                "properties": {
                    "cpus": {"type": "number", "minimum": 1, "description": "CPU 核数"},
                    "memory_gb": {"type": "number", "minimum": 0.1, "description": "内存（GB）"},
                    "walltime_min": {"type": "number", "minimum": 1, "description": "墙钟时间（分钟）"},
                    "partition": {"type": "string", "description": "队列/分区名"},
                },
            },
            "job_id": {"type": "string", "description": "status / cancel 模式必填"},
            "workdir": {"type": "string", "description": "工作目录（slurm/pbs 用）"},
            "state_dir": {"type": "string", "description": "作业账本目录（默认系统临时目录）"},
            "poll_tick": {"type": "integer", "default": 1, "description": "mock backend 状态推进步数"},
        },
        "required": [],
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "job_id": {"type": "string"},
            "backend": {"type": "string"},
            "state": {"type": "string", "enum": [
                "pending", "running", "completed", "cancelled",
                "submitted_external", "submission_failed",
                "submission_unavailable", "submission_error",
            ]},
            "status_endpoint": {"type": "string"},
            "executed": {"type": "boolean"},
            "submit_command": {"type": "string"},
            "external_job_id": {"type": "string"},
            "warning": {"type": "string"},
            "note": {"type": "string"},
            "submitted_at": {"type": "string"},
        },
    },
}

DEFAULT_STATE_SUBDIR = "verity-lens-hpc-ledger"
_SALT = "vl-hpc"


# --------------------------------------------------------------------------- #
# 内部工具
# --------------------------------------------------------------------------- #
def _state_dir(state_dir: str | None) -> str:
    base = state_dir or os.path.join(tempfile.gettempdir(), DEFAULT_STATE_SUBDIR)
    os.makedirs(base, exist_ok=True)
    return base


def _ledger_path(state_dir: str | None) -> str:
    return os.path.join(_state_dir(state_dir), "jobs.jsonl")


def _canonical(command: str, resources: dict | None, backend: str) -> str:
    res = {} if resources is None else dict(resources)
    return json.dumps(
        {"command": command, "resources": res, "backend": backend},
        sort_keys=True, ensure_ascii=False,
    )


def _job_id(command: str, resources: dict | None, backend: str) -> str:
    h = hashlib.sha256((_SALT + _canonical(command, resources, backend)).encode("utf-8"))
    return "vl-" + h.hexdigest()[:16]


def _read_ledger(state_dir: str | None) -> dict[str, dict]:
    p = _ledger_path(state_dir)
    jobs: dict[str, dict] = {}
    if not os.path.exists(p):
        return jobs
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            jobs[rec["job_id"]] = rec  # 后写覆盖，保留最新一条
    return jobs


def _append_ledger(record: dict, state_dir: str | None) -> None:
    p = _ledger_path(state_dir)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_resources(resources: dict | None) -> dict:
    if not resources:
        return {}
    res = dict(resources)
    for key in ("cpus", "memory_gb", "walltime_min"):
        if key in res and res[key] is not None:
            try:
                val = float(res[key])
            except (TypeError, ValueError):
                raise ValueError(f"resources.{key} 必须是数字")
            if val <= 0:
                raise ValueError(f"resources.{key} 必须 > 0")
    return res


# --------------------------------------------------------------------------- #
# 真实后端（best-effort，缺失即显式降级）
# --------------------------------------------------------------------------- #
def _submit_real_backend(command: str, resources: dict, backend: str,
                         workdir: str | None) -> dict:
    """构造并提交到真实调度器；任意异常都降级为状态字段，绝不抛出。"""
    args: list[str] = []
    try:
        if backend == "slurm":
            args = ["sbatch", f"--wrap={command}"]
            if resources.get("cpus"):
                args.append(f"--cpus-per-task={int(resources['cpus'])}")
            if resources.get("memory_gb"):
                args.append(f"--mem={int(resources['memory_gb'])}G")
            if resources.get("walltime_min"):
                args.append(f"--time={int(resources['walltime_min'])}")
            if resources.get("partition"):
                args.append(f"--partition={resources['partition']}")
            if workdir:
                args.append(f"--chdir={workdir}")
        elif backend == "pbs":
            args = ["qsub"]
            directives = []
            if resources.get("cpus"):
                directives.append(f"ncpus={int(resources['cpus'])}")
            if resources.get("memory_gb"):
                directives.append(f"mem={int(resources['memory_gb'])}gb")
            if resources.get("walltime_min"):
                directives.append(f"walltime={int(resources['walltime_min'])}:00")
            if directives:
                args += ["-l", ",".join(directives)]
            if resources.get("partition"):
                args += ["-q", str(resources["partition"])]
            args += ["--", "/bin/bash", "-c", command]  # 单参数，避免 shell 拼接

        proc = subprocess.run(args, capture_output=True, text=True, timeout=30)
        cmd_str = " ".join(args)
        if proc.returncode == 0:
            external_id = proc.stdout.strip().split()[-1]  # slurm: "Submitted batch job <id>"
            return {
                "state": "submitted_external", "executed": True,
                "external_job_id": external_id, "submit_command": cmd_str,
            }
        return {
            "state": "submission_failed", "executed": False,
            "warning": f"{backend} 提交失败(rc={proc.returncode}): {proc.stderr.strip()}",
            "submit_command": cmd_str,
        }
    except FileNotFoundError:
        return {
            "state": "submission_unavailable", "executed": False,
            "warning": f"{backend} 客户端未安装（scheduler 不可达），降级为仅登记规格",
            "submit_command": " ".join(args),
        }
    except Exception as exc:  # noqa: BLE001 - 调度器交互的兜底降级
        return {
            "state": "submission_error", "executed": False,
            "warning": f"{backend} 提交异常: {type(exc).__name__}: {exc}",
        }


# --------------------------------------------------------------------------- #
# 三种模式
# --------------------------------------------------------------------------- #
def submit(command: str, resources: dict | None = None, backend: str = "dry_run",
           state_dir: str | None = None, workdir: str | None = None) -> dict:
    if not command or not str(command).strip():
        raise ValueError("submit 模式必须提供非空 command")
    if backend not in ("dry_run", "mock", "slurm", "pbs"):
        raise ValueError(f"未知 backend: {backend}")

    res = _validate_resources(resources)
    job_id = _job_id(command, resources, backend)
    submitted_at = _now()
    status_endpoint = f"hpc://{backend}/{job_id}"

    record: dict[str, Any] = {
        "job_id": job_id,
        "backend": backend,
        "command": command,
        "resources": res,
        "workdir": workdir,
        "submitted_at": submitted_at,
        "status_endpoint": status_endpoint,
        "executed": False,
        "state": "pending",
        "poll_count": 0,
    }

    if backend == "dry_run":
        record["state"] = "completed"
        record["executed"] = False
        record["note"] = "dry_run: 未实际执行，仅登记规格（可审计）"
    elif backend == "mock":
        record["state"] = "pending"
    else:  # slurm / pbs
        record.update(_submit_real_backend(command, res, backend, workdir) or {})

    _append_ledger(record, state_dir)
    return _public(record)


def status(job_id: str, state_dir: str | None = None, poll_tick: int = 1) -> dict:
    jobs = _read_ledger(state_dir)
    rec = jobs.get(job_id)
    if rec is None:
        raise ValueError(f"未知 job_id: {job_id}")

    if rec["backend"] == "mock" and rec["state"] not in ("cancelled", "completed"):
        rec["poll_count"] = rec.get("poll_count", 0) + max(1, int(poll_tick))
        if rec["poll_count"] <= 1:
            rec["state"] = "running"
        else:
            rec["state"] = "completed"
            rec["executed"] = True  # 模拟执行完成
        _append_ledger(rec, state_dir)
        rec = _read_ledger(state_dir).get(job_id, rec)

    return _public(rec)


def cancel(job_id: str, state_dir: str | None = None) -> dict:
    jobs = _read_ledger(state_dir)
    rec = jobs.get(job_id)
    if rec is None:
        raise ValueError(f"未知 job_id: {job_id}")
    rec["state"] = "cancelled"
    rec["cancelled_at"] = _now()
    _append_ledger(rec, state_dir)
    return {"job_id": job_id, "backend": rec["backend"], "state": "cancelled"}


def _public(record: dict) -> dict:
    out: dict[str, Any] = {
        "job_id": record["job_id"],
        "backend": record["backend"],
        "state": record["state"],
        "status_endpoint": record["status_endpoint"],
        "executed": record["executed"],
        "submitted_at": record["submitted_at"],
    }
    for key in ("note", "warning", "submit_command", "external_job_id"):
        if key in record:
            out[key] = record[key]
    return out


# --------------------------------------------------------------------------- #
# 入口（与 power_analysis / desensitize 同构）
# --------------------------------------------------------------------------- #
def run(mode: str = "submit", backend: str = "dry_run", command: str | None = None,
        resources: dict | None = None, job_id: str | None = None,
        state_dir: str | None = None, workdir: str | None = None,
        poll_tick: int = 1) -> dict:
    if mode == "submit":
        return submit(command=command, resources=resources, backend=backend,
                      state_dir=state_dir, workdir=workdir)
    if mode == "status":
        if not job_id:
            raise ValueError("status 模式必须提供 job_id")
        return status(job_id=job_id, state_dir=state_dir, poll_tick=poll_tick)
    if mode == "cancel":
        if not job_id:
            raise ValueError("cancel 模式必须提供 job_id")
        return cancel(job_id=job_id, state_dir=state_dir)
    raise ValueError(f"未知 mode: {mode}")


if __name__ == "__main__":
    import sys

    from sidecar.tools._stdio import serve

    sys.exit(serve(run))
