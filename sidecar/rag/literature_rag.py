"""Sidecar RAG：文献向量检索（完整版，orchestrator/../sidecar/rag）。

设计原则（design-blueprint.md §2.7.1）：
- 离线可测：默认嵌入器为确定性 hash 向量（无需外部 API / numpy）。
- 可插拔嵌入：传入 ``embedder`` 即可替换为真实 embedding 模型。
- 检索链路：分片 → 向量检索 → 分数阈值过滤 → MMR 去重 → token 预算 → citation-only 降级。
- 会话缓存（LRU）：命中直接返回，控制 token 膨胀。
- citation-only 模式：超硬上限时只返回引用元数据，不注入全文。
- auto-archive：超龄分片归档（仅保留元数据），回拉按需。

所有外部依赖（网络 / 模型）均通过参数注入，单测可完全离线运行。
"""
from __future__ import annotations

import json
import math
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

# ── 默认配置（来源 blueprint §2.7.1）─────────────────────────────────────
CONFIG = {
    "chunking": {"method": "semantic", "max_chunk_size": 1024, "overlap": 128},
    "indexing": {
        "embeddings_model": "text-embedding-3-small",
        "vector_dim": 1536,
        "index_type": "HNSW",
        "dedup_by": "doi",
    },
    "retrieval": {"top_k": 8, "score_threshold": 0.72, "diversity_penalty": 0.3},
    "cache": {"per_session_limit": 50, "ttl": "session", "eviction_policy": "LRU"},
    "token_budget": {
        "max_context_tokens_per_turn": 4000,
        "warning_threshold": 0.7,
        "hard_limit": 6000,
        "overflow_strategy": "truncate_oldest",
    },
    "anti_bloat": {
        "auto_archive": {"trigger": "项目 > 3 个月未活动", "restore": "用户明确引用时按需拉回"}
    },
}

# 离线默认 hash 嵌入器的余弦相似度量级显著低于真实稠密嵌入（依 token 重叠约 0.5~0.85），
# 蓝图阈值 0.72 面向真实嵌入模型；离线路径（无外部依赖、确定性）用此放宽阈值保证检索可用。
# 接入真实嵌入模型后，调用方应改回 CONFIG 的 0.72（或经 CLI --min-score 显式指定）。
OFFLINE_SCORE_THRESHOLD = 0.05

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_CJK_RE = re.compile(r"[一-鿿]")


def _tokens(text: str) -> list[str]:
    """分词：拉丁/数字词 + 中文单字 + 中文二元组。

    中文无空格，需拆成字/二元组才能做子短语匹配；拉丁词保持原样。
    """
    text = text.lower()
    toks: list[str] = _TOKEN_RE.findall(text)
    cjk = _CJK_RE.findall(text)
    toks.extend(cjk)  # 单字
    for i in range(len(cjk) - 1):
        toks.append(cjk[i] + cjk[i + 1])  # 二元组
    return toks


def estimate_tokens(text: str) -> int:
    """粗略 token 估算：英文按词、中文按字，取二者较大者。"""
    if not text:
        return 0
    words = len(_TOKEN_RE.findall(text))
    cjk = len(_CJK_RE.findall(text))
    return max(words, cjk)


def _default_embedder(text: str, dim: int = 256) -> list[float]:
    """确定性 hash 嵌入（离线、无依赖）。

    将文本切分为 token（拉丁词 + 中文单字/二元组），按 FNV-1a 哈希映射到 dim
    维并累加，最后 L2 归一化。同文本必得同向量；语义相近（共享大量词汇）的文本
    余弦相似度更高。
    """
    vec = [0.0] * dim
    for tok in _tokens(text):
        h = 2166136261
        for ch in tok.encode("utf-8"):
            h ^= ch
            h = (h * 16777619) & 0xFFFFFFFF
        vec[h % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    metadata: dict
    vector: list[float] = field(default_factory=list)
    archived: bool = False  # auto-archive 后仅留元数据


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float


def chunk_document(
    text: str,
    metadata: dict | None = None,
    max_chunk_size: int = 1024,
    overlap: int = 128,
) -> list[Chunk]:
    """按字符窗口分片（语义分片的离线近似），相邻分片保留 overlap 重叠。

    metadata 会被复制到每个 chunk（附加 char_start/char_end）。
    """
    meta = dict(metadata or {})
    if not text:
        return []
    chunks: list[Chunk] = []
    step = max(1, max_chunk_size - overlap)
    start = 0
    idx = 0
    n = len(text)
    while start < n:
        end = min(n, start + max_chunk_size)
        piece = text[start:end]
        cm = {**meta, "char_start": start, "char_end": end}
        chunks.append(Chunk(chunk_id=f"{meta.get('doi', 'doc')}#{idx}", text=piece, metadata=cm))
        if end >= n:
            break
        start += step
        idx += 1
    return chunks


class LiteratureIndex:
    """内存向量索引（HNSW 在此用线性扫描近似；接口稳定，可替换）。"""

    def __init__(
        self,
        embedder: Callable[[str], list[float]] | None = None,
        vector_dim: int = 256,
        write_observer: Callable[[str, dict], None] | None = None,
    ):
        self._embedder = embedder or (lambda t: _default_embedder(t, vector_dim))
        self._dim = vector_dim
        self._chunks: list[Chunk] = []
        self._write_observer = write_observer  # opt-in 写入观测回调（零依赖、零副作用）

    def add(self, chunks: Iterable[Chunk]) -> None:
        items = list(chunks)
        for c in items:
            if not c.vector:
                c.vector = self._embedder(c.text)
            self._chunks.append(c)
        if self._write_observer:
            self._write_observer(
                "add",
                {
                    "chunks_added": len(items),
                    "dois": sorted({c.metadata.get("doi") for c in items}),
                },
            )

    @property
    def size(self) -> int:
        return len(self._chunks)

    def query(
        self,
        query: str,
        top_k: int = 8,
        score_threshold: float = 0.0,
    ) -> list[ScoredChunk]:
        qv = self._embedder(query)
        scored = [
            ScoredChunk(chunk=c, score=_cosine(qv, c.vector))
            for c in self._chunks
            if not c.archived
        ]
        scored.sort(key=lambda s: s.score, reverse=True)
        out = [s for s in scored if s.score >= score_threshold]
        return out[:top_k]

    def archive(self, predicate: Callable[[Chunk], bool]) -> int:
        """归档满足 predicate 的分片（仅保留元数据）。返回归档数量。"""
        count = 0
        for c in self._chunks:
            if not c.archived and predicate(c):
                c.text = ""
                c.vector = []
                c.archived = True
                count += 1
        if self._write_observer:
            self._write_observer("archive", {"chunks_archived": count})
        return count


def mmr_rerank(
    candidates: list[ScoredChunk],
    query_vector: list[float],
    top_k: int,
    diversity_penalty: float = 0.3,
    embedder: Callable[[str], list[float]] | None = None,
) -> list[ScoredChunk]:
    """最大边际相关（MMR）重排：在相关性与多样性间权衡，避免重复片段。"""
    emb = embedder or _default_embedder
    selected: list[ScoredChunk] = []
    remaining = list(candidates)
    while remaining and len(selected) < top_k:
        best_idx = 0
        best_val = -math.inf
        for i, cand in enumerate(remaining):
            relevance = cand.score
            if selected:
                max_sim = max(
                    _cosine(emb(cand.chunk.text), emb(s.chunk.text)) for s in selected
                )
            else:
                max_sim = 0.0
            val = relevance - diversity_penalty * max_sim
            if val > best_val:
                best_val = val
                best_idx = i
        selected.append(remaining.pop(best_idx))
    return selected


class SessionCache:
    """会话级 LRU 缓存（按 query 命中）。"""

    def __init__(self, limit: int = 50):
        self._limit = limit
        self._store: "OrderedDict[str, list[ScoredChunk]]" = OrderedDict()

    def get(self, query: str) -> list[ScoredChunk] | None:
        if query in self._store:
            self._store.move_to_end(query)
            return self._store[query]
        return None

    def put(self, query: str, results: list[ScoredChunk]) -> None:
        self._store[query] = results
        self._store.move_to_end(query)
        while len(self._store) > self._limit:
            self._store.popitem(last=False)

    @property
    def size(self) -> int:
        return len(self._store)


@dataclass
class RetrievalResult:
    mode: str  # "full" | "citation_only"
    chunks: list[ScoredChunk] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    tokens_used: int = 0
    warning: bool = False


class LiteratureRAG:
    """文献 RAG 编排门面：缓存 → 检索 → MMR → token 预算 → citation-only 降级。"""

    def __init__(
        self,
        index: LiteratureIndex | None = None,
        cache: SessionCache | None = None,
        config: dict | None = None,
        embedder: Callable[[str], list[float]] | None = None,
        write_observer: Callable[[str, dict], None] | None = None,
    ):
        self.config = config or CONFIG
        self.index = index or LiteratureIndex(
            embedder=embedder, write_observer=write_observer
        )
        self.cache = cache or SessionCache(self.config["cache"]["per_session_limit"])

    def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        force_citation_only: bool = False,
    ) -> RetrievalResult:
        top_k = top_k or self.config["retrieval"]["top_k"]
        threshold = self.config["retrieval"]["score_threshold"]
        budget = self.config["token_budget"]
        hard = budget["hard_limit"]

        # ① 缓存命中
        cached = self.cache.get(query)
        if cached is not None:
            return self._budget(cached, budget, hard, force_citation_only)

        # ② 向量检索 + 阈值过滤
        candidates = self.index.query(query, top_k=top_k * 2, score_threshold=threshold)
        if not candidates:
            return RetrievalResult(mode="full", chunks=[], citations=[], tokens_used=0)

        # ③ MMR 去重
        qv = self.index._embedder(query)
        diversed = mmr_rerank(
            candidates,
            qv,
            top_k=top_k,
            diversity_penalty=self.config["retrieval"]["diversity_penalty"],
        )
        self.cache.put(query, diversed)
        return self._budget(diversed, budget, hard, force_citation_only)

    @staticmethod
    def _budget(
        chunks: list[ScoredChunk],
        budget: dict,
        hard_limit: int,
        force_citation_only: bool,
    ) -> RetrievalResult:
        per_turn = budget["max_context_tokens_per_turn"]
        warn_at = budget["warning_threshold"]
        total = sum(estimate_tokens(c.chunk.text) for c in chunks)

        citations = [
            {
                "chunk_id": c.chunk.chunk_id,
                "doi": c.chunk.metadata.get("doi"),
                "score": round(c.score, 4),
                "section": c.chunk.metadata.get("section_title"),
            }
            for c in chunks
        ]

        # 超硬上限或显式降级 → citation-only
        if force_citation_only or total > hard_limit:
            return RetrievalResult(
                mode="citation_only",
                chunks=[],
                citations=citations,
                tokens_used=sum(estimate_tokens(c["doi"] or "") + 8 for c in citations),
            )

        # 软告警
        warning = total >= warn_at * per_turn
        return RetrievalResult(
            mode="full", chunks=chunks, citations=citations, tokens_used=total, warning=warning
        )


def save_index(index: "LiteratureIndex", path: Path) -> None:
    """持久化索引到 JSON（含预计算向量）。

    仅依赖标准库；向量与分片一并落盘，重建时无需重算（默认 hash 嵌入器确定性，
    查询时按相同方式重算即可）。用于编排层 CLI（``vl rag``）跨进程共享同一份索引。
    """
    payload = {
        "schema_version": 1,
        "vector_dim": index._dim,
        "embedder": "default_hash",
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "text": c.text,
                "metadata": c.metadata,
                "vector": c.vector,
                "archived": c.archived,
            }
            for c in index._chunks
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_index(path: Path, *, write_observer: Callable[[str, dict], None] | None = None) -> "LiteratureIndex | None":
    """从 JSON 重建索引；文件不存在 / 损坏 / 为空时返回 ``None``。

    重建后复用默认 hash 嵌入器（与落盘向量同构），查询重算与写入保持一致。
    ``write_observer`` 透传给 ``LiteratureIndex``，使后续 ``add`` / ``archive`` 仍可触发观测。
    """
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    dim = data.get("vector_dim", 256)
    idx = LiteratureIndex(vector_dim=dim, write_observer=write_observer)
    for c in data.get("chunks", []):
        chunk = Chunk(
            chunk_id=c.get("chunk_id", ""),
            text=c.get("text", ""),
            metadata=c.get("metadata", {}),
            vector=c.get("vector", []),
            archived=c.get("archived", False),
        )
        idx._chunks.append(chunk)
    return idx


def retrieve(query: str) -> list:
    """蓝图占位函数的向后兼容入口（默认空索引）。"""
    return LiteratureRAG().retrieve(query).chunks
