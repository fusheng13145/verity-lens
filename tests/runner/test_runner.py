"""Runner / advance 流程驱动测试（对应审计 P0-1 / P0-2）。

验证：状态机推进、经 HAL 启动会话（注入假适配器）、pre_session 硬阻断链
（门禁 / 预算 / 失败回流）、会话 token 用量回写预算。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hal.dsh_adapter import SessionHandle
from orchestrator import gates
from orchestrator.runner import PreSessionBlocked, Runner


class FakeAdapter:
    """最小 HAL 桩：记录 start_session 调用，返回可携带 usage 事件的句柄。"""

    def __init__(self, *, tokens: int = 0, degraded: bool = False):
        self.calls: list[tuple] = []
        self.tokens = tokens
        self.degraded = degraded

    def start_session(self, preset, workspace, task, session_id=None):
        self.calls.append((preset, workspace, task, session_id))
        events = [{"type": "session_start", "task": task}]
        if self.tokens:
            events.append({"usage": {"total_tokens": self.tokens}})
        return SessionHandle(
            session_id=session_id or "sess_0001",
            preset=preset,
            workspace=Path(workspace),
            events=events,
            degraded=self.degraded,
        )

    def register_skills(self, skill_dirs):
        return [Path(d) for d in skill_dirs]


RESEARCH_TMPL = """project_id: "{pid}"
discipline: "biomed"
current_phase: "{phase}"
approvals:
  question: {{ approved_by: null, approved_at: null, note: null }}
  writing:  {{ approved_by: null, approved_at: null, note: null }}
locks: {{}}
degraded_features: []
hypotheses: {hyp}
model_config:
  primary: "deepseek-chat-v4-pro"
  fallback: "deepseek-chat-v4-flash"
token_budget:
  total: {{ cap: 500000, used: {used} }}
  per_phase:
    literature: {{ cap: 100000, used: 0 }}
    question:   {{ cap: 50000,  used: 0 }}
    experiment: {{ cap: 200000, used: 0 }}
    analysis:   {{ cap: 100000, used: 0 }}
    writing:    {{ cap: 50000,  used: 0 }}
"""


def _make_ws(tmp_path: Path, *, phase: str = "literature", hypotheses="[]",
             budget_used: int = 0, with_lit: bool = True) -> Path:
    ws = tmp_path / "ws"
    for d in ("docs", "experiments", "data/raw", "data/processed", "figures", "manuscript", "analysis"):
        (ws / d).mkdir(parents=True, exist_ok=True)
    (ws / "RESEARCH.yaml").write_text(
        RESEARCH_TMPL.format(pid="p", phase=phase, hyp=hypotheses, used=budget_used),
        encoding="utf-8",
    )
    if with_lit:
        (ws / "docs" / "literature_notes.md").write_text("# 文献笔记\n\n_已补充_\n", encoding="utf-8")
        (ws / "docs" / "hypothesis_tree.json").write_text(
            '{"root_question": "", "nodes": [], "metadata": {"created_at": null, "updated_at": null, "version": 0}}\n',
            encoding="utf-8",
        )
    return ws


def test_current_and_next_phase(tmp_path):
    ws = _make_ws(tmp_path, phase="literature")
    r = Runner(adapter=FakeAdapter())
    assert r.current_phase(ws) == "literature"
    assert r.next_phase(ws) == "question"
    ws_w = _make_ws(tmp_path / "w2", phase="writing")
    assert r.next_phase(ws_w) is None


def test_advance_blocked_when_next_gate_unmet(tmp_path):
    # literature → question 需要 hypotheses_len_ge_1；此处 hypotheses=[] 故阻塞
    ws = _make_ws(tmp_path, phase="literature", hypotheses="[]")
    r = Runner(adapter=FakeAdapter())
    res = r.advance(ws, start_session=False)
    assert res["advanced"] is False
    assert res["next"] == "question"
    assert res["gate"] is not None and not res["gate"].ok
    # current_phase 不应改变
    assert gates.load_project(ws)["current_phase"] == "literature"


def test_advance_succeeds_and_moves_phase(tmp_path):
    ws = _make_ws(tmp_path, phase="literature", hypotheses='[{"id": "H1", "status": "proposed"}]')
    r = Runner(adapter=FakeAdapter())
    res = r.advance(ws, start_session=True)
    assert res["advanced"] is True
    assert res["current"] == "literature"
    assert res["next"] == "question"
    assert gates.load_project(ws)["current_phase"] == "question"
    # 会话被启动（假适配器记录）
    assert r.adapter.calls, "应经 HAL 启动会话"


def test_run_starts_session_for_current_phase(tmp_path):
    ws = _make_ws(tmp_path, phase="question", hypotheses='[{"id": "H1", "status": "proposed"}]')
    r = Runner(adapter=FakeAdapter())
    out = r.run(ws)
    assert out["phase"] == "question"
    assert r.adapter.calls


def test_pre_session_blocked_by_budget(tmp_path):
    ws = _make_ws(tmp_path, phase="question", hypotheses='[{"id": "H1"}]', budget_used=500000)
    r = Runner(adapter=FakeAdapter())
    gate = r.pre_session(ws, "question")
    assert gate.ok is False
    assert any("预算" in m for m in gate.missing)


def test_pre_session_blocked_by_unresolved_failure(tmp_path):
    ws = _make_ws(tmp_path, phase="experiment", hypotheses='[{"id": "H1"}]')
    (ws / "experiments" / "exp_001.yaml").write_text(
        "experiment_id: exp_001\nparent_hypothesis: H1\nobjective: o\n"
        "success_criteria:\n  - {metric: x, condition: '>=', threshold: 0.5}\nstatus: failed\n",
        encoding="utf-8",
    )
    r = Runner(adapter=FakeAdapter())
    gate = r.pre_session(ws, "experiment")
    assert gate.ok is False
    assert any("failed" in m for m in gate.missing)


def test_session_tokens_written_back_to_budget(tmp_path):
    ws = _make_ws(tmp_path, phase="literature")
    r = Runner(adapter=FakeAdapter(tokens=1234))
    r.run(ws, "literature")
    used = gates.load_project(ws)["token_budget"]["total"]["used"]
    assert used == 1234


def test_run_raises_blocked_when_gate_fails(tmp_path):
    ws = _make_ws(tmp_path, phase="writing", hypotheses='[{"id": "H1"}]')
    # writing 门禁需要实质性产物；此处无 → 阻塞
    r = Runner(adapter=FakeAdapter())
    with pytest.raises(PreSessionBlocked):
        r.run(ws, "writing")
