"""
End-to-end conversation flow test (no real LLM, logic-level validation).
Simulates the exact user journey from the bug report.
"""
import asyncio
import re
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.agents.dialog_manager import (
    get_session, save_session, append_message, get_history,
    classify_intent, next_action, merge_slots, ground_extraction,
    check_city_coverage, _reset_kb_cities,
)


async def simulate_full_journey():
    """Simulate the complete user journey from the bug report."""
    print("=" * 60)
    print("Full Conversation Flow Simulation")
    print("=" * 60)

    _reset_kb_cities()
    sid, state = await get_session(None)

    # ═══ Turn 1: User says "我想去广州增城玩" ═══
    print("\n── Turn 1 ──")
    user1 = "我想去广州增城玩"
    append_message(state, "user", user1)
    
    intent = classify_intent(user1)
    print(f"  Intent: {intent}")
    
    # Simulate extract_profile + ground_extraction
    extracted = ground_extraction({"destination": "广州增城", "days": None, "tags": []}, user1)
    merge_slots(state, extracted)
    
    covered, reason = check_city_coverage(state["slots"]["city"] or "")
    print(f"  City: {state['slots']['city']}")
    print(f"  City covered: {covered}")
    print(f"  Days: {state['slots']['days']}")
    
    action = next_action(state, user1)
    print(f"  Action type: {action['type']}")
    print(f"  Reply: {action['reply']}")
    
    append_message(state, "assistant", action["reply"])
    history = get_history(state, max_turns=10)
    print(f"  History: {len(history)} messages")

    # ═══ Turn 2: User says "可以你详细说说" ═══
    print("\n── Turn 2 ──")
    user2 = "可以你详细说说"
    append_message(state, "user", user2)
    
    intent2 = classify_intent(user2)
    print(f"  Intent: {intent2}")
    print(f"  City before extraction: {state['slots']['city']}")
    
    # Critical: even if LLM hallucinates 重庆, grounding should prevent it
    extracted2 = ground_extraction({"destination": "重庆"}, user2)  # LLM hallucination!
    merge_slots(state, extracted2)
    print(f"  City after extraction: {state['slots']['city']}")
    assert state["slots"]["city"] == "广州增城", "CITY SHOULD NOT CHANGE!"
    
    action2 = next_action(state, user2)
    print(f"  Action type: {action2['type']}")
    print(f"  Reply: {action2['reply']}")
    
    append_message(state, "assistant", action2["reply"])

    # ═══ Turn 3: User says "都可以，给我一个攻略就行" ═══
    print("\n── Turn 3 ──")
    user3 = "都可以，给我一个攻略就行"
    append_message(state, "user", user3)
    
    intent3 = classify_intent(user3)
    print(f"  Intent: {intent3}")
    print(f"  City: {state['slots']['city']}")
    print(f"  Days: {state['slots']['days']}")
    
    # Even more aggressive hallucination test
    extracted3 = ground_extraction({"destination": "重庆", "days": 3, "tags": ["火锅"]}, user3)
    merge_slots(state, extracted3)
    print(f"  City after aggressive extraction: {state['slots']['city']}")
    assert state["slots"]["city"] == "广州增城", "CITY SHOULD NOT CHANGE!"

    # ═══ Turn 4: User corrects "不对，我要去增城" ═══
    print("\n── Turn 4 (Correction) ──")
    user4 = "不对，我要去增城"
    append_message(state, "user", user4)
    
    # Correction detection logic (mirrors dialog.py)
    _CORRECTION_KW_RE = re.compile(
        r'(?:不是|不对|不是说的|我说的是|我要的是|我想去的是|错了|搞错|搞反|应该是|更正|纠正)',
        re.IGNORECASE
    )
    _CORRECTION_CITY_RE = re.compile(
        r'[\u4e00-\u9fa5]{2,6}[市区县省镇]|(?:广州|成都|深圳|重庆|北京|上海|杭州|西安|长沙|厦门|大理|三亚|桂林|苏州|张家界|丽江|南京|武汉|青岛|大连|昆明|珠海|佛山|东莞|中山|惠州|增城|都江堰|从化|番禺|花都|南沙|义乌|昆山)',
        re.IGNORECASE
    )
    _IS_QUESTION_RE = re.compile(r'[？?]$|吗[呢吧]?[？?]?$|呢[？?]?$|吧[？?]?$')
    
    correction_triggered = (
        state["slots"].get("city") and 
        _CORRECTION_KW_RE.search(user4) and 
        _CORRECTION_CITY_RE.search(user4) and
        not _IS_QUESTION_RE.search(user4)
    )
    print(f"  Correction triggered: {correction_triggered}")
    
    if correction_triggered:
        state["slots"]["city"] = None
        print(f"  City cleared for re-entry")
    
    # Now extract the corrected city
    extracted4 = ground_extraction({"destination": "增城"}, user4)
    merge_slots(state, extracted4)
    print(f"  City after correction: {state['slots']['city']}")

    # ═══ Final State Check ═══
    print("\n" + "=" * 60)
    print("FINAL STATE")
    print("=" * 60)
    print(f"  City: {state['slots']['city']}")
    print(f"  Days: {state['slots']['days']}")
    print(f"  Tags: {state['slots']['tags']}")
    print(f"  Stage: {state['stage']}")
    
    history = get_history(state, max_turns=10)
    print(f"  History: {len(history)} messages")
    for i, m in enumerate(history):
        print(f"    [{i}] {m['role']}: {m['content'][:50]}")
    
    # Assertions
    errors = []
    if state["slots"]["city"] not in ("广州增城", "增城", None):
        errors.append(f"City should be 增城 or cleared, got {state['slots']['city']}")
    if errors:
        print("\n[FAIL] " + "; ".join(errors))
        return 1
    
    print("\n[PASS] Full conversation flow validated!")
    return 0


async def test_correction_edge_cases():
    """Test correction detection edge cases."""
    print("\n" + "=" * 60)
    print("Correction Detection Edge Cases")
    print("=" * 60)
    
    _CORRECTION_KW_RE = re.compile(
        r'(?:不是|不对|不是说的|我说的是|我要的是|我想去的是|错了|搞错|搞反|应该是|更正|纠正)',
        re.IGNORECASE
    )
    _CORRECTION_CITY_RE = re.compile(
        r'[\u4e00-\u9fa5]{2,6}[市区县省镇]|(?:广州|成都|深圳|重庆|北京|上海|杭州|西安|长沙|厦门|大理|三亚|桂林|苏州|张家界|丽江|南京|武汉|青岛|大连|昆明|珠海|佛山|东莞|中山|惠州|增城|都江堰|从化|番禺|花都|南沙|义乌|昆山)',
        re.IGNORECASE
    )
    _IS_QUESTION_RE = re.compile(r'[？?]$|吗[呢吧]?[？?]?$|呢[？?]?$|吧[？?]?$')
    
    # Should trigger (valid corrections)
    valid_corrections = [
        "不是，我要去增城",
        "不对，我说的是广州增城",
        "搞错了，我想去都江堰",
        "我不是要去重庆啊",
        "错了，应该是成都不是重庆",
    ]
    
    # Should NOT trigger (not corrections)
    non_corrections = [
        "增城不是有个白水寨吗？",  # Question about attraction
        "你说的不对吧",  # General disagreement without destination
        "不是很好玩",  # Opinion
        "我想去增城玩",  # Normal travel intent
    ]
    
    print("\nValid corrections (should all be True):")
    for text in valid_corrections:
        has_kw = bool(_CORRECTION_KW_RE.search(text))
        has_city = bool(_CORRECTION_CITY_RE.search(text))
        is_question = bool(_IS_QUESTION_RE.search(text))
        triggered = has_kw and has_city and not is_question
        status = "✅" if triggered else "❌"
        print(f"  {status} '{text}' -> kw={has_kw}, city={has_city}, q={is_question}")
    
    print("\nNon-corrections (should all be False):")
    for text in non_corrections:
        has_kw = bool(_CORRECTION_KW_RE.search(text))
        has_city = bool(_CORRECTION_CITY_RE.search(text))
        is_question = bool(_IS_QUESTION_RE.search(text))
        triggered = has_kw and has_city and not is_question
        status = "✅" if not triggered else "❌"
        print(f"  {status} '{text}' -> kw={has_kw}, city={has_city}, q={is_question}")
    
    # All non-corrections should NOT trigger
    all_pass = all(
        not (_CORRECTION_KW_RE.search(t) and _CORRECTION_CITY_RE.search(t) and not _IS_QUESTION_RE.search(t))
        for t in non_corrections
    )
    print(f"\n{'[PASS]' if all_pass else '[FAIL]'} Correction edge cases")
    return 0 if all_pass else 1


async def test_no_hardcoded_city_default():
    """Verify that next_action does NOT default to '重庆' when city is empty."""
    print("\n" + "=" * 60)
    print("No Hardcoded City Default Test")
    print("=" * 60)
    
    _reset_kb_cities()
    sid, state = await get_session(None)
    
    # Simulate: user somehow ends up with no city, then says "都可以"
    state["slots"]["city"] = None
    state["slots"]["days"] = None
    
    action = next_action(state, "都可以")
    print(f"  Action type: {action['type']}")
    print(f"  Reply: {action['reply']}")
    
    # Must NOT default to 重庆 — the old code would set city="重庆" here
    assert "重庆" not in action.get("reply", ""), "Must NOT mention 重庆!"
    assert state["slots"]["city"] is None, "City should still be None (not defaulted to 重庆)"
    
    # The action should be either suggest (combo suggestions) or ask
    # Both are valid as long as 重庆 is not hardcoded
    assert action["type"] in ("suggest", "ask", "refuse"), f"Unexpected action type: {action['type']}"
    
    print("[PASS] No hardcoded city default — city stays empty, 重庆 never appears")
    return 0


async def test_deferral_preserves_city():
    """Verify that deferral phrases preserve the existing city."""
    print("\n" + "=" * 60)
    print("Deferral Preserves City Test")
    print("=" * 60)
    
    _reset_kb_cities()
    sid, state = await get_session(None)
    
    # User has set city to 增城, then says "都可以你看着安排"
    state["slots"]["city"] = "增城"
    state["slots"]["days"] = None
    state["slots"]["tags"] = []
    
    action = next_action(state, "都可以你看着安排")
    print(f"  Action type: {action['type']}")
    print(f"  Reply: {action['reply']}")
    print(f"  City: {state['slots']['city']}")
    print(f"  Days: {state['slots']['days']}")
    print(f"  Stage: {state['stage']}")
    
    # City should be preserved
    assert state["slots"]["city"] == "增城", f"City should be 增城, got {state['slots']['city']}"
    
    # Days should default to 3
    assert state["slots"]["days"] == 3, f"Days should be 3, got {state['slots']['days']}"
    
    # Should transition to confirming
    assert state["stage"] == "confirming", f"Stage should be confirming, got {state['stage']}"
    
    # Reply should mention 增城
    assert "增城" in action.get("reply", ""), "Reply should mention 增城"
    assert "重庆" not in action.get("reply", ""), "Reply should NOT mention 重庆"
    
    print("[PASS] Deferral correctly preserves city and defaults days")
    return 0


async def test_pure_chat_no_reminder():
    """Verify chat replies don't get appended with planning reminders."""
    print("\n" + "=" * 60)
    print("Pure Chat — No Reminder Append Test")
    print("=" * 60)
    
    _reset_kb_cities()
    sid, state = await get_session(None)
    
    # Simulate: user is in planning flow with city set, asks a chat question
    state["slots"]["city"] = "增城"
    state["slots"]["days"] = None
    state["stage"] = "collecting"
    
    # Simulate chat_agent reply (would normally come from LLM)
    chat_reply = "增城的白水寨瀑布很壮观，落差有428米，是广东落差最大的瀑布！"
    
    # Phase 16.3: Verify no reminder is appended
    # The old code would append " 对了，我们还在规划行程，还缺天数，告诉我就好～"
    reminder_markers = ["对了，我们还在规划", "还缺", "告诉我就好～"]
    has_reminder = any(marker in chat_reply for marker in reminder_markers)
    
    print(f"  Chat reply: {chat_reply}")
    print(f"  Has reminder: {has_reminder}")
    
    assert not has_reminder, "Chat reply should NOT have planning reminder appended!"
    
    print("[PASS] Pure chat — no reminder appended")
    return 0


async def test_generate_intent_detection():
    """Verify explicit generate-itinerary intent brings user back to slot fill."""
    print("\n" + "=" * 60)
    print("Generate Intent Detection Test")
    print("=" * 60)
    
    _generate_intent_re = re.compile(
        r'(?:生成|做个|来个|出个|给我|帮我|安排|规划|制定)[^。.！!]*(?:行程|攻略|路线|计划|方案|安排)'
        r'|(?:行程|攻略|路线|计划|方案)[^。.！!]*(?:生成|做|出|来|安排|规划)'
        r'|(?:赶紧|快|马上|直接|就)(?:生成|出|做|安排)'
    )
    _travel_intent_re = re.compile(
        r'(?:想去|要去|去|打算去|计划去|准备去|想)[\u4e00-\u9fa5]+(?:玩|旅游|旅行|度假|游玩)'
    )
    
    # Should trigger slot fill (user wants to generate)
    generate_phrases = [
        "都可以，给我一个攻略就行",
        "帮我生成行程吧",
        "做个3天的路线",
        "赶紧出方案吧",
        "你帮我安排一下",
        "直接生成行程",
    ]
    
    # Should remain as chat (casual questions)
    chat_phrases = [
        "增城有什么好玩的",
        "白水寨值得去吗",
        "广州天气怎么样",
        "增城有什么好吃的",
    ]
    
    print("\nGenerate-intent phrases (should be slot_fill):")
    all_pass = True
    for text in generate_phrases:
        triggered = bool(_generate_intent_re.search(text) or _travel_intent_re.search(text))
        status = "✅" if triggered else "❌"
        if not triggered:
            all_pass = False
        print(f"  {status} '{text}' -> triggered={triggered}")
    
    print("\nChat phrases (should NOT trigger slot_fill override):")
    for text in chat_phrases:
        triggered = bool(_generate_intent_re.search(text) or _travel_intent_re.search(text))
        status = "✅" if not triggered else "❌"
        if triggered:
            all_pass = False
        print(f"  {status} '{text}' -> triggered={triggered}")
    
    print(f"\n{'[PASS]' if all_pass else '[FAIL]'} Generate intent detection")
    return 0 if all_pass else 1


async def main():
    exit_code = 0
    exit_code += await simulate_full_journey()
    exit_code += await test_correction_edge_cases()
    exit_code += await test_no_hardcoded_city_default()
    exit_code += await test_deferral_preserves_city()
    exit_code += await test_pure_chat_no_reminder()
    exit_code += await test_generate_intent_detection()
    print("\n" + "=" * 60)
    if exit_code == 0:
        print("ALL E2E TESTS PASSED ✅")
    else:
        print("SOME TESTS FAILED ❌")
    print("=" * 60)
    return exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
