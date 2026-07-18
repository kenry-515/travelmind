"""
TravelMind Agent — Chroma Vector Store Wrapper

Provides a clean interface around ChromaDB for:
  - Adding documents with pre-computed embeddings
  - Similarity search (top-K)
  - Filtered search by metadata (city, tags, price_level, etc.)
  - Collection management

Uses pre-computed embeddings so the embedding provider is decoupled
from Chroma's built-in embedding functions.
"""

import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.api.types import Embedding, Metadata

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Default collection name
DEFAULT_COLLECTION = "attractions"


class ChromaStore:
    """ChromaDB vector store wrapper for attraction knowledge base."""

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        collection_name: str = DEFAULT_COLLECTION,
    ):
        persist_dir = persist_dir or settings.CHROMA_PERSIST_DIR
        self._persist_dir = str(Path(persist_dir).resolve())
        self._collection_name = collection_name
        self._client: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[Any] = None
        self._connected = False

    # -- Connection management --

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        """Initialize the Chroma persistent client and get/create collection."""
        try:
            import os
            os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

            Path(self._persist_dir).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self._persist_dir)
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._connected = True
            logger.info(
                f"Chroma connected: {self._persist_dir} "
                f"(collection={self._collection_name}, "
                f"count={self._collection.count()})"
            )
        except Exception as e:
            logger.error(f"Failed to connect to Chroma: {e}")
            self._connected = False
            self._collection = None
            raise

    def disconnect(self) -> None:
        """Close the Chroma client (if needed in future versions)."""
        self._connected = False
        self._collection = None
        self._client = None

    # -- Document operations --

    def add_documents(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        batch_size: int = 150,
    ) -> List[str]:
        """Add documents with pre-computed embeddings to the store.

        Args:
            documents: List of document texts (name + description).
            embeddings: Pre-computed embedding vectors (same length as documents).
            metadatas: Optional metadata dicts (city, tags, price_level, ...).
            ids: Optional document IDs (auto-generated UUIDs if not provided).
            batch_size: Add in batches to avoid memory issues.

        Returns:
            List of document IDs.
        """
        if not self._connected or self._collection is None:
            raise RuntimeError("ChromaStore not connected. Call connect() first.")

        if ids is None:
            ids = [str(uuid.uuid4()) for _ in documents]

        if len(documents) != len(embeddings):
            raise ValueError(
                f"Mismatch: {len(documents)} documents vs {len(embeddings)} embeddings"
            )
        if len(ids) != len(documents):
            raise ValueError(
                f"Mismatch: {len(documents)} documents vs {len(ids)} ids"
            )

        # Chroma requires metadata values to be str, int, float, or bool
        clean_metas: List[Optional[Metadata]] = None
        if metadatas:
            clean_metas = [
                _sanitize_metadata(m) if m else None
                for m in metadatas
            ]

        # Batch insert
        total = len(documents)
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            try:
                self._collection.add(
                    documents=documents[start:end],
                    embeddings=embeddings[start:end],  # type: ignore
                    metadatas=clean_metas[start:end] if clean_metas else None,  # type: ignore
                    ids=ids[start:end],
                )
            except Exception as e:
                logger.error(f"Failed to add batch [{start}:{end}]: {e}")
                raise

        logger.info(f"Added {total} documents to Chroma")
        return ids

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 20,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic similarity search.

        Args:
            query_embedding: Query embedding vector.
            top_k: Number of results to return.
            where: Chroma metadata filter dict.
            where_document: Chroma document content filter dict.

        Returns:
            List of result dicts with keys: id, document, metadata, score.
        """
        if not self._connected or self._collection is None:
            raise RuntimeError("ChromaStore not connected. Call connect() first.")

        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where,
                where_document=where_document,
            )
        except Exception as e:
            logger.error(f"Chroma query error: {e}")
            return []

        # Flatten Chroma's result format
        ids = results.get("ids", [[]])[0] or []
        docs = results.get("documents", [[]])[0] or []
        metas = results.get("metadatas", [[]])[0] or []
        distances = results.get("distances", [[]])[0] or []

        output = []
        for i, doc_id in enumerate(ids):
            item: Dict[str, Any] = {
                "id": doc_id,
                "document": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
                "score": 1.0 - distances[i] if i < len(distances) else 0.0,
            }
            output.append(item)

        return output

    def delete_collection(self) -> None:
        """Delete the collection entirely (for rebuild)."""
        if self._client and self._connected:
            try:
                self._client.delete_collection(self._collection_name)
                logger.info(f"Deleted collection '{self._collection_name}'")
                self._collection = None
            except Exception as e:
                logger.warning(f"Failed to delete collection: {e}")

    def count(self) -> int:
        """Return the number of documents in the collection."""
        if not self._connected or self._collection is None:
            return 0
        return self._collection.count()

    def get_by_ids(self, ids: List[str]) -> List[Dict[str, Any]]:
        """Retrieve documents by ID."""
        if not self._connected or self._collection is None:
            return []
        try:
            results = self._collection.get(ids=ids)
            output = []
            for i, doc_id in enumerate(results.get("ids", [])):
                output.append({
                    "id": doc_id,
                    "document": results["documents"][i] if results.get("documents") else "",
                    "metadata": results["metadatas"][i] if results.get("metadatas") else {},
                })
            return output
        except Exception as e:
            logger.error(f"Chroma get_by_ids error: {e}")
            return []


# ── Helpers ──────────────────────────────────────────────


def _sanitize_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all metadata values are Chroma-compatible types.

    Chroma allows: str, int, float, bool (not list, dict, None).
    """
    clean: Dict[str, Any] = {}
    for k, v in meta.items():
        if v is None:
            continue  # skip None values
        if isinstance(v, (str, int, float, bool)):
            clean[k] = v
        elif isinstance(v, list):
            clean[k] = ", ".join(str(x) for x in v)
        else:
            clean[k] = str(v)
    return clean


# ── Singleton ────────────────────────────────────────────

_store: Optional[ChromaStore] = None


def get_vector_store() -> ChromaStore:
    """Get or create the singleton ChromaStore."""
    global _store
    if _store is None:
        _store = ChromaStore()
    return _store
