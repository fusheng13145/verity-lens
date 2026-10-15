"""Git 分支协作流单元测试（orchestrator/collab.py）。

git 调用通过假 runner 注入，无需真实仓库；就绪检查的硬逻辑（失败实验 / 门禁）
基于真实文件，确保与编排层一致。
"""
from pathlib import Path

from orchestrator.collab import (
    check_merge_readiness,
    create_hypothesis_branch,
    current_branch,
    merge_to_main,
)


class FakeGit:
    def __init__(self, branch="hypothesis/H1"):
        self.branch = branch
        self.calls = []

    def __call__(self, args, cwd):
        self.calls.append((list(args), str(cwd)))
        # 模拟 git 输出
        if args[:2] == ["rev-parse", "--abbrev-ref"]:
            return _cp(self.branch)
        if args[:1] == ["checkout"]:
            self.branch = args[-1]
            return _cp("")
        if args[:1] == ["merge"]:
            return _cp("")
        return _cp("")


def _cp(stdout, returncode=0, stderr=""):
    class R:
        pass

    r = R()
    r.stdout = stdout
    r.stderr = stderr
    r.returncode = returncode
    return r


def _init_workspace(tmp_path: Path) -> Path:
    import orchestrator.cli as cli

    ws = tmp_path / "proj_col"
    cli.cmd_init(type("A", (), {"project_id": "proj_col", "discipline": "biomed", "path": str(tmp_path)})())
    # cmd_init 写到 path/project_id
    return tmp_path / "proj_col"


def test_current_branch_via_fake_git():
    fg = FakeGit("hypothesis/H2")
    assert current_branch(Path("/x"), git_runner=fg) == "hypothesis/H2"


def test_create_hypothesis_branch():
    fg = FakeGit("main")
    ws = Path("/x")
    ok, info = create_hypothesis_branch("H3", ws, git_runner=fg)
    assert ok is True
    assert info == "hypothesis/H3"
    assert ["checkout", "-B", "hypothesis/H3", "main"] in [c[0] for c in fg.calls]


def test_readiness_ready_on_clean_branch(tmp_path):
    ws = _init_workspace(tmp_path)
    fg = FakeGit("hypothesis/H1")
    state = check_merge_readiness(ws, git_runner=fg)
    assert state["ready"] is True
    assert state["branch"] == "hypothesis/H1"


def test_readiness_blocked_on_main_with_failed_exp(tmp_path):
    ws = _init_workspace(tmp_path)
    # 制造一个未处理 failed 实验
    exp = ws / "experiments" / "exp_001.yaml"
    exp.parent.mkdir(parents=True, exist_ok=True)
    exp.write_text(
        "experiment_id: exp_001\nparent_hypothesis: H1\nstatus: failed\n", encoding="utf-8"
    )
    fg = FakeGit("hypothesis/H1")
    state = check_merge_readiness(ws, git_runner=fg)
    assert state["ready"] is False
    assert any("failed 实验" in r for r in state["reasons"])


def test_merge_to_main_requires_readiness(tmp_path):
    ws = _init_workspace(tmp_path)
    exp = ws / "experiments" / "exp_001.yaml"
    exp.parent.mkdir(parents=True, exist_ok=True)
    exp.write_text(
        "experiment_id: exp_001\nparent_hypothesis: H1\nstatus: failed\n", encoding="utf-8"
    )
    fg = FakeGit("hypothesis/H1")
    ok, info = merge_to_main(ws, git_runner=fg)
    assert ok is False  # 被未处理失败阻塞，未真正执行 merge
    assert any("failed 实验" in c[1] for c in fg.calls if c[0][:1] == ["merge"]) is False


def test_merge_to_main_success(tmp_path):
    ws = _init_workspace(tmp_path)
    fg = FakeGit("hypothesis/H1")
    ok, info = merge_to_main(ws, git_runner=fg)
    assert ok is True
    assert info == "hypothesis/H1"
