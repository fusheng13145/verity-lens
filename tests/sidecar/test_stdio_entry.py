"""Sidecar 工具 stdio 入口测试（Phase 4c）：MCP 声明可执行，不止是纸面声明。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_tool(module: str, payload: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", module],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def test_stat_test_stdio():
    out = _run_tool(
        "sidecar.tools.stat_test",
        {"group_a": [1.2, 2.3, 3.1, 2.8, 4.0],
         "group_b": [2.1, 3.9, 3.3, 5.2, 4.4], "test": "welch"},
    )
    assert out["test_used"] == "welch"
    assert out["n_a"] == 5 and out["n_b"] == 5
    assert round(out["p_value"], 4) == 0.1541


def test_doi_verify_stdio_offline_format_error():
    out = _run_tool("sidecar.tools.doi_verify", {"doi": "not-a-doi"})
    assert out["exists"] is False
    assert out["error"] == "DOI 格式非法"
