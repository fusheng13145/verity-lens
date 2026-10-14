"""失败驱动迭代模块测试（Layer 2 相关 + 业务闭环）。

覆盖：五类失败分类路由、未处理 failed 检测、决策落盘、假设树回流、
低置信度强制 HITL、重试上限升级。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from orchestrator.failure_loop import (
    MAX_EXEC_RETRIES,
    apply_decision,
    check_loop,
    find_unresolved_failures,
    load_ledger,
    load_tree,
    route,
    validate_entry,
)


def _mk(workspace, exp_id, status, **extra):
    d = workspace / "experiments"
    d.mkdir(parents=True, exist_ok=True)
    data = {
        "experiment_id": exp_id,
        "parent_hypothesis": "H1",
        "objective": "obj",
        "status": status,
        "retry_count": 0,
        "failure_ref": None,
        "success_criteria": [
            {"metric": "m", "condition": ">=", "threshold": 0.5}
        ],
    }
    data.update(extra)
    (d / f"{exp_id}.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def _entry(exp_id="exp_001", category="METH", confidence=0.8, approved="pi",
           dtype="revise_experiment"):
    return {
        "id": "F-001",
        "experiment_id": exp_id,
        "hypothesis_id": "H1",
        "phase": "experiment",
        "detected_at": "2026-10-20T14:00:00Z",
        "classification": {
            "category": category,
            "code": f"{category}-X",
            "confidence": confidence,
            "rationale": "r",
        },
        "evidence": [{"path": "a.json"}],
        "decision": {"type": dtype, "approved_by": approved},
        "lesson": "l",
        "tags": ["t"],
    }


# ── 未处理失败检测 ────────────────────────────────────────────────────

def test_find_unresolved(tmp_path):
    _mk(tmp_path, "exp_001", "failed")
    _mk(tmp_path, "exp_002", "completed")
    assert find_unresolved_failures(tmp_path) == ["exp_001"]


def test_check_loop_blocks_when_unresolved(tmp_path):
    _mk(tmp_path, "exp_001", "failed")
    ok, unresolved = check_loop(tmp_path)
    assert ok is False and unresolved == ["exp_001"]


def test_check_loop_passes_when_resolved(tmp_path):
    _mk(tmp_path, "exp_001", "failed")
    tree = {"root_question": "q", "nodes": [
        {"id": "H1", "parent_id": None, "type": "hypothesis",
         "content": "c", "status": "testing", "confidence": 0.6}]}
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "hypothesis_tree.json").write_text(
        json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")

    result = apply_decision(tmp_path, _entry())
    assert result["experiment_status"] == "concluded_failed"
    assert find_unresolved_failures(tmp_path) == []
    assert result["tree_version"] == 1


# ── Schema 校验 ──────────────────────────────────────────────────────

def test_validate_entry_rejects_bad_id():
    e = _entry()
    e["id"] = "FAIL-1"
    assert validate_entry(e)


def test_validate_entry_rejects_missing_decision():
    e = _entry()
    e.pop("decision")
    assert validate_entry(e)


def test_validate_entry_rejects_bad_category():
    e = _entry(category="LATER")
    assert validate_entry(e)


# ── 五类路由 ──────────────────────────────────────────────────────────

def test_route_exec_retry_under_limit():
    r = route(_entry(category="EXEC", dtype="retry_execution"))
    assert r.action == "retry_execution"
    assert r.experiment_status == "running"
    assert r.needs_hitl is False


def test_route_exec_escalates_over_limit():
    e = _entry(category="EXEC", dtype="abandon_hypothesis")
    e["retry_count"] = MAX_EXEC_RETRIES
    r = route(e)
    assert r.escalate is True and r.needs_hitl is True


def test_route_data_suspends():
    r = route(_entry(category="DATA", dtype="supplement_data"))
    assert r.action == "supplement_data"
    assert r.experiment_status == "suspended"


def test_route_meth_revises():
    r = route(_entry(category="METH", dtype="revise_experiment"))
    assert r.action == "revise_experiment"
    assert r.experiment_status == "concluded_failed"


def test_route_hyp_revises():
    r = route(_entry(category="HYP", dtype="revise_hypothesis"))
    assert r.action == "revise_hypothesis"


def test_route_epis_revises_premise():
    r = route(_entry(category="EPIS", dtype="revise_premise"))
    assert r.action == "revise_premise"


def test_route_unknown_category_forces_hitl():
    r = route(_entry(category="NOPE"))
    assert r.needs_hitl is True


def test_route_low_confidence_forces_hitl():
    r = route(_entry(category="EXEC", confidence=0.3, dtype="retry_execution"))
    assert r.needs_hitl is True and r.escalate is False


# ── 落盘：实验终态 / 假设树 / ledger / lessons ───────────────────────

def test_apply_decision_updates_experiment_and_tree(tmp_path):
    _mk(tmp_path, "exp_001", "failed")
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "hypothesis_tree.json").write_text(
        json.dumps({"root_question": "q", "nodes": [
            {"id": "H1", "parent_id": None, "type": "hypothesis",
             "content": "c", "status": "testing", "confidence": 0.6}]},
                 ensure_ascii=False, indent=2),
        encoding="utf-8")

    entry = _entry()
    entry["decision"]["hypothesis_impact"] = {"H1": {"status": "refuted",
                                                     "confidence_change": -0.2}}
    res = apply_decision(tmp_path, entry)

    # 实验转终态并关联条目
    exp = yaml.safe_load((tmp_path / "experiments" / "exp_001.yaml").read_text(encoding="utf-8"))
    assert exp["status"] == "concluded_failed"
    assert exp["failure_ref"] == "F-001"

    # 假设树节点被更新 + 证据链保留 + 版本递增
    tree = load_tree(tmp_path)
    h1 = [n for n in tree["nodes"] if n["id"] == "H1"][0]
    assert h1["status"] == "refuted"
    assert abs(h1["confidence"] - 0.4) < 1e-9
    assert "F-001" in h1["provenance"]["justified_by"]
    assert res["tree_version"] == 1

    # ledger 与 lessons 落盘
    ledger = load_ledger(tmp_path)
    assert ledger["entries"][-1]["id"] == "F-001"
    lessons = (tmp_path / "docs" / "lessons.md").read_text(encoding="utf-8")
    assert "F-001" in lessons


def test_apply_decision_rejects_unapproved(tmp_path):
    _mk(tmp_path, "exp_001", "failed")
    with pytest.raises(ValueError, match="人工批准"):
        apply_decision(tmp_path, _entry(approved=None))


def test_data_route_sets_suspended(tmp_path):
    _mk(tmp_path, "exp_001", "failed")
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "hypothesis_tree.json").write_text(
        json.dumps({"root_question": "q", "nodes": []}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    apply_decision(tmp_path, _entry(category="DATA", dtype="supplement_data"))
    exp = yaml.safe_load((tmp_path / "experiments" / "exp_001.yaml").read_text(encoding="utf-8"))
    assert exp["status"] == "suspended"
