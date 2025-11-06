"""
Get Trending Topics MCP Tool.

Implements the get_trending_topics tool for analyzing trending keywords
on Reddit by extracting and counting keywords from recent posts.

Story: MVP-009 (Tool: get_trending_topics)
"""

import asyncio
import re
import time
from collections import Counter
from datetime import datetime
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

# Common English stopwords to filter out
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves"
}


class GetTrendingTopicsInput(BaseModel):
    """
    Input schema for get_trending_topics tool.

    Validates and sanitizes parameters for trending topic analysis.
    """

    scope: Literal["all", "subreddit"] = Field(
        "all",
        description="Analyze trends across all of Reddit or a specific subreddit",
    )

    subreddit: Optional[str] = Field(
        None,
        pattern="^[A-Za-z0-9_]+$",
        description="Subreddit name (required if scope='subreddit')",
        example="technology",
    )

    timeframe: Literal["hour", "day"] = Field(
        "day",
        description="Time range for trend analysis",
    )

    limit: int = Field(
        10,
        ge=1,
        le=50,
        description="Maximum number of trending topics to return",
    )

    @validator("subreddit")
    def validate_subreddit(cls, v: Optional[str], values: Dict[str, Any]) -> Optional[str]:
        """
        Validate that subreddit is provided when scope is 'subreddit'.

        Args:
            v: Subreddit value
            values: All field values

        Returns:
            Validated subreddit value

        Raises:
            ValueError: If subreddit required but not provided
        """
        if values.get("scope") == "subreddit" and not v:
            raise ValueError("subreddit is required when scope='subreddit'")
        return v

    class Config:
        schema_extra = {
            "example": {
                "scope": "subreddit",
                "subreddit": "technology",
                "timeframe": "day",
                "limit": 10,
            }
        }


def _extract_keywords(title: str) -> List[str]:
    """
    Extract meaningful keywords from a post title.

    Simple keyword extraction approach for MVP:
    1. Convert to lowercase
    2. Remove special characters
    3. Split on whitespace
    4. Filter stopwords
    5. Filter short words (<3 chars)

    Args:
        title: Post title string

    Returns:
        List of extracted keywords

    Example:
        >>> _extract_keywords("Breaking: New AI Model Released by OpenAI")
        ['breaking', 'new', 'model', 'released', 'openai']
    """
    # Convert to lowercase
    title_lower = title.lower()

    # Remove URLs
    title_lower = re.sub(r'https?://\S+', '', title_lower)

    # Remove special characters but keep alphanumeric and spaces
    title_clean = re.sub(r'[^a-z0-9\s]', ' ', title_lower)

    # Split on whitespace
    words = title_clean.split()

    # Filter stopwords and short words
    keywords = [
        word for word in words
        if word not in STOPWORDS and len(word) >= 3
    ]

    return keywords


def _calculate_growth(keyword: str, posts: List[Any]) -> float:
    """
    Calculate growth rate for a keyword.

    Simplified for MVP: Returns 1.0 as baseline.
    Future versions will compare to historical data.

    Args:
        keyword: Keyword to calculate growth for
        posts: List of posts (for future growth calculation)

    Returns:
        Growth rate (1.0 for MVP)

    Example:
        >>> _calculate_growth("chatgpt", posts_list)
        1.0
    """
    # MVP: Return baseline growth rate
    # v1.0: Compare frequency in recent period vs previous period
    return 1.0


def _top_subreddits(posts: List[Any], limit: int = 3) -> List[str]:
    """
    Get top subreddits where keyword appears.

    Counts subreddit occurrences and returns the most frequent ones.

    Args:
        posts: List of PRAW submission objects
        limit: Maximum number of subreddits to return (default: 3)

    Returns:
        List of top subreddit names

    Example:
        >>> _top_subreddits(keyword_posts, limit=3)
        ['technology', 'artificial', 'MachineLearning']
    """
    if not posts:
        return []

    # Count subreddit occurrences
    subreddit_counts = Counter(
        post.subreddit.display_name for post in posts
    )

    # Return top N subreddits
    top = subreddit_counts.most_common(limit)
    return [subreddit for subreddit, count in top]


@mcp.tool()
async def get_trending_topics(params: GetTrendingTopicsInput) -> Dict[str, Any]:
    """
    Identify trending topics on Reddit.

    This tool analyzes recent Reddit posts to identify trending keywords
    and topics. It uses keyword extraction and frequency analysis to
    determine what's currently popular on Reddit.

    COMPUTATIONALLY INTENSIVE: Fetches and analyzes 100-200 posts.
    Results are cached for 15 minutes to minimize load.

    Args:
        params: Validated trend analysis parameters (GetTrendingTopicsInput)

    Returns:
        Dictionary containing:
            - data: List of trending topics with metadata
            - metadata: Response metadata (caching, rate limits, timing)

    Raises:
        ValidationError: If input parameters are invalid
        RateLimitError: If Reddit API rate limit is exceeded
        RedditAPIError: If Reddit API returns an error

    Example:
        >>> result = await get_trending_topics(GetTrendingTopicsInput(
        ...     scope="subreddit",
        ...     subreddit="technology",
        ...     timeframe="day",
        ...     limit=10
        ... ))
        >>> print(f"Found {len(result['data']['trending_topics'])} trending topics")
        >>> print(f"Cached: {result['metadata']['cached']}")

    Cache Strategy:
        - TTL: 900 seconds (15 minutes)
        - Key pattern: reddit:get_trending_topics:{hash}:v1
        - High cache value due to computational cost

    Rate Limiting:
        - May require 1-2 API calls (depends on post count)
        - Uses token bucket rate limiter
    """
    start_time = time.time()

    logger.info(
        "get_trending_topics_started",
        scope=params.scope,
        subreddit=params.subreddit,
        timeframe=params.timeframe,
        limit=params.limit,
    )

    # 1. Generate cache key
    cache_key = key_generator.generate("get_trending_topics", params.dict())
    ttl = CacheTTL.get_ttl("get_trending_topics", params.dict())

    # 2. Define fetch function (called on cache miss)
    async def analyze_trends() -> Dict[str, Any]:
        """
        Analyze trends from Reddit posts.

        Returns:
            Dictionary with trending topics and metadata

        Raises:
            RedditAPIError: If Reddit API call fails
        """
        # Acquire rate limit token (blocks if necessary)
        await rate_limiter.acquire()

        logger.debug(
            "reddit_api_call",
            tool="get_trending_topics",
            rate_limit_remaining=rate_limiter.get_remaining(),
        )

        # Get Reddit client
        reddit = get_reddit_client()

        # Determine scope
        if params.scope == "subreddit":
            target = reddit.subreddit(params.subreddit)
            logger.debug("trend_target_subreddit", subreddit=params.subreddit)
        else:
            target = reddit.subreddit("all")
            logger.debug("trend_target_all")

        # Fetch recent posts based on timeframe
        # hour: new posts (100), day: top posts (200)
        try:
            if params.timeframe == "hour":
                posts = await asyncio.to_thread(
                    lambda: list(target.new(limit=100))
                )
                logger.debug("fetched_new_posts", count=len(posts))
            else:
                posts = await asyncio.to_thread(
                    lambda: list(target.top(time_filter="day", limit=200))
                )
                logger.debug("fetched_top_posts", count=len(posts))

            logger.info(
                "posts_fetched",
                scope=params.scope,
                timeframe=params.timeframe,
                posts_count=len(posts),
            )

        except Exception as e:
            logger.error(
                "posts_fetch_error",
                scope=params.scope,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

        # Extract keywords from titles
        keyword_freq: Dict[str, int] = {}
        keyword_posts: Dict[str, List[Any]] = {}

        for post in posts:
            keywords = _extract_keywords(post.title)

            for keyword in keywords:
                keyword_freq[keyword] = keyword_freq.get(keyword, 0) + 1
                if keyword not in keyword_posts:
                    keyword_posts[keyword] = []
                keyword_posts[keyword].append(post)

        logger.debug(
            "keywords_extracted",
            total_keywords=len(keyword_freq),
            unique_keywords=len(keyword_posts),
        )

        # Calculate trending score (frequency + recency)
        trending: List[Dict[str, Any]] = []
        for keyword, count in keyword_freq.items():
            if count >= 3:  # Minimum threshold
                sample_posts = keyword_posts[keyword][:3]

                trending.append({
                    "keyword": keyword,
                    "mentions": count,
                    "growth_rate": _calculate_growth(keyword, posts),
                    "sentiment": "neutral",  # Simplified for MVP
                    "top_subreddits": _top_subreddits(keyword_posts[keyword]),
                    "sample_posts": [
                        {
                            "id": p.id,
                            "title": p.title,
                            "score": p.score,
                            "subreddit": p.subreddit.display_name,
                        }
                        for p in sample_posts
                    ]
                })

        # Sort by mentions (most mentioned first)
        trending.sort(key=lambda x: x["mentions"], reverse=True)

        logger.info(
            "trending_analysis_completed",
            total_trending=len(trending),
            returned=min(params.limit, len(trending)),
        )

        return {
            "trending_topics": trending[:params.limit],
            "analysis_timestamp": int(datetime.utcnow().timestamp()),
            "posts_analyzed": len(posts),
            "unique_keywords": len(keyword_freq),
        }

    # 3. Get from cache or fetch
    response = await cache_manager.get_or_fetch(cache_key, analyze_trends, ttl)

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
        "get_trending_topics_completed",
        trending_count=len(response["data"]["trending_topics"]),
        cached=metadata.cached,
        execution_time_ms=metadata.execution_time_ms,
    )

    return tool_response.dict()
