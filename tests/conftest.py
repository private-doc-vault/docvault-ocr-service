"""
Test configuration and fixtures
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def mock_redis_client():
    """Mock Redis client for tests"""
    from datetime import datetime

    # Storage for created tasks during tests
    test_tasks = {}

    async def mock_hset(key, *args, mapping=None, **kwargs):
        """Mock hset that stores task data"""
        if key.startswith('task:') or key.startswith('batch:'):
            if key not in test_tasks:
                test_tasks[key] = {}

            # Handle mapping parameter (hset with dict)
            if mapping:
                for field, value in mapping.items():
                    test_tasks[key][field] = value
            elif len(args) == 2:
                # Single key-value pair: hset(key, field, value)
                test_tasks[key][args[0]] = args[1]
            elif len(args) > 2:
                # Multiple key-value pairs: hset(key, f1, v1, f2, v2, ...)
                for i in range(0, len(args), 2):
                    test_tasks[key][args[i]] = args[i+1]
        return True

    async def mock_hgetall(key):
        """Mock hgetall that retrieves stored task data"""
        if key in test_tasks:
            # Convert to bytes like real Redis
            result = {}
            for k, v in test_tasks[key].items():
                key_bytes = k.encode() if isinstance(k, str) else k
                value_bytes = v.encode() if isinstance(v, str) else v
                result[key_bytes] = value_bytes
            return result
        return {}

    async def mock_exists(key):
        """Mock exists check"""
        return 1 if key in test_tasks else 0

    async def mock_get(key):
        """Mock get for string values (like JSON results)"""
        # For now, return None (no results stored yet)
        return None

    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.keys = AsyncMock(return_value=[])
    redis_mock.hgetall = AsyncMock(side_effect=mock_hgetall)
    redis_mock.hset = AsyncMock(side_effect=mock_hset)
    redis_mock.hget = AsyncMock(return_value=None)
    redis_mock.get = AsyncMock(side_effect=mock_get)
    redis_mock.exists = AsyncMock(side_effect=mock_exists)
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.lpush = AsyncMock(return_value=1)
    redis_mock.rpop = AsyncMock(return_value=None)
    redis_mock.llen = AsyncMock(return_value=0)
    redis_mock.close = AsyncMock()
    redis_mock.wait_closed = AsyncMock()

    # Store reference for tests
    redis_mock._test_tasks = test_tasks

    return redis_mock


@pytest.fixture(scope="function")
def initialize_test_app(mock_redis_client):
    """Initialize the FastAPI app with mocked Redis for API tests"""
    import asyncio

    # Get or create event loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Start patching
    patcher = patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis_client)
    patcher.start()

    # Import app after patching to ensure the patch is applied
    from app.main import app
    from app.redis_queue import init_redis_queue_manager, redis_queue_manager

    # Manually trigger the startup event
    async def setup():
        await init_redis_queue_manager("redis://localhost:6379/0")

    loop.run_until_complete(setup())

    yield app

    # Cleanup
    if redis_queue_manager:
        loop.run_until_complete(redis_queue_manager.disconnect())

    # Stop patching
    patcher.stop()


@pytest.fixture(scope="function")
def client(initialize_test_app):
    """Test client with initialized app"""
    from app.main import app
    return TestClient(app)
