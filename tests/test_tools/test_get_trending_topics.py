"""
Comprehensive tests for get_trending_topics tool.

Tests cover:
- Input validation (edge cases, invalid inputs)
- Keyword extraction logic
- Frequency counting
- Helper functions (_extract_keywords, _calculate_growth, _top_subreddits)
- Cache hit scenarios
- Cache miss scenarios
- Rate limiting integration
- Error handling
- Empty results handling

Story: MVP-009 (Tool: get_trending_topics)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.tools.get_trending_topics import (
    GetTrendingTopicsInput,
    _extract_keywords,
    _calculate_growth,
    _top_subreddits,
    get_trending_topics,
)


class TestGetTrendingTopicsInput:
    """Test suite for GetTrendingTopicsInput validation."""

    def test_valid_input_minimal(self):
        """Test valid input with minimal required fields."""
        params = GetTrendingTopicsInput()

        assert params.scope == "all"
        assert params.subreddit is None
        assert params.timeframe == "day"
        assert params.limit == 10

    def test_valid_input_all_fields(self):
        """Test valid input with all fields specified."""
        params = GetTrendingTopicsInput(
            scope="subreddit",
            subreddit="technology",
            timeframe="hour",
            limit=25,
        )

        assert params.scope == "subreddit"
        assert params.subreddit == "technology"
        assert params.timeframe == "hour"
        assert params.limit == 25

    def test_scope_all_without_subreddit(self):
        """Test scope='all' works without subreddit."""
        params = GetTrendingTopicsInput(scope="all")

        assert params.scope == "all"
        assert params.subreddit is None

    def test_scope_subreddit_requires_subreddit(self):
        """Test validation fails when scope='subreddit' but no subreddit provided."""
        with pytest.raises(ValidationError) as exc_info:
            GetTrendingTopicsInput(scope="subreddit")

        errors = exc_info.value.errors()
        assert any("subreddit" in str(error["loc"]) for error in errors)

    def test_scope_subreddit_with_subreddit(self):
        """Test scope='subreddit' works with subreddit provided."""
        params = GetTrendingTopicsInput(
            scope="subreddit",
            subreddit="python"
        )

        assert params.scope == "subreddit"
        assert params.subreddit == "python"

    def test_invalid_subreddit_pattern(self):
        """Test validation fails for invalid subreddit pattern."""
        with pytest.raises(ValidationError) as exc_info:
            GetTrendingTopicsInput(
                scope="subreddit",
                subreddit="r/python"  # Invalid: contains slash
            )

        errors = exc_info.value.errors()
        assert any("subreddit" in str(error["loc"]) for error in errors)

    def test_valid_subreddit_pattern(self):
        """Test valid subreddit patterns."""
        valid_names = ["python", "MachineLearning", "tech_news", "Python3"]

        for name in valid_names:
            params = GetTrendingTopicsInput(
                scope="subreddit",
                subreddit=name
            )
            assert params.subreddit == name

    def test_invalid_scope(self):
        """Test validation fails for invalid scope."""
        with pytest.raises(ValidationError):
            GetTrendingTopicsInput(scope="invalid")

    def test_invalid_timeframe(self):
        """Test validation fails for invalid timeframe."""
        with pytest.raises(ValidationError):
            GetTrendingTopicsInput(timeframe="week")  # Not a valid option

    def test_limit_too_low(self):
        """Test validation fails for limit < 1."""
        with pytest.raises(ValidationError) as exc_info:
            GetTrendingTopicsInput(limit=0)

        errors = exc_info.value.errors()
        assert any("limit" in str(error["loc"]) for error in errors)

    def test_limit_too_high(self):
        """Test validation fails for limit > 50."""
        with pytest.raises(ValidationError) as exc_info:
            GetTrendingTopicsInput(limit=51)

        errors = exc_info.value.errors()
        assert any("limit" in str(error["loc"]) for error in errors)

    def test_limit_boundaries(self):
        """Test limit boundaries (1 and 50) are valid."""
        params_min = GetTrendingTopicsInput(limit=1)
        assert params_min.limit == 1

        params_max = GetTrendingTopicsInput(limit=50)
        assert params_max.limit == 50


class TestExtractKeywords:
    """Test suite for _extract_keywords helper function."""

    def test_extract_simple_keywords(self):
        """Test extraction from simple title."""
        title = "Python programming tutorial"
        keywords = _extract_keywords(title)

        assert "python" in keywords
        assert "programming" in keywords
        assert "tutorial" in keywords

    def test_filter_stopwords(self):
        """Test that stopwords are filtered out."""
        title = "The best way to learn AI and machine learning"
        keywords = _extract_keywords(title)

        # Stopwords should be removed
        assert "the" not in keywords
        assert "to" not in keywords
        assert "and" not in keywords

        # Content words should remain
        assert "best" in keywords
        assert "learn" in keywords
        assert "machine" in keywords
        assert "learning" in keywords

    def test_filter_short_words(self):
        """Test that words shorter than 3 characters are filtered."""
        title = "AI is a new ML technology"
        keywords = _extract_keywords(title)

        # Short words should be removed
        assert "ai" not in keywords
        assert "is" not in keywords
        assert "a" not in keywords
        assert "ml" not in keywords

        # Longer words should remain
        assert "new" in keywords
        assert "technology" in keywords

    def test_lowercase_conversion(self):
        """Test that all keywords are converted to lowercase."""
        title = "Breaking NEWS: OpenAI Releases GPT-5"
        keywords = _extract_keywords(title)

        # All should be lowercase
        assert "breaking" in keywords
        assert "news" in keywords
        assert "openai" in keywords
        assert "releases" in keywords

        # Uppercase versions should not exist
        assert "Breaking" not in keywords
        assert "NEWS" not in keywords

    def test_special_characters_removed(self):
        """Test that special characters are removed."""
        title = "Python 3.11: What's new? [Tutorial]"
        keywords = _extract_keywords(title)

        # Words should be extracted without special chars
        assert "python" in keywords
        assert "what" in keywords  # what's -> what
        assert "tutorial" in keywords

    def test_url_removal(self):
        """Test that URLs are removed from title."""
        title = "Check out https://example.com for more info"
        keywords = _extract_keywords(title)

        # URL should be removed
        assert "https" not in keywords
        assert "example" not in keywords
        assert "com" not in keywords

        # Other words should remain
        assert "check" in keywords
        assert "more" in keywords
        assert "info" in keywords

    def test_empty_title(self):
        """Test extraction from empty title."""
        keywords = _extract_keywords("")
        assert keywords == []

    def test_title_only_stopwords(self):
        """Test title containing only stopwords."""
        title = "the a an is are"
        keywords = _extract_keywords(title)
        assert keywords == []

    def test_title_with_numbers(self):
        """Test title containing numbers."""
        title = "Top 10 Python tips for 2024"
        keywords = _extract_keywords(title)

        # Numbers in words should be kept
        assert "top" in keywords
        assert "python" in keywords
        assert "tips" in keywords
        assert "2024" in keywords


class TestCalculateGrowth:
    """Test suite for _calculate_growth helper function."""

    def test_calculate_growth_mvp(self):
        """Test that MVP implementation returns 1.0."""
        # MVP: Always returns 1.0 as baseline
        posts = []  # Empty list for MVP (not used)
        growth = _calculate_growth("test", posts)

        assert growth == 1.0

    def test_calculate_growth_with_posts(self):
        """Test growth calculation with actual posts (MVP)."""
        mock_posts = [MagicMock() for _ in range(10)]
        growth = _calculate_growth("python", mock_posts)

        # MVP always returns 1.0
        assert growth == 1.0


class TestTopSubreddits:
    """Test suite for _top_subreddits helper function."""

    def test_top_subreddits_empty_list(self):
        """Test with empty post list."""
        result = _top_subreddits([])
        assert result == []

    def test_top_subreddits_single_subreddit(self):
        """Test with posts from single subreddit."""
        mock_posts = []
        for _ in range(5):
            post = MagicMock()
            post.subreddit.display_name = "python"
            mock_posts.append(post)

        result = _top_subreddits(mock_posts)

        assert len(result) == 1
        assert "python" in result

    def test_top_subreddits_multiple_subreddits(self):
        """Test with posts from multiple subreddits."""
        mock_posts = []

        # Create posts from different subreddits with different frequencies
        for _ in range(5):
            post = MagicMock()
            post.subreddit.display_name = "python"
            mock_posts.append(post)

        for _ in range(3):
            post = MagicMock()
            post.subreddit.display_name = "technology"
            mock_posts.append(post)

        for _ in range(1):
            post = MagicMock()
            post.subreddit.display_name = "programming"
            mock_posts.append(post)

        result = _top_subreddits(mock_posts, limit=3)

        # Should be ordered by frequency
        assert result[0] == "python"  # 5 posts
        assert result[1] == "technology"  # 3 posts
        assert result[2] == "programming"  # 1 post

    def test_top_subreddits_limit(self):
        """Test that limit parameter works correctly."""
        mock_posts = []

        # Create posts from 5 different subreddits
        for i in range(5):
            post = MagicMock()
            post.subreddit.display_name = f"subreddit{i}"
            mock_posts.append(post)

        result = _top_subreddits(mock_posts, limit=2)

        # Should return only top 2
        assert len(result) == 2

    def test_top_subreddits_default_limit(self):
        """Test default limit of 3."""
        mock_posts = []

        # Create posts from 5 different subreddits
        for i in range(5):
            post = MagicMock()
            post.subreddit.display_name = f"subreddit{i}"
            mock_posts.append(post)

        result = _top_subreddits(mock_posts)

        # Default limit is 3
        assert len(result) == 3


class TestGetTrendingTopicsTool:
    """Test suite for get_trending_topics tool function."""

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Test that cached results are returned quickly."""
        params = GetTrendingTopicsInput(
            scope="all",
            timeframe="day",
            limit=10
        )

        # Mock cache to return cached data
        mock_cache_response = {
            "data": {
                "trending_topics": [
                    {
                        "keyword": "python",
                        "mentions": 50,
                        "growth_rate": 1.0,
                        "sentiment": "neutral",
                        "top_subreddits": ["python", "programming"],
                        "sample_posts": [
                            {"id": "abc123", "title": "Test", "score": 100, "subreddit": "python"}
                        ]
                    }
                ],
                "analysis_timestamp": 1699123456,
                "posts_analyzed": 200,
                "unique_keywords": 150,
            },
            "metadata": {
                "cached": True,
                "cache_age_seconds": 120,
            }
        }

        with patch("src.tools.get_trending_topics.cache_manager") as mock_cache:
            mock_cache.get_or_fetch = AsyncMock(return_value=mock_cache_response)

            with patch("src.tools.get_trending_topics.rate_limiter") as mock_limiter:
                mock_limiter.get_remaining = MagicMock(return_value=95)

                result = await get_trending_topics(params)

                # Verify cache was used
                assert result["metadata"]["cached"] is True
                assert result["metadata"]["cache_age_seconds"] == 120

                # Verify no Reddit API calls made
                assert result["metadata"]["reddit_api_calls"] == 0

    @pytest.mark.asyncio
    async def test_cache_miss_scope_all(self):
        """Test cache miss scenario with scope='all'."""
        params = GetTrendingTopicsInput(
            scope="all",
            timeframe="day",
            limit=10
        )

        # Mock Reddit API
        mock_reddit = MagicMock()
        mock_subreddit = MagicMock()

        # Create mock posts
        mock_posts = []
        for i in range(10):
            post = MagicMock()
            post.id = f"post{i}"
            post.title = f"Python programming tutorial part {i}"
            post.score = 100 + i
            post.subreddit.display_name = "python"
            mock_posts.append(post)

        mock_subreddit.top = MagicMock(return_value=mock_posts)
        mock_reddit.subreddit = MagicMock(return_value=mock_subreddit)

        with patch("src.tools.get_trending_topics.get_reddit_client", return_value=mock_reddit):
            with patch("src.tools.get_trending_topics.cache_manager") as mock_cache:
                # Simulate cache miss by calling the fetch function
                async def mock_get_or_fetch(key, fetch_fn, ttl):
                    data = await fetch_fn()
                    return {
                        "data": data,
                        "metadata": {"cached": False, "cache_age_seconds": 0}
                    }

                mock_cache.get_or_fetch = mock_get_or_fetch

                with patch("src.tools.get_trending_topics.rate_limiter") as mock_limiter:
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining = MagicMock(return_value=95)

                    result = await get_trending_topics(params)

                    # Verify Reddit API was called
                    mock_reddit.subreddit.assert_called_with("all")

                    # Verify result structure
                    assert "data" in result
                    assert "metadata" in result
                    assert "trending_topics" in result["data"]
                    assert result["metadata"]["cached"] is False

    @pytest.mark.asyncio
    async def test_cache_miss_scope_subreddit(self):
        """Test cache miss scenario with scope='subreddit'."""
        params = GetTrendingTopicsInput(
            scope="subreddit",
            subreddit="technology",
            timeframe="hour",
            limit=5
        )

        # Mock Reddit API
        mock_reddit = MagicMock()
        mock_subreddit = MagicMock()

        # Create mock posts
        mock_posts = []
        for i in range(10):
            post = MagicMock()
            post.id = f"post{i}"
            post.title = f"AI technology breakthrough number {i}"
            post.score = 200 + i
            post.subreddit.display_name = "technology"
            mock_posts.append(post)

        mock_subreddit.new = MagicMock(return_value=mock_posts)
        mock_reddit.subreddit = MagicMock(return_value=mock_subreddit)

        with patch("src.tools.get_trending_topics.get_reddit_client", return_value=mock_reddit):
            with patch("src.tools.get_trending_topics.cache_manager") as mock_cache:
                async def mock_get_or_fetch(key, fetch_fn, ttl):
                    data = await fetch_fn()
                    return {
                        "data": data,
                        "metadata": {"cached": False, "cache_age_seconds": 0}
                    }

                mock_cache.get_or_fetch = mock_get_or_fetch

                with patch("src.tools.get_trending_topics.rate_limiter") as mock_limiter:
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining = MagicMock(return_value=95)

                    result = await get_trending_topics(params)

                    # Verify correct subreddit was targeted
                    mock_reddit.subreddit.assert_called_with("technology")

                    # Verify new() was called for hour timeframe
                    mock_subreddit.new.assert_called()

    @pytest.mark.asyncio
    async def test_keyword_frequency_threshold(self):
        """Test that only keywords with >= 3 mentions are included."""
        params = GetTrendingTopicsInput(limit=50)

        mock_reddit = MagicMock()
        mock_subreddit = MagicMock()

        # Create posts with controlled keyword frequencies
        mock_posts = []

        # Keyword "python" appears 5 times (should be included)
        for i in range(5):
            post = MagicMock()
            post.id = f"post{i}"
            post.title = "Python programming tutorial"
            post.score = 100
            post.subreddit.display_name = "python"
            mock_posts.append(post)

        # Keyword "rare" appears 2 times (should be excluded)
        for i in range(2):
            post = MagicMock()
            post.id = f"rare{i}"
            post.title = "rare keyword test"
            post.score = 50
            post.subreddit.display_name = "test"
            mock_posts.append(post)

        # Keyword "machine" appears 3 times (should be included - at threshold)
        for i in range(3):
            post = MagicMock()
            post.id = f"ml{i}"
            post.title = "machine learning guide"
            post.score = 75
            post.subreddit.display_name = "machinelearning"
            mock_posts.append(post)

        mock_subreddit.top = MagicMock(return_value=mock_posts)
        mock_reddit.subreddit = MagicMock(return_value=mock_subreddit)

        with patch("src.tools.get_trending_topics.get_reddit_client", return_value=mock_reddit):
            with patch("src.tools.get_trending_topics.cache_manager") as mock_cache:
                async def mock_get_or_fetch(key, fetch_fn, ttl):
                    data = await fetch_fn()
                    return {
                        "data": data,
                        "metadata": {"cached": False, "cache_age_seconds": 0}
                    }

                mock_cache.get_or_fetch = mock_get_or_fetch

                with patch("src.tools.get_trending_topics.rate_limiter") as mock_limiter:
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining = MagicMock(return_value=95)

                    result = await get_trending_topics(params)

                    trending_keywords = [
                        t["keyword"] for t in result["data"]["trending_topics"]
                    ]

                    # "python" should be included (5 mentions)
                    assert "python" in trending_keywords

                    # "machine" should be included (3 mentions - at threshold)
                    assert "machine" in trending_keywords

                    # "rare" should NOT be included (2 mentions - below threshold)
                    assert "rare" not in trending_keywords

    @pytest.mark.asyncio
    async def test_trending_sorted_by_mentions(self):
        """Test that trending topics are sorted by mention count."""
        params = GetTrendingTopicsInput(limit=50)

        mock_reddit = MagicMock()
        mock_subreddit = MagicMock()

        mock_posts = []

        # Keyword "python" - 10 mentions
        for i in range(10):
            post = MagicMock()
            post.id = f"python{i}"
            post.title = "Python programming"
            post.score = 100
            post.subreddit.display_name = "python"
            mock_posts.append(post)

        # Keyword "javascript" - 5 mentions
        for i in range(5):
            post = MagicMock()
            post.id = f"js{i}"
            post.title = "JavaScript tutorial"
            post.score = 90
            post.subreddit.display_name = "javascript"
            mock_posts.append(post)

        # Keyword "rust" - 7 mentions
        for i in range(7):
            post = MagicMock()
            post.id = f"rust{i}"
            post.title = "Rust programming"
            post.score = 85
            post.subreddit.display_name = "rust"
            mock_posts.append(post)

        mock_subreddit.top = MagicMock(return_value=mock_posts)
        mock_reddit.subreddit = MagicMock(return_value=mock_subreddit)

        with patch("src.tools.get_trending_topics.get_reddit_client", return_value=mock_reddit):
            with patch("src.tools.get_trending_topics.cache_manager") as mock_cache:
                async def mock_get_or_fetch(key, fetch_fn, ttl):
                    data = await fetch_fn()
                    return {
                        "data": data,
                        "metadata": {"cached": False, "cache_age_seconds": 0}
                    }

                mock_cache.get_or_fetch = mock_get_or_fetch

                with patch("src.tools.get_trending_topics.rate_limiter") as mock_limiter:
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining = MagicMock(return_value=95)

                    result = await get_trending_topics(params)

                    trending = result["data"]["trending_topics"]

                    # Find positions of keywords
                    keyword_positions = {
                        t["keyword"]: i for i, t in enumerate(trending)
                    }

                    # Verify ordering by mentions (python > rust > javascript)
                    assert keyword_positions["python"] < keyword_positions["rust"]
                    assert keyword_positions["rust"] < keyword_positions["javascript"]

                    # Verify actual mention counts
                    python_topic = next(t for t in trending if t["keyword"] == "python")
                    assert python_topic["mentions"] == 10

    @pytest.mark.asyncio
    async def test_sample_posts_included(self):
        """Test that sample posts are included for each trending topic."""
        params = GetTrendingTopicsInput(limit=10)

        mock_reddit = MagicMock()
        mock_subreddit = MagicMock()

        mock_posts = []
        for i in range(5):
            post = MagicMock()
            post.id = f"post{i}"
            post.title = "Python programming tutorial"
            post.score = 100 + i
            post.subreddit.display_name = "python"
            mock_posts.append(post)

        mock_subreddit.top = MagicMock(return_value=mock_posts)
        mock_reddit.subreddit = MagicMock(return_value=mock_subreddit)

        with patch("src.tools.get_trending_topics.get_reddit_client", return_value=mock_reddit):
            with patch("src.tools.get_trending_topics.cache_manager") as mock_cache:
                async def mock_get_or_fetch(key, fetch_fn, ttl):
                    data = await fetch_fn()
                    return {
                        "data": data,
                        "metadata": {"cached": False, "cache_age_seconds": 0}
                    }

                mock_cache.get_or_fetch = mock_get_or_fetch

                with patch("src.tools.get_trending_topics.rate_limiter") as mock_limiter:
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining = MagicMock(return_value=95)

                    result = await get_trending_topics(params)

                    # Find "python" topic
                    python_topic = next(
                        (t for t in result["data"]["trending_topics"] if t["keyword"] == "python"),
                        None
                    )

                    assert python_topic is not None
                    assert "sample_posts" in python_topic
                    assert len(python_topic["sample_posts"]) <= 3  # Max 3 samples

                    # Verify sample post structure
                    sample = python_topic["sample_posts"][0]
                    assert "id" in sample
                    assert "title" in sample
                    assert "score" in sample
                    assert "subreddit" in sample

    @pytest.mark.asyncio
    async def test_empty_results(self):
        """Test handling of no posts returned from Reddit."""
        params = GetTrendingTopicsInput()

        mock_reddit = MagicMock()
        mock_subreddit = MagicMock()
        mock_subreddit.top = MagicMock(return_value=[])  # No posts
        mock_reddit.subreddit = MagicMock(return_value=mock_subreddit)

        with patch("src.tools.get_trending_topics.get_reddit_client", return_value=mock_reddit):
            with patch("src.tools.get_trending_topics.cache_manager") as mock_cache:
                async def mock_get_or_fetch(key, fetch_fn, ttl):
                    data = await fetch_fn()
                    return {
                        "data": data,
                        "metadata": {"cached": False, "cache_age_seconds": 0}
                    }

                mock_cache.get_or_fetch = mock_get_or_fetch

                with patch("src.tools.get_trending_topics.rate_limiter") as mock_limiter:
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining = MagicMock(return_value=95)

                    result = await get_trending_topics(params)

                    # Should return empty trending topics
                    assert result["data"]["trending_topics"] == []
                    assert result["data"]["posts_analyzed"] == 0

    @pytest.mark.asyncio
    async def test_rate_limiter_integration(self):
        """Test that rate limiter is called before Reddit API."""
        params = GetTrendingTopicsInput()

        mock_reddit = MagicMock()
        mock_subreddit = MagicMock()
        mock_subreddit.top = MagicMock(return_value=[])
        mock_reddit.subreddit = MagicMock(return_value=mock_subreddit)

        with patch("src.tools.get_trending_topics.get_reddit_client", return_value=mock_reddit):
            with patch("src.tools.get_trending_topics.cache_manager") as mock_cache:
                async def mock_get_or_fetch(key, fetch_fn, ttl):
                    data = await fetch_fn()
                    return {
                        "data": data,
                        "metadata": {"cached": False, "cache_age_seconds": 0}
                    }

                mock_cache.get_or_fetch = mock_get_or_fetch

                with patch("src.tools.get_trending_topics.rate_limiter") as mock_limiter:
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining = MagicMock(return_value=95)

                    await get_trending_topics(params)

                    # Verify rate limiter was called
                    mock_limiter.acquire.assert_called_once()
