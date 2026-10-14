"""Layer 1：声明式文件 Schema 校验测试。

校验 RESEARCH.yaml / hypothesis_tree.json / experiment.yaml / failure_ledger.json
是否符合 orchestrator/schemas/*.json 契约。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# tests/schema/test_schemas.py → parents: [0]=tests/schema  [1]=tests  [2]=项目根
SCHEMAS = Path(__file__).resolve().parents[2] / "orchestrator" / "schemas"


def _validate(schema_name: str, data: dict) -> list[str]:
    schema = json.loads((SCHEMAS / schema_name).read_text(encoding="utf-8"))
    v = Draft202012Validator(schema)
    return [e.message for e in sorted(v.iter_errors(data), key=lambda e: list(e.path))]


VALID_RESEARCH = {
    "project_id": "proj_20261014_001",
    "discipline": "biomed",
    "current_phase": "experiment",
    "hypotheses": [{"id": "H1", "status": "testing", "confidence": 0.55}],
    "token_budget": {
        "total": {"cap": 500000, "used": 42300},
        "per_phase": {"literature": {"cap": 100000, "used": 42300}},
    },
}

VALID_TREE = {
    "root_question": "构象差异能否作为 AD 早期生物标志物？",
    "nodes": [
        {
            "id": "H1",
            "parent_id": None,
            "type": "hypothesis",
            "content": "构象存在可预测的差异",
            "status": "testing",
            "confidence": 0.65,
            "children": ["E1"],
        },
        {
            "id": "E1",
            "parent_id": "H1",
            "type": "experiment",
            "content": "比较 RMSD 分布",
            "status": "proposed",
        },
    ],
}

VALID_EXPERIMENT = {
    "experiment_id": "exp_001",
    "parent_hypothesis": "H1",
    "objective": "比较 RMSD 分布差异",
    "status": "concluded_failed",
    "retry_count": 1,
    "failure_ref": "F-001",
    "superseded_by": "exp_002",
    "success_criteria": [
        {"metric": "group_rmsd_difference", "condition": ">=", "threshold": 0.5}
    ],
}

VALID_LEDGER = {
    "entries": [
        {
            "id": "F-001",
            "experiment_id": "exp_001",
            "hypothesis_id": "H1",
            "phase": "experiment",
            "detected_at": "2026-10-20T14:00:00Z",
            "classification": {
                "category": "METH",
                "code": "METH-POWER-LOW",
                "confidence": 0.8,
                "rationale": "power=0.41 < 0.8",
            },
            "evidence": [
                {"path": "data/processed/exp_001/stats.json", "locator": "$.power"}
            ],
            "decision": {
                "type": "revise_experiment",
                "action": "exp_002",
                "approved_by": "researcher_pi",
            },
            "lesson": "设计前先做功效分析",
            "tags": ["power-analysis"],
        }
    ]
}


@pytest.mark.parametrize(
    "schema_name,data",
    [
        ("research.schema.json", VALID_RESEARCH),
        ("hypothesis_tree.schema.json", VALID_TREE),
        ("experiment.schema.json", VALID_EXPERIMENT),
        ("failure_ledger.schema.json", VALID_LEDGER),
    ],
)
def test_valid_samples_pass(schema_name, data):
    assert _validate(schema_name, data) == []


@pytest.mark.parametrize(
    "schema_name,mutate",
    [
        ("research.schema.json", lambda d: d.pop("project_id")),
        ("research.schema.json", lambda d: d.update(current_phase="nope")),
        ("research.schema.json", lambda d: d.update(hypotheses=[{"id": "H1", "status": "maybe"}])),
        ("experiment.schema.json", lambda d: d.pop("success_criteria")),
        ("experiment.schema.json", lambda d: d.update(status="weird")),
        ("failure_ledger.schema.json", lambda d: d["entries"][0].update(id="FAIL-1")),
        ("failure_ledger.schema.json", lambda d: d["entries"][0].pop("decision")),
        ("failure_ledger.schema.json", lambda d: d["entries"][0]["classification"].update(category="LATER")),
        ("hypothesis_tree.schema.json", lambda d: d["nodes"][0].pop("status")),
    ],
)
def test_invalid_samples_are_rejected(schema_name, mutate):
    data = json.loads(json.dumps(VALID_RESEARCH if schema_name == "research.schema.json"
                                                else VALID_EXPERIMENT if schema_name == "experiment.schema.json"
                                                else VALID_LEDGER if schema_name == "failure_ledger.schema.json"
                                                else VALID_TREE))
    mutate(data)
    assert _validate(schema_name, data) != []
