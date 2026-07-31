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

    Truthful data: price_range can be null (not verified).
    """
    pr = attraction.get("price_range")
    has_price = pr is not None and isinstance(pr, dict)

    # Price: use 0 for min/max when not verified, but mark as unverifiable
    if has_price:
        pr_min = int(pr.get("min", 0))
        pr_max = int(pr.get("max", 0))
        price_verifiable = True
    else:
        pr_min = 0
        pr_max = 0
        price_verifiable = False

    return {
        "name": attraction.get("name", ""),
        "name_normalized": attraction.get("name_normalized", attraction.get("name", "")),
        "city": attraction.get("city", ""),
        "lat": attraction.get("lat"),
        "lon": attraction.get("lon"),
        "tags": ", ".join(attraction.get("tags", [])) if attraction.get("tags") else "",
        "price_level": attraction.get("price_level", ""),
        # Truthful price fields
        "price_range_min": pr_min,
        "price_range_max": pr_max,
        "price_verifiable": price_verifiable,
        "price_source": attraction.get("price_source", "") or "",
        "price_updated_at": attraction.get("price_updated_at", "") or "",
        "amap_id": attraction.get("amap_id", ""),
        "popularity_score": attraction.get("popularity_score", 0),
        "best_time": attraction.get("best_time", "") or "",
        "suitable_for": attraction.get("suitable_for", "") or "",
        "instance_of": attraction.get("instance_of", "") or "",
        "source": attraction.get("source", "") or "",
        "internal_rating": attraction.get("internal_rating", 0),
        "data_reliability": (
            attraction.get("data_quality", {}).get("reliability", "unknown")
            if isinstance(attraction.get("data_quality"), dict)
            else "unknown"
        ),
        "description_source": attraction.get("description_source", "") or "",
        "description_quality": attraction.get("description_quality", "") or "",
        "wiki_article": attraction.get("wiki_article", "") or "",
        "thumbnail_url": attraction.get("thumbnail_url", "") or "",
        # Truncated description for keyword matching in rerank
        "description": (attraction.get("description", "") or "")[:500],
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
    from app.rag.retriever import retrieve_by_preferences, retrieve

    async def _run_tests():
        # Test 1: City-based retrieval
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

        # Test 2: P0-1 fix — preference recall (keyword matching)
        logger.info("  --- P0-1 Preference Recall Tests ---")
        test_queries = [
            ({"destination": "成都", "tags": ["熊猫", "亲子"]}, "熊猫基地/亲子"),
            ({"destination": "北京", "tags": ["历史", "皇家"]}, "历史皇家"),
            ({"destination": "西安", "tags": ["古迹", "文物"]}, "古迹文物"),
            ({"destination": "重庆", "tags": ["夜景", "网红"]}, "夜景网红"),
        ]
        for profile, desc in test_queries:
            t0 = time.time()
            items = await retrieve(
                query=f"{profile['destination']}好玩的地方",
                user_profile=profile,
                top_k=5,
            )
            elapsed = time.time() - t0
            if items:
                top_names = [item.get("metadata", {}).get("name", "?") for item in items[:3]]
                scores = [item.get("_score_breakdown", {}) for item in items[:3]]
                keyword_hits = [s.get("keyword_hit", 0) for s in scores]
                logger.info(
                    f"  Pref '{desc}': {top_names} | "
                    f"keyword_hits={keyword_hits} ({elapsed:.3f}s)"
                )
            else:
                logger.warning(f"  Pref '{desc}': no results ({elapsed:.3f}s)")

    import asyncio
    asyncio.run(_run_tests())

    store.disconnect()
    logger.info("Done!")


if __name__ == "__main__":
    main()
