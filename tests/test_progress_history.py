"""
Tests for Progress History Tracking in Redis (Task 5.8)
Tests that progress updates are stored in Redis for debugging and monitoring
"""
import pytest
import json
from datetime import datetime
from unittest.mock import AsyncMock, Mock

from app.redis_queue import RedisQueueManager


class TestProgressHistoryTracking:
    """Test progress history storage and retrieval in Redis"""

    @pytest.fixture
    async def redis_manager(self):
        """Create Redis queue manager with mocked Redis"""
        mock_redis = AsyncMock()
        manager = RedisQueueManager(redis_url="redis://localhost")
        manager.redis = mock_redis
        return manager

    @pytest.mark.asyncio
    async def test_record_progress_update_stores_in_history(self, redis_manager):
        """Test that progress updates are stored in Redis history"""
        task_id = "task-123"
        progress = 25
        operation = "Converting document to images"
        status = "processing"

        await redis_manager.record_progress_update(
            task_id=task_id,
            progress=progress,
            operation=operation,
            status=status
        )

        # Verify Redis LPUSH was called to add to history
        redis_manager.redis.lpush.assert_called_once()
        call_args = redis_manager.redis.lpush.call_args

        # Check the key is correct
        assert call_args[0][0] == f"task:{task_id}:progress_history"

        # Check the data is JSON serialized
        history_entry = call_args[0][1]
        data = json.loads(history_entry)
        assert data['progress'] == progress
        assert data['operation'] == operation
        assert data['status'] == status
        assert 'timestamp' in data

    @pytest.mark.asyncio
    async def test_progress_history_limited_to_10_entries(self, redis_manager):
        """Test that progress history is trimmed to last 10 entries"""
        task_id = "task-123"

        await redis_manager.record_progress_update(
            task_id=task_id,
            progress=50,
            operation="Processing",
            status="processing"
        )

        # Verify LTRIM was called to limit to 10 entries
        redis_manager.redis.ltrim.assert_called_once()
        call_args = redis_manager.redis.ltrim.call_args
        assert call_args[0][0] == f"task:{task_id}:progress_history"
        assert call_args[0][1] == 0  # Start
        assert call_args[0][2] == 9  # End (0-9 = 10 entries)

    @pytest.mark.asyncio
    async def test_get_progress_history_returns_list_of_updates(self, redis_manager):
        """Test retrieving progress history returns chronological list"""
        task_id = "task-123"

        # Mock Redis LRANGE to return history entries
        mock_history = [
            json.dumps({
                "timestamp": "2024-01-15T10:30:00Z",
                "progress": 75,
                "operation": "Extracting metadata",
                "status": "processing"
            }),
            json.dumps({
                "timestamp": "2024-01-15T10:29:30Z",
                "progress": 50,
                "operation": "Performing OCR on page 5/10",
                "status": "processing"
            }),
            json.dumps({
                "timestamp": "2024-01-15T10:29:00Z",
                "progress": 25,
                "operation": "Converting document",
                "status": "processing"
            })
        ]
        redis_manager.redis.lrange = AsyncMock(return_value=[s.encode() for s in mock_history])

        history = await redis_manager.get_progress_history(task_id)

        # Verify correct key was queried
        redis_manager.redis.lrange.assert_called_once_with(
            f"task:{task_id}:progress_history", 0, 9
        )

        # Verify history is returned as list of dicts
        assert len(history) == 3
        assert history[0]['progress'] == 75
        assert history[1]['progress'] == 50
        assert history[2]['progress'] == 25

    @pytest.mark.asyncio
    async def test_get_progress_history_returns_empty_for_new_task(self, redis_manager):
        """Test getting history for task with no history returns empty list"""
        task_id = "new-task-456"
        redis_manager.redis.lrange = AsyncMock(return_value=[])

        history = await redis_manager.get_progress_history(task_id)

        assert history == []

    @pytest.mark.asyncio
    async def test_progress_history_includes_timestamps(self, redis_manager):
        """Test that each progress update includes ISO timestamp"""
        task_id = "task-123"

        await redis_manager.record_progress_update(
            task_id=task_id,
            progress=25,
            operation="Starting OCR",
            status="processing"
        )

        call_args = redis_manager.redis.lpush.call_args
        history_entry = json.loads(call_args[0][1])

        # Verify timestamp is present and valid ISO format
        assert 'timestamp' in history_entry
        # Should be able to parse as ISO datetime
        datetime.fromisoformat(history_entry['timestamp'].replace('Z', '+00:00'))

    @pytest.mark.asyncio
    async def test_progress_history_preserves_order(self, redis_manager):
        """Test that progress history maintains chronological order (newest first)"""
        task_id = "task-123"

        # Simulate multiple progress updates
        updates = [
            (10, "Starting", "processing"),
            (25, "Converting", "processing"),
            (50, "OCR midpoint", "processing"),
            (75, "Metadata", "processing"),
            (100, "Completed", "completed")
        ]

        mock_history = []
        for progress, operation, status in updates:
            entry = json.dumps({
                "timestamp": f"2024-01-15T10:{30+progress//10}:00Z",
                "progress": progress,
                "operation": operation,
                "status": status
            })
            mock_history.insert(0, entry)  # Insert at beginning (newest first)

        redis_manager.redis.lrange = AsyncMock(
            return_value=[s.encode() for s in mock_history]
        )

        history = await redis_manager.get_progress_history(task_id)

        # Newest should be first
        assert history[0]['progress'] == 100
        assert history[1]['progress'] == 75
        assert history[2]['progress'] == 50
        assert history[3]['progress'] == 25
        assert history[4]['progress'] == 10

    @pytest.mark.asyncio
    async def test_progress_history_handles_status_changes(self, redis_manager):
        """Test progress history records status changes (processing → completed/failed)"""
        task_id = "task-123"

        # Record completion
        await redis_manager.record_progress_update(
            task_id=task_id,
            progress=100,
            operation="Processing complete",
            status="completed"
        )

        call_args = redis_manager.redis.lpush.call_args
        history_entry = json.loads(call_args[0][1])

        assert history_entry['status'] == "completed"
        assert history_entry['progress'] == 100

    @pytest.mark.asyncio
    async def test_progress_history_survives_multiple_calls(self, redis_manager):
        """Test that multiple progress updates accumulate in history"""
        task_id = "task-123"

        # Simulate 3 progress updates
        for i, (progress, operation) in enumerate([
            (25, "Converting"),
            (50, "OCR"),
            (75, "Metadata")
        ]):
            redis_manager.redis.lpush = AsyncMock()
            redis_manager.redis.ltrim = AsyncMock()

            await redis_manager.record_progress_update(
                task_id=task_id,
                progress=progress,
                operation=operation,
                status="processing"
            )

            # Each call should add to history
            redis_manager.redis.lpush.assert_called_once()
            redis_manager.redis.ltrim.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_progress_history_with_limit(self, redis_manager):
        """Test getting limited number of history entries"""
        task_id = "task-123"

        mock_history = [
            json.dumps({"timestamp": f"2024-01-15T10:{30+i}:00Z",
                       "progress": i*10, "operation": f"Step {i}", "status": "processing"})
            for i in range(10, 0, -1)  # 10 entries
        ]
        redis_manager.redis.lrange = AsyncMock(return_value=[s.encode() for s in mock_history])

        # Get only last 5 entries
        history = await redis_manager.get_progress_history(task_id, limit=5)

        # Should query with limit
        redis_manager.redis.lrange.assert_called_once_with(
            f"task:{task_id}:progress_history", 0, 4  # 0-4 = 5 entries
        )

    @pytest.mark.asyncio
    async def test_progress_history_cleanup_on_task_deletion(self, redis_manager):
        """Test that progress history is cleaned up when task is deleted"""
        task_id = "task-123"

        # Mock delete_task to delete history as well
        redis_manager.redis.delete = AsyncMock()

        await redis_manager.delete_task(task_id)

        # Should delete both task and its progress history
        delete_calls = redis_manager.redis.delete.call_args_list
        deleted_keys = [call[0][0] for call in delete_calls]

        assert f"task:{task_id}" in deleted_keys or \
               any(f"task:{task_id}" in str(call) for call in delete_calls)

    @pytest.mark.asyncio
    async def test_progress_history_includes_operation_text(self, redis_manager):
        """Test that progress history includes descriptive operation text"""
        task_id = "task-123"
        operation_text = "Performing OCR on page 5/10"

        await redis_manager.record_progress_update(
            task_id=task_id,
            progress=50,
            operation=operation_text,
            status="processing"
        )

        call_args = redis_manager.redis.lpush.call_args
        history_entry = json.loads(call_args[0][1])

        assert history_entry['operation'] == operation_text
        assert len(history_entry['operation']) > 0

    @pytest.mark.asyncio
    async def test_progress_history_with_none_operation(self, redis_manager):
        """Test progress history handles None operation gracefully"""
        task_id = "task-123"

        await redis_manager.record_progress_update(
            task_id=task_id,
            progress=100,
            operation=None,  # No operation when completed
            status="completed"
        )

        call_args = redis_manager.redis.lpush.call_args
        history_entry = json.loads(call_args[0][1])

        # Should handle None gracefully
        assert 'operation' in history_entry
        assert history_entry['operation'] is None or history_entry['operation'] == ""
