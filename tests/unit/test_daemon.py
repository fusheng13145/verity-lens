"""sidecar 长驻守护进程测试（审计 #6）。"""
from __future__ import annotations

import io
import json

from sidecar.daemon import handle_line, serve_loop
from sidecar.tools._registry import list_tools


def _run_stream(lines: list[str]) -> list[dict]:
    inp = io.StringIO("\n".join(lines) + "\n")
    out = io.StringIO()
    serve_loop(inp, out, tools=list_tools())
    return [json.loads(l) for l in out.getvalue().splitlines() if l.strip()]


def test_ready_emitted_on_start():
    out = io.StringIO()
    serve_loop(io.StringIO(""), out, tools=list_tools())
    first = json.loads(out.getvalue().splitlines()[0])
    assert first["type"] == "ready"
    assert "plot" in first["tools"]
    assert first["protocol"] == "ndjson-line"


def test_dispatch_plot_writes_file(tmp_path):
    csv = tmp_path / "d.csv"
    csv.write_text("label,value\na,1\nb,2\n", encoding="utf-8")
    out_path = tmp_path / "fig.svg"
    resp = handle_line(
        json.dumps(
            {
                "id": "r1",
                "tool": "plot",
                "params": {"csv_path": str(csv), "out_path": str(out_path), "kind": "bar"},
            }
        ),
        list_tools(),
    )
    assert resp["id"] == "r1"
    assert resp["ok"] is True
    assert (out_path).exists()
    assert out_path.read_text(encoding="utf-8").startswith("<svg")


def test_multiple_calls_reuse_single_process():
    lines = []
    for i in range(3):
        csv = f"label,value\na,{i}\nb,{i+1}\n"
        # 用 inline：每次写临时文件较重，这里改用纯参数工具 hpc_submit dry_run
        lines.append(
            json.dumps(
                {
                    "id": f"x{i}",
                    "tool": "hpc_submit",
                    "params": {"mode": "submit", "backend": "dry_run", "command": f"echo {i}"},
                }
            )
        )
    out = _run_stream(lines)
    # 1 条 ready + 3 条响应（单进程内复用）
    assert sum(1 for o in out if o.get("type") == "ready") == 1
    responses = [o for o in out if o.get("id")]
    assert len(responses) == 3
    assert all(r["ok"] for r in responses)


def test_unknown_tool_rejected():
    resp = handle_line(json.dumps({"id": 1, "tool": "nope"}), list_tools())
    assert resp["ok"] is False
    assert "未知" in resp["error"]


def test_missing_tool_field_rejected():
    resp = handle_line(json.dumps({"id": 1}), list_tools())
    assert resp["ok"] is False
    assert "tool" in resp["error"]


def test_malformed_json_rejected():
    resp = handle_line("not-json", list_tools())
    assert resp["ok"] is False
    assert "解析" in resp["error"]


def test_shutdown_breaks_loop():
    out = _run_stream(['{"type":"shutdown"}', '{"id":2,"tool":"hpc_submit","params":{"mode":"status","job_id":"j1"}}'])
    # shutdown 后不应再处理后续请求
    assert all(o.get("id") != 2 for o in out)
    assert any(o.get("type") == "ready" for o in out)


def test_tool_exception_isolated():
    # 触发参数错误（plot 缺必填 csv_path）不应崩进程，应返回 ok:false
    resp = handle_line(
        json.dumps({"id": "e", "tool": "plot", "params": {}}), list_tools()
    )
    assert resp["ok"] is False
    assert "ValueError" in resp["error"] or "csv_path" in resp["error"]
