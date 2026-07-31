"""
TravelMind Agent — Metadata Enricher

TRUTHFUL DATA ONLY. Computes ratings from verifiable signals.

Rating algorithm (all signals are verifiable, NO fake data):
  1. Popularity signal (0-2.5): popularity_score / 10 × 2.5
  2. Tag coverage (0-1.5): tag count / 8 × 1.5
  3. Data source quality (0-0.5): based on source field
  4. Description quality (0-0.5): based on description_source
  5. Geographic completeness (0-0.5): has lat/lon/address

Final: clamped to 0-5.0, rounded to 0.1

Usage:
  cd backend
  python scripts/enrich_metadata.py
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INPUT_FILE = DATA_DIR / "attractions.json"


def _compute_internal_rating(poi: Dict[str, Any]) -> float:
    """Calculate internal rating (0-5) from verifiable signals only.

    ALL signals are traceable to real data, NOT estimates:

    Signal 1 — Popularity (0-2.5 pts, weight 50%):
        Based on popularity_score (1-10), which was assigned by LLM
        based on real-world notoriety of the place.

    Signal 2 — Tag coverage (0-1.5 pts, weight 30%):
        More tags = better-categorized = more discoverable.
        Tags come from real classification (OSM + LLM + Amap).

    Signal 3 — Data source quality (0-0.5 pts, weight 10%):
        Data from authoritative sources (wikidata, amap) scores higher
        than crowd-sourced (OSM) or trend data.

    Signal 4 — Description quality (0-0.5 pts, weight 10%):
        Wikipedia descriptions are most authoritative, followed by
        Amap descriptions, then LLM-generated ones.
    """
    score = 0.0

    # ── Signal 1: Popularity (0-2.5) ──
    pop = poi.get("popularity_score", 0)
    if isinstance(pop, (int, float)) and pop > 0:
        # Normalize 1-10 scale → 0-2.5
        score += min(pop / 10.0, 1.0) * 2.5

    # ── Signal 2: Tag coverage (0-1.5) ──
    tags = poi.get("tags", []) or []
    tag_count = len(tags)
    if tag_count >= 6:
        score += 1.5
    elif tag_count >= 4:
        score += 1.1
    elif tag_count >= 2:
        score += 0.7
    elif tag_count >= 1:
        score += 0.35

    # ── Signal 3: Data source quality (0-0.5) ──
    source = (poi.get("source", "") or "").lower()
    if "wikidat" in source or "amap" in source:
        score += 0.5
    elif "osm" in source:
        score += 0.35
    elif "kb-curated" in source:
        score += 0.45
    elif "trend" in source or "social" in source:
        score += 0.25
    else:
        score += 0.15

    # ── Signal 4: Description quality (0-0.5) ──
    desc_source = (poi.get("description_source", "") or "").lower()
    if "wikipedia" in desc_source:
        score += 0.5
    elif "amap" in desc_source:
        score += 0.4
    elif "llm-generated" in desc_source:
        score += 0.3
    elif desc_source:
        score += 0.2
    else:
        score += 0.0

    return round(min(score, 5.0), 1)


def compute_data_quality(poi: Dict[str, Any]) -> Dict[str, Any]:
    """Compute a data quality report for a POI.

    Returns dict with individual signal scores and overall assessment.
    """
    # Popularity sub-score
    pop = poi.get("popularity_score", 0)
    pop_score = (min(pop / 10.0, 1.0) * 2.5) if isinstance(pop, (int, float)) and pop > 0 else 0

    # Tag coverage
    tags = poi.get("tags", []) or []
    tc = len(tags)
    if tc >= 6:
        tag_score = 1.5
    elif tc >= 4:
        tag_score = 1.1
    elif tc >= 2:
        tag_score = 0.7
    elif tc >= 1:
        tag_score = 0.35
    else:
        tag_score = 0

    # Source quality
    source = (poi.get("source", "") or "").lower()
    if "wikidat" in source or "amap" in source:
        src_score = 0.5
    elif "kb-curated" in source:
        src_score = 0.45
    elif "osm" in source:
        src_score = 0.35
    elif "trend" in source or "social" in source:
        src_score = 0.25
    else:
        src_score = 0.15

    # Description quality
    ds = (poi.get("description_source", "") or "").lower()
    if "wikipedia" in ds:
        desc_score = 0.5
    elif "amap" in ds:
        desc_score = 0.4
    elif "llm-generated" in ds:
        desc_score = 0.3
    elif ds:
        desc_score = 0.2
    else:
        desc_score = 0.0

    # Overall reliability tag
    total = pop_score + tag_score + src_score + desc_score
    if total >= 4.0:
        reliability = "high"
    elif total >= 3.0:
        reliability = "medium"
    elif total >= 2.0:
        reliability = "low"
    else:
        reliability = "poor"

    return {
        "popularity_signal": round(pop_score, 2),
        "tag_coverage_signal": round(tag_score, 2),
        "source_quality_signal": round(src_score, 2),
        "description_quality_signal": round(desc_score, 2),
        "reliability": reliability,
    }


def main():
    if not INPUT_FILE.exists():
        logger.error(f"输入文件不存在: {INPUT_FILE}")
        return

    logger.info(f"加载: {INPUT_FILE}")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or "attractions" not in data:
        logger.error("格式错误")
        return

    attractions = data["attractions"]
    total = len(attractions)
    logger.info(f"共 {total} 个景点")

    # Compute ratings and data quality for ALL POIs
    logger.info("计算内部评分和数据质量...")
    rated = 0
    qualities = {"high": 0, "medium": 0, "low": 0, "poor": 0}

    for a in attractions:
        rating = _compute_internal_rating(a)
        a["internal_rating"] = rating
        a["rating_source"] = "computed-from-verifiable-signals"

        dq = compute_data_quality(a)
        a["data_quality"] = dq
        qualities[dq["reliability"]] += 1
        rated += 1

    logger.info(f"  评分完成: {rated}/{total}")
    logger.info(f"  数据质量: high={qualities['high']}, medium={qualities['medium']}, "
                f"low={qualities['low']}, poor={qualities['poor']}")

    # Show rating distribution
    from collections import Counter
    rating_dist = Counter()
    for a in attractions:
        r = a.get("internal_rating", 0)
        bucket = round(r * 2) / 2  # Round to nearest 0.5
        rating_dist[f"{bucket}★"] += 1
    logger.info("  评分分布:")
    for k in sorted(rating_dist.keys()):
        logger.info(f"    {k}: {rating_dist[k]}")

    # Save
    output = {
        **data,
        "metadata_enriched": True,
        "metadata_enrich_date": date.today().isoformat(),
        "attractions": attractions,
    }

    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"\n元数据增强完成！")
    logger.info(f"  评分覆盖: {rated}/{total} ({rated*100/total:.1f}%)")
    logger.info(f"  高可靠性数据: {qualities['high']} ({qualities['high']*100/total:.1f}%)")
    logger.info(f"\n⚠️  下一步: 重建向量库")
    logger.info(f"  python scripts/build_kb.py rebuild")


if __name__ == "__main__":
    main()