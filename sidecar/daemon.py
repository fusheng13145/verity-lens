"""Sidecar 长驻守护进程（常驻进程化，审计 #6）。

替代「每工具调用启动一个进程」的一次性 stdio：单进程常驻，经 NDJSON 行协议
（stdin 读请求、stdout 写响应）处理多个工具调用，进程内复用已 import 的模块与状态。

协议（每行一条 JSON）：
- 启动就绪：输出 ``{"type":"ready","tools":[...],"protocol":"ndjson-line"}`` 并 flush；
- 请求：``{"id":<任意>,"tool":"plot","params":{...}}``
  → 响应：``{"id":<echo>,"ok":true,"result":{...}}``
         或 ``{"id":<echo>,"ok":false,"error":"..."}``
- 关闭：收到 ``{"type":"shutdown"}`` 或 stdin EOF → 退出 0；SIGTERM/SIGINT → 优雅退出 0。

该协议与 MCP stdio 传输同构（行分隔 JSON），可直接作为 DSH mcp-client 的常驻
StdioConfig server（替代每条调用 spawn 新进程），降低冷启动与重复 import 开销。
"""
from __future__ import annotations

import json
import signal
import sys
from typing import Iterable, TextIO

from sidecar.tools._registry import dispatch, list_tools


def _emit(out: TextIO, obj: dict) -> None:
    out.write(json.dumps(obj, ensure_ascii=False) + "\n")
    out.flush()


def handle_line(line: str, tools: Iterable[str]) -> dict | None:
    """解析并处理单行请求；返回响应 dict；控制消息（shutdown）返回 None。

    ``tools`` 仅用于校验工具是否可用（避免误报为未知工具）。
    """
    line = line.strip()
    if not line:
        return None
    try:
        req = json.loads(line)
    except Exception as exc:
        return {"id": None, "ok": False, "error": f"输入解析失败: {exc}"}
    if not isinstance(req, dict):
        return {"id": None, "ok": False, "error": "请求必须是 JSON 对象"}

    if req.get("type") == "shutdown":
        return None  # 信号：关闭

    req_id = req.get("id")
    name = req.get("tool")
    if not name:
        return {"id": req_id, "ok": False, "error": "缺少 tool 字段"}
    if name not in tools:
        return {"id": req_id, "ok": False, "error": f"未知或不可用工具: {name}"}

    try:
        result = dispatch(name, req.get("params") or {})
    except Exception as exc:
        return {"id": req_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"id": req_id, "ok": True, "result": result}


def serve_loop(
    in_stream: TextIO,
    out_stream: TextIO,
    *,
    tools: Iterable[str] | None = None,
) -> int:
    """常驻主循环：逐行读取 → 分发 → 写响应。EOF / shutdown 返回 0。"""
    tools = list(tools if tools is not None else list_tools())
    _emit(out_stream, {"type": "ready", "tools": tools, "protocol": "ndjson-line"})

    for raw in in_stream:
        try:
            resp = handle_line(raw, tools)
        except Exception as exc:  # 绝不让单行错误崩掉整个常驻进程
            _emit(out_stream, {"id": None, "ok": False, "error": f"守护进程内部错误: {exc}"})
            continue
        if resp is None:  # shutdown
            break
        _emit(out_stream, resp)
    return 0


def _install_signal_handlers() -> None:
    """SIGTERM/SIGINT → 设置 _SHUTDOWN 标志；主循环在下一轮迭代优雅退出。"""

    def _handler(_signum, _frame):
        raise KeyboardInterrupt  # 由 serve_loop 的调用方捕获为正常退出

    try:
        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)
    except (ValueError, OSError):
        pass  # 非主线程 / Windows 限制时忽略，EOF 仍可作为关闭途径


def main(argv=None) -> int:
    _install_signal_handlers()
    try:
        return serve_loop(sys.stdin, sys.stdout)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
