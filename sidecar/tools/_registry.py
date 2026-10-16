"""Sidecar 工具注册表（供长驻守护进程与 CLI 分发）。

集中登记各工具的「调用入口 + 规格」，使 ``daemon`` / ``cli`` 无需散落 import。
新增工具只需在此登记一处；``TOOL_SPEC`` 以各工具模块内声明为单一真相。
"""
from __future__ import annotations

from typing import Callable


def _plot_dispatch(params: dict) -> dict:
    """plot 的入口是 ``render``（返回 Path），统一包装为 {path: ...}。"""
    from sidecar.tools.plot import render

    out = render(
        params["csv_path"],
        params["out_path"],
        kind=params.get("kind", "bar"),
        title=params.get("title", ""),
    )
    return {"path": str(out)}


def _resolve(name: str) -> Callable[[dict], dict]:
    """返回 tool 名对应的分发函数（params: dict -> result: dict）。"""
    if name == "plot":
        return _plot_dispatch
    if name == "doi_verify":
        from sidecar.tools.doi_verify import run as _run

        return lambda p: _run(**p)
    if name == "stat_test":
        from sidecar.tools.stat_test import run as _run

        return lambda p: _run(**p)
    if name == "power_analysis":
        from sidecar.tools.power_analysis import run as _run

        return lambda p: _run(**p)
    if name == "hpc_submit":
        from sidecar.tools.hpc_submit import run as _run

        return lambda p: _run(**p)
    if name == "desensitize":
        from sidecar.tools.desensitize import run as _run

        return lambda p: _run(**p)
    raise KeyError(name)


def list_tools() -> list[str]:
    """已登记且可导入的工具名列表（导入失败的工具自动剔除，不阻断守护进程）。"""
    names = ["plot", "doi_verify", "stat_test", "power_analysis", "hpc_submit", "desensitize"]
    ok: list[str] = []
    for n in names:
        try:
            _resolve(n)
            ok.append(n)
        except Exception:
            continue
    return ok


def dispatch(name: str, params: dict) -> dict:
    """分发一次工具调用；未知工具 / 参数错误以异常形式交给调用方格式化。"""
    return _resolve(name)(params or {})


def spec_of(name: str) -> dict | None:
    """返回工具的 TOOL_SPEC（用于守护进程就绪握手与 MCP 声明）。"""
    modules = {
        "plot": "sidecar.tools.plot",
        "doi_verify": "sidecar.tools.doi_verify",
        "stat_test": "sidecar.tools.stat_test",
        "power_analysis": "sidecar.tools.power_analysis",
        "hpc_submit": "sidecar.tools.hpc_submit",
        "desensitize": "sidecar.tools.desensitize",
    }
    mod_name = modules.get(name)
    if not mod_name:
        return None
    try:
        import importlib

        mod = importlib.import_module(mod_name)
        return getattr(mod, "TOOL_SPEC", None)
    except Exception:
        return None
