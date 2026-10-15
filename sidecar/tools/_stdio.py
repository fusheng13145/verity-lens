"""Sidecar 工具 stdio 入口（供 MCP 声明以 `python -m sidecar.tools.<tool>` 启动）。

协议（每进程一次调用，行分隔 JSON）：
- stdin：一个 JSON 对象，字段即 run() 关键字参数；
- stdout：一个 JSON 对象（run() 返回值）；
- 失败：stdout 输出 {"error": "..."} 并以退出码 1 结束（不静默）。

该入口让 bundle.yml 的 MCP 声明可执行（不是纸面声明），
同时保持工具本身可被编排层直接 import 调用（双通道，见 tool-calling.md）。
"""
from __future__ import annotations

import json
import sys
from typing import Callable


def serve(run_fn: Callable[..., dict]) -> int:
    """从 stdin 读 JSON 参数 → 调 run_fn → stdout 写 JSON 结果。"""
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("stdin 必须是 JSON 对象")
    except Exception as exc:
        print(json.dumps({"error": f"输入解析失败: {exc}"}, ensure_ascii=False))
        return 1

    try:
        result = run_fn(**payload)
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0
