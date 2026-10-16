"""Finalize 收尾闭环测试（Phase 4a）。

覆盖：ready 场景、三类 blocked 场景（缺 summary / 非终态 failed / 缺可复现元数据）、
报告落盘。直接构造最小 Workspace，不依赖真实项目目录。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from orchestrator.finalize import run_finalize

RESEARCH = """project_id: "proj_test"
discipline: "materials"
title: "t"
research_question: "q"
current_phase: "writing"
approvals:
  question: { approved_by: null, approved_at: null, note: null }
  writing:  { approved_by: null, approved_at: null, note: null }
locks: {}
degraded_features: []
hypotheses: []
model_config:
  primary: "deepseek-chat-v4-pro"
  fallback: "deepseek-chat-v4-flash"
token_budget:
  total: { cap: 500000, used: 1000 }
  per_phase:
    literature: { cap: 100000, used: 0 }
    question:   { cap: 50000,  used: 0 }
    experiment: { cap: 200000, used: 0 }
    analysis:   { cap: 100000, used: 0 }
    writing:    { cap: 50000,  used: 0 }
"""

EXP_COMPLETED = """experiment_id: "exp_001"
parent_hypothesis: "H1"
objective: "o"
success_criteria:
  - { metric: "x", condition: ">=", threshold: 0.5 }
status: "completed"
reproducibility:
  model: "deepseek-chat-v4-pro"
  data_hash: "sha256:abc"
  random_seed: 42
"""

EXP_COMPLETED_NO_REPRO = """experiment_id: "exp_002"
parent_hypothesis: "H1"
objective: "o"
success_criteria:
  - { metric: "x", condition: ">=", threshold: 0.5 }
status: "completed"
"""

EXP_FAILED = """experiment_id: "exp_003"
parent_hypothesis: "H1"
objective: "o"
success_criteria:
  - { metric: "x", condition: ">=", threshold: 0.5 }
status: "failed"
"""


def _make_workspace(tmp_path, experiments: dict[str, str], *, summary: bool = True,
                    figure: bool = True) -> Path:
    ws = tmp_path / "ws"
    (ws / "experiments").mkdir(parents=True)
    (ws / "analysis").mkdir(parents=True)
    (ws / "figures").mkdir(parents=True)
    (ws / "RESEARCH.yaml").write_text(RESEARCH, encoding="utf-8")
    for name, content in experiments.items():
        (ws / "experiments" / name).write_text(content, encoding="utf-8")
    if summary:
        # 实质内容（≥200 字节 + 统计结论签名），满足 analysis_summary_substantive
        (ws / "analysis" / "summary.md").write_text(
            "# 分析结果\n\n本研究比较了干预组与对照组的均值差异。\n\n"
            "效应量 (effect size) = 0.82（Cohen's d）。\n"
            "95% 置信区间 = [0.41, 1.23]。\np 值 = 0.003，小于 0.05 显著性水平，拒绝原假设。\n\n"
            "结论：干预组显著优于对照组，假设得到支持。\n",
            encoding="utf-8",
        )
    if figure:
        # 真实图像产物（SVG，含 <svg 且 ≥64 字节），满足 figures_substantive
        (ws / "figures" / "fig1.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400">'
            '<rect width="100%" height="100%" fill="#ffffff"/>'
            '<text x="16" y="24" font-size="16">Effect size by group</text></svg>\n',
            encoding="utf-8",
        )
    return ws


def test_finalize_ready(tmp_path):
    ws = _make_workspace(tmp_path, {"exp_001.yaml": EXP_COMPLETED})
    rep = run_finalize(ws, write_report=False)
    assert rep.ready
    assert rep.status == "ready"
    assert rep.experiments_total == 1 and rep.experiments_terminal == 1
    assert not rep.reproducibility_missing
    assert "可以收尾" in rep.report_text


def test_finalize_blocked_missing_summary(tmp_path):
    ws = _make_workspace(tmp_path, {"exp_001.yaml": EXP_COMPLETED}, summary=False)
    rep = run_finalize(ws, write_report=False)
    assert not rep.ready
    assert any("summary" in b for b in rep.blockers)


def test_finalize_blocked_missing_figure(tmp_path):
    ws = _make_workspace(tmp_path, {"exp_001.yaml": EXP_COMPLETED}, figure=False)
    rep = run_finalize(ws, write_report=False)
    assert not rep.ready
    assert any("figures" in b for b in rep.blockers)


def test_finalize_blocked_unresolved_failed(tmp_path):
    ws = _make_workspace(tmp_path, {"exp_003.yaml": EXP_FAILED})
    rep = run_finalize(ws, write_report=False)
    assert not rep.ready
    assert any("失败" in b for b in rep.blockers)


def test_finalize_blocked_missing_reproducibility(tmp_path):
    ws = _make_workspace(tmp_path, {"exp_002.yaml": EXP_COMPLETED_NO_REPRO})
    rep = run_finalize(ws, write_report=False)
    assert not rep.ready
    assert any("exp_002" in m for m in rep.reproducibility_missing)
    assert any("可复现元数据" in b for b in rep.blockers)


def test_finalize_writes_report(tmp_path):
    ws = _make_workspace(tmp_path, {"exp_001.yaml": EXP_COMPLETED})
    rep = run_finalize(ws, write_report=True)
    report_path = ws / "finalize_report.md"
    assert report_path.exists()
    text = report_path.read_text(encoding="utf-8")
    assert "收尾报告" in text
    assert "AI 贡献声明" in text
