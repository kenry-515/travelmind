"""
TravelMind Agent — Description Enricher

Replaces template/generic descriptions with LLM-generated unique descriptions.
Uses DeepSeek batch processing (20 per batch) for efficiency.

Input:  data/attractions.json
Output: data/attractions.json (updated in place)

Usage:
  cd backend
  python scripts/enrich_descriptions.py [--force]
  
  --force: Regenerate ALL descriptions, not just template ones.
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

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INPUT_FILE = DATA_DIR / "attractions.json"
BACKUP_FILE = DATA_DIR / "attractions.json.bak"

BATCH_SIZE = 20
MAX_CONCURRENT = 2
MAX_RETRIES = 2

# Templates to detect and replace
TEMPLATE_PATTERNS = [
    "收藏展示相关主题",
    "收藏和展示",
    "一座.*的博物馆.*收藏",
    "一座.*的购物中心",
    "提供.*餐饮服务",
    "为顾客提供",
    "是一家.*酒店",
    "位于.*市中心.*酒店",
]


def _fix_json(text: str) -> str:
    """Fix common LLM JSON output issues.

    Handles:
    - Trailing commas before } or ]
    - Unescaped control characters in strings
    - Windows-style line endings
    """
    import re
    # Remove trailing commas before ] or }
    text = re.sub(r',\s*([}\]])', r'\1', text)
    # Fix unescaped newlines in strings
    text = re.sub(r'(?<!\\)\n(?=[^\s])', '\\n', text)
    return text

def _load_settings():
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


def _is_template_description(desc: str) -> bool:
    """Check if a description is a generic/template one."""
    if not desc or len(desc.strip()) < 20:
        return True
    import re
    for pattern in TEMPLATE_PATTERNS:
        if re.search(pattern, desc):
            return True
    return False


def _build_attraction_context(a: Dict[str, Any]) -> str:
    """Build a rich context string for LLM description generation."""
    parts = [f"名称: {a.get('name', '')}"]
    parts.append(f"城市: {a.get('city', '')}")
    
    category = a.get("instance_of", "") or a.get("category", "") or ""
    if category:
        parts.append(f"类型: {category}")
    
    tags = a.get("tags", [])
    if tags:
        parts.append(f"标签: {', '.join(tags[:5])}")
    
    if a.get("suitable_for"):
        parts.append(f"适合: {a['suitable_for']}")
    
    if a.get("best_time"):
        parts.append(f"最佳时间: {a['best_time']}")
    
    price = a.get("price_range", "")
    if price:
        parts.append(f"价格: {price}")
    
    popularity = a.get("popularity_score", "")
    if popularity:
        parts.append(f"热度: {popularity}/10")
    
    existing_desc = a.get("description", "")
    if existing_desc and not _is_template_description(existing_desc):
        parts.append(f"现有描述: {existing_desc[:300]}")
    
    source = a.get("source", "")
    if source:
        parts.append(f"数据来源: {source}")
    
    return "\n".join(parts)


DESCRIPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {
            "type": "string",
            "description": "A unique, factual 2-3 sentence description (80-150 chars). Focus on what makes this specific place unique — its history, features, collections, atmosphere, or significance. Avoid generic phrases like 'a museum in the city'. Write in Chinese.",
            "minLength": 50,
            "maxLength": 200,
        },
    },
    "required": ["description"],
    "additionalProperties": False,
}

BATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "description": "Description results, one per attraction in order",
            "items": DESCRIPTION_SCHEMA,
            "minItems": 1,
        },
    },
    "required": ["results"],
    "additionalProperties": False,
}


async def enrich_descriptions_batch(
    client: AsyncOpenAI,
    model: str,
    batch: List[Dict[str, Any]],
    batch_idx: int,
    total_batches: int,
) -> List[str]:
    """Enrich a batch of attractions with unique descriptions."""
    
    contexts = "\n\n---\n\n".join(
        f"[{i + 1}]\n{_build_attraction_context(a)}"
        for i, a in enumerate(batch)
    )
    
    system_prompt = """你是一名旅游内容编辑，需要为每个景点撰写独特、真实、有趣的中文描述。

要求：
1. 每个描述 2-3 句话，80-150 字
2. 突出景点的独特性——历史背景、特色展品、建筑风格、文化意义、氛围特点
3. 不要使用模板化语言（如"位于XX市的一座博物馆"），要具体描述
4. 如果是博物馆：描述其特色展品、历史背景
5. 如果是古建筑：描述其建造年代、建筑风格、历史意义
6. 如果是自然景观：描述其地貌特征、观赏季节、独特看点
7. 如果是美食场所：描述其特色菜品、历史渊源、文化特色
8. 如果是购物场所：描述其定位、特色商品、历史
9. 用中文撰写，语言生动但准确"""

    user_prompt = f"""请为以下 {len(batch)} 个景点各写一段独特的描述：

{contexts}

请确保每个描述都是独一无二的，避免重复使用相同的句式。"""

    messages = [
        {"role": "user", "content": user_prompt},
    ]
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            tool_instruction = (
                "你必须调用 'output' 函数返回结构化结果。"
                "不要用普通文本回复——始终使用函数。"
            )
            full_messages = [
                {"role": "system", "content": f"{system_prompt}\n\n{tool_instruction}"},
                messages[0],
            ]
            
            tools = [{
                "type": "function",
                "function": {
                    "name": "output",
                    "description": "返回所有景点的描述结果。",
                    "parameters": BATCH_SCHEMA,
                },
            }]
            
            response = await client.chat.completions.create(
                model=model,
                messages=full_messages,
                temperature=0.7,
                tools=tools,
                tool_choice={"type": "function", "function": {"name": "output"}},
                extra_body={"thinking": {"type": "disabled"}},
            )
            
            tool_calls = response.choices[0].message.tool_calls
            if tool_calls and tool_calls[0].function.arguments:
                raw_args = tool_calls[0].function.arguments
                try:
                    parsed = json.loads(raw_args)
                except json.JSONDecodeError:
                    # Try fixing common LLM JSON issues
                    fixed = _fix_json(raw_args)
                    parsed = json.loads(fixed)
                results = parsed.get("results", [])
                if len(results) < len(batch):
                    logger.warning(
                        f"  Batch {batch_idx + 1}: 仅收到 {len(results)} 条结果，"
                        f"期望 {len(batch)} 条。补全中。"
                    )
                    results.extend([{"description": ""}] * (len(batch) - len(results)))
                return [r.get("description", "") for r in results[:len(batch)]]
            
            content = response.choices[0].message.content
            if content:
                parsed = json.loads(content)
                return [r.get("description", "") for r in parsed.get("results", [])[:len(batch)]]
            
            logger.warning(f"  Batch {batch_idx + 1}: 空响应，使用默认值")
            return [""] * len(batch)
            
        except json.JSONDecodeError as e:
            logger.warning(f"  Batch {batch_idx + 1}: JSON 解析错误: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.warning(f"  Batch {batch_idx + 1}: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
    
    logger.error(f"  Batch {batch_idx + 1}: 所有重试均失败")
    return [""] * len(batch)


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="重新生成所有描述")
    args = parser.parse_args()
    
    config = _load_settings()
    if not config["api_key"]:
        logger.error("DEEPSEEK_API_KEY 未设置。在 backend/.env 中配置。")
        return
    
    if not INPUT_FILE.exists():
        logger.error(f"输入文件不存在: {INPUT_FILE}")
        return
    
    logger.info(f"加载景点数据: {INPUT_FILE}")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if not isinstance(data, dict) or "attractions" not in data:
        logger.error("输入格式错误")
        return
    
    attractions = data["attractions"]
    total = len(attractions)
    logger.info(f"共 {total} 个景点")
    
    # Identify POIs needing description
    to_enrich = []
    for i, a in enumerate(attractions):
        desc = a.get("description", "")
        if args.force or _is_template_description(desc):
            to_enrich.append((i, a))
    
    skip_count = total - len(to_enrich)
    if skip_count > 0 and not args.force:
        logger.info(f"跳过 {skip_count} 个已有高质量描述的景点")
    logger.info(f"需要生成描述: {len(to_enrich)} 个景点")
    
    if not to_enrich:
        logger.info("无需处理！")
        return
    
    # Create backup
    logger.info(f"备份原文件 → {BACKUP_FILE}")
    import shutil
    shutil.copy2(INPUT_FILE, BACKUP_FILE)
    
    # Create batches
    batches = [
        to_enrich[i:i + BATCH_SIZE]
        for i in range(0, len(to_enrich), BATCH_SIZE)
    ]
    total_batches = len(batches)
    logger.info(f"分为 {total_batches} 批处理，每批 {BATCH_SIZE} 个")
    
    client = AsyncOpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"],
        timeout=120.0,
        max_retries=1,
        http_client=httpx.AsyncClient(trust_env=False, timeout=120.0),
    )
    
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    
    stats = {"generated": 0, "failed": 0}
    start_time = time.time()
    
    async def process_batch(batch_idx, batch_items):
        async with semaphore:
            batch = [item[1] for item in batch_items]
            logger.info(f"  批次 {batch_idx + 1}/{total_batches}: {len(batch)} 个景点...")
            
            descriptions = await enrich_descriptions_batch(
                client, config["model"], batch, batch_idx, total_batches
            )
            
            updated = 0
            for (orig_idx, _), new_desc in zip(batch_items, descriptions):
                if new_desc and len(new_desc.strip()) >= 30:
                    attractions[orig_idx]["description"] = new_desc.strip()
                    attractions[orig_idx]["description_source"] = "llm-generated"
                    updated += 1
                    stats["generated"] += 1
                else:
                    stats["failed"] += 1
            
            logger.info(f"  批次 {batch_idx + 1}: 更新 {updated}/{len(batch)} 个")
    
    tasks = [process_batch(i, batch) for i, batch in enumerate(batches)]
    await asyncio.gather(*tasks)
    
    elapsed = time.time() - start_time
    
    # Save
    output = {
        **data,
        "description_enriched": True,
        "description_enrich_date": time.strftime("%Y-%m-%d %H:%M"),
        "attractions": attractions,
    }
    
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    # Final stats
    with_desc = sum(1 for a in attractions if a.get("description") and not _is_template_description(a["description"]))
    
    logger.info(f"\n{'='*50}")
    logger.info(f"描述生成完成！耗时 {elapsed:.1f}s")
    logger.info(f"  成功: {stats['generated']}")
    logger.info(f"  失败: {stats['failed']}")
    logger.info(f"  当前有效描述: {with_desc}/{total}")
    logger.info(f"  备份文件: {BACKUP_FILE}")
    logger.info(f"  输出文件: {INPUT_FILE}")
    logger.info(f"\n⚠️  下一步: 重建向量库")
    logger.info(f"  python scripts/build_kb.py rebuild")


if __name__ == "__main__":
    asyncio.run(main())