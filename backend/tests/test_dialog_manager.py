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

    def test_ready_goes_confirming(self):
        st = _state()
        st["slots"].update({"city": "重庆", "days": 3})
        action = next_action(st)
        assert action["type"] == "confirm"
        assert st["stage"] == "confirming"

    def test_followup_cap_then_defaults(self):
        st = _state()
        st["followups_used"] = 3
        action = next_action(st)
        assert action["type"] == "confirm"
        assert st["slots"]["city"] == "重庆"
        assert st["slots"]["days"] == 3
        assert "默认值" in action["reply"]

    def test_followup_counter_increments(self):
        st = _state()
        next_action(st)
        next_action(st)
        assert st["followups_used"] == 2


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
