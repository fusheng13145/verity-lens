"""Bundle 工厂：半自动生成学科 L0 Bundle 骨架。

设计依据（design-blueprint.md §2.6）：
新学科一律从 L0 起步（bundle.yml + 1 份 SKILL.md，复用通用验证脚本），
不引入 Preset Patch 与 MCP；专家只填领域知识，结构由生成器保证一致。

流程：
  专家访谈提纲（模板见 INTERVIEW_TEMPLATE）→ vl bundle new <discipline> → L0 骨架
  → 专家评审 SKILL.md → 工程师补验证脚本（L0→L1）→ Golden 用例（L1→L2）
"""
from __future__ import annotations

import shutil
from pathlib import Path

from orchestrator.gates import compute_facts, load_project

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "bundles" / "_template"
TEMPLATE_SKILL_DIRNAME = "capability"

INTERVIEW_TEMPLATE = """# 领域专家访谈提纲（新学科接入）

1. 该学科典型研究流程包含哪些阶段？各阶段产出物是什么？
2. 有哪些必须报告的指标？（如效应量、CI、p 值、AUC、敏感度/特异度）
3. 常见的可验证错误有哪些？（方法误用、统计错误、参数缺失）
4. 该领域公认的报告规范/标准？（如 CONSORT / STROBE / PRISMA）
5. 核心术语与缩写清单？（用于术语表）
6. 典型可视化图表类型与必标要素？
"""


class BundleExistsError(RuntimeError):
    """目标 Bundle 已存在。"""


def _substitute(text: str, mapping: dict[str, str]) -> str:
    for token, value in mapping.items():
        text = text.replace(token, value)
    return text


def _substitute_tree(root: Path, mapping: dict[str, str],
                     suffixes: tuple[str, ...] = (".yml", ".yaml", ".md", ".json")) -> None:
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in suffixes:
            p.write_text(_substitute(p.read_text(encoding="utf-8"), mapping), encoding="utf-8")


def new_bundle(discipline: str, target_dir: Path | str, capability: str = "core") -> Path:
    """基于 _template 生成 L0 Bundle 骨架。

    :param discipline: 学科标识（如 biomed / materials）
    :param target_dir: Bundle 根目录（通常为 bundles/）
    :param capability: 首个 Skill 的能力名，Skill 目录 = <discipline>-<capability>
    """
    dest = Path(target_dir) / discipline
    if dest.exists():
        raise BundleExistsError(f"Bundle 已存在: {dest}")

    shutil.copytree(TEMPLATE_DIR, dest)

    # 重命名占位 Skill 目录：skills/capability → skills/<discipline>-<capability>
    old = dest / "skills" / TEMPLATE_SKILL_DIRNAME
    new = dest / "skills" / f"{discipline}-{capability}"
    if old.exists():
        old.rename(new)

    _substitute_tree(dest, {"${DISCIPLINE}": discipline, "${CAPABILITY}": capability})
    return dest


def validate_preset_patch_declaration(patch: object) -> list[str]:
    """校验 preset_patch 声明结构，返回问题列表（空=合规）。

    结构约定（L2 必需，bundle-registry.md §3）：
        preset_patch:
          preset: "verity-research"      # 必填：目标 Preset 名
          system_prompt: "..."           # 可选：注入系统提示的片段
          tool_whitelist: ["stat_test"]  # 可选：工具白名单
    """
    if not isinstance(patch, dict):
        return ["preset_patch 必须为映射"]
    problems: list[str] = []
    if not patch.get("preset"):
        problems.append("preset_patch.preset 不能为空")
    if not isinstance(patch.get("tool_whitelist", []), list):
        problems.append("preset_patch.tool_whitelist 必须为列表")
    return problems


def validate_mcp_declaration(mcp: object) -> list[str]:
    """校验 mcp 声明结构，返回问题列表（空=合规）。

    结构约定（L2 必需，bundle-registry.md §3）：
        mcp:
          servers:
            - name: "verity-stat-test"
              command: ["python", "-m", "sidecar.tools.stat_test"]
              tools: ["stat_test"]
    """
    if not isinstance(mcp, dict):
        return ["mcp 必须为映射（含 servers 列表）"]
    servers = mcp.get("servers")
    if not isinstance(servers, list) or not servers:
        return ["mcp.servers 必须为非空列表"]
    problems: list[str] = []
    for i, srv in enumerate(servers):
        if not isinstance(srv, dict):
            problems.append(f"mcp.servers[{i}] 必须为映射")
            continue
        if not srv.get("name"):
            problems.append(f"mcp.servers[{i}] 缺少 name")
        if not srv.get("command") and not srv.get("url"):
            problems.append(f"mcp.servers[{i}] 缺少 command/url")
    return problems


def validate_bundle(bundle_dir: Path | str) -> list[str]:
    """校验 Bundle 结构是否合规，返回问题列表（空=通过）。

    L2 追加规则（design-blueprint.md §2.6）：preset_patch + mcp 声明 +
    golden_cases 三者齐备且文件存在，否则不得标称 L2。
    """
    d = Path(bundle_dir)
    problems: list[str] = []

    manifest = d / "bundle.yml"
    if not manifest.exists():
        return [f"缺少 bundle.yml: {manifest}"]

    try:
        import yaml

        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return [f"bundle.yml 解析失败: {exc}"]

    for field in ("name", "level", "discipline", "skills"):
        if field not in data:
            problems.append(f"bundle.yml 缺少字段: {field}")

    if data.get("level") not in ("L0", "L1", "L2"):
        problems.append(f"level 非法（应为 L0/L1/L2）: {data.get('level')!r}")

    for rel in data.get("skills") or []:
        if not (d / rel).exists():
            problems.append(f"声明的 Skill 不存在: {rel}")

    if data.get("level") == "L2":
        if not data.get("preset_patch"):
            problems.append("L2 必须声明 preset_patch")
        else:
            problems.extend(validate_preset_patch_declaration(data["preset_patch"]))
        if not data.get("mcp"):
            problems.append("L2 必须声明 mcp")
        else:
            problems.extend(validate_mcp_declaration(data["mcp"]))
        golden = data.get("golden_cases")
        if not isinstance(golden, list) or not golden:
            problems.append("L2 必须声明 golden_cases（非空列表）")
        else:
            for rel in golden:
                if not (d / rel).exists():
                    problems.append(f"golden_cases 文件不存在: {rel}")

    return problems
