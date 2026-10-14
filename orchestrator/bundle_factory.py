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


def validate_bundle(bundle_dir: Path | str) -> list[str]:
    """校验 Bundle 结构是否合规，返回问题列表（空=通过）。"""
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

    return problems
