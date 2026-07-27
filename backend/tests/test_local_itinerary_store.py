"""local_itinerary_store 单元测试：文件型行程存储（PG 回退）。"""

import json

import pytest

from app.services import local_itinerary_store as store


@pytest.fixture()
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_STORE_ROOT", tmp_path)
    yield tmp_path


def _sample_itinerary(city="重庆"):
    return {
        "trip": {"title": f"{city}三日游", "city": city, "daysCount": 3},
        "days": [{"day": 1, "items": []}],
    }


class TestLocalItineraryStore:
    def test_save_and_get(self, tmp_store):
        iid = store.save_itinerary("dev1", _sample_itinerary())
        detail = store.get_itinerary("dev1", iid)
        assert detail is not None
        assert detail["title"] == "重庆三日游"
        assert detail["city"] == "重庆"
        assert detail["plan"]["days"][0]["day"] == 1
        assert detail["created_at"]

    def test_list_newest_first_and_pagination(self, tmp_store):
        import time as _t
        for i in range(3):
            store.save_itinerary("dev1", _sample_itinerary(f"城市{i}"))
            _t.sleep(1.1)  # 时间戳秒级，需间隔保证排序
        summaries, total = store.list_itineraries("dev1", page=1, page_size=2)
        assert total == 3
        assert len(summaries) == 2
        assert summaries[0]["title"] == "城市2三日游"
        _, total2 = store.list_itineraries("dev1", page=2, page_size=2)
        assert total2 == 3

    def test_user_isolation(self, tmp_store):
        iid = store.save_itinerary("dev1", _sample_itinerary())
        assert store.get_itinerary("dev2", iid) is None
        assert store.list_itineraries("dev2")[1] == 0

    def test_delete(self, tmp_store):
        iid = store.save_itinerary("dev1", _sample_itinerary())
        assert store.delete_itinerary("dev1", iid) is True
        assert store.get_itinerary("dev1", iid) is None
        assert store.delete_itinerary("dev1", iid) is False

    def test_device_id_sanitized(self, tmp_store):
        iid = store.save_itinerary("../../etc/evil", _sample_itinerary())
        # 路径穿越被消毒，文件落在安全目录内
        assert store.get_itinerary("../../etc/evil", iid) is not None
        assert not (tmp_store.parent / "etc").exists()

    def test_corrupted_file_skipped(self, tmp_store):
        store.save_itinerary("dev1", _sample_itinerary())
        d = tmp_store / "dev1"
        (d / "bad.json").write_text("{invalid json", encoding="utf-8")
        summaries, total = store.list_itineraries("dev1")
        assert total == 1
