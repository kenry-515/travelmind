"""
TravelMind Agent — Embedding Provider

Abstract embedding interface with provider implementations.
Primary: TF-IDF (pure Python, no GPU needed — works everywhere).
Swap to BGE-M3 / DeepSeek embeddings when available.
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Optional

logger = logging.getLogger(__name__)


class BaseEmbeddingProvider(ABC):
    """Abstract embedding provider."""

    @abstractmethod
    def embed(self, texts: List[str], tags_list: Optional[List[List[str]]] = None) -> List[List[float]]:
        """Convert a list of texts to embeddings.

        Args:
            texts: Document texts to embed.
            tags_list: Optional tags per document (used by composite providers).
        """
        ...

    @abstractmethod
    def embed_query(self, text: str, tags: Optional[List[str]] = None) -> List[float]:
        """Convert a single query text to an embedding.

        Args:
            text: Query text.
            tags: Optional tags for the query (used by composite providers).
        """
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Embedding vector dimension."""
        ...


class TFIDFEmbeddingProvider(BaseEmbeddingProvider):
    """TF-IDF based embedding provider using scikit-learn.

    Fits on an initial corpus, then transforms any text into
    a sparse TF-IDF vector (converted to dense list).
    Works as a pure-Python fallback when GPU/torch is unavailable.
    """

    def __init__(self, max_features: int = 1024):
        self._max_features = max_features
        self._vectorizer = None
        self._fitted = False

    # -- sklearn lazy import (avoid import cost at module level) --

    @staticmethod
    def _get_vectorizer_class():
        from sklearn.feature_extraction.text import TfidfVectorizer
        return TfidfVectorizer

    # -- Public API --

    @property
    def dimension(self) -> int:
        return self._max_features

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def fit(self, corpus: List[str]) -> "TFIDFEmbeddingProvider":
        """Fit the TF-IDF vectorizer on a corpus of documents.

        Call this once before embed()/embed_query().
        """
        if not corpus:
            logger.warning("TFIDFEmbeddingProvider.fit() called with empty corpus")
            return self

        TfidfVectorizer = self._get_vectorizer_class()
        self._vectorizer = TfidfVectorizer(
            max_features=self._max_features,
            analyzer="char_wb",  # character n-grams — good for Chinese
            ngram_range=(2, 4),
            sublinear_tf=True,
        )
        self._vectorizer.fit(corpus)
        self._fitted = True
        logger.info(
            f"TF-IDF fitted on {len(corpus)} docs, "
            f"vocab size: {len(self._vectorizer.vocabulary_)}"
        )
        return self

    def save(self, path: str) -> None:
        """Save the fitted vectorizer to disk for fast cold-start.

        Pickles the sklearn TfidfVectorizer so subsequent restarts
        skip the corpus fitting step (saves ~1-2s).
        """
        if not self._fitted or self._vectorizer is None:
            raise RuntimeError("TFIDFEmbeddingProvider not fitted. Cannot save.")
        import pickle
        with open(path, "wb") as f:
            pickle.dump({
                "vectorizer": self._vectorizer,
                "max_features": self._max_features,
            }, f)
        logger.info(f"TF-IDF vectorizer saved to {path}")

    def load(self, path: str) -> bool:
        """Load a pre-fitted vectorizer from disk.

        Returns True on success, False if file doesn't exist or is invalid.
        """
        import os
        if not os.path.exists(path):
            return False
        try:
            import pickle
            with open(path, "rb") as f:
                data = pickle.load(f)
            self._vectorizer = data["vectorizer"]
            self._max_features = data.get("max_features", self._max_features)
            self._fitted = True
            logger.info(
                f"TF-IDF loaded from {path}, "
                f"vocab size: {len(self._vectorizer.vocabulary_)}"
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to load TF-IDF from {path}: {e}")
            self._vectorizer = None
            self._fitted = False
            return False

    def embed(
        self, texts: List[str], tags_list: Optional[List[List[str]]] = None
    ) -> List[List[float]]:
        """Embed a list of texts. Returns dense vectors."""
        if not self._fitted or self._vectorizer is None:
            raise RuntimeError("TFIDFEmbeddingProvider not fitted. Call fit() first.")
        matrix = self._vectorizer.transform(texts)
        # Convert sparse rows to dense lists
        return [row.toarray()[0].tolist() for row in matrix]

    def embed_query(self, text: str, tags: Optional[List[str]] = None) -> List[float]:
        """Embed a single query text."""
        return self.embed([text])[0]


class CompositeEmbeddingProvider(BaseEmbeddingProvider):
    """Combines TF-IDF text features with structured tag features.

    Produces a concatenated vector:
      [tfidf_vector (max_features dims)] + [tag_one_hot (num_tags dims)]

    where tag_one_hot is a binary vector indicating which tags
    from the global taxonomy are present.
    """

    def __init__(
        self,
        tfidf: TFIDFEmbeddingProvider,
        tag_vocabulary: List[str],
        tfidf_weight: float = 0.6,
    ):
        self._tfidf = tfidf
        self._tag_vocab = tag_vocabulary
        self._tag_index = {tag: i for i, tag in enumerate(tag_vocabulary)}
        self._tfidf_weight = tfidf_weight

    @property
    def dimension(self) -> int:
        return self._tfidf.dimension + len(self._tag_vocab)

    def _tags_to_vector(self, tags: List[str]) -> List[float]:
        """Convert a list of tags to a binary vector."""
        vec = [0.0] * len(self._tag_vocab)
        for tag in tags:
            idx = self._tag_index.get(tag)
            if idx is not None:
                vec[idx] = 1.0
        return vec

    def embed(
        self,
        texts: List[str],
        tags_list: Optional[List[List[str]]] = None,
    ) -> List[List[float]]:
        """Embed texts with optional tag features."""
        tfidf_vecs = self._tfidf.embed(texts)
        tags_list = tags_list or [[] for _ in texts]

        combined = []
        for tfidf_vec, tags in zip(tfidf_vecs, tags_list):
            tag_vec = self._tags_to_vector(tags)
            # Weighted concatenation
            weighted_tfidf = [v * self._tfidf_weight for v in tfidf_vec]
            weighted_tags = [v * (1 - self._tfidf_weight) for v in tag_vec]
            combined.append(weighted_tfidf + weighted_tags)
        return combined

    def embed_query(
        self,
        text: str,
        tags: Optional[List[str]] = None,
    ) -> List[float]:
        """Embed a query with optional tags."""
        return self.embed([text], [tags or []])[0]


# ── Factory ──────────────────────────────────────────────

_embedding_provider: Optional[BaseEmbeddingProvider] = None


def get_embedding_provider() -> BaseEmbeddingProvider:
    """Get the singleton embedding provider."""
    global _embedding_provider
    if _embedding_provider is None:
        raise RuntimeError(
            "Embedding provider not initialized. "
            "Call init_embedding_provider() first."
        )
    return _embedding_provider


def init_embedding_provider(
    corpus: List[str],
    tags_list: Optional[List[List[str]]] = None,
    max_features: int = 1024,
    tag_vocabulary: Optional[List[str]] = None,
) -> BaseEmbeddingProvider:
    """Initialize the embedding provider.

    Currently uses TF-IDF as the primary provider (no GPU required).
    When BGE-M3 / DeepSeek embeddings become available, swap here.

    Args:
        corpus: List of document texts to fit the TF-IDF vectorizer.
        tags_list: Optional list of tag lists per document (for composite provider).
        max_features: Max TF-IDF features.
        tag_vocabulary: Global tag vocabulary (for composite provider).

    Returns:
        The initialized embedding provider.
    """
    global _embedding_provider

    tfidf = TFIDFEmbeddingProvider(max_features=max_features)
    tfidf.fit(corpus)

    if tag_vocabulary and tags_list:
        _embedding_provider = CompositeEmbeddingProvider(
            tfidf=tfidf,
            tag_vocabulary=tag_vocabulary,
        )
    else:
        _embedding_provider = tfidf

    logger.info(
        f"Embedding provider initialized: {type(_embedding_provider).__name__} "
        f"(dim={_embedding_provider.dimension})"
    )
    return _embedding_provider
