"""
TravelMind Agent — POI Name Normalizer (Phase 11.1)

Unified name normalization + alias system for cross-source POI matching.

Problem: KB, trends, Amap, and AI-generated text use different names for the
same place (e.g., "洪崖洞民俗风貌区" vs "洪崖洞" vs "洪崖洞景区").
Exact match rate: only ~17%.

Solution:
  1. Unicode normalization (full-width → half-width, CJK compatibility)
  2. Strip city prefixes and generic suffixes to extract "core name"
  3. Optional alias lookup (load curated aliases from poi_aliases.json)
  4. Canonical form for consistent map-key usage across all agents

Integration points:
  - recommendation_agent.py: trend_map lookup via canonical name
  - trend_agent.py: _fuzzy_match_name already similar; this supersedes it
  - route_optimizer.py: _normalize replaced by this module
  - poi_health_service.py: inactive POI name matching

Usage:
    from app.services.name_normalizer import NameNormalizer
    nn = NameNormalizer.singleton()
    canonical = nn.normalize("重庆洪崖洞民俗风貌区")  # → "洪崖洞"
"""

import asyncio
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Set

try:
    import zhconv
    _HAS_ZHCONV = True
except ImportError:
    _HAS_ZHCONV = False

logger = logging.getLogger(__name__)

# ── City prefixes (sorted longest-first for deterministic stripping) ─
_CITY_PREFIXES: List[str] = sorted(
    [
        "重庆", "成都", "北京", "上海", "广州", "深圳", "杭州",
        "西安", "长沙", "厦门", "大理", "南京", "武汉", "苏州",
        "三亚", "丽江", "昆明", "青岛", "大连", "桂林", "哈尔滨",
        "拉萨", "贵阳", "南宁", "天津", "郑州", "福州", "黄山",
        "张家界", "香格里拉",
    ],
    key=len,
    reverse=True,
)

# ── Generic suffixes (sorted longest-first) ─
_GENERIC_SUFFIXES: List[str] = sorted(
    [
        "国家级自然保护区", "国家森林公园", "国家地质公园",
        "历史文化街区", "商业步行街",
        "文创公园", "观景平台", "风景区", "旅游区", "度假村",
        "轻轨站", "地铁站", "火车站", "博物馆", "纪念馆",
        "景区", "公园", "古镇", "老街", "寺庙", "平台",
        "广场", "大桥", "索道", "步道", "遗址",
        "故里", "故居", "书院", "园林",
        "游览区", "风景区", "步行街", "商业街",
    ],
    key=len,
    reverse=True,
)

# ── Common punctuation / whitespace removals ─
_CLEAN_RE = re.compile(r"[（()）\[\]【】《》、，。；：·\s\-—]+")

# ── Character normalization map ─
_CHAR_MAP: Dict[str, str] = {
    "贰": "二", "叁": "三", "肆": "四", "伍": "五",
    "拾": "十", "佰": "百", "仟": "千",
}


def _unicode_normalize(text: str) -> str:
    """NFKC + traditional-to-simplified Chinese normalization."""
    n = unicodedata.normalize("NFKC", text)
    if _HAS_ZHCONV:
        try:
            n = zhconv.convert(n, "zh-cn")
        except Exception:
            pass
    return n


def _replace_chars(text: str) -> str:
    """Replace known variant characters (e.g., 贰→二)."""
    for old, new in _CHAR_MAP.items():
        text = text.replace(old, new)
    return text


def _strip_city_prefix(name: str) -> str:
    """Strip city prefix from a POI name (重庆洪崖洞 → 洪崖洞)."""
    for prefix in _CITY_PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix) + 1:
            return name[len(prefix):]
    return name


def _strip_generic_suffix(name: str) -> str:
    """Strip generic suffix from a POI name (洪崖洞景区 → 洪崖洞).

    Requires at least 1 remaining character after stripping so that
    suffixes that ARE the core name (e.g., "博物馆") are preserved.
    """
    for suffix in _GENERIC_SUFFIXES:
        if not name.endswith(suffix):
            continue
        if len(name) >= len(suffix) + 1:
            return name[:-len(suffix)]
    return name


def extract_core_name(name: str, suffixes: Optional[List[str]] = None) -> str:
    """Extract the core/semantic name of a POI.

    Steps:
      1. Unicode NFKC normalization + traditional→simplified
      2. Remove punctuation & whitespace
      3. Character variant normalization
      4. Strip generic suffix (original name, before prefix stripping)
      5. If result too short, try: strip city prefix → strip suffix
      6. Return best result (≥ 2 chars preferred)

    Args:
        name: The POI name to normalize.
        suffixes: Optional custom suffix list (for price_enricher compat).
                  When provided, overrides the default _GENERIC_SUFFIXES.
    """
    if not name:
        return ""

    suf_list = suffixes if suffixes is not None else list(_GENERIC_SUFFIXES)
    suf_list = sorted(suf_list, key=len, reverse=True)

    def _strip(name_to_strip: str) -> str:
        for suf in suf_list:
            if name_to_strip.endswith(suf) and len(name_to_strip) >= len(suf) + 1:
                result = name_to_strip[:-len(suf)]
                # Only strip if ≥ 2 chars remain (avoids "风景区" → "风")
                if len(result) >= 2:
                    return result
        return name_to_strip

    n = _unicode_normalize(name)
    n = _CLEAN_RE.sub("", n)
    n = _replace_chars(n)

    # Strategy 1: suffix stripping only (no prefix strip)
    result1 = _strip(n)

    # Strategy 2: prefix → suffix (for "重庆洪崖洞景区" → "洪崖洞")
    without_prefix = _strip_city_prefix(n)
    if without_prefix != n:
        result2 = _strip(without_prefix)
    else:
        result2 = ""

    # Pick the shorter non-empty result (more stripping = closer to core)
    candidates = [r for r in (result1, result2) if len(r) >= 2]
    if candidates:
        return min(candidates, key=len).strip()

    # Fallback: return the best available
    if len(result1) >= 1:
        return result1.strip()
    if len(result2) >= 1:
        return result2.strip()
    return n.strip()


# ── Alias Map ─────────────────────────────────────────────


class NameNormalizer:
    """Singleton name normalizer with optional alias map.

    Loads curated aliases from data/poi_aliases.json on first use.
    """

    _instance: Optional["NameNormalizer"] = None

    def __init__(self, aliases_file: Optional[Path] = None) -> None:
        """Initialize normalizer and load alias map.

        Args:
            aliases_file: Path to poi_aliases.json. Defaults to data/poi_aliases.json.
        """
        self._canonical: Dict[str, str] = {}  # core_name → canonical form
        self._aliases: Dict[str, Set[str]] = {}  # canonical → {variant1, variant2, ...}
        self._loaded = False
        self._aliases_file = aliases_file

    @classmethod
    def singleton(cls) -> "NameNormalizer":
        """Return the global singleton (created on first call)."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_singleton(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    def _load(self) -> None:
        """Load alias map from JSON file (idempotent)."""
        if self._loaded:
            return
        self._loaded = True

        path = self._aliases_file
        if path is None:
            path = Path(__file__).resolve().parent.parent.parent / "data" / "poi_aliases.json"

        if not path.exists():
            logger.debug("No poi_aliases.json found — using core-name normalization only")
            return

        try:
            data = json.loads(path.read_text("utf-8"))

            aliases_list = data.get("aliases", []) if isinstance(data, dict) else data

            count = 0
            for entry in aliases_list:
                canonical = entry.get("canonical", "").strip()
                variants = entry.get("variants", [])
                if not canonical or not variants:
                    continue

                canonical = extract_core_name(canonical)
                if not canonical:
                    continue

                self._aliases[canonical] = set()
                for v in variants:
                    v_clean = extract_core_name(v.strip())
                    if v_clean and v_clean != canonical:
                        self._aliases[canonical].add(v_clean)
                        self._canonical[v_clean] = canonical
                count += 1

            logger.info(
                "Loaded %d alias groups covering %d variant mappings",
                count,
                len(self._canonical),
            )
        except Exception as e:
            logger.warning("Failed to load poi_aliases.json: %s", e)

    def normalize(self, name: str) -> str:
        """Normalize a POI name to its canonical form.

        Returns the core name if no alias is known.
        """
        core = extract_core_name(name)
        self._load()
        return self._canonical.get(core, core)

    def matches(self, name_a: str, name_b: str) -> bool:
        """Check if two POI names refer to the same place.

        Uses multi-strategy matching:
          1. Canonical name equality (after full normalization + aliases)
          2. Core name containment (after normalization)
          3. Raw name substring (preserves context that normalization strips)
        """
        a = self.normalize(name_a)
        b = self.normalize(name_b)
        if a == b:
            return True
        # Check core containment (after normalization)
        if len(a) >= 2 and len(b) >= 2 and (a in b or b in a):
            return True
        # Check raw names (preserves context: "上海博物馆" ⊂ "上海博物馆新馆")
        ra = _unicode_normalize(name_a)
        rb = _unicode_normalize(name_b)
        ra = _CLEAN_RE.sub("", ra)
        rb = _CLEAN_RE.sub("", rb)
        if len(ra) >= 2 and len(rb) >= 2 and (ra in rb or rb in ra):
            return True
        return False

    def has_alias(self, name: str) -> bool:
        """Check if a name has a known alias mapping."""
        core = extract_core_name(name)
        self._load()
        return core in self._canonical

    def get_variants(self, name: str) -> Set[str]:
        """Get all known variants of a POI name (including the canonical form)."""
        canonical = self.normalize(name)
        self._load()
        result = {canonical}
        for canon, variants in self._aliases.items():
            if canon == canonical:
                result.update(variants)
        return result


# ── Convenience Functions ────────────────────────────────────


def normalize_poi_name(name: str) -> str:
    """Convenience: normalize a single POI name."""
    return NameNormalizer.singleton().normalize(name)


def poi_names_match(a: str, b: str) -> bool:
    """Convenience: check if two POI names match."""
    return NameNormalizer.singleton().matches(a, b)


def build_canonical_map(names: List[str]) -> Dict[str, str]:
    """Build a canonical name lookup dict for a list of names.

    Returns: {canonical_name: original_name} mapping.
    """
    nn = NameNormalizer.singleton()
    result: Dict[str, str] = {}
    for name in names:
        if not name:
            continue
        canonical = nn.normalize(name)
        if canonical not in result:
            result[canonical] = name
    return result
