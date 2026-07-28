"""
TravelMind Agent — Chat Agent (Phase 12.1)

Free-form travel conversation agent. Handles general travel questions
that fall outside the slot-filling intent — weather inquiries, attraction
details, food recommendations, travel tips, and casual chat.

Uses DeepSeek v4-flash (non-thinking mode) for low-latency responses.
"""

import logging
from typing import Any, Dict, List, Optional

from app.services.llm_service import get_llm_provider

logger = logging.getLogger(__name__)

# ── System prompt for free chat ───────────────────────────

CHAT_SYSTEM_PROMPT = """你是 TravelMind，一个专业的中国旅行助手。你的知识涵盖中国各大城市的旅游信息，包括景点、美食、天气、交通、文化等。

对话原则：
1. 回答要简洁友好，2-4 句话为宜（除非用户要求详细说明）
2. 如果用户问到具体景点，尽量给出准确信息（开放时间、门票、特色等）
3. 如果用户问到美食，推荐当地特色菜品和知名餐厅
4. 如果用户问到天气，结合季节给出穿衣和出行建议
5. 如果信息不确定，诚实说明而非编造
6. 用热情但不过分夸张的语气，像一位有经验的当地朋友
7. 用户只是打招呼或一般性询问（如"你能帮我规划旅行吗"）时，先自然回应并简单介绍你能做什么，不要一次性罗列"去哪个城市、玩几天、预算多少"等一串问题
8. 用户让对比两个目的地时，明确说出各自的差异、特色和适合人群，给出有立场的建议，不要和稀泥

当前支持的旅游城市：重庆、成都、北京、上海、广州、西安、杭州、长沙、厦门、大理、三亚、桂林、苏州、张家界、丽江。

如果用户的问题是关于旅行规划的（目的地、天数、预算等），请引导他们使用「对话规划」功能来生成详细行程。"""

# ── Fallback reply templates (when LLM is unavailable) ───

FALLBACK_REPLIES: Dict[str, str] = {
    "weather": "天气方面，建议你查看当地一周预报。夏天注意防暑防晒，冬天注意保暖。需要我帮你查具体城市的天气吗？",
    "food": "说到美食，我们支持的城市都有各自的特色！比如重庆火锅、成都串串、西安肉夹馍、广州早茶……你对哪个城市的美食感兴趣？",
    "attraction": "想了解哪个景点呢？告诉我城市和景点名字，我可以帮你介绍！比如「洪崖洞」「西湖」「故宫」等等。",
    "tip": "旅行小贴士：提前订票更划算，避开节假日人少体验好，下载离线地图以防山区没信号。还有其他想了解的吗？",
    "default": "好问题！不过我还在学习中。不如试试让我帮你规划行程？告诉我目的地和天数就可以开始～",
}


# ── Public API ────────────────────────────────────────────

async def free_chat(
    user_text: str,
    slots_context: Dict[str, Any],
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Generate a free-form travel conversation response.

    Args:
        user_text: The user's raw text input.
        slots_context: Current dialog slots (city, days, tags, etc.) for context.
        history: Optional conversation history for multi-turn context.

    Returns:
        A natural-language reply string.
    """
    # Build context from known slots
    ctx_parts = []
    if slots_context.get("city"):
        ctx_parts.append(f"用户当前规划目的地：{slots_context['city']}")
    if slots_context.get("days"):
        ctx_parts.append(f"计划天数：{slots_context['days']}天")
    if slots_context.get("tags"):
        ctx_parts.append(f"旅行偏好：{'、'.join(slots_context['tags'])}")
    if slots_context.get("budget_level"):
        ctx_parts.append(f"预算水平：{slots_context['budget_level']}")
    context_text = "；".join(ctx_parts) if ctx_parts else "用户尚未设置旅行偏好"

    # Build messages for LLM
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "system", "content": f"[当前上下文] {context_text}"},
    ]

    # Append conversation history (last 6 turns to stay within context limit)
    if history:
        messages.extend(history[-6:])

    messages.append({"role": "user", "content": user_text})

    # Try LLM
    try:
        provider = await get_llm_provider()
        reply = await provider.chat(
            messages=messages,
            temperature=0.7,  # Slightly creative for natural conversation
            max_tokens=500,
        )
        if reply and len(reply.strip()) >= 10:
            return reply.strip()
    except Exception as e:
        logger.warning(f"Free chat LLM call failed, using fallback: {e}")

    # Fallback: keyword-based template matching
    return _fallback_reply(user_text)


def _fallback_reply(text: str) -> str:
    """Template-based fallback when LLM is unavailable."""
    keywords_map = [
        (["天气", "下雨", "温度", "热", "冷", "穿什么"], "weather"),
        (["吃", "美食", "火锅", "小吃", "餐厅", "好吃", "推荐菜"], "food"),
        (["景点", "好玩", "值得去", "介绍", "有什么"], "attraction"),
        (["注意", "建议", "提示", "小贴士", "攻略", "怎么玩"], "tip"),
    ]
    for keywords, key in keywords_map:
        if any(kw in text for kw in keywords):
            return FALLBACK_REPLIES[key]
    return FALLBACK_REPLIES["default"]
