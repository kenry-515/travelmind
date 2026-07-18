# TravelMind Agent — RAG Module
#
# Embedding → Vector Store → Retriever
#
# Usage:
#   from app.rag.embedding import init_embedding_provider, get_embedding_provider
#   from app.rag.vector_store import ChromaStore, get_vector_store
#   from app.rag.retriever import retrieve, retrieve_by_preferences
#
# Startup initialization:
#   from app.rag import init_rag_from_data
#   init_rag_from_data(Path("data/attractions.json"))

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.rag.embedding import (
    BaseEmbeddingProvider,
    CompositeEmbeddingProvider,
    TFIDFEmbeddingProvider,
    get_embedding_provider,
    init_embedding_provider,
)
from app.rag.vector_store import ChromaStore, get_vector_store
from app.rag.retriever import retrieve, retrieve_by_preferences

logger = logging.getLogger(__name__)

__all__ = [
    # embedding
    "BaseEmbeddingProvider",
    "TFIDFEmbeddingProvider",
    "CompositeEmbeddingProvider",
    "init_embedding_provider",
    "get_embedding_provider",
    # vector store
    "ChromaStore",
    "get_vector_store",
    # retriever
    "retrieve",
    "retrieve_by_preferences",
    # startup
    "init_rag_from_data",
]


def init_rag_from_data(
    attractions_path: Path,
    tags_path: Optional[Path] = None,
    max_features: int = 1024,
) -> bool:
    """Initialize the full RAG pipeline from data files.

    This is the single entry point for RAG initialization at application
    startup. It loads attraction data, fits the embedding provider,
    and connects Chroma.

    Args:
        attractions_path: Path to attractions.json.
        tags_path: Path to tags.json (default: data/tags.json).
        max_features: Max TF-IDF features.

    Returns:
        True on success, False if RAG is unavailable.
    """
    if not attractions_path.exists():
        logger.warning(
            f"{attractions_path} not found — RAG disabled. "
            "Run scripts/build_knowledge_base.py first."
        )
        return False

    with open(attractions_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    attractions: List[dict] = data.get("attractions", [])
    if not attractions:
        logger.warning("No attractions in knowledge base — RAG disabled.")
        return False

    # Build document corpus
    documents = [_build_document(a) for a in attractions]
    tags_lists = [a.get("tags", []) or [] for a in attractions]

    # Load tag vocabulary
    tag_vocab = _load_tag_vocabulary(tags_path)

    # Initialize embedding provider
    init_embedding_provider(
        corpus=documents,
        tags_list=tags_lists,
        tag_vocabulary=tag_vocab,
        max_features=max_features,
    )

    # Connect Chroma
    store = get_vector_store()
    if not store.is_connected:
        store.connect()

    logger.info(
        f"RAG initialized: {len(attractions)} attractions, "
        f"{len(tag_vocab)} tags, Chroma={store.count()} docs"
    )
    return True


# ── Helpers (shared with build_knowledge_base.py) ────────


def _load_tag_vocabulary(tags_path: Optional[Path] = None) -> List[str]:
    """Load global tag vocabulary from tags.json."""
    if tags_path is None:
        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        tags_path = data_dir / "tags.json"
    if tags_path.exists():
        with open(tags_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("all_tags", [])
    return []


def _build_document(attraction: Dict[str, Any]) -> str:
    """Build a searchable document string from an attraction.

    Characters with semantic weight:
      - Name (repeated for TF-IDF weight boost)
      - City
      - Description (first 500 chars)
      - Tags
      - Instance type
      - Suitable for
    """
    parts = []

    name = attraction.get("name", "")
    if name:
        parts.append(f"{name} {name}")

    city = attraction.get("city", "")
    if city:
        parts.append(f"位于{city}")

    desc = attraction.get("description", "")
    if desc:
        parts.append(desc[:500])

    instance_type = attraction.get("instance_of", "")
    if instance_type:
        parts.append(f"类型: {instance_type}")

    tags = attraction.get("tags", []) or []
    if tags:
        parts.append(f"标签: {' '.join(tags)}")

    suitable = attraction.get("suitable_for", "")
    if suitable:
        parts.append(f"适合: {suitable}")

    return "\n".join(parts)
