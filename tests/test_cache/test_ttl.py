"""Unit tests for TTL policies."""

import pytest

from src.cache.ttl import CacheTTL


class TestCacheTTL:
    """Test suite for CacheTTL enum and policies."""

    def test_enum_values_are_integers(self):
        """Test that all TTL values are integers."""
        for ttl in CacheTTL:
            assert isinstance(ttl.value, int)
            assert ttl.value > 0

    def test_new_posts_ttl(self):
        """Test TTL for new posts is 2 minutes."""
        assert CacheTTL.NEW_POSTS.value == 120

    def test_hot_posts_ttl(self):
        """Test TTL for hot posts is 5 minutes."""
        assert CacheTTL.HOT_POSTS.value == 300

    def test_top_posts_ttl(self):
        """Test TTL for top posts is 1 hour."""
        assert CacheTTL.TOP_POSTS.value == 3600

    def test_comments_ttl(self):
        """Test TTL for comments is 15 minutes."""
        assert CacheTTL.COMMENTS.value == 900

    def test_get_ttl_subreddit_posts_new(self):
        """Test TTL for get_subreddit_posts with sort=new."""
        params = {"sort": "new"}
        ttl = CacheTTL.get_ttl("get_subreddit_posts", params)
        assert ttl == 120

    def test_get_ttl_subreddit_posts_hot(self):
        """Test TTL for get_subreddit_posts with sort=hot."""
        params = {"sort": "hot"}
        ttl = CacheTTL.get_ttl("get_subreddit_posts", params)
        assert ttl == 300

    def test_get_ttl_subreddit_posts_top(self):
        """Test TTL for get_subreddit_posts with sort=top."""
        params = {"sort": "top"}
        ttl = CacheTTL.get_ttl("get_subreddit_posts", params)
        assert ttl == 3600

    def test_get_ttl_subreddit_posts_rising(self):
        """Test TTL for get_subreddit_posts with sort=rising."""
        params = {"sort": "rising"}
        ttl = CacheTTL.get_ttl("get_subreddit_posts", params)
        assert ttl == 180

    def test_get_ttl_subreddit_posts_controversial(self):
        """Test TTL for get_subreddit_posts with sort=controversial."""
        params = {"sort": "controversial"}
        ttl = CacheTTL.get_ttl("get_subreddit_posts", params)
        assert ttl == 3600

    def test_get_ttl_search_reddit(self):
        """Test TTL for search_reddit."""
        params = {"query": "python"}
        ttl = CacheTTL.get_ttl("search_reddit", params)
        assert ttl == 300

    def test_get_ttl_get_post_comments(self):
        """Test TTL for get_post_comments."""
        params = {"post_id": "abc123"}
        ttl = CacheTTL.get_ttl("get_post_comments", params)
        assert ttl == 900

    def test_get_ttl_get_trending_topics(self):
        """Test TTL for get_trending_topics."""
        params = {"scope": "all"}
        ttl = CacheTTL.get_ttl("get_trending_topics", params)
        assert ttl == 900

    def test_get_ttl_get_user_info(self):
        """Test TTL for get_user_info."""
        params = {"username": "testuser"}
        ttl = CacheTTL.get_ttl("get_user_info", params)
        assert ttl == 600

    def test_get_ttl_get_subreddit_info(self):
        """Test TTL for get_subreddit_info."""
        params = {"subreddit": "python"}
        ttl = CacheTTL.get_ttl("get_subreddit_info", params)
        assert ttl == 3600

    def test_get_ttl_analyze_sentiment(self):
        """Test TTL for analyze_sentiment."""
        params = {"content_id": "abc123"}
        ttl = CacheTTL.get_ttl("analyze_sentiment", params)
        assert ttl == 3600

    def test_get_ttl_unknown_tool_default(self):
        """Test that unknown tools get default TTL of 5 minutes."""
        params = {"foo": "bar"}
        ttl = CacheTTL.get_ttl("unknown_tool", params)
        assert ttl == 300  # Default

    def test_get_ttl_subreddit_posts_default_sort(self):
        """Test TTL when sort param is missing (defaults to hot)."""
        params = {}  # No sort param
        ttl = CacheTTL.get_ttl("get_subreddit_posts", params)
        assert ttl == 300  # Should default to hot

    def test_ttl_ordering(self):
        """Test that TTL values follow expected ordering."""
        # Real-time content should have shorter TTL than historical
        assert CacheTTL.NEW_POSTS.value < CacheTTL.TOP_POSTS.value
        assert CacheTTL.HOT_POSTS.value < CacheTTL.TOP_POSTS.value

        # Comments should have medium TTL
        assert CacheTTL.NEW_POSTS.value < CacheTTL.COMMENTS.value < CacheTTL.TOP_POSTS.value
