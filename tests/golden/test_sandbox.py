"""容器沙箱生成器单元测试（orchestrator/sandbox.py）。"""
from orchestrator.sandbox import (
    generate,
    missing_host_dirs,
    render_compose,
    validate_compose,
)


def test_render_contains_project_and_security_baseline():
    text = render_compose("proj_x", workspace_root="workspaces")
    assert "proj_x" in text
    assert "workspaces/proj_x/data/raw:/workspace/data/raw:ro" in text
    assert "network_mode: \"none\"" in text
    assert "cap_drop" in text
    assert "read_only: true" in text


def test_validate_compose_passes_template():
    text = render_compose("proj_x")
    assert validate_compose(text) == []


def test_validate_compose_detects_missing_baseline():
    bad = "services:\n  s:\n    image: x\n"
    problems = validate_compose(bad)
    assert any("no-new-privileges" in p for p in problems)
    assert any("network_mode" in p for p in problems)


def test_missing_host_dirs(tmp_path):
    # 创建一个真实 workspace 缺部分目录
    ws = tmp_path / "workspaces" / "p1"
    (ws / "data" / "raw").mkdir(parents=True)
    (ws / "figures").mkdir(parents=True)
    missing = missing_host_dirs("p1", workspace_root=str(tmp_path / "workspaces"))
    # data/processed / manuscript / analysis 缺失
    assert "data/processed" in missing
    assert "manuscript" in missing
    assert "data/raw" not in missing


def test_generate_writes_file(tmp_path):
    dest = generate("p2", workspace_root="workspaces", out_dir=str(tmp_path / "docker"))
    assert dest.exists()
    assert "p2" in dest.read_text(encoding="utf-8")
