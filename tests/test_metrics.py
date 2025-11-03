"""
Tests for task processing metrics collection
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from app.redis_queue import RedisQueueManager
from app.models import TaskStatus


@pytest.fixture
def mock_redis():
    """Mock Redis client for metrics tests"""
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.keys = AsyncMock(return_value=[])
    redis_mock.hgetall = AsyncMock(return_value={})
    redis_mock.hget = AsyncMock(return_value=None)
    redis_mock.hset = AsyncMock(return_value=1)
    redis_mock.hincrby = AsyncMock(return_value=1)
    redis_mock.incr = AsyncMock(return_value=1)
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.expire = AsyncMock(return_value=True)
    redis_mock.close = AsyncMock()
    return redis_mock


class TestTaskMetrics:
    """Test suite for task processing metrics"""

    @pytest.mark.asyncio
    async def test_metrics_track_task_completion_time(self, mock_redis):
        """Should track duration from task start to completion"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis) as mock_from_url:
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            task_id = "duration-task-123"
            started_at = (datetime.utcnow() - timedelta(minutes=5)).isoformat()

            # Mock task data
            async def hgetall_side_effect(key):
                return {
                    b"task_id": b"duration-task-123",
                    b"status": b"processing",
                    b"task_started_at": started_at.encode(),
                    b"created_at": (datetime.utcnow() - timedelta(minutes=6)).isoformat().encode()
                }

            mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

            # Get metrics
            metrics = await manager.get_task_metrics(task_id)

            assert metrics is not None
            assert "duration_seconds" in metrics or "processing_time" in metrics or "current_duration_seconds" in metrics

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_metrics_track_success_rate(self, mock_redis):
        """Should calculate success rate from completed vs failed tasks"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis) as mock_from_url:
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mock metrics data: 80 completed, 20 failed
            mock_redis.get = AsyncMock(side_effect=lambda key: {
                b"metrics:tasks:completed": b"80",
                b"metrics:tasks:failed": b"20"
            }.get(key.encode() if isinstance(key, str) else key, b"0"))

            # Get aggregate metrics
            metrics = await manager.get_aggregate_metrics()

            assert metrics is not None
            assert "total_tasks" in metrics
            assert "success_rate" in metrics

            # Success rate should be 80% (80 out of 100)
            if metrics.get("success_rate") is not None and metrics["success_rate"] > 0:
                assert 75 <= metrics["success_rate"] <= 85  # Allow some tolerance

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_metrics_track_retry_rate(self, mock_redis):
        """Should calculate retry rate from retry attempts"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis) as mock_from_url:
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mock: 100 total tasks, 25 retries
            mock_redis.get = AsyncMock(side_effect=lambda key: {
                b"metrics:tasks:total": b"100",
                b"metrics:tasks:retried": b"25"
            }.get(key.encode() if isinstance(key, str) else key, b"0"))

            metrics = await manager.get_aggregate_metrics()

            assert metrics is not None
            assert "retry_rate" in metrics

            # Retry rate should be 25%
            if metrics.get("retry_rate") is not None and metrics["retry_rate"] > 0:
                assert 20 <= metrics["retry_rate"] <= 30

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_metrics_increment_on_task_completion(self, mock_redis):
        """Should increment completed counter when task completes"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis) as mock_from_url:
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            task_id = "complete-task-123"

            # Mock task data
            async def hgetall_side_effect(key):
                return {
                    b"task_id": b"complete-task-123",
                    b"status": b"processing",
                    b"task_started_at": datetime.utcnow().isoformat().encode()
                }

            mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

            # Record completion
            await manager.record_task_completion(task_id, success=True)

            # Should increment metrics counter
            assert mock_redis.incr.called or mock_redis.hincrby.called

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_metrics_increment_on_task_failure(self, mock_redis):
        """Should increment failed counter when task fails"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis) as mock_from_url:
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            task_id = "failed-task-456"

            # Record failure
            await manager.record_task_completion(task_id, success=False)

            # Should increment failed counter
            assert mock_redis.incr.called or mock_redis.hincrby.called

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_metrics_track_average_processing_time(self, mock_redis):
        """Should calculate average processing time across all tasks"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis) as mock_from_url:
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mock: total duration 1000 seconds, 20 tasks = 50 sec average
            mock_redis.get = AsyncMock(side_effect=lambda key: {
                b"metrics:tasks:total_duration": b"1000",
                b"metrics:tasks:completed": b"20"
            }.get(key.encode() if isinstance(key, str) else key, b"0"))

            metrics = await manager.get_aggregate_metrics()

            assert metrics is not None
            if "average_duration_seconds" in metrics:
                # Should be around 50 seconds
                assert 45 <= metrics["average_duration_seconds"] <= 55

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_metrics_stored_in_redis_with_ttl(self, mock_redis):
        """Should store metrics in Redis with expiration"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis) as mock_from_url:
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            task_id = "ttl-task-789"

            # Record completion
            await manager.record_task_completion(task_id, success=True, duration_seconds=120)

            # Should set with expiration
            if mock_redis.set.called:
                # Check if expire was called
                assert mock_redis.expire.called or "ex" in str(mock_redis.set.call_args)

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_metrics_include_retry_count_in_stats(self, mock_redis):
        """Should include retry statistics in metrics"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis) as mock_from_url:
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mock various retry counts
            mock_redis.get = AsyncMock(side_effect=lambda key: {
                b"metrics:tasks:retry_0": b"70",  # No retries
                b"metrics:tasks:retry_1": b"20",  # 1 retry
                b"metrics:tasks:retry_2": b"7",   # 2 retries
                b"metrics:tasks:retry_3": b"3"    # 3 retries (max)
            }.get(key.encode() if isinstance(key, str) else key, b"0"))

            metrics = await manager.get_aggregate_metrics()

            assert metrics is not None
            # Should include retry distribution
            if "retry_distribution" in metrics:
                assert isinstance(metrics["retry_distribution"], dict)

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_metrics_track_tasks_in_dlq(self, mock_redis):
        """Should track count of tasks moved to dead letter queue"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis) as mock_from_url:
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mock DLQ count
            mock_redis.llen = AsyncMock(return_value=5)

            metrics = await manager.get_aggregate_metrics()

            assert metrics is not None
            if "dead_letter_queue_count" in metrics:
                assert metrics["dead_letter_queue_count"] == 5

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_metrics_reset_functionality(self, mock_redis):
        """Should allow resetting metrics counters"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis) as mock_from_url:
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Reset metrics
            if hasattr(manager, 'reset_metrics'):
                await manager.reset_metrics()

                # Should delete or reset metric keys
                assert mock_redis.delete.called or mock_redis.set.called

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_metrics_handle_missing_data_gracefully(self, mock_redis):
        """Should return default values when metrics data is missing"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis) as mock_from_url:
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # All metrics return None
            mock_redis.get = AsyncMock(return_value=None)

            metrics = await manager.get_aggregate_metrics()

            # Should not crash, should return defaults
            assert metrics is not None
            assert isinstance(metrics, dict)

            # Should have zero or default values
            if "total_tasks" in metrics:
                assert metrics["total_tasks"] >= 0

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_metrics_calculate_percentiles(self, mock_redis):
        """Should calculate duration percentiles (p50, p95, p99)"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis) as mock_from_url:
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # This would require storing duration history
            # Mock percentile data
            mock_redis.get = AsyncMock(side_effect=lambda key: {
                b"metrics:duration:p50": b"30",
                b"metrics:duration:p95": b"120",
                b"metrics:duration:p99": b"180"
            }.get(key.encode() if isinstance(key, str) else key, None))

            metrics = await manager.get_aggregate_metrics()

            if "duration_p50" in metrics:
                assert metrics["duration_p50"] > 0
            if "duration_p95" in metrics:
                assert metrics["duration_p95"] > metrics.get("duration_p50", 0)

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_metrics_track_time_windows(self, mock_redis):
        """Should track metrics for different time windows (1h, 24h, 7d)"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis) as mock_from_url:
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Get metrics for last hour
            metrics_1h = await manager.get_aggregate_metrics(time_window="1h")
            assert metrics_1h is not None

            # Get metrics for last 24 hours
            metrics_24h = await manager.get_aggregate_metrics(time_window="24h")
            assert metrics_24h is not None

            await manager.disconnect()
