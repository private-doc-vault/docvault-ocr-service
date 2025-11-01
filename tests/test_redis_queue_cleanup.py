"""
Tests for Redis queue cleanup functionality
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from app.redis_queue import RedisQueueManager
from app.models import TaskStatus


@pytest.fixture
def mock_redis():
    """Mock Redis client for cleanup tests"""
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.keys = AsyncMock(return_value=[])
    redis_mock.hgetall = AsyncMock(return_value={})
    redis_mock.exists = AsyncMock(return_value=0)
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.close = AsyncMock()
    return redis_mock


class TestRedisTaskCleanup:
    """Test suite for cleaning up old completed tasks from Redis"""

    @pytest.mark.asyncio
    async def test_find_old_completed_tasks_returns_empty_when_no_tasks(self, mock_redis):
        """Should return empty list when no completed tasks exist"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            mock_redis.keys.return_value = []

            cutoff_date = datetime.utcnow() - timedelta(days=7)
            old_tasks = await manager.find_old_completed_tasks(cutoff_date)

            assert old_tasks == []
            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_find_old_completed_tasks_returns_tasks_older_than_cutoff(self, mock_redis):
        """Should return only completed tasks older than cutoff date"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mock Redis keys() to return two task keys
            mock_redis.keys.return_value = [b"task:old-123", b"task:recent-456"]

            # Mock old task (8 days ago) and recent task (2 days ago)
            old_timestamp = (datetime.utcnow() - timedelta(days=8)).isoformat()
            recent_timestamp = (datetime.utcnow() - timedelta(days=2)).isoformat()

            # Create AsyncMock for hgetall that returns different values
            call_count = [0]

            async def hgetall_side_effect(key):
                call_count[0] += 1
                if call_count[0] == 1:  # First call for old task
                    return {
                        b"task_id": b"old-123",
                        b"status": b"COMPLETED",
                        b"completed_at": old_timestamp.encode()
                    }
                else:  # Second call for recent task
                    return {
                        b"task_id": b"recent-456",
                        b"status": b"COMPLETED",
                        b"completed_at": recent_timestamp.encode()
                    }

            mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

            cutoff_date = datetime.utcnow() - timedelta(days=7)
            old_tasks = await manager.find_old_completed_tasks(cutoff_date)

            assert len(old_tasks) == 1
            assert old_tasks[0] == "old-123"

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_find_old_completed_tasks_excludes_non_completed_tasks(self, mock_redis):
        """Should only return COMPLETED tasks, not PROCESSING or FAILED"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            mock_redis.keys.return_value = [b"task:proc-123", b"task:failed-456", b"task:done-789"]

            old_timestamp = (datetime.utcnow() - timedelta(days=10)).isoformat()

            call_count = [0]

            async def hgetall_side_effect(key):
                call_count[0] += 1
                if call_count[0] == 1:  # Processing task
                    return {
                        b"task_id": b"proc-123",
                        b"status": b"PROCESSING",
                        b"task_started_at": old_timestamp.encode()
                    }
                elif call_count[0] == 2:  # Failed task
                    return {
                        b"task_id": b"failed-456",
                        b"status": b"FAILED",
                        b"completed_at": old_timestamp.encode()
                    }
                else:  # Completed task
                    return {
                        b"task_id": b"done-789",
                        b"status": b"COMPLETED",
                        b"completed_at": old_timestamp.encode()
                    }

            mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

            cutoff_date = datetime.utcnow() - timedelta(days=7)
            old_tasks = await manager.find_old_completed_tasks(cutoff_date)

            assert len(old_tasks) == 1
            assert old_tasks[0] == "done-789"

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_delete_task_removes_task_from_redis(self, mock_redis):
        """Should completely remove task data from Redis"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            mock_redis.exists.return_value = 1
            mock_redis.delete.return_value = 2  # Both task and result deleted

            deleted = await manager.delete_task("task-123")

            assert deleted is True
            mock_redis.delete.assert_called_once()

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_delete_task_returns_false_for_nonexistent_task(self, mock_redis):
        """Should return False when trying to delete non-existent task"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            mock_redis.exists.return_value = 0

            deleted = await manager.delete_task("nonexistent-task-id")

            assert deleted is False

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_cleanup_old_completed_tasks_removes_multiple_tasks(self, mock_redis):
        """Should delete multiple old completed tasks in one operation"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mock 5 old tasks
            mock_redis.keys.return_value = [
                b"task:1", b"task:2", b"task:3", b"task:4", b"task:5"
            ]

            old_timestamp = (datetime.utcnow() - timedelta(days=10)).isoformat()

            call_count = [0]

            # Mock all tasks as completed and old
            async def hgetall_side_effect(key):
                call_count[0] += 1
                task_num = call_count[0]
                return {
                    b"task_id": f"{task_num}".encode(),
                    b"status": b"COMPLETED",
                    b"completed_at": old_timestamp.encode()
                }

            mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

            # Mock successful deletions
            mock_redis.exists.return_value = 1
            mock_redis.delete.return_value = 2

            cutoff_date = datetime.utcnow() - timedelta(days=7)
            deleted_count = await manager.cleanup_old_completed_tasks(cutoff_date)

            assert deleted_count == 5

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_cleanup_old_completed_tasks_with_dry_run(self, mock_redis):
        """Should not delete tasks when dry_run is True"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            mock_redis.keys.return_value = [b"task:123"]

            old_timestamp = (datetime.utcnow() - timedelta(days=10)).isoformat()

            async def hgetall_side_effect(key):
                return {
                    b"task_id": b"123",
                    b"status": b"COMPLETED",
                    b"completed_at": old_timestamp.encode()
                }

            mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

            cutoff_date = datetime.utcnow() - timedelta(days=7)
            deleted_count = await manager.cleanup_old_completed_tasks(cutoff_date, dry_run=True)

            # Should report what would be deleted
            assert deleted_count == 1

            # But delete should not be called
            mock_redis.delete.assert_not_called()

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_cleanup_old_completed_tasks_handles_missing_completed_at(self, mock_redis):
        """Should skip tasks without completed_at timestamp"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            mock_redis.keys.return_value = [b"task:123"]

            # Task without completed_at
            mock_redis.hgetall.return_value = {
                b"task_id": b"123",
                b"status": b"COMPLETED"
            }

            cutoff_date = datetime.utcnow() - timedelta(days=7)
            deleted_count = await manager.cleanup_old_completed_tasks(cutoff_date)

            # Should not delete task without timestamp
            assert deleted_count == 0

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_cleanup_old_completed_tasks_returns_zero_when_no_old_tasks(self, mock_redis):
        """Should return 0 when no old tasks to cleanup"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            mock_redis.keys.return_value = [b"task:123"]

            # Recent task (2 days ago)
            recent_timestamp = (datetime.utcnow() - timedelta(days=2)).isoformat()
            mock_redis.hgetall.return_value = {
                b"task_id": b"123",
                b"status": b"COMPLETED",
                b"completed_at": recent_timestamp.encode()
            }

            # Try to cleanup tasks older than 7 days
            cutoff_date = datetime.utcnow() - timedelta(days=7)
            deleted_count = await manager.cleanup_old_completed_tasks(cutoff_date)

            assert deleted_count == 0

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_find_old_completed_tasks_handles_invalid_timestamp_format(self, mock_redis):
        """Should skip tasks with invalid timestamp format"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            mock_redis.keys.return_value = [b"task:123"]

            # Task with invalid timestamp
            mock_redis.hgetall.return_value = {
                b"task_id": b"123",
                b"status": b"COMPLETED",
                b"completed_at": b"invalid-timestamp"
            }

            cutoff_date = datetime.utcnow() - timedelta(days=7)
            old_tasks = await manager.find_old_completed_tasks(cutoff_date)

            # Should skip task with invalid timestamp
            assert len(old_tasks) == 0

            await manager.disconnect()
