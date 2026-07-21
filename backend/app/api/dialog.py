"""
TravelMind Agent — Dialog API (对话式规划 · 意图层)

POST /api/v1/dialog/message   — 多轮对话（槽位收敛 / 修改分流）
POST /api/v1/dialog/generate  — 确认后触发生成（复用生成管线，零改动）

只做意图层：槽位、状态机、分流判定；生成能力全部复用
（run_travel_workflow / regenerate_day / itinerary_contract）。
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.dialog_manager import (
    apply_slot_override,
    build_summary,
    classify_modification,
    get_session,
    merge_slots,
    next_action,
    save_session,
    synthesize_input,
)
from app.agents.orchestrator import run_travel_workflow
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
        result = await get_llm_provider().chat_structured(
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

@router.post("/dialog/message", response_model=DialogResponse)
async def dialog_message(request: DialogMessageRequest):
    """多轮对话：槽位收敛、组合建议、确认摘要、生成后修改分流。"""
    sid, state = await get_session(request.session_id)
    text = (request.text or "").strip()

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

    # ── DELIVERED 后的修改分流 ──
    if state["stage"] == "delivered":
        return await _handle_modification(sid, state, text)

    # ── COLLECTING / CONFIRMING：槽位收敛 ──
    context = _slots_context(state["slots"])
    extract_input = f"已知偏好：{context}\n用户补充：{text}" if context else text
    try:
        extracted = await extract_profile(extract_input)
    except Exception as e:
        logger.error(f"Dialog profile extraction failed: {e}")
        return _resp(sid, state, "理解你的意思时出了点问题，能换个说法吗？")

    merge_slots(state, extracted)
    action = next_action(state)
    await save_session(sid, state)

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
        raise HTTPException(status_code=502, detail="生成服务暂不可用，请稍后再试。")

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

    # ── Auto-save itinerary to PostgreSQL (non-blocking, best-effort) ──
    saved_id: Optional[str] = None
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

    reply = "行程卡片生成好啦 ✅ 点卡片看完整版；想改哪里直接说（比如「第二天太赶了」）。"
    if queued_count:
        reply += f"（你生成中留的 {queued_count} 条留言，直接再说一遍即可）"
    return _resp(sid, state, reply, itinerary=itinerary, itinerary_id=saved_id)


async def _handle_modification(sid: str, state: Dict[str, Any], text: str) -> DialogResponse:
    """DELIVERED 态：规则分流 → LLM 兜底 → 反问。"""
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
            return _resp(sid, state, f"修改第 {day_index + 1} 天时出错了：{e}")
        state["itinerary"] = updated
        await save_session(sid, state)
        return _resp(
            sid, state,
            f"第 {day_index + 1} 天已重新安排 ✅ 其他天没动。还要继续调吗？",
            itinerary=updated,
        )

    if dtype == "slot_change":
        updates = decision.get("slot_updates") or {}
        apply_slot_override(state, updates)
        state["stage"] = "confirming"
        await save_session(sid, state)
        return _resp(sid, state, build_summary(state), confirm=True)

    if dtype == "global":
        state["stage"] = "confirming"
        await save_session(sid, state)
        summary = "好的，整体重新规划。\n" + build_summary(state)
        return _resp(sid, state, summary, confirm=True)

    # 仍然不明 → 反问（二选一按钮）
    return _resp(
        sid, state,
        "想确认一下：你是只想改某一天，还是整体重新规划？",
        suggestions=[
            {"label": "只改某一天", "text": "只改某一天"},
            {"label": "整体重新规划", "text": "整体重新规划"},
        ],
    )
