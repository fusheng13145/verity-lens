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

from orchestrator.failure_loop import apply_decision
from orchestrator.gates import PHASES, check_gate, compute_facts, load_project
from orchestrator.doi_metrics import compute_doi_metric, persist_doi_metric

WORKSPACES_ROOT = Path("workspaces")

app = FastAPI(title="verity-lens Headless API", version="0.1.0")


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


class DoiVerifyRequest(BaseModel):
    """DOI 度量触发参数（审计 #10）。online=True 时真联网调 Crossref。"""

    online: bool = False


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
    """登记失败条目并驱动回流闭环（审计 P0-4：关闭「直接写 ledger 绕过闭环」通道）。

    改走 ``failure_loop.apply_decision``：校验 → 路由 → 更新实验/假设树 → 追加 ledger →
    渲染 lessons，使失败被登记后真正回流（假设树更新、级联影响发生）。
    HITL 强制：``decision.approved_by`` 不得为空（``apply_decision`` 内部强制，未满足返回 400）。
    """
    ws = _workspace(project_id)
    if not entry.decision.approved_by:
        raise HTTPException(
            status_code=400,
            detail="失败登记需人工批准：decision.approved_by 不能为空",
        )
    try:
        result = apply_decision(ws, entry.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": "recorded",
        "entry_id": result["entry_id"],
        "action": result["action"],
        "experiment_status": result["experiment_status"],
        "cascaded_nodes": result.get("cascaded_nodes", []),
    }


# ── DOI 可验证率度量（审计 #10）──────────────────────────────────────

@app.get("/api/projects/{project_id}/doi-metrics")
def get_doi_metrics(project_id: str):
    """返回 DOI 可验证率度量（此前持久化的结果；无则现算离线度量，不落盘）。"""
    ws = _workspace(project_id)
    stored = _read_json(ws / "docs" / "doi_verification.json")
    if stored is not None:
        return stored
    return compute_doi_metric(ws, online=False)


@app.post("/api/projects/{project_id}/doi-metrics")
def verify_doi_metrics(project_id: str, req: DoiVerifyRequest):
    """触发一次 DOI 度量并持久化（RESEARCH.yaml + docs/doi_verification.json）。"""
    ws = _workspace(project_id)
    if not (ws / "RESEARCH.yaml").exists():
        raise HTTPException(status_code=400, detail="缺少 RESEARCH.yaml，无法持久化度量")
    metric = compute_doi_metric(ws, online=req.online)
    persist_doi_metric(ws / "RESEARCH.yaml", metric)
    return metric
