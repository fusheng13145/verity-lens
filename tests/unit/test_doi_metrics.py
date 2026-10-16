"""DOI 可验证率度量测试（审计 #10）。"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from orchestrator.doi_metrics import (
    collect_dois,
    compute_doi_metric,
    persist_doi_metric,
    verify_dois,
)
from orchestrator.finalize import run_finalize


def _make_ws(tmp_path: Path, *, cited: list[str] | None = None) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "RESEARCH.yaml").write_text(
        yaml.safe_dump({"project_id": "t", "cited_dois": cited or []}, allow_unicode=True),
        encoding="utf-8",
    )
    return ws


def test_collect_dois_from_rag_index_and_cited(tmp_path):
    ws = _make_ws(tmp_path, cited=["10.1234/FromCited", "https://doi.org/10.9999/UPPER"])
    vdir = ws / ".verity"
    vdir.mkdir()
    (vdir / "rag-index.json").write_text(
        json.dumps(
            {
                "chunks": [
                    {"metadata": {"doi": "10.1234/fromcited"}},
                    {"metadata": {"doi": "10.5555/only-in-index"}},
                    {"metadata": {"doi": ""}},
                ]
            }
        ),
        encoding="utf-8",
    )
    dois = collect_dois(ws)
    # 归一化去重：10.1234/fromcited 两个来源合一；URL 前缀剥离 + 小写
    assert "10.1234/fromcited" in dois
    assert "10.9999/upper" in dois
    assert "10.5555/only-in-index" in dois
    assert len(dois) == 3


def test_collect_dois_from_hypothesis_tree_doi_fields(tmp_path):
    ws = _make_ws(tmp_path)
    docs = ws / "docs"
    docs.mkdir()
    (docs / "hypothesis_tree.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {"hypothesis_id": "H1", "doi": "10.1111/h1"},
                    {"children": [{"doi": "10.2222/h2"}]},
                ]
            }
        ),
        encoding="utf-8",
    )
    dois = collect_dois(ws)
    assert "10.1111/h1" in dois and "10.2222/h2" in dois


def test_verify_dois_offline_format_check():
    checks = verify_dois(["10.1234/valid.doi", "not-a-doi", "10.9999/x"])
    by_doi = {c["doi"]: c for c in checks}
    assert by_doi["10.1234/valid.doi"]["valid_format"] is True
    assert by_doi["not-a-doi"]["valid_format"] is False
    assert by_doi["10.9999/x"]["valid_format"] is True
    # 离线模式不产生 exists 字段（未联网）
    assert "exists" not in by_doi["10.1234/valid.doi"]


def test_compute_doi_metric_aggregates(tmp_path):
    ws = _make_ws(tmp_path, cited=["10.1234/ok", "bad-doi", "10.7777/also-ok"])
    m = compute_doi_metric(ws, online=False)
    assert m["total"] == 3
    assert m["valid_format"] == 2
    assert m["verification_rate"] == round(2 / 3, 4)
    assert m["online"] is False
    assert m["verified"] == 0  # 离线不产生已验证


def test_persist_doi_metric_writes_research_and_json(tmp_path):
    ws = _make_ws(tmp_path, cited=["10.1234/ok"])
    metric = compute_doi_metric(ws, online=False)
    persist_doi_metric(ws / "RESEARCH.yaml", metric)
    proj = yaml.safe_load((ws / "RESEARCH.yaml").read_text(encoding="utf-8"))
    assert proj["metrics"]["doi_verification"]["total"] == 1
    stored = json.loads((ws / "docs" / "doi_verification.json").read_text(encoding="utf-8"))
    assert stored["total"] == 1


def test_finalize_integrates_doi_metric(tmp_path):
    """收尾主流程自度量：报告含 DOI 章节，RESEARCH.yaml 获得持久化度量。"""
    ws = _make_ws(tmp_path, cited=["10.1234/ok", "bad-doi"])
    report = run_finalize(ws, write_report=True)
    assert "DOI 可验证率" in report.report_text
    assert report.doi_metric["total"] == 2
    # finalize 后度量已持久化
    proj = yaml.safe_load((ws / "RESEARCH.yaml").read_text(encoding="utf-8"))
    assert proj["metrics"]["doi_verification"]["total"] == 2


def test_finalize_no_dois_is_neutral(tmp_path):
    ws = _make_ws(tmp_path)
    report = run_finalize(ws, write_report=True)
    assert report.doi_metric["total"] == 0
    assert "未采集到引用 DOI" in report.report_text
