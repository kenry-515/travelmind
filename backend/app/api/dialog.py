"""
TravelMind Agent — Dialog API (对话式规划 · 意图层)

POST /api/v1/dialog/message          — 多轮对话（槽位收敛 / 修改分流）
POST /api/v1/dialog/generate         — 确认后触发生成（阻塞式）
POST /api/v1/dialog/generate/stream  — 确认后触发生成（SSE 真实阶段进度，Phase 12.24）

只做意图层：槽位、状态机、分流判定；生成能力全部复用
（run_travel_workflow / regenerate_day / itinerary_contract）。
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.errors import error_response
from app.agents.dialog_manager import (
    append_message,
    apply_slot_override,
    build_summary,
    classify_intent,
    classify_modification,
    get_history,
    get_session,
    ground_extraction,
    merge_slots,
    next_action,
    save_session,
    synthesize_input,
    try_remove_item,
    _DEFER_RE,
)
from app.agents.orchestrator import run_travel_workflow, run_travel_workflow_stream
from app.agents.planning_agent import regenerate_day
from app.agents.profile_agent import extract_profile
from app.api.deps import get_device_id
from app.database import connection as db_conn
from app.rag.retriever import retrieve
from app.services.llm_service import get_llm_provider
from app.services.user_service import get_or_create_user
from app.services import itinerary_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response Models ────────────────────────────

class DialogMessageRequest(BaseModel):
    session_id: Optional[str] = Field(None, max_length=64)
    text: str = Field("", max_length=2000)
    slot_override: Optional[Dict[str, Any]] = Field(
        None, description="意图状态条手动编辑的槽位覆盖"
    )


class DialogGenerateRequest(BaseModel):
    session_id: str = Field(..., max_length=64)


class DialogResponse(BaseModel):
    session_id: str
    reply: str
    stage: str
    slots: Dict[str, Any]
    followups_left: int
    suggestions: Optional[List[Dict[str, str]]] = None
    confirm: bool = False
    itinerary: Optional[Dict[str, Any]] = None
    itinerary_id: Optional[str] = None
    queued: int = 0
    # Phase 8.1: 拒答 / 降级字段
    refused: bool = False
    refuse_reason: Optional[str] = None
    coverage_warning: Optional[str] = None


# ── Helpers ──────────────────────────────────────────────

def _resp(sid: str, state: Dict[str, Any], reply: str, **kw) -> DialogResponse:
    return DialogResponse(
        session_id=sid,
        reply=reply,
        stage=state["stage"],
        slots=state["slots"],
        followups_left=max(0, 3 - state["followups_used"]),
        **kw,
    )


def _slots_context(slots: Dict[str, Any]) -> str:
    known = []
    if slots.get("city"):
        known.append(f"目的地={slots['city']}")
    if slots.get("days"):
        known.append(f"天数={slots['days']}")
    if slots.get("companions") and slots["companions"] != "不限":
        known.append(f"同行={slots['companions']}")
    if slots.get("tags"):
        known.append(f"偏好={','.join(slots['tags'])}")
    return "；".join(known)


async def _naturalize_reply(
    action: Dict[str, Any],
    state: Dict[str, Any],
    user_text: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """把状态机的模板回复润色成自然、每次不同的对话语气（LLM，失败回退模板）。

    Phase 12.20: 用户反馈"AI 只会机械重复询问意图要素"——状态机决定
    做什么（追问/建议/确认），LLM 负责怎么说得像朋友。

    Phase 16.1: 传入完整对话历史，让 LLM 基于上下文生成连贯回复。
    """
    template = action.get("reply", "")
    if not template:
        return template
    try:
        from app.agents.dialog_manager import required_missing
        slots = state["slots"]
        known = _slots_context(slots) or "（还没有已知信息）"
        missing = "、".join(required_missing(slots)) or "无"
        suggestions_text = ""
        if action.get("suggestions"):
            suggestions_text = "、".join(s.get("label", "") for s in action["suggestions"])

        # Phase 16.1: Build the full message with history for context
        system_prompt = "你是用户贴心的旅行搭子「小游」，说话自然、真诚、简洁，像好朋友一样帮用户规划旅行。"

        user_msg = (
            f"用户最新消息：「{user_text}」\n"
            f"当前已知：{known}\n"
            f"还缺的信息：{missing}\n"
            f"可选建议：{suggestions_text or '无'}\n"
            f"参考意思（请用自己的话重写，别照抄）：{template}\n\n"
            "要求：像朋友聊天一样回复 1-3 句；自然承接用户说的话；"
            "如果需要追问，把问题融进对话里而不是生硬审问；"
            "不要输出「我在听」「说说你的想法」这类空话；每次措辞都要不一样。"
        )

        # Build messages with history + current turn
        # Phase 16.1 bugfix: history already contains the current user message
        # (appended before calling this function), so we need to strip the last
        # user message from history to avoid duplicating it in the final prompt.
        messages: List[Dict[str, str]] = []
        if history:
            # Find the last user message index and exclude it (it's the current turn)
            last_user_idx = -1
            for i in range(len(history) - 1, -1, -1):
                if history[i]["role"] == "user":
                    last_user_idx = i
                    break
            # Include history up to (but not including) the last user message
            for m in history[:last_user_idx] if last_user_idx >= 0 else history:
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_msg})

        _provider = await get_llm_provider()
        reply = await _provider.chat(
            messages=messages,
            system_prompt=system_prompt,
            temperature=0.9,
            max_tokens=200,
        )
        reply = (reply or "").strip()
        if len(reply) >= 4:
            return reply
    except Exception as e:
        logger.debug(f"Reply naturalize failed, using template: {e}")
    return template


async def _classify_with_llm(text: str) -> Dict[str, Any]:
    """规则未命中时的 LLM 兜底分类（一次低成本结构化调用）。"""
    schema = {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["local", "global", "slot_change", "unknown"],
                "description": "local=只改某一天；global=整体重生成；slot_change=改天数/城市/预算",
            },
            "day_index": {"type": "integer", "description": "local 时的 0 基天索引，不适用填 -1"},
            "slot_updates": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer"},
                    "city": {"type": "string"},
                    "budget_level": {"type": "string"},
                },
            },
        },
        "required": ["type"],
    }
    try:
        _provider_s = await get_llm_provider()
        result = await _provider_s.chat_structured(
            messages=[{"role": "user", "content": f"用户对已生成的旅行行程说：「{text}」。请判断修改意图类型。"}],
            output_schema=schema,
            system_prompt="你是修改意图分类器，只通过 output 函数返回 JSON。",
        )
        if result and result.get("type") in ("local", "global", "slot_change"):
            out: Dict[str, Any] = {"type": result["type"], "reason": "llm-fallback"}
            if result["type"] == "local":
                out["day_index"] = max(int(result.get("day_index", 0)), 0)
            if result["type"] == "slot_change" and isinstance(result.get("slot_updates"), dict):
                out["slot_updates"] = {
                    k: v for k, v in result["slot_updates"].items() if v is not None
                }
            return out
    except Exception as e:
        logger.warning(f"LLM modification classify failed: {e}")
    return {"type": "unknown", "reason": "llm-unknown"}


# ── Routes ───────────────────────────────────────────────

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


async def _auto_save_itinerary(
    state: Dict[str, Any],
    itinerary: Dict[str, Any],
    result: Dict[str, Any],
    user_input: str,
    device_id: Optional[str],
) -> Optional[str]:
    """行程自动保存（best-effort）：PG 优先，PG 不可达时本地文件回退。

    dialog_generate 与 dialog_generate_stream 共用（Phase 12.24 抽取）。
    """
    saved_id: Optional[str] = None
    if itinerary and device_id and not db_conn.DB_HEALTHY:
        # PG 不可达 → 本地文件存储回退
        try:
            from app.services import local_itinerary_store
            saved_id = local_itinerary_store.save_itinerary(
                device_id=device_id,
                itinerary=itinerary,
                validation_report=itinerary.get("validation_report"),
                profile_snapshot={
                    "slots": state.get("slots", {}),
                    "user_input": user_input,
                },
                weather_snapshot=result.get("weather"),
            )
        except Exception as e:
            logger.warning(f"Local itinerary save failed (non-fatal): {e}")
    if db_conn.DB_HEALTHY and itinerary and device_id:
        try:
            async with db_conn.async_session() as db:
                user = await get_or_create_user(db, device_id)
                saved = await itinerary_service.save_itinerary(
                    db=db,
                    user_id=user.id,
                    itinerary=itinerary,
                    validation_report=itinerary.get("validation_report"),
                    profile_snapshot={
                        "slots": state.get("slots", {}),
                        "user_input": user_input,
                    },
                    weather_snapshot=result.get("weather"),
                )
                if saved:
                    saved_id = saved.id
        except Exception as e:
            logger.warning(f"Auto-save itinerary skipped (non-fatal): {e}")
    return saved_id

# Pattern to detect and strip saved-places footer from user text
_SAVED_PLACES_RE = re.compile(r'【用户收藏[^】]*】[\s\S]*$')


def _split_user_text(raw: str) -> tuple[str, str]:
    """Separate user's actual message from the saved-places footer.

    Returns (clean_text, saved_places_text).
    """
    raw = (raw or "").strip()
    if not raw:
        return "", ""
    m = _SAVED_PLACES_RE.search(raw)
    if m:
        clean = raw[:m.start()].strip()
        saved = m.group(0).strip()
        return clean, saved
    return raw, ""


@router.post("/dialog/message", response_model=DialogResponse)
async def dialog_message(request: DialogMessageRequest):
    """多轮对话：槽位收敛、组合建议、确认摘要、生成后修改分流。"""
    sid, state = await get_session(request.session_id)
    raw_text = (request.text or "").strip()

    # Phase 15.4: Strip saved-places footer before any processing
    text, saved_places_text = _split_user_text(raw_text)

    # ── 修正 2：GENERATING 态输入 → 提示 + 排队，不进分流 ──
    if state["stage"] == "generating":
        if text:
            state["queued"].append(text)
            await save_session(sid, state)
        return _resp(
            sid, state,
            "正在生成行程中，约需 30-60 秒～你的留言已记下，生成后继续。",
            queued=len(state["queued"]),
        )

    # ── 状态条手动编辑（任何阶段都可改）──
    if request.slot_override:
        changed = apply_slot_override(state, request.slot_override)
        if changed:
            state["stage"] = "confirming"
            await save_session(sid, state)
            return _resp(sid, state, build_summary(state), confirm=True)

    if not text:
        return _resp(sid, state, "我在听，说说你的想法～")

    # Phase 16.1: Append user message to conversation history
    append_message(state, "user", text)

    # ── Phase 16.1: Correction detection — user is fixing a mistake ──
    # Phase 16.1 bugfix: Only trigger correction when correction keywords
    # appear together with a NEW destination AND the message is NOT a question.
    _CORRECTION_KW_RE = re.compile(
        r'(?:不是|不对|不是说的|我说的是|我要的是|我想去的是|错了|搞错|搞反|应该是|更正|纠正)',
        re.IGNORECASE
    )
    _CORRECTION_CITY_RE = re.compile(
        r'[\u4e00-\u9fa5]{2,6}[市区县省镇]|(?:广州|成都|深圳|重庆|北京|上海|杭州|西安|长沙|厦门|大理|三亚|桂林|苏州|张家界|丽江|南京|武汉|青岛|大连|昆明|珠海|佛山|东莞|中山|惠州|增城|都江堰|从化|番禺|花都|南沙|义乌|昆山)',
        re.IGNORECASE
    )
    _IS_QUESTION_RE = re.compile(r'[？?]$|吗[呢吧]?[？?]?$|呢[？?]?$|吧[？?]?$')
    if (
        state["slots"].get("city")
        and _CORRECTION_KW_RE.search(text)
        and _CORRECTION_CITY_RE.search(text)
        and not _IS_QUESTION_RE.search(text)
    ):
        logger.info(f"Correction detected with city ref: '{text}'")
        old_city = state["slots"]["city"]
        state["slots"]["city"] = None
        reply = f"哎呀抱歉！我之前理解错啦，之前说的「{old_city}」不对对吧？你重新说一下要去哪里，我这次记牢！"
        append_message(state, "assistant", reply)
        await save_session(sid, state)
        return _resp(sid, state, reply, confirm=True)

    # ── Phase 12.1: 自由对话意图检测 ──
    # Phase 15.4: Use clean text (without saved-places footer) for classification
    intent = classify_intent(text)

    # Phase 15.4: Strengthen travel-intent detection — explicit travel statements
    # should always go through slot-fill, even if they look like chat
    _TRAVEL_INTENT_RE = re.compile(
        r'(?:想去|要去|去|打算去|计划去|准备去|想)[\u4e00-\u9fa5]+(?:玩|旅游|旅行|度假|游玩)'
    )
    # Phase 16.3: Detect explicit itinerary-generation intent — only these phrases
    # should bring user back to slot filling from pure chat mode.
    _GENERATE_INTENT_RE = re.compile(
        r'(?:生成|做个|来个|出个|给我|帮我|安排|规划|制定)[^。.！!]*(?:行程|攻略|路线|计划|方案|安排)'
        r'|(?:行程|攻略|路线|计划|方案)[^。.！!]*(?:生成|做|出|来|安排|规划)'
        r'|(?:赶紧|快|马上|直接|就|开始|确认)(?:生成|出|做|安排)'
        r'|生成(?:吧|了|呢)?(?:[。！.!?]|$)'
        r'|开[始始]生成'
    )
    if intent == "chat" and (_TRAVEL_INTENT_RE.search(text) or _GENERATE_INTENT_RE.search(text)):
        logger.info(f"Override intent: 'chat' → 'slot_fill' (travel/generate intent detected: '{text}')")
        intent = "slot_fill"

    if intent == "chat":
        # Free-form chat — don't extract slots, just have a conversation
        # Phase 16.3: 纯自然聊天，不追加规划提醒。
        # 用户在规划流程中提问（如"增城有什么好玩的"）时直接回答，
        # 只有当用户主动表达生成行程意图时才回到槽位收敛。
        try:
            from app.agents.chat_agent import free_chat
            history = get_history(state, max_turns=10)
            reply = await free_chat(
                user_text=text,
                slots_context=state["slots"],
                history=history,
            )
        except Exception as e:
            logger.warning(f"Free chat failed, falling back to slot fill: {e}")
            reply = "好问题！要不我们先继续规划行程？告诉我你想去的城市和天数吧～"

        # Phase 16.1: Append assistant reply to history before returning
        append_message(state, "assistant", reply)
        await save_session(sid, state)
        return _resp(sid, state, reply)

    # ── DELIVERED 后的修改分流 ──
    if state["stage"] == "delivered":
        return await _handle_modification(sid, state, text)

    # ── COLLECTING / CONFIRMING：槽位收敛 ──
    context = _slots_context(state["slots"])

    # Phase 15.4: Build extraction input with saved-places as context metadata,
    # not mixed into the user's actual message
    extract_parts = [f"用户当前输入：{text}"]
    if context:
        extract_parts.insert(0, f"已知偏好：{context}")
    if saved_places_text:
        # Saved places as BACKGROUND INFO, not as primary directive
        extract_parts.append(f"\n[背景信息] {saved_places_text}")

    # Phase 16.1: Add conversation history as context for better extraction
    history = get_history(state, max_turns=10)
    if history:
        history_text = "；".join(f"{m['role']}：{m['content']}" for m in history[-8:])
        extract_parts.append(f"\n[对话历史] {history_text}")

    extract_input = "\n".join(extract_parts)

    # Phase 15.3: Fast path for deferral phrases ("都可以你看着安排吧")
    # Skip LLM extraction entirely to prevent city-destination hallucination.
    if _DEFER_RE.search(text):
        logger.info(f"Deferral phrase detected: '{text}' — skipping profile extraction")
        # Still run next_action to fill defaults and transition to confirming
        action = next_action(state, text)
    else:
        try:
            extracted = await extract_profile(extract_input)
        except Exception as e:
            logger.error(f"Dialog profile extraction failed: {e}")
            return _resp(sid, state, "理解你的意思时出了点问题，能换个说法吗？")

        merge_slots(state, ground_extraction(extracted, text))
        action = next_action(state, text)

    # Phase 12.20 + 16.1: 状态机定动作，LLM 定语气 + 传入完整历史
    reply_text = action.get("reply", "")
    action["reply"] = await _naturalize_reply(action, state, text, history=history)

    # Phase 16.1: Append assistant reply to history
    append_message(state, "assistant", action["reply"])
    await save_session(sid, state)

    if action["type"] == "refuse":
        state["stage"] = "refused"
        await save_session(sid, state)
        return _resp(
            sid, state, action["reply"],
            suggestions=action.get("suggestions"),
            refused=True,
            refuse_reason=action.get("reason", ""),
        )
    if action["type"] == "suggest":
        return _resp(sid, state, action["reply"], suggestions=action["suggestions"])
    if action["type"] == "confirm":
        return _resp(sid, state, action["reply"], confirm=True)
    return _resp(sid, state, action["reply"])


@router.post("/dialog/generate", response_model=DialogResponse)
async def dialog_generate(
    request: DialogGenerateRequest,
    device_id: Optional[str] = Depends(get_device_id),
):
    """用户点「生成行程卡片」→ 复用生成管线（零改动）。"""
    sid, state = await get_session(request.session_id)

    if state["stage"] == "delivered" and state.get("itinerary"):
        return _resp(sid, state, "行程卡片已生成过啦，直接告诉我要改哪里就行。",
                     itinerary=state["itinerary"])

    state["stage"] = "generating"
    await save_session(sid, state)
    user_input = synthesize_input(state["slots"])
    logger.info(f"Dialog generate: {user_input}")

    try:
        result = await run_travel_workflow(user_input)
    except Exception as e:
        logger.error(f"Dialog generate failed: {e}", exc_info=True)
        state["stage"] = "confirming"
        raise error_response(502, "UPSTREAM_ERROR", "生成服务暂不可用，请稍后再试。")

    itinerary = result.get("itinerary") or {}
    queued_count = len(state["queued"])

    if not itinerary:
        state["stage"] = "confirming"
        await save_session(sid, state)
        err = result.get("error") or "行程生成失败，请再试一次。"
        return _resp(sid, state, f"抱歉，{err}\n{build_summary(state)}", confirm=True)

    state["itinerary"] = itinerary
    state["stage"] = "delivered"
    state["queued"] = []
    await save_session(sid, state)

    # Phase 8.1: Propagate coverage warning from orchestrator
    coverage_warning = result.get("coverage_warning") or None

    # ── Auto-save itinerary（PG 优先，本地文件回退；Phase 12.24 抽取共用）
    saved_id = await _auto_save_itinerary(state, itinerary, result, user_input, device_id)

    reply = _delivered_reply(coverage_warning, queued_count)
    return _resp(sid, state, reply, itinerary=itinerary, itinerary_id=saved_id,
                 coverage_warning=coverage_warning)

def _delivered_reply(coverage_warning: Optional[str], queued_count: int) -> str:
    reply = "行程卡片生成好啦 ✅ 点卡片看完整版；想改哪里直接说（比如「第二天太赶了」）。"
    if coverage_warning:
        reply = f"⚠️ {coverage_warning}\n\n{reply}"
    if queued_count:
        reply += f"（你生成中留的 {queued_count} 条留言，直接再说一遍即可）"
    return reply


@router.post("/dialog/generate/stream")
async def dialog_generate_stream(
    request: DialogGenerateRequest,
    device_id: Optional[str] = Depends(get_device_id),
):
    """SSE 版生成（Phase 12.24）：与 /agent/plan/stream 同一事件源的真实阶段进度。

    事件序列：progress × N → done（DialogResponse 全字段）/ error。
    会话状态机与自动保存逻辑与阻塞式 /dialog/generate 完全一致。
    """
    sid, state = await get_session(request.session_id)

    if state["stage"] == "delivered" and state.get("itinerary"):
        payload = _resp(
            sid, state, "行程卡片已生成过啦，直接告诉我要改哪里就行。",
            itinerary=state["itinerary"],
        ).model_dump()

        async def _already():
            yield f"data: {json.dumps({'event': 'done', 'data': payload}, ensure_ascii=False)}\n\n".encode("utf-8")

        return StreamingResponse(_already(), media_type="text/event-stream", headers=_SSE_HEADERS)

    state["stage"] = "generating"
    await save_session(sid, state)
    user_input = synthesize_input(state["slots"])
    logger.info(f"Dialog generate (stream): {user_input}")

    async def event_generator():
        final: Dict[str, Any] = {}
        try:
            async for event in run_travel_workflow_stream(user_input=user_input):
                if event.get("event") == "result" and isinstance(event.get("data"), dict):
                    final = event["data"]
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
        except Exception as e:
            logger.error(f"Dialog stream failed: {e}", exc_info=True)
            state["stage"] = "confirming"
            await save_session(sid, state)
            yield f"data: {json.dumps({'event': 'error', 'message': '生成服务暂不可用，请稍后再试。'}, ensure_ascii=False)}\n\n".encode("utf-8")
            return

        itinerary = final.get("itinerary") or {}
        queued_count = len(state["queued"])

        if not itinerary:
            state["stage"] = "confirming"
            await save_session(sid, state)
            err = final.get("error") or "行程生成失败，请再试一次。"
            yield f"data: {json.dumps({'event': 'error', 'message': err}, ensure_ascii=False)}\n\n".encode("utf-8")
            return

        state["itinerary"] = itinerary
        state["stage"] = "delivered"
        state["queued"] = []
        await save_session(sid, state)

        coverage_warning = final.get("coverage_warning") or None
        saved_id = await _auto_save_itinerary(state, itinerary, final, user_input, device_id)
        reply = _delivered_reply(coverage_warning, queued_count)

        done_payload = _resp(
            sid, state, reply,
            itinerary=itinerary, itinerary_id=saved_id,
            coverage_warning=coverage_warning,
        ).model_dump()
        yield f"data: {json.dumps({'event': 'done', 'data': done_payload}, ensure_ascii=False)}\n\n".encode("utf-8")

    return StreamingResponse(
        event_generator(), media_type="text/event-stream", headers=_SSE_HEADERS
    )


async def _handle_modification(sid: str, state: Dict[str, Any], text: str) -> DialogResponse:
    """DELIVERED 态：单项删除 → 规则分流 → LLM 兜底 → 反问。"""
    # Phase 12.27: 单项删除优先——"去掉 XX" 确定性处理，零 LLM
    try:
        removed = try_remove_item(state.get("itinerary"), text)
    except Exception as e:
        logger.warning(f"try_remove_item failed (non-fatal): {e}")
        removed = None
    if removed:
        if removed[0] == "__day_would_empty__":
            reply = f"第 {removed[1]} 天只剩「{removed[2]}」了，去掉这一天就空了～要不我帮你把这一天重新安排一下？"
            append_message(state, "assistant", reply)
            await save_session(sid, state)
            return _resp(sid, state, reply)
        state["stage"] = "delivered"
        reply = f"已把「{removed[0]}」从第 {removed[1]} 天去掉啦 ✅ 还想调整哪里？"
        append_message(state, "assistant", reply)
        await save_session(sid, state)
        return _resp(
            sid, state, reply,
            itinerary=state["itinerary"],
        )

    decision = classify_modification(text, state.get("itinerary"))
    if decision["type"] == "unknown":
        decision = await _classify_with_llm(text)

    dtype = decision["type"]

    if dtype == "local":
        itinerary = state["itinerary"]
        day_index = decision.get("day_index", 0)
        if not 0 <= day_index < len(itinerary.get("days", [])):
            day_index = 0
        profile = {
            "destination": state["slots"].get("city", ""),
            "days": state["slots"].get("days", 3),
            "tags": state["slots"].get("tags", []),
            "companions": state["slots"].get("companions", ""),
        }
        places: List[Dict[str, Any]] = []
        try:
            places = await retrieve(profile, text, top_k=10)
        except Exception as e:
            logger.warning(f"RAG retrieve failed for dialog regen (non-fatal): {e}")
        try:
            updated = await regenerate_day(
                itinerary=itinerary,
                day_index=day_index,
                feedback=text,
                profile=profile,
                places=places,
            )
        except (ValueError, RuntimeError) as e:
            reply = f"修改第 {day_index + 1} 天时出错了：{e}"
            append_message(state, "assistant", reply)
            await save_session(sid, state)
            return _resp(sid, state, reply)
        state["itinerary"] = updated
        reply = f"第 {day_index + 1} 天已重新安排 ✅ 其他天没动。还要继续调吗？"
        append_message(state, "assistant", reply)
        await save_session(sid, state)
        return _resp(
            sid, state, reply,
            itinerary=updated,
        )

    if dtype == "slot_change":
        updates = decision.get("slot_updates") or {}
        apply_slot_override(state, updates)
        state["stage"] = "confirming"
        summary = build_summary(state)
        append_message(state, "assistant", summary)
        await save_session(sid, state)
        return _resp(sid, state, summary, confirm=True)

    if dtype == "global":
        state["stage"] = "confirming"
        summary = "好的，整体重新规划。\n" + build_summary(state)
        append_message(state, "assistant", summary)
        await save_session(sid, state)
        return _resp(sid, state, summary, confirm=True)

    # 仍然不明 → 反问（二选一按钮）
    reply = "想确认一下：你是只想改某一天，还是整体重新规划？"
    append_message(state, "assistant", reply)
    await save_session(sid, state)
    return _resp(
        sid, state, reply,
    )
