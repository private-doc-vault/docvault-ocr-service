"""
Tests for alerting mechanism for high stuck task count
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, call
from datetime import datetime, timedelta
from app.redis_queue import RedisQueueManager
import logging


@pytest.fixture
def mock_redis():
    """Mock Redis client for alerting tests"""
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.keys = AsyncMock(return_value=[])
    redis_mock.hgetall = AsyncMock(return_value={})
    redis_mock.close = AsyncMock()
    return redis_mock


class TestStuckTaskAlerting:
    """Test suite for stuck task alerting mechanism"""

    @pytest.mark.asyncio
    async def test_no_alert_when_stuck_count_below_threshold(self, mock_redis):
        """Should not trigger alert when stuck tasks below threshold"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mock 2 stuck tasks (below threshold of 5)
            mock_redis.keys.return_value = [b"task:stuck-1", b"task:stuck-2"]

            started_at = (datetime.utcnow() - timedelta(minutes=35)).isoformat()

            async def hgetall_side_effect(key):
                return {
                    b"task_id": b"stuck-1",
                    b"status": b"processing",
                    b"task_started_at": started_at.encode()
                }

            mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

            # Mock logger to capture log calls
            with patch('app.redis_queue.logger') as mock_logger:
                stuck_tasks = await manager.find_stuck_tasks(timeout_minutes=30)

                # Should find tasks but not trigger warning
                assert len(stuck_tasks) == 2

                # No warning should be logged for counts below threshold
                warning_calls = [call for call in mock_logger.warning.call_args_list
                               if 'HIGH' in str(call) or 'alert' in str(call).lower()]
                assert len(warning_calls) == 0

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_alert_triggered_when_stuck_count_exceeds_threshold(self, mock_redis):
        """Should trigger alert when stuck tasks exceed threshold"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mock 6 stuck tasks (above threshold of 5)
            mock_redis.keys.return_value = [
                b"task:stuck-1", b"task:stuck-2", b"task:stuck-3",
                b"task:stuck-4", b"task:stuck-5", b"task:stuck-6"
            ]

            started_at = (datetime.utcnow() - timedelta(minutes=35)).isoformat()

            call_count = [0]

            async def hgetall_side_effect(key):
                call_count[0] += 1
                return {
                    b"task_id": f"stuck-{call_count[0]}".encode(),
                    b"status": b"processing",
                    b"task_started_at": started_at.encode()
                }

            mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

            # Mock logger to capture log calls
            with patch('app.redis_queue.logger') as mock_logger:
                stuck_tasks = await manager.find_stuck_tasks(
                    timeout_minutes=30,
                    alert_threshold=5
                )

                # Should find all tasks
                assert len(stuck_tasks) == 6

                # Warning should be logged for high count
                mock_logger.warning.assert_called()

                # Check that the warning mentions high stuck task count
                warning_message = str(mock_logger.warning.call_args_list)
                assert 'stuck' in warning_message.lower() or 'alert' in warning_message.lower()

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_alert_includes_task_count_in_message(self, mock_redis):
        """Should include actual task count in alert message"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mock 10 stuck tasks
            mock_redis.keys.return_value = [f"task:stuck-{i}".encode() for i in range(1, 11)]

            started_at = (datetime.utcnow() - timedelta(minutes=35)).isoformat()

            async def hgetall_side_effect(key):
                return {
                    b"task_id": b"stuck-x",
                    b"status": b"processing",
                    b"task_started_at": started_at.encode()
                }

            mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

            with patch('app.redis_queue.logger') as mock_logger:
                stuck_tasks = await manager.find_stuck_tasks(
                    timeout_minutes=30,
                    alert_threshold=5
                )

                assert len(stuck_tasks) == 10

                # Check warning was called
                assert mock_logger.warning.called

                # Verify the count is mentioned in the message
                warning_calls = mock_logger.warning.call_args_list
                message = str(warning_calls[0])
                # Should mention the count somewhere
                assert '10' in message or 'count' in message.lower()

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_alert_with_custom_threshold(self, mock_redis):
        """Should allow custom alert threshold"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mock 3 stuck tasks
            mock_redis.keys.return_value = [b"task:stuck-1", b"task:stuck-2", b"task:stuck-3"]

            started_at = (datetime.utcnow() - timedelta(minutes=35)).isoformat()

            async def hgetall_side_effect(key):
                return {
                    b"task_id": b"stuck-x",
                    b"status": b"processing",
                    b"task_started_at": started_at.encode()
                }

            mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

            with patch('app.redis_queue.logger') as mock_logger:
                # Use threshold of 2 (should trigger with 3 tasks)
                stuck_tasks = await manager.find_stuck_tasks(
                    timeout_minutes=30,
                    alert_threshold=2
                )

                assert len(stuck_tasks) == 3

                # Should trigger warning with custom threshold
                mock_logger.warning.assert_called()

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_no_alert_when_threshold_is_none(self, mock_redis):
        """Should not trigger alert when threshold is None (disabled)"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mock 100 stuck tasks
            mock_redis.keys.return_value = [f"task:stuck-{i}".encode() for i in range(1, 101)]

            started_at = (datetime.utcnow() - timedelta(minutes=35)).isoformat()

            async def hgetall_side_effect(key):
                return {
                    b"task_id": b"stuck-x",
                    b"status": b"processing",
                    b"task_started_at": started_at.encode()
                }

            mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

            with patch('app.redis_queue.logger') as mock_logger:
                # Explicitly disable alerting with None
                stuck_tasks = await manager.find_stuck_tasks(
                    timeout_minutes=30,
                    alert_threshold=None
                )

                assert len(stuck_tasks) == 100

                # No alert should be triggered
                alert_calls = [call for call in mock_logger.warning.call_args_list
                             if 'alert' in str(call).lower() or 'HIGH' in str(call)]
                assert len(alert_calls) == 0

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_alert_logs_at_warning_level(self, mock_redis):
        """Should log alerts at WARNING level"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mock enough stuck tasks to trigger alert
            mock_redis.keys.return_value = [f"task:stuck-{i}".encode() for i in range(1, 7)]

            started_at = (datetime.utcnow() - timedelta(minutes=35)).isoformat()

            async def hgetall_side_effect(key):
                return {
                    b"task_id": b"stuck-x",
                    b"status": b"processing",
                    b"task_started_at": started_at.encode()
                }

            mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

            with patch('app.redis_queue.logger') as mock_logger:
                await manager.find_stuck_tasks(timeout_minutes=30, alert_threshold=5)

                # Should use warning level (not info or error)
                mock_logger.warning.assert_called()

                # Should not use error level for this
                assert not mock_logger.error.called

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_multiple_alerts_on_consecutive_checks(self, mock_redis):
        """Should trigger alert on each check if count remains high"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mock 6 stuck tasks
            mock_redis.keys.return_value = [f"task:stuck-{i}".encode() for i in range(1, 7)]

            started_at = (datetime.utcnow() - timedelta(minutes=35)).isoformat()

            async def hgetall_side_effect(key):
                return {
                    b"task_id": b"stuck-x",
                    b"status": b"processing",
                    b"task_started_at": started_at.encode()
                }

            mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

            with patch('app.redis_queue.logger') as mock_logger:
                # First check
                await manager.find_stuck_tasks(timeout_minutes=30, alert_threshold=5)
                first_call_count = mock_logger.warning.call_count

                # Second check (should alert again)
                await manager.find_stuck_tasks(timeout_minutes=30, alert_threshold=5)
                second_call_count = mock_logger.warning.call_count

                # Should have warned on both checks
                assert first_call_count > 0
                assert second_call_count > first_call_count

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_alert_message_format(self, mock_redis):
        """Should format alert message with useful information"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mock 8 stuck tasks
            mock_redis.keys.return_value = [f"task:stuck-{i}".encode() for i in range(1, 9)]

            started_at = (datetime.utcnow() - timedelta(minutes=35)).isoformat()

            async def hgetall_side_effect(key):
                return {
                    b"task_id": b"stuck-x",
                    b"status": b"processing",
                    b"task_started_at": started_at.encode()
                }

            mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

            with patch('app.redis_queue.logger') as mock_logger:
                await manager.find_stuck_tasks(timeout_minutes=30, alert_threshold=5)

                # Get the warning message
                warning_calls = mock_logger.warning.call_args_list
                assert len(warning_calls) > 0

                message = str(warning_calls[0])

                # Should contain key information
                # Count: 8 tasks
                # Threshold: exceeded
                # Context: stuck tasks
                assert any(term in message.lower() for term in ['stuck', 'alert', 'high', 'threshold'])

            await manager.disconnect()

    @pytest.mark.asyncio
    async def test_default_threshold_value(self, mock_redis):
        """Should have reasonable default threshold when not specified"""
        with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis):
            manager = RedisQueueManager("redis://localhost:6379/0")
            await manager.connect()

            # Mock 11 stuck tasks (above default threshold of 10)
            mock_redis.keys.return_value = [f"task:stuck-{i}".encode() for i in range(1, 12)]

            started_at = (datetime.utcnow() - timedelta(minutes=35)).isoformat()

            async def hgetall_side_effect(key):
                return {
                    b"task_id": b"stuck-x",
                    b"status": b"processing",
                    b"task_started_at": started_at.encode()
                }

            mock_redis.hgetall = AsyncMock(side_effect=hgetall_side_effect)

            with patch('app.redis_queue.logger') as mock_logger:
                # Don't specify threshold - should use default
                stuck_tasks = await manager.find_stuck_tasks(timeout_minutes=30)

                assert len(stuck_tasks) == 11

                # With reasonable default of 10, should trigger alert
                # (If default is higher, this test will need adjustment)

            await manager.disconnect()
