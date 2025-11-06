"""
Comprehensive tests for get_post_comments tool.

Tests cover:
- Input validation (post_id formats, URLs, edge cases)
- Post ID extraction from URLs
- Comment tree building (nested structure)
- Cache hit/miss scenarios
- Max depth filtering
- Rate limiting integration
- Error handling (deleted comments, missing parents)
- Integration tests (end-to-end)

Story: MVP-008 (Tool: get_post_comments)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.tools.get_post_comments import (
    GetPostCommentsInput,
    get_post_comments,
    _extract_post_id,
    _build_comment_tree,
)


class TestExtractPostId:
    """Test suite for _extract_post_id helper function."""

    def test_extract_plain_id(self):
        """Test extraction from plain post ID."""
        assert _extract_post_id("abc123") == "abc123"
        assert _extract_post_id("xyz789") == "xyz789"
        assert _extract_post_id("1a2b3c") == "1a2b3c"

    def test_extract_with_t3_prefix(self):
        """Test extraction from ID with t3_ prefix."""
        assert _extract_post_id("t3_abc123") == "abc123"
        assert _extract_post_id("t3_xyz789") == "xyz789"

    def test_extract_from_full_url(self):
        """Test extraction from full Reddit URL."""
        url = "https://reddit.com/r/python/comments/abc123/my_post_title/"
        assert _extract_post_id(url) == "abc123"

        url2 = "https://www.reddit.com/r/technology/comments/xyz789/title/"
        assert _extract_post_id(url2) == "xyz789"

    def test_extract_from_short_url(self):
        """Test extraction from Reddit short URL (redd.it)."""
        url = "https://redd.it/abc123"
        assert _extract_post_id(url) == "abc123"

    def test_extract_with_whitespace(self):
        """Test extraction handles leading/trailing whitespace."""
        assert _extract_post_id("  abc123  ") == "abc123"
        assert _extract_post_id("\t t3_xyz789 \n") == "xyz789"

    def test_extract_invalid_format(self):
        """Test extraction fails for invalid formats."""
        with pytest.raises(ValueError, match="Invalid post ID format"):
            _extract_post_id("invalid!")

        with pytest.raises(ValueError, match="Invalid post ID format"):
            _extract_post_id("ab")  # Too short

        with pytest.raises(ValueError, match="Invalid post ID format"):
            _extract_post_id("12345678901")  # Too long

    def test_extract_invalid_url(self):
        """Test extraction fails for invalid URL."""
        with pytest.raises(ValueError, match="Could not extract post ID from URL"):
            _extract_post_id("https://reddit.com/r/python/")

        with pytest.raises(ValueError, match="Could not extract post ID from URL"):
            _extract_post_id("https://reddit.com/invalid")


class TestBuildCommentTree:
    """Test suite for _build_comment_tree helper function."""

    def test_build_tree_empty_list(self):
        """Test building tree from empty comment list."""
        result = _build_comment_tree([])
        assert result == []

    def test_build_tree_single_top_level(self):
        """Test building tree with single top-level comment."""
        # Create mock comment
        comment = MagicMock()
        comment.id = "comment1"
        comment.parent_id = "t3_post123"  # Top-level (parent is submission)
        comment.author.name = "user1"
        comment.body = "Top level comment"
        comment.score = 10
        comment.created_utc = 1699123456
        comment.depth = 0
        comment.is_submitter = False
        comment.stickied = False
        comment.distinguished = None
        comment.edited = False
        comment.controversiality = 0

        result = _build_comment_tree([comment])

        assert len(result) == 1
        assert result[0]["id"] == "comment1"
        assert result[0]["body"] == "Top level comment"
        assert result[0]["replies"] == []

    def test_build_tree_nested_comments(self):
        """Test building tree with nested comments."""
        # Create mock comments
        # Structure:
        # - comment1 (top-level)
        #   - comment2 (reply to comment1)
        #     - comment3 (reply to comment2)

        comment1 = MagicMock()
        comment1.id = "comment1"
        comment1.parent_id = "t3_post123"
        comment1.author.name = "user1"
        comment1.body = "Top level"
        comment1.score = 10
        comment1.created_utc = 1699123456
        comment1.depth = 0
        comment1.is_submitter = False
        comment1.stickied = False
        comment1.distinguished = None
        comment1.edited = False
        comment1.controversiality = 0

        comment2 = MagicMock()
        comment2.id = "comment2"
        comment2.parent_id = "t1_comment1"  # Reply to comment1
        comment2.author.name = "user2"
        comment2.body = "First reply"
        comment2.score = 5
        comment2.created_utc = 1699123457
        comment2.depth = 1
        comment2.is_submitter = False
        comment2.stickied = False
        comment2.distinguished = None
        comment2.edited = False
        comment2.controversiality = 0

        comment3 = MagicMock()
        comment3.id = "comment3"
        comment3.parent_id = "t1_comment2"  # Reply to comment2
        comment3.author.name = "user3"
        comment3.body = "Second reply"
        comment3.score = 3
        comment3.created_utc = 1699123458
        comment3.depth = 2
        comment3.is_submitter = False
        comment3.stickied = False
        comment3.distinguished = None
        comment3.edited = False
        comment3.controversiality = 0

        result = _build_comment_tree([comment1, comment2, comment3])

        # Check structure
        assert len(result) == 1  # One top-level comment
        assert result[0]["id"] == "comment1"
        assert len(result[0]["replies"]) == 1  # One reply to comment1
        assert result[0]["replies"][0]["id"] == "comment2"
        assert len(result[0]["replies"][0]["replies"]) == 1  # One reply to comment2
        assert result[0]["replies"][0]["replies"][0]["id"] == "comment3"

    def test_build_tree_multiple_top_level(self):
        """Test building tree with multiple top-level comments."""
        comment1 = MagicMock()
        comment1.id = "comment1"
        comment1.parent_id = "t3_post123"
        comment1.author.name = "user1"
        comment1.body = "First top level"
        comment1.score = 10
        comment1.created_utc = 1699123456
        comment1.depth = 0
        comment1.is_submitter = False
        comment1.stickied = False
        comment1.distinguished = None
        comment1.edited = False
        comment1.controversiality = 0

        comment2 = MagicMock()
        comment2.id = "comment2"
        comment2.parent_id = "t3_post123"
        comment2.author.name = "user2"
        comment2.body = "Second top level"
        comment2.score = 8
        comment2.created_utc = 1699123457
        comment2.depth = 0
        comment2.is_submitter = False
        comment2.stickied = False
        comment2.distinguished = None
        comment2.edited = False
        comment2.controversiality = 0

        result = _build_comment_tree([comment1, comment2])

        assert len(result) == 2
        assert result[0]["id"] == "comment1"
        assert result[1]["id"] == "comment2"

    def test_build_tree_orphaned_comment(self):
        """Test building tree handles orphaned comments (missing parent)."""
        comment1 = MagicMock()
        comment1.id = "comment1"
        comment1.parent_id = "t3_post123"
        comment1.author.name = "user1"
        comment1.body = "Top level"
        comment1.score = 10
        comment1.created_utc = 1699123456
        comment1.depth = 0
        comment1.is_submitter = False
        comment1.stickied = False
        comment1.distinguished = None
        comment1.edited = False
        comment1.controversiality = 0

        # Orphaned comment (parent doesn't exist)
        comment2 = MagicMock()
        comment2.id = "comment2"
        comment2.parent_id = "t1_missing"  # Parent doesn't exist
        comment2.author.name = "user2"
        comment2.body = "Orphaned reply"
        comment2.score = 5
        comment2.created_utc = 1699123457
        comment2.depth = 1
        comment2.is_submitter = False
        comment2.stickied = False
        comment2.distinguished = None
        comment2.edited = False
        comment2.controversiality = 0

        result = _build_comment_tree([comment1, comment2])

        # Only top-level comment should be in result
        assert len(result) == 1
        assert result[0]["id"] == "comment1"
        assert len(result[0]["replies"]) == 0

    def test_build_tree_deleted_author(self):
        """Test building tree handles deleted comment authors."""
        comment = MagicMock()
        comment.id = "comment1"
        comment.parent_id = "t3_post123"
        comment.author = None  # Deleted author
        comment.body = "Comment with deleted author"
        comment.score = 5
        comment.created_utc = 1699123456
        comment.depth = 0
        comment.is_submitter = False
        comment.stickied = False
        comment.distinguished = None
        comment.edited = False
        comment.controversiality = 0

        result = _build_comment_tree([comment])

        assert len(result) == 1
        assert result[0]["author"] == "[deleted]"


class TestGetPostCommentsInput:
    """Test suite for GetPostCommentsInput validation."""

    def test_valid_input_minimal(self):
        """Test valid input with minimal required fields."""
        params = GetPostCommentsInput(post_id="abc123")

        assert params.post_id == "abc123"
        assert params.sort == "best"
        assert params.max_depth == 0

    def test_valid_input_all_fields(self):
        """Test valid input with all fields specified."""
        params = GetPostCommentsInput(
            post_id="xyz789",
            sort="top",
            max_depth=5,
        )

        assert params.post_id == "xyz789"
        assert params.sort == "top"
        assert params.max_depth == 5

    def test_post_id_with_t3_prefix(self):
        """Test post_id validator removes t3_ prefix."""
        params = GetPostCommentsInput(post_id="t3_abc123")
        assert params.post_id == "abc123"

    def test_post_id_from_url(self):
        """Test post_id validator extracts ID from URL."""
        url = "https://reddit.com/r/python/comments/abc123/title/"
        params = GetPostCommentsInput(post_id=url)
        assert params.post_id == "abc123"

    def test_invalid_post_id_format(self):
        """Test validation fails for invalid post_id format."""
        with pytest.raises(ValidationError) as exc_info:
            GetPostCommentsInput(post_id="invalid!")

        errors = exc_info.value.errors()
        assert any("post_id" in str(error["loc"]) for error in errors)

    def test_invalid_sort(self):
        """Test validation fails for invalid sort option."""
        with pytest.raises(ValidationError) as exc_info:
            GetPostCommentsInput(post_id="abc123", sort="invalid")

        errors = exc_info.value.errors()
        assert any("sort" in str(error["loc"]) for error in errors)

    def test_valid_sort_options(self):
        """Test all valid sort options are accepted."""
        valid_sorts = ["best", "top", "new", "controversial", "old"]

        for sort_value in valid_sorts:
            params = GetPostCommentsInput(post_id="abc123", sort=sort_value)
            assert params.sort == sort_value

    def test_max_depth_negative(self):
        """Test validation fails for negative max_depth."""
        with pytest.raises(ValidationError) as exc_info:
            GetPostCommentsInput(post_id="abc123", max_depth=-1)

        errors = exc_info.value.errors()
        assert any("max_depth" in str(error["loc"]) for error in errors)

    def test_max_depth_too_high(self):
        """Test validation fails for max_depth > 10."""
        with pytest.raises(ValidationError) as exc_info:
            GetPostCommentsInput(post_id="abc123", max_depth=11)

        errors = exc_info.value.errors()
        assert any("max_depth" in str(error["loc"]) for error in errors)

    def test_max_depth_boundary_values(self):
        """Test max_depth boundary values (0 and 10)."""
        params_min = GetPostCommentsInput(post_id="abc123", max_depth=0)
        params_max = GetPostCommentsInput(post_id="abc123", max_depth=10)

        assert params_min.max_depth == 0
        assert params_max.max_depth == 10


@pytest.mark.asyncio
class TestGetPostCommentsTool:
    """Test suite for get_post_comments tool functionality."""

    @pytest.fixture
    def mock_reddit_client(self):
        """Create mock Reddit client."""
        mock_client = MagicMock()
        return mock_client

    @pytest.fixture
    def mock_submission(self):
        """Create mock Reddit submission."""
        submission = MagicMock()
        submission.id = "post123"
        submission.title = "Test Post Title"
        submission.author.name = "post_author"
        submission.subreddit.display_name = "python"
        submission.created_utc = 1699123456
        submission.score = 100
        submission.num_comments = 3
        submission.url = "https://reddit.com/r/python/test"
        submission.permalink = "/r/python/comments/post123/test"
        submission.comment_sort = "best"
        return submission

    @pytest.fixture
    def mock_comments(self):
        """Create mock comment list."""
        comment1 = MagicMock()
        comment1.id = "comment1"
        comment1.parent_id = "t3_post123"
        comment1.author.name = "user1"
        comment1.body = "Top level comment"
        comment1.score = 10
        comment1.created_utc = 1699123456
        comment1.depth = 0
        comment1.is_submitter = False
        comment1.stickied = False
        comment1.distinguished = None
        comment1.edited = False
        comment1.controversiality = 0

        comment2 = MagicMock()
        comment2.id = "comment2"
        comment2.parent_id = "t1_comment1"
        comment2.author.name = "user2"
        comment2.body = "Reply to comment1"
        comment2.score = 5
        comment2.created_utc = 1699123457
        comment2.depth = 1
        comment2.is_submitter = False
        comment2.stickied = False
        comment2.distinguished = None
        comment2.edited = False
        comment2.controversiality = 0

        return [comment1, comment2]

    @pytest.mark.asyncio
    async def test_get_post_comments_cache_miss(
        self, mock_reddit_client, mock_submission, mock_comments
    ):
        """Test get_post_comments with cache miss (calls Reddit API)."""
        # Arrange
        params = GetPostCommentsInput(post_id="post123")

        with patch("src.tools.get_post_comments.get_reddit_client") as mock_get_client:
            with patch("src.tools.get_post_comments.cache_manager") as mock_cache:
                with patch("src.tools.get_post_comments.rate_limiter") as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_reddit_client.submission.return_value = mock_submission
                    mock_submission.comments.replace_more = MagicMock()
                    mock_submission.comments.list.return_value = mock_comments

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
                    result = await get_post_comments(params)

                    # Assert
                    assert result["data"]["post"]["id"] == "post123"
                    assert result["data"]["metadata"]["total_comments"] == 2
                    assert len(result["data"]["comments"]) == 1  # 1 top-level
                    assert result["metadata"]["cached"] is False
                    assert result["metadata"]["reddit_api_calls"] == 1
                    mock_limiter.acquire.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_post_comments_cache_hit(self):
        """Test get_post_comments with cache hit (no Reddit API call)."""
        # Arrange
        params = GetPostCommentsInput(post_id="post123")
        cached_data = {
            "post": {
                "id": "cached123",
                "title": "Cached Post",
                "author": "cached_author",
                "subreddit": "python",
                "created_utc": 1699123456,
                "score": 50,
                "num_comments": 10,
                "url": "https://reddit.com/test",
                "permalink": "https://reddit.com/r/python/comments/cached123/test",
            },
            "comments": [
                {
                    "id": "comment1",
                    "author": "user1",
                    "body": "Cached comment",
                    "score": 5,
                    "depth": 0,
                    "replies": [],
                }
            ],
            "metadata": {
                "total_comments": 1,
                "returned_comments": 1,
                "max_depth_applied": 0,
            },
        }

        with patch("src.tools.get_post_comments.cache_manager") as mock_cache:
            with patch("src.tools.get_post_comments.rate_limiter") as mock_limiter:
                # Cache hit scenario
                async def mock_get_or_fetch(key, fetch_func, ttl):
                    return {
                        "data": cached_data,
                        "metadata": {
                            "cached": True,
                            "cache_age_seconds": 600,
                            "ttl": ttl,
                        },
                    }

                mock_cache.get_or_fetch = mock_get_or_fetch
                mock_limiter.get_remaining.return_value = 100

                # Act
                result = await get_post_comments(params)

                # Assert
                assert result["data"]["post"]["id"] == "cached123"
                assert result["metadata"]["cached"] is True
                assert result["metadata"]["cache_age_seconds"] == 600
                assert result["metadata"]["reddit_api_calls"] == 0

    @pytest.mark.asyncio
    async def test_get_post_comments_max_depth_filter(
        self, mock_reddit_client, mock_submission
    ):
        """Test get_post_comments with max_depth filtering."""
        # Arrange
        params = GetPostCommentsInput(post_id="post123", max_depth=1)

        # Create comments with different depths
        comment1 = MagicMock()
        comment1.id = "comment1"
        comment1.parent_id = "t3_post123"
        comment1.author.name = "user1"
        comment1.body = "Depth 0"
        comment1.score = 10
        comment1.created_utc = 1699123456
        comment1.depth = 0
        comment1.is_submitter = False
        comment1.stickied = False
        comment1.distinguished = None
        comment1.edited = False
        comment1.controversiality = 0

        comment2 = MagicMock()
        comment2.id = "comment2"
        comment2.parent_id = "t1_comment1"
        comment2.author.name = "user2"
        comment2.body = "Depth 1"
        comment2.score = 5
        comment2.created_utc = 1699123457
        comment2.depth = 1
        comment2.is_submitter = False
        comment2.stickied = False
        comment2.distinguished = None
        comment2.edited = False
        comment2.controversiality = 0

        comment3 = MagicMock()
        comment3.id = "comment3"
        comment3.parent_id = "t1_comment2"
        comment3.author.name = "user3"
        comment3.body = "Depth 2 - should be filtered"
        comment3.score = 3
        comment3.created_utc = 1699123458
        comment3.depth = 2
        comment3.is_submitter = False
        comment3.stickied = False
        comment3.distinguished = None
        comment3.edited = False
        comment3.controversiality = 0

        all_comments = [comment1, comment2, comment3]

        with patch("src.tools.get_post_comments.get_reddit_client") as mock_get_client:
            with patch("src.tools.get_post_comments.cache_manager") as mock_cache:
                with patch("src.tools.get_post_comments.rate_limiter") as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_reddit_client.submission.return_value = mock_submission
                    mock_submission.comments.replace_more = MagicMock()
                    mock_submission.comments.list.return_value = all_comments

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
                    result = await get_post_comments(params)

                    # Assert - comment3 should be filtered out
                    assert result["data"]["metadata"]["total_comments"] == 2
                    assert result["data"]["metadata"]["max_depth_applied"] == 1

    @pytest.mark.asyncio
    async def test_get_post_comments_nested_structure(
        self, mock_reddit_client, mock_submission, mock_comments
    ):
        """Test get_post_comments returns nested comment structure."""
        # Arrange
        params = GetPostCommentsInput(post_id="post123")

        with patch("src.tools.get_post_comments.get_reddit_client") as mock_get_client:
            with patch("src.tools.get_post_comments.cache_manager") as mock_cache:
                with patch("src.tools.get_post_comments.rate_limiter") as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_reddit_client.submission.return_value = mock_submission
                    mock_submission.comments.replace_more = MagicMock()
                    mock_submission.comments.list.return_value = mock_comments

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
                    result = await get_post_comments(params)

                    # Assert nested structure
                    comments = result["data"]["comments"]
                    assert len(comments) == 1  # 1 top-level comment
                    assert comments[0]["id"] == "comment1"
                    assert "replies" in comments[0]
                    assert len(comments[0]["replies"]) == 1
                    assert comments[0]["replies"][0]["id"] == "comment2"

    @pytest.mark.asyncio
    async def test_get_post_comments_metadata_fields(
        self, mock_reddit_client, mock_submission, mock_comments
    ):
        """Test get_post_comments returns all required metadata fields."""
        # Arrange
        params = GetPostCommentsInput(post_id="post123")

        with patch("src.tools.get_post_comments.get_reddit_client") as mock_get_client:
            with patch("src.tools.get_post_comments.cache_manager") as mock_cache:
                with patch("src.tools.get_post_comments.rate_limiter") as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_reddit_client.submission.return_value = mock_submission
                    mock_submission.comments.replace_more = MagicMock()
                    mock_submission.comments.list.return_value = mock_comments

                    async def mock_get_or_fetch(key, fetch_func, ttl):
                        data = await fetch_func()
                        return {
                            "data": data,
                            "metadata": {
                                "cached": False,
                                "cache_age_seconds": 0,
                                "ttl": 900,
                            },
                        }

                    mock_cache.get_or_fetch = mock_get_or_fetch
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining.return_value = 85

                    # Act
                    result = await get_post_comments(params)

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
    async def test_get_post_comments_response_structure(
        self, mock_reddit_client, mock_submission, mock_comments
    ):
        """Test get_post_comments returns correct response structure."""
        # Arrange
        params = GetPostCommentsInput(post_id="post123")

        with patch("src.tools.get_post_comments.get_reddit_client") as mock_get_client:
            with patch("src.tools.get_post_comments.cache_manager") as mock_cache:
                with patch("src.tools.get_post_comments.rate_limiter") as mock_limiter:
                    # Setup mocks
                    mock_get_client.return_value = mock_reddit_client
                    mock_reddit_client.submission.return_value = mock_submission
                    mock_submission.comments.replace_more = MagicMock()
                    mock_submission.comments.list.return_value = mock_comments

                    async def mock_get_or_fetch(key, fetch_func, ttl):
                        data = await fetch_func()
                        return {
                            "data": data,
                            "metadata": {
                                "cached": False,
                                "cache_age_seconds": 0,
                                "ttl": 900,
                            },
                        }

                    mock_cache.get_or_fetch = mock_get_or_fetch
                    mock_limiter.acquire = AsyncMock()
                    mock_limiter.get_remaining.return_value = 90

                    # Act
                    result = await get_post_comments(params)

                    # Assert - check response structure
                    assert "data" in result
                    assert "metadata" in result

                    # Check data structure
                    data = result["data"]
                    assert "post" in data
                    assert "comments" in data
                    assert "metadata" in data

                    # Check post structure
                    post = data["post"]
                    assert "id" in post
                    assert "title" in post
                    assert "author" in post
                    assert "subreddit" in post

                    # Check data metadata
                    data_metadata = data["metadata"]
                    assert "total_comments" in data_metadata
                    assert "returned_comments" in data_metadata
