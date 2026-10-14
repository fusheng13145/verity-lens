"""级联回流测试（Phase 2）：假设被证伪时派生子节点同步标记。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from orchestrator.failure_loop import cascade_impact, apply_decision


def _tree_with_descendants():
    return {
        "root_question": "q",
        "nodes": [
            {"id": "H1", "parent_id": None, "type": "hypothesis",
             "content": "根假设", "status": "testing", "confidence": 0.6,
             "children": ["H1.1", "E1"]},
            {"id": "H1.1", "parent_id": "H1", "type": "hypothesis",
             "content": "派生假设", "status": "testing", "confidence": 0.5,
             "children": ["E2"]},
            {"id": "E1", "parent_id": "H1", "type": "experiment",
             "content": "根实验", "status": "running"},
            {"id": "E2", "parent_id": "H1.1", "type": "experiment",
             "content": "派生实验", "status": "draft"},
        ],
        "metadata": {"version": 1},
    }


def test_cascade_marks_descendants():
    tree = _tree_with_descendants()
    affected = cascade_impact(tree, "H1", "refuted")
    assert set(affected) == {"H1.1", "E1", "E2"}

    by_id = {n["id"]: n for n in tree["nodes"]}
    assert by_id["H1.1"]["status"] == "revised"     # 派生假设需修订
    assert by_id["E1"]["status"] == "abandoned"    # 其下实验放弃
    assert by_id["E2"]["status"] == "abandoned"  # 孙节点同样级联
    assert "cascade_note" in by_id["E2"]


def test_cascade_noop_for_non_cascading_status():
    tree = _tree_with_descendants()
    affected = cascade_impact(tree, "H1", "testing")
    assert affected == []


def test_apply_decision_cascades_on_refuted(tmp_path):
    _mk = tmp_path / "experiments"
    _mk.mkdir(parents=True)
    exp = {
        "experiment_id": "exp_001", "parent_hypothesis": "H1",
        "objective": "o", "status": "failed", "retry_count": 0,
        "failure_ref": None,
        "success_criteria": [{"metric": "m", "condition": ">=", "threshold": 0.5}],
    }
    (_mk / "exp_001.yaml").write_text(
        yaml.safe_dump(exp, allow_unicode=True, sort_keys=False), encoding="utf-8")

    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "hypothesis_tree.json").write_text(
        json.dumps(_tree_with_descendants(), ensure_ascii=False, indent=2),
        encoding="utf-8")

    entry = {
        "id": "F-002",
        "experiment_id": "exp_001",
        "hypothesis_id": "H1",
        "phase": "experiment",
        "detected_at": "2026-10-21T10:00:00Z",
        "classification": {"category": "HYP", "code": "HYP-NULL", "confidence": 0.85,
                                    "rationale": "效应量为 0，方向与假设相反"},
        "decision": {
            "type": "abandon_hypothesis",
            "approved_by": "pi",
            "hypothesis_impact": {"H1": {"status": "refuted", "confidence_change": -0.6}},
        },
        "evidence": [{"path": "data/processed/exp_001/stats.json"}],
        "lesson": "构象差异假设未获支持",
        "tags": ["null-result"],
    }

    res = apply_decision(tmp_path, entry)
    assert res["category"] == "HYP"
    assert set(res["cascaded_nodes"]) == {"H1.1", "E1", "E2"}

    tree_file = tmp_path / "docs" / "hypothesis_tree.json"
    saved = json.loads(tree_file.read_text(encoding="utf-8"))
    by_id = {n["id"]: n for n in saved["nodes"]}
    assert by_id["H1"]["status"] == "refuted"
    assert by_id["E2"]["status"] == "abandoned"
