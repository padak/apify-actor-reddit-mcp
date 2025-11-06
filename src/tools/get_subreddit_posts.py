"""
Get Subreddit Posts MCP Tool.

Implements the get_subreddit_posts tool for fetching posts from a specific
subreddit with various sorting options (hot, new, top, rising, controversial).

Story: MVP-007 (Tool: get_subreddit_posts)
"""

import asyncio
import time
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, validator

from src.cache import CacheTTL, cache_manager, key_generator
from src.models.responses import ResponseMetadata, ToolResponse
from src.reddit import get_reddit_client, normalize_post_batch
from src.reddit.rate_limiter import TokenBucketRateLimiter
from src.server import mcp
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Global rate limiter instance
rate_limiter = TokenBucketRateLimiter(max_calls=100, period_seconds=60)


class GetSubredditPostsInput(BaseModel):
    """
    Input schema for get_subreddit_posts tool.

    Validates and sanitizes parameters for fetching posts from a subreddit
    with support for multiple sort types and time filters.
    """

    subreddit: str = Field(
        ...,
        pattern="^[A-Za-z0-9_]+$",
        description="Target subreddit name (without r/ prefix)",
        example="technology",
    )

    sort: Literal["hot", "new", "top", "rising", "controversial"] = Field(
        "hot",
        description="Sort order for posts",
    )

    time_filter: Optional[Literal["hour", "day", "week", "month", "year", "all"]] = Field(
        None,
        description="Time range for top/controversial sorts (required for these)",
    )

    limit: int = Field(
        25,
        ge=1,
        le=100,
        description="Maximum number of posts to return",
    )

    @validator("time_filter")
    def validate_time_filter(cls, v: Optional[str], values: Dict[str, Any]) -> Optional[str]:
        """
        Validate time_filter is provided when required by sort type.

        Args:
            v: time_filter value
            values: All field values (including sort)

        Returns:
            Validated time_filter value

        Raises:
            ValueError: If time_filter is required but not provided
        """
        sort = values.get("sort")

        # time_filter is required for top and controversial sorts
        if sort in ["top", "controversial"] and not v:
            raise ValueError(
                f"time_filter is required when sort='{sort}'. "
                "Valid values: hour, day, week, month, year, all"
            )

        # time_filter should not be used with other sort types
        if sort not in ["top", "controversial"] and v:
            logger.warning(
                "time_filter_ignored",
                sort=sort,
                time_filter=v,
                message=f"time_filter is ignored when sort='{sort}'",
            )

        return v

    class Config:
        schema_extra = {
            "example": {
                "subreddit": "python",
                "sort": "top",
                "time_filter": "week",
                "limit": 50,
            }
        }


@mcp.tool()
async def get_subreddit_posts(params: GetSubredditPostsInput) -> Dict[str, Any]:
    """
    Get posts from a specific subreddit.

    This tool fetches posts from a subreddit with various sorting options.
    Uses cache-aside pattern with variable TTL based on sort type:
    - new: 2 minutes (120s) - changes rapidly
    - hot: 5 minutes (300s) - moderately dynamic
    - rising: 3 minutes (180s) - dynamic trending
    - top: 1 hour (3600s) - historical, stable
    - controversial: 1 hour (3600s) - historical, stable

    Args:
        params: Validated input parameters (GetSubredditPostsInput)

    Returns:
        Dictionary containing:
            - data: List of normalized Reddit posts from subreddit
            - metadata: Response metadata (caching, rate limits, timing)

    Raises:
        ValidationError: If input parameters are invalid
        RateLimitError: If Reddit API rate limit is exceeded
        RedditAPIError: If Reddit API returns an error

    Example:
        >>> result = await get_subreddit_posts(GetSubredditPostsInput(
        ...     subreddit="python",
        ...     sort="hot",
        ...     limit=25
        ... ))
        >>> print(f"Found {len(result['data']['posts'])} posts")
        >>> print(f"Cached: {result['metadata']['cached']}")

    Cache Strategy:
        - TTL: Variable based on sort type (see above)
        - Key pattern: reddit:get_subreddit_posts:{hash}:v1
        - Cache hit expected: ~75%

    Rate Limiting:
        - 100 calls per 60 seconds (Reddit free tier)
        - Blocks if limit exceeded (waits for token availability)
    """
    start_time = time.time()

    logger.info(
        "get_subreddit_posts_started",
        subreddit=params.subreddit,
        sort=params.sort,
        time_filter=params.time_filter,
        limit=params.limit,
    )

    # 1. Generate cache key
    cache_key = key_generator.generate("get_subreddit_posts", params.dict())
    ttl = CacheTTL.get_ttl("get_subreddit_posts", params.dict())

    # 2. Define fetch function (called on cache miss)
    async def fetch_from_reddit() -> List[Dict[str, Any]]:
        """
        Fetch posts from Reddit API.

        Returns:
            List of normalized post dictionaries

        Raises:
            RedditAPIError: If Reddit API call fails
        """
        # Acquire rate limit token (blocks if necessary)
        await rate_limiter.acquire()

        logger.debug(
            "reddit_api_call",
            tool="get_subreddit_posts",
            rate_limit_remaining=rate_limiter.get_remaining(),
        )

        # Get Reddit client
        reddit = get_reddit_client()

        # Get subreddit instance
        subreddit = reddit.subreddit(params.subreddit)
        logger.debug("fetching_from_subreddit", subreddit=params.subreddit)

        # Execute appropriate PRAW method based on sort type
        try:
            if params.sort == "hot":
                results = await asyncio.to_thread(
                    lambda: list(subreddit.hot(limit=params.limit))
                )
            elif params.sort == "new":
                results = await asyncio.to_thread(
                    lambda: list(subreddit.new(limit=params.limit))
                )
            elif params.sort == "top":
                results = await asyncio.to_thread(
                    lambda: list(
                        subreddit.top(time_filter=params.time_filter, limit=params.limit)
                    )
                )
            elif params.sort == "rising":
                results = await asyncio.to_thread(
                    lambda: list(subreddit.rising(limit=params.limit))
                )
            elif params.sort == "controversial":
                results = await asyncio.to_thread(
                    lambda: list(
                        subreddit.controversial(
                            time_filter=params.time_filter, limit=params.limit
                        )
                    )
                )
            else:
                # Should never reach here due to Pydantic validation
                raise ValueError(f"Invalid sort type: {params.sort}")

            logger.info(
                "reddit_fetch_completed",
                subreddit=params.subreddit,
                sort=params.sort,
                results_count=len(results),
            )

        except Exception as e:
            logger.error(
                "reddit_fetch_error",
                subreddit=params.subreddit,
                sort=params.sort,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Return empty results for not found/permission errors
            # (fail gracefully instead of crashing)
            if "not found" in str(e).lower() or "forbidden" in str(e).lower():
                logger.warning(
                    "subreddit_not_accessible",
                    subreddit=params.subreddit,
                    error=str(e),
                )
                return []
            raise

        # Normalize results
        normalized = normalize_post_batch(results)

        return normalized

    # 3. Get from cache or fetch
    response = await cache_manager.get_or_fetch(cache_key, fetch_from_reddit, ttl)

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
        data={
            "subreddit": params.subreddit,
            "sort": params.sort,
            "time_filter": params.time_filter,
            "posts": response["data"],
            "total_returned": len(response["data"]),
        },
        metadata=metadata,
    )

    logger.info(
        "get_subreddit_posts_completed",
        subreddit=params.subreddit,
        sort=params.sort,
        posts_count=len(response["data"]),
        cached=metadata.cached,
        execution_time_ms=metadata.execution_time_ms,
    )

    return tool_response.dict()
