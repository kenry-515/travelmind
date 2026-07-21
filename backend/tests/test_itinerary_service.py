"""
TravelMind Agent — Itinerary Service Tests

Tests for itinerary CRUD with mocked AsyncSession.
No real database or LLM calls.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import itinerary_service
from app.database.models import Itinerary


SAMPLE_ITINERARY = {
    "trip": {
        "title": "重庆3日美食之旅",
        "city": "重庆",
        "daysCount": 3,
        "dateStart": "2026-08-01",
        "dateEnd": "2026-08-03",
        "stats": [{"value": "3", "label": "天数"}],
    },
    "days": [
        {
            "day": 1,
            "theme": "美食探索",
            "title": "解放碑→洪崖洞",
            "items": [
                {"time": "09:00", "poi": "解放碑", "note": "重庆地标"},
            ],
            "eat": "重庆小面",
        }
    ],
    "budget": [{"label": "餐饮", "amount": 500, "percent": 30}],
    "checklist": [{"text": "带伞"}],
    "tips": ["重庆夏季炎热"],
    "validation_report": {
        "poi_verified": "1/1",
        "route_backtrack": False,
        "weather_fit": "good",
    },
}


class TestSaveItinerary:
    """Tests for save_itinerary()."""

    @pytest.mark.asyncio
    async def test_saves_itinerary_with_all_fields(self):
        """Saving an itinerary should create a row with correct fields."""
        db = AsyncMock(spec=AsyncSession)

        saved = await itinerary_service.save_itinerary(
            db=db,
            user_id="user-uuid-123",
            itinerary=SAMPLE_ITINERARY,
            validation_report=SAMPLE_ITINERARY["validation_report"],
            profile_snapshot={"slots": {"city": "重庆", "days": 3}},
            weather_snapshot={"city": "重庆", "overall_score": 85},
        )

        db.add.assert_called_once()
        db.commit.assert_called_once()
        assert saved is not None

        # Check the object that was added
        added_obj = db.add.call_args[0][0]
        assert added_obj.user_id == "user-uuid-123"
        assert added_obj.title == "重庆3日美食之旅"
        assert added_obj.days == 3
        assert added_obj.plan == SAMPLE_ITINERARY
        assert added_obj.validation_report == SAMPLE_ITINERARY["validation_report"]
        assert added_obj.profile_snapshot == {"slots": {"city": "重庆", "days": 3}}
        assert added_obj.weather_snapshot == {"city": "重庆", "overall_score": 85}

    @pytest.mark.asyncio
    async def test_returns_none_when_db_is_none(self):
        """When DB is None (degraded), save should return None."""
        saved = await itinerary_service.save_itinerary(
            db=None,
            user_id="user-123",
            itinerary=SAMPLE_ITINERARY,
        )
        assert saved is None

    @pytest.mark.asyncio
    async def test_rollback_on_error(self):
        """If commit fails, should rollback and return None."""
        db = AsyncMock(spec=AsyncSession)
        db.commit.side_effect = Exception("connection lost")

        saved = await itinerary_service.save_itinerary(
            db=db,
            user_id="user-123",
            itinerary=SAMPLE_ITINERARY,
        )

        db.rollback.assert_called_once()
        assert saved is None


class TestListItineraries:
    """Tests for list_itineraries()."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_db_none(self):
        """When DB is None, should return empty list."""
        summaries, total = await itinerary_service.list_itineraries(
            db=None, user_id="user-123"
        )
        assert summaries == []
        assert total == 0


class TestGetItinerary:
    """Tests for get_itinerary()."""

    @pytest.mark.asyncio
    async def test_returns_none_when_db_none(self):
        """When DB is None, should return None."""
        result = await itinerary_service.get_itinerary(db=None, itinerary_id="abc")
        assert result is None


class TestDeleteItinerary:
    """Tests for delete_itinerary()."""

    @pytest.mark.asyncio
    async def test_returns_false_when_db_none(self):
        """When DB is None, should return False."""
        ok = await itinerary_service.delete_itinerary(db=None, itinerary_id="abc", user_id="u1")
        assert ok is False
