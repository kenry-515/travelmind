"""recommendation_agent 单元测试：6 因子评分的纯函数与主流程（外部调用全部 mock）。

特别包含匿名化 bug 回归守卫：RAG 嵌套结构候选的扁平字段必须出现在结果顶层。
"""

import asyncio

import pytest

from app.agents import recommendation_agent as ra


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestScorePreference:
    def test_empty_user_tags_neutral(self):
        assert ra._score_preference([], ["美食"]) == 0.5

    def test_empty_place_tags_weak(self):
        assert ra._score_preference(["美食"], []) == 0.2

    def test_perfect_overlap(self):
        assert ra._score_preference(["美食", "夜景"], ["美食", "夜景"]) == 1.0

    def test_partial_overlap(self):
        score = ra._score_preference(["美食", "夜景", "古镇"], ["美食"])
        assert 0.2 < score < 1.0


class TestScoreBudget:
    def test_exact(self):
        assert ra._score_budget("舒适", "适中") == 1.0 or ra._score_budget("适中", "适中") == 1.0

    def test_one_level_off(self):
        assert ra._score_budget("穷游", "适中") == 0.6

    def test_two_levels_off(self):
        assert ra._score_budget("穷游", "高端") == 0.2

    def test_empty_budget_neutral(self):
        assert ra._score_budget("", "适中") == 0.5

    def test_unknown_place_price_neutral(self):
        assert ra._score_budget("舒适", "未知") == 0.5


class TestScoreTime:
    def test_exact_month(self):
        assert ra._score_time(7, "夏季") == 1.0

    def test_adjacent_month(self):
        assert ra._score_time(6, "7月") == 0.7

    def test_far_month(self):
        assert ra._score_time(1, "7月") == 0.3

    def test_zero_month_neutral(self):
        assert ra._score_time(0, "夏季") == 0.5


class TestReliability:
    def test_known_sources(self):
        assert ra._get_reliability("wikidata+amap") == 0.9
        assert ra._get_reliability("amap") == 0.8
        assert ra._get_reliability("wikidata") == 0.7

    def test_unknown_neutral(self):
        assert ra._get_reliability("whatever") == 0.5
        assert ra._get_reliability("") == 0.5


class TestMetadata:
    def test_nested_chroma_shape(self):
        c = {"id": "x", "metadata": {"name": "洪崖洞", "city": "重庆", "tags": "夜景,网红打卡"}}
        p = ra._extract_metadata(c)
        assert p["name"] == "洪崖洞"
        assert p["tags"] == ["夜景", "网红打卡"]

    def test_flat_shape(self):
        p = ra._extract_metadata({"name": "磁器口", "city": "重庆", "tags": ["古镇"]})
        assert p["name"] == "磁器口"

    def test_parse_tags_variants(self):
        assert ra._parse_tags("夜景, 美食") == ["夜景", "美食"]
        assert ra._parse_tags(["古镇"]) == ["古镇"]
        assert ra._parse_tags(None) == []


class TestRecommendMain:
    """recommend() 主流程：amap 服务 mock 为 None（中立位置分）。"""

    def test_sorted_and_flattened(self, monkeypatch):
        monkeypatch.setattr(ra, "_get_amap_service", lambda: None)

        candidates = [
            # RAG/Chroma 嵌套形态（匿名化 bug 的来源）
            {"id": "c1", "metadata": {"name": "洪崖洞", "city": "重庆", "tags": "夜景,网红打卡",
                                      "price_level": "适中", "popularity_score": 9, "source": "amap"}},
            {"id": "c2", "metadata": {"name": "磁器口古镇", "city": "重庆", "tags": "古镇",
                                      "price_level": "经济", "popularity_score": 8, "source": "wikidata"}},
        ]
        profile = {"tags": ["夜景"], "budget_level": "舒适", "travel_month": 0, "days": 3}

        results = run(ra.recommend(profile, candidates, trends=[]))

        assert len(results) == 2
        # 排序：洪崖洞标签匹配应排第一
        assert results[0]["name"] == "洪崖洞"
        # 回归守卫：嵌套候选的扁平字段必须在结果顶层（修复前的匿名化 bug）
        for r in results:
            assert r["name"] and r["city"] and isinstance(r["tags"], list)
            assert "total_score" in r and "_score_breakdown" in r
            assert set(r["_score_breakdown"].keys()) == {
                "preference_match", "trend_heat", "budget_match",
                "location_efficiency", "time_match", "data_reliability",
            }

    def test_empty_candidates(self):
        assert run(ra.recommend({"tags": []}, [], trends=[])) == []
