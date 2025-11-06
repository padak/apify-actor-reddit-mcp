"""
Comprehensive tests for get_subreddit_posts tool.

Tests cover:
- Input validation (edge cases, invalid inputs, time_filter validation)
- All 5 sort types (hot, new, top, rising, controversial)
- Cache hit scenarios with variable TTL
- Cache miss scenarios
- Rate limiting integration
- Error handling (subreddit not found, permission errors)
- Empty results handling
- Integration tests (end-to-end)

Story: MVP-007 (Tool: get_subreddit_posts)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.tools.get_subreddit_posts import GetSubredditPostsInput, get_subreddit_posts


class TestGetSubredditPostsInput:
    """Test suite for GetSubredditPostsInput validation."""

    def test_valid_input_minimal(self):
        """Test valid input with minimal required fields."""
        params = GetSubredditPostsInput(subreddit="python")

        assert params.subreddit == "python"
        assert params.sort == "hot"
        assert params.time_filter is None
        assert params.limit == 25

    def test_valid_input_all_fields(self):
        """Test valid input with all fields specified."""
        params = GetSubredditPostsInput(
            subreddit="technology",
            sort="top",
            time_filter="week",
            limit=50,
        )

        assert params.subreddit == "technology"
        assert params.sort == "top"
        assert params.time_filter == "week"
        assert params.limit == 50

    def test_subreddit_required(self):
        """Test validation fails when subreddit is missing."""
        with pytest.raises(ValidationError) as exc_info:
            GetSubredditPostsInput()

        errors = exc_info.value.errors()
        assert any("subreddit" in str(error["loc"]) for error in errors)

    def test_invalid_subreddit_special_chars(self):
        """Test validation fails for subreddit with special characters."""
        invalid_names = ["r/python", "python-test", "python.test", "python/test"]

        for name in invalid_names:
            with pytest.raises(ValidationError) as exc_info:
                GetSubredditPostsInput(subreddit=name)

            errors = exc_info.value.errors()
            assert any("subreddit" in str(error["loc"]) for error in errors)

    def test_valid_subreddit_names(self):
        """Test valid subreddit names pass validation."""
        valid_names = [
            "python",
            "Python",
            "MachineLearning",
            "test_123",
            "AskReddit",
            "learnpython",
        ]

        for name in valid_names:
            params = GetSubredditPostsInput(subreddit=name)
            assert params.subreddit == name

    def test_invalid_sort_option(self):
        """Test validation fails for invalid sort option."""
        with pytest.raises(ValidationError) as exc_info:
            GetSubredditPostsInput(subreddit="python", sort="invalid")

        errors = exc_info.value.errors()
        assert any("sort" in str(error["loc"]) for error in errors)

    def test_valid_sort_options(self):
        """Test all valid sort options are accepted."""
        valid_sorts = ["hot", "new", "top", "rising", "controversial"]

        for sort_value in valid_sorts:
            # For top/controversial, provide time_filter
            if sort_value in ["top", "controversial"]:
                params = GetSubredditPostsInput(
                    subreddit="python", sort=sort_value, time_filter="day"
                )
            else:
                params = GetSubredditPostsInput(subreddit="python", sort=sort_value)

            assert params.sort == sort_value

    def test_time_filter_required_for_top(self):
        """Test validation fails when time_filter missing for top sort."""
        with pytest.raises(ValidationError) as exc_info:
            GetSubredditPostsInput(subreddit="python", sort="top")

        errors = exc_info.value.errors()
        assert any("time_filter" in str(error["loc"]) for error in errors)
        assert any("required" in str(error["msg"]).lower() for error in errors)

    def test_time_filter_required_for_controversial(self):
        """Test validation fails when time_filter missing for controversial sort."""
        with pytest.raises(ValidationError) as exc_info:
            GetSubredditPostsInput(subreddit="python", sort="controversial")

        errors = exc_info.value.errors()
        assert any("time_filter" in str(error["loc"]) for error in errors)
        assert any("required" in str(error["msg"]).lower() for error in errors)

    def test_time_filter_not_required_for_hot(self):
        """Test time_filter is optional for hot sort."""
        params = GetSubredditPostsInput(subreddit="python", sort="hot")
        assert params.time_filter is None

    def test_time_filter_not_required_for_new(self):
        """Test time_filter is optional for new sort."""
        params = GetSubredditPostsInput(subreddit="python", sort="new")
        assert params.time_filter is None

    def test_time_filter_not_required_for_rising(self):
        """Test time_filter is optional for rising sort."""
        params = GetSubredditPostsInput(subreddit="python", sort="rising")
        assert params.time_filter is None

    def test_invalid_time_filter(self):
        """Test validation fails for invalid time_filter."""
        with pytest.raises(ValidationError) as exc_info:
            GetSubredditPostsInput(
                subreddit="python", sort="top", time_filter="invalid"
            )

        errors = exc_info.value.errors()
        assert any("time_filter" in str(error["loc"]) for error in errors)

    def test_valid_time_filters(self):
        """Test all valid time filters are accepted."""
        valid_filters = ["hour", "day", "week", "month", "year", "all"]

        for filter_value in valid_filters:
            params = GetSubredditPostsInput(
                subreddit="python", sort="top", time_filter=filter_value
            )
            assert params.time_filter == filter_value

    def test_limit_too_low(self):
        """Test validation fails for limit < 1."""
        with pytest.raises(ValidationError) as exc_info:
            GetSubredditPostsInput(subreddit="python", limit=0)

        errors = exc_info.value.errors()
        assert any("limit" in str(error["loc"]) for error in errors)

    def test_limit_too_high(self):
        """Test validation fails for limit > 100."""
        with pytest.raises(ValidationError) as exc_info:
            GetSubredditPostsInput(subreddit="python", limit=101)

        errors = exc_info.value.errors()
        assert any("limit" in str(error["loc"]) for error in errors)

    def test_limit_boundary_values(self):
        """Test limit boundary values (1 and 100)."""
        params_min = GetSubredditPostsInput(subreddit="python", limit=1)
        params_max = GetSubredditPostsInput(subreddit="python", limit=100)

        assert params_min.limit == 1
        assert params_max.limit == 100

    def test_time_filter_with_top_sort(self):
        """Test time_filter works correctly with top sort."""
        params = GetSubredditPostsInput(
            subreddit="python", sort="top", time_filter="month"
        )

        assert params.sort == "top"
        assert params.time_filter == "month"

    def test_time_filter_with_controversial_sort(self):
        """Test time_filter works correctly with controversial sort."""
        params = GetSubredditPostsInput(
            subreddit="python", sort="controversial", time_filter="year"
        )

        assert params.sort == "controversial"
        assert params.time_filter == "year"


@pytest.mark.asyncio
class TestGetSubredditPostsTool:
    """Test suite for get_subreddit_posts tool functionality."""

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
        submission.title = "Test Post from Subreddit"
        submission.author.name = "test_user"
        submission.subreddit.display_name = "python"
        submission.created_utc = 1699123456
        submission.score = 500
        submission.upvote_ratio = 0.92
        submission.num_comments = 125
        submission.url = "https://reddit.com/r/python/test"
        submission.permalink = "/r/python/comments/abc123/test"
        submission.selftext = "Test post content from subreddit"
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
    async def test_get_subreddit_posts_hot_cache_miss(
        self, mock_reddit_client, mock_submission
    ):
        """Test get_subreddit_posts with hot sort and cache miss."""
        # Arrange
        params = GetSubredditPostsInput(subreddit="python", sort="hot", limit=10)

        with patch(
            "src.tools.get_subreddit_posts.get_reddit_client"
        ) as mock_get_client:
            with patch("src.tools.get_subreddit_posts.cache_manager") as mock_cache:
                with patch(
                    "src.tools.get_subreddit_posts.rate_limiter"
                ) as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_subreddit = MagicMock()
                    mock_subreddit.hot.return_value = [mock_submission]
                    mock_reddit_client.subreddit.return_value = mock_subreddit

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
                    result = await get_subreddit_posts(params)

                    # Assert
                    assert result["data"]["subreddit"] == "python"
                    assert result["data"]["sort"] == "hot"
                    assert result["data"]["total_returned"] == 1
                    assert result["data"]["posts"][0]["id"] == "abc123"
                    assert result["metadata"]["cached"] is False
                    assert result["metadata"]["reddit_api_calls"] == 1
                    mock_limiter.acquire.assert_called_once()
                    mock_subreddit.hot.assert_called_once_with(limit=10)

    @pytest.mark.asyncio
    async def test_get_subreddit_posts_new_cache_miss(
        self, mock_reddit_client, mock_submission
    ):
        """Test get_subreddit_posts with new sort and cache miss."""
        # Arrange
        params = GetSubredditPostsInput(subreddit="technology", sort="new", limit=15)

        with patch(
            "src.tools.get_subreddit_posts.get_reddit_client"
        ) as mock_get_client:
            with patch("src.tools.get_subreddit_posts.cache_manager") as mock_cache:
                with patch(
                    "src.tools.get_subreddit_posts.rate_limiter"
                ) as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_subreddit = MagicMock()
                    mock_subreddit.new.return_value = [mock_submission]
                    mock_reddit_client.subreddit.return_value = mock_subreddit

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
                    mock_limiter.get_remaining.return_value = 94

                    # Act
                    result = await get_subreddit_posts(params)

                    # Assert
                    assert result["data"]["sort"] == "new"
                    assert result["metadata"]["ttl"] == 120  # NEW_POSTS = 120s
                    mock_subreddit.new.assert_called_once_with(limit=15)

    @pytest.mark.asyncio
    async def test_get_subreddit_posts_top_cache_miss(
        self, mock_reddit_client, mock_submission
    ):
        """Test get_subreddit_posts with top sort and cache miss."""
        # Arrange
        params = GetSubredditPostsInput(
            subreddit="python", sort="top", time_filter="week", limit=20
        )

        with patch(
            "src.tools.get_subreddit_posts.get_reddit_client"
        ) as mock_get_client:
            with patch("src.tools.get_subreddit_posts.cache_manager") as mock_cache:
                with patch(
                    "src.tools.get_subreddit_posts.rate_limiter"
                ) as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_subreddit = MagicMock()
                    mock_subreddit.top.return_value = [mock_submission]
                    mock_reddit_client.subreddit.return_value = mock_subreddit

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
                    mock_limiter.get_remaining.return_value = 93

                    # Act
                    result = await get_subreddit_posts(params)

                    # Assert
                    assert result["data"]["sort"] == "top"
                    assert result["data"]["time_filter"] == "week"
                    assert result["metadata"]["ttl"] == 3600  # TOP_POSTS = 3600s
                    mock_subreddit.top.assert_called_once_with(
                        time_filter="week", limit=20
                    )

    @pytest.mark.asyncio
    async def test_get_subreddit_posts_rising_cache_miss(
        self, mock_reddit_client, mock_submission
    ):
        """Test get_subreddit_posts with rising sort and cache miss."""
        # Arrange
        params = GetSubredditPostsInput(subreddit="news", sort="rising", limit=25)

        with patch(
            "src.tools.get_subreddit_posts.get_reddit_client"
        ) as mock_get_client:
            with patch("src.tools.get_subreddit_posts.cache_manager") as mock_cache:
                with patch(
                    "src.tools.get_subreddit_posts.rate_limiter"
                ) as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_subreddit = MagicMock()
                    mock_subreddit.rising.return_value = [mock_submission]
                    mock_reddit_client.subreddit.return_value = mock_subreddit

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
                    mock_limiter.get_remaining.return_value = 92

                    # Act
                    result = await get_subreddit_posts(params)

                    # Assert
                    assert result["data"]["sort"] == "rising"
                    assert result["metadata"]["ttl"] == 180  # RISING_POSTS = 180s
                    mock_subreddit.rising.assert_called_once_with(limit=25)

    @pytest.mark.asyncio
    async def test_get_subreddit_posts_controversial_cache_miss(
        self, mock_reddit_client, mock_submission
    ):
        """Test get_subreddit_posts with controversial sort and cache miss."""
        # Arrange
        params = GetSubredditPostsInput(
            subreddit="politics", sort="controversial", time_filter="day", limit=30
        )

        with patch(
            "src.tools.get_subreddit_posts.get_reddit_client"
        ) as mock_get_client:
            with patch("src.tools.get_subreddit_posts.cache_manager") as mock_cache:
                with patch(
                    "src.tools.get_subreddit_posts.rate_limiter"
                ) as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_subreddit = MagicMock()
                    mock_subreddit.controversial.return_value = [mock_submission]
                    mock_reddit_client.subreddit.return_value = mock_subreddit

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
                    mock_limiter.get_remaining.return_value = 91

                    # Act
                    result = await get_subreddit_posts(params)

                    # Assert
                    assert result["data"]["sort"] == "controversial"
                    assert result["data"]["time_filter"] == "day"
                    assert result["metadata"]["ttl"] == 3600  # TOP_POSTS = 3600s
                    mock_subreddit.controversial.assert_called_once_with(
                        time_filter="day", limit=30
                    )

    @pytest.mark.asyncio
    async def test_get_subreddit_posts_cache_hit(self, mock_submission):
        """Test get_subreddit_posts with cache hit (no Reddit API call)."""
        # Arrange
        params = GetSubredditPostsInput(subreddit="python", sort="hot", limit=10)
        cached_data = [
            {
                "id": "cached123",
                "title": "Cached Post",
                "type": "post",
                "author": "cached_user",
                "subreddit": "python",
                "created_utc": 1699123456,
                "score": 300,
                "upvote_ratio": 0.88,
                "num_comments": 45,
                "url": "https://reddit.com/test",
                "permalink": "https://reddit.com/r/python/comments/cached123/test",
                "selftext": "Cached content",
                "link_flair_text": "Help",
                "is_self": True,
                "is_video": False,
                "over_18": False,
                "spoiler": False,
                "stickied": False,
                "locked": False,
                "archived": False,
            }
        ]

        with patch("src.tools.get_subreddit_posts.cache_manager") as mock_cache:
            with patch("src.tools.get_subreddit_posts.rate_limiter") as mock_limiter:
                # Cache hit scenario
                async def mock_get_or_fetch(key, fetch_func, ttl):
                    return {
                        "data": cached_data,
                        "metadata": {
                            "cached": True,
                            "cache_age_seconds": 180,
                            "ttl": ttl,
                        },
                    }

                mock_cache.get_or_fetch = mock_get_or_fetch
                mock_limiter.get_remaining.return_value = 100

                # Act
                result = await get_subreddit_posts(params)

                # Assert
                assert result["data"]["total_returned"] == 1
                assert result["data"]["posts"][0]["id"] == "cached123"
                assert result["metadata"]["cached"] is True
                assert result["metadata"]["cache_age_seconds"] == 180
                assert result["metadata"]["reddit_api_calls"] == 0

    @pytest.mark.asyncio
    async def test_get_subreddit_posts_empty_results(self, mock_reddit_client):
        """Test get_subreddit_posts returns empty results for empty subreddit."""
        # Arrange
        params = GetSubredditPostsInput(subreddit="emptysubreddit", sort="new")

        with patch(
            "src.tools.get_subreddit_posts.get_reddit_client"
        ) as mock_get_client:
            with patch("src.tools.get_subreddit_posts.cache_manager") as mock_cache:
                with patch(
                    "src.tools.get_subreddit_posts.rate_limiter"
                ) as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_subreddit = MagicMock()
                    mock_subreddit.new.return_value = []
                    mock_reddit_client.subreddit.return_value = mock_subreddit

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
                    mock_limiter.get_remaining.return_value = 90

                    # Act
                    result = await get_subreddit_posts(params)

                    # Assert
                    assert result["data"]["total_returned"] == 0
                    assert result["data"]["posts"] == []
                    assert result["metadata"]["cached"] is False

    @pytest.mark.asyncio
    async def test_get_subreddit_posts_subreddit_not_found(self, mock_reddit_client):
        """Test get_subreddit_posts handles subreddit not found error."""
        # Arrange
        params = GetSubredditPostsInput(subreddit="nonexistentsubreddit123", sort="hot")

        with patch(
            "src.tools.get_subreddit_posts.get_reddit_client"
        ) as mock_get_client:
            with patch("src.tools.get_subreddit_posts.cache_manager") as mock_cache:
                with patch(
                    "src.tools.get_subreddit_posts.rate_limiter"
                ) as mock_limiter:
                    # Setup mocks to simulate not found error
                    mock_get_client.return_value = mock_reddit_client
                    mock_subreddit = MagicMock()
                    mock_subreddit.hot.side_effect = Exception("Subreddit not found")
                    mock_reddit_client.subreddit.return_value = mock_subreddit

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
                    mock_limiter.get_remaining.return_value = 89

                    # Act
                    result = await get_subreddit_posts(params)

                    # Assert - should return empty results, not crash
                    assert result["data"]["posts"] == []
                    assert result["data"]["total_returned"] == 0

    @pytest.mark.asyncio
    async def test_get_subreddit_posts_rate_limiter_called(
        self, mock_reddit_client, mock_submission
    ):
        """Test get_subreddit_posts acquires rate limiter token before API call."""
        # Arrange
        params = GetSubredditPostsInput(subreddit="python", sort="hot")

        with patch(
            "src.tools.get_subreddit_posts.get_reddit_client"
        ) as mock_get_client:
            with patch("src.tools.get_subreddit_posts.cache_manager") as mock_cache:
                with patch(
                    "src.tools.get_subreddit_posts.rate_limiter"
                ) as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_subreddit = MagicMock()
                    mock_subreddit.hot.return_value = [mock_submission]
                    mock_reddit_client.subreddit.return_value = mock_subreddit

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
                    await get_subreddit_posts(params)

                    # Assert - rate limiter acquire should be called
                    mock_limiter.acquire.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_subreddit_posts_metadata_fields(
        self, mock_reddit_client, mock_submission
    ):
        """Test get_subreddit_posts returns all required metadata fields."""
        # Arrange
        params = GetSubredditPostsInput(subreddit="python", sort="hot")

        with patch(
            "src.tools.get_subreddit_posts.get_reddit_client"
        ) as mock_get_client:
            with patch("src.tools.get_subreddit_posts.cache_manager") as mock_cache:
                with patch(
                    "src.tools.get_subreddit_posts.rate_limiter"
                ) as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_subreddit = MagicMock()
                    mock_subreddit.hot.return_value = [mock_submission]
                    mock_reddit_client.subreddit.return_value = mock_subreddit

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
                    result = await get_subreddit_posts(params)

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
    async def test_get_subreddit_posts_response_structure(
        self, mock_reddit_client, mock_submission
    ):
        """Test get_subreddit_posts returns correct response structure."""
        # Arrange
        params = GetSubredditPostsInput(subreddit="python", sort="new")

        with patch(
            "src.tools.get_subreddit_posts.get_reddit_client"
        ) as mock_get_client:
            with patch("src.tools.get_subreddit_posts.cache_manager") as mock_cache:
                with patch(
                    "src.tools.get_subreddit_posts.rate_limiter"
                ) as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_subreddit = MagicMock()
                    mock_subreddit.new.return_value = [mock_submission]
                    mock_reddit_client.subreddit.return_value = mock_subreddit

                    async def mock_get_or_fetch(key, fetch_func, ttl):
                        data = await fetch_func()
                        return {
                            "data": data,
                            "metadata": {
                                "cached": False,
                                "cache_age_seconds": 0,
                                "ttl": 120,
                            },
                        }

                    mock_cache.get_or_fetch = mock_get_or_fetch
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining.return_value = 90

                    # Act
                    result = await get_subreddit_posts(params)

                    # Assert - check response structure
                    assert "data" in result
                    assert "metadata" in result

                    # Check data structure
                    data = result["data"]
                    assert "subreddit" in data
                    assert "sort" in data
                    assert "time_filter" in data
                    assert "posts" in data
                    assert "total_returned" in data

                    assert isinstance(data["posts"], list)
                    assert data["subreddit"] == "python"
                    assert data["sort"] == "new"

    @pytest.mark.asyncio
    async def test_get_subreddit_posts_variable_ttl_new(
        self, mock_reddit_client, mock_submission
    ):
        """Test get_subreddit_posts uses correct TTL for new sort (120s)."""
        # Arrange
        params = GetSubredditPostsInput(subreddit="python", sort="new")

        with patch(
            "src.tools.get_subreddit_posts.get_reddit_client"
        ) as mock_get_client:
            with patch("src.tools.get_subreddit_posts.cache_manager") as mock_cache:
                with patch(
                    "src.tools.get_subreddit_posts.rate_limiter"
                ) as mock_limiter:
                    mock_get_client.return_value = mock_reddit_client
                    mock_subreddit = MagicMock()
                    mock_subreddit.new.return_value = [mock_submission]
                    mock_reddit_client.subreddit.return_value = mock_subreddit

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
                    mock_limiter.get_remaining.return_value = 88

                    # Act
                    result = await get_subreddit_posts(params)

                    # Assert
                    assert result["metadata"]["ttl"] == 120  # NEW_POSTS

    @pytest.mark.asyncio
    async def test_get_subreddit_posts_variable_ttl_hot(
        self, mock_reddit_client, mock_submission
    ):
        """Test get_subreddit_posts uses correct TTL for hot sort (300s)."""
        # Arrange
        params = GetSubredditPostsInput(subreddit="python", sort="hot")

        with patch(
            "src.tools.get_subreddit_posts.get_reddit_client"
        ) as mock_get_client:
            with patch("src.tools.get_subreddit_posts.cache_manager") as mock_cache:
                with patch(
                    "src.tools.get_subreddit_posts.rate_limiter"
                ) as mock_limiter:
                    mock_get_client.return_value = mock_reddit_client
                    mock_subreddit = MagicMock()
                    mock_subreddit.hot.return_value = [mock_submission]
                    mock_reddit_client.subreddit.return_value = mock_subreddit

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
                    mock_limiter.get_remaining.return_value = 87

                    # Act
                    result = await get_subreddit_posts(params)

                    # Assert
                    assert result["metadata"]["ttl"] == 300  # HOT_POSTS

    @pytest.mark.asyncio
    async def test_get_subreddit_posts_variable_ttl_top(
        self, mock_reddit_client, mock_submission
    ):
        """Test get_subreddit_posts uses correct TTL for top sort (3600s)."""
        # Arrange
        params = GetSubredditPostsInput(
            subreddit="python", sort="top", time_filter="all"
        )

        with patch(
            "src.tools.get_subreddit_posts.get_reddit_client"
        ) as mock_get_client:
            with patch("src.tools.get_subreddit_posts.cache_manager") as mock_cache:
                with patch(
                    "src.tools.get_subreddit_posts.rate_limiter"
                ) as mock_limiter:
                    mock_get_client.return_value = mock_reddit_client
                    mock_subreddit = MagicMock()
                    mock_subreddit.top.return_value = [mock_submission]
                    mock_reddit_client.subreddit.return_value = mock_subreddit

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
                    mock_limiter.get_remaining.return_value = 86

                    # Act
                    result = await get_subreddit_posts(params)

                    # Assert
                    assert result["metadata"]["ttl"] == 3600  # TOP_POSTS
