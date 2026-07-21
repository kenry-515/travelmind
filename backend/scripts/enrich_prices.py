#!/usr/bin/env python3
"""
TravelMind Agent — Price Enrichment Script

One-shot batch job that reads attractions.json and adds 3 price-related
fields to every attraction entry:

  - price_range:      {"min": int, "max": int}  — ticket price estimate range (CNY)
  - price_source:     str  — origin of the price data
  - price_updated_at: str  — ISO date when price was last updated

Rules (deterministic, no LLM):
  1. Map price_level → numeric range baseline
  2. Adjust for attraction type (temples/museums/parks often free or low-cost)
  3. Free attractions get {min: 0, max: 0} with source "free"
  4. Amap-verified attractions get source "高德POI"; AI-estimated get "估算（基于价格等级）"

Usage:
    cd backend
    python scripts/enrich_prices.py              # enrich in-place
    python scripts/enrich_prices.py --dry-run    # preview without writing
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Constants ────────────────────────────────────────────

# Baseline price range mapping from price_level → (min, max)
LEVEL_TO_RANGE: Dict[str, tuple] = {
    "经济": (0, 50),
    "适中": (20, 120),
    "舒适": (60, 200),
    "高端": (150, 500),
    "奢华": (200, 800),
}

# Attraction types that are commonly free or low-cost in China
FREE_OR_CHEAP_TYPES = {
    "寺庙", "寺庙道观", "博物馆", "公园", "广场", "纪念馆",
    "教堂", "清真寺", "古镇", "古村", "步行街", "街区",
}

# Types that suggest low entrance fees
LOW_COST_TYPES = {
    "风景名胜", "旅游景点", "遗址", "名人故居", "园林",
}


def classify_price_range(
    price_level: str,
    amap_type: str = "",
    tags: Optional[List[str]] = None,
) -> Dict[str, int]:
    """Map price_level + type hints to a numeric price range.

    Returns {"min": int, "max": int}. min=0, max=0 means free.
    """
    tags = tags or []
    baseline = LEVEL_TO_RANGE.get(price_level, (0, 50))

    # Check if the attraction type suggests free/low-cost
    type_lower = (amap_type or "").lower()
    amap_types = {t.strip() for t in (amap_type or "").split(";") if t.strip()}

    is_free_type = bool(amap_types & FREE_OR_CHEAP_TYPES)
    is_low_cost_type = bool(amap_types & LOW_COST_TYPES)

    # Tag-based hints
    has_free_tag = any(t in tags for t in ["免费", "开放", "街区"])

    if has_free_tag:
        return {"min": 0, "max": 0}

    if is_free_type and price_level == "经济":
        # Temples, museums, parks, etc. — often free or symbolic fee
        if "博物馆" in amap_types or "纪念馆" in amap_types:
            return {"min": 0, "max": 30}  # Many museums are free
        if "寺庙" in amap_types or "教堂" in amap_types or "清真寺" in amap_types:
            return {"min": 0, "max": 50}  # Small entrance fee or free
        if "公园" in amap_types or "广场" in amap_types:
            return {"min": 0, "max": 0}  # Parks & squares are generally free
        return {"min": 0, "max": 30}

    if is_low_cost_type and price_level == "经济":
        return {"min": 0, "max": 60}

    if is_free_type and price_level == "适中":
        return {"min": 20, "max": 80}

    return {"min": baseline[0], "max": baseline[1]}


def determine_price_source(
    amap_verified: bool,
    price_level: str,
    price_range: Dict[str, int],
) -> str:
    """Determine the human-readable source label for the price data."""
    if price_range["min"] == 0 and price_range["max"] == 0:
        return "免费"
    if amap_verified:
        return "高德POI"
    return "估算（基于价格等级）"


def enrich_attractions(
    data: Dict[str, Any],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Add price fields to all attractions in-place.

    Args:
        data: The full attractions.json content.
        dry_run: If True, return modified copy without writing to disk.

    Returns:
        The (possibly modified) data dict.
    """
    attractions: List[Dict[str, Any]] = data.get("attractions", [])
    today = date.today().isoformat()
    stats = {"total": len(attractions), "free": 0, "estimated": 0, "amap": 0}

    for attr in attractions:
        price_level = attr.get("price_level", "适中")
        amap_type = attr.get("amap_type", "")
        amap_verified = attr.get("amap_verified", False)
        tags = attr.get("tags", [])

        price_range = classify_price_range(price_level, amap_type, tags)
        price_source = determine_price_source(amap_verified, price_level, price_range)

        attr["price_range"] = price_range
        attr["price_source"] = price_source
        attr["price_updated_at"] = today

        # Stats
        if price_range["min"] == 0 and price_range["max"] == 0:
            stats["free"] += 1
        elif amap_verified:
            stats["amap"] += 1
        else:
            stats["estimated"] += 1

    data["price_enrich_date"] = today
    data["price_stats"] = stats

    if dry_run:
        print(f"[dry-run] Would enrich {stats['total']} attractions:")
        print(f"  Free: {stats['free']}")
        print(f"  Amap-sourced: {stats['amap']}")
        print(f"  Estimated: {stats['estimated']}")

    return data


# ── CLI ──────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Enrich attractions.json with price range data"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to disk",
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Path to attractions.json (default: backend/data/attractions.json)",
    )
    args = parser.parse_args()

    # Resolve path
    if args.input:
        data_path = Path(args.input)
    else:
        # Default: backend/data/attractions.json relative to the scripts/ dir
        script_dir = Path(__file__).resolve().parent
        data_path = script_dir.parent / "data" / "attractions.json"

    if not data_path.exists():
        print(f"ERROR: File not found: {data_path}", file=sys.stderr)
        sys.exit(1)

    # Load
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {data.get('total', '?')} attractions from {data_path}")

    # Enrich
    data = enrich_attractions(data, dry_run=args.dry_run)

    if args.dry_run:
        # Preview some samples (skip on Windows GBK terminals to avoid encode errors)
        try:
            print("\nSample entries:")
            for attr in attractions[:3]:
                pr = attr.get("price_range", {})
                print(
                    f"  {attr['name']:20s} | {attr.get('price_level', '?'):6s} | "
                    f"min={pr.get('min', '?')} max={pr.get('max', '?')} | "
                    f"{attr.get('price_source', '?')}"
                )
        except UnicodeEncodeError:
            print("(sample output skipped — terminal encoding)")
    else:
        print(f"  Free: {data['price_stats']['free']}")
        print(f"  Amap-sourced: {data['price_stats']['amap']}")
        print(f"  Estimated: {data['price_stats']['estimated']}")

    if args.dry_run:
        print("\n[dry-run] No changes written. Remove --dry-run to write.")
        return

    # Write back
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n[DONE] Enriched {data['price_stats']['total']} attractions -> {data_path}")


if __name__ == "__main__":
    main()
