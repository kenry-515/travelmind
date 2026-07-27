"""Phase 12.21：美食推荐细分类型推导 + 候选池多样性保底（f08 根因回归）。

根因：高德采集把菜系信息压平成「中餐」（上海 30 条美食 POI 中 29 条），
单城语义检索又把仅存的其他类型代表（如唯一的「小龙虾→海鲜」POI）挤出
候选池，导致 food_diversity 只剩 美食/中餐 两类。
"""

from app.api.recommend import _refine_food_tags, _supplement_food_diversity


class TestRefineFoodTags:
    def test_non_food_untouched(self):
        assert _refine_food_tags("西湖", ["自然", "湖泊"]) == ["自然", "湖泊"]

    def test_empty_tags_untouched(self):
        assert _refine_food_tags("小龙虾王", []) == []

    def test_seafood_from_name(self):
        out = _refine_food_tags("刘栋梁大排档·小龙虾江湖菜", ["美食", "中餐"])
        assert "海鲜" in out
        assert "小吃" in out  # 大排档
        assert "美食" in out and "中餐" in out  # 原标签保留

    def test_no_duplicate(self):
        out = _refine_food_tags("老字号海鲜酒楼", ["美食", "海鲜"])
        assert out.count("海鲜") == 1
        assert "老字号" in out

    def test_plain_chinese_restaurant_unchanged(self):
        assert _refine_food_tags("绿波廊", ["美食", "中餐"]) == ["美食", "中餐"]


class _FakeStore:
    def __init__(self, items):
        self.is_connected = True
        self._items = items

    def get_by_metadata(self, where, limit=500):
        return self._items


def _item(name, tags, pop=5):
    return {
        "id": name,
        "document": name,
        "metadata": {
            "name": name,
            "city": "上海",
            "tags": ", ".join(tags),
            "popularity_score": pop,
        },
        "score": 0.0,
    }


class TestSupplementFoodDiversity:
    def test_adds_missing_type_representative(self, monkeypatch):
        import app.rag.vector_store as vs

        kb = [
            _item("绿波廊", ["美食", "中餐"], pop=8),
            _item("老正兴菜馆", ["美食", "中餐"], pop=7),
            _item("刘栋梁大排档·小龙虾江湖菜", ["美食", "中餐"], pop=6),
        ]
        monkeypatch.setattr(vs, "get_vector_store", lambda: _FakeStore(kb))

        # 候选池里只有中餐（模拟语义检索把小龙虾挤出 Top K）
        candidates = [_item("绿波廊", ["美食", "中餐"], pop=8)]
        out = _supplement_food_diversity("上海", candidates)

        names = [c.get("name") or c.get("metadata", {}).get("name") for c in out]
        assert "刘栋梁大排档·小龙虾江湖菜" in names  # 海鲜/小吃代表被补入
        assert "老正兴菜馆" not in names  # 纯中餐不提供新类型，不补

    def test_no_food_pois_no_crash(self, monkeypatch):
        import app.rag.vector_store as vs

        kb = [_item("东方明珠", ["地标", "夜景"], pop=9)]
        monkeypatch.setattr(vs, "get_vector_store", lambda: _FakeStore(kb))
        candidates = [_item("东方明珠", ["地标", "夜景"], pop=9)]
        out = _supplement_food_diversity("上海", candidates)
        assert len(out) == 1

    def test_store_unavailable_no_crash(self, monkeypatch):
        import app.rag.vector_store as vs

        monkeypatch.setattr(vs, "get_vector_store", lambda: _FakeStore([]))
        out = _supplement_food_diversity("上海", [_item("绿波廊", ["美食", "中餐"])])
        assert len(out) == 1
