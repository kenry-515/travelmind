"""
TravelMind Agent — Amap Maps Service 单元测试

测试 Amap 服务的关键函数，mock httpx 避免真实 API 调用。
覆盖：Key 为空降级、POI 搜索、步行路线、距离矩阵、MD5 签名、Haversine 回退。
"""

import hashlib
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.amap_service import (
    is_amap_available,
    search_poi,
    get_walking_route,
    get_distance_matrix,
    _sign_params,
)


# =============================================================================
# is_amap_available()
# =============================================================================

class TestIsAmapAvailable:
    """检查 Amap API Key 可用性。"""

    def test_is_amap_available_false(self, monkeypatch):
        """默认 Key 为空应返回 False。"""
        class _Mock:
            AMAP_API_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())
        assert is_amap_available() is False

    def test_is_amap_available_true(self, monkeypatch):
        """配置 Key 后应返回 True。"""
        class _Mock:
            AMAP_API_KEY = "test_key_abc"
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())
        assert is_amap_available() is True

    def test_is_amap_available_whitespace_only(self, monkeypatch):
        """Key 为空白字符应返回 False。"""
        class _Mock:
            AMAP_API_KEY = "   "
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())
        assert is_amap_available() is False


# =============================================================================
# _sign_params()
# =============================================================================

class TestSignParams:
    """MD5 数字签名逻辑。"""

    def test_sign_params_no_key(self, monkeypatch):
        """无签名 Key 时返回原参数字典。"""
        class _Mock:
            AMAP_SIGN_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        params = {"key": "ak_123", "keywords": "故宫"}
        result = _sign_params(params)
        assert result == params
        assert "sig" not in result

    def test_sign_params_with_key(self, monkeypatch):
        """有签名 Key 时正确计算并追加 MD5 签名。"""
        sign_key = "my_secret_signing_key_2026"
        class _Mock:
            AMAP_SIGN_KEY = sign_key
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        params = {"key": "ak_456", "keywords": "天坛", "output": "JSON"}
        result = _sign_params(dict(params))  # 拷贝以避免篡改原字典

        # 手动验证 MD5
        sorted_items = sorted(
            (k, str(v)) for k, v in params.items() if k != "sig"
        )
        raw = "&".join(f"{k}={v}" for k, v in sorted_items) + sign_key
        expected_sig = hashlib.md5(raw.encode("utf-8")).hexdigest()

        assert result["sig"] == expected_sig
        # 原始字段保留
        assert result["key"] == "ak_456"
        assert result["keywords"] == "天坛"
        assert result["output"] == "JSON"

    def test_sign_params_sorted_order(self, monkeypatch):
        """签名前参数应按 key 排序。"""
        sign_key = "secret"
        class _Mock:
            AMAP_SIGN_KEY = sign_key
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        # params 故意乱序
        params = {"z": "1", "a": "2", "m": "3"}
        result = _sign_params(dict(params))

        sorted_items = sorted(
            (k, str(v)) for k, v in params.items() if k != "sig"
        )
        raw = "&".join(f"{k}={v}" for k, v in sorted_items) + sign_key
        expected_sig = hashlib.md5(raw.encode("utf-8")).hexdigest()

        assert result["sig"] == expected_sig

    def test_sign_params_existing_sig_overwritten(self, monkeypatch):
        """如果 params 中已有 sig 字段，应被覆盖。"""
        sign_key = "secret"
        class _Mock:
            AMAP_SIGN_KEY = sign_key
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        params = {"key": "ak", "sig": "old_sig_value", "q": "test"}
        result = _sign_params(dict(params))

        # sig 不应参与排序
        sorted_items = sorted(
            (k, str(v)) for k, v in params.items() if k != "sig"
        )
        raw = "&".join(f"{k}={v}" for k, v in sorted_items) + sign_key
        expected_sig = hashlib.md5(raw.encode("utf-8")).hexdigest()

        assert result["sig"] == expected_sig
        assert result["sig"] != "old_sig_value"


# =============================================================================
# search_poi()
# =============================================================================

class TestSearchPoi:
    """POI 搜索。"""

    @pytest.mark.asyncio
    async def test_search_poi_empty_key(self, monkeypatch):
        """无 Amap Key 时返回空列表。"""
        class _Mock:
            AMAP_API_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        result = await search_poi("故宫", "北京")
        assert result == []

    @pytest.mark.asyncio
    async def test_search_poi_success(self, monkeypatch):
        """Mock HTTP 请求，验证 POI 解析结果 —— 含坐标、adname、typecode。"""
        class _Mock:
            AMAP_API_KEY = "test_key"
            AMAP_SIGN_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        mock_resp = MagicMock(spec_set=["status_code", "json", "raise_for_status"])
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "1",
            "info": "OK",
            "pois": [
                {
                    "name": "故宫博物院",
                    "adname": "东城区",
                    "address": "北京市东城区景山前街4号",
                    "typecode": "060100",
                    "location": "116.397128,39.916527",
                },
                {
                    "name": "故宫神武门",
                    "adname": "东城区",
                    "address": "北京市东城区景山前街4号",
                    "typecode": "060101",
                    "location": "116.397,39.925",
                },
            ],
        }
        mock_get = AsyncMock(return_value=mock_resp)
        mock_client = MagicMock()
        mock_client.get = mock_get
        monkeypatch.setattr("app.services.amap_service._get_client", lambda: mock_client)

        results = await search_poi("故宫", "北京")

        assert len(results) == 2
        # 第一条 POI
        assert results[0]["name"] == "故宫博物院"
        assert results[0]["adname"] == "东城区"
        assert results[0]["address"] == "北京市东城区景山前街4号"
        assert results[0]["typecode"] == "060100"
        assert results[0]["lat"] == 39.916527
        assert results[0]["lon"] == 116.397128
        # 第二条 POI
        assert results[1]["name"] == "故宫神武门"
        assert results[1]["lat"] == 39.925
        assert results[1]["lon"] == 116.397

    @pytest.mark.asyncio
    async def test_search_poi_api_status_failure(self, monkeypatch):
        """API 返回 status != 1 时返回空列表。"""
        class _Mock:
            AMAP_API_KEY = "test_key"
            AMAP_SIGN_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "0",
            "info": "INVALID_PARAMS",
            "pois": [],
        }
        mock_get = AsyncMock(return_value=mock_resp)
        mock_client = MagicMock()
        mock_client.get = mock_get
        monkeypatch.setattr("app.services.amap_service._get_client", lambda: mock_client)

        results = await search_poi("$$$", "北京")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_poi_network_retry_then_fail(self, monkeypatch):
        """网络异常应重试一次，最终返回空列表，验证两次调用。"""
        class _Mock:
            AMAP_API_KEY = "test_key"
            AMAP_SIGN_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        mock_get = AsyncMock(side_effect=Exception("Connection reset"))
        mock_client = MagicMock()
        mock_client.get = mock_get
        monkeypatch.setattr("app.services.amap_service._get_client", lambda: mock_client)

        results = await search_poi("故宫", "北京")
        assert results == []
        # 首次失败 + 重试一次 = 2 次调用
        assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_search_poi_malformed_location(self, monkeypatch):
        """location 格式异常不应导致崩溃，应返回 None 坐标。"""
        class _Mock:
            AMAP_API_KEY = "test_key"
            AMAP_SIGN_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "1",
            "info": "OK",
            "pois": [
                {
                    "name": "无坐标景点",
                    "adname": "朝阳区",
                    "address": "朝阳区某地",
                    "typecode": "060100",
                    "location": "",
                },
                {
                    "name": "坐标格式异常",
                    "adname": "海淀区",
                    "address": "海淀区某地",
                    "typecode": "060100",
                    "location": "not-a-valid-coord",
                },
            ],
        }
        mock_get = AsyncMock(return_value=mock_resp)
        mock_client = MagicMock()
        mock_client.get = mock_get
        monkeypatch.setattr("app.services.amap_service._get_client", lambda: mock_client)

        results = await search_poi("测试", "北京")
        assert len(results) == 2
        assert results[0]["lat"] is None
        assert results[0]["lon"] is None
        assert results[1]["lat"] is None
        assert results[1]["lon"] is None

    @pytest.mark.asyncio
    async def test_search_poi_missing_pois_key(self, monkeypatch):
        """响应中缺少 pois 字段不应崩溃。"""
        class _Mock:
            AMAP_API_KEY = "test_key"
            AMAP_SIGN_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "1", "info": "OK"}  # 无 pois
        mock_get = AsyncMock(return_value=mock_resp)
        mock_client = MagicMock()
        mock_client.get = mock_get
        monkeypatch.setattr("app.services.amap_service._get_client", lambda: mock_client)

        results = await search_poi("故宫", "北京")
        assert results == []


# =============================================================================
# get_walking_route()
# =============================================================================

class TestGetWalkingRoute:
    """步行路线 —— Haversine 回退 + Amap API 调用。"""

    @pytest.mark.asyncio
    async def test_walking_route_haversine_fallback(self, monkeypatch):
        """Key 为空时使用 Haversine 公式估算距离和时长。"""
        class _Mock:
            AMAP_API_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        # 故宫 (116.397, 39.917) -> 天坛 (116.407, 39.882)
        result = await get_walking_route(
            (116.397128, 39.916527),
            (116.407, 39.882),
        )
        assert result is not None
        assert "distance_m" in result
        assert "duration_s" in result
        assert "steps" in result
        # 故宫到天坛约 3.8-4.0 km
        assert 3000 < result["distance_m"] < 5000
        # 步行速度 ~1.2 m/s
        assert result["duration_s"] == int(result["distance_m"] / 1.2)
        assert result["steps"] == 1

    @pytest.mark.asyncio
    async def test_walking_route_same_point(self, monkeypatch):
        """起终点相同时 Haversine 应为 0 距离。"""
        class _Mock:
            AMAP_API_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        result = await get_walking_route(
            (116.397128, 39.916527),
            (116.397128, 39.916527),
        )
        assert result is not None
        assert result["distance_m"] == 0
        assert result["duration_s"] == 0

    @pytest.mark.asyncio
    async def test_walking_route_success(self, monkeypatch):
        """Mock Amap API 返回步行路线解析结果。"""
        class _Mock:
            AMAP_API_KEY = "test_key"
            AMAP_SIGN_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "1",
            "info": "OK",
            "route": {
                "paths": [
                    {
                        "distance": "3800",
                        "duration": "3000",
                        "steps": [
                            {"instruction": "沿景山前街向西步行"},
                            {"instruction": "左转进入南池子大街"},
                        ],
                    }
                ]
            },
        }
        mock_get = AsyncMock(return_value=mock_resp)
        mock_client = MagicMock()
        mock_client.get = mock_get
        monkeypatch.setattr("app.services.amap_service._get_client", lambda: mock_client)

        result = await get_walking_route(
            (116.397128, 39.916527),
            (116.407, 39.882),
        )
        assert result is not None
        assert result["distance_m"] == 3800
        assert result["duration_s"] == 3000
        assert result["steps"] == 2

    @pytest.mark.asyncio
    async def test_walking_route_api_failure(self, monkeypatch):
        """API 返回 status != 1 时应返回 None。"""
        class _Mock:
            AMAP_API_KEY = "test_key"
            AMAP_SIGN_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "0",
            "info": "SERVICE_NOT_AVAILABLE",
        }
        mock_get = AsyncMock(return_value=mock_resp)
        mock_client = MagicMock()
        mock_client.get = mock_get
        monkeypatch.setattr("app.services.amap_service._get_client", lambda: mock_client)

        result = await get_walking_route(
            (116.397128, 39.916527),
            (116.407, 39.882),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_walking_route_empty_paths(self, monkeypatch):
        """API 返回空 paths 时应返回 None。"""
        class _Mock:
            AMAP_API_KEY = "test_key"
            AMAP_SIGN_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "1",
            "info": "OK",
            "route": {"paths": []},
        }
        mock_get = AsyncMock(return_value=mock_resp)
        mock_client = MagicMock()
        mock_client.get = mock_get
        monkeypatch.setattr("app.services.amap_service._get_client", lambda: mock_client)

        result = await get_walking_route(
            (116.397128, 39.916527),
            (116.407, 39.882),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_walking_route_network_error(self, monkeypatch):
        """网络异常时应返回 None。"""
        class _Mock:
            AMAP_API_KEY = "test_key"
            AMAP_SIGN_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        mock_get = AsyncMock(side_effect=Exception("Timeout"))
        mock_client = MagicMock()
        mock_client.get = mock_get
        monkeypatch.setattr("app.services.amap_service._get_client", lambda: mock_client)

        result = await get_walking_route(
            (116.397128, 39.916527),
            (116.407, 39.882),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_walking_route_haversine_exception_handled(self, monkeypatch):
        """Haversine 计算异常时应返回 None（而非崩溃）。"""
        class _Mock:
            AMAP_API_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        # 传入无效坐标触发计算异常
        result = await get_walking_route(
            (float("nan"), 39.916527),
            (116.407, 39.882),
        )
        assert result is None


# =============================================================================
# get_distance_matrix()
# =============================================================================

class TestGetDistanceMatrix:
    """距离矩阵 —— Haversine 回退 + Amap API 调用。"""

    @pytest.mark.asyncio
    async def test_distance_matrix_empty_origins(self):
        """空 origins 列表应返回空列表（不涉及网络调用）。"""
        result = await get_distance_matrix([], (116.4, 39.9))
        assert result == []

    @pytest.mark.asyncio
    async def test_distance_matrix_haversine_fallback(self, monkeypatch):
        """Key 为空时使用 Haversine 公式估算所有距离。"""
        class _Mock:
            AMAP_API_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        origins = [
            (116.397, 39.916),  # 故宫
            (116.407, 39.882),  # 天坛
            (116.46, 39.92),    # 798 艺术区附近
        ]
        dest = (116.4, 39.9)  # 天安门附近

        results = await get_distance_matrix(origins, dest)
        assert len(results) == 3
        for r in results:
            assert "distance_m" in r
            assert "duration_s" in r
            assert r["distance_m"] >= 0
            assert r["duration_s"] >= 0

    @pytest.mark.asyncio
    async def test_distance_matrix_truncated_to_10(self, monkeypatch):
        """超过 10 个 origins 时只处理前 10 个。"""
        class _Mock:
            AMAP_API_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        many_origins = [(116.4 + i * 0.001, 39.9 + i * 0.001) for i in range(15)]
        results = await get_distance_matrix(many_origins, (116.4, 39.9))
        assert len(results) == 10  # 只返回前 10 个

    @pytest.mark.asyncio
    async def test_distance_matrix_success(self, monkeypatch):
        """Mock Amap API 返回距离矩阵解析结果。"""
        class _Mock:
            AMAP_API_KEY = "test_key"
            AMAP_SIGN_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "1",
            "info": "OK",
            "results": [
                {"distance": "3800", "duration": "300"},
                {"distance": "5200", "duration": "450"},
            ],
        }
        mock_get = AsyncMock(return_value=mock_resp)
        mock_client = MagicMock()
        mock_client.get = mock_get
        monkeypatch.setattr("app.services.amap_service._get_client", lambda: mock_client)

        origins = [(116.397, 39.916), (116.407, 39.882)]
        dest = (116.4, 39.9)

        results = await get_distance_matrix(origins, dest)
        assert len(results) == 2
        assert results[0]["distance_m"] == 3800
        assert results[0]["duration_s"] == 300
        assert results[1]["distance_m"] == 5200
        assert results[1]["duration_s"] == 450

    @pytest.mark.asyncio
    async def test_distance_matrix_api_failure(self, monkeypatch):
        """API 返回 status != 1 时应返回空列表。"""
        class _Mock:
            AMAP_API_KEY = "test_key"
            AMAP_SIGN_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "0",
            "info": "INVALID_REQUEST",
        }
        mock_get = AsyncMock(return_value=mock_resp)
        mock_client = MagicMock()
        mock_client.get = mock_get
        monkeypatch.setattr("app.services.amap_service._get_client", lambda: mock_client)

        results = await get_distance_matrix(
            [(116.397, 39.916)], (116.4, 39.9)
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_distance_matrix_network_error(self, monkeypatch):
        """网络异常时应返回空列表。"""
        class _Mock:
            AMAP_API_KEY = "test_key"
            AMAP_SIGN_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        mock_get = AsyncMock(side_effect=Exception("Connection error"))
        mock_client = MagicMock()
        mock_client.get = mock_get
        monkeypatch.setattr("app.services.amap_service._get_client", lambda: mock_client)

        results = await get_distance_matrix(
            [(116.397, 39.916)], (116.4, 39.9)
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_distance_matrix_haversine_bad_coord_returns_zero(self, monkeypatch):
        """Haversine 回退中单个坐标解析异常应返回 0 距离。"""
        class _Mock:
            AMAP_API_KEY = ""
        monkeypatch.setattr("app.services.amap_service.settings", _Mock())

        origins = [(116.397, 39.916), (float("inf"), 39.9)]
        results = await get_distance_matrix(origins, (116.4, 39.9))
        assert len(results) == 2
        assert results[0]["distance_m"] > 0  # 正常坐标
        assert results[1]["distance_m"] == 0  # 异常坐标应兜底为 0
