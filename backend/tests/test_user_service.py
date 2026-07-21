"""
TravelMind Agent — User Service Tests

Tests for anonymous user lifecycle: get_or_create_user, get_user_by_device_id.
Uses mocked AsyncSession — no real DB connection required.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.user_service import get_or_create_user, get_user_by_device_id
from app.database.models import User


class TestGetOrCreateUser:
    """Tests for get_or_create_user()."""

    @pytest.mark.asyncio
    async def test_creates_new_user_when_not_found(self):
        """First call with a new device_id should create a User."""
        db = AsyncMock(spec=AsyncSession)
        # Simulate no existing user
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        user = await get_or_create_user(db, "device-abc-123")

        # Verify user was created
        db.add.assert_called_once()
        db.commit.assert_called_once()
        assert user.device_id == "device-abc-123"
        assert user.is_anonymous is True

    @pytest.mark.asyncio
    async def test_returns_existing_user(self):
        """Second call with the same device_id should return existing User."""
        db = AsyncMock(spec=AsyncSession)
        existing = User(device_id="device-abc-123", is_anonymous=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        db.execute.return_value = mock_result

        user = await get_or_create_user(db, "device-abc-123")

        # Verify no new user was created
        db.add.assert_not_called()
        db.commit.assert_not_called()
        assert user is existing
        assert user.device_id == "device-abc-123"

    @pytest.mark.asyncio
    async def test_creates_user_with_nickname(self):
        """Creating a user with a nickname should set it."""
        db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        user = await get_or_create_user(db, "device-xyz", nickname="测试用户")

        assert user.nickname == "测试用户"


class TestGetUserByDeviceId:
    """Tests for get_user_by_device_id()."""

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_device(self):
        """Looking up an unknown device_id should return None."""
        db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        user = await get_user_by_device_id(db, "nonexistent")

        assert user is None

    @pytest.mark.asyncio
    async def test_returns_user_for_known_device(self):
        """Looking up a known device_id should return the User."""
        db = AsyncMock(spec=AsyncSession)
        existing = User(device_id="known-device", is_anonymous=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        db.execute.return_value = mock_result

        user = await get_user_by_device_id(db, "known-device")

        assert user is existing
        assert user.device_id == "known-device"
