"""身份解析与可信度分级测试（orchestrator/identity.py）。

git 调用通过假 runner 注入，无需真实仓库；CLI 测试通过替换 resolve_identity 隔离。
"""
from types import SimpleNamespace
from pathlib import Path

from orchestrator.identity import Identity, commit_signature_status, resolve_identity

CWD = Path("/tmp/fake-repo")


class FakeGit:
    def __init__(self, name=None, email=None, sig_status="N", sig_key=None, returncode=0):
        self.name = name
        self.email = email
        self.sig_status = sig_status
        self.sig_key = sig_key
        self.returncode = returncode

    def __call__(self, args, cwd):
        class R:
            pass

        r = R()
        if args[:2] == ["config", "user.name"]:
            r.stdout = self.name or ""
        elif args[:2] == ["config", "user.email"]:
            r.stdout = self.email or ""
        elif args[:1] == ["log"]:  # --pretty=%G?%n%GK
            r.stdout = f"{self.sig_status}\n{self.sig_key or ''}\n"
        else:
            r.stdout = ""
        r.returncode = self.returncode
        r.stderr = ""
        return r


def _ident(**kw) -> Identity:
    base = dict(
        vl_user=None,
        committer_name=None,
        committer_email=None,
        coherent=False,
        signature={"signed": False, "status": "N", "key": None},
        trust_level="unverified",
        verdict="warn",
    )
    base.update(kw)
    return Identity(**base)


# ── resolve_identity 分级逻辑 ──────────────────────────────────────────────

def test_unverified_when_no_vl_user(monkeypatch):
    monkeypatch.delenv("VL_USER", raising=False)
    ident = resolve_identity(CWD, vl_user=None, git_runner=FakeGit())
    assert ident.trust_level == "unverified"
    assert ident.verdict == "warn"
    assert ident.coherent is False


def test_self_attested_by_name(monkeypatch):
    monkeypatch.delenv("VL_USER", raising=False)
    ident = resolve_identity(
        CWD, vl_user="alice", git_runner=FakeGit(name="alice")
    )
    assert ident.coherent is True
    assert ident.trust_level == "self_attested"
    assert ident.verdict == "warn"


def test_self_attested_by_email(monkeypatch):
    monkeypatch.delenv("VL_USER", raising=False)
    ident = resolve_identity(
        CWD, vl_user="alice@example.com", git_runner=FakeGit(email="alice@example.com")
    )
    assert ident.coherent is True
    assert ident.trust_level == "self_attested"


def test_mismatch_when_holder_differs(monkeypatch):
    monkeypatch.delenv("VL_USER", raising=False)
    ident = resolve_identity(
        CWD, vl_user="alice", git_runner=FakeGit(name="bob")
    )
    assert ident.coherent is False
    assert ident.trust_level == "mismatch"
    assert ident.verdict == "fail"


def test_case_insensitive_match(monkeypatch):
    monkeypatch.delenv("VL_USER", raising=False)
    ident = resolve_identity(
        CWD, vl_user="Alice", git_runner=FakeGit(name="alice")
    )
    assert ident.coherent is True


def test_signed_verified_strongest(monkeypatch):
    monkeypatch.delenv("VL_USER", raising=False)
    ident = resolve_identity(
        CWD,
        vl_user="alice",
        git_runner=FakeGit(name="alice", sig_status="G", sig_key="ABC123"),
    )
    assert ident.trust_level == "signed_verified"
    assert ident.verdict == "pass"
    assert ident.signature["key"] == "ABC123"


def test_signed_but_mismatch_fails_on_coherence(monkeypatch):
    monkeypatch.delenv("VL_USER", raising=False)
    ident = resolve_identity(
        CWD,
        vl_user="alice",
        git_runner=FakeGit(name="bob", sig_status="G"),
    )
    # 签名有效但 VL_USER 与 committer 不符 → 仍判 mismatch（签名信息保留在 payload）
    assert ident.trust_level == "mismatch"
    assert ident.signature["status"] == "G"


def test_env_vl_user_is_read(monkeypatch):
    monkeypatch.setenv("VL_USER", "carol")
    ident = resolve_identity(CWD, git_runner=FakeGit(name="carol"))
    assert ident.vl_user == "carol"
    assert ident.coherent is True


# ── commit_signature_status 解析 ──────────────────────────────────────────

def test_signature_good():
    s = commit_signature_status(CWD, git_runner=FakeGit(sig_status="G", sig_key="K1"))
    assert s == {"signed": True, "status": "G", "key": "K1"}


def test_signature_none_on_empty_repo():
    s = commit_signature_status(CWD, git_runner=FakeGit(sig_status="N"))
    assert s["signed"] is False and s["status"] == "N"


def test_signature_untrusted_or_bad_still_flagged_signed():
    s = commit_signature_status(CWD, git_runner=FakeGit(sig_status="U"))
    assert s["signed"] is True and s["status"] == "U"


def test_signature_git_error_returns_no_sig():
    s = commit_signature_status(CWD, git_runner=FakeGit(returncode=128))
    assert s["signed"] is False and s["status"] == "N"


# ── CLI 接线（隔离 git） ──────────────────────────────────────────────────

def _ns(**kw):
    d = {"path": ".", "require": None, "json": False}
    d.update(kw)
    return SimpleNamespace(**d)


def test_cli_identity_json_output(monkeypatch, capsys):
    from orchestrator import cli

    monkeypatch.setattr(
        "orchestrator.identity.resolve_identity",
        lambda ws, vl_user=None, git_runner=None: _ident(vl_user="alice", coherent=True),
    )
    rc = cli.cmd_identity(_ns(json=True))
    assert rc == cli.EXIT_OK
    out = capsys.readouterr().out
    assert '"vl_user": "alice"' in out


def test_cli_identity_require_coherent_pass(monkeypatch, capsys):
    from orchestrator import cli

    monkeypatch.setattr(
        "orchestrator.identity.resolve_identity",
        lambda ws, vl_user=None, git_runner=None: _ident(
            vl_user="alice", committer_name="alice", coherent=True,
            trust_level="self_attested", verdict="warn"),
    )
    rc = cli.cmd_identity(_ns(require="coherent"))
    assert rc == cli.EXIT_OK


def test_cli_identity_require_coherent_fail(monkeypatch, capsys):
    from orchestrator import cli

    monkeypatch.setattr(
        "orchestrator.identity.resolve_identity",
        lambda ws, vl_user=None, git_runner=None: _ident(
            vl_user="alice", committer_name="bob", coherent=False,
            trust_level="mismatch", verdict="fail"),
    )
    rc = cli.cmd_identity(_ns(require="coherent"))
    assert rc == cli.EXIT_ERROR
    assert "FAIL" in capsys.readouterr().out


def test_cli_identity_require_signed_fail(monkeypatch, capsys):
    from orchestrator import cli

    monkeypatch.setattr(
        "orchestrator.identity.resolve_identity",
        lambda ws, vl_user=None, git_runner=None: _ident(
            vl_user="alice", coherent=True,
            signature={"signed": False, "status": "N", "key": None}),
    )
    rc = cli.cmd_identity(_ns(require="signed"))
    assert rc == cli.EXIT_ERROR
