"""
TravelMind Agent — Full Multi-Source Data Pipeline

Runs the complete data enrichment pipeline in order:
  1. Fetch enhanced Wikidata (prices + quality signals)
  2. Merge into attractions.json
  3. Run real price enrichment (Amap/Ctrip/Wikidata/Wikipedia)
  4. Update price_level and data_quality
  5. Rebuild knowledge base
  6. Generate data quality report

Usage:
  cd backend
  python scripts/run_full_pipeline.py [--skip-wikidata] [--skip-prices] [--skip-kb]
"""

import asyncio
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ATTRACTIONS_FILE = DATA_DIR / "attractions.json"
WIKIDATA_FILE = DATA_DIR / "wikidata_attractions.json"
WIKIDATA_ENHANCED_FILE = DATA_DIR / "wikidata_enhanced.json"


def load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_price_from_text(text: str) -> Optional[Dict[str, int]]:
    """Parse a price string like '60', '60元', 'free', etc."""
    if not text:
        return None
    text = str(text).strip()

    # Free indicators
    if text in ("免费", "free", "Free", "FREE", "免费开放", "免票"):
        return {"min": 0, "max": 0}

    # Try to extract number
    m = re.search(r"(\d+)", text)
    if m:
        price = int(m.group(1))
        if 0 <= price <= 99999:
            return {"min": price, "max": price}

    return None


def merge_wikidata_prices(wd_path: Path, attr_path: Path) -> Dict[str, Any]:
    """Merge enhanced Wikidata price data into attractions.

    Cross-reference by wikidata_id and name+city.
    Only update if current price is null and Wikidata has a verified price.
    """
    if not wd_path.exists():
        logger.warning(f"Wikidata file not found: {wd_path}")
        return load_json(attr_path)

    wd_data = load_json(wd_path)
    if isinstance(wd_data, dict):
        wd_list = wd_data.get("attractions", [])
    else:
        wd_list = wd_data

    logger.info(f"Merging {len(wd_list)} Wikidata entries into attractions...")

    # Build lookup by wikidata_id
    wd_by_id = {}
    for w in wd_list:
        wid = w.get("wikidata_id", "")
        if wid:
            wd_by_id[wid] = w

    # Also build lookup by name+city
    wd_by_name = {}
    for w in wd_list:
        key = (w.get("name", ""), w.get("city", ""))
        if key[0]:
            wd_by_name[key] = w

    data = load_json(attr_path)
    updated = 0
    price_found = 0

    for attr in data.get("attractions", []):
        updated += 1
        wid = attr.get("wikidata_id", "")
        name = attr.get("name", "")
        city = attr.get("city", "")

        # Find Wikidata match
        wd_match = None
        if wid and wid in wd_by_id:
            wd_match = wd_by_id[wid]
        elif name and city:
            wd_match = wd_by_name.get((name, city))

        if not wd_match:
            continue

        # Update price if currently null
        if attr.get("price_range") is None:
            fee = wd_match.get("fee", "")
            if fee:
                price = parse_price_from_text(str(fee))
                if price:
                    attr["price_range"] = price
                    attr["price_source"] = f"Wikidata(verified): {fee}"
                    attr["price_verifiable"] = True
                    attr["price_updated_at"] = time.strftime("%Y-%m-%d")
                    price_found += 1

        # Update English name if missing
        if not attr.get("name_en") and wd_match.get("name_en"):
            attr["name_en"] = wd_match["name_en"]

        # Update inception date if available
        if wd_match.get("inception") and not attr.get("inception"):
            attr["inception"] = wd_match["inception"]

    logger.info(f"Wikidata merge: {price_found} new prices found")
    return data


def compute_final_price_level(attr: Dict[str, Any]) -> str:
    """Compute price_level based on verified price_range."""
    pr = attr.get("price_range")
    if not pr:
        # Check amap_type hints
        amap_type = attr.get("amap_type", "") or ""
        if any(t in amap_type for t in ["风景名胜", "寺庙", "主题乐园", "海洋馆"]):
            return "付费"
        return ""

    if isinstance(pr, dict):
        min_p = pr.get("min", 0)
        max_p = pr.get("max", 0)
        if max_p == 0:
            return "免费"
        avg = (min_p + max_p) / 2
        if avg <= 50:
            return "经济"
        elif avg <= 200:
            return "适中"
        else:
            return "高端"
    return ""


def update_price_levels(data: Dict[str, Any]) -> None:
    """Update price_level for all attractions based on verified prices."""
    for attr in data.get("attractions", []):
        new_level = compute_final_price_level(attr)
        if new_level:
            attr["price_level"] = new_level


def generate_quality_report(data: Dict[str, Any]) -> str:
    """Generate a data quality report."""
    attractions = data.get("attractions", [])
    total = len(attractions)

    lines = []
    lines.append("=" * 60)
    lines.append("TravelMind Agent — 多源数据质量报告")
    lines.append("=" * 60)
    lines.append(f"总景点数: {total}")
    lines.append("")

    # Price coverage
    verified = [a for a in attractions if a.get("price_verifiable")]
    free = [a for a in verified if a.get("price_range", {}).get("max", 0) == 0]
    paid_verified = [a for a in verified if a.get("price_range", {}).get("max", 0) > 0]

    lines.append("【价格数据】")
    lines.append(f"  ✅ 已核实: {len(verified)} ({len(verified)*100/total:.1f}%)")
    lines.append(f"     - 免费: {len(free)}")
    lines.append(f"     - 有票价: {len(paid_verified)}")
    lines.append(f"  ⚠️  待核实: {total - len(verified)} ({(total-len(verified))*100/total:.1f}%)")
    lines.append("")

    # Data sources
    sources = {}
    for a in attractions:
        src = a.get("price_source", "")
        if src and "Wikidata" in src:
            sources["Wikidata"] = sources.get("Wikidata", 0) + 1
        elif src and "Wikipedia" in src:
            sources["Wikipedia"] = sources.get("Wikipedia", 0) + 1
        elif src and "高德" in src:
            sources["高德"] = sources.get("高德", 0) + 1
        elif src and "携程" in src:
            sources["携程"] = sources.get("携程", 0) + 1
        elif src and "飞猪" in src:
            sources["飞猪"] = sources.get("飞猪", 0) + 1
        elif src and "描述" in src:
            sources["描述提取"] = sources.get("描述提取", 0) + 1
        elif src and "类型" in src:
            sources["类型推断"] = sources.get("类型推断", 0) + 1

    if sources:
        lines.append("【价格来源分布】")
        for src, count in sorted(sources.items(), key=lambda x: -x[1]):
            lines.append(f"  {src}: {count}")
        lines.append("")

    # Description quality
    desc_sources = {}
    for a in attractions:
        ds = a.get("description_source", "") or "unknown"
        desc_sources[ds] = desc_sources.get(ds, 0) + 1

    lines.append("【描述来源分布】")
    for src, count in sorted(desc_sources.items(), key=lambda x: -x[1]):
        lines.append(f"  {src}: {count}")
    lines.append("")

    # Data quality
    qualities = {"high": 0, "medium": 0, "low": 0, "poor": 0}
    for a in attractions:
        dq = a.get("data_quality", {})
        if isinstance(dq, dict):
            r = dq.get("reliability", "low")
            qualities[r] = qualities.get(r, 0) + 1

    lines.append("【数据可靠性】")
    icons = {"high": "🟢", "medium": "🔵", "low": "🟡", "poor": "🔴"}
    for level in ["high", "medium", "low", "poor"]:
        count = qualities.get(level, 0)
        pct = count * 100 / total
        lines.append(f"  {icons.get(level, '⚪')} {level:8s}: {count:5d} ({pct:5.1f}%)")

    lines.append("")
    lines.append("下一步建议:")
    lines.append("  1. 在 backend/.env 中配置 AMAP_API_KEY 启用高德 POI Detail")
    lines.append("  2. 手动查询待核实景点的实时票价 (携程/飞猪/高德)")
    lines.append("  3. 补充更多高质量景点描述 (Wikipedia/专业旅游资料)")

    report = "\n".join(lines)
    print(report)
    return report


async def main():
    skip_wikidata = "--skip-wikidata" in sys.argv
    skip_prices = "--skip-prices" in sys.argv
    skip_kb = "--skip-kb" in sys.argv

    # ── Step 1: Fetch enhanced Wikidata ──
    if not skip_wikidata:
        logger.info("=" * 60)
        logger.info("STEP 1: 获取增强 Wikidata 数据")
        logger.info("=" * 60)
        from scripts.fetch_wikidata_enhanced import main as fetch_wd
        await fetch_wd()
    else:
        logger.info("SKIP: Wikidata fetch")

    # ── Step 2: Merge Wikidata prices ──
    logger.info("=" * 60)
    logger.info("STEP 2: 合并 Wikidata 价格到 attractions.json")
    logger.info("=" * 60)

    # If we have enhanced Wikidata data, merge it
    if WIKIDATA_ENHANCED_FILE.exists():
        data = merge_wikidata_prices(WIKIDATA_ENHANCED_FILE, ATTRACTIONS_FILE)
    elif WIKIDATA_FILE.exists():
        data = merge_wikidata_prices(WIKIDATA_FILE, ATTRACTIONS_FILE)
    else:
        data = load_json(ATTRACTIONS_FILE)
        logger.warning("没有 Wikidata 增强数据可合并")

    # ── Step 3: Multi-source price enrichment ──
    if not skip_prices:
        logger.info("=" * 60)
        logger.info("STEP 3: 多源价格获取")
        logger.info("=" * 60)
        from scripts.enrich_real_prices import main as enrich_prices
        await enrich_prices(dry_run=False)
    else:
        logger.info("SKIP: Price enrichment")

    # Reload after price enrichment
    data = load_json(ATTRACTIONS_FILE)

    # ── Step 4: Update price_level ──
    logger.info("=" * 60)
    logger.info("STEP 4: 更新 price_level")
    logger.info("=" * 60)
    update_price_levels(data)
    save_json(data, ATTRACTIONS_FILE)

    # ── Step 5: Rebuild knowledge base ──
    if not skip_kb:
        logger.info("=" * 60)
        logger.info("STEP 5: 重建向量库")
        logger.info("=" * 60)
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/build_knowledge_base.py", "rebuild"],
            cwd=str(Path(__file__).resolve().parent.parent),
            capture_output=True, text=True, timeout=120,
        )
        logger.info(result.stdout[-500:] if result.stdout else "")
        if result.returncode != 0:
            logger.error(f"KB build failed: {result.stderr[-500:]}")
    else:
        logger.info("SKIP: KB rebuild")

    # ── Step 6: Generate report ──
    logger.info("=" * 60)
    logger.info("STEP 6: 生成数据质量报告")
    logger.info("=" * 60)
    data = load_json(ATTRACTIONS_FILE)
    report = generate_quality_report(data)

    # Save report
    report_file = DATA_DIR / "data_quality_report.json"
    report_data = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_attractions": len(data.get("attractions", [])),
        "verified_prices": sum(1 for a in data.get("attractions", []) if a.get("price_verifiable")),
        "report_text": report,
    }
    save_json(report_data, report_file)
    logger.info(f"报告已保存到 {report_file}")


if __name__ == "__main__":
    asyncio.run(main())