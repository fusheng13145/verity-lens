"""Bundle 加载器：bundle.yml → HAL 注册（design-blueprint.md §2.6.3）。

职责边界（AGENTS.md 硬规则 1 依赖收敛）：
- Bundle 只做声明（bundle.yml），加载逻辑全部收敛在本模块（编排层）；
- 本模块只通过 HAL 接口与底座交互，禁止 import DSH 内部 API。

加载动作（按蓝图 §2.6.3）：
1. register_skills：注册 Bundle 声明的 Skill 目录；
2. declare_mcp_servers：注册 Bundle 声明的 MCP 服务（sidecar 确定性工具）；
3. apply_preset_patch：应用阶段化 Preset 补丁（学科方法论注入系统提示）。

降级策略（蓝图 §2.1 降级表；能力缺失必须显式记录，禁止静默失败）：
- mcp 能力缺失     → 跳过 MCP 声明，记录 degradation，改由编排层直连 sidecar 工具；
- preset_patch 缺失 → 跳过补丁，记录 degradation，建议改为启动参数注入系统提示。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from hal.dsh_adapter import DSHAdapter, PresetPatch
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
    preset: str = ""
    degradations: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


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


def _validate_mcp_servers(mcp: object) -> list[str]:
    """校验 MCP 声明结构（转发到 bundle_factory 的共享校验器）。"""
    return validate_mcp_declaration(mcp)


def _validate_preset_patch(patch: object) -> list[str]:
    """校验 Preset Patch 声明结构（转发到 bundle_factory 的共享校验器）。"""
    return validate_preset_patch_declaration(patch)


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
        if adapter.capabilities().get("mcp"):
            declared = adapter.declare_mcp_servers(mcp)
            report.mcp_servers = [s.get("name", "?") for s in declared.get("servers", [])]
        else:
            report.degradations.append(
                "底座不支持 mcp 能力：已跳过 MCP 声明（降级：编排层直连 sidecar 工具）"
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
            )
            adapter.apply_preset_patch(patch)
            report.preset = patch.preset
        else:
            report.degradations.append(
                "底座不支持 preset_patch 能力：已跳过补丁"
                "（降级：改为启动参数注入系统提示，见 design-blueprint.md §2.1 降级表）"
            )

    return report
