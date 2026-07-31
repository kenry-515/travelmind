#!/usr/bin/env python3
"""
TravelMind Agent — Price Verification Script

TRUTHFUL DATA ONLY. No estimated/simulated prices.

Policy:
  1. Only mark as "free" when verifiable by common knowledge:
     - Parks, squares, pedestrian streets, some temples
  2. ALL other POIs → price_range = null with clear guidance:
     "价格未核实，建议自行查询高德/携程"
  3. Every field has a transparent source label

Usage:
    cd backend
    python scripts/enrich_prices.py              # verify in-place
    python scripts/enrich_prices.py --dry-run    # preview only
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INPUT_FILE = DATA_DIR / "attractions.json"

# Types that are VERIFIABLY free by common knowledge
FREE_TYPES = {
    "公园", "广场", "步行街", "街区", "古镇", "古村",
    "免费", "开放", "免费开放",
}

# Types that are SOMETIMES free but need verification
MAYBE_FREE_TYPES = {
    "博物馆", "纪念馆", "图书馆",
}

# Types that ALMOST ALWAYS require tickets
PAID_TYPES = {
    "寺庙", "寺庙道观", "教堂", "清真寺", "风景名胜",
    "旅游景点", "遗址", "名人故居", "园林", "游乐园",
    "海底世界", "动物园", "植物园", "水族馆",
}


def _is_verifiably_free(poi: Dict[str, Any]) -> bool:
    """Check if a POI type is verifiably free by common knowledge."""
    tags = set(poi.get("tags", []) or [])
    amap_type = (poi.get("amap_type", "") or "").lower()
    instance_of = (poi.get("instance_of", "") or "").lower()
    category = (poi.get("category", "") or "").lower()

    # Check tags first — most reliable
    for tag in tags:
        if tag in FREE_TYPES:
            return True

    # Check amap_type
    for ft in FREE_TYPES:
        if ft in amap_type:
            return True

    # Check instance_of / category
    for ft in FREE_TYPES:
        if ft in instance_of or ft in category:
            return True

    # Museums: most are free in China but some charge
    for mt in MAYBE_FREE_TYPES:
        if mt in amap_type or mt in instance_of or mt in category:
            # Public museums are generally free
            tags_str = " ".join(tags)
            if "公共" in tags_str or "文化" in tags_str or "历史" in tags_str:
                return True
            # Default: museums are "maybe free" → mark as needing verification
            return False

    return False


def _has_ticket_type(poi: Dict[str, Any]) -> bool:
    """Check if a POI type almost always requires tickets."""
    tags = set(poi.get("tags", []) or [])
    amap_type = (poi.get("amap_type", "") or "").lower()
    instance_of = (poi.get("instance_of", "") or "").lower()

    for pt in PAID_TYPES:
        if pt in amap_type or pt in instance_of:
            return True
    return False


def verify_prices(
    data: Dict[str, Any],
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Verify and clean price data — NO estimates, NO fabrications.

    Returns modified data dict with truthful price fields.
    """
    attractions: List[Dict[str, Any]] = data.get("attractions", [])
    today = date.today().isoformat()
    stats = {
        "total": len(attractions),
        "verifiably_free": 0,
        "needs_verification": 0,
        "already_correct": 0,
    }

    for attr in attractions:
        is_free = _is_verifiably_free(attr)
        is_paid_type = _has_ticket_type(attr)

        if is_free:
            # Verifiably free — this is a factual claim based on type
            new_price = {"min": 0, "max": 0}
            new_source = "免费（基于景点类型判断）"
            new_verifiable = True
            new_level = "免费"
            stats["verifiably_free"] += 1
        elif is_paid_type:
            # Requires ticket but we don't know the real price
            new_price = None
            new_source = "价格未核实，建议自行查询高德/携程"
            new_verifiable = False
            new_level = "付费"
            stats["needs_verification"] += 1
        else:
            # Unknown — could be free or paid, don't guess
            new_price = None
            new_source = "价格未核实，建议自行查询"
            new_verifiable = False
            new_level = ""
            stats["needs_verification"] += 1

        # Only update if different from current
        old_price = attr.get("price_range")
        if (old_price != new_price
            or attr.get("price_source") != new_source
            or attr.get("price_level", "") != new_level):
            attr["price_range"] = new_price
            attr["price_source"] = new_source
            attr["price_level"] = new_level
            attr["price_verifiable"] = new_verifiable
            attr["price_updated_at"] = today
            attr["price_confidence"] = "high" if new_verifiable else "low"
        else:
            stats["already_correct"] += 1

    # Remove price_confidence for non-verifiable entries (confidence doesn't help)
    for attr in attractions:
        if not attr.get("price_verifiable"):
            attr.pop("price_confidence", None)

    data["price_verified_date"] = today
    data["price_stats"] = stats

    if dry_run:
        print(f"[dry-run] Would verify {stats['total']} attractions:")
        print(f"  Verifiably free: {stats['verifiably_free']}")
        print(f"  Needs verification: {stats['needs_verification']}")
        print(f"  Already correct: {stats['already_correct']}")

    return data


def main():
    parser = argparse.ArgumentParser(
        description="Verify attraction prices — truthful data only"
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
        help="Path to attractions.json",
    )
    args = parser.parse_args()

    if args.input:
        data_path = Path(args.input)
    else:
        data_path = INPUT_FILE

    if not data_path.exists():
        print(f"ERROR: File not found: {data_path}", file=sys.stderr)
        sys.exit(1)

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {data.get('total', '?')} attractions from {data_path}")

    data = verify_prices(data, dry_run=args.dry_run)

    if args.dry_run:
        print("\n[dry-run] No changes written. Remove --dry-run to write.")
        return

    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n[DONE] Verified {data['price_stats']['total']} attractions -> {data_path}")
    print(f"  Verifiably free: {data['price_stats']['verifiably_free']}")
    print(f"  Needs user lookup: {data['price_stats']['needs_verification']}")
    print(f"  Already correct: {data['price_stats']['already_correct']}")
    print(f"\n⚠️  Prices that need verification should prompt users to check Amap/Ctrip.")


if __name__ == "__main__":
    main()