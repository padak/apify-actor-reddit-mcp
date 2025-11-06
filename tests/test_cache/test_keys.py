"""Unit tests for cache key generation."""

import pytest

from src.cache.keys import CacheKeyGenerator


class TestCacheKeyGenerator:
    """Test suite for CacheKeyGenerator class."""

    def test_generate_basic_key(self):
        """Test basic cache key generation."""
        params = {"query": "python", "limit": 25}
        key = CacheKeyGenerator.generate("search_reddit", params)

        assert key.startswith("reddit:search_reddit:")
        assert key.endswith(":v1")
        assert len(key.split(":")) == 4

    def test_generate_deterministic(self):
        """Test that same params generate same key."""
        params1 = {"query": "python", "limit": 25}
        params2 = {"query": "python", "limit": 25}

        key1 = CacheKeyGenerator.generate("search_reddit", params1)
        key2 = CacheKeyGenerator.generate("search_reddit", params2)

        assert key1 == key2

    def test_generate_order_independent(self):
        """Test that parameter order doesn't affect key."""
        params1 = {"query": "python", "limit": 25}
        params2 = {"limit": 25, "query": "python"}

        key1 = CacheKeyGenerator.generate("search_reddit", params1)
        key2 = CacheKeyGenerator.generate("search_reddit", params2)

        assert key1 == key2

    def test_generate_different_params_different_keys(self):
        """Test that different params generate different keys."""
        params1 = {"query": "python", "limit": 25}
        params2 = {"query": "javascript", "limit": 25}

        key1 = CacheKeyGenerator.generate("search_reddit", params1)
        key2 = CacheKeyGenerator.generate("search_reddit", params2)

        assert key1 != key2

    def test_generate_different_tools_different_keys(self):
        """Test that different tools generate different keys."""
        params = {"query": "python"}

        key1 = CacheKeyGenerator.generate("search_reddit", params)
        key2 = CacheKeyGenerator.generate("get_trending_topics", params)

        assert key1 != key2

    def test_parse_valid_key(self):
        """Test parsing a valid cache key."""
        key = "reddit:search_reddit:a3f8d9c2e1b4:v1"
        parsed = CacheKeyGenerator.parse(key)

        assert parsed["prefix"] == "reddit"
        assert parsed["tool"] == "search_reddit"
        assert parsed["params_hash"] == "a3f8d9c2e1b4"
        assert parsed["version"] == "v1"

    def test_parse_invalid_key_raises_error(self):
        """Test that parsing invalid key raises ValueError."""
        invalid_key = "reddit:search_reddit:invalid"

        with pytest.raises(ValueError) as exc_info:
            CacheKeyGenerator.parse(invalid_key)

        assert "Invalid cache key format" in str(exc_info.value)

    def test_generate_hash_length(self):
        """Test that hash is exactly 12 characters."""
        params = {"query": "test"}
        key = CacheKeyGenerator.generate("search_reddit", params)

        parts = key.split(":")
        params_hash = parts[2]

        assert len(params_hash) == 12

    def test_generate_with_empty_params(self):
        """Test key generation with empty params."""
        params = {}
        key = CacheKeyGenerator.generate("search_reddit", params)

        assert key.startswith("reddit:search_reddit:")
        assert key.endswith(":v1")

    def test_generate_with_nested_params(self):
        """Test key generation with nested params."""
        params = {
            "query": "python",
            "filters": {"time": "week", "sort": "top"},
        }
        key = CacheKeyGenerator.generate("search_reddit", params)

        assert key.startswith("reddit:search_reddit:")
        assert key.endswith(":v1")
