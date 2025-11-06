"""Redis connection and pooling management.

This module provides the RedisCache class for managing Redis connections
with connection pooling and graceful error handling.
"""

import os
from typing import Optional

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

import structlog

logger = structlog.get_logger(__name__)


class RedisCache:
    """
    Redis cache connection manager with connection pooling.

    Provides connection pool management, health checks, and graceful
    error handling for Redis operations.

    Attributes:
        pool: Redis connection pool
        client: Redis client instance
    """

    def __init__(self) -> None:
        """Initialize Redis cache with connection pooling."""
        self.pool: Optional[ConnectionPool] = None
        self.client: Optional[redis.Redis] = None
        self._initialize_pool()

    def _initialize_pool(self) -> None:
        """
        Initialize Redis connection pool.

        Configures connection pool from REDIS_URL environment variable
        with optimal settings for the MCP server.
        """
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        try:
            self.pool = ConnectionPool.from_url(
                redis_url,
                max_connections=20,  # Support high concurrency
                decode_responses=True,  # Auto-decode bytes to str
                socket_timeout=5,  # 5 second socket timeout
                socket_connect_timeout=5,  # 5 second connect timeout
                retry_on_timeout=True,  # Retry on timeout
            )

            self.client = redis.Redis(connection_pool=self.pool)

            logger.info(
                "redis_pool_initialized",
                max_connections=20,
                redis_url=redis_url.split("@")[-1],  # Don't log credentials
            )

        except Exception as e:
            logger.error(
                "redis_pool_initialization_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            # Don't raise - fail open (cache unavailable but server continues)
            self.client = None
            self.pool = None

    async def ping(self) -> bool:
        """
        Check Redis connection health.

        Returns:
            True if Redis is healthy, False otherwise

        Example:
            >>> cache = RedisCache()
            >>> is_healthy = await cache.ping()
            >>> print(f"Redis healthy: {is_healthy}")
        """
        if not self.client:
            logger.warning("redis_ping_failed", reason="client_not_initialized")
            return False

        try:
            result = await self.client.ping()
            logger.debug("redis_ping_success", result=result)
            return result

        except Exception as e:
            logger.error(
                "redis_ping_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            return False

    async def close(self) -> None:
        """
        Close Redis connection pool gracefully.

        Should be called during application shutdown to ensure
        all connections are properly closed.

        Example:
            >>> cache = RedisCache()
            >>> # ... use cache ...
            >>> await cache.close()
        """
        try:
            if self.client:
                await self.client.close()
                logger.info("redis_client_closed")

            if self.pool:
                await self.pool.disconnect()
                logger.info("redis_pool_disconnected")

        except Exception as e:
            logger.error(
                "redis_close_error",
                error=str(e),
                error_type=type(e).__name__,
            )

    def is_available(self) -> bool:
        """
        Check if Redis client is available.

        Returns:
            True if client is initialized, False otherwise

        Note:
            This only checks if the client exists, not if Redis is reachable.
            Use ping() for a real health check.
        """
        return self.client is not None


# Global Redis cache instance (singleton pattern)
cache = RedisCache()
