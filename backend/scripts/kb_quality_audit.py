"""
Knowledge Base Quality Audit Script
全面审计 attractions.json 的数据质量
"""
import json
import sys
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime


def audit_kb(data_path: str) -> dict:
    """Perform comprehensive KB quality audit."""
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("attractions", [])
    results = {
        "total": len(items),
        "source": data.get("source", "unknown"),
        "enrich_date": data.get("enrich_date", ""),
        "checks": {},
    }

    # ── 1. 城市分布 ──
    city_counts = Counter(a.get("city", "") for a in items)
    results["checks"]["city_coverage"] = {
        "total_cities": len(city_counts),
        "cities": sorted(city_counts.keys()),
        "top_cities": city_counts.most_common(10),
    }

    # ── 2. 类别分布（基于tags和type推断）──
    category_stats = defaultdict(int)
    for a in items:
        tags_str = " ".join(a.get("tags", []) or []).lower()
        amap_type = (a.get("amap_type", "") or "").lower()
        if any(kw in tags_str for kw in ["餐厅", "美食", "小吃", "food", "火锅", "烧烤"]):
            category_stats["restaurants"] += 1
        elif any(kw in tags_str for kw in ["酒店", "住宿", "hotel", "民宿", "客栈"]):
            category_stats["hotels"] += 1
        elif "酒店" in amap_type or "住宿" in amap_type or "民宿" in amap_type:
            category_stats["hotels"] += 1
        elif "餐饮" in amap_type or "餐厅" in amap_type or "美食" in amap_type:
            category_stats["restaurants"] += 1
        else:
            category_stats["attractions"] += 1
    results["checks"]["category_distribution"] = dict(category_stats)

    # ── 3. 字段完整性 ──
    fields = [
        "name", "city", "description", "tags", "lat", "lon",
        "price_level", "price_range", "price_source", "price_verifiable",
        "popularity_score", "internal_rating", "data_quality",
        "amap_id", "wiki_article", "address",
    ]
    field_coverage = {}
    for f in fields:
        non_empty = sum(1 for a in items if a.get(f) not in (None, "", [], {}))
        field_coverage[f] = {
            "count": non_empty,
            "pct": round(non_empty / len(items) * 100, 1),
        }
    results["checks"]["field_coverage"] = field_coverage

    # ── 4. 价格数据质量 ──
    price_verified = [a for a in items if a.get("price_verifiable")]
    price_range_valid = [
        a for a in items
        if a.get("price_range") not in (None, "", [])
    ]
    free_count = sum(
        1 for a in items
        if a.get("price_level") == "免费"
    )
    paid_verified = [
        a for a in price_verified
        if a.get("price_level") == "付费" and a.get("price_range")
    ]
    results["checks"]["price_quality"] = {
        "total_items": len(items),
        "price_verifiable_count": len(price_verified),
        "price_verifiable_pct": round(len(price_verified) / len(items) * 100, 1),
        "price_range_valid_count": len(price_range_valid),
        "price_range_valid_pct": round(len(price_range_valid) / len(items) * 100, 1),
        "free_count": free_count,
        "paid_verified_count": len(paid_verified),
        "sample_paid": [
            {"name": a["name"], "city": a["city"], "price_range": a["price_range"]}
            for a in paid_verified[:10]
        ],
    }

    # ── 5. 描述质量 ──
    desc_lengths = [len(a.get("description", "") or "") for a in items]
    desc_stats = {
        "avg_length": round(sum(desc_lengths) / len(desc_lengths), 1),
        "min_length": min(desc_lengths),
        "max_length": max(desc_lengths),
        "empty_desc": sum(1 for l in desc_lengths if l == 0),
        "short_desc_under_50": sum(1 for l in desc_lengths if l < 50),
    }

    # 检查模板化描述（包含"适合"、"主要特点"等AI生成痕迹）
    template_patterns = ["主要特点包括", "适合", "具有重要的", "适合深度"]
    template_count = 0
    for a in items:
        desc = a.get("description", "") or ""
        if any(p in desc for p in template_patterns):
            template_count += 1
    desc_stats["template_like_count"] = template_count
    desc_stats["template_like_pct"] = round(template_count / len(items) * 100, 1)
    results["checks"]["description_quality"] = desc_stats

    # ── 6. 标签质量 ──
    tag_counts = Counter()
    for a in items:
        for tag in a.get("tags", []) or []:
            tag_counts[tag] += 1
    results["checks"]["tag_quality"] = {
        "total_unique_tags": len(tag_counts),
        "top_tags": tag_counts.most_common(20),
        "items_without_tags": sum(1 for a in items if not a.get("tags")),
    }

    # ── 7. 数据质量评级分布 ──
    reliability_counts = Counter()
    for a in items:
        dq = a.get("data_quality", {}) or {}
        rel = dq.get("reliability", "unknown")
        reliability_counts[rel] += 1
    results["checks"]["reliability_distribution"] = dict(reliability_counts)

    # ── 8. 评分分布 ──
    rating_scores = [a.get("internal_rating", 0) for a in items if a.get("internal_rating")]
    results["checks"]["rating_distribution"] = {
        "count": len(rating_scores),
        "avg": round(sum(rating_scores) / len(rating_scores), 2) if rating_scores else 0,
        "min": min(rating_scores) if rating_scores else 0,
        "max": max(rating_scores) if rating_scores else 0,
        "below_3": sum(1 for r in rating_scores if r < 3.0),
        "above_4": sum(1 for r in rating_scores if r >= 4.0),
    }

    # ── 9. 过期/缺失检查 ──
    old_price = []
    for a in items:
        updated = a.get("price_updated_at", "")
        if updated and updated < "2026-07-01":
            old_price.append({"name": a["name"], "city": a["city"], "updated": updated})
    results["checks"]["freshness"] = {
        "old_price_entries": len(old_price),
        "sample_old": old_price[:5],
    }

    return results


def generate_reports(results: dict):
    """Generate human-readable reports."""
    checks = results["checks"]

    print("=" * 70)
    print("📊 知识库质量审计报告")
    print("=" * 70)
    print(f"  数据源: {results['source']}")
    print(f"  富集日期: {results['enrich_date']}")
    print(f"  总条目数: {results['total']}")
    print()

    # 城市
    cc = checks["city_coverage"]
    print("-" * 50)
    print(f"🏙️  城市覆盖: {cc['total_cities']} 个城市")
    print(f"    城市列表: {', '.join(cc['cities'])}")
    print(f"    TOP10城市:")
    for city, count in cc["top_cities"]:
        print(f"      {city}: {count} 条")
    print()

    # 类别
    cd = checks["category_distribution"]
    total = sum(cd.values())
    print("-" * 50)
    print(f"🍽️  类别分布 (总计 {total} 条):")
    for cat, count in sorted(cd.items(), key=lambda x: -x[1]):
        pct = round(count / total * 100, 1)
        bar = "█" * int(pct / 2)
        print(f"    {cat:15s}: {count:5d} ({pct:5.1f}%) {bar}")
    print()

    # 字段覆盖
    fc = checks["field_coverage"]
    print("-" * 50)
    print("📋 字段覆盖率:")
    for field, info in sorted(fc.items(), key=lambda x: -x[1]["pct"]):
        status = "✅" if info["pct"] >= 90 else "⚠️" if info["pct"] >= 50 else "❌"
        print(f"    {status} {field:25s}: {info['count']:5d}/{results['total']} ({info['pct']:5.1f}%)")
    print()

    # 价格
    pq = checks["price_quality"]
    print("-" * 50)
    print(f"💰 价格数据质量:")
    print(f"    价格可验证: {pq['price_verifiable_count']}/{pq['total_items']} ({pq['price_verifiable_pct']}%)")
    print(f"    有价格区间: {pq['price_range_valid_count']}/{pq['total_items']} ({pq['price_range_valid_pct']}%)")
    print(f"    免费景点: {pq['free_count']}")
    print(f"    付费已验证: {pq['paid_verified_count']}")
    if pq["sample_paid"]:
        print(f"    已验证价格示例:")
        for p in pq["sample_paid"][:5]:
            print(f"      {p['name']}({p['city']}): {p['price_range']}")
    print()

    # 描述
    dq = checks["description_quality"]
    print("-" * 50)
    print(f"📝 描述质量:")
    print(f"    平均长度: {dq['avg_length']} 字符")
    print(f"    最短/最长: {dq['min_length']}/{dq['max_length']}")
    print(f"    空描述: {dq['empty_desc']}")
    print(f"    过短(<50字): {dq['short_desc_under_50']}")
    print(f"    模板化描述: {dq['template_like_count']} ({dq['template_like_pct']}%)")
    print()

    # 标签
    tq = checks["tag_quality"]
    print("-" * 50)
    print(f"🏷️  标签质量:")
    print(f"    唯一标签数: {tq['total_unique_tags']}")
    print(f"    无标签条目: {tq['items_without_tags']}")
    print(f"    TOP标签:")
    for tag, count in tq["top_tags"][:10]:
        print(f"      {tag}: {count}")
    print()

    # 可靠性
    rel = checks["reliability_distribution"]
    print("-" * 50)
    print(f"⭐ 数据可靠性分布:")
    for level in ["high", "medium", "low", "poor", "unknown"]:
        if level in rel:
            print(f"    {level:10s}: {rel[level]}")
    print()

    # 评分
    rd = checks["rating_distribution"]
    print("-" * 50)
    print(f"📈 内部评分分布:")
    print(f"    已评分: {rd['count']}")
    print(f"    平均分: {rd['avg']}")
    print(f"    评分范围: {rd['min']} - {rd['max']}")
    print(f"    低分(<3.0): {rd['below_3']}")
    print(f"    高分(>=4.0): {rd['above_4']}")
    print()

    # 新鲜度
    fresh = checks["freshness"]
    print("-" * 50)
    print(f"🕐 数据新鲜度:")
    print(f"    过期价格条目: {fresh['old_price_entries']}")
    if fresh["sample_old"]:
        for o in fresh["sample_old"][:3]:
            print(f"      {o['name']}({o['city']}): {o['updated']}")
    print()

    # 总结与建议
    print("=" * 70)
    print("📋 优化建议:")
    print("=" * 70)

    suggestions = []
    if pq["price_verifiable_pct"] < 15:
        suggestions.append("🔴 价格覆盖率过低(<!15%)，建议接入高德/携程API补充真实价格")
    if pq["price_verifiable_count"] > 0 and pq["free_count"] / max(pq["price_verifiable_count"], 1) > 0.5:
        suggestions.append("🟡 免费景点占比较高，建议补充更多付费景点的真实价格")
    if cd.get("restaurants", 0) < 100:
        suggestions.append("🔴 餐饮数据不足(<100条)，建议补充餐饮POI到知识库")
    if cd.get("hotels", 0) < 50:
        suggestions.append("🟡 酒店数据不足(<50条)，建议补充酒店POI到知识库")
    if dq["template_like_pct"] > 20:
        suggestions.append("🟡 模板化描述占比高(>20%)，建议用真实描述替换")
    if dq["short_desc_under_50"] > 100:
        suggestions.append("🟡 大量描述过短(<50字)，建议扩充")
    if rd["below_3"] > rd["count"] * 0.3:
        suggestions.append("🟡 低分条目过多(>30%)，建议补充评分信号或移除质量差的条目")

    if suggestions:
        for s in suggestions:
            print(f"  {s}")
    else:
        print("  ✅ 数据质量良好，无需优化")

    print()
    return results


if __name__ == "__main__":
    data_path = Path(__file__).parent.parent / "data" / "attractions.json"
    if len(sys.argv) > 1:
        data_path = sys.argv[1]

    if not Path(data_path).exists():
        print(f"❌ File not found: {data_path}")
        sys.exit(1)

    print(f"📂 Analyzing: {data_path}")
    results = audit_kb(str(data_path))
    generate_reports(results)
