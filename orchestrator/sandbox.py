"""容器沙箱生成器（orchestrator/sandbox.py）。

依据 design-blueprint.md §2.8.2 生成强隔离的科研代码执行沙箱 compose 文件。
要点：no-new-privileges / cap_drop ALL / network_mode none / read_only / tmpfs /
资源硬限制；原始敏感数据（data/raw）以只读挂载，脱敏产物（data/processed）可写。

本模块纯函数优先：render_compose() 返回 YAML 文本，文件写入由 generate() 负责，
便于单测（无需 docker）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

TEMPLATE = """\
# 自动生成（orchestrator/sandbox.py）—— 项目 {project_id}
# 安全基线见 design-blueprint.md §2.8.2；如需联网拉依赖临时放开 network_mode。
services:
  dsh-sandbox:
    image: python:3.13-slim
    security_opt:
      - no-new-privileges:true
      - seccomp=unconfined
    cap_drop: ["ALL"]
    cap_add: ["CHOWN"]
    network_mode: "none"
    read_only: true
    tmpfs:
      - /tmp:size=1g
      - /var/tmp:size=512m
    volumes:
      - {root}/data/raw:/workspace/data/raw:ro
      - {root}/data/processed:/workspace/data/processed:rw
      - {root}/figures:/workspace/figures:rw
      - {root}/manuscript:/workspace/manuscript:rw
      - {root}/analysis:/workspace/analysis:rw
    deploy:
      resources:
        limits:
          cpus: "4"
          memory: "8g"
          pids: 100
    environment:
      - DSH_WORKSPACE=/workspace
      - DSH_PERMISSION=workspace_write
    init: true
    restart: "no"
    working_dir: /workspace
    command: ["python", "-c", "print('sandbox ready')"]
"""

REQUIRED_DIRS = ("data/raw", "data/processed", "figures", "manuscript", "analysis")


def render_compose(project_id: str, workspace_root: str = "workspaces") -> str:
    """渲染沙箱 compose 文本（PROJECT_ID 已内联）。"""
    if not project_id:
        raise ValueError("project_id 不可为空")
    root = f"{workspace_root}/{project_id}"
    return TEMPLATE.format(project_id=project_id, root=root)


def missing_host_dirs(project_id: str, workspace_root: str = "workspaces") -> list[str]:
    """返回宿主机上尚未创建的必需目录（相对路径列表）。"""
    base = Path(workspace_root) / project_id
    return [d for d in REQUIRED_DIRS if not (base / d).exists()]


def generate(
    project_id: str,
    workspace_root: str = "workspaces",
    out_dir: str = "docker",
) -> Path:
    """生成 project 专属 compose 文件并写入 out_dir。

    返回写出路径。若宿主必需目录缺失，仍会写出（沙箱首次运行前需先创建）。
    """
    text = render_compose(project_id, workspace_root=workspace_root)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / f"sandbox-compose.{project_id}.yml"
    dest.write_text(text, encoding="utf-8")
    return dest


def validate_compose(text: str) -> list[str]:
    """静态校验 compose 文本是否满足最小安全基线（不依赖 docker）。"""
    problems: list[str] = []
    checks: Iterable[tuple[str, str]] = (
        ("no-new-privileges", "缺少 no-new-privileges"),
        ('cap_drop', "缺少 cap_drop"),
        ("network_mode: \"none\"", "未禁用网络（network_mode: none）"),
        ("read_only: true", "根文件系统未设为只读"),
        ("data/raw:/workspace/data/raw:ro", "原始数据未以只读挂载"),
        ("pids: 100", "缺少 pids 资源限制"),
    )
    for needle, msg in checks:
        if needle not in text:
            problems.append(msg)
    return problems
