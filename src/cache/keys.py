"""Cache key generation for consistent, deterministic cache keys.

This module provides the CacheKeyGenerator class for generating
hashed cache keys from tool names and parameters.
"""

import hashlib
import json
from typing import Any, Dict

import structlog

logger = structlog.get_logger(__name__)


class CacheKeyGenerator:
    """
    Generate consistent cache keys for Reddit MCP tools.

    Cache keys follow the pattern: reddit:{tool}:{params_hash}:{version}

    The params_hash is generated using MD5 hashing of sorted parameters
    to ensure deterministic key generation (same params = same key).

    Attributes:
        VERSION: Cache schema version (increment when response format changes)
    """

    VERSION = "v1"

    @staticmethod
    def generate(tool_name: str, params: Dict[str, Any]) -> str:
        """
        Generate cache key for Reddit tool request.

        Args:
            tool_name: Name of the MCP tool (e.g., "search_reddit")
            params: Tool parameters as dictionary

        Returns:
            Cache key string in format: reddit:{tool}:{hash}:{version}

        Example:
            >>> params = {"query": "python", "limit": 25}
            >>> key = CacheKeyGenerator.generate("search_reddit", params)
            >>> print(key)
            reddit:search_reddit:a3f8d9c2e1b4:v1
        """
        # Sort params for consistent hashing
        params_str = json.dumps(params, sort_keys=True)

        # Generate MD5 hash (first 12 chars for brevity)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:12]

        # Build cache key
        cache_key = f"reddit:{tool_name}:{params_hash}:{CacheKeyGenerator.VERSION}"

        logger.debug(
            "cache_key_generated",
            tool=tool_name,
            params_hash=params_hash,
            cache_key=cache_key,
        )

        return cache_key

    @staticmethod
    def parse(cache_key: str) -> Dict[str, str]:
        """
        Parse cache key back to components.

        Args:
            cache_key: Cache key string to parse

        Returns:
            Dictionary with parsed components:
                - prefix: "reddit"
                - tool: Tool name
                - params_hash: Parameter hash
                - version: Cache version

        Raises:
            ValueError: If cache key format is invalid

        Example:
            >>> key = "reddit:search_reddit:a3f8d9c2e1b4:v1"
            >>> parsed = CacheKeyGenerator.parse(key)
            >>> print(parsed['tool'])
            search_reddit
        """
        parts = cache_key.split(":")

        if len(parts) != 4:
            raise ValueError(
                f"Invalid cache key format: {cache_key}. "
                f"Expected 4 parts separated by ':', got {len(parts)}"
            )

        return {
            "prefix": parts[0],
            "tool": parts[1],
            "params_hash": parts[2],
            "version": parts[3],
        }


# Convenience singleton instance
key_generator = CacheKeyGenerator()
