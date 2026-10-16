"""Headless API 契约测试。

验证前端依赖的端点行为（docs/interfaces.md §2.1、docs/frontend.md）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import orchestrator.api as api
from fastapi.testclient import TestClient


def _make_workspace(root: Path, project_id: str, hypotheses: list) -> Path:
    p = root / project_id
    for d in ("docs", "experiments", "data/raw", "data/processed", "figures", "manuscript", "analysis"):
        (p / d).mkdir(parents=True, exist_ok=True)
    approvals_block = "\n".join(
        f"  {ph}:\n    approved_by: null\n    approved_at: null\n    note: null"
        for ph in ("question", "writing")
    )
    hyp_block = (
        "\n".join(
            f"  - id: {h['id']}\n    status: {h['status']}\n    confidence: null"
            for h in hypotheses
        )
        or "[]"
    )
    (p / "RESEARCH.yaml").write_text(
        f'project_id: "{project_id}"\ndiscipline: "biomed"\ncurrent_phase: "question"\n'
        f"approvals:\n{approvals_block}\n"
        f"hypotheses:\n{hyp_block}\n"
        "token_budget:\n  total:\n    cap: 500000\n    used: 0\n"
        "  per_phase:\n    literature:\n      cap: 100000\n      used: 0\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "WORKSPACES_ROOT", tmp_path)
    _make_workspace(tmp_path, "proj_test", [{"id": "H1", "status": "proposed"}])
    return TestClient(api.app)


def test_get_project(client):
    r = client.get("/api/projects/proj_test")
    assert r.status_code == 200
    assert r.json()["project_id"] == "proj_test"


def test_project_not_found(client):
    assert client.get("/api/projects/nope").status_code == 404


def test_get_phases_returns_facts_and_gates(client):
    r = client.get("/api/projects/proj_test/phases")
    assert r.status_code == 200
    body = r.json()
    assert "facts" in body and "gates" in body
    assert set(body["gates"]) == {
        "literature",
        "question",
        "experiment",
        "analysis",
        "writing",
    }
    assert body["facts"]["hypotheses_len_ge_1"] is True
    assert body["facts"]["approvals_question_approved"] is False


def test_approve_phase_persists(client):
    r = client.post(
        "/api/projects/proj_test/approve_phase",
        json={"phase": "question", "approved_by": "researcher_pi", "note": "ok"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    # 回读确认已落盘
    body = client.get("/api/projects/proj_test").json()
    assert body["approvals"]["question"]["approved_by"] == "researcher_pi"


def test_approve_unknown_phase(client):
    r = client.post(
        "/api/projects/proj_test/approve_phase",
        json={"phase": "nope", "approved_by": "x"},
    )
    assert r.status_code == 400


def test_failure_ledger_rejects_unapproved(client):
    entry = {
        "id": "F-001",
        "experiment_id": "exp_001",
        "hypothesis_id": "H1",
        "phase": "experiment",
        "detected_at": "2026-10-20T14:00:00Z",
        "classification": {"category": "METH", "code": "X", "confidence": 0.8},
        "decision": {"type": "revise_experiment", "approved_by": None},
    }
    assert client.post(
        "/api/projects/proj_test/failure_ledger", json=entry
    ).status_code == 400


def test_failure_ledger_accepts_approved(client):
    entry = {
        "id": "F-002",
        "experiment_id": "exp_001",
        "hypothesis_id": "H1",
        "phase": "experiment",
        "detected_at": "2026-10-20T14:00:00Z",
        "classification": {"category": "METH", "code": "X", "confidence": 0.8},
        "decision": {"type": "revise_experiment", "approved_by": "pi"},
    }
    r = client.post("/api/projects/proj_test/failure_ledger", json=entry)
    assert r.status_code == 200
    assert r.json()["entry_id"] == "F-002"
    assert client.get("/api/projects/proj_test/failure_ledger").json()["entries"][-1]["id"] == "F-002"


def test_failure_ledger_routes_via_apply_decision(client, tmp_path):
    """P0-4：登记 METH 失败须真正回流（实验状态被更新），而非仅追加 ledger。"""
    ws = tmp_path / "proj_test"
    (ws / "experiments").mkdir(parents=True, exist_ok=True)
    (ws / "experiments" / "exp_001.yaml").write_text(
        "experiment_id: exp_001\nparent_hypothesis: H1\nobjective: o\n"
        "success_criteria:\n  - {metric: x, condition: '>=', threshold: 0.5}\nstatus: running\n",
        encoding="utf-8",
    )
    (ws / "docs" / "hypothesis_tree.json").write_text(
        '{"root_question": "", "nodes": [{"id": "H1", "status": "proposed", "confidence": null}], '
        '"metadata": {"created_at": null, "updated_at": null, "version": 0}}\n',
        encoding="utf-8",
    )
    entry = {
        "id": "F-010",
        "experiment_id": "exp_001",
        "hypothesis_id": "H1",
        "phase": "experiment",
        "detected_at": "2026-10-20T14:00:00Z",
        "classification": {"category": "METH", "code": "X", "confidence": 0.8},
        "decision": {"type": "revise_experiment", "approved_by": "pi"},
    }
    r = client.post("/api/projects/proj_test/failure_ledger", json=entry)
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "revise_experiment"
    assert body["experiment_status"] == "concluded_failed"
    # 实验文件状态应被 apply_decision 更新（闭环真正发生）
    exp = yaml.safe_load((ws / "experiments" / "exp_001.yaml").read_text(encoding="utf-8"))
    assert exp["status"] == "concluded_failed"
    assert any(
        e["id"] == "F-010"
        for e in client.get("/api/projects/proj_test/failure_ledger").json()["entries"]
    )


# ── DOI 可验证率度量（审计 #10）──────────────────────────────────────


def test_doi_metrics_get_computes_offline(client):
    r = client.get("/api/projects/proj_test/doi-metrics")
    assert r.status_code == 200
    body = r.json()
    assert {"total", "valid_format", "verification_rate", "online"} <= set(body)
    assert body["online"] is False


def test_doi_metrics_post_persists(client, tmp_path):
    r = client.post("/api/projects/proj_test/doi-metrics", json={"online": False})
    assert r.status_code == 200
    # 已持久化：docs/doi_verification.json 落盘，GET 返回同一份
    stored = tmp_path / "proj_test" / "docs" / "doi_verification.json"
    assert stored.exists()
    r2 = client.get("/api/projects/proj_test/doi-metrics")
    assert r2.json()["checked_at"] == r.json()["checked_at"]
