"""
TravelMind Agent — AI Enricher (DeepSeek Batch Tagging)

Uses DeepSeek chat_structured() to batch-enrich attractions with:
  - tags (from our taxonomy)
  - suitable_for (who this place is best for)
  - best_time (best season / time of day to visit)
  - price_level (经济 / 适中 / 高端)
  - popularity_score (1-10, estimated)

Processes attractions in batches of 25 to balance speed and quality.

Input:  data/amap_enriched.json (fallback: data/wikipedia_enriched.json)
Output: data/attractions.json (final knowledge base)

Usage:
  cd backend
  python scripts/ai_enrich.py
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from openai import AsyncOpenAI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PREFERRED_INPUT = DATA_DIR / "amap_enriched.json"
FALLBACK_INPUT = DATA_DIR / "wikipedia_enriched.json"
OUTPUT_FILE = DATA_DIR / "attractions.json"

BATCH_SIZE = 25
MAX_CONCURRENT_BATCHES = 2  # avoid rate limits
MAX_RETRIES = 2

# Tag taxonomy (synced with data/tags.json)
ALL_TAGS = [
    "美食", "摄影", "购物", "夜生活", "网红打卡", "探险", "滑雪", "潜水", "冲浪",
    "骑行", "徒步", "露营", "温泉", "历史", "博物馆", "寺庙", "古镇", "建筑",
    "遗址", "民俗", "自然", "海岛", "海滩", "爬山", "日出", "日落", "赏花",
    "红叶", "峡谷", "瀑布", "湖泊", "森林", "溶洞", "亲子", "情侣", "家庭",
    "老年", "独自", "休闲", "小众", "文艺", "深度", "打卡", "特种兵", "穷游",
    "奢华", "春季", "夏季", "秋季", "冬季", "全年",
]

VALID_TAGS_SET = set(ALL_TAGS)

# JSON schema for the structured output of a single attraction enrichment
ENRICH_SCHEMA = {
    "type": "object",
    "properties": {
        "tags": {
            "type": "array",
            "description": f"Relevant tags from: {', '.join(ALL_TAGS)}",
            "items": {"type": "string"},
            "maxItems": 8,
        },
        "suitable_for": {
            "type": "string",
            "description": "Who this place is best for (e.g. 亲子家庭, 情侣, 历史爱好者, 摄影爱好者, 徒步爱好者, 美食爱好者, 所有人). Use Chinese.",
        },
        "best_time": {
            "type": "string",
            "description": "Best season/time to visit (e.g. 春季, 秋季, 清晨, 傍晚, 全年). Use Chinese.",
        },
        "price_level": {
            "type": "string",
            "enum": ["经济", "适中", "高端"],
            "description": "Estimated price level.",
        },
        "popularity_score": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "Estimated popularity (10 = most popular).",
        },
    },
    "required": ["tags", "suitable_for", "best_time", "price_level", "popularity_score"],
    "additionalProperties": False,
}

# ── Helpers ──────────────────────────────────────────────


def _load_settings():
    """Load DeepSeek settings from project config or environment variables."""
    try:
        from app.config.settings import settings
        return {
            "api_key": settings.DEEPSEEK_API_KEY,
            "base_url": settings.DEEPSEEK_BASE_URL,
            "model": settings.LLM_MODEL,
        }
    except ImportError:
        import os
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "")
        model = os.getenv("LLM_MODEL", "")
        # If still empty, try loading from .env
        if not api_key:
            try:
                from pydantic_settings import BaseSettings
                class _LLMEnv(BaseSettings):
                    DEEPSEEK_API_KEY: str = ""
                    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
                    LLM_MODEL: str = "deepseek-v4-flash"
                    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": True, "extra": "ignore"}
                _e = _LLMEnv()
                api_key = _e.DEEPSEEK_API_KEY
                base_url = _e.DEEPSEEK_BASE_URL
                model = _e.LLM_MODEL
            except ImportError:
                pass
        return {
            "api_key": api_key,
            "base_url": base_url or "https://api.deepseek.com",
            "model": model or "deepseek-v4-flash",
        }


def _clean_tags(tags: List[str]) -> List[str]:
    """Filter tags to only valid ones, deduplicate."""
    seen = set()
    cleaned = []
    for t in tags:
        t = t.strip()
        if t in VALID_TAGS_SET and t not in seen:
            cleaned.append(t)
            seen.add(t)
    return cleaned


def _build_attraction_prompt(attraction: Dict[str, Any]) -> str:
    """Build a concise prompt describing one attraction for the LLM."""
    parts = [f"景点名称: {attraction.get('name', '未知')}"]
    if attraction.get("city"):
        parts.append(f"城市: {attraction.get('city')}")
    desc = attraction.get("description", "")
    if desc:
        # Truncate long descriptions to save tokens
        desc_short = desc[:300] + "..." if len(desc) > 300 else desc
        parts.append(f"描述: {desc_short}")
    instance = attraction.get("instance_of", "")
    if instance:
        parts.append(f"类型: {instance}")
    return "\n".join(parts)


# ── Validation ────────────────────────────────────────────

VALID_PRICE_LEVELS = {"经济", "适中", "高端"}


def _validate_enrichment(result: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Validate and sanitize a single enrichment result from the LLM.

    Ensures all fields are present and within allowed ranges.
    Returns a cleaned dict safe to merge into the knowledge base.
    """
    cleaned: Dict[str, Any] = {}

    # Tags — must be list of strings, filtered to VALID_TAGS_SET
    raw_tags = result.get("tags", [])
    if not isinstance(raw_tags, list):
        logger.warning(f"  Item {index}: tags is not a list ({type(raw_tags).__name__}), defaulting to []")
        raw_tags = []
    cleaned["tags"] = _clean_tags(raw_tags)

    # suitable_for — must be a non-empty string
    suitable = result.get("suitable_for", "所有人")
    if not isinstance(suitable, str) or not suitable.strip():
        suitable = "所有人"
    cleaned["suitable_for"] = suitable.strip()[:200]  # max 200 chars

    # best_time — must be a non-empty string
    best_time = result.get("best_time", "全年")
    if not isinstance(best_time, str) or not best_time.strip():
        best_time = "全年"
    cleaned["best_time"] = best_time.strip()[:100]  # max 100 chars

    # price_level — must be one of VALID_PRICE_LEVELS
    price = result.get("price_level", "适中")
    if price not in VALID_PRICE_LEVELS:
        logger.warning(f"  Item {index}: invalid price_level '{price}', defaulting to '适中'")
        price = "适中"
    cleaned["price_level"] = price

    # popularity_score — must be int 1-10
    pop = result.get("popularity_score", 5)
    if not isinstance(pop, (int, float)):
        logger.warning(f"  Item {index}: popularity_score is not a number ({type(pop).__name__}), defaulting to 5")
        pop = 5
    pop = int(pop)
    if pop < 1:
        pop = 1
    elif pop > 10:
        pop = 10
    cleaned["popularity_score"] = pop

    return cleaned


# ── Batch Enrichment ────────────────────────────────────


async def enrich_batch(
    client: AsyncOpenAI,
    model: str,
    batch: List[Dict[str, Any]],
    batch_idx: int,
    total_batches: int,
) -> List[Dict[str, Any]]:
    """Enrich a batch of attractions using DeepSeek chat_structured()."""
    # Build the list of attractions in the prompt
    attractions_text = "\n\n---\n\n".join(
        f"[{i + 1}] {_build_attraction_prompt(a)}"
        for i, a in enumerate(batch)
    )

    system_prompt = f"""你是 TravelMind 旅游数据标注专家。请为每个景点标注以下信息：

- tags: 从以下标签列表中选择最合适的 3-6 个标签。
  请优先选择能体现景点独特性的标签，避免所有景点都选择相同的热门标签（如"历史"、"摄影"）。
  应根据景点实际特点选择差异化标签：
  • 自然景观 → 选"自然/爬山/湖泊/森林/瀑布/峡谷/赏花"等
  • 文化古迹 → 选"历史/博物馆/古镇/寺庙/遗址/建筑"等
  • 美食场所 → 选"美食/火锅/小吃/海鲜/夜市"等
  • 购物商圈 → 选"购物/网红打卡/夜生活"等
  • 室内休闲 → 选"亲子/休闲/温泉/美术馆/图书馆"等
  目标是让所有景点的标签分布多样化，提升行程推荐的丰富度。
{', '.join(ALL_TAGS)}

- suitable_for: 最适合的人群（中文描述，如 亲子家庭、情侣、历史爱好者等）
- best_time: 最佳游玩季节/时间（中文，如 春季、秋季、清晨、傍晚、全年 等）
- price_level: 价格水平（经济/适中/高端）
- popularity_score: 热门程度 1-10 分（10 表示非常热门）

请基于景点名称、描述和类型进行判断。对于信息不足的景点，给出合理推测。

你需要为每个景点输出一个标注结果。请调用 output 函数，将所有结果以数组形式返回，
数组中的每个元素对应输入中的每个景点（按顺序）。"""

    messages = [
        {"role": "user", "content": f"请为以下 {len(batch)} 个景点标注信息：\n\n{attractions_text}"}
    ]

    # Output schema: array of enrichment objects
    output_schema = {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "description": "Enrichment results, one per attraction in order",
                "items": ENRICH_SCHEMA,
                "minItems": len(batch),
                "maxItems": len(batch),
            },
        },
        "required": ["results"],
        "additionalProperties": False,
    }

    for attempt in range(MAX_RETRIES + 1):
        try:
            # Build tool-calling request
            tool_instruction = (
                "You MUST call the 'output' function with your structured result. "
                "Do not respond in plain text — always use the function."
            )
            full_messages = [
                {"role": "system", "content": f"{system_prompt}\n\n{tool_instruction}"},
                messages[0],
            ]

            tools = [{
                "type": "function",
                "function": {
                    "name": "output",
                    "description": "Return the enrichment results for all attractions.",
                    "parameters": output_schema,
                },
            }]

            response = await client.chat.completions.create(
                model=model,
                messages=full_messages,  # type: ignore
                temperature=0.3,
                tools=tools,  # type: ignore
                tool_choice={"type": "function", "function": {"name": "output"}},
                # DeepSeek V4 defaults to thinking mode, which rejects forced
                # tool_choice — disable it (same fix as llm_service).
                extra_body={"thinking": {"type": "disabled"}},
            )

            tool_calls = response.choices[0].message.tool_calls
            if tool_calls and tool_calls[0].function.arguments:
                parsed = json.loads(tool_calls[0].function.arguments)
                results = parsed.get("results", [])

                # Pad/truncate to match batch size
                if len(results) < len(batch):
                    logger.warning(
                        f"  Batch {batch_idx + 1}: got {len(results)} results, "
                        f"expected {len(batch)}. Padding with defaults."
                    )
                    results.extend([
                        {"tags": [], "suitable_for": "所有人", "best_time": "全年",
                         "price_level": "适中", "popularity_score": 5}
                    ] * (len(batch) - len(results)))
                return results[:len(batch)]

            # Fallback: try content as JSON
            content = response.choices[0].message.content
            if content:
                parsed = json.loads(content)
                return parsed.get("results", [])[:len(batch)]

            logger.warning(f"  Batch {batch_idx + 1}: empty response, using defaults")
            return [
                {"tags": [], "suitable_for": "所有人", "best_time": "全年",
                 "price_level": "适中", "popularity_score": 5}
            ] * len(batch)

        except json.JSONDecodeError as e:
            logger.warning(f"  Batch {batch_idx + 1}: JSON parse error: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.warning(f"  Batch {batch_idx + 1}: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)

    # All retries exhausted — return defaults
    logger.error(f"  Batch {batch_idx + 1}: all retries failed, using defaults")
    return [
        {"tags": [], "suitable_for": "所有人", "best_time": "全年",
         "price_level": "适中", "popularity_score": 5}
    ] * len(batch)


# ── Main ─────────────────────────────────────────────────


async def main():
    """Main entry point."""
    config = _load_settings()
    if not config["api_key"]:
        logger.error(
            "DEEPSEEK_API_KEY is not set. Set it in backend/.env."
        )
        return

    # Pick input file
    input_file = PREFERRED_INPUT if PREFERRED_INPUT.exists() else FALLBACK_INPUT
    if not input_file.exists():
        logger.error(f"No input file found at {PREFERRED_INPUT} or {FALLBACK_INPUT}")
        return

    logger.info(f"Loading attractions from {input_file.name}...")
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or "attractions" not in data:
        logger.error(f"Invalid input format in {input_file}")
        return

    attractions = data["attractions"]
    total = len(attractions)
    logger.info(f"Loaded {total} attractions")

    # Filter: enrich only those without ai tags (idempotent)
    to_enrich = [
        (i, a) for i, a in enumerate(attractions)
        if not a.get("tags") or not a.get("ai_enriched")
    ]
    skip_count = total - len(to_enrich)

    if skip_count > 0:
        logger.info(f"Skipping {skip_count} already-enriched attractions")
    logger.info(f"Enriching {len(to_enrich)} attractions in batches of {BATCH_SIZE}...")

    if not to_enrich:
        logger.info("Nothing to do!")
        return

    # Create batches
    batches = [
        to_enrich[i:i + BATCH_SIZE]
        for i in range(0, len(to_enrich), BATCH_SIZE)
    ]
    total_batches = len(batches)
    logger.info(f"Total batches: {total_batches}")

    client = AsyncOpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"],
        timeout=120.0,
        max_retries=1,
        # trust_env=False: DeepSeek is reachable directly; a VPN system proxy
        # breaks Python TLS through the tunnel (same fix as llm_service).
        http_client=httpx.AsyncClient(trust_env=False, timeout=120.0),
    )

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)

    async def process_batch(batch_idx, batch_items):
        async with semaphore:
            # batch_items is list of (original_index, attraction_dict)
            batch = [item[1] for item in batch_items]
            logger.info(
                f"  Batch {batch_idx + 1}/{total_batches}: "
                f"{len(batch)} attractions..."
            )
            results = await enrich_batch(client, config["model"], batch, batch_idx, total_batches)

            # Validate and merge results back
            for (orig_idx, _), enrichment in zip(batch_items, results):
                att = attractions[orig_idx]
                validated = _validate_enrichment(enrichment, orig_idx)
                att["tags"] = validated["tags"]
                att["suitable_for"] = validated["suitable_for"]
                att["best_time"] = validated["best_time"]
                att["price_level"] = validated["price_level"]
                att["popularity_score"] = validated["popularity_score"]
                att["ai_enriched"] = True

            logger.info(
                f"  Batch {batch_idx + 1}/{total_batches}: done"
            )

    # Process batches concurrently (but limited by semaphore)
    tasks = [process_batch(i, batch) for i, batch in enumerate(batches)]
    await asyncio.gather(*tasks)

    # Stats
    with_tags = sum(1 for a in attractions if a.get("tags"))
    logger.info(f"Enrichment complete: {with_tags}/{total} have tags")

    # Safety: never overwrite a good knowledge base with an all-defaults run
    # (e.g. when every batch failed on a network issue).
    if with_tags == 0 and total > 0:
        logger.error(
            "0 attractions enriched — aborting WITHOUT saving to protect the "
            "existing attractions.json. Fix the connection issue and re-run."
        )
        return

    # Tag distribution
    tag_counts: Dict[str, int] = {}
    for a in attractions:
        for t in a.get("tags", []):
            tag_counts[t] = tag_counts.get(t, 0) + 1
    top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:15]
    logger.info("Top 15 tags:")
    for tag, count in top_tags:
        logger.info(f"  {tag}: {count}")

    # Save final knowledge base
    output = {
        "source": data.get("source", "") + " + AI Enrichment",
        "enrich_date": time.strftime("%Y-%m-%d"),
        "total": total,
        "ai_enriched": with_tags,
        "attractions": attractions,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"Done! Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
