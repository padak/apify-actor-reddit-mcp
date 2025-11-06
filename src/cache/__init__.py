"""Redis caching layer for API response caching.

This package provides Redis-based caching with:
- Connection pooling (RedisCache)
- Cache key generation (CacheKeyGenerator)
- TTL policies (CacheTTL)
- Cache operations (CacheManager)
- Graceful fail-open behavior
"""

from src.cache.connection import RedisCache, cache
from src.cache.keys import CacheKeyGenerator, key_generator
from src.cache.manager import CacheManager, cache_manager
from src.cache.ttl import CacheTTL

__all__ = [
    # Connection
    "RedisCache",
    "cache",
    # Key generation
    "CacheKeyGenerator",
    "key_generator",
    # Cache manager
    "CacheManager",
    "cache_manager",
    # TTL policies
    "CacheTTL",
]
