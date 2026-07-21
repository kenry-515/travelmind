"""
TravelMind Agent — Favorite Service Tests

Tests for favorites CRUD with mocked AsyncSession.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import favorite_service
from app.database.models import Favorite


class TestAddFavorite:
    """Tests for add_favorite()."""

    @pytest.mark.asyncio
    async def test_returns_none_when_db_none(self):
        """When DB is None, should return None."""
        result = await favorite_service.add_favorite(
            db=None, user_id="u1", target_type="itinerary", target_id="abc"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_adds_new_favorite(self):
        """Adding a new favorite should create a row."""
        db = AsyncMock(spec=AsyncSession)
        # No existing favorite
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        result = await favorite_service.add_favorite(
            db=db, user_id="u1", target_type="itinerary", target_id="itinerary-1"
        )

        db.add.assert_called_once()
        db.commit.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_does_not_duplicate(self):
        """Adding the same favorite twice should not duplicate."""
        db = AsyncMock(spec=AsyncSession)
        existing = Favorite(user_id="u1", target_type="itinerary", target_id="itinerary-1")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        db.execute.return_value = mock_result

        result = await favorite_service.add_favorite(
            db=db, user_id="u1", target_type="itinerary", target_id="itinerary-1"
        )

        db.add.assert_not_called()
        assert result is None  # idempotent — caller treats as success


class TestListFavorites:
    """Tests for list_favorites()."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_db_none(self):
        """When DB is None, should return empty list."""
        result = await favorite_service.list_favorites(db=None, user_id="u1")
        assert result == []


class TestRemoveFavorite:
    """Tests for remove_favorite()."""

    @pytest.mark.asyncio
    async def test_returns_false_when_db_none(self):
        """When DB is None, should return False."""
        ok = await favorite_service.remove_favorite(db=None, favorite_id="f1", user_id="u1")
        assert ok is False
