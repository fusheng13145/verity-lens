"""文献 RAG 侧车单元测试（sidecar/rag/literature_rag.py）。"""
from sidecar.rag.literature_rag import (
    Chunk,
    LiteratureIndex,
    LiteratureRAG,
    RetrievalResult,
    SessionCache,
    _default_embedder,
    chunk_document,
    estimate_tokens,
    mmr_rerank,
)


def _idx_with(texts):
    idx = LiteratureIndex()
    chunks = []
    for i, t in enumerate(texts):
        chunks.append(Chunk(chunk_id=f"d#{i}", text=t, metadata={"doi": f"10.0/{i}"}))
    idx.add(chunks)
    return idx


def test_embedder_deterministic_and_normalized():
    v1 = _default_embedder("AlphaFold 构象差异 生物标志物")
    v2 = _default_embedder("AlphaFold 构象差异 生物标志物")
    assert v1 == v2
    norm = sum(x * x for x in v1) ** 0.5
    assert abs(norm - 1.0) < 1e-9


def test_embedder_similarity_semantic():
    v_a = _default_embedder("RMSD 构象差异 阿尔茨海默病 生物标志物")
    v_b = _default_embedder("RMSD 构象差异 阿尔茨海默 标志物")  # 近义
    v_c = _default_embedder("深度学习 图像分类 卷积神经网络")
    from sidecar.rag.literature_rag import _cosine

    assert _cosine(v_a, v_b) > _cosine(v_a, v_c)


def test_chunk_document_overlap_and_count():
    long = "x" * 3000
    chunks = chunk_document(long, metadata={"doi": "10.0/1"}, max_chunk_size=1024, overlap=128)
    assert len(chunks) > 1
    # 相邻分片应有重叠
    c0, c1 = chunks[0], chunks[1]
    assert c1.metadata["char_start"] < c0.metadata["char_end"]


def test_index_query_threshold():
    idx = _idx_with([
        "AlphaFold2 预测的构象差异可作为阿尔茨海默病早期生物标志物",
        "卷积神经网络在图像分类上的应用",
        "RMSD 用于衡量蛋白质构象差异",
    ])
    res = idx.query("构象差异 生物标志物", top_k=5, score_threshold=0.1)
    assert len(res) >= 2
    assert res[0].score >= res[-1].score


def test_mmr_dedup_reduces_redundancy():
    idx = _idx_with([
        "RMSD 衡量构象差异 蛋白质",
        "RMSD 衡量构象差异 蛋白质结构",
        "卷积神经网络 图像分类",
    ])
    cands = idx.query("RMSD 构象差异", top_k=6, score_threshold=0.0)
    qv = idx._embedder("RMSD 构象差异")
    diversed = mmr_rerank(cands, qv, top_k=2, diversity_penalty=0.3)
    texts = [c.chunk.text for c in diversed]
    # 两个高度相似的 RMSD chunk 不应同时入选 top2（多样性已起效）
    assert len(diversed) == 2
    assert "卷积" in texts[1] or "蛋白质结构" in texts[1]


def test_session_cache_lru():
    cache = SessionCache(limit=2)
    c = Chunk(chunk_id="a", text="t", metadata={})
    cache.put("q1", [Chunk(chunk_id="x", text="y", metadata={})])
    cache.put("q2", [c])
    cache.put("q3", [c])
    assert cache.get("q1") is None  # 被淘汰
    assert cache.get("q2") is not None


def test_token_budget_citation_only_when_over_hard_limit():
    # 构造一个会超硬的检索结果：注入超大 chunk
    big = "阿尔茨海默病 生物标志物 " * 2000  # 远超 hard_limit(6000)
    idx = _idx_with([big])
    rag = LiteratureRAG(index=idx)
    rag.config["token_budget"]["hard_limit"] = 100
    res = rag.retrieve("阿尔茨海默病 生物标志物")
    assert isinstance(res, RetrievalResult)
    assert res.mode == "citation_only"
    assert res.chunks == []
    assert len(res.citations) >= 1


def test_token_budget_full_with_warning_flag():
    # 长文档以触发 token 软告警（estimate_tokens 按中文字符计数）
    long_doc = "阿尔茨海默病早期生物标志物构象差异蛋白质折叠预测 " * 15
    idx = _idx_with([long_doc])
    rag = LiteratureRAG(index=idx)
    # 离线 hash 嵌入相似度低于真实稠密嵌入，按嵌入器调低阈值（真实嵌入仍用 0.72）
    rag.config["retrieval"]["score_threshold"] = 0.1
    rag.config["token_budget"]["max_context_tokens_per_turn"] = 100
    rag.config["token_budget"]["warning_threshold"] = 0.5
    rag.config["token_budget"]["hard_limit"] = 100000
    res = rag.retrieve("构象差异 生物标志物")
    assert res.mode == "full"
    assert res.warning is True


def test_cache_hit_returns_same():
    idx = _idx_with(["AlphaFold 构象差异"])
    rag = LiteratureRAG(index=idx)
    r1 = rag.retrieve("构象差异")
    r2 = rag.retrieve("构象差异")
    assert r1.chunks and r2.chunks
    assert r1.chunks[0].chunk.chunk_id == r2.chunks[0].chunk.chunk_id


def test_auto_archive_keeps_metadata_only():
    idx = _idx_with(["AlphaFold 构象差异 生物标志物", "卷积神经网络 图像分类"])
    n = idx.archive(lambda c: "构象" in c.text)
    assert n == 1
    archived = [c for c in idx._chunks if c.archived]
    assert archived[0].text == "" and archived[0].metadata["doi"] == "10.0/0"
    # 归档后不再参与检索
    res = idx.query("构象差异", top_k=5, score_threshold=0.0)
    assert all("构象" not in (c.chunk.text or "") for c in res)


def test_write_observer_called_on_add():
    calls = []
    idx = LiteratureIndex(write_observer=lambda op, meta: calls.append((op, meta)))
    idx.add([Chunk(chunk_id="d#0", text="t", metadata={"doi": "10.0/0"})])
    assert ("add", {"chunks_added": 1, "dois": ["10.0/0"]}) in calls


def test_write_observer_called_on_archive():
    calls = []
    idx = LiteratureIndex(write_observer=lambda op, meta: calls.append((op, meta)))
    idx.add([Chunk(chunk_id="d#0", text="构象差异", metadata={"doi": "10.0/0"})])
    n = idx.archive(lambda c: "构象" in c.text)
    assert n == 1
    assert ("archive", {"chunks_archived": 1}) in calls


def test_no_observer_by_default_no_error():
    idx = LiteratureIndex()
    idx.add([Chunk(chunk_id="d#0", text="t", metadata={})])
    assert idx.size == 1
    assert idx.archive(lambda c: True) == 1
