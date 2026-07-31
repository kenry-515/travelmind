"""
P0-6: Clean remaining suspicious POIs and cross-city duplicates.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INPUT_FILE = DATA_DIR / "attractions.json"

# Suspicious POIs to remove (dishes, generic names, non-POI entries)
SUSPICIOUS_NAMES = {
    "焖子": "郑州",  # Not a POI
    "仿膳饭庄": "北海",  # Not a standalone POI, part of Beihai Park
    "木府": "昆明",  # This is in 丽江, not 昆明
    "校史馆": "西安",  # Generic institutional building
    "校史馆": "长沙",
    "校史馆": "成都",
    "李先生": "北京",  # Chain store, not landmark
    "李先生": "天津",
    "李先生": "哈尔滨",
}

# Cross-city duplicates to keep only the first occurrence
# These are chain stores that create noise
CHAIN_NAMES = {"百盛百货", "新世界百货", "锦江之星", "李先生", "7天连锁酒店"}


def main():
    print(f"📂 Loading {INPUT_FILE}")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    attractions = data.get("attractions", [])
    original = len(attractions)

    # Step 1: Remove suspicious POIs
    removed = []
    clean = []
    for poi in attractions:
        name = poi.get("name", "")
        city = poi.get("city", "")
        key = (name, city)

        if key in SUSPICIOUS_NAMES:
            removed.append(poi)
            continue

        # Remove chain stores that appear in 3+ cities
        if name in CHAIN_NAMES:
            # Keep only first city occurrence
            clean.append(poi)
            continue

        clean.append(poi)

    print(f"\n🗑️  Removed {len(removed)} suspicious POIs:")
    for p in removed:
        print(f"  ❌ {p.get('name')} ({p.get('city')}) [{p.get('category','')}]")

    # Step 2: Remove chain store duplicates (keep only first city)
    seen_chains = {}
    final_list = []
    chain_removed = []
    for poi in clean:
        name = poi.get("name", "")
        city = poi.get("city", "")

        if name in CHAIN_NAMES:
            if name not in seen_chains:
                seen_chains[name] = city
                final_list.append(poi)
            else:
                chain_removed.append(poi)
                continue
        else:
            final_list.append(poi)

    print(f"\n🗑️  Removed {len(chain_removed)} chain store duplicates:")
    for p in chain_removed:
        print(f"  ❌ {p.get('name')} ({p.get('city')})")

    data["attractions"] = final_list
    data["total"] = len(final_list)

    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Saved. {original} → {len(final_list)} entries ({original - len(final_list)} removed)")


if __name__ == "__main__":
    main()
