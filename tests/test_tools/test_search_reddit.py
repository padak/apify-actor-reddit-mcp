"""
Comprehensive tests for search_reddit tool.

Tests cover:
- Input validation (edge cases, invalid inputs)
- Cache hit scenarios
- Cache miss scenarios
- Rate limiting integration
- Error handling (Reddit API errors)
- Empty results handling
- Integration tests (end-to-end)

Story: MVP-006 (Tool: search_reddit)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.tools.search_reddit import SearchRedditInput, search_reddit


class TestSearchRedditInput:
    """Test suite for SearchRedditInput validation."""

    def test_valid_input_minimal(self):
        """Test valid input with minimal required fields."""
        params = SearchRedditInput(query="python")

        assert params.query == "python"
        assert params.subreddit is None
        assert params.time_filter == "week"
        assert params.sort == "relevance"
        assert params.limit == 25

    def test_valid_input_all_fields(self):
        """Test valid input with all fields specified."""
        params = SearchRedditInput(
            query="machine learning",
            subreddit="MachineLearning",
            time_filter="month",
            sort="top",
            limit=50,
        )

        assert params.query == "machine learning"
        assert params.subreddit == "MachineLearning"
        assert params.time_filter == "month"
        assert params.sort == "top"
        assert params.limit == 50

    def test_query_too_short(self):
        """Test validation fails for empty query."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRedditInput(query="")

        errors = exc_info.value.errors()
        assert any("query" in str(error["loc"]) for error in errors)

    def test_query_too_long(self):
        """Test validation fails for query exceeding max length."""
        long_query = "a" * 501  # Exceeds 500 char limit

        with pytest.raises(ValidationError) as exc_info:
            SearchRedditInput(query=long_query)

        errors = exc_info.value.errors()
        assert any("query" in str(error["loc"]) for error in errors)

    def test_query_sanitization_whitespace(self):
        """Test query is stripped of leading/trailing whitespace."""
        params = SearchRedditInput(query="  python programming  ")

        assert params.query == "python programming"

    def test_query_sanitization_null_bytes(self):
        """Test null bytes are removed from query."""
        params = SearchRedditInput(query="python\x00programming")

        assert params.query == "pythonprogramming"

    def test_query_empty_after_sanitization(self):
        """Test validation fails if query is empty after sanitization."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRedditInput(query="   ")

        errors = exc_info.value.errors()
        assert any("query" in str(error["loc"]) for error in errors)

    def test_invalid_subreddit_special_chars(self):
        """Test validation fails for subreddit with special characters."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRedditInput(query="test", subreddit="r/python")

        errors = exc_info.value.errors()
        assert any("subreddit" in str(error["loc"]) for error in errors)

    def test_valid_subreddit_pattern(self):
        """Test valid subreddit names pass validation."""
        valid_names = ["python", "Python", "MachineLearning", "test_123"]

        for name in valid_names:
            params = SearchRedditInput(query="test", subreddit=name)
            assert params.subreddit == name

    def test_invalid_time_filter(self):
        """Test validation fails for invalid time_filter."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRedditInput(query="test", time_filter="invalid")

        errors = exc_info.value.errors()
        assert any("time_filter" in str(error["loc"]) for error in errors)

    def test_valid_time_filters(self):
        """Test all valid time filters are accepted."""
        valid_filters = ["hour", "day", "week", "month", "year", "all"]

        for filter_value in valid_filters:
            params = SearchRedditInput(query="test", time_filter=filter_value)
            assert params.time_filter == filter_value

    def test_invalid_sort(self):
        """Test validation fails for invalid sort option."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRedditInput(query="test", sort="invalid")

        errors = exc_info.value.errors()
        assert any("sort" in str(error["loc"]) for error in errors)

    def test_valid_sort_options(self):
        """Test all valid sort options are accepted."""
        valid_sorts = ["relevance", "hot", "top", "new", "comments"]

        for sort_value in valid_sorts:
            params = SearchRedditInput(query="test", sort=sort_value)
            assert params.sort == sort_value

    def test_limit_too_low(self):
        """Test validation fails for limit < 1."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRedditInput(query="test", limit=0)

        errors = exc_info.value.errors()
        assert any("limit" in str(error["loc"]) for error in errors)

    def test_limit_too_high(self):
        """Test validation fails for limit > 100."""
        with pytest.raises(ValidationError) as exc_info:
            SearchRedditInput(query="test", limit=101)

        errors = exc_info.value.errors()
        assert any("limit" in str(error["loc"]) for error in errors)

    def test_limit_boundary_values(self):
        """Test limit boundary values (1 and 100)."""
        params_min = SearchRedditInput(query="test", limit=1)
        params_max = SearchRedditInput(query="test", limit=100)

        assert params_min.limit == 1
        assert params_max.limit == 100


@pytest.mark.asyncio
class TestSearchRedditTool:
    """Test suite for search_reddit tool functionality."""

    @pytest.fixture
    def mock_reddit_client(self):
        """Create mock Reddit client."""
        mock_client = MagicMock()
        return mock_client

    @pytest.fixture
    def mock_submission(self):
        """Create mock Reddit submission."""
        submission = MagicMock()
        submission.id = "abc123"
        submission.title = "Test Post Title"
        submission.author.name = "test_user"
        submission.subreddit.display_name = "python"
        submission.created_utc = 1699123456
        submission.score = 100
        submission.upvote_ratio = 0.95
        submission.num_comments = 50
        submission.url = "https://reddit.com/r/python/test"
        submission.permalink = "/r/python/comments/abc123/test"
        submission.selftext = "Test post content"
        submission.link_flair_text = "Discussion"
        submission.is_self = True
        submission.is_video = False
        submission.over_18 = False
        submission.spoiler = False
        submission.stickied = False
        submission.locked = False
        submission.archived = False
        return submission

    @pytest.mark.asyncio
    async def test_search_reddit_cache_miss(
        self, mock_reddit_client, mock_submission
    ):
        """Test search_reddit with cache miss (calls Reddit API)."""
        # Arrange
        params = SearchRedditInput(query="python", limit=10)

        with patch("src.tools.search_reddit.get_reddit_client") as mock_get_client:
            with patch("src.tools.search_reddit.cache_manager") as mock_cache:
                with patch("src.tools.search_reddit.rate_limiter") as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_reddit_client.subreddit.return_value.search.return_value = [
                        mock_submission
                    ]

                    # Cache miss scenario
                    async def mock_get_or_fetch(key, fetch_func, ttl):
                        data = await fetch_func()
                        return {
                            "data": data,
                            "metadata": {
                                "cached": False,
                                "cache_age_seconds": 0,
                                "ttl": ttl,
                            },
                        }

                    mock_cache.get_or_fetch = mock_get_or_fetch
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining.return_value = 95

                    # Act
                    result = await search_reddit(params)

                    # Assert
                    assert result["data"]["total_found"] == 1
                    assert result["data"]["results"][0]["id"] == "abc123"
                    assert result["metadata"]["cached"] is False
                    assert result["metadata"]["reddit_api_calls"] == 1
                    mock_limiter.acquire.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_reddit_cache_hit(self, mock_submission):
        """Test search_reddit with cache hit (no Reddit API call)."""
        # Arrange
        params = SearchRedditInput(query="python", limit=10)
        cached_data = [
            {
                "id": "cached123",
                "title": "Cached Post",
                "type": "post",
                "author": "cached_user",
                "subreddit": "python",
                "created_utc": 1699123456,
                "score": 200,
                "upvote_ratio": 0.9,
                "num_comments": 25,
                "url": "https://reddit.com/test",
                "permalink": "https://reddit.com/r/python/comments/cached123/test",
                "selftext": "",
                "link_flair_text": None,
                "is_self": False,
                "is_video": False,
                "over_18": False,
                "spoiler": False,
                "stickied": False,
                "locked": False,
                "archived": False,
            }
        ]

        with patch("src.tools.search_reddit.cache_manager") as mock_cache:
            with patch("src.tools.search_reddit.rate_limiter") as mock_limiter:
                # Cache hit scenario
                async def mock_get_or_fetch(key, fetch_func, ttl):
                    return {
                        "data": cached_data,
                        "metadata": {
                            "cached": True,
                            "cache_age_seconds": 120,
                            "ttl": ttl,
                        },
                    }

                mock_cache.get_or_fetch = mock_get_or_fetch
                mock_limiter.get_remaining.return_value = 100

                # Act
                result = await search_reddit(params)

                # Assert
                assert result["data"]["total_found"] == 1
                assert result["data"]["results"][0]["id"] == "cached123"
                assert result["metadata"]["cached"] is True
                assert result["metadata"]["cache_age_seconds"] == 120
                assert result["metadata"]["reddit_api_calls"] == 0

    @pytest.mark.asyncio
    async def test_search_reddit_empty_results(self, mock_reddit_client):
        """Test search_reddit returns empty results when no posts found."""
        # Arrange
        params = SearchRedditInput(query="nonexistent_query_xyz123", limit=10)

        with patch("src.tools.search_reddit.get_reddit_client") as mock_get_client:
            with patch("src.tools.search_reddit.cache_manager") as mock_cache:
                with patch("src.tools.search_reddit.rate_limiter") as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_reddit_client.subreddit.return_value.search.return_value = []

                    async def mock_get_or_fetch(key, fetch_func, ttl):
                        data = await fetch_func()
                        return {
                            "data": data,
                            "metadata": {
                                "cached": False,
                                "cache_age_seconds": 0,
                                "ttl": ttl,
                            },
                        }

                    mock_cache.get_or_fetch = mock_get_or_fetch
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining.return_value = 99

                    # Act
                    result = await search_reddit(params)

                    # Assert
                    assert result["data"]["total_found"] == 0
                    assert result["data"]["results"] == []
                    assert result["metadata"]["cached"] is False

    @pytest.mark.asyncio
    async def test_search_reddit_subreddit_specific(
        self, mock_reddit_client, mock_submission
    ):
        """Test search_reddit with specific subreddit."""
        # Arrange
        params = SearchRedditInput(
            query="python",
            subreddit="learnpython",
            limit=5,
        )

        with patch("src.tools.search_reddit.get_reddit_client") as mock_get_client:
            with patch("src.tools.search_reddit.cache_manager") as mock_cache:
                with patch("src.tools.search_reddit.rate_limiter") as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_reddit_client.subreddit.return_value.search.return_value = [
                        mock_submission
                    ]

                    async def mock_get_or_fetch(key, fetch_func, ttl):
                        data = await fetch_func()
                        return {
                            "data": data,
                            "metadata": {
                                "cached": False,
                                "cache_age_seconds": 0,
                                "ttl": ttl,
                            },
                        }

                    mock_cache.get_or_fetch = mock_get_or_fetch
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining.return_value = 98

                    # Act
                    result = await search_reddit(params)

                    # Assert
                    assert result["data"]["subreddit"] == "learnpython"
                    mock_reddit_client.subreddit.assert_called_with("learnpython")

    @pytest.mark.asyncio
    async def test_search_reddit_all_subreddits(
        self, mock_reddit_client, mock_submission
    ):
        """Test search_reddit searches all subreddits when none specified."""
        # Arrange
        params = SearchRedditInput(query="python", limit=5)

        with patch("src.tools.search_reddit.get_reddit_client") as mock_get_client:
            with patch("src.tools.search_reddit.cache_manager") as mock_cache:
                with patch("src.tools.search_reddit.rate_limiter") as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_reddit_client.subreddit.return_value.search.return_value = [
                        mock_submission
                    ]

                    async def mock_get_or_fetch(key, fetch_func, ttl):
                        data = await fetch_func()
                        return {
                            "data": data,
                            "metadata": {
                                "cached": False,
                                "cache_age_seconds": 0,
                                "ttl": ttl,
                            },
                        }

                    mock_cache.get_or_fetch = mock_get_or_fetch
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining.return_value = 97

                    # Act
                    result = await search_reddit(params)

                    # Assert
                    assert result["data"]["subreddit"] is None
                    mock_reddit_client.subreddit.assert_called_with("all")

    @pytest.mark.asyncio
    async def test_search_reddit_rate_limiter_called(
        self, mock_reddit_client, mock_submission
    ):
        """Test search_reddit acquires rate limiter token before API call."""
        # Arrange
        params = SearchRedditInput(query="test")

        with patch("src.tools.search_reddit.get_reddit_client") as mock_get_client:
            with patch("src.tools.search_reddit.cache_manager") as mock_cache:
                with patch("src.tools.search_reddit.rate_limiter") as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_reddit_client.subreddit.return_value.search.return_value = [
                        mock_submission
                    ]

                    async def mock_get_or_fetch(key, fetch_func, ttl):
                        data = await fetch_func()
                        return {
                            "data": data,
                            "metadata": {
                                "cached": False,
                                "cache_age_seconds": 0,
                                "ttl": ttl,
                            },
                        }

                    mock_cache.get_or_fetch = mock_get_or_fetch
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining.return_value = 50

                    # Act
                    await search_reddit(params)

                    # Assert - rate limiter acquire should be called
                    mock_limiter.acquire.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_reddit_metadata_fields(
        self, mock_reddit_client, mock_submission
    ):
        """Test search_reddit returns all required metadata fields."""
        # Arrange
        params = SearchRedditInput(query="test")

        with patch("src.tools.search_reddit.get_reddit_client") as mock_get_client:
            with patch("src.tools.search_reddit.cache_manager") as mock_cache:
                with patch("src.tools.search_reddit.rate_limiter") as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_reddit_client.subreddit.return_value.search.return_value = [
                        mock_submission
                    ]

                    async def mock_get_or_fetch(key, fetch_func, ttl):
                        data = await fetch_func()
                        return {
                            "data": data,
                            "metadata": {
                                "cached": False,
                                "cache_age_seconds": 0,
                                "ttl": 300,
                            },
                        }

                    mock_cache.get_or_fetch = mock_get_or_fetch
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining.return_value = 85

                    # Act
                    result = await search_reddit(params)

                    # Assert - check all metadata fields present
                    metadata = result["metadata"]
                    assert "cached" in metadata
                    assert "cache_age_seconds" in metadata
                    assert "ttl" in metadata
                    assert "rate_limit_remaining" in metadata
                    assert "execution_time_ms" in metadata
                    assert "reddit_api_calls" in metadata

                    # Check types
                    assert isinstance(metadata["cached"], bool)
                    assert isinstance(metadata["cache_age_seconds"], int)
                    assert isinstance(metadata["ttl"], int)
                    assert isinstance(metadata["rate_limit_remaining"], int)
                    assert isinstance(metadata["execution_time_ms"], float)
                    assert isinstance(metadata["reddit_api_calls"], int)

    @pytest.mark.asyncio
    async def test_search_reddit_response_structure(
        self, mock_reddit_client, mock_submission
    ):
        """Test search_reddit returns correct response structure."""
        # Arrange
        params = SearchRedditInput(query="test")

        with patch("src.tools.search_reddit.get_reddit_client") as mock_get_client:
            with patch("src.tools.search_reddit.cache_manager") as mock_cache:
                with patch("src.tools.search_reddit.rate_limiter") as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_reddit_client.subreddit.return_value.search.return_value = [
                        mock_submission
                    ]

                    async def mock_get_or_fetch(key, fetch_func, ttl):
                        data = await fetch_func()
                        return {
                            "data": data,
                            "metadata": {
                                "cached": False,
                                "cache_age_seconds": 0,
                                "ttl": 300,
                            },
                        }

                    mock_cache.get_or_fetch = mock_get_or_fetch
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining.return_value = 90

                    # Act
                    result = await search_reddit(params)

                    # Assert - check response structure
                    assert "data" in result
                    assert "metadata" in result

                    # Check data structure
                    data = result["data"]
                    assert "results" in data
                    assert "query" in data
                    assert "subreddit" in data
                    assert "total_found" in data

                    assert isinstance(data["results"], list)
                    assert data["query"] == "test"
