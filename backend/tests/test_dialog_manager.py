"""dialog_manager 纯逻辑单元测试（无外部调用）。

覆盖：槽位合并（含 nullish 过滤）/ 阶段推进与追问上限 / 组合建议 /
修改分流（天数限定词优先、slot_change 前置条件、整体词、POI 命中）/
摘要与输入合成 / 槽位覆盖。
"""

from app.agents.dialog_manager import (
    DEFAULT_SLOTS,
    apply_slot_override,
    build_summary,
    classify_modification,
    combo_suggestions,
    merge_slots,
    next_action,
    synthesize_input,
)


def _state(**over):
    return {
        "stage": "collecting",
        "slots": dict(DEFAULT_SLOTS, tags=[]),
        "followups_used": 0,
        "itinerary": None,
        "queued": [],
        "touched": 0,
        **over,
    }


class TestMergeSlots:
    def test_basic_merge(self):
        st = _state()
        changed = merge_slots(st, {
            "destination": "重庆", "days": 3, "companions": "家庭",
            "budget_level": "舒适", "tags": ["夜景", "美食"], "travel_style": "休闲",
        })
        # travel_style「休闲」与默认 pace 相同、budget「舒适」与默认相同，不计入变更
        assert set(changed) == {"city", "days", "companions", "tags"}
        assert st["slots"]["city"] == "重庆"
        assert st["slots"]["days"] == 3
        assert st["slots"]["tags"] == ["夜景", "美食"]

    def test_nullish_city_not_merged(self):
        for bad in ("null", "none", "随便", "都可以", "你定", "不知道", ""):
            st = _state()
            merge_slots(st, {"destination": bad})
            assert st["slots"]["city"] is None, f"{bad!r} 不应入槽"

    def test_empty_values_never_overwrite(self):
        st = _state()
        st["slots"]["city"] = "重庆"
        merge_slots(st, {"destination": "", "days": None})
        assert st["slots"]["city"] == "重庆"

    def test_tags_append_and_cap(self):
        st = _state()
        st["slots"]["tags"] = ["夜景"]
        merge_slots(st, {"tags": ["美食", "火锅", "夜景"]})
        assert st["slots"]["tags"] == ["夜景", "美食", "火锅"]
        assert len(st["slots"]["tags"]) <= 8


class TestNextAction:
    def test_missing_city_gives_combo(self):
        st = _state()
        action = next_action(st)
        assert action["type"] == "suggest"
        assert 1 <= len(action["suggestions"]) <= 3

    def test_missing_days_asks(self):
        st = _state()
        st["slots"]["city"] = "重庆"
        action = next_action(st)
        assert action["type"] == "ask"
        assert "几天" in action["reply"]

    def test_city_days_asks_preferences(self):
        """Phase 12.25 核心：只有城市+天数时不得推卡片，先问偏好。"""
        st = _state()
        st["slots"].update({"city": "南宁", "days": 3})
        action = next_action(st)
        assert action["type"] == "ask"
        assert "怎么玩" in action["reply"] or "偏好" in action["reply"]
        assert st["stage"] == "collecting"  # 不进入 confirming

    def test_full_slots_confirm(self):
        st = _state()
        st["slots"].update({"city": "重庆", "days": 3, "tags": ["美食"]})
        action = next_action(st)
        assert action["type"] == "confirm"
        assert st["stage"] == "confirming"

    def test_defer_phrase_confirms_with_defaults(self):
        """放权语「随便你看着办」→ 跳过剩余追问，默认值明示后确认。"""
        st = _state()
        st["slots"]["city"] = "南宁"
        action = next_action(st, text="随便，你看着办吧")
        assert action["type"] == "confirm"
        assert st["slots"]["days"] == 3
        assert "默认值" in action["reply"]

    def test_each_slot_asked_only_once(self):
        """同一槽位不重复追问：忽略天数问题 → 下一轮问偏好而非再问天数。"""
        st = _state()
        st["slots"]["city"] = "南宁"
        a1 = next_action(st)
        assert a1["type"] == "ask" and "几天" in a1["reply"]
        # 用户答非所问，天数仍空 → 不应再问天数
        a2 = next_action(st)
        assert not (a2["type"] == "ask" and "几天" in a2["reply"])

    def test_followup_cap_then_defaults(self):
        st = _state()
        st["followups_used"] = 3
        action = next_action(st)
        # Phase 16.2: 城市为空时不再默认填"重庆"，而是继续追问城市
        assert action["type"] == "ask"
        assert st["slots"]["city"] is None
        assert "重庆" not in action["reply"]

    def test_followup_counter_increments(self):
        st = _state()
        next_action(st)
        next_action(st)
        assert st["followups_used"] == 2


class TestTryRemoveItem:
    """Phase 12.27：delivered 态单项确定性删除（"去掉 XX"）。"""

    def _it(self):
        return {
            "trip": {"city": "重庆", "daysCount": 2, "stats": []},
            "days": [
                {"day": 1, "items": [
                    {"poi": "洪崖洞", "time": "09:00", "note": ""},
                    {"poi": "解放碑", "time": "14:00", "note": ""},
                ]},
                {"day": 2, "items": [
                    {"poi": "磁器口古镇", "time": "09:00", "note": ""},
                ]},
            ],
        }

    def test_remove_named_item(self):
        from app.agents.dialog_manager import try_remove_item
        it = self._it()
        r = try_remove_item(it, "把洪崖洞去掉")
        assert r == ("洪崖洞", 1)
        pois = [i["poi"] for i in it["days"][0]["items"]]
        assert pois == ["解放碑"]

    def test_remove_by_normalized_name(self):
        from app.agents.dialog_manager import try_remove_item
        it = self._it()
        # 磁器口古镇移到第 1 天（2 项），验证核心名匹配且不受空天保护影响
        it["days"][0]["items"].append(it["days"][1]["items"].pop(0))
        r = try_remove_item(it, "磁器口不想去了")
        assert r == ("磁器口古镇", 1)

    def test_no_match_returns_none(self):
        from app.agents.dialog_manager import try_remove_item
        it = self._it()
        assert try_remove_item(it, "去掉大熊猫基地") is None
        assert try_remove_item(it, "今天天气怎么样") is None

    def test_day_would_empty_guard(self):
        from app.agents.dialog_manager import try_remove_item
        it = self._it()
        r = try_remove_item(it, "把磁器口古镇删掉")
        assert r and r[0] == "__day_would_empty__"
        assert len(it["days"][1]["items"]) == 1  # 未删

    def test_stats_recomputed(self):
        from app.agents.dialog_manager import try_remove_item
        it = self._it()
        try_remove_item(it, "去掉洪崖洞")
        stats = {s["label"]: s["value"] for s in it["trip"]["stats"]}
        assert stats.get("计划地点") == "2 个"  # 3 项游览删 1 → 2


class TestGroundExtraction:
    """Phase 12.25 接地校验：LLM 提取值必须有原文依据。

    根因回归：「我想去惠州玩」被 extract_profile 补出 days=3、
    tags=["休闲","自然"]，槽位假满 → 直接推生成卡片。"""

    def test_fabricated_days_and_tags_dropped(self):
        from app.agents.dialog_manager import ground_extraction
        out = ground_extraction(
            {"destination": "惠州", "days": 3, "tags": ["休闲", "自然"]},
            "我想去惠州玩",
        )
        assert out["days"] is None
        assert out["tags"] == []
        assert out["destination"] == "惠州"  # 城市放行（覆盖校验兜底）

    def test_days_with_cue_kept(self):
        from app.agents.dialog_manager import ground_extraction
        out = ground_extraction({"days": 3, "tags": []}, "重庆3日游")
        assert out["days"] == 3

    def test_tag_synonym_cues(self):
        from app.agents.dialog_manager import ground_extraction
        out = ground_extraction({"tags": ["美食", "休闲"]}, "想吃粉")
        assert out["tags"] == ["美食"]  # 吃→美食 放行；休闲 无依据丢弃

    def test_tag_literal_kept(self):
        from app.agents.dialog_manager import ground_extraction
        out = ground_extraction({"tags": ["网红打卡"]}, "想去网红打卡地")
        assert out["tags"] == ["网红打卡"]

    def test_companions_cue(self):
        from app.agents.dialog_manager import ground_extraction
        out = ground_extraction({"companions": "家庭"}, "想带爸妈出去玩")
        assert out["companions"] == "家庭"
        out2 = ground_extraction({"companions": "家庭"}, "想去南宁")
        assert out2["companions"] is None

    def test_budget_and_pace_cues(self):
        from app.agents.dialog_manager import ground_extraction
        out = ground_extraction(
            {"budget_level": "经济", "travel_style": "休闲"}, "预算有限，想穷游")
        assert out["budget_level"] == "经济"
        assert out["travel_style"] is None  # 无节奏线索


class TestComboSuggestions:
    def test_pool_size_and_shape(self):
        st = _state()
        combos = combo_suggestions(st)
        assert 1 <= len(combos) <= 3
        for c in combos:
            assert "city" in c and "days" in c and "label" in c


class TestClassifyModification:
    IT = {
        "days": [
            {"day": 1, "theme": "D1", "title": "t", "items": [{"time": "09:00", "poi": "洪崖洞", "note": "n"}], "eat": "x"},
            {"day": 2, "theme": "D2", "title": "t", "items": [{"time": "10:00", "poi": "磁器口古镇", "note": "n"}], "eat": "y"},
        ]
    }

    def test_day_qualifier_forces_local(self):
        d = classify_modification("第二天太赶了", self.IT)
        assert d["type"] == "local" and d["day_index"] == 1

    def test_boundary_case_zoo(self):
        d = classify_modification("第二天改去动物园", self.IT)
        assert d["type"] == "local" and d["day_index"] == 1

    def test_slot_days_change_requires_no_day_qualifier(self):
        d = classify_modification("改成4天", self.IT)
        assert d["type"] == "slot_change" and d["slot_updates"]["days"] == 4

    def test_budget_change(self):
        d = classify_modification("预算砍半", self.IT)
        assert d["type"] == "slot_change" and d["slot_updates"]["budget_level"] == "经济"

    def test_global_word(self):
        d = classify_modification("整体重新规划", self.IT)
        assert d["type"] == "global"

    def test_day_qualifier_beats_slot_pattern(self):
        # 「第2天」是天数限定词，按用户修正 1 必须走 local 而不是 slot_change
        d = classify_modification("第2天改成4个景点", self.IT)
        assert d["type"] == "local"

    def test_poi_hit_locates_day(self):
        d = classify_modification("把洪崖洞换了", self.IT)
        assert d["type"] == "local" and d["day_index"] == 0

    def test_unknown(self):
        d = classify_modification("我想吃烧烤", self.IT)
        assert d["type"] == "unknown"


class TestSummaryAndSynthesis:
    def test_summary_contains_slots(self):
        st = _state()
        st["slots"].update({"city": "重庆", "days": 3, "companions": "家庭", "tags": ["夜景"]})
        s = build_summary(st)
        assert "重庆" in s and "3 天" in s and "家庭" in s and "夜景" in s

    def test_synthesize_input(self):
        text = synthesize_input({
            "city": "重庆", "days": 3, "companions": "家庭",
            "tags": ["夜景", "美食"], "pace": "休闲", "budget_level": "舒适",
        })
        assert "重庆3日游" in text and "夜景" in text


class TestSlotOverride:
    def test_forced_change(self):
        st = _state()
        changed = apply_slot_override(st, {"days": 4})
        assert changed == ["days"] and st["slots"]["days"] == 4
