"""身份解析与可信度分级（orchestrator/identity.py）。

对应 docs/collab.md §7.8（协作模型重评估 P0：身份可信化）。

问题：当前协作身份仅靠 ``VL_USER`` 环境变量（口头约定）+ git committer（``git config
user.*``，可伪造）。多人时写锁互斥 / committer 比对都是「自报家门」，A 标自己为 B 即可绕过。

本模块把身份从「自由字符串」升级为**可解析、可分级、可强制**的结构：
- ``resolve_identity`` 读取 ``VL_USER`` 与 git committer，做规范化比对，给出 ``coherent`` 与 ``trust_level``。
- ``commit_signature_status`` 读取最新提交签名状态（GPG/SSH），作为**密码学锚点**
  （git config 可伪造，但签名密钥不可伪造 —— 这是真正可信的身份来源）。
- ``trust_level``：``unverified`` / ``self_attested``（自报一致，但可伪造）/ ``mismatch``
  （设了但不一致）/ ``signed_verified``（签名有效 **且** 与 VL_USER 一致）。

本模块不引入外部依赖，``git`` 调用通过 ``git_runner`` 注入便于单测；读 ``VL_USER`` 走真实环境。
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

# 签名状态字母（git log --pretty=%G?）
# G=有效签名 U=密钥不在钥匙圈 B=签名损坏 N=无签名 E=校验错误
_GOOD = "G"


def _real_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


def _norm(s: Optional[str]) -> str:
    return (s or "").strip().lower()


@dataclass
class Identity:
    vl_user: Optional[str]
    committer_name: Optional[str]
    committer_email: Optional[str]
    coherent: bool
    signature: dict
    trust_level: str
    verdict: str

    def to_dict(self) -> dict:
        return asdict(self)


def _trust_level(vl_set: bool, coherent: bool, sig_status: str) -> str:
    """由要素推导可信度等级。"""
    if sig_status == _GOOD and coherent:
        return "signed_verified"  # 密码学锚定 + 与 VL_USER 一致（最强）
    if coherent:
        return "self_attested"  # VL_USER 与 git committer 一致，但 git config 可伪造
    if vl_set:
        return "mismatch"  # 设了 VL_USER 但与 committer 不符（冒充/配置漂移）
    return "unverified"  # 连 VL_USER 都没设


def _verdict(trust_level: str) -> str:
    return {
        "signed_verified": "pass",
        "self_attested": "warn",
        "mismatch": "fail",
        "unverified": "warn",
    }[trust_level]


def commit_signature_status(
    cwd: Path,
    git_runner: Callable = _real_git,
) -> dict:
    """读取当前仓库最新提交的签名状态（GPG/SSH）。

    返回 ``{"signed": bool, "status": str, "key": str|None}``。
    无提交 / git 不可用时 ``status="N"``、``signed=False``。
    """
    res = git_runner(
        ["log", "-1", "--pretty=%G?%n%GK"],
        cwd=cwd,
    )
    if res.returncode != 0:
        return {"signed": False, "status": "N", "key": None}
    lines = [ln for ln in res.stdout.splitlines()]
    status = lines[0].strip() if lines else "N"
    key = lines[1].strip() if len(lines) > 1 else ""
    return {
        "signed": status in ("G", "U", "B"),
        "status": status or "N",
        "key": key or None,
    }


def resolve_identity(
    cwd: Path,
    vl_user: Optional[str] = None,
    git_runner: Callable = _real_git,
) -> Identity:
    """解析当前身份并分级。

    ``vl_user`` 缺省时从环境变量 ``VL_USER`` 读取（允许单测直接注入）。
    committer 经 ``orchestrator.collab.current_committer`` 读取（同一 git_runner 注入）。
    """
    from orchestrator.collab import current_committer

    if vl_user is None:
        vl_user = os.environ.get("VL_USER")

    committer = current_committer(cwd, git_runner=git_runner) or {}
    cn = committer.get("name")
    ce = committer.get("email")

    coherent = bool(vl_user) and (
        _norm(vl_user) == _norm(cn) or _norm(vl_user) == _norm(ce)
    )
    sig = commit_signature_status(cwd, git_runner=git_runner)
    trust_level = _trust_level(bool(vl_user), coherent, sig["status"])
    return Identity(
        vl_user=vl_user,
        committer_name=cn,
        committer_email=ce,
        coherent=coherent,
        signature=sig,
        trust_level=trust_level,
        verdict=_verdict(trust_level),
    )


def render_report(ident: Identity) -> str:
    """人类可读的身份报告。"""
    sig = ident.signature
    return "\n".join(
        [
            f"[identity] VL_USER       : {ident.vl_user or '(未设置)'}",
            f"[identity] git committer : name={ident.committer_name or '?'} "
            f"email={ident.committer_email or '?'}",
            f"[identity] coherent      : {'yes' if ident.coherent else 'no'}",
            f"[identity] signature     : status={sig['status']} "
            f"signed={sig['signed']} key={sig['key'] or '-'}",
            f"[identity] trust_level   : {ident.trust_level}",
            f"[identity] verdict       : {ident.verdict}",
        ]
    )
