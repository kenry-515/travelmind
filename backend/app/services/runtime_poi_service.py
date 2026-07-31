"""
TravelMind Agent — Runtime POI Service

Real-time POI (Point of Interest) discovery for ANY city in China.
Replaces the static-KB-only approach with a hybrid model:

  1. STATIC KB (attractions.json) — fast-path cache for 3,391 known attractions
  2. RUNTIME API — fetch POIs for ANY city not in the static KB
  3. MERGE — combine static + runtime results into a unified candidate pool

Supported POI types:
  - attractions (景点): scenic spots, museums, landmarks, parks
  - restaurants (美食): local cuisine, famous restaurants, food streets
  - hotels (酒店): accommodations (for reference, not booking)

Data sources (cascading):
  1. Bing search (cn.bing.com) — works from China without API key
  2. Amap POI Search API (when AMAP_KEY env var available)
  3. Trip.com Open API (when TRIP_API_KEY env var available)
  4. Fallback — generate search links for user self-service

This is the KEY architecture change: the system can now answer queries
about ANY city, ANY attraction, ANY food, ANY hotel in China,
with real data fetched at request time.
"""

import asyncio
import json
import logging
import os
import re
import socket
import tempfile
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

# ── Configuration ───────────────────────────────────────────

# ── Caching (thread-safe, in-memory with periodic flush) ────

import threading

_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "poi_cache"
_CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 days
_DEFAULT_LIMIT = 20  # default POIs per category

# Thread-safe in-memory cache (avoids repeated file I/O)
_cache_lock = threading.Lock()
_cache_data: Optional[Dict[str, Any]] = None
_cache_dirty = False
_LAST_FLUSH = 0.0
_FLUSH_INTERVAL = 30.0  # seconds between auto-flushes to disk

# POI type definitions with search keywords
_POI_CATEGORIES = {
    "attractions": {
        "label": "景点",
        "bing_suffix": "景区 门票 必去 旅游攻略",
        "amap_type": "景区",
        "filter_include": ["景区", "景点", "门票", "旅游", "名胜", "古迹", "遗址", "公园", "博物馆", "纪念馆", "古城", "古镇", "塔", "寺", "庙", "楼", "阁", "洞", "湖", "山", "海", "瀑布", "峡谷", "森林", "草原", "沙漠", "石林", "温泉", "乐园", "水族馆", "动物园", "植物园"],
        "filter_exclude": ["酒店", "餐厅", "饭店", "客栈", "民宿", "宾馆", "住宿", "美食", "小吃", "餐馆", "米线", "火锅", "烧烤"],
    },
    "restaurants": {
        "label": "美食",
        "bing_suffix": "特色美食 餐厅 饭店 必吃",
        "amap_type": "餐厅",
        "filter_include": ["餐厅", "饭店", "美食", "小吃", "馆", "酒楼", "火锅", "烧烤", "酒吧", "咖啡馆", "甜品", "蛋糕", "面包", "茶餐厅", "餐馆", "食府", "记", "坊", "米线", "面", "铺", "摊", "串串", "麻辣烫", "烤鱼", "烤肉", "日料", "韩餐", "西餐", "小炒", "中餐", "自助餐"],
        "filter_exclude": ["景区", "景点", "博物馆", "公园", "酒店", "客栈", "民宿", "宾馆", "住宿", "大酒店"],
    },
    "hotels": {
        "label": "酒店",
        "bing_suffix": "酒店 客栈 民宿 住宿 预订",
        "amap_type": "酒店",
        "filter_include": ["酒店", "大酒店", "客栈", "民宿", "宾馆", "旅店", "旅馆", "青年旅舍", "度假村", "公寓", "住宿", "连锁", "如家", "7天", "汉庭", "锦江", "速8", "万豪", "希尔顿", "洲际", "雅高", "香格里拉"],
        "filter_exclude": ["景区", "景点", "博物馆", "公园", "美食", "小吃", "餐厅", "饭店", "米线", "火锅", "烧烤", "铺", "摊"],
    },
}

# Headers to mimic a real browser
_BING_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# Semaphore for rate limiting Bing requests
_BING_SEM = asyncio.Semaphore(5)
_BING_TIMEOUT = 10

# Wikipedia API for POI discovery (high quality, structured data)
_WIKIPEDIA_API = "https://zh.wikipedia.org/w/api.php"
_WIKIPEDIA_TIMEOUT = 8
_WIKIPEDIA_UA = "TravelMindAgent/1.0 (https://github.com/travelmind; mailto:travelmind@example.com)"

# Proxy detection — check for common local proxy ports
_PROXY_CANDIDATES = [
    "http://127.0.0.1:34131",
    "http://127.0.0.1:7890",
    "http://127.0.0.1:1080",
    "http://127.0.0.1:10808",
]

_DETECTED_PROXY: Optional[str] = None


def _detect_proxy() -> Optional[str]:
    """Auto-detect local proxy by checking common ports."""
    global _DETECTED_PROXY
    if _DETECTED_PROXY is not None:
        return _DETECTED_PROXY
    # Check if proxy is already configured via env var
    for var in ["HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"]:
        val = os.environ.get(var, "")
        if val:
            _DETECTED_PROXY = val
            return val
    # Try common local proxy ports
    for proxy_url in _PROXY_CANDIDATES:
        try:
            host, port_str = proxy_url.replace("http://", "").split(":")
            port = int(port_str)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                logger.info(f"Auto-detected local proxy: {proxy_url}")
                _DETECTED_PROXY = proxy_url
                return proxy_url
        except Exception:
            continue
    _DETECTED_PROXY = ""
    return None


def _build_httpx_client(timeout: int = 15, use_proxy: bool = False) -> httpx.AsyncClient:
    """Build an httpx client with optional proxy support."""
    if use_proxy:
        proxy = _detect_proxy()
        if proxy:
            logger.debug(f"Using proxy: {proxy}")
            return httpx.AsyncClient(timeout=timeout, proxy=proxy, trust_env=True)
    return httpx.AsyncClient(timeout=timeout, trust_env=True)


# ── Caching ────────────────────────────────────────────────


def _cache_path() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / "poi_queries.json"


def _load_cache() -> Dict[str, Any]:
    """Load cache into memory (thread-safe, one-time load)."""
    global _cache_data, _LAST_FLUSH
    with _cache_lock:
        if _cache_data is not None:
            return _cache_data
        path = _cache_path()
        if path.exists():
            try:
                _cache_data = json.loads(path.read_text("utf-8"))
            except (json.JSONDecodeError, IOError):
                _cache_data = {}
        else:
            _cache_data = {}
        _LAST_FLUSH = time.time()
        return _cache_data


def _save_cache(force: bool = False) -> None:
    """Flush in-memory cache to disk (atomic write via temp file)."""
    global _cache_data, _cache_dirty, _LAST_FLUSH
    with _cache_lock:
        if not _cache_dirty and not force:
            return
        if _cache_data is None:
            return
        try:
            path = _cache_path()
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=str(_CACHE_DIR), suffix=".json.tmp"
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(_cache_data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, str(path))
                _cache_dirty = False
                _LAST_FLUSH = time.time()
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except IOError as e:
            logger.warning(f"Failed to save POI cache: {e}")


def _maybe_flush_cache() -> None:
    """Auto-flush cache if enough time has passed since last flush."""
    global _LAST_FLUSH
    if _cache_dirty and (time.time() - _LAST_FLUSH) > _FLUSH_INTERVAL:
        _save_cache(force=True)


def _get_cached(city: str, category: str) -> Optional[Dict[str, Any]]:
    cache = _load_cache()
    key = f"{city}|{category}"
    entry = cache.get(key)
    if not entry:
        return None
    ts = entry.get("timestamp", 0)
    if time.time() - ts > _CACHE_TTL_SECONDS:
        return None
    return entry.get("data")


def _set_cached(city: str, category: str, data: Dict[str, Any]) -> None:
    global _cache_dirty
    cache = _load_cache()
    key = f"{city}|{category}"
    cache[key] = {"timestamp": time.time(), "data": data}
    _cache_dirty = True
    _maybe_flush_cache()


# ── City coverage check ────────────────────────────────────

_KB_CITIES_CACHE: Optional[List[str]] = None
_KB_CITIES_CACHE_TS: float = 0.0


def get_kb_cities() -> List[str]:
    """Return list of cities covered by the static knowledge base (cached)."""
    global _KB_CITIES_CACHE, _KB_CITIES_CACHE_TS
    now = time.time()
    if _KB_CITIES_CACHE is not None and (now - _KB_CITIES_CACHE_TS) < 300:
        return _KB_CITIES_CACHE
    try:
        data_path = Path(__file__).parent.parent.parent / "data" / "attractions.json"
        with open(data_path, "r", encoding="utf-8") as f:
            cities = sorted(
                {
                    a.get("city", "")
                    for a in json.load(f).get("attractions", [])
                    if a.get("city")
                }
            )
        _KB_CITIES_CACHE = cities
        _KB_CITIES_CACHE_TS = now
        return cities
    except Exception:
        return []


def is_city_in_kb(city: str) -> bool:
    """Check if a city has data in the static knowledge base."""
    if not city:
        return False
    kb_cities = get_kb_cities()
    return city in kb_cities


# ── POI parsing from Bing search ────────────────────────────


# ── Pre-compiled regex patterns (performance) ───────────────

_RE_HTML_TAG = re.compile(r"<[^>]+>")
_RE_PIPE_SEP = re.compile(r"[|｜丨:：]")
_RE_ADMIN_SUFFIX = re.compile(r"(省|市|区|县|盟|自治州|特别行政区)$")
_RE_CHINESE_CHARS = re.compile(r"[\u4e00-\u9fff]")
_RE_DIGIT_START = re.compile(r"^\d")
_RE_DIGITS_2PLUS = re.compile(r"\d{2,}")
_RE_PUNCTUATION = re.compile(r"[，,。.!！?？]")
_RE_DASH_SUFFIX = re.compile(r"\s*[-–—_].*$")
_RE_PARENTHETICAL = re.compile(r"[（(].*?[）)]")
_RE_ARTICLE_MARKERS = re.compile(r"(推荐|攻略|必去|必吃|必玩|大全|排行|盘点|汇总)")
_RE_SUSPICIOUS = re.compile(
    r"^\d+|^\d+[万人千口]+$|^[A-Za-z]{3,}$|"
    r"Dept\. of|Department|Council|Government|University|College|Institute|Vote|Election",
    re.IGNORECASE
)
_RE_INSTITUTION = re.compile(
    r"人民政府|市政府|区委|行政公署|委员会|政府|党委|人大|政协|公安局|法院|检察院"
)
_RE_FRAGMENT = re.compile(
    r"(时间|提醒|查询|预订|开放|免费政策|政策|方式|多少钱|价格|多少钱|费用|花销)|"
    r"(提供|为您|整理|包括)|"
    r"(门票价格|门票团购|门票预订|门票开放)|"
    r"(旅游景点|景点门票|旅游攻略)|"
    r"^\d"
)
_RE_STRONG_ARTICLE = re.compile(
    r"(攻略|推荐|必去|必吃|大全|排行|盘点|汇总)|"
    r"(第\d+站|去了\d+次|打卡)|"
    r"(门票价格|门票团购|门票预订)|"
    r"(旅游景点|必游景点)|"
    r"(值得去|此生无憾|不能错过)"
)

# Article/listicle detection patterns
_ARTICLE_DETECT_PATTERNS = [
    r"推荐", r"攻略", r"有哪些", r"盘点", r"汇总",
    r"排行榜", r"必去", r"必吃", r"必玩", r"大全",
    r"旅游", r"景点", r"美食", r"酒店", r"住宿",
    r"好玩", r"值得", r"TOP", r"排名", r"指南",
    r"十大", r"九大", r"八大", r"七大", r"六大",
    r"去了", r"玩法", r"玩转", r"地方", r"攻略",
    r"最美", r"最值得", r"此生无憾", r"秘境",
    r"之地", r"纯净", r"休闲", r"终于", r"明白了",
    r"第\d+站", r"打卡", r"必游", r"必看",
]

# Non-POI skip patterns
_SKIP_PATTERNS_COMMON = [
    r"百度百科", r"维基百科", r"汉语词语", r"词典",
    r"玉溪烟", r"多少钱", r"价格", r"官网",
    r"人民政府", r"市政府", r"区委",
]


def _is_likely_poi_title(title: str) -> bool:
    """Check if a title is likely a real POI name, not an article or non-POI."""
    if not title:
        return False
    clean = title.strip()
    if len(clean) < 2:
        return False
    if len(clean) > 80:
        return False

    # Quick reject: number-only or very suspicious patterns
    if _RE_SUSPICIOUS.search(clean):
        return False

    # Check for government/institution patterns
    if _RE_INSTITUTION.search(clean):
        return False

    # Check for phone/address patterns (not POI names)
    if re.search(r"(电话|地址|预订|官网|人均|价格|营业时间)[:：]?", clean):
        return False

    # Quick reject: title contains pipe/separator (article format)
    if _RE_PIPE_SEP.search(clean):
        return False
    
    # Quick reject: title is a fragment/query string (not a POI name)
    if _RE_FRAGMENT.search(clean):
        return False
    
    # Quick reject: title contains query/mobile/phone patterns
    _QUERY_PATTERNS = [
        r"多少钱", r"价格", r"费用", r"花销",
        r"怎么去", r"怎么走", r"如何去", r"如何到达",
        r"在哪里", r"在哪", r"在哪[儿里]",
        r"有.*好玩的", r"有.*好吃的",
        r"几[点时]", r"开放时间",
    ]
    for pat in _QUERY_PATTERNS:
        if re.search(pat, clean):
            return False
    
    # Check for article/listicle keywords
    hits = sum(1 for p in _ARTICLE_DETECT_PATTERNS if re.search(p, clean))
    if hits >= 2:
        return False
    
    # Single article keyword might indicate a real POI with description
    # Only reject if it looks like a pure article title
    if hits == 1:
        _ARTICLE_TITLE_PATTERNS = [
            r"^.*(攻略|推荐|必去|必吃|大全|排行).*$",
            r"^\d+.*地方",
            r"^.*(值得|不能错过|此生).*$",
            r"^.*(TOP|Top|top)\d*.*$",
            r"^.*(半程|全程|马拉松|赛事).*$",
            r"^.*(住宿大优惠|特价|促销).*$",
            r"^.*(第\d+站|终于|明白了).*$",
            r"^.*(纯净|休闲).*$",
        ]
        for pat in _ARTICLE_TITLE_PATTERNS:
            if re.search(pat, clean):
                return False

    # Must contain some Chinese characters for Chinese queries
    if not _RE_CHINESE_CHARS.search(clean):
        return False

    # POI name quality check - short names like "玉溪" are acceptable
    # since they're cleaned from article titles
    # But pure admin names without POI context should be rejected
    if _RE_ADMIN_SUFFIX.search(clean) and len(clean) <= 2:
        # Very short (2 chars) ending with admin suffix
        # These are likely just city/district abbreviations
        if re.match(r"^[\u4e00-\u9fff]{2}$", clean):
            return False

    return True


def _filter_by_category(items: List[Dict[str, Any]], category: str) -> List[Dict[str, Any]]:
    """Filter POI items to match the requested category.

    Uses category-specific include/exclude keyword lists to
    differentiate between attractions, restaurants, and hotels
    when Bing returns mixed/identical results.

    Cross-category exclusion: if an item matches another category's
    include keywords but not the current category's, it's excluded.
    """
    config = _POI_CATEGORIES.get(category, {})
    include_words = config.get("filter_include", [])
    exclude_words = config.get("filter_exclude", [])

    if not include_words and not exclude_words:
        return items

    # Collect include words from ALL other categories for cross-filtering
    other_include_words: List[str] = []
    for cat, cat_config in _POI_CATEGORIES.items():
        if cat != category:
            other_include_words.extend(cat_config.get("filter_include", []))

    # Deduplicate
    other_include_words = list(set(other_include_words) - set(include_words))

    filtered = []
    for item in items:
        name = item.get("name", "")
        desc = item.get("description", "")
        full_text = f"{name} {desc}"

        # Skip search_link items (they are category-agnostic)
        if item.get("source") == "search_link":
            filtered.append(item)
            continue

        # Check exclude first — if it contains exclude words, skip
        has_exclude = any(w in full_text for w in exclude_words)
        if has_exclude:
            continue

        # If it contains include words, keep it
        has_include = any(w in full_text for w in include_words)
        if has_include:
            filtered.append(item)
            continue

        # Cross-category check: if it matches another category's include, skip
        # (it clearly belongs to a different category)
        matches_other = any(w in full_text for w in other_include_words)
        if matches_other:
            continue

        # For remaining items that match nothing, keep them only if they
        # look like generic POIs (not city-level admin entries etc.)
        city_markers = ["市", "省", "区", "县", "地区", "盟", "自治州"]
        if any(m in name for m in city_markers):
            continue

        # Keep as fallback (might be a valid POI we can't categorize)
        filtered.append(item)

    return filtered


def _separate_search_links(
    items: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Separate real POI items from search_link fallback items.

    Returns (real_pois, search_links) tuple.
    """
    real_pois = []
    search_links = []
    for item in items:
        if item.get("source") == "search_link":
            search_links.append(item)
        else:
            real_pois.append(item)
    return real_pois, search_links


def _parse_bing_results(html: str, category: str, limit: int) -> List[Dict[str, Any]]:
    """Parse Bing search results page to extract POI names and metadata.

    Two strategies:
    1. Direct POI results: Extract POI names from search result titles
    2. List/article results: Extract POI names from article snippets that
       contain lists of attractions/restaurants/hotels

    Filters out non-POI results like Wikipedia pages, news, etc.
    """
    results: List[Dict[str, Any]] = []
    seen_names: set = set()

    # Non-POI patterns to filter out
    _SKIP_PATTERNS = [
        r"百度百科", r"维基百科", r"汉语词语", r"词典",
        r"玉溪烟", r"多少钱", r"价格", r"官网",
        r"人民政府", r"市政府", r"区委",
    ]

    # POI name patterns in list articles (Chinese list markers)
    _LIST_ITEM_PATTERNS = [
        re.compile(r"[《》]([^《》\n]{2,30})[》《]"),  # 《POI名》
        re.compile(r"[\d]+[\.\)、]\s*([^\s，,。；;\n]{2,20})"),  # 1. POI名 or 1) POI名
    ]

    result_blocks = re.findall(
        r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>',
        html,
        re.DOTALL,
    )

    if not result_blocks:
        result_blocks = re.findall(
            r'<div[^>]*class="[^"]*b_caption[^"]*"[^>]*>(.*?)</div>',
            html,
            re.DOTALL,
        )

    def _is_poi_title(title: str, desc: str) -> bool:
        """Check if a result is likely a real POI, not an article about POIs."""
        full = f"{title} {desc}"
        for pat in _SKIP_PATTERNS_COMMON:
            if re.search(pat, full):
                return False
        # Use category-specific filtering for better quality
        if not _is_likely_poi_title(title):
            return False
        # Additional category check for Bing results
        if category == "restaurants":
            return _is_wikipedia_poi(title, "restaurants")
        elif category == "attractions":
            return _is_wikipedia_poi(title, "attractions")
        return True

    def _extract_poi_names_from_text(text: str, category: str = "attractions") -> List[str]:
        """Extract POI-like names from article text."""
        names = []
        # Pattern: 《POI名》or "POI名（XXX）"
        for pat in _LIST_ITEM_PATTERNS:
            matches = pat.findall(text)
            for match in matches:
                match = match.strip()
                if 2 <= len(match) <= 30 and match not in seen_names:
                    # Skip generic words
                    if not re.match(r"^[\d\s]+$", match):
                        names.append(match)
        
        # Category-specific suffix patterns - these are more reliable
        _SUFFIX_PATTERNS = {
            "attractions": [
                r"([^\s，,。；;\n]{2,10})(?:景区|公园|风景区|湖|山|寺|庙|塔|楼|阁|广场|博物馆|纪念馆|古镇|古城|温泉|瀑布|石林|景点|洞穴)",
            ],
            "restaurants": [
                r"([^\s，,。；;\n]{2,10})(?:餐厅|饭店|酒楼|餐馆|美食|小吃|火锅|烧烤|菜馆|酒家|食府|面馆|米线|烧烤店)",
            ],
            "hotels": [
                r"([^\s，,。；;\n]{2,15})(?:酒店|旅馆|客栈|民宿|宾馆|旅店|度假村|青年旅舍|公寓)",
            ],
        }
        
        cat_patterns = _SUFFIX_PATTERNS.get(category, _SUFFIX_PATTERNS["attractions"])
        for pat in cat_patterns:
            for match in re.finditer(pat, text):
                name = match.group(1).strip()
                if 2 <= len(name) <= 15 and name not in seen_names and name not in names:
                    # More strict validation
                    if not re.search(r"[的了过在是有和与及]", name):
                        # Avoid names that look like they're part of a phrase
                        if not re.search(r"^\d", name):
                            names.append(name)
        
        return names

    # Phase 1: Extract direct POI results
    for block in result_blocks[:limit * 3]:
        title_match = re.search(r"<h[23][^>]*>(.*?)</h[23]>", block, re.DOTALL)
        if not title_match:
            title_match = re.search(
                r'<a[^>]*class="[^"]*b_attribution[^"]*"[^>]*>(.*?)</a>',
                block,
                re.DOTALL,
            )
        if not title_match:
            # Try to find the first link in the block as fallback
            title_match = re.search(r'<a[^>]*>(.*?)</a>', block, re.DOTALL)
            if not title_match:
                continue

        title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
        title = re.sub(r"\s*[-–—_].*$", "", title).strip()

        # Extract description
        desc_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.DOTALL)
        description = ""
        if desc_match:
            description = re.sub(r"<[^>]+>", "", desc_match.group(1)).strip()

        if not title or len(title) < 2 or title in seen_names:
            continue

        # Check if original title had strong article indicators
        _STRONG_ARTICLE_PATTERNS = [
            r"(攻略|推荐|必去|必吃|大全|排行|盘点|汇总)",
            r"(第\d+站|去了\d+次|打卡)",
            r"(门票价格|门票团购|门票预订)",
            r"(旅游景点|必游景点)",
            r"(值得去|此生无憾|不能错过)",
        ]
        had_article_indicators = any(
            re.search(p, title) for p in _STRONG_ARTICLE_PATTERNS
        )

        # Clean and validate the title
        cleaned_title = _clean_poi_name(title)
        if not cleaned_title or len(cleaned_title) < 2:
            continue
        if cleaned_title in seen_names:
            continue
            
        # Skip non-POI results
        if not _is_poi_title(cleaned_title, description):
            continue
        
        # Additional quality checks
        if len(cleaned_title) > 15:
            continue
        if re.search(r"[，,。.!！?？]", cleaned_title):
            continue
        if re.search(r"\d{2,}", cleaned_title):  # Avoid names with 2+ digit numbers
            continue
        
        # If original had article indicators, require the cleaned title
        # to also appear in the description (cross-validation)
        if had_article_indicators and description:
            if cleaned_title not in description:
                continue
        
        # Check if cleaned title looks like just a city/admin name
        # (2-3 chars with admin suffix, no POI context)
        admin_suffixes = ["省", "市", "区", "县", "盟", "自治州"]
        for suffix in admin_suffixes:
            if cleaned_title.endswith(suffix) and len(cleaned_title) <= 3:
                if re.match(r"^[\u4e00-\u9fff]{2,3}$", cleaned_title):
                    # If it's just an admin name without POI context,
                    # only keep if description contains POI keywords
                    if description and not any(
                        kw in description 
                        for kw in ["景区", "景点", "公园", "博物馆", "旅游", "名胜"]
                    ):
                        continue

        seen_names.add(cleaned_title)

        url_match = re.search(r'<a[^>]*href="([^"]*)"[^>]*>', block)
        source_url = url_match.group(1) if url_match else ""

        entry = _build_poi_entry(cleaned_title, description, category, source_url)
        results.append(entry)

        if len(results) >= limit:
            break

    # Phase 2: Extract POI names from list/article descriptions
    if len(results) < limit:
        for block in result_blocks[:limit * 3]:
            if len(results) >= limit:
                break
            desc_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.DOTALL)
            if not desc_match:
                continue
            description = re.sub(r"<[^>]+>", "", desc_match.group(1)).strip()
            # Extract POI names from the description text
            poi_names = _extract_poi_names_from_text(description, category=category)
            for poi_name in poi_names:
                if len(results) >= limit:
                    break
                if poi_name in seen_names:
                    continue
                
                # Validate and clean the extracted name
                cleaned = _clean_poi_name(poi_name)
                if not cleaned:
                    continue
                if cleaned in seen_names:
                    continue
                if not _is_likely_poi_title(cleaned):
                    continue
                
                # Additional quality check: names should not be too long or contain article patterns
                if len(cleaned) > 15:
                    continue
                if re.search(r"[，,。.!！?？]", cleaned):
                    continue
                if re.search(r"\d{2,}", cleaned):  # Avoid names with numbers
                    continue
                    
                seen_names.add(cleaned)
                entry = _build_poi_entry(cleaned, "", category, "")
                results.append(entry)

    return results


def _build_poi_entry(
    name: str,
    description: str,
    category: str,
    source_url: str = "",
    source: str = "bing_runtime",
) -> Dict[str, Any]:
    """Build a normalized POI entry from raw search data.
    
    Includes advanced name cleaning to remove article titles, 
    redundant suffixes, and non-POI content.
    """
    cleaned_name = _clean_poi_name(name)
    
    return {
        "name": cleaned_name,
        "description": _clean_description(description)[:300] if description else "",
        "category": category,
        "source": source,
        "source_url": source_url,
        "runtime_verified": True,
        "kb_verified": False,
        "tags": _extract_tags(cleaned_name, description, category),
        "price_range": _extract_price_from_desc(description),
        "popularity_score": 5.0,
        "fetched_at": date.today().isoformat(),
    }


def _clean_poi_name(name: str) -> str:
    """Clean POI name to remove non-POI suffixes and article patterns."""
    if not name:
        return ""
    
    clean = name.strip()
    
    # First, remove article prefix markers like 【...】 [...] 《...》
    _PREFIX_PATTERNS = [
        r"^【[^】]*】",
        r"^\[[^\]]*\]",
        r"^[《][^》]*[》]",
    ]
    for pat in _PREFIX_PATTERNS:
        clean = re.sub(pat, "", clean).strip()
    
    # Remove pipe/separator content (article format: "Article Title | POI Name")
    # Only split if the separator is clearly an article delimiter (not a label colon)
    if _RE_PIPE_SEP.search(clean):
        # Check if this looks like an article separator (not "地址：" or similar)
        # Count separators - multiple ones indicate article format
        sep_count = len(_RE_PIPE_SEP.findall(clean))
        if sep_count >= 2 or (sep_count == 1 and not re.search(r"(地址|电话|预订|官网|人均|价格|门票)[：:]", clean)):
            parts = _RE_PIPE_SEP.split(clean)
            # Take the last part if it's shorter and looks like a POI name
            candidate = parts[-1].strip()
            if 2 <= len(candidate) <= 20:
                clean = candidate
            else:
                # Try taking the first part before separator
                candidate = parts[0].strip()
                if 2 <= len(candidate) <= 20:
                    clean = candidate
    
    # Check if remaining content looks like an article title
    _ARTICLE_TITLE_PATTERNS = [
        (r"最值得去的", True),
        (r"必去的?", True),
        (r"推荐", True),
        (r"攻略", True),
        (r"大全", True),
        (r"排行", True),
        (r"地方", True),
        (r"此生无憾", True),
        (r"打卡", True),
        (r"清单", True),
        (r"旅游第\d+站", True),
    ]
    
    is_article = any(re.search(p, clean) for p, _ in _ARTICLE_TITLE_PATTERNS)
    
    if is_article:
        # Try to extract the city/POI name from the article title
        for pattern, _ in _ARTICLE_TITLE_PATTERNS:
            match = re.split(pattern, clean, maxsplit=1)
            if len(match) > 1 and len(match[0]) >= 2:
                clean = match[0].rstrip("的了过")
                break
    
    # Remove common article suffixes/prefixes (order matters)
    _REMOVE_PATTERNS = [
        r"电话[:：]?.*$",
        r"地址[:：]?.*$",
        r"预订[:：]?.*$",
        r"官网[:：]?.*$",
        r"人均[:：]?.*$",
        r"价格[:：]?.*$",
        r"门票(?:价格|团购|预订|开放)?[:：]?.*$",
        r"(?:，|,)\s*地址[:：]?.*$",
        r"(?:，|,)\s*位于.*$",
        r"[—–\-_].*$",
        r"被誉为.*$",
        r"位于.*$",
        r"的$",
    ]
    
    for pat in _REMOVE_PATTERNS:
        clean = re.sub(pat, "", clean).strip()
    
    # Remove parenthetical info using pre-compiled pattern
    clean = _RE_PARENTHETICAL.sub("", clean).strip()
    
    # Remove duplicate content (e.g., "抚仙湖抚仙湖")
    half = len(clean) // 2
    if half >= 2 and clean[:half] == clean[half:half * 2]:
        clean = clean[:half]
    
    # Clean up remaining noise
    clean = re.sub(r"\s+", " ", clean).strip()
    clean = _RE_PUNCTUATION.sub("", clean).strip()
    
    # Minimum length check
    if len(clean) < 2:
        return ""
    
    return clean


def _clean_description(desc: str) -> str:
    """Clean description text, removing article-like content."""
    if not desc:
        return ""
    
    clean = desc.strip()
    
    # Remove article markers
    _ARTICLE_MARKERS = [
        r"(?i)推荐", r"攻略", r"必去", r"必吃", r"必玩",
        r"大全", r"排行", r"盘点", r"汇总",
    ]
    
    for pat in _ARTICLE_MARKERS:
        if re.search(pat, clean):
            # If description looks like an article, truncate to first sentence
            sentences = re.split(r"[。！？!?]", clean)
            if len(sentences) > 0:
                clean = sentences[0] + "。"
                if len(clean) < 10:
                    return desc  # Keep original if truncated too much
    
    return clean


def _extract_tags(name: str, description: str, category: str) -> List[str]:
    """Extract relevant tags from POI name and description."""
    tags = [category]  # always include the category

    # Common Chinese tags
    tag_patterns = {
        "世界遗产": ["世界遗产", "世界文化遗产", "世界自然遗产"],
        "5A景区": ["5A", "AAAAA", "5A级"],
        "博物馆": ["博物馆", "纪念馆", "美术馆"],
        "古建筑": ["古建筑", "古迹", "遗址"],
        "自然风景": ["自然风景", "自然风光", "山水"],
        "主题乐园": ["乐园", "主题公园", "游乐园"],
        "寺庙": ["寺庙", "寺院", "庙", "寺"],
        "古镇": ["古镇", "古村", "古街"],
        "购物中心": ["购物", "商场", "商业街"],
        "美食": ["美食", "小吃", "餐厅", "饭馆"],
        "老字号": ["老字号", "百年老店"],
        "网红": ["网红", "打卡", "热门"],
        "免费": ["免费", "开放", "免票"],
        "亲子": ["亲子", "儿童", "适合家庭"],
        "情侣": ["情侣", "浪漫", "约会"],
    }

    text = f"{name} {description}"
    for tag, patterns in tag_patterns.items():
        if any(p in text for p in patterns):
            tags.append(tag)

    return list(set(tags))[:8]  # deduplicate, max 8 tags


def _extract_price_from_desc(description: str) -> Optional[Dict[str, int]]:
    """Extract ticket price from description text."""
    if not description:
        return None

    # Free indicators
    free_patterns = ["免费开放", "免票", "免费入园", "免费景点", "不收取门票"]
    for pat in free_patterns:
        if pat in description:
            return {"min": 0, "max": 0}

    # Price range patterns
    range_patterns = [
        r"门票\s*(\d+)\s*[-~到至]\s*(\d+)\s*元",
        r"票价\s*(\d+)\s*[-~到至]\s*(\d+)\s*元",
        r"(\d+)\s*[-~到至]\s*(\d+)\s*元\s*/\s*人",
    ]
    for pat in range_patterns:
        m = re.search(pat, description)
        if m:
            pmin, pmax = int(m.group(1)), int(m.group(2))
            if pmin <= pmax:
                return {"min": pmin, "max": pmax}

    # Single price patterns
    single_patterns = [
        r"门票\s*(\d+)\s*元",
        r"票价\s*(\d+)\s*元",
        r"(\d+)\s*元\s*/\s*人",
        r"(\d+)\s*元\s*起",
    ]
    for pat in single_patterns:
        m = re.search(pat, description)
        if m:
            price = int(m.group(1))
            return {"min": price, "max": price}

    return None


# ── Bing search implementation ────────────────────────────


async def _wikipedia_search(
    client: httpx.AsyncClient,
    city: str,
    category: str,
    limit: int = _DEFAULT_LIMIT,
) -> List[Dict[str, Any]]:
    """Search Wikipedia for POIs in a city.
    
    Wikipedia provides high-quality, structured POI data for attractions,
    restaurants, and hotels. This is the preferred data source.
    """
    config = _POI_CATEGORIES.get(category, {})
    label = config.get("label", category)
    
    # Search patterns for different categories
    search_queries = []
    if category == "attractions":
        search_queries = [
            f"{city} 地标",
            f"{city} 景点",
            f"{city} 旅游",
        ]
    elif category == "restaurants":
        search_queries = [
            f"{city} 美食",
            f"{city} 餐厅",
            f"{city} 小吃",
        ]
    elif category == "hotels":
        search_queries = [
            f"{city} 酒店",
            f"{city} 住宿",
            f"{city} 客栈",
        ]
    else:
        search_queries = [f"{city} {label}"]
    
    results: List[Dict[str, Any]] = []
    seen_names: set = set()
    
    for query in search_queries[:2]:  # Limit to 2 queries to avoid rate limiting
        try:
            params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": min(limit * 2, 50),
                "format": "json",
                "utf8": "1",
            }
            
            resp = await client.get(
                _WIKIPEDIA_API,
                params=params,
                timeout=_WIKIPEDIA_TIMEOUT,
                headers={
                    "Accept": "application/json",
                    "User-Agent": _WIKIPEDIA_UA,
                },
            )
            
            if resp.status_code != 200:
                continue
            
            data = resp.json()
            search_results = data.get("query", {}).get("search", [])
            
            for item in search_results:
                title = item.get("title", "").strip()
                snippet = item.get("snippet", "")
                
                # Clean HTML tags from snippet
                snippet = re.sub(r"<[^>]+>", "", snippet)
                
                # Skip if title contains non-POI patterns
                if not _is_wikipedia_poi(title, category, snippet):
                    continue
                
                # Extract description from snippet
                description = _extract_from_wikipedia_snippet(snippet, title)
                
                if title not in seen_names and len(results) < limit:
                    seen_names.add(title)
                    # Build POI entry with Wikipedia source
                    entry = _build_poi_entry(
                        title, description, category,
                        source_url=f"https://zh.wikipedia.org/wiki/{quote(title)}",
                        source="wikipedia"
                    )
                    results.append(entry)
                    
        except Exception as e:
            logger.debug(f"Wikipedia search error for '{query}': {e}")
            continue
    
    # Also try to get city overview page and extract landmarks
    if len(results) < limit and category == "attractions":
        try:
            # Get the city's Wikipedia page
            city_params = {
                "action": "parse",
                "page": city,
                "prop": "links",
                "pllimit": 50,
                "format": "json",
                "utf8": "1",
            }
            
            resp = await client.get(
                _WIKIPEDIA_API,
                params=city_params,
                timeout=_WIKIPEDIA_TIMEOUT,
                headers={"User-Agent": _WIKIPEDIA_UA},
            )
            
            if resp.status_code == 200:
                data = resp.json()
                links = data.get("parse", {}).get("links", [])
                
                for link in links:
                    link_title = link.get("*", "")
                    if _is_wikipedia_poi(link_title, category):
                        if link_title not in seen_names and len(results) < limit:
                            seen_names.add(link_title)
                            results.append(_build_poi_entry(
                                link_title, "", category,
                                source_url=f"https://zh.wikipedia.org/wiki/{quote(link_title)}",
                                source="wikipedia"
                            ))
        except Exception as e:
            logger.debug(f"Wikipedia city parse error for '{city}': {e}")
    
    return results


def _is_wikipedia_poi(title: str, category: str, snippet: str = "") -> bool:
    """Check if a Wikipedia title is likely a POI of the requested category."""
    if not title or len(title) < 2:
        return False
    
    # Skip non-POI patterns (banks, products, institutions, etc.)
    skip_patterns = [
        r"^List of",
        r"^Category:",
        r"^Template:",
        r"^Wikipedia:",
        r"^File:",
        r"^Module:",
        r"^Draft:",
        r"(消歧义)",
        r"^Main_Page",
        r"银行", r"香烟", r"卷烟", r"烟草",
        r"大学", r"学院", r"医院", r"学校",
        r"政府", r"公司", r"集团", r"协会",
        r"厂$", r"工厂", r"企业", r"股份",
        r"联赛", r"比赛", r"足球", r"篮球", r"排球",
        r"列表", r"List", r"年鉴", r"统计",
    ]
    
    for pat in skip_patterns:
        if re.search(pat, title, re.IGNORECASE):
            return False
    
    # If snippet is available, check for person indicators
    if snippet and category == "restaurants":
        person_indicators = [
            "演员", "电影", "电视剧", "导演", "出生", "逝世",
            "人物", "歌手", "明星", "艺人", "编剧",
        ]
        if any(ind in snippet for ind in person_indicators):
            return False
    
    # Category-specific validation
    if category == "attractions":
        attraction_keywords = [
            "景区", "景点", "公园", "博物馆", "纪念馆", "塔", "寺", "庙",
            "楼", "阁", "桥", "故居", "遗址", "广场", "古城", "古镇",
            "乐园", "水族馆", "动物园", "植物园", "温泉", "瀑布",
            "湖", "山", "海", "沙滩", "岛", "石林",
            "风景名胜", "旅游区", "自然保护区", "世界遗产",
            "石窟", "石刻", "壁画", "陵园", "墓园",
            "城", "坛", "关", "塞", "窟", "洞",
            "宫", "殿", "府", "堂", "庄", "园",
            "峡", "谷", "沟", "泉", "潭",
            "遗址", "遗迹", "旧址",
            "化石", "俑",
        ]
        # Accept if title contains attraction keywords
        if any(kw in title for kw in attraction_keywords):
            return True
        # For short titles without keywords, check landmark suffixes
        if 2 <= len(title) <= 12:
            landmark_suffixes = [
                "府", "宫", "殿", "堂", "庄", "园", "苑",
                "阁", "楼", "台", "亭",
                "洞", "窟", "峡", "谷",
            ]
            if any(title.endswith(s) for s in landmark_suffixes):
                return True
        # Special case: known attraction names without explicit keywords
        _KNOWN_ATTRACTIONS = [
            "草原", "沙漠", "森林", "冰川",
        ]
        for att in _KNOWN_ATTRACTIONS:
            if att in title and len(title) > len(att):
                # Must have a location modifier (e.g., "呼伦贝尔草原")
                return True
        return False
        
    elif category == "restaurants":
        restaurant_keywords = [
            "餐厅", "饭店", "酒楼", "餐馆", "美食", "小吃",
            "咖啡", "酒吧", "茶馆", "火锅", "烧烤", "料理",
            "菜馆", "酒家", "食府", "快餐",
            "烤鸭", "饭庄", "名吃", "老字号", "特色",
            "米线", "盖浇饭", "铁板", "自助", "素食",
            "面馆", "饼", "饺", "包子", "馄饨",
        ]
        if any(kw in title for kw in restaurant_keywords):
            return True
        # Accept titles with restaurant-like suffixes
        restaurant_suffixes = [
            "楼", "堂", "庄", "苑", "阁", "轩", "居", "记",
            "饭庄", "菜馆", "食府", "酒楼", "店", "坊", "铺",
        ]
        if any(title.endswith(s) for s in restaurant_suffixes):
            return True
        # Restaurant-specific negative patterns
        restaurant_skip = [
            r"站$",
            r"墓园", r"墓地", r"陵园",
            r"宅$", r"宅邸", r"舍$",
            r"故居",
            r"大桥$", r"桥$",
            r"公园$", r"广场$",
            r"雕像$", r"塑像$", r"纪念碑$",
            r"医院$", r"诊所$", r"学校$",
            r"图书馆", r"博物馆", r"档案馆",
            r"谈判", r"旧址", r"遗迹",
            r"道$", r"省$", r"市$", r"县$", r"区$",
            r"联赛", r"比赛", r"足球", r"篮球",
            r"电视", r"电影", r"广播",
            r"银行", r"香烟", r"卷烟", r"烟草",
            r"大学", r"学院", r"政府", r"公司",
            r"工厂", r"企业", r"股份",
        ]
        for pat in restaurant_skip:
            if re.search(pat, title):
                return False
        # Accept known restaurant/fast-food brands (check snippet for context)
        _RESTAURANT_BRANDS = [
            "麦当劳", "肯德基", "全聚德", "东来顺", "鼎泰丰",
            "海底捞", "小龙坎", "巴奴", "呷哺呷哺",
            "星巴克", "瑞幸", "必胜客", "塔可钟",
            "汉堡王", "赛百味", "达美乐",
            "杨国福", "张亮", "老乡鸡", "真功夫",
            "杏花楼", "绿波廊", "南翔", "小杨生煎",
            "鼎泰丰", "聚春园", "楼外楼", "知味观",
            "狗不理", "陶然亭", "南门涮肉",
            "沙县小吃", "兰州拉面", "重庆小面",
            "外婆家", "绿茶餐厅", "新白鹿",
        ]
        for brand in _RESTAURANT_BRANDS:
            if brand in title:
                return True
        # Stricter fallback: require food evidence in title or snippet
        food_chars = "食味香鲜餐饮酒茶饭菜肉鱼面点糕饼饺包汤粥面火烤炸蒸煮炖焖烧酸甜麻辣鲜香"
        if any(c in food_chars for c in title):
            return True
        # If snippet available, check for food context
        if snippet:
            snippet_food = ["菜", "吃", "美食", "特色", "招牌", "推荐", "必尝",
                           "火锅", "烧烤", "小吃", "面食", "中餐", "西餐",
                           "快餐", "连锁", "品牌", "餐饮", "料理", "主厨"]
            if any(ind in snippet for ind in snippet_food):
                return True
        return False
        
    elif category == "hotels":
        hotel_keywords = [
            "酒店", "旅馆", "客栈", "民宿", "宾馆", "旅店",
            "度假村", "公寓", "青年旅舍", "连锁",
        ]
        return any(kw in title for kw in hotel_keywords)
    
    return True


def _extract_from_wikipedia_snippet(snippet: str, title: str) -> str:
    """Extract a clean description from Wikipedia snippet HTML."""
    if not snippet:
        return ""
    
    # The snippet may have <span class="searchmatch"> tags around matched text
    # Remove these but keep the text
    desc = re.sub(r"<[^>]+>", "", snippet)
    desc = desc.strip()
    
    # If description is too short, return empty
    if len(desc) < 15:
        return ""
    
    # If description is too long, truncate to first sentence
    if len(desc) > 100:
        sentences = re.split(r"[。！？!?]", desc)
        if sentences and len(sentences[0]) > 10:
            desc = sentences[0] + "。"
    
    return desc


async def _bing_search(
    client: httpx.AsyncClient,
    city: str,
    category: str,
    limit: int = _DEFAULT_LIMIT,
) -> List[Dict[str, Any]]:
    """Search Bing for POIs in a city, with Sogou fallback."""
    async with _BING_SEM:
        config = _POI_CATEGORIES.get(category, {})
        search_suffix = config.get("bing_suffix", "景点")
        search_term = f"{city} {search_suffix}"
        encoded = quote(search_term)

        results: List[Dict[str, Any]] = []

        # Try Bing first
        try:
            url = f"https://cn.bing.com/search?q={encoded}"
            resp = await client.get(
                url, headers=_BING_HEADERS, follow_redirects=True, timeout=_BING_TIMEOUT,
            )
            if resp.status_code == 200:
                html = resp.text
                results = _parse_bing_results(html, category, limit)
        except Exception as e:
            logger.debug(f"Bing search error ({city}/{category}): {e}")

        # If Bing returns too few real POIs, try Sogou
        real_count = sum(1 for r in results if _is_likely_poi_title(r.get("name", "")))
        if real_count < 3:
            logger.info(
                f"Bing returned {len(results)} results ({real_count} real POIs), "
                f"trying Sogou for {city}/{category}"
            )
            sogou_results = await _sogou_search(client, city, category, limit)
            # Merge, prefer real POIs
            seen = {r["name"] for r in results}
            for sr in sogou_results:
                if sr["name"] not in seen:
                    results.append(sr)
                    seen.add(sr["name"])

        # Supplement with search links if still too few
        if len(results) < limit:
            link_pois = _generate_search_link_pois(city, category, limit - len(results))
            results.extend(link_pois)

        # Final cleanup: filter out low-quality results
        cleaned = []
        seen_final = set()
        for r in results:
            name = r.get("name", "")
            src = r.get("source", "")
            if src == "search_link":
                # Always keep search links
                cleaned.append(r)
                continue
            if not _is_likely_poi_title(name):
                continue
            # Remove very short or obviously wrong names
            if name in seen_final:
                continue
            seen_final.add(name)
            cleaned.append(r)

        # Apply category-specific filtering to differentiate POI types
        cleaned = _filter_by_category(cleaned, category)

        # If after cleanup we still have < 3 real results, add search links
        real_count = sum(1 for r in cleaned if r.get("source") != "search_link")
        link_count = sum(1 for r in cleaned if r.get("source") == "search_link")
        if real_count < 3 and link_count == 0:
            needed = max(0, 3 - real_count)
            link_pois = _generate_search_link_pois(city, category, needed)
            cleaned.extend(link_pois)

        return cleaned


async def _sogou_search(
    client: httpx.AsyncClient,
    city: str,
    category: str,
    limit: int = _DEFAULT_LIMIT,
) -> List[Dict[str, Any]]:
    """Search Sogou for a city's POIs — better Chinese content coverage."""
    config = _POI_CATEGORIES.get(category, {})
    search_suffix = config.get("bing_suffix", "景点")
    search_term = f"{city} {search_suffix}"
    encoded = quote(search_term)

    try:
        url = f"https://www.sogou.com/web?query={encoded}"
        headers = {**_BING_HEADERS, "Referer": "https://www.sogou.com/"}
        resp = await client.get(url, headers=headers, follow_redirects=True, timeout=_BING_TIMEOUT)
        if resp.status_code != 200:
            return []
        return _parse_sogou_results(resp.text, category, limit)
    except Exception as e:
        logger.debug(f"Sogou search error ({city}/{category}): {e}")
        return []


def _parse_sogou_results(html: str, category: str, limit: int) -> List[Dict[str, Any]]:
    """Parse Sogou search results to extract POI names."""
    results: List[Dict[str, Any]] = []
    seen_names: set = set()

    result_blocks = re.findall(
        r'<div[^>]*class="[^"]*vrwrap[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL,
    )
    if not result_blocks:
        result_blocks = re.findall(
            r'<div[^>]*class="[^"]*rb[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL,
        )

    _SKIP_PATTERNS = [
        r"百度百科", r"维基百科", r"汉语词语", r"词典",
        r"人民政府", r"市政府", r"官方网站",
    ]

    for block in result_blocks[:limit * 3]:
        title_match = re.search(r"<h3[^>]*>(.*?)</h3>", block, re.DOTALL)
        if not title_match:
            title_match = re.search(r'<a[^>]*href="[^"]*"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not title_match:
            continue

        title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
        title = re.sub(r"\s*[-–—_].*$", "", title).strip()

        if not title or len(title) < 2 or title in seen_names:
            continue

        desc_match = re.search(
            r'<p[^>]*class="[^"]*str_info[^"]*"[^>]*>(.*?)</p>', block, re.DOTALL,
        )
        if not desc_match:
            desc_match = re.search(r"<p[^>]*>(.*?)</p>", block, re.DOTALL)
        description = ""
        if desc_match:
            description = re.sub(r"<[^>]+>", "", desc_match.group(1)).strip()

        full_text = f"{title} {description}"
        if any(re.search(p, full_text) for p in _SKIP_PATTERNS_COMMON):
            continue
        if not _is_likely_poi_title(title):
            continue

        seen_names.add(title)
        results.append(_build_poi_entry(title, description, category, ""))

        if len(results) >= limit:
            break

    # Phase 2: Extract POI names from description text
    if len(results) < limit:
        _extract_names_from_descriptions(html, results, seen_names, category, limit)

    return results


def _extract_names_from_descriptions(
    html: str,
    results: List[Dict[str, Any]],
    seen_names: set,
    category: str,
    limit: int,
) -> None:
    """Extract POI-like names from search result descriptions."""
    snippets = re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL)
    _SKIP_WORDS = {"推荐", "攻略", "景点", "美食", "酒店", "必去", "必吃", "热门", "旅游", "大全", "门票", "价格", "预订", "团购", "优惠", "免费"}

    for snippet in snippets:
        if len(results) >= limit:
            break
        text = re.sub(r"<[^>]+>", "", snippet).strip()
        if not text or len(text) < 10:
            continue

        # 《name》pattern
        for match in re.finditer(r"[《]([^《》\n]{2,30})[》]", text):
            name = match.group(1).strip()
            if name not in seen_names and 2 <= len(name) <= 30 and name not in _SKIP_WORDS:
                seen_names.add(name)
                results.append(_build_poi_entry(name, "", category, ""))
                if len(results) >= limit:
                    return

        # Numbered list patterns: 1. name, 2) name, 3、name
        for match in re.finditer(r"[\d]+[\.\)、]\s*([^\s，,。；;\n]{2,20})", text):
            name = match.group(1).strip()
            if name not in seen_names and 2 <= len(name) <= 20:
                if not re.match(r"^[\d\s]+$", name) and name not in _SKIP_WORDS:
                    seen_names.add(name)
                    results.append(_build_poi_entry(name, "", category, ""))
                    if len(results) >= limit:
                        return

        # name（desc）or name(desc) pattern
        for match in re.finditer(r"([^\s，,。；;\n]{2,15})[（(][^）)]{2,30}[）)]", text):
            name = match.group(1).strip()
            if name not in seen_names and 2 <= len(name) <= 15 and name not in _SKIP_WORDS:
                seen_names.add(name)
                results.append(_build_poi_entry(name, "", category, ""))
                if len(results) >= limit:
                    return

        # "name位于" or "name被誉为" or "name地处" pattern
        for match in re.finditer(r"([^\s，,。；;\n]{2,15})(?:位于|地处|坐落|被誉为|是|在)", text):
            name = match.group(1).strip()
            if name not in seen_names and 2 <= len(name) <= 15 and name not in _SKIP_WORDS:
                # Check if it looks like a real name (not a clause)
                if not re.search(r"[的了过]", name):
                    seen_names.add(name)
                    results.append(_build_poi_entry(name, "", category, ""))
                    if len(results) >= limit:
                        return

        # Category-specific patterns
        if category == "attractions":
            # "name景区" or "name公园" or "name湖" or "name山"
            for match in re.finditer(r"([^\s，,。；;\n]{2,10})(?:景区|公园|风景区|湖|山|寺|庙|塔|楼|阁|广场|博物馆|纪念馆|古镇|古城|温泉|瀑布|石林)", text):
                name = match.group(1).strip()
                if name not in seen_names and 2 <= len(name) <= 10 and name not in _SKIP_WORDS:
                    seen_names.add(name)
                    results.append(_build_poi_entry(name, "", category, ""))
                    if len(results) >= limit:
                        return
        elif category == "restaurants":
            # "name餐厅" or "name饭店" or "name美食"
            for match in re.finditer(r"([^\s，,。；;\n]{2,10})(?:餐厅|饭店|酒楼|餐馆|美食|小吃|火锅|烧烤|菜馆|酒家)", text):
                name = match.group(1).strip()
                if name not in seen_names and 2 <= len(name) <= 10 and name not in _SKIP_WORDS:
                    seen_names.add(name)
                    results.append(_build_poi_entry(name, "", category, ""))
                    if len(results) >= limit:
                        return
        elif category == "hotels":
            # "name酒店" or "name客栈" or "name民宿" or "name宾馆"
            for match in re.finditer(r"([^\s，,。；;\n]{2,15})(?:酒店|旅馆|客栈|民宿|宾馆|旅店|度假村)", text):
                name = match.group(1).strip()
                if name not in seen_names and 2 <= len(name) <= 15 and name not in _SKIP_WORDS:
                    seen_names.add(name)
                    results.append(_build_poi_entry(name, "", category, ""))
                    if len(results) >= limit:
                        return


def _generate_search_link_pois(
    city: str,
    category: str,
    count: int,
) -> List[Dict[str, Any]]:
    """Generate POI entries backed by search links for user self-service."""
    config = _POI_CATEGORIES.get(category, {})
    label = config.get("label", category)
    search_term = f"{city} {label}"
    encoded = quote(search_term)

    platforms = [
        ("ctrip", f"https://piao.ctrip.com/search?q={encoded}", f"携程{label}"),
        ("trip", f"https://www.trip.com/search?q={encoded}", f"Trip.com{label}"),
        ("dianping", f"https://www.dianping.com/search/keyword/{encoded}", f"大众点评{label}"),
        ("baidu", f"https://www.baidu.com/s?wd={encoded}", f"百度{label}"),
    ]

    results = []
    for i, (platform, url, display_name) in enumerate(platforms[:count]):
        results.append({
            "name": f"[搜索链接] {display_name}",
            "description": f"点击查看{city}{label}真实{platform}数据",
            "category": category,
            "source": "search_link",
            "source_url": url,
            "runtime_verified": False,
            "kb_verified": False,
            "tags": [category, "search_link"],
            "price_range": None,
            "price_source": "",
            "popularity_score": 0.0,
            "city": city,
        })
    return results


# ── Amap POI API (when key available) ─────────────────────

_AMAP_KEY_CACHED: Optional[str] = None


def _get_amap_key() -> str:
    """Lazy-load Amap API key from environment."""
    global _AMAP_KEY_CACHED
    if _AMAP_KEY_CACHED is not None:
        return _AMAP_KEY_CACHED
    _AMAP_KEY_CACHED = os.environ.get("AMAP_KEY", "")
    return _AMAP_KEY_CACHED


async def _amap_poi_search(
    client: httpx.AsyncClient,
    city: str,
    category: str,
    limit: int = _DEFAULT_LIMIT,
) -> List[Dict[str, Any]]:
    """Search Amap POI API for a city's attractions/restaurants/hotels.

    Requires AMAP_KEY env variable. This provides the most authoritative
    Chinese POI data including exact coordinates, prices, and ratings.
    """
    if not _get_amap_key():
        return []

    config = _POI_CATEGORIES.get(category, {})
    type_code = {
        "attractions": "141200|141300|141400|141500",  # scenic spots
        "restaurants": "050000",  # food & beverage
        "hotels": "100100|100200",  # hotels
    }.get(category, "141200")

    url = "https://restapi.amap.com/v3/place/text"
    params = {
        "key": _get_amap_key(),
        "keywords": config.get("label", category),
        "city": city,
        "type": type_code,
        "offset": min(limit, 20),
        "page": 1,
        "extensions": "all",
    }

    try:
        resp = await client.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return []

        data = resp.json()
        if data.get("status") != "1":
            return []

        pois = data.get("pois", [])
        results = []
        for poi in pois[:limit]:
            entry = {
                "name": poi.get("name", ""),
                "description": poi.get("address", "") or "",
                "category": category,
                "source": "amap_api",
                "source_url": f"https://uri.amap.com/detail?poiid={poi.get('id', '')}",
                "amap_id": poi.get("id", ""),
                "runtime_verified": True,
                "kb_verified": False,
                "tags": [category],
                "price_range": None,
                "popularity_score": float(poi.get("biz_ext", {}).get("rating", "5") or 5),
                "lat": poi.get("location", "").split(",")[0] if poi.get("location") else None,
                "lng": poi.get("location", "").split(",")[1] if poi.get("location") and "," in poi.get("location", "") else None,
                "fetched_at": date.today().isoformat(),
            }
            if entry["name"]:
                results.append(entry)

        return results

    except Exception as e:
        logger.debug(f"Amap API error ({city}/{category}): {e}")
        return []


# ── Trip.com API (placeholder) ───────────────────────────

_TRIP_API_KEY = os.environ.get("TRIP_API_KEY", "")


async def _trip_poi_search(
    client: httpx.AsyncClient,
    city: str,
    category: str,
    limit: int = _DEFAULT_LIMIT,
) -> List[Dict[str, Any]]:
    """Search Trip.com Open API for POIs.

    Requires TRIP_API_KEY from https://open.trip.com/ttd
    """
    if not _TRIP_API_KEY:
        return []

    # Only supports attractions for now
    if category != "attractions":
        return []

    try:
        url = "https://open.trip.com/v2/search/attractions"
        headers = {
            "Authorization": f"Bearer {_TRIP_API_KEY}",
            "Content-Type": "application/json",
        }
        params = {"keyword": city, "language": "zh-CN", "limit": limit}

        resp = await client.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            return []

        data = resp.json()
        attractions = data.get("data", {}).get("attractions", [])
        results = []
        for attr in attractions[:limit]:
            ticket = attr.get("ticket", {})
            entry = {
                "name": attr.get("name", ""),
                "description": attr.get("description", "") or "",
                "category": category,
                "source": "trip_api",
                "source_url": attr.get("url", ""),
                "runtime_verified": True,
                "kb_verified": False,
                "tags": attr.get("tags", []) or [category],
                "price_range": {
                    "min": ticket.get("min_price", 0),
                    "max": ticket.get("max_price", ticket.get("min_price", 0)),
                } if ticket.get("min_price", 0) > 0 else (
                    {"min": 0, "max": 0} if ticket.get("free", False) else None
                ),
                "popularity_score": float(attr.get("rating", 5) or 5),
                "fetched_at": date.today().isoformat(),
            }
            if entry["name"]:
                results.append(entry)

        return results

    except Exception as e:
        logger.debug(f"Trip API error ({city}/{category}): {e}")
        return []


# ── Main runtime POI search ────────────────────────────────


# ── P0-3: Runtime POI quality filter ──────────────────────

# Dish / fake POI indicators
_DISH_CHARS = set("面条粉饺粥饭肠饼鸡鱼牛肉丝包卷丸串糕糊羹酱汤烧炖炒炸蒸煮烤卤")
_RESTAURANT_INDICATORS = set(["店", "楼", "馆", "记", "坊", "街", "铺",
                               "府", "居", "轩", "阁", "堂", "山庄",
                               "餐厅", "酒楼", "饭庄", "食堂", "大排档", "小吃", "食府"])
_HOTEL_INDICATORS = set(["酒店", "宾馆", "旅馆", "客栈", "民宿", "旅舍", "住宿",
                         "连锁", "如家", "锦江", "7天", "汉庭", "速8", "假日", "万豪", "希尔顿"])
_FAKE_EXACT_NAMES = set(["蔡瀾", "蔡澜", "豫菜", "唐朝", "宋朝", "明朝", "清朝",
                         "食街", "美食街", "青年旅舍", "酒店", "北海",
                         "黄山", "华山", "泰山"])  # City-name-as-POI patterns


def _filter_runtime_pois(items: List[Dict[str, Any]], category: str) -> List[Dict[str, Any]]:
    """Filter fake/low-quality runtime POIs before ingestion.

    P0-3 fix: Removes entries that are:
    - Dish names without restaurant context (e.g., "牛肉面" not "XX牛肉面店")
    - Dynasty/person names misclassified as restaurants
    - TV shows, songs, article titles
    - Generic names like "酒店", "食街"
    """
    if not items:
        return items

    filtered: List[Dict[str, Any]] = []
    for item in items:
        name = item.get("name", "").strip()
        if not name or len(name) < 2:
            continue

        # Exact match against known fake names
        if name in _FAKE_EXACT_NAMES and category != "attractions":
            continue

        # Restaurant filtering: dish names without restaurant indicators
        if category == "restaurants":
            has_dish = any(c in name for c in _DISH_CHARS)
            has_rest = any(x in name for x in _RESTAURANT_INDICATORS)
            if has_dish and not has_rest and len(name) <= 6:
                continue  # Pure dish name, not a restaurant
            # Also filter known bad entries
            bad_restaurants = ["老友粉", "牛肉面", "牛杂面", "浆面条", "冰粉",
                               "米线", "刀削面", "炸酱面", "螺蛳粉", "酸辣粉",
                               "肠粉", "煎饺", "小籠包", "雞卷", "新疆椒麻鸡",
                               "肉臊", "芙蓉燒包", "缸子肉", "鼎边糊",
                               "沟帮子熏鸡"]
            if name in bad_restaurants:
                continue

        # Hotel filtering: non-hotel names
        if category == "hotels":
            has_hotel = any(x in name for x in _HOTEL_INDICATORS)
            if not has_hotel and len(name) < 4 and name not in _FAKE_EXACT_NAMES:
                # Short non-hotel names are suspicious
                has_location = any(x in name for x in ["路", "街", "大道", "广场", "中心"])
                if not has_location:
                    continue

        filtered.append(item)

    return filtered


async def search_city_pois(
    city: str,
    categories: Optional[List[str]] = None,
    limit_per_category: int = _DEFAULT_LIMIT,
    use_cache: bool = True,
) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """Search for POIs in ANY city at runtime.

    This is the MAIN entry point for runtime POI discovery.
    It implements a cascading strategy:
      1. Check local cache (7-day TTL)
      2. Try Amap POI API (if key available)
      3. Try Wikipedia API (high-quality, structured data)
      4. Try Trip.com API (if key available, attractions only)
      5. Try Bing search (works without API key)
      6. Return results with metadata about their source

    Args:
        city: The city name (e.g., "昆明", "丽江", "三亚").
        categories: POI types to search. Default: all 3 categories.
        limit_per_category: Max results per category.
        use_cache: Whether to use local cache.

    Returns:
        Dict of category → { "items": [...], "search_links": [...] }.
        Items are real POIs; search_links are fallback URLs for user self-service.
    """
    if not categories:
        categories = ["attractions", "restaurants", "hotels"]

    results: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    proxy_client: Optional[httpx.AsyncClient] = None
    try:
        async with _build_httpx_client(timeout=15, use_proxy=False) as direct_client:
            for category in categories:
                all_items: List[Dict[str, Any]] = []

                # Check cache
                if use_cache:
                    cached = _get_cached(city, category)
                    if cached is not None:
                        cached["cached"] = True
                        all_items = cached.get("items", [])
                        real_pois, search_links = _separate_search_links(all_items)
                        results[category] = {
                            "items": real_pois,
                            "search_links": search_links,
                        }
                        continue

                # Try sources in order of preference
                items: List[Dict[str, Any]] = []
                source_used = "fallback"

                # 1. Try Amap API (best data quality, requires key) — direct
                items = await _amap_poi_search(direct_client, city, category, limit_per_category)
                if items:
                    source_used = "amap_api"

                # 2. Try Wikipedia API — needs proxy
                if not items:
                    if proxy_client is None:
                        proxy_client = _build_httpx_client(timeout=15, use_proxy=True)
                    wiki_items = await _wikipedia_search(proxy_client, city, category, limit_per_category)
                    if wiki_items:
                        items = wiki_items
                        source_used = "wikipedia"

                # 3. Try Trip.com API — needs proxy
                if not items and category == "attractions":
                    if proxy_client is None:
                        proxy_client = _build_httpx_client(timeout=15, use_proxy=True)
                    items = await _trip_poi_search(proxy_client, city, category, limit_per_category)
                    if items:
                        source_used = "trip_api"

                # 4. Try Bing search — always supplement if below limit
                if len(items) < limit_per_category:
                    bing_items = await _bing_search(direct_client, city, category, limit_per_category)
                    if not items:
                        items = bing_items
                        source_used = "bing"
                    elif bing_items:
                        # Merge Wikipedia + Bing results for better coverage
                        seen_names = {i["name"] for i in items}
                        for bi in bing_items:
                            if bi["name"] not in seen_names and len(items) < limit_per_category:
                                items.append(bi)
                                seen_names.add(bi["name"])

                # Add source metadata
                for item in items:
                    item["query_source"] = source_used
                    item["city"] = city

                # P0-3 fix: Filter fake/low-quality runtime POIs
                items = _filter_runtime_pois(items, category)

                # Separate real POIs from search_link fallbacks
                real_pois, search_links = _separate_search_links(items)

                results[category] = {
                    "items": real_pois,
                    "search_links": search_links,
                }

                # Cache the raw results (before separation, for reuse)
                _set_cached(city, category, {
                    "items": items,
                    "source": source_used,
                    "cached_at": date.today().isoformat(),
                })
    finally:
        if proxy_client is not None:
            await proxy_client.aclose()

    return results


# ── Hybrid POI pool (static KB + runtime) ──────────────────


async def get_hybrid_poi_pool(
    city: str,
    categories: Optional[List[str]] = None,
    limit_per_category: int = _DEFAULT_LIMIT,
) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """Get POIs for a city using hybrid static+runtime strategy.

    Strategy:
      1. If city is in static KB → use KB data as primary source
      2. If city is NOT in KB → trigger runtime API query
      3. For KB cities, also supplement with runtime POIs if KB coverage is thin

    This ensures ANY city in China can provide POI data.

    Returns:
        Dict of category → { "items": [...], "search_links": [...] }.
    """
    if not categories:
        categories = ["attractions", "restaurants", "hotels"]

    kb_in_cities = is_city_in_kb(city)

    if kb_in_cities:
        # City is in static KB — use KB as primary, supplement with runtime
        from app.agents.planning_agent import _get_kb_attractions

        kb_attractions = await _get_kb_attractions()
        city_kb = [a for a in kb_attractions if a.get("city", "") == city]

        pool: Dict[str, List[Dict[str, Any]]] = {
            "attractions": [],
            "restaurants": [],
            "hotels": [],
        }

        for attr in city_kb:
            cat = "attractions"
            tags = attr.get("tags", []) or []
            if isinstance(tags, str):
                tags_lower = tags.lower()
            else:
                tags_lower = " ".join(tags).lower()

            if any(w in tags_lower for w in ["餐厅", "美食", "小吃", "food"]):
                cat = "restaurants"
            elif any(w in tags_lower for w in ["酒店", "住宿", "hotel"]):
                cat = "hotels"

            entry = {
                "name": attr.get("name", ""),
                "description": attr.get("description", "") or "",
                "category": cat,
                "source": "kb",
                "source_url": "",
                "kb_verified": True,
                "runtime_verified": False,
                "tags": attr.get("tags", []) or [cat],
                "price_range": attr.get("price_range"),
                "price_source": attr.get("price_source", ""),
                "price_verifiable": attr.get("price_verifiable", False),
                "price_updated_at": attr.get("price_updated_at", ""),
                "popularity_score": attr.get("popularity_score", 5.0),
                "internal_rating": attr.get("internal_rating", 3.0),
                "data_quality": attr.get("data_quality", {"reliability": "medium"}),
                "city": city,
                "amap_id": attr.get("amap_id", ""),
                "wiki_article": attr.get("wiki_article", ""),
                "wiki_article_en": attr.get("wiki_article_en", ""),
                "thumbnail_url": attr.get("thumbnail_url", ""),
                "lat": attr.get("lat", 0),
                "lon": attr.get("lon", 0),
                "address": attr.get("address", ""),
                "price_level": attr.get("price_level", "付费"),
                "suitable_for": attr.get("suitable_for", ""),
                "best_time": attr.get("best_time", ""),
                "description_quality": attr.get("description_quality", ""),
                "description_source": attr.get("description_source", ""),
                "name_normalized": attr.get("name_normalized", attr.get("name", "")),
            }
            pool.setdefault(cat, []).append(entry)

        # If KB has few entries, supplement with runtime queries
        all_search_links: Dict[str, List[Dict[str, Any]]] = {}
        for cat in categories:
            if len(pool.get(cat, [])) < 5:
                logger.info(f"Supplementing {city} {cat} with runtime query (KB only has {len(pool.get(cat, []))})")
                runtime = await search_city_pois(city, [cat], limit_per_category)
                cat_data = runtime.get(cat, {})
                runtime_items = cat_data.get("items", [])
                cat_links = cat_data.get("search_links", [])
                
                # Store search links
                if cat_links:
                    all_search_links[cat] = cat_links
                
                # Merge real POIs, dedup by name
                existing_names = {e["name"] for e in pool.get(cat, [])}
                for r in runtime_items:
                    if r["name"] not in existing_names:
                        r["source"] = r.get("source", "bing_runtime")
                        r["runtime_verified"] = True
                        r["kb_verified"] = False
                        pool.setdefault(cat, []).append(r)
                        existing_names.add(r["name"])

        # Format return with separated search links
        result: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for cat in categories:
            result[cat] = {
                "items": pool.get(cat, [])[:limit_per_category],
                "search_links": all_search_links.get(cat, []),
            }
        return result

    else:
        # City NOT in static KB — full runtime query
        logger.info(f"City '{city}' not in static KB, triggering runtime POI query")
        return await search_city_pois(city, categories, limit_per_category)


# ── Search links for user self-service ─────────────────────


def generate_city_search_links(city: str) -> Dict[str, Dict[str, str]]:
    """Generate multi-platform search links for a city's POIs.

    When runtime queries can't get enough data, these links let the
    user search directly on major platforms.
    """
    links: Dict[str, Dict[str, str]] = {}
    for cat_key, cat_info in _POI_CATEGORIES.items():
        label = cat_info["label"]
        search = f"{city} {label}"
        encoded = quote(search)
        links[cat_key] = {
            "ctrip": f"https://piao.ctrip.com/search?q={encoded}",
            "fliggy": f"https://s.alitrip.com/search_union.htm?keyword={encoded}",
            "dianping": f"https://www.dianping.com/search/keyword/{encoded}",
            "baidu": f"https://www.baidu.com/s?wd={encoded}",
            "bing": f"https://cn.bing.com/search?q={encoded}",
        }
    return links


# ── Cache management ──────────────────────────────────────


def get_poi_cache_stats() -> Dict[str, Any]:
    """Get statistics about the POI cache."""
    cache = _load_cache()
    now = time.time()
    active = 0
    expired = 0
    sources: Dict[str, int] = {}
    for key, entry in cache.items():
        ts = entry.get("timestamp", 0)
        if now - ts > _CACHE_TTL_SECONDS:
            expired += 1
        else:
            active += 1
            src = entry.get("data", {}).get("source", "unknown")
            sources[src] = sources.get(src, 0) + 1
    return {
        "total_entries": len(cache),
        "active_entries": active,
        "expired_entries": expired,
        "by_source": sources,
        "cache_file": str(_cache_path()),
        "dirty": _cache_dirty,
    }


def clear_poi_cache() -> int:
    """Clear all cached POI queries."""
    global _cache_data, _cache_dirty
    with _cache_lock:
        count = len(_cache_data) if _cache_data else 0
        _cache_data = {}
        _cache_dirty = True
    _save_cache(force=True)
    logger.info(f"Cleared {count} cached POI queries")
    return count