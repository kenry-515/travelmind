"""
TravelMind Agent — Weather Cache 单元测试（Phase 12.29+）

测试 WeatherCache 的内存 TTL 缓存、线程安全、命中率统计。
纯确定性测试，不依赖外部服务。
"""

import time
import pytest
from unittest.mock import patch

from app.services.weather_cache import WeatherCache


class TestWeatherCache:
    """WeatherCache 功能测试。"""

    def test_get_set_basic(self):
        """基本的 get/set 应正常运作。"""
        cache = WeatherCache(ttl_seconds=3600)
        cache.set(("重庆", 5), {"city": "重庆", "temp": 30})
        result = cache.get(("重庆", 5))
        assert result is not None
        assert result["city"] == "重庆"
        assert result["temp"] == 30

    def test_get_missing_key(self):
        """不存在的 key 应返回 None。"""
        cache = WeatherCache()
        result = cache.get(("广州", 3))
        assert result is None

    def test_get_expired(self):
        """过期的缓存应返回 None。"""
        cache = WeatherCache(ttl_seconds=0)  # 0 TTL = 立即过期
        cache.set(("成都", 3), {"city": "成都"})
        time.sleep(0.01)  # 确保过期
        result = cache.get(("成都", 3))
        assert result is None

    def test_invalidate_single_key(self):
        """清除单个 key 应只移除该条。"""
        cache = WeatherCache()
        cache.set(("A", 1), "value_a")
        cache.set(("B", 2), "value_b")
        cache.invalidate(("A", 1))
        assert cache.get(("A", 1)) is None
        assert cache.get(("B", 2)) is not None

    def test_invalidate_all(self):
        """清除全部应清空所有条目。"""
        cache = WeatherCache()
        cache.set(("A", 1), "value_a")
        cache.set(("B", 2), "value_b")
        cache.invalidate()
        assert cache.get(("A", 1)) is None
        assert cache.get(("B", 2)) is None

    def test_hit_rate_all_misses(self):
        """全部 miss 时 hit_rate 应为 0。"""
        cache = WeatherCache()
        cache.get(("未知", 1))
        cache.get(("未知", 2))
        assert cache.hit_rate == 0.0

    def test_hit_rate_mixed(self):
        """混合 hit/miss 应正确计算命中率。"""
        cache = WeatherCache(ttl_seconds=3600)
        cache.set(("重庆", 5), "data")
        cache.get(("重庆", 5))   # hit
        cache.get(("重庆", 5))   # hit
        cache.get(("未知", 1))   # miss
        # hit_rate = 2/3 ≈ 0.667
        assert cache.hit_rate > 0.6
        assert cache.hit_rate < 0.7

    def test_stats_structure(self):
        """stats 属性应返回完整字典。"""
        cache = WeatherCache(ttl_seconds=1800)
        stats = cache.stats
        assert "entries" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        assert "ttl_seconds" in stats
        assert stats["ttl_seconds"] == 1800

    def test_thread_safety(self):
        """并发访问不应抛出异常。"""
        import threading
        cache = WeatherCache()
        errors = []

        def worker():
            try:
                for i in range(100):
                    cache.set((f"key_{i}", i), f"value_{i}")
                    cache.get((f"key_{i}", i))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0

    def test_singleton(self):
        """get_weather_cache 应返回单例。"""
        from app.services.weather_cache import get_weather_cache
        c1 = get_weather_cache()
        c2 = get_weather_cache()
        assert c1 is c2
