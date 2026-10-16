"""Preset Patch 机读校验 + DSH 配置 schema 钉固（design-blueprint.md §2.6.3 / Backlog C）。

背景：DSH `--dump-config-schema` 输出 Cordis 风格 schema（root 为 array，含 `$defs`），
而 verity 物化的 preset_patch（`preset` / `system_prompt` / `tool_whitelist`）是 verity 层抽象，
尚未映射为 DSH 真正接受的 Cordis 叠加层（patch 文件格式官方未公开）。

因此本模块做两件事（均不改变 `vl bundle load` 的默认行为）：
1. 对 verity 的 preset_patch 声明做**严格 JSON Schema 机读校验**（替代 bundle_factory 的
   ad-hoc 字符串检查），可离线、确定性、无底座依赖；
2. 在显式开启 `--check-patch-schema` 时，把真实 DSH 配置 schema **钉到磁盘**作为契约参考
   （填补「patch 文件结构官方未公开」的缺口，供后续 verity→Cordis 映射工作时核对）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PINNED_SCHEMA_PATH = REPO_ROOT / ".verity" / "dsh-config-schema.json"

#: verity 物化 preset_patch 的契约 schema（machine-readable contract）
VERITY_PRESET_PATCH_SCHEMA: dict = {
    "type": "object",
    "required": ["preset"],
    "additionalProperties": False,
    "properties": {
        "preset": {"type": "string", "minLength": 1},
        "system_prompt": {"type": "string"},
        "tool_whitelist": {"type": "array", "items": {"type": "string"}},
        "_note": {"type": "string"},
    },
}

def _type_ok(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def validate_preset_patch(patch: dict) -> list[str]:
    """按 `VERITY_PRESET_PATCH_SCHEMA` 严格校验 preset_patch 声明，返回问题列表（空=合规）。

    无外部依赖、确定性、可离线运行。覆盖：必填 `preset`、各字段类型、
    `tool_whitelist` 元素类型、`additionalProperties`（未知字段即报错）。
    """
    if not isinstance(patch, dict):
        return ["preset_patch 必须为映射"]
    problems: list[str] = []
    props = VERITY_PRESET_PATCH_SCHEMA["properties"]

    for key in VERITY_PRESET_PATCH_SCHEMA["required"]:
        if key not in patch or not patch[key]:
            problems.append(f"preset_patch.{key} 不能为空")

    for key, val in patch.items():
        if key not in props:
            problems.append(f"preset_patch 含未知字段: {key!r}（契约不允许）")
            continue
        spec = props[key]
        if not _type_ok(val, spec["type"]):
            problems.append(
                f"preset_patch.{key} 类型错误（期望 {spec['type']}，实际 {type(val).__name__}）"
            )
        if spec["type"] == "array" and not all(isinstance(item, str) for item in val):
            problems.append(f"preset_patch.{key} 每项必须为字符串")

    return problems


def pin_dsh_schema(
    adapter, profile: str = "headless", out_path: Path | None = None
) -> Path | None:
    """抓取真实 DSH 配置 schema 并钉到磁盘（契约参考）。

    依赖底座 `--dump-config-schema`（0.2.x 特性）；底座不可用 / 失败返回 None。
    默认落盘 `.verity/dsh-config-schema.json`（已被 .gitignore 忽略，属生成物）。
    """
    out_path = out_path or PINNED_SCHEMA_PATH
    schema = adapter.dump_config_schema(profile)
    if schema is None:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_path


def load_pinned_schema(path: Path | None = None) -> dict | None:
    path = path or PINNED_SCHEMA_PATH
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
