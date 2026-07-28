"""
RAG 层测试 — 嵌入式提供程序
"""

import pytest
from app.rag.embedding import init_embedding_provider


@pytest.mark.asyncio
async def test_tfidf_fit_and_embed_query():
    """TF-IDF 能拟合文本并产生查询嵌入。"""
    provider = init_embedding_provider(
        corpus=["故宫是北京的世界遗产", "长城是世界奇迹", "西湖在杭州"],
        max_features=1024,
    )
    assert provider is not None
    assert provider.dimension > 0
    vec = provider.embed_query("故宫")
    assert len(vec) > 0
    assert all(isinstance(v, float) for v in vec)


@pytest.mark.asyncio
async def test_embedding_consistent():
    """相同文本应产生相同的嵌入向量。"""
    provider = init_embedding_provider(
        corpus=["故宫是北京的世界遗产", "长城是世界奇迹"],
        max_features=512,
    )
    v1 = provider.embed_query("故宫")
    v2 = provider.embed_query("故宫")
    diff = sum(abs(a - b) for a, b in zip(v1, v2))
    assert diff < 1e-10


@pytest.mark.asyncio
async def test_embedding_different_texts_different_vectors():
    """不同文本应产生不同嵌入。"""
    provider = init_embedding_provider(
        corpus=["故宫是北京的世界遗产", "长城是世界奇迹", "西湖在杭州"],
        max_features=1024,
    )
    v_a = provider.embed_query("故宫")
    v_b = provider.embed_query("西湖")
    diff = sum(abs(a - b) for a, b in zip(v_a, v_b))
    assert diff > 0.001


@pytest.mark.asyncio
async def test_composite_provider():
    """组合提供程序能正确拼接嵌入。"""
    from app.rag.embedding import CompositeEmbeddingProvider
    base = init_embedding_provider(
        corpus=["故宫是北京的世界遗产", "长城是世界奇迹"],
        max_features=256,
    )
    composite = CompositeEmbeddingProvider(
        tfidf=base,
        tag_vocabulary=["历史", "自然", "美食"],
    )
    vec = composite.embed_query("故宫", tags=["历史"])
    assert len(vec) > 0
