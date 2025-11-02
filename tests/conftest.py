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
    redis_mock = AsyncMock()
    redis_mock.ping = AsyncMock(return_value=True)
    redis_mock.keys = AsyncMock(return_value=[])
    redis_mock.hgetall = AsyncMock(return_value={})
    redis_mock.hset = AsyncMock(return_value=True)
    redis_mock.hget = AsyncMock(return_value=None)
    redis_mock.exists = AsyncMock(return_value=0)
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.lpush = AsyncMock(return_value=1)
    redis_mock.rpop = AsyncMock(return_value=None)
    redis_mock.llen = AsyncMock(return_value=0)
    redis_mock.close = AsyncMock()
    redis_mock.wait_closed = AsyncMock()
    return redis_mock


@pytest.fixture(scope="function")
def initialize_test_app(mock_redis_client):
    """Initialize the FastAPI app with mocked Redis for API tests"""
    with patch('app.redis_queue.aioredis.from_url', new_callable=AsyncMock, return_value=mock_redis_client):
        # Import app after patching to ensure the patch is applied
        from app.main import app
        from app.redis_queue import init_redis_queue_manager

        # Manually trigger the startup event
        import asyncio

        async def setup():
            await init_redis_queue_manager("redis://localhost:6379/0")

        # Run the startup in an event loop
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(setup())

        yield app

        # Cleanup
        from app.redis_queue import redis_queue_manager
        if redis_queue_manager:
            loop.run_until_complete(redis_queue_manager.disconnect())


@pytest.fixture(scope="function")
def client(initialize_test_app):
    """Test client with initialized app"""
    from app.main import app
    return TestClient(app)
