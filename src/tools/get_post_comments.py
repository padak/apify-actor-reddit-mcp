"""
Get Post Comments MCP Tool.

Implements the get_post_comments tool for fetching all comments from a Reddit
post with support for nested tree structures, comment sorting, and max depth
filtering.

Story: MVP-008 (Tool: get_post_comments)
"""

import asyncio
import re
import time
from typing import Any, Dict, List, Literal, Optional

import praw
from pydantic import BaseModel, Field, validator

from src.cache import CacheTTL, cache_manager, key_generator
from src.models.responses import ResponseMetadata, ToolResponse
from src.reddit import get_reddit_client, normalize_comment
from src.reddit.rate_limiter import TokenBucketRateLimiter
from src.server import mcp
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Global rate limiter instance
rate_limiter = TokenBucketRateLimiter(max_calls=100, period_seconds=60)


def _extract_post_id(post_id_or_url: str) -> str:
    """
    Extract Reddit post ID from various input formats.

    Handles:
    - Plain ID: "abc123"
    - With t3_ prefix: "t3_abc123"
    - Full URL: "https://reddit.com/r/python/comments/abc123/title/"
    - Short URL: "https://redd.it/abc123"

    Args:
        post_id_or_url: Post ID or URL in any supported format

    Returns:
        Clean post ID without prefix

    Raises:
        ValueError: If input format is invalid

    Example:
        >>> _extract_post_id("t3_abc123")
        "abc123"
        >>> _extract_post_id("https://reddit.com/r/python/comments/xyz789/title/")
        "xyz789"
    """
    # Remove whitespace
    value = post_id_or_url.strip()

    # Remove t3_ prefix if present
    if value.startswith("t3_"):
        value = value[3:]

    # Check if it's a URL
    if "reddit.com" in value or "redd.it" in value:
        # Extract post ID from URL using regex
        # Matches: /comments/{id}/ or redd.it/{id}
        patterns = [
            r'/comments/([a-z0-9]+)',  # Standard URL
            r'redd\.it/([a-z0-9]+)',   # Short URL
        ]

        for pattern in patterns:
            match = re.search(pattern, value)
            if match:
                return match.group(1)

        raise ValueError(
            f"Could not extract post ID from URL: {post_id_or_url}"
        )

    # Validate plain ID format (alphanumeric, 6-10 chars typically)
    if not re.match(r'^[a-z0-9]{5,10}$', value):
        raise ValueError(
            f"Invalid post ID format: {post_id_or_url}. "
            "Expected format: 'abc123', 't3_abc123', or full Reddit URL"
        )

    return value


def _build_comment_tree(comments: List[praw.models.Comment]) -> List[Dict[str, Any]]:
    """
    Build nested comment tree structure from flat comment list.

    Implements two-pass algorithm:
    1. First pass: Normalize all comments and create lookup map
    2. Second pass: Build tree by connecting parents to children

    Args:
        comments: Flat list of PRAW Comment objects

    Returns:
        List of top-level comments with nested replies

    Example:
        >>> comments = submission.comments.list()
        >>> tree = _build_comment_tree(comments)
        >>> print(tree[0]['replies'][0]['body'])
        "This is a reply"

    Note:
        Comments with missing parents are silently dropped to handle
        deleted/removed parent comments gracefully.
    """
    comment_map: Dict[str, Dict[str, Any]] = {}
    root_comments: List[Dict[str, Any]] = []

    # First pass: create all comment nodes with replies array
    for comment in comments:
        # Normalize comment to standard format
        normalized = normalize_comment(comment)
        # Initialize empty replies array
        normalized["replies"] = []
        # Store in map by comment ID
        comment_map[comment.id] = normalized

    # Second pass: build tree by connecting parents to children
    for comment in comments:
        # Check if this is a top-level comment (parent is submission)
        if comment.parent_id.startswith("t3_"):
            # Top-level comment - add to root
            root_comments.append(comment_map[comment.id])
        else:
            # Reply to another comment
            # Extract parent comment ID (remove t1_ prefix)
            parent_id = comment.parent_id.replace("t1_", "")

            # Find parent in map and add this comment to its replies
            if parent_id in comment_map:
                comment_map[parent_id]["replies"].append(comment_map[comment.id])
            else:
                # Parent not found (deleted/removed) - log and skip
                logger.debug(
                    "orphaned_comment",
                    comment_id=comment.id,
                    parent_id=parent_id,
                    reason="Parent comment not in tree (deleted/removed)",
                )

    return root_comments


class GetPostCommentsInput(BaseModel):
    """
    Input schema for get_post_comments tool.

    Validates and sanitizes parameters for fetching Reddit post comments.
    """

    post_id: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Reddit post ID (with or without t3_ prefix) or full URL",
        example="abc123",
    )

    sort: Literal["best", "top", "new", "controversial", "old"] = Field(
        "best",
        description="Comment sort order",
    )

    max_depth: int = Field(
        0,
        ge=0,
        le=10,
        description="Maximum comment depth (0 = all levels, 1-10 = limit depth)",
    )

    @validator("post_id")
    def clean_post_id(cls, v: str) -> str:
        """
        Clean and validate post ID.

        Extracts ID from URLs, removes t3_ prefix, validates format.

        Args:
            v: Raw post_id value

        Returns:
            Clean post ID

        Raises:
            ValueError: If post_id format is invalid
        """
        return _extract_post_id(v)

    class Config:
        schema_extra = {
            "example": {
                "post_id": "1a2b3c4",
                "sort": "best",
                "max_depth": 0,
            }
        }


@mcp.tool()
async def get_post_comments(params: GetPostCommentsInput) -> Dict[str, Any]:
    """
    Get all comments from a Reddit post with nested tree structure.

    This tool implements a cache-aside pattern with rate limiting to efficiently
    fetch and organize Reddit comments. Comments are built into a nested tree
    structure reflecting the actual reply hierarchy. Supports filtering by depth
    and various sort orders.

    Args:
        params: Validated comment fetch parameters (GetPostCommentsInput)

    Returns:
        Dictionary containing:
            - data: Post info and nested comment tree
            - metadata: Response metadata (caching, rate limits, timing)

    Raises:
        ValidationError: If input parameters are invalid
        NotFoundError: If post does not exist
        RateLimitError: If Reddit API rate limit is exceeded
        RedditAPIError: If Reddit API returns an error

    Example:
        >>> result = await get_post_comments(GetPostCommentsInput(
        ...     post_id="1a2b3c4",
        ...     sort="best",
        ...     max_depth=2
        ... ))
        >>> print(f"Total comments: {result['data']['metadata']['total_comments']}")
        >>> print(f"Top comment: {result['data']['comments'][0]['body'][:100]}")

    Cache Strategy:
        - TTL: 900 seconds (15 minutes)
        - Key pattern: reddit:get_post_comments:{hash}:v1
        - Comments are relatively stable after initial activity

    Rate Limiting:
        - 100 calls per 60 seconds (Reddit free tier)
        - Blocks if limit exceeded (waits for token availability)

    Performance:
        - Small threads (<100 comments): <2s
        - Large threads (500+ comments): <5s
        - Cached requests: <500ms

    Special Handling:
        - Deleted comments: Author shows as "[deleted]"
        - Removed comments: Body shows as "[removed]"
        - Missing parents: Orphaned comments are dropped with debug log
        - Max depth: Applied after fetching but before tree building
    """
    start_time = time.time()

    logger.info(
        "get_post_comments_started",
        post_id=params.post_id,
        sort=params.sort,
        max_depth=params.max_depth,
    )

    # 1. Generate cache key
    cache_key = key_generator.generate("get_post_comments", params.dict())
    ttl = CacheTTL.get_ttl("get_post_comments", params.dict())

    # 2. Define fetch function (called on cache miss)
    async def fetch_comments_from_reddit() -> Dict[str, Any]:
        """
        Fetch comments from Reddit API and build tree structure.

        Returns:
            Dictionary with post info, comments tree, and metadata

        Raises:
            RedditAPIError: If Reddit API call fails
            NotFoundError: If post does not exist
        """
        # Acquire rate limit token (blocks if necessary)
        await rate_limiter.acquire()

        logger.debug(
            "reddit_api_call",
            tool="get_post_comments",
            post_id=params.post_id,
            rate_limit_remaining=rate_limiter.get_remaining(),
        )

        # Get Reddit client
        reddit = get_reddit_client()

        try:
            # Fetch submission (PRAW is sync, wrap in to_thread)
            submission = await asyncio.to_thread(
                lambda: reddit.submission(id=params.post_id)
            )

            # Set comment sort order
            submission.comment_sort = params.sort

            logger.debug(
                "fetching_comments",
                post_id=params.post_id,
                post_title=submission.title[:50],
                num_comments=submission.num_comments,
            )

            # Expand all "more comments" (PRAW replace_more)
            # limit=0 means expand all, can be slow for large threads
            await asyncio.to_thread(
                lambda: submission.comments.replace_more(limit=0)
            )

            # Flatten comment forest into list
            all_comments = await asyncio.to_thread(
                lambda: submission.comments.list()
            )

            logger.info(
                "comments_fetched",
                post_id=params.post_id,
                total_comments=len(all_comments),
            )

            # Filter by max_depth if specified
            if params.max_depth > 0:
                filtered_comments = [
                    c for c in all_comments
                    if c.depth < params.max_depth
                ]
                logger.debug(
                    "depth_filtered",
                    original_count=len(all_comments),
                    filtered_count=len(filtered_comments),
                    max_depth=params.max_depth,
                )
                all_comments = filtered_comments

            # Build nested comment tree
            comments_tree = _build_comment_tree(all_comments)

            logger.info(
                "comment_tree_built",
                post_id=params.post_id,
                root_comments=len(comments_tree),
                total_comments=len(all_comments),
            )

            return {
                "post": {
                    "id": submission.id,
                    "title": submission.title,
                    "author": (
                        submission.author.name
                        if submission.author
                        else "[deleted]"
                    ),
                    "subreddit": submission.subreddit.display_name,
                    "created_utc": int(submission.created_utc),
                    "score": submission.score,
                    "num_comments": submission.num_comments,
                    "url": submission.url,
                    "permalink": f"https://reddit.com{submission.permalink}",
                },
                "comments": comments_tree,
                "metadata": {
                    "total_comments": len(all_comments),
                    "returned_comments": len(comments_tree),
                    "max_depth_applied": params.max_depth,
                },
            }

        except Exception as e:
            logger.error(
                "fetch_comments_error",
                post_id=params.post_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    # 3. Get from cache or fetch
    response = await cache_manager.get_or_fetch(
        cache_key,
        fetch_comments_from_reddit,
        ttl
    )

    # 4. Calculate execution time
    execution_time_ms = (time.time() - start_time) * 1000

    # 5. Build metadata
    metadata = ResponseMetadata(
        cached=response["metadata"]["cached"],
        cache_age_seconds=response["metadata"]["cache_age_seconds"],
        ttl=ttl,
        rate_limit_remaining=rate_limiter.get_remaining(),
        execution_time_ms=round(execution_time_ms, 2),
        reddit_api_calls=0 if response["metadata"]["cached"] else 1,
    )

    # 6. Build final response
    tool_response = ToolResponse(
        data=response["data"],
        metadata=metadata,
    )

    logger.info(
        "get_post_comments_completed",
        post_id=params.post_id,
        total_comments=response["data"]["metadata"]["total_comments"],
        root_comments=response["data"]["metadata"]["returned_comments"],
        cached=metadata.cached,
        execution_time_ms=metadata.execution_time_ms,
    )

    return tool_response.dict()
