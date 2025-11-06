"""TTL (Time To Live) policies for different content types.

This module defines cache expiration policies based on content type
and freshness requirements.
"""

from enum import Enum
from typing import Any, Dict

import structlog

logger = structlog.get_logger(__name__)


class CacheTTL(Enum):
    """
    Cache TTL policies for different Reddit content types.

    TTL values are optimized based on how frequently the content changes:
    - Real-time content (new posts): Short TTL (2-5 minutes)
    - Historical content (top posts): Long TTL (1 hour)
    - Computed content (trending): Medium TTL (15 minutes)

    Values are in seconds.
    """

    # Real-time content (changes rapidly)
    NEW_POSTS = 120  # 2 minutes
    HOT_POSTS = 300  # 5 minutes
    RISING_POSTS = 180  # 3 minutes

    # Historical content (relatively stable)
    TOP_POSTS = 3600  # 1 hour
    SEARCH_RESULTS = 300  # 5 minutes

    # User/subreddit metadata (slow-changing)
    USER_INFO = 600  # 10 minutes
    SUBREDDIT_INFO = 3600  # 1 hour

    # Comments (relatively stable after initial activity)
    COMMENTS = 900  # 15 minutes

    # Trending/analysis (computationally expensive, cache aggressively)
    TRENDING_TOPICS = 900  # 15 minutes
    SENTIMENT_ANALYSIS = 3600  # 1 hour

    @staticmethod
    def get_ttl(tool_name: str, params: Dict[str, Any]) -> int:
        """
        Determine TTL based on tool name and parameters.

        This method implements dynamic TTL selection based on the type
        of content being cached. For example, "new" posts get shorter TTL
        than "top" posts since they change more frequently.

        Args:
            tool_name: Name of the MCP tool
            params: Tool parameters that may affect TTL

        Returns:
            TTL in seconds

        Example:
            >>> ttl = CacheTTL.get_ttl("get_subreddit_posts", {"sort": "new"})
            >>> print(f"TTL for new posts: {ttl}s")
            120
        """
        # Tool: get_subreddit_posts
        if tool_name == "get_subreddit_posts":
            sort = params.get("sort", "hot")
            if sort == "new":
                ttl = CacheTTL.NEW_POSTS.value
            elif sort == "hot":
                ttl = CacheTTL.HOT_POSTS.value
            elif sort == "rising":
                ttl = CacheTTL.RISING_POSTS.value
            else:  # top, controversial
                ttl = CacheTTL.TOP_POSTS.value

        # Tool: search_reddit
        elif tool_name == "search_reddit":
            ttl = CacheTTL.SEARCH_RESULTS.value

        # Tool: get_post_comments
        elif tool_name == "get_post_comments":
            ttl = CacheTTL.COMMENTS.value

        # Tool: get_trending_topics
        elif tool_name == "get_trending_topics":
            ttl = CacheTTL.TRENDING_TOPICS.value

        # Tool: get_user_info
        elif tool_name == "get_user_info":
            ttl = CacheTTL.USER_INFO.value

        # Tool: get_subreddit_info
        elif tool_name == "get_subreddit_info":
            ttl = CacheTTL.SUBREDDIT_INFO.value

        # Tool: analyze_sentiment
        elif tool_name == "analyze_sentiment":
            ttl = CacheTTL.SENTIMENT_ANALYSIS.value

        # Default fallback for unknown tools
        else:
            ttl = 300  # 5 minutes default
            logger.warning(
                "unknown_tool_using_default_ttl",
                tool=tool_name,
                default_ttl=ttl,
            )

        logger.debug(
            "ttl_determined",
            tool=tool_name,
            ttl_seconds=ttl,
            params=params,
        )

        return ttl
