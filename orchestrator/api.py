"""Headless API：供 Web 前端（web/）与自动化调用的唯一入口。

设计约束（docs/frontend.md / docs/interfaces.md）：
- 前端只经本 API 与系统交互，不得直连底座或读写 Workspace 文件系统；
- 本层不持有状态，只读（或按门禁规则写）Workspace 声明式文件；
- 类型契约以 orchestrator/schemas/*.json 为单一真相。

启动：uvicorn orchestrator.api:app --port 8000
"""
from __future__ import annotations

import json
from pathlib import Path

from typing import Literal

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from orchestrator.gates import PHASES, check_gate, compute_facts, load_project

WORKSPACES_ROOT = Path("workspaces")

app = FastAPI(title="VerityLens Headless API", version="0.1.0")


# ── 数据模型 ──────────────────────────────────────────────────────────

class ApprovalRequest(BaseModel):
    phase: str
    approved_by: str
    note: str | None = None


class Classification(BaseModel):
    category: Literal["EXEC", "DATA", "METH", "HYP", "EPIS"]
    code: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str | None = None


class Decision(BaseModel):
    type: Literal[
        "retry_execution",
        "supplement_data",
        "revise_experiment",
        "revise_hypothesis",
        "abandon_hypothesis",
        "revise_premise",
    ]
    action: str | None = None
    changes: list[str] = Field(default_factory=list)
    hypothesis_impact: dict = Field(default_factory=dict)
    approved_by: str | None = None
    approved_at: str | None = None


class Evidence(BaseModel):
    path: str
    locator: str | None = None
    event: str | None = None


class FailureEntry(BaseModel):
    id: str = Field(pattern=r"^F-\d+$")
    experiment_id: str
    hypothesis_id: str
    phase: Literal["literature", "question", "experiment", "analysis", "writing"]
    detected_at: str
    classification: Classification
    decision: Decision
    evidence: list[Evidence] = Field(default_factory=list)
    lesson: str | None = None
    tags: list[str] = Field(default_factory=list)


# ── 工具函数 ──────────────────────────────────────────────────────────

def _workspace(project_id: str) -> Path:
    ws = WORKSPACES_ROOT / project_id
    if not ws.exists():
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_id}")
    return ws


def _read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


# ── 项目与阶段 ────────────────────────────────────────────────────────

@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    ws = _workspace(project_id)
    return load_project(ws)


@app.get("/api/projects/{project_id}/phases")
def get_phases(project_id: str):
    """返回各阶段的门禁状态与事实（供阶段看板展示）。"""
    ws = _workspace(project_id)
    project = load_project(ws)
    facts = compute_facts(project, ws)
    gates = {}
    for phase in PHASES:
        res = check_gate(phase, ws)
        gates[phase] = {
            "ok": res.ok,
            "hitl_required": res.hitl_required,
            "missing": list(res.missing),
        }
    return {"current_phase": project.get("current_phase"), "facts": facts, "gates": gates}


@app.post("/api/projects/{project_id}/approve_phase")
def approve_phase(project_id: str, req: ApprovalRequest):
    """HITL 审批：写入 approvals[phase]（approver + 时间戳）。"""
    from datetime import datetime, timezone

    ws = _workspace(project_id)
    if req.phase not in PHASES:
        raise HTTPException(status_code=400, detail=f"未知阶段: {req.phase}")
    research_path = ws / "RESEARCH.yaml"
    project = load_project(ws)
    approvals = project.setdefault("approvals", {})
    approvals[req.phase] = {
        "approved_by": req.approved_by,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "note": req.note,
    }
    _write_yaml(research_path, project)
    return {"status": "approved", "phase": req.phase, "approved_by": req.approved_by}


# ── 假设树 / 实验 / 失败登记簿 ────────────────────────────────────────

@app.get("/api/projects/{project_id}/hypothesis_tree")
def get_hypothesis_tree(project_id: str):
    ws = _workspace(project_id)
    tree = _read_json(ws / "docs" / "hypothesis_tree.json")
    if tree is None:
        raise HTTPException(status_code=404, detail="缺少 hypothesis_tree.json")
    return tree


@app.get("/api/projects/{project_id}/experiments")
def get_experiments(project_id: str):
    ws = _workspace(project_id)
    exp_dir = ws / "experiments"
    if not exp_dir.exists():
        return {"experiments": []}
    out = []
    for f in sorted(exp_dir.glob("exp_*.yaml")):
        out.append(yaml.safe_load(f.read_text(encoding="utf-8")) or {})
    return {"experiments": out}


@app.get("/api/projects/{project_id}/failure_ledger")
def get_failure_ledger(project_id: str):
    ws = _workspace(project_id)
    ledger = _read_json(ws / "docs" / "failure_ledger.json")
    if ledger is None:
        raise HTTPException(status_code=404, detail="缺少 failure_ledger.json")
    return ledger


@app.post("/api/projects/{project_id}/failure_ledger")
def append_failure_entry(project_id: str, entry: FailureEntry):
    """登记失败条目。HITL 强制：decision.approved_by 不得为空。"""
    ws = _workspace(project_id)
    ledger_path = ws / "docs" / "failure_ledger.json"
    ledger = _read_json(ledger_path) or {"entries": []}
    if not entry.decision.approved_by:
        raise HTTPException(
            status_code=400,
            detail="失败登记需人工批准：decision.approved_by 不能为空",
        )
    ledger.setdefault("entries", []).append(entry.model_dump())
    ledger_path.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"status": "recorded", "entry_id": entry.id}
