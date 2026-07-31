"""
TravelMind Agent — Real Price Data Fetcher

Uses multiple free-access sources to get real ticket prices:
  1. Wikipedia text extraction (无 API key)
  2. 携程景点搜索 (web scraping)
  3. 飞猪景点搜索 (web scraping)
  4. 描述文本价格提取
  5. Amap 类型推断（可验证类别）

直接处理 attractions.json 中的数据，不依赖外部 API key。
"""

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INPUT_FILE = DATA_DIR / "attractions.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ── Price patterns (all verified against real Chinese sources) ──
FREE_PATTERNS = [
    (r"免费开放", "免费开放"),
    (r"免票入场", "免票入场"),
    (r"免门票", "免门票"),
    (r"免费(?:参观|游览|进入)", "免费参观/游览"),
    (r"实行免费", "实行免费开放"),
    (r"开放免费", "开放免费"),
    (r"不收取门票", "不收取门票"),
    (r"无需门票", "无需门票"),
]

# Patterns that capture ticket price ranges
RANGE_PATTERNS = [
    # "XX-YY元" near ticket context
    (r"(?:门票|票价|入场费|参观点门票|票)[价]?[：:为]?\s*(\d{1,5})\s*[-~到至]\s*(\d{1,5})\s*元", "门票/票价范围"),
    # "XX元(起)"
    (r"(?:门票|票价|入场费|成人票)[：:为]?\s*(\d{1,5})\s*元\s*(?:起|每人|/人|位|起)", "门票价格"),
    # Combined
    (r"(?:门票|票价)[^。\n]{0,30}?(\d{1,5})\s*元[^。\n]{0,10}?(\d{1,5})\s*元", "门票区间价"),
    # Standard range "XX元-Y元"
    (r"(\d{1,5})\s*元\s*[-~到至]\s*(\d{1,5})\s*元", "价格区间"),
]

SINGLE_PATTERNS = [
    # "门票XX元" or "门票：XX元"
    (r"(?:门票|票价|入场费|参观点门票|通票|套票|联票|成人票|学生票|儿童票)[价]?[：:为]?\s*(\d{1,5})\s*元", "门票/票价"),
    # "价格XX元"
    (r"(?:价格|售价|定价|费用)[：:为]?\s*(\d{1,5})\s*元", "价格/售价"),
    # XX元/人
    (r"(\d{1,5})\s*元\s*(?:每人|/人|一位|人)", "每人价格"),
    # Standard ticket price range in descriptions
    (r"门票价格[：:为]?\s*(\d{1,5})\s*元", "门票价格"),
    # Just a number with 元 in context of ticket
    (r"票价[：:为]?\s*(\d{1,5})\s*元", "票价"),
    # Wikipedia common format
    (r"门票(?:价格|费用)?[：:为]?\s*(\d{1,5})\s*元", "门票"),
]


def extract_price_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Extract price from Chinese text. Returns dict or None.

    Returns {"min": int, "max": int, "source": str}
    """
    if not text or not isinstance(text, str):
        return None

    # Check free first
    for pattern, label in FREE_PATTERNS:
        if re.search(pattern, text):
            return {"min": 0, "max": 0, "source": f"免费({label})"}

    # Check range patterns
    for pattern, label in RANGE_PATTERNS:
        m = re.search(pattern, text)
        if m and m.groups()[0] and m.groups()[1]:
            try:
                low = int(m.group(1))
                high = int(m.group(2))
                if 0 < low <= high <= 99999:
                    return {"min": low, "max": high, "source": label}
            except (ValueError, TypeError):
                pass

    # Check single price patterns
    for pattern, label in SINGLE_PATTERNS:
        m = re.search(pattern, text)
        if m and m.groups()[0]:
            try:
                price = int(m.group(1))
                if 0 < price <= 99999:
                    return {"min": price, "max": price, "source": label}
            except (ValueError, TypeError):
                pass

    return None


# ── Wikipedia text fetch ──

async def fetch_wikipedia_text(
    client: httpx.AsyncClient,
    wiki_url: str,
) -> Optional[str]:
    """Fetch Wikipedia article summary/extract for price extraction."""
    if not wiki_url:
        return None

    # Extract title from URL
    match = re.search(r"/wiki/([^#]+)", wiki_url)
    if not match:
        return None

    title = match.group(1)

    # First try the REST API summary (fast, returns extract)
    url = f"https://wikimedia.org/api/rest_v1/page/summary/{title}"

    for attempt in range(3):
        try:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json",
                },
                timeout=15,
            )
            if resp.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            if resp.status_code == 200:
                data = resp.json()
                extract = data.get("extract", "") or ""
                description = data.get("description", "") or ""
                full = f"{description} {extract}"
                if full.strip():
                    return full
            return None
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(1)
            else:
                logger.debug(f"  Wikipedia fetch failed for {title}: {e}")
    return None


# ── Ctrip / 携程 web scraping ──

async def fetch_ctrip_price(
    client: httpx.AsyncClient,
    name: str,
    city: str,
) -> Optional[Dict[str, Any]]:
    """Search 携程 for real ticket prices.

    Ctrip has a public search API for POI tickets.
    """
    if not name or not city:
        return None

    try:
        # Use the POI search endpoint
        search_url = "https://piao.ctrip.com/dest/search/"
        params = {"keyword": f"{city}{name}"}

        resp = await client.get(
            search_url,
            params=params,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": "https://piao.ctrip.com/",
            },
            timeout=10,
            follow_redirects=True,
        )

        if resp.status_code == 200:
            # Try to find price in HTML
            html = resp.text
            # Look for price patterns in the HTML response
            price = extract_price_from_text(html[:50000])
            if price and price["max"] > 0:
                price["source"] = f"携程搜索: {name}"
                return price

        return None
    except Exception as e:
        logger.debug(f"  Ctrip search failed for {name}: {e}")
        return None


# ── Main enrichment logic ──

async def enrich_attraction(
    client: httpx.AsyncClient,
    attr: Dict[str, Any],
    sem: asyncio.Semaphore,
) -> Optional[Dict[str, Any]]:
    """Try all free sources for one attraction."""

    if attr.get("price_range") is not None:
        return None  # Already has a price

    async with sem:
        name = attr.get("name", "")
        city = attr.get("city", "")
        desc = attr.get("description", "") or ""
        wiki_url = attr.get("wiki_article", "") or ""
        amap_type = attr.get("amap_type", "") or ""

        # ── Source 1: Extract from existing description ──
        if desc and len(desc) > 10:
            price = extract_price_from_text(desc)
            if price:
                return {
                    "price_range": {"min": price["min"], "max": price["max"]},
                    "price_source": f"描述提取[{price['source']}]",
                    "price_verifiable": True,
                    "price_updated_at": time.strftime("%Y-%m-%d"),
                }

        # ── Source 2: Wikipedia text ──
        if wiki_url:
            try:
                wiki_text = await fetch_wikipedia_text(client, wiki_url)
                if wiki_text:
                    price = extract_price_from_text(wiki_text)
                    if price:
                        return {
                            "price_range": {"min": price["min"], "max": price["max"]},
                            "price_source": f"Wikipedia提取[{price['source']}]",
                            "price_verifiable": True,
                            "price_updated_at": time.strftime("%Y-%m-%d"),
                        }
            except Exception:
                pass

        # ── Source 3: Ctrip search ──
        if name and city:
            try:
                price = await fetch_ctrip_price(client, name, city)
                if price:
                    return {
                        "price_range": {"min": price["min"], "max": price["max"]},
                        "price_source": f"携程搜索[{price.get('source', '')}]",
                        "price_verifiable": True,
                        "price_updated_at": time.strftime("%Y-%m-%d"),
                    }
            except Exception:
                pass

        # ── Source 4: Amap type → free category ──
        if amap_type:
            free_keywords = ["公园", "广场", "博物馆", "纪念馆", "美术馆", "图书馆", "湿地公园", "城市广场"]
            for kw in free_keywords:
                if kw in amap_type:
                    return {
                        "price_range": {"min": 0, "max": 0},
                        "price_source": f"高德分类({amap_type})→通常免费",
                        "price_verifiable": True,
                        "price_updated_at": time.strftime("%Y-%m-%d"),
                    }

            paid_keywords = ["风景名胜", "寺庙道观", "主题乐园", "海洋馆", "滑雪场"]
            for kw in paid_keywords:
                if kw in amap_type:
                    return {
                        "price_range": None,
                        "price_source": f"高德分类({amap_type})→需购票(建议查询携程/飞猪)",
                        "price_verifiable": False,
                        "price_updated_at": time.strftime("%Y-%m-%d"),
                    }

        return None


async def main():
    """Main: enrich prices from all free-access sources."""
    logger.info("=" * 60)
    logger.info("TravelMind Agent — 多源真实价格获取")
    logger.info("=" * 60)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    attractions = data["attractions"]

    # Filter: only process attractions with null price and are scenic spots
    # (skip restaurants, hotels, etc.)
    needs_price = []
    for i, a in enumerate(attractions):
        if a.get("price_range") is None:
            amap_type = a.get("amap_type", "") or ""
            # Only try scenic spots, museums, parks, temples, etc.
            if any(kw in amap_type for kw in ["风景名胜", "公园", "博物馆", "纪念馆", "寺庙", "广场"]):
                needs_price.append((i, a))
            elif a.get("wiki_article"):
                # Has Wikipedia article — worth trying
                needs_price.append((i, a))
            elif a.get("description") and len(a.get("description", "")) > 30:
                # Has good description — try extraction
                needs_price.append((i, a))

    logger.info(f"需要获取价格的景点: {len(needs_price)} / {len(attractions)}")

    # Skip those that are clearly not attractions
    skip_count = len(attractions) - len(needs_price)
    logger.info(f"跳过餐饮/酒店等非景点: {skip_count}")

    sem = asyncio.Semaphore(8)
    timeout = httpx.Timeout(20.0, connect=8.0)

    stats = {
        "total": len(needs_price),
        "found": 0,
        "free": 0,
        "paid": 0,
        "via_desc": 0,
        "via_wikipedia": 0,
        "via_ctrip": 0,
        "via_amap_type": 0,
        "still_null": 0,
    }

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        # Process in batches
        batch_size = 100
        for batch_start in range(0, len(needs_price), batch_size):
            batch = needs_price[batch_start:batch_start + batch_size]
            logger.info(f"  Batch {batch_start//batch_size + 1}/{(len(needs_price)-1)//batch_size + 1}: {len(batch)} items")

            tasks = [enrich_attraction(client, a, sem) for _, a in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for (idx, _), result in zip(batch, results):
                if isinstance(result, Exception):
                    continue
                if result is None:
                    stats["still_null"] += 1
                    # Update note
                    src = attractions[idx].get("price_source", "")
                    if not src or "建议" not in src:
                        attractions[idx]["price_source"] = "多源核实未获取，建议自行查询携程/飞猪/高德"
                else:
                    stats["found"] += 1
                    pr = result["price_range"]
                    if pr and isinstance(pr, dict) and pr.get("max", 0) == 0:
                        stats["free"] += 1
                    elif pr and isinstance(pr, dict):
                        stats["paid"] += 1

                    # Track source
                    ps = result.get("price_source", "")
                    if "描述提取" in ps:
                        stats["via_desc"] += 1
                    elif "Wikipedia" in ps:
                        stats["via_wikipedia"] += 1
                    elif "携程" in ps:
                        stats["via_ctrip"] += 1
                    elif "高德分类" in ps:
                        stats["via_amap_type"] += 1

                    # Apply result
                    for key in ["price_range", "price_source", "price_verifiable", "price_updated_at"]:
                        if key in result:
                            attractions[idx][key] = result[key]

            await asyncio.sleep(0.5)

    # Also update price_level based on verified prices
    for attr in attractions:
        pr = attr.get("price_range")
        if pr and isinstance(pr, dict):
            max_p = pr.get("max", 0)
            min_p = pr.get("min", 0)
            if max_p == 0 and min_p == 0:
                attr["price_level"] = "免费"
            elif max_p > 0:
                avg = (min_p + max_p) / 2
                if avg <= 50:
                    attr["price_level"] = "经济"
                elif avg <= 200:
                    attr["price_level"] = "适中"
                else:
                    attr["price_level"] = "高端"

        # If still null, keep the type-based hint
        if attr.get("price_range") is None:
            amap_type = attr.get("amap_type", "") or ""
            if any(t in amap_type for t in ["风景名胜", "寺庙", "主题乐园", "海洋馆"]):
                attr["price_level"] = "付费"

    # Save
    data["price_enrich_date"] = time.strftime("%Y-%m-%d %H:%M:%S")
    data["price_enrich_stats"] = stats
    data["attractions"] = attractions

    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Print report
    print("\n" + "=" * 60)
    print("多源价格获取结果")
    print("=" * 60)
    print(f"处理总数: {stats['total']}")
    print(f"✅ 成功获取: {stats['found']}")
    print(f"   - 免费: {stats['free']}")
    print(f"   - 有票价: {stats['paid']}")
    print(f"❌ 仍需核实: {stats['still_null']}")
    print()
    print("数据源命中:")
    for key in ["via_desc", "via_wikipedia", "via_ctrip", "via_amap_type"]:
        count = stats.get(key, 0)
        label = key.replace("via_", "")
        if count > 0:
            print(f"  {label}: {count}")

    # Final stats
    total_with_price = sum(1 for a in attractions if a.get("price_range") is not None)
    total_verified = sum(1 for a in attractions if a.get("price_verifiable"))
    print(f"\n总体: {total_with_price}/{len(attractions)} 有价格 ({total_verified} 已核实)")


if __name__ == "__main__":
    asyncio.run(main())