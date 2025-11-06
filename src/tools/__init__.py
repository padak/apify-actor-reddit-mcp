"""MCP tool implementations for Reddit data access."""

from src.tools.get_subreddit_posts import (
    GetSubredditPostsInput,
    get_subreddit_posts,
)
from src.tools.get_trending_topics import (
    GetTrendingTopicsInput,
    get_trending_topics,
)
from src.tools.search_reddit import SearchRedditInput, search_reddit

__all__ = [
    # Search tool
    "search_reddit",
    "SearchRedditInput",
    # Subreddit posts tool
    "get_subreddit_posts",
    "GetSubredditPostsInput",
    # Trending topics tool
    "get_trending_topics",
    "GetTrendingTopicsInput",
]
