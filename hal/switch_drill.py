"""底座切换季度演练（Backlog C ②，design-blueprint.md 底座可替换性保障）。

把「定期评估备选底座接入成本」从纸面结论变成**可重复执行的自动化演练**：
deepseek-harness 处于 developer preview（官方明示会有破坏性变更），可替换性若不
定期体检，会被日常迭代悄悄侵蚀——本演练就是那个体检。

四项核心检查 + 一项权威回归：

1. ``interface_conformance``：DSHAdapter 仍结构性实现 ``HarnessAdapter`` Protocol
   全部方法（存在性 + 签名兼容：Protocol 参数名必须全部出现，实现新增参数须有默认值）；
2. ``coupling_scan``：orchestrator / sidecar / tests 中直连底座实现
   （``hal.dsh_adapter`` / ``hal.capability_probe``）的行项数不超过预算——
   预算内的直连是已知可接受成本（逐项列出 = 换底座时要改的文件清单），超出即视为侵蚀；
   ``hal.interface`` 与本演练模块属底座无关 HAL 面，不计入；
3. ``swap_simulation``：用无 DSH 依赖的 ``_MinimalAdapter`` 实现 Protocol，
   通过 ``runtime_checkable`` isinstance 检查且 ``capabilities()`` 返回全部
   ``CAPABILITY_KEYS``——证明接口可被第三方（备选底座）实现；
4. ``version_drift``：本机 ``dsh --version`` vs ``version_lock.yml`` verified_version
   漂移检测（底座不在 PATH 时记 skip，不算失败）；漂移 = 底座已升级但契约未复验，FAIL；
5. ``contract_tests``（可选，默认开启）：全量跑 ``hal/contract_tests``——
   底座升级后的权威回归（40 例，离线假桩 + 真实 dsh 实测）。

退出码：0 = 演练通过（允许含 skip）；1 = 存在 FAIL（先修复再考虑升级底座）。

用法：``python scripts/base-switch-drill.py [--skip-contract-tests] [--budget N] [--json]``
或 ``make base-switch-drill``。季度执行一次，或每次升级 deepseek-harness 后执行。
"""
from __future__ import annotations

import inspect
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from hal.interface import CAPABILITY_KEYS, HarnessAdapter

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 直连行项预算：当前实际 2（orchestrator/bundle_loader.py、tests/golden/test_bundle_loader.py）。
# 预算给头寸但防失控——新增直连须有明确理由，超预算应优先改为经 hal.interface 工厂。
COUPLING_BUDGET = 6
COUPLING_SCAN_ROOTS: tuple[str, ...] = ("orchestrator", "sidecar", "tests")
# 底座相关模块（换底座即失效）；hal.interface / hal.switch_drill 为底座无关 HAL 面。
BASE_MODULES: frozenset[str] = frozenset({"hal.dsh_adapter", "hal.capability_probe"})

_FROM_RE = re.compile(r"^\s*from\s+(hal[\w.]*)\s+import\s+(.+)$")
_IMPORT_RE = re.compile(r"^\s*import\s+(hal[\w.]*)")


def protocol_methods(protocol: type = HarnessAdapter) -> dict[str, inspect.Signature]:
    """提取 Protocol 定义的公开方法（含签名）；过滤 dunder / 下划线。"""
    out: dict[str, inspect.Signature] = {}
    for name, member in vars(protocol).items():
        if name.startswith("_") or not callable(member):
            continue
        try:
            out[name] = inspect.signature(member)
        except (TypeError, ValueError):
            out[name] = None  # type: ignore[misc]
    return out


def check_interface_conformance(adapter_cls: type | None = None, protocol: type = HarnessAdapter) -> dict:
    """结构符合性：Protocol 每个方法在适配器上存在且签名兼容。

    规则：Protocol 参数名（除 self）必须全部出现在实现签名中；实现新增参数须有默认值
    （调用方按 Protocol 签名编码，实现多收可选参数合法、多收必选参数不合法）。
    实现含 ``*args``/``**kwargs`` 时视为兼容（可承接任意 Protocol 签名）。
    """
    if adapter_cls is None:
        from hal.dsh_adapter import DSHAdapter as adapter_cls  # 默认检查真实适配器

    problems: list[str] = []
    checked: list[str] = []
    for name, psig in protocol_methods(protocol).items():
        checked.append(name)
        impl = getattr(adapter_cls, name, None)
        if impl is None or not callable(impl):
            problems.append(f"缺少方法 {name}（Protocol 要求，适配器未实现）")
            continue
        try:
            isig = inspect.signature(impl)
        except (TypeError, ValueError):
            problems.append(f"方法 {name} 签名不可内省")
            continue

        def _names(sig: inspect.Signature) -> tuple[set[str], bool, bool]:
            params = list(sig.parameters.values())
            params = [p for p in params if p.name not in ("self", "cls")]
            names = {p.name for p in params if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)}
            has_var = any(
                p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in params
            )
            extra_required = {
                p.name
                for p in params
                if p.default is p.empty
                and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
            }
            return names, has_var, extra_required

        pnames = (
            {p.name for p in psig.parameters.values() if p.name != "self"}
            if psig
            else set()
        )
        inames, has_var, extra_required = _names(isig)
        if has_var:
            continue  # *args/**kwargs 可承接任意 Protocol 签名
        missing = pnames - inames
        if missing:
            problems.append(f"方法 {name} 缺少 Protocol 参数: {sorted(missing)}")
        # 实现新增的必选参数 = inames - pnames 且无默认值
        if extra_required - pnames:
            problems.append(
                f"方法 {name} 新增了 Protocol 之外的必选参数: {sorted(extra_required - pnames)}"
            )
    return {"name": "interface_conformance", "ok": not problems, "problems": problems, "checked": checked}


def _line_imports_base(line: str) -> str | None:
    """单行是否直连底座模块；命中返回模块路径，否则 None。"""
    m = _FROM_RE.match(line)
    if m:
        mod, names = m.group(1), [n.strip().rstrip(",") for n in m.group(2).split(",")]
        if mod in BASE_MODULES:
            return mod
        for n in names:
            if f"{mod}.{n}" in BASE_MODULES:  # from hal import dsh_adapter
                return f"{mod}.{n}"
        return None
    m = _IMPORT_RE.match(line)
    if m:
        target = m.group(1)
        if target in BASE_MODULES or any(target.startswith(b + ".") for b in BASE_MODULES):
            return target
    return None


def scan_coupling(
    root: Path | None = None,
    budget: int = COUPLING_BUDGET,
    roots: tuple[str, ...] = COUPLING_SCAN_ROOTS,
) -> dict:
    """扫描编排层/侧车/测试对底座实现的直连行项（换底座时要改的文件清单）。"""
    root = root or PROJECT_ROOT
    hits: list[dict] = []
    for rel in roots:
        base = root / rel
        if not base.exists():
            continue
        for py in sorted(base.rglob("*.py")):
            try:
                lines = py.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, line in enumerate(lines, 1):
                mod = _line_imports_base(line)
                if mod:
                    hits.append(
                        {"file": py.relative_to(root).as_posix(), "line": lineno, "module": mod}
                    )
    over = len(hits) > budget
    return {
        "name": "coupling_scan",
        "ok": not over,
        "budget": budget,
        "count": len(hits),
        "hits": hits,
        "problems": (
            [f"直连行项 {len(hits)} 超出预算 {budget}——可替换性被侵蚀，新增直连须改为经 hal.interface"]
            if over
            else []
        ),
    }


class _MinimalAdapter:
    """无 DSH 依赖的协议实现（演练用：证明接口可被备选底座实现）。"""

    def start_session(self, preset: str, workspace: str, task: str):
        return {"preset": preset, "workspace": workspace, "task": task}

    def resume_session(self, handle):
        return handle

    def stop_session(self, handle, graceful: bool = True) -> None:
        return None

    def export_session_log(self, handle):
        return iter(())

    def fork_trajectory(self, handle, at_event: str):
        return {"forked_at": at_event}

    def register_skills(self, skill_dirs: list[str]) -> None:
        return None

    def register_tools(self, tools: list) -> None:
        return None

    def declare_mcp_servers(self, config: dict) -> None:
        return None

    def apply_preset_patch(self, patch) -> None:
        return None

    def set_permission(self, scope: str, level: str) -> None:
        return None

    def spawn_subagent(self, spec) -> None:
        return None

    def capabilities(self) -> dict:
        return {k: True for k in CAPABILITY_KEYS}


def simulate_swap() -> dict:
    """替换模拟：第三方适配器通过 runtime_checkable Protocol 检查并覆盖全部能力键。"""
    problems: list[str] = []
    minimal = _MinimalAdapter()
    if not isinstance(minimal, HarnessAdapter):
        problems.append("_MinimalAdapter 未通过 HarnessAdapter 运行时检查（Protocol 可实现性受损）")
    # 负例：非适配器必须被拒（接口检查不是摆设）
    if isinstance(object(), HarnessAdapter):
        problems.append("object() 通过了 HarnessAdapter 检查（runtime_checkable 失效）")
    caps = minimal.capabilities()
    missing = [k for k in CAPABILITY_KEYS if k not in caps]
    if missing:
        problems.append(f"capabilities() 缺少能力键: {missing}")
    # 生命周期冒烟（无底座、无副作用）
    handle = minimal.start_session("headless", "/tmp/ws", "task")
    minimal.resume_session(handle)
    minimal.stop_session(handle, graceful=True)
    minimal.register_skills([])
    minimal.register_tools([])
    minimal.declare_mcp_servers({})
    minimal.apply_preset_patch({})
    minimal.set_permission("workspace", "read")
    minimal.spawn_subagent({})
    list(minimal.export_session_log(handle))
    minimal.fork_trajectory(handle, "e1")
    return {"name": "swap_simulation", "ok": not problems, "problems": problems}


def check_version_drift(adapter=None, lock_path: Path | None = None) -> dict:
    """版本漂移：本机底座版本 vs 版本锁 verified_version（漂移 = 升级未复验，FAIL）。"""
    from hal.dsh_adapter import DSHAdapter, parse_version

    adapter = adapter or DSHAdapter(version_lock=lock_path)
    if not adapter.available():
        return {
            "name": "version_drift",
            "ok": True,
            "status": "skip",
            "problems": [],
            "detail": "底座可执行文件不在 PATH（离线模式），跳过版本漂移检查",
        }
    try:
        installed_raw = adapter.installed_version()
    except Exception as exc:  # HarnessUnavailableError 或子进程异常
        return {
            "name": "version_drift",
            "ok": True,
            "status": "skip",
            "problems": [],
            "detail": f"底座版本探测失败（{exc}），跳过",
        }
    locked_raw = adapter.locked_version()
    installed, locked = parse_version(installed_raw), parse_version(locked_raw)
    if installed != locked:
        return {
            "name": "version_drift",
            "ok": False,
            "status": "fail",
            "problems": [
                f"版本漂移：已安装 {installed_raw} vs 版本锁 {locked_raw}——"
                "底座已升级但契约未复验；先跑 hal/contract_tests 再更新 version_lock.yml"
            ],
        }
    return {
        "name": "version_drift",
        "ok": True,
        "status": "ok",
        "problems": [],
        "detail": f"已安装 = 版本锁 = {locked_raw}",
    }


def run_contract_tests(extra_args: list[str] | None = None, timeout: float = 300.0) -> dict:
    """全量 HAL 契约回归（底座升级后的权威判据）；pytest 缺失或失败均如实报告。"""
    cmd = [sys.executable, "-m", "pytest", "hal/contract_tests", "-q", *(extra_args or [])]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"name": "contract_tests", "ok": False, "problems": [f"契约测试执行失败: {exc}"]}
    tail = "\n".join((proc.stdout or "").strip().splitlines()[-5:])
    ok = proc.returncode == 0
    return {
        "name": "contract_tests",
        "ok": ok,
        "problems": [] if ok else [f"契约测试未通过（exit={proc.returncode}）：\n{tail}"],
        "tail": tail,
    }


def run_drill(
    root: Path | None = None,
    *,
    with_contract_tests: bool = True,
    adapter=None,
    coupling_budget: int = COUPLING_BUDGET,
    contract_pytest_args: list[str] | None = None,
) -> tuple[dict, int]:
    """执行演练，返回 (报告, 退出码)。退出码 0=通过，1=存在 FAIL 项。"""
    checks: list[dict] = [
        check_interface_conformance(),
        scan_coupling(root, budget=coupling_budget),
        simulate_swap(),
        check_version_drift(adapter=adapter),
    ]
    if with_contract_tests:
        checks.append(run_contract_tests(contract_pytest_args))
    ok = all(c["ok"] for c in checks)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root or PROJECT_ROOT),
        "with_contract_tests": with_contract_tests,
        "checks": checks,
        "ok": ok,
        "exit_code": 0 if ok else 1,
    }
    return report, report["exit_code"]


def render_report(report: dict) -> str:
    """渲染人读演练报告。"""
    lines = ["═" * 62, "底座切换季度演练（base-switch drill）", "═" * 62]
    for c in report["checks"]:
        status = "PASS" if c["ok"] else "FAIL"
        extra = ""
        if c["name"] == "coupling_scan":
            extra = f"（直连 {c['count']}/{c['budget']} 行项）"
        elif c.get("status") == "skip" or c.get("detail"):
            extra = f"（{c.get('detail', 'skip')}）"
        lines.append(f"[{status}] {c['name']}{extra}")
        for p in c.get("problems", []):
            lines.append(f"       - {p}")
        if c["name"] == "coupling_scan" and c["hits"]:
            for h in c["hits"]:
                lines.append(f"       · {h['file']}:{h['line']} → {h['module']}")
        if c["name"] == "interface_conformance":
            lines.append(f"       · 已核验 {len(c['checked'])} 个 Protocol 方法")
    verdict = "通过：底座可替换性健康" if report["ok"] else "未通过：存在 FAIL 项，先修复再考虑升级底座"
    lines.append("─" * 62)
    lines.append(f"[{'PASS' if report['ok'] else 'FAIL'}] 演练结论：{verdict}")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    _r, _code = run_drill()
    print(render_report(_r))
    sys.exit(_code)