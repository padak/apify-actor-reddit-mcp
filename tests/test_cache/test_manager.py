"""Unit tests for cache manager."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cache.manager import CacheManager


class TestCacheManager:
    """Test suite for CacheManager class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = AsyncMock()
        mock.get = AsyncMock(return_value=None)
        mock.setex = AsyncMock()
        mock.delete = AsyncMock(return_value=1)
        return mock

    @pytest.fixture
    def cache_manager(self, mock_redis):
        """Create CacheManager with mocked Redis client."""
        manager = CacheManager()
        manager.redis = mock_redis
        return manager

    @pytest.mark.asyncio
    async def test_get_cache_hit(self, cache_manager, mock_redis):
        """Test get() returns cached data on cache hit."""
        cached_data = {
            "data": {"results": [{"id": "123"}]},
            "cached_at": datetime.utcnow().isoformat(),
            "ttl": 300,
        }
        mock_redis.get.return_value = json.dumps(cached_data)

        result = await cache_manager.get("test_key")

        assert result is not None
        assert result["data"] == cached_data["data"]
        assert "age_seconds" in result
        mock_redis.get.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_get_cache_miss(self, cache_manager, mock_redis):
        """Test get() returns None on cache miss."""
        mock_redis.get.return_value = None

        result = await cache_manager.get("test_key")

        assert result is None
        mock_redis.get.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_get_with_no_redis(self):
        """Test get() returns None when Redis is not available."""
        manager = CacheManager()
        manager.redis = None

        result = await manager.get("test_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_invalid_json(self, cache_manager, mock_redis):
        """Test get() handles invalid JSON gracefully."""
        mock_redis.get.return_value = "invalid json {"
        mock_redis.delete = AsyncMock()

        result = await cache_manager.get("test_key")

        assert result is None
        # Should delete invalid cached data
        mock_redis.delete.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_set_success(self, cache_manager, mock_redis):
        """Test set() stores data successfully."""
        data = {"results": [{"id": "123"}]}

        result = await cache_manager.set("test_key", data, ttl=300)

        assert result is True
        mock_redis.setex.assert_called_once()
        args = mock_redis.setex.call_args[0]
        assert args[0] == "test_key"  # key
        assert args[1] == 300  # ttl
        # Verify JSON can be parsed
        cached = json.loads(args[2])
        assert cached["data"] == data

    @pytest.mark.asyncio
    async def test_set_with_no_redis(self):
        """Test set() returns False when Redis is not available."""
        manager = CacheManager()
        manager.redis = None

        result = await manager.set("test_key", {"data": "test"}, ttl=300)

        assert result is False

    @pytest.mark.asyncio
    async def test_set_non_serializable_data(self, cache_manager, mock_redis):
        """Test set() handles non-serializable data gracefully."""
        # Create non-serializable data (function object)
        non_serializable = {"func": lambda x: x}

        result = await cache_manager.set("test_key", non_serializable, ttl=300)

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_success(self, cache_manager, mock_redis):
        """Test delete() removes cached data."""
        mock_redis.delete.return_value = 1

        result = await cache_manager.delete("test_key")

        assert result is True
        mock_redis.delete.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self, cache_manager, mock_redis):
        """Test delete() with nonexistent key."""
        mock_redis.delete.return_value = 0

        result = await cache_manager.delete("test_key")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_with_no_redis(self):
        """Test delete() returns False when Redis is not available."""
        manager = CacheManager()
        manager.redis = None

        result = await manager.delete("test_key")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_or_fetch_cache_hit(self, cache_manager, mock_redis):
        """Test get_or_fetch() returns cached data without calling fetch."""
        cached_data = {
            "data": {"results": [{"id": "123"}]},
            "cached_at": datetime.utcnow().isoformat(),
            "ttl": 300,
        }
        mock_redis.get.return_value = json.dumps(cached_data)

        fetch_func = AsyncMock()

        result = await cache_manager.get_or_fetch("test_key", fetch_func, ttl=300)

        assert result["metadata"]["cached"] is True
        assert result["data"] == cached_data["data"]
        fetch_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_or_fetch_cache_miss(self, cache_manager, mock_redis):
        """Test get_or_fetch() calls fetch function on cache miss."""
        mock_redis.get.return_value = None
        fetched_data = {"results": [{"id": "456"}]}
        fetch_func = AsyncMock(return_value=fetched_data)

        result = await cache_manager.get_or_fetch("test_key", fetch_func, ttl=300)

        assert result["metadata"]["cached"] is False
        assert result["data"] == fetched_data
        fetch_func.assert_called_once()
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_fetch_fetch_error(self, cache_manager, mock_redis):
        """Test get_or_fetch() propagates fetch function errors."""
        mock_redis.get.return_value = None
        fetch_func = AsyncMock(side_effect=Exception("Fetch failed"))

        with pytest.raises(Exception) as exc_info:
            await cache_manager.get_or_fetch("test_key", fetch_func, ttl=300)

        assert "Fetch failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_or_fetch_no_redis_still_fetches(self):
        """Test get_or_fetch() still fetches data when Redis is unavailable."""
        manager = CacheManager()
        manager.redis = None
        fetched_data = {"results": [{"id": "789"}]}
        fetch_func = AsyncMock(return_value=fetched_data)

        result = await manager.get_or_fetch("test_key", fetch_func, ttl=300)

        assert result["metadata"]["cached"] is False
        assert result["data"] == fetched_data
        fetch_func.assert_called_once()
