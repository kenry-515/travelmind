"""
TravelMind Agent — Orchestrator 管线测试（Phase 12.29d）

mock 所有子 agent 模块级引用来测试管线编排和错误处理。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def mock_all_agents():
    """Mock orchestrator 模块级的惰性子 agent 引用。"""
    patches = {
        "_extract_profile": AsyncMock(return_value={
            "destination": "重庆", "tags": ["美食", "夜景"],
            "budget_level": "舒适", "days": 3,
        }),
        "_analyze_trends": AsyncMock(return_value=[
            {"place": "洪崖洞", "heat_score": 90, "tag": "夜景"},
        ]),
        "_get_weather_forecast": AsyncMock(return_value=MagicMock(
            city="重庆", daily=[], overall_score=0.8, advice="适合出行",
            lat=29.56, lon=106.55,
        )),
        "_retrieve": AsyncMock(return_value=[
            {"name": "洪崖洞", "city": "重庆", "tags": ["夜景", "地标"]},
        ]),
        "_recommend": AsyncMock(return_value=[
            {"name": "洪崖洞", "city": "重庆", "total_score": 0.92, "tags": ["夜景"]},
        ]),
        "_generate_itinerary": AsyncMock(return_value={
            "trip": {"title": "重庆三日游", "city": "重庆", "daysCount": 3},
            "days": [
                {"day": 1, "theme": "夜景", "title": "山城夜景", "items": [{"poi": "洪崖洞", "time": "18:00"}]},
                {"day": 2, "theme": "美食", "title": "重庆味道", "items": [{"poi": "解放碑", "time": "10:00"}]},
                {"day": 3, "theme": "休闲", "title": "慢享重庆", "items": [{"poi": "磁器口", "time": "09:00"}]},
            ],
        }),
    }
    with patch.multiple(
        "app.agents.orchestrator",
        **patches,
        create=True,  # _get_weather_forecast may be None; create=True handles this
    ):
        yield


async def test_workflow_full_pipeline(mock_all_agents):
    """7 步管线应完整执行并返回行程。"""
    from app.agents.orchestrator import run_travel_workflow
    state = await run_travel_workflow("重庆3日游，喜欢美食和夜景")
    assert state is not None
    assert state.get("itinerary") is not None
    assert state["itinerary"]["trip"]["city"] == "重庆"


async def test_workflow_profile_sets_upstream(mock_all_agents):
    """Profile 提取结果应在 state 中可用。"""
    from app.agents.orchestrator import run_travel_workflow
    state = await run_travel_workflow("重庆3日游")
    assert state.get("user_profile") is not None
    assert state["user_profile"].get("destination") == "重庆"


async def test_workflow_minimal_input():
    """极简输入不应崩溃。"""
    from unittest.mock import patch as _patch
    with _patch("app.agents.orchestrator._extract_profile", new_callable=AsyncMock) as mp, \
         _patch("app.agents.orchestrator._analyze_trends", new_callable=AsyncMock) as mt, \
         _patch("app.agents.orchestrator._get_weather_forecast", new_callable=AsyncMock) as mw, \
         _patch("app.agents.orchestrator._retrieve", new_callable=AsyncMock) as mr, \
         _patch("app.agents.orchestrator._recommend", new_callable=AsyncMock) as mrec, \
         _patch("app.agents.orchestrator._generate_itinerary", new_callable=AsyncMock) as mp_plan:
        mp.return_value = {"destination": "成都", "tags": [], "budget_level": "适中", "days": 2}
        mt.return_value = []
        mw.return_value = MagicMock(city="成都", overall_score=0.7, daily=[])
        mr.return_value = []
        mrec.return_value = []
        mp_plan.return_value = {"trip": {"title": "成都2日游", "city": "成都", "daysCount": 2}, "days": []}
        from app.agents.orchestrator import run_travel_workflow
        state = await run_travel_workflow("成都")
        assert state is not None


async def test_workflow_no_input():
    """空输入不应崩溃。"""
    from app.agents.orchestrator import run_travel_workflow
    state = await run_travel_workflow("")
    assert state is not None
