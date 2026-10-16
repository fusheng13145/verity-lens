"""orchestrator/hooks/on_change.py 单元测试（审计 #4 文件监听触发回流检查）。"""
import json

from orchestrator.hooks import on_change
from pathlib import Path


def _make_ws(tmp_path: Path) -> Path:
    (tmp_path / "experiments").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "failure_ledger.json").write_text(
        json.dumps({"entries": []}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return tmp_path


def _write_failed_exp(ws: Path, exp_id: str) -> None:
    (ws / "experiments" / f"exp_{exp_id}.yaml").write_text(
        f"experiment_id: {exp_id}\nstatus: failed\n", encoding="utf-8"
    )


def test_run_checks_zero_when_no_failures(tmp_path):
    ws = _make_ws(tmp_path)
    assert on_change.run_checks(ws) == 0


def test_run_checks_counts_unresolved_failed(tmp_path):
    ws = _make_ws(tmp_path)
    _write_failed_exp(ws, "E1")
    assert on_change.run_checks(ws) == 1


def test_run_checks_clears_after_ledger_approval(tmp_path):
    ws = _make_ws(tmp_path)
    _write_failed_exp(ws, "E1")
    assert on_change.run_checks(ws) == 1
    # 登记带 approved_by 的回流条目 → 视为已解决
    (ws / "docs" / "failure_ledger.json").write_text(
        json.dumps(
            {"entries": [{"experiment_id": "E1", "decision": {"approved_by": "reviewer"}}]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    assert on_change.run_checks(ws) == 0


def test_snapshot_and_changed_detect_modification(tmp_path):
    ws = _make_ws(tmp_path)
    (ws / "docs" / "hypothesis_tree.json").write_text("{}", encoding="utf-8")
    prev = on_change.snapshot(ws)
    assert "docs/hypothesis_tree.json" in prev
    # 修改受监控文件 → changed 应捕获
    (ws / "docs" / "hypothesis_tree.json").write_text('{"x": 1}', encoding="utf-8")
    diffs = on_change.changed(ws, prev)
    assert "docs/hypothesis_tree.json" in diffs


def test_snapshot_ignores_untracked_dir(tmp_path):
    ws = _make_ws(tmp_path)
    snap = on_change.snapshot(ws / "nonexistent_workspace")
    assert snap == {}
