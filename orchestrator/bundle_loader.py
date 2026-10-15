"""Bundle 加载器：bundle.yml → HAL 注册（design-blueprint.md §2.6.3）。

职责边界（AGENTS.md 硬规则 1 依赖收敛）：
- Bundle 只做声明（bundle.yml），加载逻辑全部收敛在本模块（编排层）；
- 本模块只通过 HAL 接口与底座交互，禁止 import DSH 内部 API。

加载动作（按蓝图 §2.6.3）：
1. register_skills：注册 Bundle 声明的 Skill 目录；
2. declare_mcp_servers：把 Bundle 声明映射为 DSH mcp-client 真实配置后注册；
3. apply_preset_patch：应用阶段化 Preset 补丁（对应 DSH `--patch <path>` 叠加层）。

声明格式与底座格式的差异由本模块吸收（映射表见 `to_dsh_mcp_config`）：
    Bundle（人读）              → DSH mcp-client StdioConfig（机器）
    servers[].name              → serverName（[A-Za-z0-9_-]{1,32}）
    servers[].command（数组）   → command（字符串）+ args（字符串数组）
    servers[].tools             → 模型可见工具名 mcp__<serverName>__<rawName>

降级策略（蓝图 §2.1 降级表；能力缺失必须显式记录，禁止静默失败）：
- mcp 能力缺失     → 跳过 MCP 声明，记录 degradation，改由编排层直连 sidecar 工具；
- preset_patch 缺失 → 跳过补丁，记录 degradation，建议改为启动参数注入系统提示。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from hal.dsh_adapter import DSHAdapter, PresetPatch, model_tool_name
from orchestrator.bundle_factory import (
    validate_bundle,
    validate_mcp_declaration,
    validate_preset_patch_declaration,
)

MANIFEST_NAME = "bundle.yml"


class BundleLoadError(RuntimeError):
    """Bundle 无法加载（清单缺失 / 解析失败 / 结构不合规）。"""


@dataclass
class LoadReport:
    """一次 Bundle 加载的结果留痕（供 vl bundle load 输出与测试断言）。"""

    bundle: str
    level: str
    skills: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)
    model_tools: list[str] = field(default_factory=list)
    preset: str = ""
    patch_path: str = ""
    degradations: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def to_dsh_mcp_config(mcp: dict) -> dict:
    """Bundle 的 MCP 声明 → DSH mcp-client StdioConfig（真实键）。

    依据 deepseek-ai/deepseek-harness docs/config-catalog.md：
    StdioConfig = {transport:'stdio', serverName, command, args, env?, cwd?,
                   toolCallTimeoutMs, failOnStartupError, maxInstructionBytes?, reconnect?}
    serverName 约束 `[A-Za-z0-9_-]{1,32}`，模型可见工具名为 mcp__<serverName>__<rawName>。
    """
    servers: list[dict] = []
    for srv in mcp.get("servers") or []:
        command = srv.get("command")
        if isinstance(command, str):
            cmd, args = command, list(srv.get("args", []))
        else:  # Bundle 侧写法：["python", "-m", "sidecar.tools.stat_test"]
            seq = list(command or [])
            cmd, args = (seq[0] if seq else ""), seq[1:]
        entry = {
            "transport": srv.get("transport", "stdio"),
            "serverName": srv.get("name", ""),
            "command": cmd,
            "args": args,
        }
        for key in ("toolCallTimeoutMs", "failOnStartupError", "env", "cwd"):
            if srv.get(key) is not None:
                entry[key] = srv[key]
        servers.append(entry)
    return {"servers": servers}


def model_tool_names(bundle_mcp: dict) -> list[str]:
    """展开 Bundle 声明的 MCP 服务将暴露给模型的工具名（mcp__<serverName>__<rawName>）。"""
    names: list[str] = []
    for srv in bundle_mcp.get("servers", []):
        for raw in srv.get("tools") or ["*"]:
            names.append(model_tool_name(srv.get("name", ""), raw))
    return names


def _validate_mcp_servers(mcp: object) -> list[str]:
    """校验 MCP 声明结构（转发到 bundle_factory 的共享校验器）。"""
    return validate_mcp_declaration(mcp)


def _validate_preset_patch(patch: object) -> list[str]:
    """校验 Preset Patch 声明结构（转发到 bundle_factory 的共享校验器）。"""
    return validate_preset_patch_declaration(patch)


def load_manifest(bundle_dir: Path | str) -> dict:
    """读取并解析 bundle.yml。"""
    manifest = Path(bundle_dir) / MANIFEST_NAME
    if not manifest.exists():
        raise BundleLoadError(f"缺少 {MANIFEST_NAME}: {manifest}")
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise BundleLoadError(f"{MANIFEST_NAME} 解析失败: {exc}") from exc
    if not isinstance(data, dict):
        raise BundleLoadError(f"{MANIFEST_NAME} 顶层必须为映射")
    return data


def load_bundle(bundle_dir: Path | str, adapter: DSHAdapter | None = None) -> LoadReport:
    """把 Bundle 注册到运行底座，返回加载报告。

    结构不合规时直接返回带 problems 的报告（不注册任何内容）。
    能力缺失时降级并记录到 degradations（不静默）。
    """
    d = Path(bundle_dir)
    adapter = adapter or DSHAdapter()

    problems = validate_bundle(d)
    report = LoadReport(bundle=d.name, level="?")
    if problems:
        report.problems = problems
        return report

    manifest = load_manifest(d)
    report.level = str(manifest.get("level"))

    # ── 1. Skill 注册 ──────────────────────────────────────────────
    skills_dir = d / "skills"
    if skills_dir.is_dir():
        report.skills = [str(p) for p in adapter.register_skills([str(skills_dir)])]
    else:
        report.problems.append(f"缺少 skills 目录: {skills_dir}")
        return report

    # ── 2. MCP 声明（L2） ─────────────────────────────────────────
    mcp = manifest.get("mcp")
    if mcp:
        mcp_problems = _validate_mcp_servers(mcp)
        if mcp_problems:
            report.problems.extend(mcp_problems)
            return report
        # 无论底座是否可用都做映射校验：配置形状错误必须立刻暴露，而不是
        # 等到真机联调才发现 serverName/command 形状不合法。
        dsh_mcp = to_dsh_mcp_config(mcp)
        if adapter.capabilities().get("mcp"):
            declared = adapter.declare_mcp_servers(dsh_mcp)
            report.mcp_servers = [s["serverName"] for s in declared.get("servers", [])]
            report.model_tools = model_tool_names(mcp)
        else:
            report.degradations.append(
                "底座不支持 mcp 能力：已跳过 MCP 声明"
                "（降级：编排层直连 sidecar 工具，见 design-blueprint.md §2.1 降级表）"
            )

    # ── 3. Preset Patch（L2） ─────────────────────────────────────
    patch_data = manifest.get("preset_patch")
    if patch_data:
        patch_problems = _validate_preset_patch(patch_data)
        if patch_problems:
            report.problems.extend(patch_problems)
            return report
        if adapter.capabilities().get("preset_patch"):
            patch = PresetPatch(
                preset=str(patch_data["preset"]),
                system_prompt=str(patch_data.get("system_prompt", "")),
                tool_whitelist=list(patch_data.get("tool_whitelist", [])),
                scope=report.bundle,  # 学科前缀：三学科同 preset 名时叠加层互不覆盖
            )
            adapter.apply_preset_patch(patch)
            report.preset = patch.preset
            report.patch_path = str(patch.path) if patch.path else ""
        else:
            report.degradations.append(
                "底座不支持 preset_patch 能力：已跳过补丁"
                "（降级：改为启动参数注入系统提示，见 design-blueprint.md §2.1 降级表）"
            )

    return report
