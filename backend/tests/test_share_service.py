"""
Tests for share_service module.
"""
import pytest
import os
from app.services import share_service

@pytest.fixture(autouse=True)
def cleanup_shares():
    """Cleanup shares before and after each test."""
    # Cleanup before test
    import shutil
    from pathlib import Path
    share_root = Path(share_service._SHARE_ROOT)
    if share_root.exists():
        shutil.rmtree(share_root)
    yield
    # Cleanup after test
    if share_root.exists():
        shutil.rmtree(share_root)

def test_create_and_get_share():
    """Test basic create and get functionality."""
    device_id = "test-device-123"
    itinerary_id = "test-itinerary-456"
    
    share_id = share_service.create_share(device_id, itinerary_id, expires_days=30)
    assert share_id is not None
    
    # Get the share
    record = share_service.get_share(share_id)
    assert record is not None
    assert record["share_id"] == share_id
    assert record["device_id"] == device_id
    assert record["itinerary_id"] == itinerary_id
    assert record["days_valid"] == 30

def test_get_nonexistent_share():
    """Test getting a non-existent share."""
    result = share_service.get_share("non-existent-id")
    assert result is None

def test_delete_share():
    """Test delete functionality."""
    device_id = "test-device-123"
    itinerary_id = "test-itinerary-456"
    
    share_id = share_service.create_share(device_id, itinerary_id)
    assert share_service.get_share(share_id) is not None
    
    deleted = share_service.delete_share(share_id)
    assert deleted is True
    assert share_service.get_share(share_id) is None

def test_delete_nonexistent_share():
    """Test deleting a non-existent share."""
    deleted = share_service.delete_share("non-existent-id")
    assert deleted is False

def test_list_shares():
    """Test listing shares by device."""
    device_id = "test-device-123"
    
    # Create multiple shares
    share_service.create_share(device_id, "itinerary-1")
    share_service.create_share(device_id, "itinerary-2")
    share_service.create_share("other-device", "itinerary-3")
    
    shares = share_service.list_shares(device_id)
    assert len(shares) == 2

def test_different_expiry_days():
    """Test creating shares with different expiry days."""
    share_id_7 = share_service.create_share("device", "itin-1", expires_days=7)
    share_id_90 = share_service.create_share("device", "itin-2", expires_days=90)
    
    record_7 = share_service.get_share(share_id_7)
    record_90 = share_service.get_share(share_id_90)
    
    assert record_7["days_valid"] == 7
    assert record_90["days_valid"] == 90
