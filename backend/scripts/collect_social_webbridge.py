"""
TravelMind Agent — WebBridge 社交热度采集器

通过 Kimi WebBridge（用户真实浏览器登录态）抓取小红书搜索结果，
提取笔记标题中的 POI 名 + 点赞数 → 生成带热度分值的趋势数据。

数据流向（🔴 铁律：社交源只出热度信号，不出事实）：
  - 匹配 KB 已有 POI → 写入 data/social_trends_live.json（trends.json 兼容格式，
    含 heat_score、平台、来源 URL），供 trend_agent 消费
  - 未匹配的疑似 POI 名 → 追加到 data/social_poi_candidates.json，
    走 verify_merge_social_pois.py 的 OSM 验证管线，验证通过才入 KB

用法：
  cd backend
  python scripts/collect_social_webbridge.py                      # 默认 武汉,郑州,天津
  python scripts/collect_social_webbridge.py --cities 武汉,青岛    # 指定城市
"""

import asyncio
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services.name_normalizer import normalize_poi_name

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ATTRACTIONS_FILE = DATA_DIR / "attractions.json"
OUTPUT_FILE = DATA_DIR / "social_trends_live.json"
CANDIDATES_FILE = DATA_DIR / "social_poi_candidates.json"

WEBBRIDGE_URL = "http://127.0.0.1:10086"
SESSION = "social-trends-live"

DEFAULT_CITIES = ["武汉", "郑州", "天津"]
# 类目定向查询：标题更可能含具体场所名（正文页被 XHS 反爬封锁，只有搜索页可用）
QUERY_TEMPLATES = ["{city}博物馆", "{city}商场", "{city}夜市 美食"]
MAX_NOTES_PER_QUERY = 15
NAV_DELAY = 3.0

# 标题中 POI 名提取：引号包裹名 / 后缀匹配
_QUOTED_RE = re.compile(r"[《「『【]([^《》「」『』【】]{2,15})[》」』】]")
_SUFFIX_RE = re.compile(
    r"([\u4e00-\u9fa5A-Za-z0-9·]{2,14}?"
    r"(?:博物馆|美术馆|科技馆|图书馆|纪念馆|展览馆|海洋馆|水族馆|海洋公园|"
    r"购物中心|商场|百货|大剧院|剧院|书店|古镇|古街|步行街|美食街|夜市|"
    r"遗址公园|主题公园|艺术中心|文化中心|会展中心|"
    r"公园|寺庙|古寺|教堂|乐园|湿地|故居|旧址|遗址|大院|塔|楼|阁))"
)
# 标题噪音词（不作为 POI）
_NOISE = ("攻略", "推荐", "合集", "打卡", "旅游", "旅行", "遛娃", "夏天", "雨天",
          "免费", "必去", "值得", "本地", "地铁", "一日游", "两日游", "三日游")

_EXTRACT_JS = """
(async()=>{
  await new Promise(r=>setTimeout(r,2500));
  const cards=[...document.querySelectorAll('section.note-item')].slice(0,%d).map(s=>{
    const t=s.querySelector('.title, .footer .title, a.title span');
    const l=s.querySelector('.like-wrapper .count, .count');
    const a=s.querySelector('a[href*="/explore/"]');
    return {title:t?t.textContent.trim():'',likes:l?l.textContent.trim():'',href:a?a.href:''}
  }).filter(c=>c.title);
  return JSON.stringify({count:cards.length,cards})
})()
"""

# 抖音视频卡片：文案含 POI 名和话题标签，点赞数在卡片第二行
_EXTRACT_DOUYIN_JS = """
(async()=>{
  await new Promise(r=>setTimeout(r,3500));
  const sel='div[class*="search-result-card"],li[class*="search-result-item"],div[data-e2e="search-result-card"]';
  const cards=[...document.querySelectorAll(sel)].slice(0,%d).map(s=>{
    const a=s.querySelector('a[href*="/video/"]');
    return {text:(s.innerText||'').slice(0,400),href:a?a.href:''}
  }).filter(c=>c.text);
  return JSON.stringify({count:cards.length,cards})
})()
"""


def _parse_douyin_card(text: str) -> Dict[str, str]:
    """Parse douyin card innerText: duration 行之后的纯数字/万行是点赞数，
    其余为文案（含 POI 名与话题标签）。"""
    lines = [l.strip() for l in (text or "").split("\n") if l.strip()]
    likes = ""
    caption: List[str] = []
    for i, l in enumerate(lines):
        if ":" not in l and re.match(r"^[\d.]+万?$", l):
            likes = l
            caption = lines[i + 1:]
            break
    if not caption:
        caption = lines
    return {"title": " ".join(caption)[:200], "likes": likes}


async def _scrape_city_douyin(
    client: httpx.AsyncClient, city: str
) -> List[Dict[str, Any]]:
    """Scrape douyin search video cards for one city."""
    notes: List[Dict[str, Any]] = []
    for tpl in QUERY_TEMPLATES:
        query = tpl.format(city=city)
        url = f"https://www.douyin.com/search/{quote(query)}?type=video"
        try:
            await _wb_command(client, "navigate", {"url": url})
            await asyncio.sleep(NAV_DELAY)
            result = await _wb_command(
                client, "evaluate", {"code": _EXTRACT_DOUYIN_JS % MAX_NOTES_PER_QUERY}
            )
            payload = json.loads(result.get("value", "{}"))
            for card in payload.get("cards", []):
                parsed = _parse_douyin_card(card.get("text", ""))
                if not parsed["title"]:
                    continue
                notes.append({
                    "title": parsed["title"],
                    "likes": parsed["likes"],
                    "href": card.get("href", ""),
                    "query": query,
                    "city": city,
                    "platform": "douyin",
                })
            logger.info(f"  {city} / 抖音 {query}: {payload.get('count', 0)} 条视频")
        except Exception as e:
            logger.warning(f"  {city} / 抖音 {query}: 抓取失败 {e}")
        await asyncio.sleep(NAV_DELAY)
    return notes


def _parse_likes(text: str) -> int:
    """Parse XHS like count text: '262' / '1.2万' / '赞' → int."""
    text = (text or "").strip()
    if not text or text == "赞":
        return 0
    m = re.match(r"^([\d.]+)万$", text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.match(r"^(\d+)$", text)
    return int(m.group(1)) if m else 0


def _heat_from_likes(likes: int) -> int:
    """log-scale likes → heat_score 40-98（与 trends.json 量级对齐）。"""
    import math
    return min(98, 40 + int(math.log10(likes + 1) * 15))


def _extract_place_names(title: str) -> List[str]:
    """Extract candidate POI names from a note title."""
    names: List[str] = []
    for m in _QUOTED_RE.findall(title):
        if not any(n in m for n in _NOISE):
            names.append(m.strip())
    for m in _SUFFIX_RE.findall(title):
        m = m.strip()
        if any(n in m for n in _NOISE):
            continue
        # 去掉开头常见修饰
        m = re.sub(r"^(武汉|郑州|天津|青岛|大连|昆明|南京|福州|南宁|贵阳|深圳|哈尔滨|拉萨|黄山|香格里拉)", "", m)
        if len(m) >= 3:
            names.append(m)
    # 去重保序
    seen = set()
    return [n for n in names if not (n in seen or seen.add(n))]


async def _wb_command(client: httpx.AsyncClient, action: str, args: Dict[str, Any]) -> Dict[str, Any]:
    last_err: Any = None
    for attempt in range(3):
        r = await client.post(
            f"{WEBBRIDGE_URL}/command",
            json={"action": action, "args": args, "session": SESSION},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("ok"):
            return data.get("data", {})
        err = data.get("error", {})
        last_err = err
        # 扩展偶发 Detached（页面加载时序），等待后重试
        if "Detached" in str(err.get("message", "")) and attempt < 2:
            await asyncio.sleep(3)
            continue
        raise RuntimeError(f"WebBridge {action} failed: {err}")
    raise RuntimeError(f"WebBridge {action} failed after retries: {last_err}")


async def _scrape_city(
    client: httpx.AsyncClient, city: str
) -> List[Dict[str, Any]]:
    """Scrape XHS search results for one city → raw note cards."""
    notes: List[Dict[str, Any]] = []
    for tpl in QUERY_TEMPLATES:
        query = tpl.format(city=city)
        url = f"https://www.xiaohongshu.com/search_result?keyword={quote(query)}&type=51"
        try:
            await _wb_command(client, "navigate", {"url": url})
            await asyncio.sleep(NAV_DELAY)
            result = await _wb_command(
                client, "evaluate", {"code": _EXTRACT_JS % MAX_NOTES_PER_QUERY}
            )
            payload = json.loads(result.get("value", "{}"))
            for card in payload.get("cards", []):
                card["query"] = query
                card["city"] = city
                notes.append(card)
            logger.info(f"  {city} / {query}: {payload.get('count', 0)} 条笔记")
        except Exception as e:
            logger.warning(f"  {city} / {query}: 抓取失败 {e}")
        await asyncio.sleep(NAV_DELAY)
    return notes


def _load_attractions() -> List[Dict[str, Any]]:
    with open(ATTRACTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)["attractions"]


async def main(cities: List[str], platform: str = "xiaohongshu") -> None:
    # WebBridge 健康检查
    async with httpx.AsyncClient(timeout=10) as probe:
        try:
            r = await probe.post(
                f"{WEBBRIDGE_URL}/command",
                json={"action": "list_tabs", "args": {}, "session": SESSION},
            )
            if not r.json().get("ok"):
                raise RuntimeError(r.json())
        except Exception as e:
            logger.error(f"WebBridge 不可达: {e}。请先启动 daemon 并打开浏览器。")
            return

    attractions_all = _load_attractions()
    all_trends: List[Dict[str, Any]] = []
    all_candidates: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        for city in cities:
            logger.info(f"采集 {city}...")
            scraper = _scrape_city_douyin if platform == "douyin" else _scrape_city
            notes = await scraper(client, city)

            # ⚠️ XHS 反爬：笔记正文页返回「当前笔记暂时无法浏览，请打开App扫码」，
            # 登录态也无法读取正文（2026-07-25 实测）。只有搜索结果页（标题/点赞）
            # 可用，因此不做正文抓取，匹配仅基于标题。

            # 标题 ↔ KB 名双向匹配：城市内每个 KB POI 的名称变体
            # （原名/normalized/去城市前缀的 core）在文本中出现即计热度。
            kb_city = [a for a in attractions_all if a.get("city") == city]
            name_variants: List[tuple] = []
            for a in kb_city:
                official = a["name"]
                variants = {official}
                norm = a.get("name_normalized") or normalize_poi_name(official)
                if norm and len(norm) >= 3:
                    variants.add(norm)
                core = official[len(city):] if official.startswith(city) else official
                if len(core) >= 4:
                    variants.add(core)
                name_variants.append((official, variants))

            poi_heat: Dict[str, Dict[str, Any]] = {}
            for note in notes:
                likes = _parse_likes(note.get("likes", ""))
                text = (note.get("title", "") or "") + "\n" + (note.get("content", "") or "")
                if not text.strip():
                    continue
                for official, variants in name_variants:
                    if any(v in text for v in variants):
                        cur = poi_heat.get(official)
                        if not cur or likes > cur["likes"]:
                            poi_heat[official] = {
                                "likes": likes,
                                "href": note.get("href", ""),
                                "title": note.get("title", ""),
                                "platform": note.get("platform", platform),
                            }

            matched = 0
            for official, info in poi_heat.items():
                all_trends.append({
                    "city": city,
                    "place_name": official,
                    "tag": "社交热议",
                    "heat_score": _heat_from_likes(info["likes"]),
                    "rank": 0,
                    "source": info["platform"],
                    "source_url": info["href"],
                    "likes": info["likes"],
                })
                matched += 1

            # 新 POI 发现：标题中的引号名/后缀名，排除 KB 已有
            unmatched = 0
            kb_norms = {v for _, variants in name_variants for v in variants}
            seen_cand = set()
            for note in notes:
                likes = _parse_likes(note.get("likes", ""))
                for name in _extract_place_names(note.get("title", "")):
                    if name in kb_norms or name in seen_cand:
                        continue
                    seen_cand.add(name)
                    all_candidates.append({
                        "city": city,
                        "name": name,
                        "category": "室内其他",
                        "source_url": note.get("href", "") or "xiaohongshu-search",
                        "likes": likes,
                    })
                    unmatched += 1
            logger.info(f"  {city}: KB 匹配 {matched}，新候选 {unmatched}")

    # 写入 trends（与已有数据合并：同 city+place+source 覆盖，其余保留；
    # 绝不因本次零产出而清空历史数据）
    existing_trends: List[Dict[str, Any]] = []
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing_trends = json.load(f).get("trends", [])
        except Exception:
            pass
    new_keys = {(t["city"], t["place_name"], t["source"]) for t in all_trends}
    merged_trends = [
        t for t in existing_trends
        if (t.get("city"), t.get("place_name"), t.get("source")) not in new_keys
    ]
    merged_trends.extend(all_trends)
    output = {
        "source": "WebBridge social live",
        "collected_at": time.strftime("%Y-%m-%d %H:%M"),
        "cities": cities,
        "trends": merged_trends,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"\n趋势数据 新增 {len(all_trends)} 条，合并后共 {len(merged_trends)} 条 → {OUTPUT_FILE}")

    # 未匹配候选追加到验证管线
    if all_candidates:
        existing = {"candidates": []}
        if CANDIDATES_FILE.exists():
            with open(CANDIDATES_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        seen = {(c["city"], c["name"]) for c in existing.get("candidates", [])}
        added = 0
        for c in all_candidates:
            if (c["city"], c["name"]) not in seen:
                existing["candidates"].append(c)
                seen.add((c["city"], c["name"]))
                added += 1
        with open(CANDIDATES_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        logger.info(f"新候选 {added} 条追加到 {CANDIDATES_FILE}（待 OSM 验证）")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="WebBridge 社交热度采集")
    parser.add_argument("--cities", type=str, default="",
                        help="逗号分隔城市列表")
    parser.add_argument("--platform", type=str, default="xiaohongshu",
                        choices=["xiaohongshu", "douyin"],
                        help="采集平台（默认小红书）")
    args = parser.parse_args()
    city_list = ([c.strip() for c in args.cities.split(",") if c.strip()]
                 if args.cities else DEFAULT_CITIES)
    asyncio.run(main(city_list, platform=args.platform))
