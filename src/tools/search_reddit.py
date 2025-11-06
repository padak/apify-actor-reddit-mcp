"""
Search Reddit MCP Tool.

Implements the search_reddit tool for searching Reddit posts by query with
optional subreddit filtering, time filters, sorting, and result limiting.

Story: MVP-006 (Tool: search_reddit)
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


class SearchRedditInput(BaseModel):
    """
    Input schema for search_reddit tool.

    Validates and sanitizes search parameters to ensure they meet Reddit API
    requirements and prevent injection attacks.
    """

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Search query or keywords",
        example="artificial intelligence",
    )

    subreddit: Optional[str] = Field(
        None,
        pattern="^[A-Za-z0-9_]+$",
        description="Limit search to specific subreddit (optional)",
        example="technology",
    )

    time_filter: Literal["hour", "day", "week", "month", "year", "all"] = Field(
        "week",
        description="Time range for search results",
    )

    sort: Literal["relevance", "hot", "top", "new", "comments"] = Field(
        "relevance",
        description="Sort order for results",
    )

    limit: int = Field(
        25,
        ge=1,
        le=100,
        description="Maximum number of results to return",
    )

    @validator("query")
    def sanitize_query(cls, v: str) -> str:
        """
        Sanitize query string to remove dangerous characters.

        Args:
            v: Raw query string

        Returns:
            Sanitized query string

        Raises:
            ValueError: If query is empty after sanitization
        """
        # Remove null bytes and strip whitespace
        sanitized = v.replace("\x00", "").strip()

        # Ensure query is not empty after sanitization
        if not sanitized:
            raise ValueError("Query cannot be empty")

        return sanitized

    class Config:
        schema_extra = {
            "example": {
                "query": "machine learning",
                "subreddit": "MachineLearning",
                "time_filter": "week",
                "sort": "top",
                "limit": 50,
            }
        }


@mcp.tool()
async def search_reddit(params: SearchRedditInput) -> Dict[str, Any]:
    """
    Search Reddit for posts matching query.

    This tool implements a cache-aside pattern with rate limiting to efficiently
    search Reddit while minimizing API calls. Results are cached for 5 minutes.

    Args:
        params: Validated search parameters (SearchRedditInput)

    Returns:
        Dictionary containing:
            - data: List of normalized Reddit posts
            - metadata: Response metadata (caching, rate limits, timing)

    Raises:
        ValidationError: If input parameters are invalid
        RateLimitError: If Reddit API rate limit is exceeded
        RedditAPIError: If Reddit API returns an error

    Example:
        >>> result = await search_reddit(SearchRedditInput(
        ...     query="python programming",
        ...     subreddit="python",
        ...     limit=10
        ... ))
        >>> print(f"Found {len(result['data'])} posts")
        >>> print(f"Cached: {result['metadata']['cached']}")

    Cache Strategy:
        - TTL: 300 seconds (5 minutes)
        - Key pattern: reddit:search_reddit:{hash}:v1
        - Cache hit expected: ~75%

    Rate Limiting:
        - 100 calls per 60 seconds (Reddit free tier)
        - Blocks if limit exceeded (waits for token availability)
    """
    start_time = time.time()

    logger.info(
        "search_reddit_started",
        query=params.query[:50],  # Log truncated query
        subreddit=params.subreddit,
        limit=params.limit,
    )

    # 1. Generate cache key
    cache_key = key_generator.generate("search_reddit", params.dict())
    ttl = CacheTTL.get_ttl("search_reddit", params.dict())

    # 2. Define fetch function (called on cache miss)
    async def fetch_from_reddit() -> List[Dict[str, Any]]:
        """
        Fetch search results from Reddit API.

        Returns:
            List of normalized post dictionaries

        Raises:
            RedditAPIError: If Reddit API call fails
        """
        # Acquire rate limit token (blocks if necessary)
        await rate_limiter.acquire()

        logger.debug(
            "reddit_api_call",
            tool="search_reddit",
            rate_limit_remaining=rate_limiter.get_remaining(),
        )

        # Get Reddit client
        reddit = get_reddit_client()

        # Build search target
        if params.subreddit:
            target = reddit.subreddit(params.subreddit)
            logger.debug("search_target_subreddit", subreddit=params.subreddit)
        else:
            target = reddit.subreddit("all")
            logger.debug("search_target_all")

        # Execute search (PRAW is sync, wrap in to_thread)
        try:
            results = await asyncio.to_thread(
                lambda: list(
                    target.search(
                        query=params.query,
                        sort=params.sort,
                        time_filter=params.time_filter,
                        limit=params.limit,
                    )
                )
            )

            logger.info(
                "reddit_search_completed",
                query=params.query[:50],
                results_count=len(results),
            )

        except Exception as e:
            logger.error(
                "reddit_search_error",
                query=params.query[:50],
                error=str(e),
                error_type=type(e).__name__,
            )
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
            "results": response["data"],
            "query": params.query,
            "subreddit": params.subreddit,
            "total_found": len(response["data"]),
        },
        metadata=metadata,
    )

    logger.info(
        "search_reddit_completed",
        query=params.query[:50],
        results_count=len(response["data"]),
        cached=metadata.cached,
        execution_time_ms=metadata.execution_time_ms,
    )

    return tool_response.dict()
