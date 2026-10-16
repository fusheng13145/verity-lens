"""RAG CLI 接入单元测试（orchestrator/cli.py cmd_rag + sidecar/rag 持久化）。

覆盖：索引持久化 round-trip、``vl rag index/query`` 端到端、``rag_index_write`` 埋点
opt-in 接线（开启记录 / 关闭零副作用）、重复索引去重、参数错误退出码。
"""
import json
from pathlib import Path

from sidecar.rag.literature_rag import (
    Chunk,
    LiteratureIndex,
    load_index,
    save_index,
)


def _ns(**kw):
    return type("A", (), kw)()


def _write_doc(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _init_workspace(tmp_path: Path) -> Path:
    import orchestrator.cli as cli

    cli.cmd_init(_ns(project_id="proj_rag", discipline="biomed", path=str(tmp_path)))
    return tmp_path / "proj_rag"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ── 持久化 round-trip ────────────────────────────────────────────────

def test_save_load_roundtrip_preserves_chunks_and_vectors(tmp_path):
    idx = LiteratureIndex()
    idx.add([
        Chunk(chunk_id="d#0", text="AlphaFold 构象差异", metadata={"doi": "10.0/1"}),
        Chunk(chunk_id="d#1", text="卷积神经网络", metadata={"doi": "10.0/2"}),
    ])
    idx.archive(lambda c: "构象" in c.text)
    p = tmp_path / "rag-index.json"
    save_index(idx, p)
    assert p.exists()
    loaded = load_index(p)
    assert loaded is not None
    assert loaded.size == 2
    # 归档状态被保留（仅留元数据）
    assert loaded._chunks[0].archived is True
    assert loaded._chunks[0].text == ""
    # 未归档分片的向量被落盘并可重建检索（离线 hash 嵌入器确定性）
    res = loaded.query("卷积神经网络", top_k=5, score_threshold=0.0)
    assert any("卷积" in (c.chunk.text or "") for c in res)


def test_load_index_missing_returns_none(tmp_path):
    assert load_index(tmp_path / "nope.json") is None


def test_load_index_corrupt_returns_none(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert load_index(p) is None


# ── CLI 端到端 ───────────────────────────────────────────────────────

def test_rag_index_then_query_end_to_end(tmp_path, capsys):
    import orchestrator.cli as cli

    ws = _init_workspace(tmp_path)
    docs = ws / "docs"
    docs.mkdir(exist_ok=True)
    _write_doc(docs / "a.md", "# 阿尔茨海默病\nAlphaFold 构象差异 生物标志物 研究")
    _write_doc(docs / "b.md", "# 深度学习\n卷积神经网络 图像分类 应用")
    _write_doc(docs / "skip.pdf", "binary-ish")  # 不匹配默认 glob，不索引

    rc = cli.cmd_rag(_ns(action="index", target=str(docs), query=None,
                         path=str(ws), glob="*.md", top_k=None, reset=False,
                         json=False, force_citation_only=False, min_score=None))
    assert rc == 0
    index_file = ws / ".verity" / "rag-index.json"
    assert index_file.exists()

    rc2 = cli.cmd_rag(_ns(action="query", target=None, query="构象差异 生物标志物",
                          path=str(ws), glob="*.md", top_k=None, reset=False,
                          json=False, force_citation_only=False, min_score=None))
    assert rc2 == 0
    out = capsys.readouterr().out
    # 离线 hash 嵌入器 + 放宽阈值：应命中索引文献
    assert "命中=0" not in out


def test_rag_index_query_json_output(tmp_path, capsys):
    import orchestrator.cli as cli

    ws = _init_workspace(tmp_path)
    docs = ws / "docs"
    docs.mkdir(exist_ok=True)
    _write_doc(docs / "a.md", "AlphaFold 构象差异 生物标志物")
    cli.cmd_rag(_ns(action="index", target=str(docs), query=None, path=str(ws),
                     glob="*.md", top_k=None, reset=False, json=False,
                     force_citation_only=False, min_score=None))
    cli.cmd_rag(_ns(action="query", target=None, query="构象差异", path=str(ws),
                     glob="*.md", top_k=3, reset=False, json=True,
                     force_citation_only=False, min_score=None))
    out = capsys.readouterr().out
    data = json.loads(out.strip().splitlines()[-1])
    assert data["mode"] in ("full", "citation_only")
    assert isinstance(data["chunks"], list)
    assert data["chunks"], "离线放宽阈值下应命中已索引文献"
    assert data["citations"]
    assert data["chunks"][0]["score"] > 0


def test_rag_query_min_score_override(tmp_path, capsys):
    import orchestrator.cli as cli

    ws = _init_workspace(tmp_path)
    docs = ws / "docs"
    docs.mkdir(exist_ok=True)
    _write_doc(docs / "a.md", "AlphaFold 构象差异 生物标志物")
    cli.cmd_rag(_ns(action="index", target=str(docs), query=None, path=str(ws),
                     glob="*.md", top_k=None, reset=False, json=False,
                     force_citation_only=False, min_score=None))
    # 显式高阈值（真实嵌入量级）→ 无命中；显式低阈值 → 有命中
    cli.cmd_rag(_ns(action="query", target=None, query="构象差异", path=str(ws),
                     glob="*.md", top_k=3, reset=False, json=True,
                     force_citation_only=False, min_score=0.99))
    strict = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert strict["chunks"] == []
    cli.cmd_rag(_ns(action="query", target=None, query="构象差异", path=str(ws),
                     glob="*.md", top_k=3, reset=False, json=True,
                     force_citation_only=False, min_score=0.0))
    loose = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert loose["chunks"]


def test_rag_index_dedup_on_rerun(tmp_path):
    import orchestrator.cli as cli

    ws = _init_workspace(tmp_path)
    docs = ws / "docs"
    docs.mkdir(exist_ok=True)
    _write_doc(docs / "a.md", "AlphaFold 构象差异 生物标志物")
    cli.cmd_rag(_ns(action="index", target=str(docs), query=None, path=str(ws),
                     glob="*.md", top_k=None, reset=False, json=False,
                     force_citation_only=False, min_score=None))
    first = load_index(ws / ".verity" / "rag-index.json").size
    # 同目录再跑一次，分片数不应翻倍（按 chunk_id 去重）
    cli.cmd_rag(_ns(action="index", target=str(docs), query=None, path=str(ws),
                     glob="*.md", top_k=None, reset=False, json=False,
                     force_citation_only=False, min_score=None))
    second = load_index(ws / ".verity" / "rag-index.json").size
    assert second == first
    assert first > 0


def test_rag_index_reset_rebuilds_not_stacks(tmp_path):
    import orchestrator.cli as cli

    ws = _init_workspace(tmp_path)
    docs = ws / "docs"
    docs.mkdir(exist_ok=True)
    _write_doc(docs / "a.md", "AlphaFold 构象差异 生物标志物")
    cli.cmd_rag(_ns(action="index", target=str(docs), query=None, path=str(ws),
                     glob="*.md", top_k=None, reset=False, json=False,
                     force_citation_only=False, min_score=None))
    first = load_index(ws / ".verity" / "rag-index.json").size
    # reset 应重建而非叠加 → 分片数等于首次，而非翻倍
    cli.cmd_rag(_ns(action="index", target=str(docs), query=None, path=str(ws),
                     glob="*.md", top_k=None, reset=True, json=False,
                     force_citation_only=False, min_score=None))
    after = load_index(ws / ".verity" / "rag-index.json").size
    assert after == first
    assert first > 0


# ── 埋点 opt-in 接线 ─────────────────────────────────────────────────

def test_rag_index_write_telemetry_recorded_when_enabled(tmp_path, monkeypatch):
    import orchestrator.cli as cli

    monkeypatch.setenv("VL_TELEMETRY", "1")
    ws = _init_workspace(tmp_path)
    docs = ws / "docs"
    docs.mkdir(exist_ok=True)
    _write_doc(docs / "a.md", "AlphaFold 构象差异 生物标志物")
    cli.cmd_rag(_ns(action="index", target=str(docs), query=None, path=str(ws),
                     glob="*.md", top_k=None, reset=False, json=False,
                     force_citation_only=False, min_score=None))
    audit = ws / ".verity" / "collab-audit.jsonl"
    assert audit.exists()
    events = _read_jsonl(audit)
    rag_events = [e for e in events if e["event"] == "rag_index_write"]
    assert rag_events, "opt-in 开启应记录 rag_index_write"
    assert rag_events[0]["op"] == "add"
    assert rag_events[0]["chunks_added"] >= 1


def test_rag_index_write_no_side_effect_when_disabled(tmp_path, monkeypatch):
    import orchestrator.cli as cli

    monkeypatch.delenv("VL_TELEMETRY", raising=False)
    ws = _init_workspace(tmp_path)
    docs = ws / "docs"
    docs.mkdir(exist_ok=True)
    _write_doc(docs / "a.md", "AlphaFold 构象差异 生物标志物")
    cli.cmd_rag(_ns(action="index", target=str(docs), query=None, path=str(ws),
                     glob="*.md", top_k=None, reset=False, json=False,
                     force_citation_only=False, min_score=None))
    # 索引文件应落盘（功能可用），但审计目录不应因埋点产生
    assert (ws / ".verity" / "rag-index.json").exists()
    assert not (ws / ".verity" / "collab-audit.jsonl").exists()


# ── 参数错误与空索引 ─────────────────────────────────────────────────

def test_rag_index_missing_target_errors(tmp_path):
    import orchestrator.cli as cli

    ws = _init_workspace(tmp_path)
    rc = cli.cmd_rag(_ns(action="index", target=None, query=None, path=str(ws),
                         glob="*.md", top_k=None, reset=False, json=False,
                         force_citation_only=False, min_score=None))
    assert rc == cli.EXIT_ERROR


def test_rag_query_missing_query_errors(tmp_path):
    import orchestrator.cli as cli

    ws = _init_workspace(tmp_path)
    rc = cli.cmd_rag(_ns(action="query", target=None, query=None, path=str(ws),
                         glob="*.md", top_k=None, reset=False, json=False,
                         force_citation_only=False, min_score=None))
    assert rc == cli.EXIT_ERROR


def test_rag_query_empty_index_graceful(tmp_path):
    import orchestrator.cli as cli

    ws = _init_workspace(tmp_path)
    rc = cli.cmd_rag(_ns(action="query", target=None, query="x", path=str(ws),
                         glob="*.md", top_k=None, reset=False, json=False,
                         force_citation_only=False, min_score=None))
    assert rc == cli.EXIT_OK
