"""
TravelMind Agent — Vision Agent 单元测试（Phase 12.29+）

测试图片分析的标签标准化、非中国地点判定、地理提示等纯函数逻辑。
不调用实际视觉 API —— 纯确定性测试。

注意：只有 async 测试使用 pytest.mark.asyncio；纯函数测试不标记。
"""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def mock_vision_provider():
    """Mock vision provider to avoid real Kimi API calls."""
    provider = AsyncMock()
    provider.analyze_image.return_value = {
        "location": "洪崖洞",
        "landmark_features": "吊脚楼建筑群，灯光夜景",
        "tags": ["夜景", "地标", "建筑"],
        "description": "重庆洪崖洞夜景，典型的吊脚楼建筑群",
        "confidence": 0.92,
    }
    provider.model = "kimi-k2.6"
    with patch("app.agents.vision_agent.get_vision_provider", return_value=provider):
        yield provider


@pytest.fixture(autouse=True)
def mock_tags_file():
    """Mock tags.json to return a known taxonomy."""
    import json
    from unittest.mock import mock_open

    mock_data = {
        "all_tags": ["夜景", "地标", "建筑", "美食", "摄影", "历史", "自然", "博物馆",
                     "古镇", "寺庙", "海岛", "爬山", "日出", "日落", "湖泊", "森林",
                     "休闲", "小众", "文艺", "打卡", "网红打卡", "亲子", "情侣", "家庭",
                     "购物", "艺术", "田园", "探险", "极限运动", "温泉", "滑雪"]
    }
    with patch("app.agents.vision_agent.open", mock_open(read_data=json.dumps(mock_data))):
        yield


def test_clean_result_with_valid_location():
    """有效中国地点应保留位置信息。"""
    from app.agents.vision_agent import _clean_result, _load_valid_tags

    valid_tags = _load_valid_tags()
    result = _clean_result({
        "location": "洪崖洞",
        "landmark_features": "吊脚楼建筑群，灯光夜景",
        "tags": ["夜景", "地标", "建筑"],
        "description": "重庆洪崖洞夜景",
        "confidence": 0.92,
    }, valid_tags)
    assert result["location"] == "洪崖洞"
    assert "夜景" in result["tags"]
    assert result["confidence"] == 0.92


def test_clean_result_non_china_rejection():
    """非中国地点应被清空 location。"""
    from app.agents.vision_agent import _clean_result, _load_valid_tags

    valid_tags = _load_valid_tags()
    result = _clean_result({
        "location": "Eiffel Tower",
        "landmark_features": "铁塔，巴黎城市景观",
        "tags": ["建筑", "地标"],
        "description": "法国巴黎埃菲尔铁塔",
        "confidence": 0.95,
    }, valid_tags)
    assert result["location"] == ""  # 应被拒绝
    assert result["confidence"] == 0.0  # 没有 location 时 confidence 应归零


def test_geographic_hint_karst():
    """喀斯特地貌应提示广西/贵州。"""
    from app.agents.vision_agent import _geographic_hint

    hint = _geographic_hint("喀斯特峰林地貌，溶洞景观")
    assert "广西" in hint or "贵州" in hint


def test_geographic_hint_empty():
    """空地貌特征应返回空字符串。"""
    from app.agents.vision_agent import _geographic_hint
    assert _geographic_hint("") == ""


def test_geographic_hint_snow_mountain():
    """雪山应提示云南/四川/西藏/新疆。"""
    from app.agents.vision_agent import _geographic_hint
    hint = _geographic_hint("雪山冰川，巍峨壮观")
    assert "云南" in hint or "四川" in hint or "西藏" in hint


def test_normalize_tag_exact_match():
    """精确匹配的标签应直接返回。"""
    from app.agents.vision_agent import _normalize_tag
    valid = {"夜景", "美食", "摄影"}

    assert _normalize_tag("夜景", valid) == "夜景"
    assert _normalize_tag("美食", valid) == "美食"


def test_normalize_tag_substring():
    """子串匹配应正常工作。"""
    from app.agents.vision_agent import _normalize_tag
    valid = {"夜景", "网红打卡", "摄影"}

    assert _normalize_tag("夜景拍摄", valid) == "夜景"
    assert _normalize_tag("打卡", valid) == "网红打卡"


def test_normalize_tag_no_match():
    """没有任何匹配的标签应返回 None。"""
    from app.agents.vision_agent import _normalize_tag
    valid = {"夜景", "美食", "摄影"}

    assert _normalize_tag("滑雪", valid) is None


def test_looks_non_china():
    """非中国关键词检测应正确。"""
    from app.agents.vision_agent import _looks_non_china

    assert _looks_non_china("germany"), "germany 关键词应被识别"
    assert _looks_non_china("日本"), "日本关键词应被识别"
    assert _looks_non_china("thailand"), "thailand 应被识别"
    assert _looks_non_china("bali"), "bali 应被识别"
    assert not _looks_non_china("洪崖洞"), "国内地名不应被拒绝"
    assert not _looks_non_china("西湖"), "国内地名不应被拒绝"


def test_geographic_hint_karst():
    """喀斯特地貌应提示广西/贵州。"""
    from app.agents.vision_agent import _geographic_hint

    hint = _geographic_hint("喀斯特峰林地貌，溶洞景观")
    assert "广西" in hint or "贵州" in hint


def test_geographic_hint_empty():
    """空地貌特征应返回空字符串。"""
    from app.agents.vision_agent import _geographic_hint

    assert _geographic_hint("") == ""


@pytest.mark.asyncio
async def test_analyze_travel_image_success(mock_vision_provider):
    """完整的图片分析流程应返回结构化结果。"""
    from app.agents.vision_agent import analyze_travel_image

    result = await analyze_travel_image("data:image/jpeg;base64,/9j/4AAQ...")
    assert result is not None
    assert "location" in result
    assert "tags" in result
    assert "confidence" in result
    assert "kb_matches" in result


@pytest.mark.asyncio
async def test_analyze_travel_image_empty(mock_vision_provider):
    """空结果应抛出 RuntimeError。"""
    from app.agents.vision_agent import analyze_travel_image

    mock_vision_provider.analyze_image.return_value = {
        "location": "",
        "landmark_features": "",
        "tags": [],
        "description": "",
        "confidence": 0.0,
    }
    with pytest.raises(RuntimeError):
        await analyze_travel_image("data:image/jpeg;base64,empty...")


# ── _geographic_hint additional tests ──


def test_geographic_hint_danxia():
    """丹霞地貌应提示广东/福建/甘肃。"""
    from app.agents.vision_agent import _geographic_hint

    hint = _geographic_hint("丹霞地貌，彩色丘陵")
    assert "广东" in hint or "福建" in hint or "甘肃" in hint


def test_geographic_hint_snow_forest():
    """雪原+雾凇应提示哈尔滨/吉林。"""
    from app.agents.vision_agent import _geographic_hint

    hint = _geographic_hint("雪原林海，雾凇景观")
    assert "哈尔滨" in hint or "吉林" in hint


def test_geographic_hint_terrace():
    """梯田应提示云南/广西/贵州/福建。"""
    from app.agents.vision_agent import _geographic_hint

    hint = _geographic_hint("梯田稻作，层层叠叠")
    assert "云南" in hint or "广西" in hint or "贵州" in hint or "福建" in hint


def test_geographic_hint_grassland():
    """草原+蒙古包应提示内蒙古/新疆/青海/四川。"""
    from app.agents.vision_agent import _geographic_hint

    hint = _geographic_hint("辽阔草原，蒙古包点缀其间")
    assert "内蒙古" in hint or "新疆" in hint or "青海" in hint or "四川" in hint


def test_geographic_hint_sutra_streamer():
    """经幡应提示西藏/四川/云南/青海。"""
    from app.agents.vision_agent import _geographic_hint

    hint = _geographic_hint("五彩经幡，藏式寺庙")
    assert "西藏" in hint or "四川" in hint or "云南" in hint or "青海" in hint


# ── _clean_result additional boundary tests ──


def test_clean_result_location_is_number():
    """location 是数字时应能正确转为字符串。"""
    from app.agents.vision_agent import _clean_result, _load_valid_tags

    valid_tags = _load_valid_tags()
    result = _clean_result({
        "location": 12345,
        "landmark_features": "现代建筑",
        "tags": ["建筑"],
        "description": "某地标建筑",
        "confidence": 0.8,
    }, valid_tags)
    assert result["location"] == "12345"


def test_clean_result_tags_is_string():
    """tags 是字符串时应包装为列表。"""
    from app.agents.vision_agent import _clean_result, _load_valid_tags

    valid_tags = _load_valid_tags()
    result = _clean_result({
        "location": "洪崖洞",
        "landmark_features": "吊脚楼建筑群",
        "tags": "夜景",
        "description": "重庆洪崖洞",
        "confidence": 0.9,
    }, valid_tags)
    assert isinstance(result["tags"], list)
    assert "夜景" in result["tags"]


def test_clean_result_confidence_invalid():
    """confidence 无法转为 float 时应默认为 0.0。"""
    from app.agents.vision_agent import _clean_result, _load_valid_tags

    valid_tags = _load_valid_tags()
    result = _clean_result({
        "location": "洪崖洞",
        "landmark_features": "吊脚楼建筑群",
        "tags": ["夜景"],
        "description": "重庆洪崖洞",
        "confidence": "not-a-number",
    }, valid_tags)
    assert result["confidence"] == 0.0


def test_clean_result_location_and_high_confidence():
    """location 非空且置信度高时应保留 confidence。"""
    from app.agents.vision_agent import _clean_result, _load_valid_tags

    valid_tags = _load_valid_tags()
    result = _clean_result({
        "location": "张家界",
        "landmark_features": "砂岩峰林",
        "tags": ["自然", "爬山"],
        "description": "张家界国家森林公园",
        "confidence": 0.95,
    }, valid_tags)
    assert result["location"] == "张家界"
    assert result["confidence"] == 0.95


def test_clean_result_non_china_confidence_cleared():
    """location 含非中国关键词时 location 和 confidence 都清零。"""
    from app.agents.vision_agent import _clean_result, _load_valid_tags

    valid_tags = _load_valid_tags()
    result = _clean_result({
        "location": "日本东京塔",
        "landmark_features": "现代铁塔，城市景观",
        "tags": ["建筑", "地标"],
        "description": "日本东京塔",
        "confidence": 0.95,
    }, valid_tags)
    assert result["location"] == ""
    assert result["confidence"] == 0.0


def test_clean_result_all_empty():
    """所有字段都空时应返回全空结果。"""
    from app.agents.vision_agent import _clean_result, _load_valid_tags

    valid_tags = _load_valid_tags()
    result = _clean_result({
        "location": "",
        "landmark_features": "",
        "tags": [],
        "description": "",
        "confidence": 0.0,
    }, valid_tags)
    assert result["location"] == ""
    assert result["landmark_features"] == ""
    assert result["tags"] == []
    assert result["description"] == ""
    assert result["confidence"] == 0.0
