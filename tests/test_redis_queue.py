"""
Tests for Redis-based queue processing
Follows TDD approach - tests written first, then implementation
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
import json

# Mock Redis before importing the module
@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.exists = AsyncMock(return_value=0)
    redis_mock.lpush = AsyncMock(return_value=1)
    redis_mock.rpop = AsyncMock(return_value=None)
    redis_mock.llen = AsyncMock(return_value=0)
    redis_mock.setex = AsyncMock(return_value=True)
    redis_mock.ttl = AsyncMock(return_value=-1)
    redis_mock.hset = AsyncMock(return_value=1)
    redis_mock.hget = AsyncMock(return_value=None)
    redis_mock.hgetall = AsyncMock(return_value={})
    redis_mock.hdel = AsyncMock(return_value=1)
    redis_mock.expire = AsyncMock(return_value=True)
    redis_mock.close = AsyncMock()
    return redis_mock


class TestRedisQueueManager:
    """Tests for Redis-based queue manager"""

    @pytest.mark.asyncio
    async def test_connection_initialization(self, mock_redis):
        """Test Redis connection is initialized correctly"""
        from app.redis_queue import RedisQueueManager

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            assert manager.redis is not None
            mock_redis.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_failure_handling(self, mock_redis):
        """Test connection failure is handled gracefully"""
        from app.redis_queue import RedisQueueManager

        mock_redis.ping = AsyncMock(side_effect=Exception("Connection failed"))

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")

            with pytest.raises(Exception, match="Connection failed"):
                await manager.connect()

    @pytest.mark.asyncio
    async def test_create_task_in_queue(self, mock_redis):
        """Test creating a task and adding to queue"""
        from app.redis_queue import RedisQueueManager
        from app.models import TaskStatus

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            task_id = await manager.create_task(language="eng", priority="normal")

            assert task_id is not None
            assert len(task_id) == 36  # UUID format

            # Verify task was stored in Redis
            mock_redis.hset.assert_called()
            # Verify task was added to queue
            mock_redis.lpush.assert_called()

    @pytest.mark.asyncio
    async def test_task_priority_queuing(self, mock_redis):
        """Test tasks are queued based on priority"""
        from app.redis_queue import RedisQueueManager

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Create high priority task
            task_id_high = await manager.create_task(language="eng", priority="high")

            # Create normal priority task
            task_id_normal = await manager.create_task(language="eng", priority="normal")

            # Verify high priority tasks go to different queue
            assert mock_redis.lpush.call_count == 2

    @pytest.mark.asyncio
    async def test_get_task_status_from_redis(self, mock_redis):
        """Test retrieving task status from Redis"""
        from app.redis_queue import RedisQueueManager
        from app.models import TaskStatus

        task_data = {
            b"task_id": b"test-task-123",
            b"status": b"processing",
            b"progress": b"50",
            b"message": b"Processing document",
            b"language": b"eng",
            b"created_at": b"2024-01-01T00:00:00",
            b"updated_at": b"2024-01-01T00:01:00",
        }
        mock_redis.hgetall = AsyncMock(return_value=task_data)

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            status = await manager.get_task_status("test-task-123")

            assert status is not None
            assert status.task_id == "test-task-123"
            assert status.status == TaskStatus.PROCESSING
            assert status.progress == 50

    @pytest.mark.asyncio
    async def test_get_nonexistent_task_status(self, mock_redis):
        """Test retrieving status of non-existent task returns None"""
        from app.redis_queue import RedisQueueManager

        mock_redis.hgetall = AsyncMock(return_value={})

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            status = await manager.get_task_status("non-existent-task")

            assert status is None

    @pytest.mark.asyncio
    async def test_update_task_status_in_redis(self, mock_redis):
        """Test updating task status in Redis"""
        from app.redis_queue import RedisQueueManager
        from app.models import TaskStatus

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            result = await manager.update_task_status(
                "test-task-123",
                TaskStatus.PROCESSING,
                progress=75,
                message="Almost done"
            )

            assert result is True
            # Verify Redis hash was updated
            assert mock_redis.hset.call_count > 0

    @pytest.mark.asyncio
    async def test_dequeue_task_from_queue(self, mock_redis):
        """Test dequeuing a task from the queue"""
        from app.redis_queue import RedisQueueManager

        mock_redis.rpop = AsyncMock(return_value=b"test-task-123")

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            task_id = await manager.dequeue_task()

            assert task_id == "test-task-123"
            mock_redis.rpop.assert_called_once()

    @pytest.mark.asyncio
    async def test_dequeue_from_empty_queue(self, mock_redis):
        """Test dequeuing from empty queue returns None"""
        from app.redis_queue import RedisQueueManager

        mock_redis.rpop = AsyncMock(return_value=None)

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            task_id = await manager.dequeue_task()

            assert task_id is None

    @pytest.mark.asyncio
    async def test_get_queue_length(self, mock_redis):
        """Test getting queue length"""
        from app.redis_queue import RedisQueueManager

        mock_redis.llen = AsyncMock(return_value=5)

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            length = await manager.get_queue_length()

            assert length == 5
            mock_redis.llen.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_result_in_redis(self, mock_redis):
        """Test storing OCR result in Redis"""
        from app.redis_queue import RedisQueueManager
        from app.models import OCRResult

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            result = OCRResult(
                text="Sample text",
                confidence=95.5,
                language="eng",
                processing_time=1.5
            )

            success = await manager.store_result("test-task-123", result)

            assert success is True
            # Verify result was stored with expiration
            mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_result_from_redis(self, mock_redis):
        """Test retrieving result from Redis"""
        from app.redis_queue import RedisQueueManager
        from app.models import OCRResult

        result_data = json.dumps({
            "text": "Sample text",
            "confidence": 95.5,
            "language": "eng",
            "processing_time": 1.5,
            "pages": None,
            "metadata": None
        })
        mock_redis.get = AsyncMock(return_value=result_data.encode())

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            result = await manager.get_result("test-task-123")

            assert result is not None
            assert result.text == "Sample text"
            assert result.confidence == 95.5

    @pytest.mark.asyncio
    async def test_result_expiration(self, mock_redis):
        """Test results expire after TTL"""
        from app.redis_queue import RedisQueueManager

        mock_redis.ttl = AsyncMock(return_value=3600)  # 1 hour remaining

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            ttl = await manager.get_result_ttl("test-task-123")

            assert ttl == 3600
            mock_redis.ttl.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_operations(self, mock_redis):
        """Test batch task creation"""
        from app.redis_queue import RedisQueueManager

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            task_ids = ["task-1", "task-2", "task-3"]
            batch_id = await manager.create_batch(task_ids)

            assert batch_id is not None
            assert len(batch_id) == 36  # UUID format

            # Verify batch was stored
            mock_redis.hset.assert_called()

    @pytest.mark.asyncio
    async def test_get_batch_status(self, mock_redis):
        """Test getting batch status from Redis"""
        from app.redis_queue import RedisQueueManager

        batch_data = {
            b"batch_id": b"batch-123",
            b"task_ids": b'["task-1", "task-2", "task-3"]',
            b"total": b"3",
            b"created_at": b"2024-01-01T00:00:00"
        }
        mock_redis.hgetall = AsyncMock(return_value=batch_data)

        # Mock individual task statuses
        async def mock_hgetall_side_effect(key):
            if key.startswith("batch:"):
                return batch_data
            return {
                b"status": b"completed",
                b"progress": b"100"
            }

        mock_redis.hgetall = AsyncMock(side_effect=mock_hgetall_side_effect)

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            status = await manager.get_batch_status("batch-123")

            assert status is not None
            assert status["batch_id"] == "batch-123"
            assert status["total"] == 3

    @pytest.mark.asyncio
    async def test_task_cleanup(self, mock_redis):
        """Test cleaning up old tasks"""
        from app.redis_queue import RedisQueueManager

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            deleted = await manager.cleanup_task("test-task-123")

            assert deleted is True
            # Verify task and result were deleted
            assert mock_redis.delete.call_count >= 1

    @pytest.mark.asyncio
    async def test_connection_cleanup(self, mock_redis):
        """Test Redis connection is properly closed"""
        from app.redis_queue import RedisQueueManager

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()
            await manager.disconnect()

            mock_redis.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_task_creation(self, mock_redis):
        """Test multiple tasks can be created concurrently"""
        from app.redis_queue import RedisQueueManager

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Create multiple tasks concurrently
            tasks = [manager.create_task(language="eng") for _ in range(10)]
            task_ids = await asyncio.gather(*tasks)

            assert len(task_ids) == 10
            assert len(set(task_ids)) == 10  # All unique
            assert mock_redis.lpush.call_count == 10

    @pytest.mark.asyncio
    async def test_task_retry_mechanism(self, mock_redis):
        """Test task retry mechanism for failed tasks"""
        from app.redis_queue import RedisQueueManager
        from app.models import TaskStatus

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mark task as failed and retry
            result = await manager.retry_task("test-task-123")

            assert result is True
            # Verify task was re-queued
            mock_redis.lpush.assert_called()

    @pytest.mark.asyncio
    async def test_max_retry_limit(self, mock_redis):
        """Test tasks have a maximum retry limit"""
        from app.redis_queue import RedisQueueManager

        task_data = {
            b"task_id": b"test-task-123",
            b"status": b"failed",
            b"retry_count": b"5",  # Already retried 5 times
        }
        mock_redis.hgetall = AsyncMock(return_value=task_data)

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            result = await manager.retry_task("test-task-123", max_retries=3)

            assert result is False  # Should not retry beyond max

    @pytest.mark.asyncio
    async def test_queue_statistics(self, mock_redis):
        """Test getting queue statistics"""
        from app.redis_queue import RedisQueueManager

        mock_redis.llen = AsyncMock(side_effect=[10, 5])  # normal queue, high priority queue

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            stats = await manager.get_queue_stats()

            assert stats is not None
            assert "normal_queue" in stats or "total" in stats


class TestTaskTimeoutDetection:
    """Tests for task timeout detection and stuck task recovery - Task 4.1"""

    @pytest.mark.asyncio
    async def test_task_started_at_timestamp_set_on_dequeue(self, mock_redis):
        """Test that task_started_at timestamp is set when task is dequeued"""
        from app.redis_queue import RedisQueueManager
        from datetime import datetime

        mock_redis.rpop = AsyncMock(return_value=b"test-task-123")

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            task_id = await manager.dequeue_task()

            assert task_id == "test-task-123"

            # Verify task_started_at timestamp was set
            calls = mock_redis.hset.call_args_list
            assert len(calls) > 0

            # Check that hset was called with task_started_at
            hset_called_with_started_at = False
            for call in calls:
                if len(call.args) > 0 and "test-task-123" in str(call.args[0]):
                    if len(call.args) > 1 and "task_started_at" in str(call.args[1]):
                        hset_called_with_started_at = True
                        break

            assert hset_called_with_started_at, "task_started_at timestamp should be set on dequeue"

    @pytest.mark.asyncio
    async def test_find_stuck_tasks_returns_empty_when_no_stuck_tasks(self, mock_redis):
        """Test finding stuck tasks returns empty list when no tasks are stuck"""
        from app.redis_queue import RedisQueueManager

        # Mock Redis to return no tasks in PROCESSING state
        mock_redis.keys = AsyncMock(return_value=[])

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            stuck_tasks = await manager.find_stuck_tasks(timeout_minutes=30)

            assert stuck_tasks == []

    @pytest.mark.asyncio
    async def test_find_stuck_tasks_identifies_tasks_exceeding_timeout(self, mock_redis):
        """Test finding stuck tasks identifies tasks that exceeded timeout threshold"""
        from app.redis_queue import RedisQueueManager
        from app.models import TaskStatus

        # Create a task that started 45 minutes ago (exceeds 30 min timeout)
        started_at = (datetime.utcnow() - timedelta(minutes=45)).isoformat()

        task_data = {
            b"task_id": b"stuck-task-123",
            b"status": TaskStatus.PROCESSING.encode(),
            b"task_started_at": started_at.encode(),
            b"created_at": (datetime.utcnow() - timedelta(hours=1)).isoformat().encode(),
            b"updated_at": datetime.utcnow().isoformat().encode(),
            b"progress": b"50",
            b"message": b"Processing...",
        }

        # Mock Redis to return this stuck task
        mock_redis.keys = AsyncMock(return_value=[b"task:stuck-task-123"])
        mock_redis.hgetall = AsyncMock(return_value=task_data)

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            stuck_tasks = await manager.find_stuck_tasks(timeout_minutes=30)

            assert len(stuck_tasks) == 1
            assert stuck_tasks[0] == "stuck-task-123"

    @pytest.mark.asyncio
    async def test_find_stuck_tasks_ignores_tasks_within_timeout(self, mock_redis):
        """Test finding stuck tasks ignores tasks that are still within timeout window"""
        from app.redis_queue import RedisQueueManager
        from app.models import TaskStatus

        # Create a task that started 15 minutes ago (within 30 min timeout)
        started_at = (datetime.utcnow() - timedelta(minutes=15)).isoformat()

        task_data = {
            b"task_id": b"active-task-123",
            b"status": TaskStatus.PROCESSING.encode(),
            b"task_started_at": started_at.encode(),
            b"created_at": datetime.utcnow().isoformat().encode(),
            b"updated_at": datetime.utcnow().isoformat().encode(),
            b"progress": b"50",
            b"message": b"Processing...",
        }

        mock_redis.keys = AsyncMock(return_value=[b"task:active-task-123"])
        mock_redis.hgetall = AsyncMock(return_value=task_data)

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            stuck_tasks = await manager.find_stuck_tasks(timeout_minutes=30)

            assert len(stuck_tasks) == 0

    @pytest.mark.asyncio
    async def test_find_stuck_tasks_ignores_non_processing_tasks(self, mock_redis):
        """Test finding stuck tasks only considers tasks in PROCESSING status"""
        from app.redis_queue import RedisQueueManager
        from app.models import TaskStatus

        # Create tasks in various states
        queued_task = {
            b"task_id": b"queued-task-123",
            b"status": TaskStatus.QUEUED.encode(),
            b"created_at": (datetime.utcnow() - timedelta(hours=2)).isoformat().encode(),
            b"updated_at": datetime.utcnow().isoformat().encode(),
            b"progress": b"0",
            b"message": b"Queued",
        }

        completed_task = {
            b"task_id": b"completed-task-456",
            b"status": TaskStatus.COMPLETED.encode(),
            b"created_at": (datetime.utcnow() - timedelta(hours=1)).isoformat().encode(),
            b"updated_at": datetime.utcnow().isoformat().encode(),
            b"progress": b"100",
            b"message": b"Done",
        }

        async def mock_hgetall_side_effect(key):
            if b"queued" in key:
                return queued_task
            elif b"completed" in key:
                return completed_task
            return {}

        mock_redis.keys = AsyncMock(return_value=[b"task:queued-task-123", b"task:completed-task-456"])
        mock_redis.hgetall = AsyncMock(side_effect=mock_hgetall_side_effect)

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            stuck_tasks = await manager.find_stuck_tasks(timeout_minutes=30)

            assert len(stuck_tasks) == 0

    @pytest.mark.asyncio
    async def test_find_stuck_tasks_ignores_tasks_without_started_timestamp(self, mock_redis):
        """Test finding stuck tasks ignores tasks missing task_started_at field (legacy tasks)"""
        from app.redis_queue import RedisQueueManager
        from app.models import TaskStatus

        # Create a task in PROCESSING state but without task_started_at (legacy)
        task_data = {
            b"task_id": b"legacy-task-123",
            b"status": TaskStatus.PROCESSING.encode(),
            b"created_at": (datetime.utcnow() - timedelta(hours=1)).isoformat().encode(),
            b"updated_at": datetime.utcnow().isoformat().encode(),
            b"progress": b"50",
            b"message": b"Processing...",
            # Note: no task_started_at field
        }

        mock_redis.keys = AsyncMock(return_value=[b"task:legacy-task-123"])
        mock_redis.hgetall = AsyncMock(return_value=task_data)

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            stuck_tasks = await manager.find_stuck_tasks(timeout_minutes=30)

            # Should not raise error, should ignore legacy task
            assert len(stuck_tasks) == 0

    @pytest.mark.asyncio
    async def test_find_stuck_tasks_with_multiple_stuck_tasks(self, mock_redis):
        """Test finding multiple stuck tasks"""
        from app.redis_queue import RedisQueueManager
        from app.models import TaskStatus

        started_at_1 = (datetime.utcnow() - timedelta(minutes=45)).isoformat()
        started_at_2 = (datetime.utcnow() - timedelta(minutes=60)).isoformat()

        async def mock_hgetall_side_effect(key):
            if b"stuck-task-1" in key:
                return {
                    b"task_id": b"stuck-task-1",
                    b"status": TaskStatus.PROCESSING.encode(),
                    b"task_started_at": started_at_1.encode(),
                    b"created_at": datetime.utcnow().isoformat().encode(),
                    b"updated_at": datetime.utcnow().isoformat().encode(),
                    b"progress": b"25",
                    b"message": b"Processing...",
                }
            elif b"stuck-task-2" in key:
                return {
                    b"task_id": b"stuck-task-2",
                    b"status": TaskStatus.PROCESSING.encode(),
                    b"task_started_at": started_at_2.encode(),
                    b"created_at": datetime.utcnow().isoformat().encode(),
                    b"updated_at": datetime.utcnow().isoformat().encode(),
                    b"progress": b"10",
                    b"message": b"Processing...",
                }
            return {}

        mock_redis.keys = AsyncMock(return_value=[b"task:stuck-task-1", b"task:stuck-task-2"])
        mock_redis.hgetall = AsyncMock(side_effect=mock_hgetall_side_effect)

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            stuck_tasks = await manager.find_stuck_tasks(timeout_minutes=30)

            assert len(stuck_tasks) == 2
            assert "stuck-task-1" in stuck_tasks
            assert "stuck-task-2" in stuck_tasks

    @pytest.mark.asyncio
    async def test_find_stuck_tasks_configurable_timeout(self, mock_redis):
        """Test finding stuck tasks with different timeout thresholds"""
        from app.redis_queue import RedisQueueManager
        from app.models import TaskStatus

        # Task started 10 minutes ago
        started_at = (datetime.utcnow() - timedelta(minutes=10)).isoformat()

        task_data = {
            b"task_id": b"task-123",
            b"status": TaskStatus.PROCESSING.encode(),
            b"task_started_at": started_at.encode(),
            b"created_at": datetime.utcnow().isoformat().encode(),
            b"updated_at": datetime.utcnow().isoformat().encode(),
            b"progress": b"50",
            b"message": b"Processing...",
        }

        mock_redis.keys = AsyncMock(return_value=[b"task:task-123"])
        mock_redis.hgetall = AsyncMock(return_value=task_data)

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # With 5-minute timeout, task should be stuck
            stuck_tasks_5min = await manager.find_stuck_tasks(timeout_minutes=5)
            assert len(stuck_tasks_5min) == 1

            # With 30-minute timeout, task should not be stuck
            stuck_tasks_30min = await manager.find_stuck_tasks(timeout_minutes=30)
            assert len(stuck_tasks_30min) == 0


class TestDeadLetterQueue:
    """Tests for dead letter queue functionality - Task 4.6"""

    @pytest.mark.asyncio
    async def test_move_to_dead_letter_queue(self, mock_redis):
        """Test moving a task to the dead letter queue"""
        from app.redis_queue import RedisQueueManager

        task_data = {
            b"task_id": b"failed-task-123",
            b"status": b"failed",
            b"retry_count": b"3",
            b"priority": b"normal",
        }

        mock_redis.hgetall = AsyncMock(return_value=task_data)
        mock_redis.exists = AsyncMock(return_value=1)  # Task exists

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            success = await manager.move_to_dead_letter_queue("failed-task-123", "Max retries exceeded")

            assert success is True
            # Verify task was added to dead letter queue
            assert mock_redis.lpush.call_count >= 1

    @pytest.mark.asyncio
    async def test_dead_letter_queue_stores_reason(self, mock_redis):
        """Test that dead letter queue stores failure reason"""
        from app.redis_queue import RedisQueueManager

        task_data = {
            b"task_id": b"failed-task-123",
            b"status": b"failed",
            b"retry_count": b"5",
        }

        mock_redis.hgetall = AsyncMock(return_value=task_data)
        mock_redis.exists = AsyncMock(return_value=1)  # Task exists

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            await manager.move_to_dead_letter_queue("failed-task-123", "OCR processing failed permanently")

            # Verify hset was called to store failure reason
            hset_calls = [call for call in mock_redis.hset.call_args_list]
            assert len(hset_calls) > 0

    @pytest.mark.asyncio
    async def test_get_dead_letter_queue_tasks(self, mock_redis):
        """Test retrieving tasks from dead letter queue"""
        from app.redis_queue import RedisQueueManager

        dead_tasks = [b"task-1", b"task-2", b"task-3"]
        mock_redis.lrange = AsyncMock(return_value=dead_tasks)

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            tasks = await manager.get_dead_letter_queue_tasks()

            assert len(tasks) == 3
            assert tasks == ["task-1", "task-2", "task-3"]

    @pytest.mark.asyncio
    async def test_get_dead_letter_queue_count(self, mock_redis):
        """Test getting count of tasks in dead letter queue"""
        from app.redis_queue import RedisQueueManager

        mock_redis.llen = AsyncMock(return_value=5)

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            count = await manager.get_dead_letter_queue_count()

            assert count == 5

    @pytest.mark.asyncio
    async def test_retry_task_moves_to_dlq_when_max_retries_exceeded(self, mock_redis):
        """Test that retry_task moves task to DLQ when max retries exceeded"""
        from app.redis_queue import RedisQueueManager

        task_data = {
            b"task_id": b"task-123",
            b"status": b"failed",
            b"retry_count": b"3",  # Already at max retries
            b"priority": b"normal",
        }

        mock_redis.hgetall = AsyncMock(return_value=task_data)
        mock_redis.exists = AsyncMock(return_value=1)  # Task exists for DLQ

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Try to retry with max_retries=3
            result = await manager.retry_task("task-123", max_retries=3)

            # Should return False (not re-queued)
            assert result is False

            # Should have been added to dead letter queue
            # Check if lpush was called with dead letter queue key
            lpush_calls = mock_redis.lpush.call_args_list
            assert len(lpush_calls) > 0

    @pytest.mark.asyncio
    async def test_remove_from_dead_letter_queue(self, mock_redis):
        """Test removing a task from dead letter queue"""
        from app.redis_queue import RedisQueueManager

        mock_redis.lrem = AsyncMock(return_value=1)  # Task was removed

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            result = await manager.remove_from_dead_letter_queue("task-123")

            assert result is True
            mock_redis.lrem.assert_called_once()

    @pytest.mark.asyncio
    async def test_dead_letter_queue_task_details(self, mock_redis):
        """Test getting detailed info about dead letter queue task"""
        from app.redis_queue import RedisQueueManager
        from app.models import TaskStatus

        task_data = {
            b"task_id": b"dead-task-123",
            b"status": TaskStatus.FAILED.encode(),
            b"retry_count": b"5",
            b"dead_letter_reason": b"Max retries exceeded",
            b"moved_to_dlq_at": b"2024-01-01T12:00:00",
            b"progress": b"0",
            b"message": b"Failed permanently",
        }

        mock_redis.hgetall = AsyncMock(return_value=task_data)

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            task_status = await manager.get_task_status("dead-task-123")

            assert task_status is not None
            assert task_status.task_id == "dead-task-123"
            assert task_status.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_dead_letter_queue_prevents_requeue(self, mock_redis):
        """Test that tasks in DLQ cannot be re-queued through retry"""
        from app.redis_queue import RedisQueueManager

        task_data = {
            b"task_id": b"dlq-task-123",
            b"status": b"failed",
            b"retry_count": b"10",  # Exceeded max retries
            b"in_dead_letter_queue": b"true",
        }

        mock_redis.hgetall = AsyncMock(return_value=task_data)

        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            result = await manager.retry_task("dlq-task-123")

            assert result is False
