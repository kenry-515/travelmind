"""
Comprehensive KB Quality Optimization (Local, No External API Needed)
====================================================================
1. Fix template description detection (refine patterns)
2. Expand short descriptions with structured info from existing fields
3. Optimize rating algorithm (reduce excessive low scores)
4. Add rich metadata signals for better POI quality
"""

import json
import re
import sys
from pathlib import Path
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INPUT_FILE = DATA_DIR / "attractions.json"


# ── Refined template patterns (only match actual AI-generated junk) ──
# Note: descriptions like "「故宫」位于北京，以历史著称。适合历史爱好者。" are GOOD
# We should only target the truly bad repetitive templates.
REAL_TEMPLATE_PATTERNS = [
    # Pure AI-generated repetitive templates
    "主要特点包括",
    "具有重要的",
    "特色包括",
    "见证了当地的历史变迁",
    "具有重要的历史文化价值",
    "适合深度游览和文化探索",
    "适合文化体验和祈福参拜",
    "主要特点包括",
    "以其",
    "而闻名",
]

# Category-specific rich description builders
CATEGORY_KEYWORDS = {
    "attractions": {
        "历史": ["历史", "遗址", "古迹", "文物", "古建筑"],
        "自然": ["自然", "山", "湖", "海", "瀑布", "峡谷", "森林", "草原"],
        "文化": ["文化", "博物馆", "艺术", "宗教", "寺庙", "教堂"],
        "休闲": ["公园", "广场", "步行街", "休闲"],
        "主题": ["乐园", "水族馆", "动物园", "植物园", "主题"],
    },
    "restaurants": {
        "中餐": ["中餐", "川菜", "粤菜", "鲁菜", "苏菜", "浙菜", "闽菜", "湘菜", "徽菜"],
        "小吃": ["小吃", "面", "饺", "包", "饼", "粥"],
        "火锅": ["火锅", "涮", "锅"],
        "烧烤": ["烧烤", "烤", "串"],
        "老字号": ["老字号", "百年", "传统"],
    },
    "hotels": {
        "五星": ["五星", "豪华", "国际"],
        "商务": ["商务", "会议"],
        "度假": ["度假", "休闲"],
        "经济": ["经济", "快捷", "连锁"],
    },
}


def detect_real_template(desc: str) -> bool:
    """Detect if a description is a real AI-generated template (low quality)."""
    if not desc or len(desc) < 10:
        return True

    # Count how many template markers are present
    marker_count = sum(1 for p in REAL_TEMPLATE_PATTERNS if p in desc)

    # If 2+ markers, it's definitely a template
    if marker_count >= 2:
        return True

    # Check for repetitive structure
    if desc.count("适合") >= 3:
        return True

    # Check for very generic descriptions without specific info
    if len(desc) < 60 and any(p in desc for p in REAL_TEMPLATE_PATTERNS):
        return True

    return False


def build_rich_description(attr: Dict[str, Any]) -> str:
    """Build a rich, informative description from POI metadata."""
    name = attr.get("name", "")
    city = attr.get("city", "")
    tags = attr.get("tags", []) or []
    address = attr.get("address", "")
    suitable = attr.get("suitable_for", "")
    best_time = attr.get("best_time", "")
    price_range = attr.get("price_range")
    price_level = attr.get("price_level", "")
    amap_type = attr.get("amap_type", "") or ""
    wiki_article = attr.get("wiki_article", "")
    category = _detect_category(attr)

    parts: List[str] = []

    # 1. Opening: location info
    if address and len(address) > 3 and address not in name:
        parts.append(f"{name}位于{city}{address}，")
    elif wiki_article:
        parts.append(f"{name}坐落于{city}，")
    else:
        parts.append(f"{name}位于{city}，")

    # 2. Category-specific description
    cat_desc = _category_description(attr, category, tags, amap_type)
    if cat_desc:
        parts.append(cat_desc)

    # 3. Tags-based features (limit to 3 most relevant)
    if tags:
        feature_tags = [t for t in tags if t not in ["全年", "春季", "夏季", "秋季", "冬季"]][:3]
        if feature_tags:
            parts.append(f"标签涵盖{('、'.join(feature_tags))}等特色。")

    # 4. Price info (only if verifiable)
    if price_range and isinstance(price_range, dict):
        min_p = price_range.get("min", 0)
        max_p = price_range.get("max", 0)
        if min_p == 0 and max_p == 0:
            parts.append("免费开放，")
        elif min_p == max_p:
            parts.append(f"门票{min_p}元，")
        else:
            parts.append(f"门票{min_p}-{max_p}元，")
    elif price_level == "免费":
        parts.append("免费开放，")

    # 5. Best time
    if best_time and best_time not in ["全年", "四季皆宜"]:
        parts.append(f"最佳游览时间{best_time}。")

    # 6. Suitable for
    if suitable and len(suitable) < 30:
        parts.append(f"适合{suitable}。")

    desc = "".join(parts)
    # Cleanup
    desc = re.sub(r"，+", "，", desc)
    desc = re.sub(r"，。", "。", desc)
    if desc.endswith("，"):
        desc = desc[:-1] + "。"
    if not desc.endswith("。") and not desc.endswith("！"):
        desc += "。"

    return desc


def _detect_category(attr: Dict[str, Any]) -> str:
    """Detect POI category from tags and amap_type."""
    tags_str = " ".join(attr.get("tags", []) or []).lower()
    amap_type = (attr.get("amap_type", "") or "").lower()

    if any(kw in tags_str for kw in ["酒店", "住宿", "hotel", "民宿", "客栈"]):
        return "hotels"
    if any(kw in amap_type for kw in ["酒店", "住宿", "民宿"]):
        return "hotels"
    if any(kw in tags_str for kw in ["餐厅", "美食", "小吃", "food", "火锅", "烧烤", "中餐"]):
        return "restaurants"
    if any(kw in amap_type for kw in ["餐饮", "餐厅", "美食"]):
        return "restaurants"
    return "attractions"


def _category_description(
    attr: Dict[str, Any],
    category: str,
    tags: List[str],
    amap_type: str,
) -> str:
    """Generate category-specific description."""
    name = attr.get("name", "")

    if category == "attractions":
        # Check for historical/natural/cultural keywords
        if any(t in tags for t in ["历史", "遗址", "古迹", "古建筑"]):
            return f"是一处具有历史文化价值的景点。"
        if any(t in tags for t in ["自然", "山", "湖", "海", "瀑布", "峡谷"]):
            return f"是一处自然景观秀美的景点。"
        if any(t in tags for t in ["博物馆", "艺术"]):
            return f"是一处文化内涵丰富的景点。"
        if any(t in tags for t in ["公园", "广场"]):
            return f"是一处休闲放松的好去处。"
        if any(t in tags for t in ["寺庙", "宗教"]):
            return f"是一处宗教文化圣地。"
        if any(t in tags for t in ["乐园", "主题"]):
            return f"是一处主题娱乐景点。"
        return "是当地知名景点。"

    elif category == "restaurants":
        if any(t in tags for t in ["老字号", "百年"]):
            return f"是当地历史悠久的老字号餐厅。"
        if any(t in tags for t in ["火锅"]):
            return f"是当地知名的火锅餐厅。"
        if any(t in tags for t in ["小吃"]):
            return f"是当地特色小吃名店。"
        if any(t in tags for t in ["川菜", "粤菜", "鲁菜"]):
            cuisine = next((t for t in tags if t in ["川菜", "粤菜", "鲁菜"]), "")
            return f"是当地知名的{cuisine}餐厅。"
        return "是当地知名餐厅。"

    elif category == "hotels":
        if any(t in tags for t in ["五星", "豪华"]):
            return f"是当地豪华五星级酒店。"
        if any(t in tags for t in ["商务"]):
            return f"是当地商务型酒店。"
        if any(t in tags for t in ["度假"]):
            return f"是当地度假型酒店。"
        if any(t in tags for t in ["经济", "连锁"]):
            return f"是当地经济型连锁酒店。"
        return "是当地知名酒店。"

    return ""


def optimize_descriptions(attractions: List[Dict[str, Any]]) -> Dict[str, int]:
    """Optimize descriptions: replace templates and expand short ones."""
    stats = {
        "templates_replaced": 0,
        "short_expanded": 0,
        "already_good": 0,
        "unchanged": 0,
    }

    for attr in attractions:
        desc = attr.get("description", "") or ""

        is_template = detect_real_template(desc)
        is_short = len(desc) < 60

        if is_template or is_short:
            new_desc = build_rich_description(attr)

            # Only update if new description is better
            if len(new_desc) > len(desc) and len(new_desc) >= 40:
                attr["description"] = new_desc
                attr["description_quality"] = "enriched"

                if is_template:
                    stats["templates_replaced"] += 1
                else:
                    stats["short_expanded"] += 1
            else:
                stats["unchanged"] += 1
        else:
            # Check if it's already a well-structured description
            if ("位于" in desc or "坐落" in desc) and len(desc) >= 60:
                attr["description_quality"] = "good"
                stats["already_good"] += 1
            else:
                stats["unchanged"] += 1

    return stats


def optimize_ratings(attractions: List[Dict[str, Any]]) -> Dict[str, int]:
    """Optimize rating algorithm to reduce excessive low scores.

    Current issue: 2614/3502 (74.6%) entries have rating < 3.0.
    This is because the rating is too punitive for entries lacking signals.

    New algorithm:
    - Base score: 2.5 (neutral)
    - +1.0 for verified price
    - +0.8 for wiki article
    - +0.6 for amap_id (verified on Amap)
    - +0.4 for long description (>=100 chars)
    - +0.3 for rich tags (>=5 tags)
    - +0.3 for coordinates
    - +0.2 for address
    - Cap at 5.0, floor at 1.5
    """
    stats = {"improved": 0, "unchanged": 0}

    for attr in attractions:
        score = 2.5  # Base score

        # Signal bonuses
        if attr.get("price_verifiable"):
            score += 1.0
        if attr.get("wiki_article"):
            score += 0.8
        if attr.get("amap_id"):
            score += 0.6

        desc = attr.get("description", "") or ""
        if len(desc) >= 100:
            score += 0.4
        elif len(desc) >= 60:
            score += 0.2

        tags = attr.get("tags", []) or []
        if len(tags) >= 5:
            score += 0.3
        elif len(tags) >= 3:
            score += 0.15

        if attr.get("lat") and attr.get("lon"):
            score += 0.3

        if attr.get("address"):
            score += 0.2

        # Popularity influence (capped)
        pop = attr.get("popularity_score", 3) or 3
        score += min(pop * 0.1, 0.5)

        # Clamp
        new_rating = round(min(max(score, 1.5), 5.0), 1)

        old_rating = attr.get("internal_rating", 0)
        if abs(new_rating - old_rating) >= 0.2:
            attr["internal_rating"] = new_rating

            # Update reliability based on new score
            dq = attr.get("data_quality", {}) or {}
            if new_rating >= 4.0:
                dq["reliability"] = "high"
            elif new_rating >= 3.0:
                dq["reliability"] = "medium"
            elif new_rating >= 2.0:
                dq["reliability"] = "low"
            else:
                dq["reliability"] = "poor"
            attr["data_quality"] = dq

            stats["improved"] += 1
        else:
            stats["unchanged"] += 1

    return stats


def enrich_metadata(attractions: List[Dict[str, Any]]) -> Dict[str, int]:
    """Enrich metadata for better POI quality signals."""
    stats = {"enriched": 0, "already_rich": 0}

    for attr in attractions:
        enriched = False

        # Add category field if missing
        if not attr.get("category"):
            attr["category"] = _detect_category(attr)
            enriched = True

        # Add normalized name if missing
        if not attr.get("name_normalized"):
            attr["name_normalized"] = attr.get("name", "")
            enriched = True

        # Ensure tags include category tag
        tags = attr.get("tags", []) or []
        category = attr.get("category", "attractions")
        category_tag_map = {
            "attractions": "景点",
            "restaurants": "美食",
            "hotels": "酒店",
        }
        cat_tag = category_tag_map.get(category, "景点")
        if cat_tag not in tags and not any(t in tags for t in ["美食", "酒店", "住宿", "餐厅"]):
            tags.append(cat_tag)
            attr["tags"] = tags
            enriched = True

        # Add best_time default if missing
        if not attr.get("best_time"):
            tags_str = " ".join(tags)
            if any(t in tags_str for t in ["春季", "秋季"]):
                attr["best_time"] = "春秋季"
            elif "夏季" in tags_str:
                attr["best_time"] = "夏季"
            elif "冬季" in tags_str:
                attr["best_time"] = "冬季"
            else:
                attr["best_time"] = "全年"
            enriched = True

        # Add suitable_for default if missing
        if not attr.get("suitable_for"):
            tags_str = " ".join(tags)
            if any(t in tags_str for t in ["亲子", "家庭"]):
                attr["suitable_for"] = "家庭游客"
            elif any(t in tags_str for t in ["历史", "文化"]):
                attr["suitable_for"] = "文化爱好者"
            elif any(t in tags_str for t in ["自然", "户外"]):
                attr["suitable_for"] = "自然爱好者"
            elif any(t in tags_str for t in ["美食"]):
                attr["suitable_for"] = "美食爱好者"
            else:
                attr["suitable_for"] = "一般游客"
            enriched = True

        if enriched:
            stats["enriched"] += 1
        else:
            stats["already_rich"] += 1

    return stats


def verify_data_integrity(attractions: List[Dict[str, Any]]) -> Dict[str, int]:
    """Verify data integrity and fix common issues."""
    stats = {"issues_found": 0, "fixed": 0, "ok": 0}

    for attr in attractions:
        issues = 0

        # Check required fields
        if not attr.get("name"):
            issues += 1
        if not attr.get("city"):
            issues += 1

        # Fix missing required fields
        if not attr.get("price_level"):
            attr["price_level"] = "付费"
            stats["fixed"] += 1
            issues += 1

        if not attr.get("price_verifiable") and attr.get("price_verifiable") is not False:
            attr["price_verifiable"] = False
            stats["fixed"] += 1
            issues += 1

        if not attr.get("data_quality"):
            attr["data_quality"] = {"reliability": "low"}
            stats["fixed"] += 1
            issues += 1

        if not attr.get("internal_rating"):
            attr["internal_rating"] = 2.5
            stats["fixed"] += 1
            issues += 1

        if issues == 0:
            stats["ok"] += 1
        else:
            stats["issues_found"] += 1

    return stats


def main():
    if not INPUT_FILE.exists():
        print(f"❌ File not found: {INPUT_FILE}")
        sys.exit(1)

    # Load data
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    original_total = len(data.get("attractions", []))
    print(f"📂 Loading {original_total} attractions from {INPUT_FILE}")

    attractions = data.get("attractions", [])

    # Step 1: Verify data integrity
    print("\n🔍 Step 1: Verifying data integrity...")
    integrity_stats = verify_data_integrity(attractions)
    print(f"  OK: {integrity_stats['ok']}, Issues: {integrity_stats['issues_found']}, Fixed: {integrity_stats['fixed']}")

    # Step 2: Enrich metadata
    print("\n🏷️  Step 2: Enriching metadata...")
    meta_stats = enrich_metadata(attractions)
    print(f"  Enriched: {meta_stats['enriched']}, Already rich: {meta_stats['already_rich']}")

    # Step 3: Optimize descriptions
    print("\n📝 Step 3: Optimizing descriptions...")
    desc_stats = optimize_descriptions(attractions)
    print(f"  Templates replaced: {desc_stats['templates_replaced']}")
    print(f"  Short expanded: {desc_stats['short_expanded']}")
    print(f"  Already good: {desc_stats['already_good']}")
    print(f"  Unchanged: {desc_stats['unchanged']}")

    # Step 4: Optimize ratings
    print("\n⭐ Step 4: Optimizing rating algorithm...")
    rating_stats = optimize_ratings(attractions)
    print(f"  Improved: {rating_stats['improved']}, Unchanged: {rating_stats['unchanged']}")

    # Step 5: Update data
    data["attractions"] = attractions
    data["total"] = len(attractions)
    data["enrich_date"] = datetime.now().strftime("%Y-%m-%d")
    data["quality_optimized"] = True
    data["optimization_summary"] = {
        "integrity_fixed": integrity_stats["fixed"],
        "metadata_enriched": meta_stats["enriched"],
        "templates_replaced": desc_stats["templates_replaced"],
        "short_expanded": desc_stats["short_expanded"],
        "ratings_improved": rating_stats["improved"],
    }

    # Save
    print(f"\n💾 Saving optimized data...")
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Final stats
    ratings = [a.get("internal_rating", 0) for a in attractions]
    desc_lengths = [len(a.get("description", "") or "") for a in attractions]
    templates_remaining = sum(
        1 for a in attractions
        if detect_real_template(a.get("description", "") or "")
    )

    print("\n" + "=" * 70)
    print("📊 Optimization Report")
    print("=" * 70)
    print(f"  Total entries: {len(attractions)}")
    print(f"\n  📝 Description Quality:")
    print(f"    Avg length: {round(sum(desc_lengths) / len(desc_lengths), 1)} chars")
    print(f"    Min/Max: {min(desc_lengths)}/{max(desc_lengths)}")
    print(f"    Short (<60): {sum(1 for l in desc_lengths if l < 60)}")
    print(f"    Templates remaining: {templates_remaining}")
    print(f"\n  ⭐ Rating Distribution:")
    print(f"    Avg rating: {round(sum(ratings) / len(ratings), 2)}")
    print(f"    High (>=4.0): {sum(1 for r in ratings if r >= 4.0)}")
    print(f"    Medium (3.0-4.0): {sum(1 for r in ratings if 3.0 <= r < 4.0)}")
    print(f"    Low (<3.0): {sum(1 for r in ratings if r < 3.0)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
