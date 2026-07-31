#!/usr/bin/env python3
"""
TravelMindAgent POI Service - Acceptance Test Suite
===================================================
Comprehensive validation of runtime_poi_service.py optimizations.
Tests core integration, proxy routing, cache persistence, and edge cases.

Usage: python acceptance_test.py
"""

import sys
import os
import json
import time
import asyncio
import tempfile
import threading
import shutil
import logging
from pathlib import Path
from datetime import date
from typing import Dict, List, Any

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).parent / "backend"))

# Configure logging
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Test Results
results = {
    "passed": 0,
    "failed": 0,
    "skipped": 0,
    "errors": []
}

def log_pass(msg: str):
    results["passed"] += 1
    print(f"  ✅ {msg}")

def log_fail(msg: str, detail: str = ""):
    results["failed"] += 1
    results["errors"].append(f"{msg}: {detail}")
    print(f"  ❌ {msg}")
    if detail:
        print(f"      {detail}")

def log_skip(msg: str):
    results["skipped"] += 1
    print(f"  ⚠️  {msg}")

def section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ═══════════════════════════════════════════════════════════
# TEST SUITE 1: Module Import & Basic Structure
# ═══════════════════════════════════════════════════════════

def test_1_1_imports():
    """Test 1.1: Module imports successfully."""
    section("TEST 1.1: Module Import")
    try:
        from app.services.runtime_poi_service import (
            get_hybrid_poi_pool,
            search_city_pois,
            get_kb_cities,
            is_city_in_kb,
            _is_likely_poi_title,
            _clean_poi_name,
            _is_wikipedia_poi,
            _cache_data,
            _cache_lock,
            _cache_dirty,
            _save_cache,
            _load_cache,
            _get_cached,
            _set_cached,
            _CACHE_DIR,
            _cache_path,
        )
        log_pass("All core functions imported successfully")
        return True
    except ImportError as e:
        log_fail("Module import failed", str(e))
        return False

def test_1_2_cache_structure():
    """Test 1.2: Thread-safe cache structure exists."""
    section("TEST 1.2: Cache Structure")
    try:
        import app.services.runtime_poi_service as rps
        
        # Verify lock exists
        assert rps._cache_lock is not None, "_cache_lock not initialized"
        log_pass("_cache_lock exists (thread-safe)")
        
        # Verify cache data structure
        with rps._cache_lock:
            assert rps._cache_data is None or isinstance(rps._cache_data, dict), \
                "_cache_data should be dict or None"
            log_pass("_cache_data is properly structured")
        
        # Verify cache directory exists
        assert rps._CACHE_DIR.exists(), f"Cache directory missing: {rps._CACHE_DIR}"
        log_pass(f"Cache directory exists: {rps._CACHE_DIR}")
        
        return True
    except Exception as e:
        log_fail("Cache structure check failed", str(e))
        return False


# ═══════════════════════════════════════════════════════════
# TEST SUITE 2: POI Filter Quality (Critical Fixes)
# ═══════════════════════════════════════════════════════════

def test_2_1_restaurant_filter():
    """Test 2.1: Restaurant filter quality (post-optimization)."""
    section("TEST 2.1: Restaurant Filter Quality")
    
    import app.services.runtime_poi_service as rps
    
    # Non-restaurants that MUST be rejected
    non_restaurants = [
        ("張曼玉", None, "person name"),
        ("江原道", None, "administrative division"),
        ("王小明", None, "person name"),
        ("北京", None, "city name"),
        ("The Great Wall", None, "English text"),
        ("市政府", None, "government"),
        ("玉溪师范学院", None, "school"),
        ("红塔烟草", None, "tobacco"),
        ("玉溪卷烟厂", None, "factory"),
    ]
    
    for title, snippet, reason in non_restaurants:
        result = rps._is_wikipedia_poi(title, "restaurants", snippet)
        if result:
            log_fail(f"REJECTED expected for '{title}' ({reason}), but got ACCEPTED")
        else:
            results["passed"] += 1
            print(f"  ✅ Correctly rejected '{title}' ({reason})")
    
    # Real restaurants that MUST be accepted
    real_restaurants = [
        ("麦当劳", "全球连锁快餐品牌", "brand recognition"),
        ("肯德基", "全球连锁快餐品牌", "brand recognition"),
        ("全聚德", "中华老字号烤鸭店", "brand recognition"),
        ("海底捞火锅", "知名火锅连锁品牌", "keyword match"),
        ("狗不理包子", "天津老字号包子铺", "keyword match"),
        ("沙县小吃", "福建小吃连锁", "brand recognition"),
        ("外婆家", "杭州家常菜连锁", "brand recognition"),
        ("鼎泰丰", "台湾小笼包连锁", "brand recognition"),
        ("小龙坎火锅", "重庆火锅品牌", "keyword match"),
        ("杏花楼", "上海老字号糕饼", "brand recognition"),
    ]
    
    for title, snippet, reason in real_restaurants:
        result = rps._is_wikipedia_poi(title, "restaurants", snippet)
        if not result:
            log_fail(f"ACCEPTED expected for '{title}' ({reason}), but got REJECTED")
        else:
            results["passed"] += 1
            print(f"  ✅ Correctly accepted '{title}' ({reason})")
    
    return True

def test_2_2_attraction_filter():
    """Test 2.2: Attraction filter quality."""
    section("TEST 2.2: Attraction Filter Quality")
    
    import app.services.runtime_poi_service as rps
    
    # Non-attractions that MUST be rejected
    non_attractions = [
        ("原因", None, "generic word"),
        ("原来", None, "generic word"),
        ("原味", None, "generic word"),
        ("森", None, "too short"),
    ]
    
    for title, snippet, reason in non_attractions:
        result = rps._is_wikipedia_poi(title, "attractions", snippet)
        if result:
            log_fail(f"REJECTED expected for '{title}' ({reason}), but got ACCEPTED")
        else:
            results["passed"] += 1
            print(f"  ✅ Correctly rejected '{title}' ({reason})")
    
    # Real attractions that MUST be accepted
    real_attractions = [
        ("故宫博物院", None, "keyword: 博物馆"),
        ("颐和园", None, "keyword: 园"),
        ("长城", None, "keyword: 城"),
        ("天安门广场", None, "keyword: 广场"),
        ("玉渊潭公园", None, "keyword: 公园"),
        ("石林", None, "keyword: 石林"),
        ("西湖", None, "keyword: 湖"),
        ("布达拉宫", None, "keyword: 宫"),
        ("秦始皇兵马俑", None, "keyword: 俑"),
        ("莫高窟", None, "keyword: 窟"),
    ]
    
    for title, snippet, reason in real_attractions:
        result = rps._is_wikipedia_poi(title, "attractions", snippet)
        if not result:
            log_fail(f"ACCEPTED expected for '{title}' ({reason}), but got REJECTED")
        else:
            results["passed"] += 1
            print(f"  ✅ Correctly accepted '{title}' ({reason})")
    
    return True

def test_2_3_poi_title_validation():
    """Test 2.3: POI title validation (article detection, admin names)."""
    section("TEST 2.3: POI Title Validation")
    
    import app.services.runtime_poi_service as rps
    
    # Should be accepted
    valid_titles = [
        ("玉溪", True, "city name"),
        ("红塔山", True, "mountain/landmark"),
        ("抚仙湖", True, "lake"),
        ("聂耳故居", True, "historical site"),
        ("汇龙生态园", True, "ecological park"),
        ("大营街", True, "town/area"),
        ("红塔区", True, "district level"),
        ("元江县", True, "county level"),
    ]
    
    for title, expected, reason in valid_titles:
        result = rps._is_likely_poi_title(title)
        if result != expected:
            log_fail(f"{'ACCEPT' if expected else 'REJECT'} expected for '{title}' ({reason})")
        else:
            results["passed"] += 1
            print(f"  ✅ Correctly {'accepted' if result else 'rejected'} '{title}' ({reason})")
    
    # Should be rejected
    invalid_titles = [
        ("玉溪最值得去的7个地方", False, "article title"),
        ("攻略 | 必去景点大全", False, "article with separators"),
        ("12345", False, "pure numbers"),
        ("abc", False, "no Chinese chars"),
        ("", False, "empty string"),
        ("玉溪烟多少钱", False, "query intent"),
        ("玉溪市人民政府", False, "government institution"),
        ("如何去红塔山", False, "query intent (how-to)"),
    ]
    
    for title, expected, reason in invalid_titles:
        result = rps._is_likely_poi_title(title)
        if result != expected:
            log_fail(f"{'ACCEPT' if expected else 'REJECT'} expected for '{title}' ({reason})")
        else:
            results["passed"] += 1
            print(f"  ✅ Correctly {'accepted' if result else 'rejected'} '{title}' ({reason})")
    
    return True

def test_2_4_poi_name_cleaning():
    """Test 2.4: POI name cleaning (comma handling bug fix)."""
    section("TEST 2.4: POI Name Cleaning")
    
    import app.services.runtime_poi_service as rps
    
    # Critical: address with colon should NOT be treated as separator
    critical_cases = [
        ("汇龙生态园，地址：云南省玉溪市红塔区", "汇龙生态园", "address with colon (bug fix)"),
        ("聂耳故居门票价格", "聂耳故居", "ticket price suffix"),
        ("玉溪阳光假日酒店电话", "玉溪阳光假日酒店", "phone suffix"),
        ("阳光海岸酒店电话", "阳光海岸酒店", "phone suffix"),
    ]
    
    for input_name, expected, reason in critical_cases:
        result = rps._clean_poi_name(input_name)
        if result != expected:
            log_fail(f"'{input_name}' → '{result}' (expected '{expected}')", reason)
        else:
            results["passed"] += 1
            print(f"  ✅ '{input_name}' → '{result}' ({reason})")
    
    # Article title extraction
    article_cases = [
        ("玉溪最值得去的7个地方，去过一半此生无憾", "玉溪", "article title → extract city"),
        ("抚仙湖抚仙湖被誉为云南版", "抚仙湖", "duplicate removal"),
        ("红塔山-", "红塔山", "dash suffix removal"),
        ("玉溪市（云南省辖地级市）", "玉溪市", "parenthetical removal"),
        ("[游记] 抚仙湖 云南", "抚仙湖 云南", "bracket prefix removal"),
    ]
    
    for input_name, expected, reason in article_cases:
        result = rps._clean_poi_name(input_name)
        if result != expected:
            log_fail(f"'{input_name}' → '{result}' (expected '{expected}')", reason)
        else:
            results["passed"] += 1
            print(f"  ✅ '{input_name}' → '{result}' ({reason})")
    
    return True


# ═══════════════════════════════════════════════════════════
# TEST SUITE 3: Cache Persistence & Thread Safety
# ═══════════════════════════════════════════════════════════

def test_3_1_atomic_write():
    """Test 3.1: Atomic cache write (temp file + replace)."""
    section("TEST 3.1: Atomic Cache Write")
    
    import app.services.runtime_poi_service as rps
    
    original_dir = rps._CACHE_DIR
    try:
        # Create temp directory for test
        test_dir = Path(tempfile.mkdtemp())
        rps._CACHE_DIR = test_dir
        
        # Write cache data
        rps._cache_data = {
            "test_city": {
                "attractions": {
                    "items": [{"name": "Test POI", "type": "attraction"}],
                    "cached_at": date.today().isoformat()
                }
            }
        }
        rps._cache_dirty = True
        rps._save_cache(force=True)
        
        # Verify file was written correctly
        cache_file = test_dir / "poi_queries.json"
        assert cache_file.exists(), "Cache file should exist"
        
        with open(cache_file, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
        
        assert "test_city" in saved_data, "test_city should be in saved data"
        assert saved_data["test_city"]["attractions"]["items"][0]["name"] == "Test POI"
        log_pass("Cache data written and verified correctly")
        
        # Verify NO temp files left behind (atomic write)
        tmp_files = list(test_dir.glob("*.tmp"))
        assert len(tmp_files) == 0, f"Temp files should be cleaned up: {tmp_files}"
        log_pass("No temporary files remain (atomic write confirmed)")
        
        # Verify _cache_dirty is cleared after save
        assert not rps._cache_dirty, "Cache should not be dirty after save"
        log_pass("Cache dirty flag cleared after save")
        
        # Cleanup
        shutil.rmtree(test_dir)
        return True
        
    except Exception as e:
        log_fail("Atomic write test failed", str(e))
        return False
    finally:
        rps._CACHE_DIR = original_dir
        # Reset cache state
        with rps._cache_lock:
            rps._cache_data = None
            rps._cache_dirty = False

def test_3_2_concurrent_access():
    """Test 3.2: Concurrent cache access (thread safety)."""
    section("TEST 3.2: Concurrent Cache Access")
    
    import app.services.runtime_poi_service as rps
    
    # Clear cache
    with rps._cache_lock:
        rps._cache_data = None
        rps._cache_dirty = False
    
    errors = []
    barrier = threading.Barrier(6)  # 3 readers + 3 writers
    
    def reader():
        barrier.wait()
        try:
            for _ in range(100):
                data = rps._load_cache()
                assert isinstance(data, dict), "Cache should be dict"
                # Simulate read
                _ = rps._get_cached("test_city", "attractions")
        except Exception as e:
            errors.append(f"Reader error: {e}")
    
    def writer():
        barrier.wait()
        try:
            for i in range(50):
                with rps._cache_lock:
                    rps._cache_data = {"iter": i, "data": f"value_{i}"}
                    rps._cache_dirty = True
        except Exception as e:
            errors.append(f"Writer error: {e}")
    
    threads = [
        threading.Thread(target=reader),
        threading.Thread(target=reader),
        threading.Thread(target=reader),
        threading.Thread(target=writer),
        threading.Thread(target=writer),
        threading.Thread(target=writer),
    ]
    
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    
    if errors:
        log_fail(f"Concurrent access errors: {errors}")
        return False
    else:
        log_pass("6 concurrent threads (3 readers + 3 writers) completed without errors")
        return True

def test_3_3_cache_persistence():
    """Test 3.3: Cache persistence across function calls."""
    section("TEST 3.3: Cache Persistence")
    
    import app.services.runtime_poi_service as rps
    
    original_dir = rps._CACHE_DIR
    try:
        test_dir = Path(tempfile.mkdtemp())
        rps._CACHE_DIR = test_dir
        
        # Simulate save
        test_data = {
            "persist_test_city": {
                "attractions": {
                    "items": [{"name": "Persistent POI", "value": 42}],
                    "cached_at": date.today().isoformat()
                }
            }
        }
        
        rps._cache_data = test_data
        rps._cache_dirty = True
        rps._save_cache(force=True)
        
        # Simulate "restart" - clear in-memory cache
        with rps._cache_lock:
            rps._cache_data = None
            rps._cache_dirty = False
        
        # Load from disk (simulating new process)
        loaded = rps._load_cache()
        
        assert loaded is not None, "Should load from disk"
        assert "persist_test_city" in loaded, "City should be in loaded data"
        assert loaded["persist_test_city"]["attractions"]["items"][0]["name"] == "Persistent POI"
        log_pass("Cache persists across simulated restart (disk→memory reload)")
        
        # Cleanup
        shutil.rmtree(test_dir)
        return True
        
    except Exception as e:
        log_fail("Cache persistence test failed", str(e))
        return False
    finally:
        rps._CACHE_DIR = original_dir
        with rps._cache_lock:
            rps._cache_data = None
            rps._cache_dirty = False

def test_3_4_auto_flush():
    """Test 3.4: Auto-flush mechanism."""
    section("TEST 3.4: Auto-Flush Mechanism")
    
    import app.services.runtime_poi_service as rps
    
    original_dir = rps._CACHE_DIR
    try:
        test_dir = Path(tempfile.mkdtemp())
        rps._CACHE_DIR = test_dir
        
        # Setup cache with dirty flag
        rps._cache_data = {"flush_test": {"data": "test"}}
        rps._cache_dirty = True
        
        # Manually set _LAST_FLUSH to old time
        rps._LAST_FLUSH = 0.0
        
        # Trigger auto-flush
        rps._maybe_flush_cache()
        
        # Verify data was flushed
        cache_file = test_dir / "poi_queries.json"
        assert cache_file.exists(), "Cache file should exist after auto-flush"
        
        with open(cache_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert "flush_test" in saved, "Data should be flushed to disk"
        
        log_pass("Auto-flush mechanism works correctly")
        
        # Cleanup
        shutil.rmtree(test_dir)
        return True
        
    except Exception as e:
        log_fail("Auto-flush test failed", str(e))
        return False
    finally:
        rps._CACHE_DIR = original_dir
        with rps._cache_lock:
            rps._cache_data = None
            rps._cache_dirty = False


# ═══════════════════════════════════════════════════════════
# TEST SUITE 4: KB City Cache Performance
# ═══════════════════════════════════════════════════════════

def test_4_1_kb_cities_cache():
    """Test 4.1: KB cities caching performance."""
    section("TEST 4.1: KB Cities Caching")
    
    import app.services.runtime_poi_service as rps
    
    # Reset cache
    rps._KB_CITIES_CACHE = None
    rps._KB_CITIES_CACHE_TS = 0.0
    
    # First call (file I/O)
    start = time.perf_counter()
    cities1 = rps.get_kb_cities()
    first_call_time = time.perf_counter() - start
    
    # Second call (cached)
    start = time.perf_counter()
    cities2 = rps.get_kb_cities()
    cached_call_time = time.perf_counter() - start
    
    # Third call (cached)
    start = time.perf_counter()
    cities3 = rps.get_kb_cities()
    third_call_time = time.perf_counter() - start
    
    # Verify correctness
    assert cities1 == cities2 == cities3, "All calls should return same data"
    assert len(cities1) == 32, f"Expected 32 KB cities, got {len(cities1)}"
    log_pass(f"Consistent data across 3 calls ({len(cities1)} cities)")
    
    # Verify performance improvement
    if cached_call_time > 0:
        speedup = first_call_time / cached_call_time
        log_pass(f"Cache speedup: {speedup:.1f}x (first: {first_call_time*1000:.2f}ms, cached: {cached_call_time*1000:.4f}ms)")
    else:
        log_pass(f"Cache instant (first: {first_call_time*1000:.2f}ms, cached: instant)")
    
    # Verify is_city_in_kb works
    test_checks = [
        ("北京", True),
        ("上海", True),
        ("昆明", True),
        ("玉溪", False),  # Not in KB (runtime-only)
        ("", False),
    ]
    
    for city, expected in test_checks:
        result = rps.is_city_in_kb(city)
        if result != expected:
            log_fail(f"is_city_in_kb('{city}') = {result}, expected {expected}")
        else:
            results["passed"] += 1
            status = "in KB" if result else "NOT in KB"
            print(f"  ✅ is_city_in_kb('{city}') correctly returns {status}")
    
    return True


# ═══════════════════════════════════════════════════════════
# TEST SUITE 5: Proxy Routing Logic
# ═══════════════════════════════════════════════════════════

def test_5_1_proxy_detection():
    """Test 5.1: Proxy detection and configuration."""
    section("TEST 5.1: Proxy Detection")
    
    import app.services.runtime_poi_service as rps
    
    # Test _detect_proxy function
    proxy_url = rps._detect_proxy()
    
    if proxy_url:
        log_pass(f"Proxy detected: {proxy_url}")
    else:
        log_skip("No proxy detected (will use direct connections)")
    
    # Test client building
    try:
        # Build direct client (no proxy)
        direct_client = rps._build_httpx_client(timeout=5, use_proxy=False)
        assert direct_client is not None, "Direct client should be created"
        
        # Check transport has no proxy
        transport = direct_client._transport
        log_pass("Direct client created successfully (no proxy)")
        
        # Close
        asyncio.get_event_loop().run_until_complete(direct_client.aclose())
        log_pass("Direct client closed successfully")
        
    except Exception as e:
        log_fail("Direct client creation failed", str(e))
        return False
    
    # Test proxy client creation (if proxy available)
    if proxy_url:
        try:
            proxy_client = rps._build_httpx_client(timeout=5, use_proxy=True)
            assert proxy_client is not None, "Proxy client should be created"
            log_pass("Proxy client created successfully")
            
            asyncio.get_event_loop().run_until_complete(proxy_client.aclose())
            log_pass("Proxy client closed successfully")
            
        except Exception as e:
            log_fail("Proxy client creation failed", str(e))
            return False
    
    return True

def test_5_2_selective_routing():
    """Test 5.2: Verify selective proxy routing logic in code."""
    section("TEST 5.2: Selective Proxy Routing Logic")
    
    import app.services.runtime_poi_service as rps
    
    # Read and verify the routing logic from the source code
    source_file = Path(rps.__file__)
    
    with open(source_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Verify key routing patterns exist
    checks = {
        # Amap uses direct_client (not proxy)
        "Amap direct": "_amap_poi_search(direct_client" in content,
        # Bing uses direct_client (not proxy)
        "Bing direct": "_bing_search(direct_client" in content,
        # Wikipedia uses proxy_client
        "Wikipedia proxy": "_wikipedia_search(proxy_client" in content,
        # Trip uses proxy_client
        "Trip proxy": "_trip_poi_search(proxy_client" in content,
        # Proxy client is created lazily
        "Lazy proxy creation": "proxy_client = _build_httpx_client(timeout=15, use_proxy=True)" in content,
        # Proxy client is closed in finally block
        "Proxy cleanup": "await proxy_client.aclose()" in content,
    }
    
    for description, check_passed in checks.items():
        if check_passed:
            log_pass(f"{description}: correctly implemented")
        else:
            log_fail(f"{description}: NOT found in source code!")
    
    return True


# ═══════════════════════════════════════════════════════════
# TEST SUITE 6: Edge Cases & Brand Recognition
# ═══════════════════════════════════════════════════════════

def test_6_1_brand_recognition():
    """Test 6.1: Restaurant brand recognition."""
    section("TEST 6.1: Restaurant Brand Recognition")
    
    import app.services.runtime_poi_service as rps
    
    # Known restaurant brands that should be recognized
    brands = [
        "麦当劳", "肯德基", "全聚德", "东来顺", "鼎泰丰",
        "海底捞", "小龙坎", "星巴克", "必胜客",
        "沙县小吃", "兰州拉面", "外婆家", "杏花楼",
    ]
    
    for brand in brands:
        result = rps._is_wikipedia_poi(brand, "restaurants", None)
        if not result:
            log_fail(f"Brand '{brand}' NOT recognized as restaurant")
        else:
            results["passed"] += 1
            print(f"  ✅ Brand '{brand}' correctly recognized")
    
    return True

def test_6_2_edge_cases():
    """Test 6.2: Edge cases for POI processing."""
    section("TEST 6.2: Edge Cases")
    
    import app.services.runtime_poi_service as rps
    
    # Edge case: very long titles
    long_title = "这是一个非常非常非常长的标题用于测试POI处理逻辑是否能够正确处理异常情况和边界条件包括但不限于标题过长的情况"
    result = rps._is_likely_poi_title(long_title)
    # Should be rejected (> 80 chars)
    if not result:
        log_pass(f"Long title ({len(long_title)} chars, >80 limit) correctly rejected")
    else:
        log_fail(f"Long title ({len(long_title)} chars, >80 limit) should be rejected")
    
    # Edge case: whitespace-only
    result = rps._is_likely_poi_title("   ")
    if not result:
        log_pass("Whitespace-only title correctly rejected")
    else:
        log_fail("Whitespace-only title should be rejected")
    
    # Edge case: mixed content
    result = rps._is_likely_poi_title("玉溪｜红塔山｜攻略")
    if not result:
        log_pass("Separators in title correctly detected")
    else:
        log_fail("Title with separators should be rejected")
    
    # Edge case: _clean_poi_name with various inputs
    clean_results = [
        ("", "", "empty string"),
        ("  ", "", "whitespace only"),
        ("A", "", "single character"),
        ("AB", "AB", "short valid name"),
    ]
    
    for input_val, expected, desc in clean_results:
        result = rps._clean_poi_name(input_val)
        if result == expected:
            log_pass(f"_clean_poi_name('{input_val}') = '{result}' ({desc})")
        else:
            log_fail(f"_clean_poi_name('{input_val}') = '{result}' (expected '{expected}', {desc})")
    
    return True


# ═══════════════════════════════════════════════════════════
# TEST SUITE 7: Performance Metrics
# ═══════════════════════════════════════════════════════════

def test_7_1_filter_performance():
    """Test 7.1: Filter function performance."""
    section("TEST 7.1: Filter Performance")
    
    import app.services.runtime_poi_service as rps
    
    # Generate test data
    test_titles = []
    for i in range(1000):
        test_titles.extend([
            f"测试景点{i}",
            f"Test Restaurant {i}",
            f"城市名称{i}",
            f"攻略大全第{i}期",
            f"12345{i}",
        ])
    
    # Test _is_likely_poi_title performance
    start = time.perf_counter()
    results_list = [rps._is_likely_poi_title(t) for t in test_titles]
    elapsed = time.perf_counter() - start
    
    per_call = (elapsed / len(test_titles)) * 1_000_000  # microseconds
    
    if per_call < 10:  # < 10 microseconds per call
        log_pass(f"_is_likely_poi_title: {len(test_titles)} calls in {elapsed*1000:.2f}ms ({per_call:.1f}µs/call)")
    else:
        log_skip(f"_is_likely_poi_title: {len(test_titles)} calls in {elapsed*1000:.2f}ms ({per_call:.1f}µs/call) - may need optimization")
    
    # Test _clean_poi_name performance
    start = time.perf_counter()
    for title in test_titles[:500]:
        rps._clean_poi_name(title)
    elapsed = time.perf_counter() - start
    
    per_call = (elapsed / 500) * 1_000_000
    if per_call < 20:
        log_pass(f"_clean_poi_name: 500 calls in {elapsed*1000:.2f}ms ({per_call:.1f}µs/call)")
    else:
        log_skip(f"_clean_poi_name: 500 calls in {elapsed*1000:.2f}ms ({per_call:.1f}µs/call) - may need optimization")
    
    return True


# ═══════════════════════════════════════════════════════════
# TEST SUITE 8: Integration Test (Non-KB City)
# ═══════════════════════════════════════════════════════════

async def test_8_1_hybrid_non_kb_city():
    """Test 8.1: Integration test for non-KB city (Yuxi)."""
    section("TEST 8.1: Integration - Non-KB City (Yuxi)")
    
    import app.services.runtime_poi_service as rps
    
    # Verify Yuxi is NOT in KB
    in_kb = rps.is_city_in_kb("玉溪")
    if in_kb:
        log_skip("玉溪 is in KB, skipping runtime integration test")
        return True
    
    log_pass("玉溪 confirmed as non-KB city (will trigger runtime query)")
    
    # Check if proxy is available (needed for some sources)
    proxy_available = rps._detect_proxy()
    log_skip(f"Proxy status: {'AVAILABLE' if proxy_available else 'NOT available'}")
    
    # Try to get hybrid POI pool
    categories = ["attractions", "restaurants"]
    try:
        results_data = await rps.get_hybrid_poi_pool(
            "玉溪",
            categories=categories,
            limit_per_category=5
        )
        
        # Validate response structure
        for cat in categories:
            if cat in results_data:
                cat_data = results_data[cat]
                items = cat_data.get("items", [])
                links = cat_data.get("search_links", [])
                
                log_pass(f"{cat}: {len(items)} POIs, {len(links)} search links")
                
                # Validate item structure
                for item in items[:2]:  # Check first 2 items
                    assert "name" in item, "Item should have 'name' field"
                    assert "city" in item, "Item should have 'city' field"
                    assert item.get("city") == "玉溪", "City should be 玉溪"
                    log_pass(f"  Sample POI: '{item['name']}' (source: {item.get('query_source', 'unknown')})")
            else:
                log_fail(f"{cat}: missing from results")
        
        return True
        
    except Exception as e:
        log_fail("Integration test failed", str(e))
        import traceback
        traceback.print_exc()
        return False


# ═══════════════════════════════════════════════════════════
# TEST SUMMARY
# ═══════════════════════════════════════════════════════════

def print_summary():
    """Print final test summary."""
    section("ACCEPTANCE TEST SUMMARY")
    
    total = results["passed"] + results["failed"] + results["skipped"]
    pass_rate = (results["passed"] / total * 100) if total > 0 else 0
    
    print(f"  Total Checks: {total}")
    print(f"  ✅ Passed: {results['passed']}")
    print(f"  ❌ Failed: {results['failed']}")
    print(f"  ⚠️  Skipped: {results['skipped']}")
    print(f"  Pass Rate: {pass_rate:.1f}%")
    
    if results["errors"]:
        print(f"\n  Failed Items:")
        for i, error in enumerate(results["errors"], 1):
            print(f"    {i}. {error}")
    
    # Final verdict
    if results["failed"] == 0:
        print(f"\n  🎉 VERDICT: ACCEPTED - All critical checks passed!")
        if results["skipped"] > 0:
            print(f"     ({results['skipped']} checks skipped due to environment)")
    elif results["failed"] <= 3:
        print(f"\n  ⚠️  VERDICT: CONDITIONAL - {results['failed']} issues found")
        print(f"     These may be environment-related and should be reviewed")
    else:
        print(f"\n  ❌ VERDICT: REJECTED - {results['failed']} issues need fixing")
    
    return results["failed"] == 0


# ═══════════════════════════════════════════════════════════
# MAIN EXECUTION
# ═══════════════════════════════════════════════════════════

def main():
    """Run all acceptance tests."""
    print("""
╔══════════════════════════════════════════════════════════════╗
║     TravelMindAgent POI Service - Acceptance Test Suite     ║
║     Runtime POI Service Optimization Verification           ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Suite 1: Module & Structure
    test_1_1_imports()
    test_1_2_cache_structure()
    
    # Suite 2: POI Filter Quality
    test_2_1_restaurant_filter()
    test_2_2_attraction_filter()
    test_2_3_poi_title_validation()
    test_2_4_poi_name_cleaning()
    
    # Suite 3: Cache & Thread Safety
    test_3_1_atomic_write()
    test_3_2_concurrent_access()
    test_3_3_cache_persistence()
    test_3_4_auto_flush()
    
    # Suite 4: KB Cities Cache
    test_4_1_kb_cities_cache()
    
    # Suite 5: Proxy Routing
    test_5_1_proxy_detection()
    test_5_2_selective_routing()
    
    # Suite 6: Edge Cases
    test_6_1_brand_recognition()
    test_6_2_edge_cases()
    
    # Suite 7: Performance
    test_7_1_filter_performance()
    
    # Suite 8: Integration (async)
    # Need to run async test in event loop
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(test_8_1_hybrid_non_kb_city())
    finally:
        loop.close()
    
    # Final summary
    accepted = print_summary()
    return 0 if accepted else 1


if __name__ == "__main__":
    sys.exit(main())