"""Cache manager for Redis operations with fail-open error handling.

This module provides the CacheManager class which implements the cache-aside
pattern with graceful degradation when Redis is unavailable.
"""

import json
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import structlog

from src.cache.connection import cache

logger = structlog.get_logger(__name__)


class CacheManager:
    """
    Main cache operations manager with fail-open behavior.

    Implements cache-aside pattern with methods for get, set, delete,
    and get_or_fetch. All operations fail gracefully if Redis is unavailable.

    Attributes:
        redis: Redis client instance from connection module
    """

    def __init__(self) -> None:
        """Initialize cache manager with Redis client."""
        self.redis = cache.client

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached value by key.

        Args:
            key: Cache key to retrieve

        Returns:
            Cached data dictionary with metadata, or None if not found

        Example:
            >>> manager = CacheManager()
            >>> cached = await manager.get("reddit:search:abc123:v1")
            >>> if cached:
            ...     print(f"Cache age: {cached['age_seconds']}s")
        """
        if not self.redis:
            logger.debug("cache_get_skipped", reason="redis_not_available", key=key)
            return None

        try:
            value = await self.redis.get(key)

            if value:
                # Parse stored JSON data
                cached_data = json.loads(value)

                # Calculate cache age
                cached_at = datetime.fromisoformat(cached_data["cached_at"])
                age_seconds = int((datetime.utcnow() - cached_at).total_seconds())

                logger.debug(
                    "cache_hit",
                    key=key,
                    age_seconds=age_seconds,
                    ttl=cached_data.get("ttl"),
                )

                # Add age to metadata
                cached_data["age_seconds"] = age_seconds

                return cached_data

            logger.debug("cache_miss", key=key)
            return None

        except json.JSONDecodeError as e:
            logger.error(
                "cache_get_json_decode_error",
                key=key,
                error=str(e),
            )
            # Invalid cached data - delete it
            await self.delete(key)
            return None

        except Exception as e:
            logger.error(
                "cache_get_error",
                key=key,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Fail open - return None (cache miss)
            return None

    async def set(self, key: str, value: Any, ttl: int) -> bool:
        """
        Store value in cache with TTL.

        Args:
            key: Cache key
            value: Data to cache (must be JSON-serializable)
            ttl: Time to live in seconds

        Returns:
            True if cached successfully, False otherwise

        Example:
            >>> manager = CacheManager()
            >>> data = {"results": [{"id": "123"}]}
            >>> success = await manager.set("cache_key", data, ttl=300)
        """
        if not self.redis:
            logger.debug("cache_set_skipped", reason="redis_not_available", key=key)
            return False

        try:
            # Add metadata to cached value
            cached_data = {
                "data": value,
                "cached_at": datetime.utcnow().isoformat(),
                "ttl": ttl,
            }

            # Store with expiration
            await self.redis.setex(key, ttl, json.dumps(cached_data))

            logger.debug(
                "cache_set",
                key=key,
                ttl=ttl,
                data_size=len(json.dumps(value)),
            )

            return True

        except (TypeError, ValueError) as e:
            logger.error(
                "cache_set_serialization_error",
                key=key,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

        except Exception as e:
            logger.error(
                "cache_set_error",
                key=key,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Fail silently (cache write failures shouldn't break requests)
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete cached value by key.

        Args:
            key: Cache key to delete

        Returns:
            True if deleted, False otherwise

        Example:
            >>> manager = CacheManager()
            >>> deleted = await manager.delete("stale_cache_key")
        """
        if not self.redis:
            logger.debug("cache_delete_skipped", reason="redis_not_available", key=key)
            return False

        try:
            result = await self.redis.delete(key)
            logger.debug("cache_delete", key=key, deleted=bool(result))
            return bool(result)

        except Exception as e:
            logger.error(
                "cache_delete_error",
                key=key,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    async def get_or_fetch(
        self, key: str, fetch_func: Callable, ttl: int
    ) -> Dict[str, Any]:
        """
        Get from cache or fetch and cache (cache-aside pattern).

        This is the primary method for implementing cache-aside pattern.
        It first checks the cache, and if not found, executes the fetch
        function and caches the result.

        Args:
            key: Cache key
            fetch_func: Async function to fetch data if cache miss
            ttl: Time to live in seconds

        Returns:
            Dictionary with structure:
                {
                    "data": <actual data>,
                    "metadata": {
                        "cached": bool,
                        "cache_age_seconds": int,
                        "ttl": int
                    }
                }

        Example:
            >>> async def fetch_posts():
            ...     return await reddit.get_posts()
            >>>
            >>> manager = CacheManager()
            >>> result = await manager.get_or_fetch(
            ...     "cache_key",
            ...     fetch_posts,
            ...     ttl=300
            ... )
            >>> print(f"Cached: {result['metadata']['cached']}")
        """
        # Try cache first
        cached = await self.get(key)

        if cached:
            # Cache hit - return with metadata
            cache_age = cached.get("age_seconds", 0)

            logger.info(
                "cache_hit_get_or_fetch",
                key=key,
                cache_age_seconds=cache_age,
            )

            return {
                "data": cached["data"],
                "metadata": {
                    "cached": True,
                    "cache_age_seconds": cache_age,
                    "ttl": cached["ttl"],
                },
            }

        # Cache miss - fetch data
        logger.info("cache_miss_fetching", key=key)

        try:
            data = await fetch_func()

            # Store in cache
            await self.set(key, data, ttl)

            return {
                "data": data,
                "metadata": {
                    "cached": False,
                    "cache_age_seconds": 0,
                    "ttl": ttl,
                },
            }

        except Exception as e:
            logger.error(
                "fetch_function_error",
                key=key,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Re-raise the fetch error (don't swallow it)
            raise


# Global cache manager instance (singleton pattern)
cache_manager = CacheManager()
