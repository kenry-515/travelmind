"""
TravelMind Agent — Knowledge Base Builder

Builds the ChromaDB knowledge base from the enriched attractions data:

  1. Load attractions.json (or latest available enriched data)
  2. Initialize embedding provider (fit TF-IDF on the corpus)
  3. Split into document chunks (name + description + tags)
  4. Generate pre-computed embeddings
  5. Ingest into ChromaDB vector store

Input:  data/attractions.json → data/amap_enriched.json → data/wikipedia_enriched.json
Output: chroma_data/ (Chroma persistent store)

Usage:
  cd backend
  python scripts/build_knowledge_base.py
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Ensure the backend package is importable when run as a standalone script
_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPT_DIR.parent
if str(_BACKEND_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_BACKEND_DIR))

from app.rag import _build_document, _load_tag_vocabulary

# Input precedence: newest → oldest
INPUT_CANDIDATES = [
    DATA_DIR / "attractions.json",
    DATA_DIR / "amap_enriched.json",
    DATA_DIR / "wikipedia_enriched.json",
]


def _find_input() -> Optional[Path]:
    """Find the best available input file."""
    for path in INPUT_CANDIDATES:
        if path.exists():
            return path
    return None


def _load_attractions(path: Path) -> List[Dict[str, Any]]:
    """Load attractions from a JSON data file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "attractions" not in data:
        raise ValueError(f"Invalid format in {path}: expected dict with 'attractions' key")
    return data["attractions"]


def _build_metadata(attraction: Dict[str, Any]) -> Dict[str, Any]:
    """Build Chroma-compatible metadata from an attraction.

    Chroma metadata only supports str, int, float, bool — nested objects
    like price_range are flattened into price_range_min / price_range_max.
    """
    pr = attraction.get("price_range") or {}
    return {
        "name": attraction.get("name", ""),
        "city": attraction.get("city", ""),
        "lat": attraction.get("lat"),
        "lon": attraction.get("lon"),
        "tags": ", ".join(attraction.get("tags", [])) if attraction.get("tags") else "",
        "price_level": attraction.get("price_level", "适中"),
        # Phase 7: Flat price fields for Chroma compatibility
        "price_range_min": int(pr.get("min", 0)) if isinstance(pr, dict) else 0,
        "price_range_max": int(pr.get("max", 0)) if isinstance(pr, dict) else 0,
        "price_source": attraction.get("price_source", ""),
        "price_updated_at": attraction.get("price_updated_at", ""),
        "amap_id": attraction.get("amap_id", ""),
        "popularity_score": attraction.get("popularity_score", 5),
        "best_time": attraction.get("best_time", "全年"),
        "suitable_for": attraction.get("suitable_for", ""),
        "instance_of": attraction.get("instance_of", ""),
        "source": attraction.get("source", ""),
    }


def main():
    """Main entry point."""
    # 1. Find input
    input_path = _find_input()
    if not input_path:
        logger.error(
            "No input data found. Run at least enrich_wikipedia.py first.\n"
            f"Looked for: {', '.join(str(p) for p in INPUT_CANDIDATES)}"
        )
        return

    logger.info(f"Loading attractions from {input_path.name}...")
    attractions = _load_attractions(input_path)
    total = len(attractions)
    logger.info(f"Loaded {total} attractions")

    # Filter out attractions without a name or city
    valid = [a for a in attractions if a.get("name") and a.get("city")]
    if len(valid) < total:
        logger.warning(f"Filtered {total - len(valid)} attractions with missing name/city")
        total = len(valid)

    # 2. Build documents
    logger.info("Building document chunks...")
    documents = [_build_document(a) for a in valid]
    tags_lists = [a.get("tags", []) or [] for a in valid]
    metadatas = [_build_metadata(a) for a in valid]
    ids = [a.get("wikidata_id") or a.get("amap_id") or str(i)
           for i, a in enumerate(valid)]

    # 3. Initialize embedding provider
    logger.info("Initializing embedding provider (TF-IDF)...")
    tag_vocab = _load_tag_vocabulary()
    logger.info(f"Tag vocabulary: {len(tag_vocab)} tags")

    from app.rag.embedding import init_embedding_provider
    embedding_provider = init_embedding_provider(
        corpus=documents,
        tags_list=tags_lists,
        tag_vocabulary=tag_vocab,
        max_features=1024,
    )
    logger.info(f"Embedding provider: dim={embedding_provider.dimension}")

    # 4. Generate embeddings
    logger.info(f"Generating embeddings for {total} documents...")
    embeddings = embedding_provider.embed(documents, tags_list=tags_lists)
    logger.info(f"Generated {len(embeddings)} embeddings")

    # 5. Ingest into Chroma
    logger.info("Ingesting into ChromaDB...")
    from app.rag.vector_store import ChromaStore

    store = ChromaStore()
    store.connect()

    # Clear existing data for fresh rebuild
    if store.count() > 0:
        logger.info(f"Clearing existing {store.count()} documents...")
        store.delete_collection()
        store.connect()  # re-create collection

    store.add_documents(
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids,
        batch_size=150,
    )

    # 6. Verify
    count = store.count()
    logger.info(f"✓ ChromaDB knowledge base built: {count} documents")

    # Quick sanity check — search for something
    from app.rag.retriever import retrieve_by_preferences

    async def _run_tests():
        test_cities = ["重庆", "北京", "成都"]
        for city in test_cities:
            t0 = time.time()
            items = await retrieve_by_preferences(city=city, top_k=3)
            elapsed = time.time() - t0
            if items:
                top_names = [item.get("metadata", {}).get("name", "?") for item in items[:3]]
                logger.info(f"  Test '{city}': {top_names} ({elapsed:.3f}s)")
            else:
                logger.warning(f"  Test '{city}': no results ({elapsed:.3f}s)")

    import asyncio
    asyncio.run(_run_tests())

    store.disconnect()
    logger.info("Done!")


if __name__ == "__main__":
    main()
