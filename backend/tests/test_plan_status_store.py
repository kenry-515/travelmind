"""
Tests for plan_status_store module.
"""
import pytest
import asyncio
from app.services import plan_status_store as pss

@pytest.fixture(autouse=True)
async def cleanup_store():
    """Cleanup the store before and after each test."""
    # Cleanup before test
    for key in list(pss._status_store.keys()):
        await pss.delete_status(key)
    yield
    # Cleanup after test
    for key in list(pss._status_store.keys()):
        await pss.delete_status(key)

@pytest.mark.asyncio
async def test_set_and_get_status():
    """Test basic set and get functionality."""
    task_id = "test-task-123"
    test_data = {"hello": "world", "itinerary": {"days": []}}
    
    # Initially not found
    status = await pss.get_status(task_id)
    assert status is None
    
    # Set generating status
    await pss.set_status(task_id, "generating")
    status = await pss.get_status(task_id)
    assert status is not None
    assert status["status"] == "generating"
    assert status["data"] is None
    
    # Set completed status with data
    await pss.set_status(task_id, "completed", test_data)
    status = await pss.get_status(task_id)
    assert status is not None
    assert status["status"] == "completed"
    assert status["data"] == test_data

@pytest.mark.asyncio
async def test_delete_status():
    """Test delete functionality."""
    task_id = "test-task-delete"
    
    await pss.set_status(task_id, "generating")
    status = await pss.get_status(task_id)
    assert status is not None
    
    await pss.delete_status(task_id)
    status = await pss.get_status(task_id)
    assert status is None

@pytest.mark.asyncio
async def test_error_status():
    """Test error status handling."""
    task_id = "test-task-error"
    error_data = {"message": "Something went wrong"}
    
    await pss.set_status(task_id, "error", error_data)
    status = await pss.get_status(task_id)
    assert status is not None
    assert status["status"] == "error"
    assert status["data"] == error_data

@pytest.mark.asyncio
async def test_concurrent_access():
    """Test concurrent access safety."""
    task_id = "test-task-concurrent"
    
    async def update_status():
        await pss.set_status(task_id, "generating")
        await asyncio.sleep(0.1)
        await pss.set_status(task_id, "completed", {"result": "ok"})
    
    # Run multiple updates concurrently
    await asyncio.gather(
        update_status(),
        update_status(),
        update_status()
    )
    
    status = await pss.get_status(task_id)
    assert status is not None
    assert status["status"] == "completed"
    assert status["data"] == {"result": "ok"}
