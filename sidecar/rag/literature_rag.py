"""Sidecar RAG：文献向量检索占位。

语义分片 / MMR 去重 / 会话缓存 / token 预算 / citation-only 降级 / auto-archive。
完整配置见 docs/design-blueprint.md §2.7.1。
"""
from __future__ import annotations

CONFIG = {
    "chunking": {"method": "semantic", "max_chunk_size": 1024, "overlap": 128},
    "indexing": {"embeddings_model": "text-embedding-3-small", "vector_dim": 1536, "index_type": "HNSW"},
    "retrieval": {"top_k": 8, "score_threshold": 0.72, "diversity_penalty": 0.3},
    "token_budget": {"max_context_tokens_per_turn": 4000, "hard_limit": 6000},
}


def retrieve(query: str) -> list:
    # Phase 3 实现
    return []
