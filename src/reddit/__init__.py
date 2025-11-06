"""
Reddit API integration layer using PRAW.

This module provides the complete Reddit API integration including:
- RedditClientManager: Singleton PRAW client manager
- Custom exception hierarchy for error handling
- Response normalization functions
- Rate limiting (TokenBucketRateLimiter)

Example:
    >>> from src.reddit import get_reddit_client, normalize_post
    >>> reddit = get_reddit_client()
    >>> submission = reddit.submission(id="abc123")
    >>> normalized = normalize_post(submission)
"""

from src.reddit.client import (
    RedditClientManager,
    reddit_client_manager,
    get_reddit_client,
)
from src.reddit.exceptions import (
    RedditAPIError,
    AuthenticationError,
    RateLimitError,
    NotFoundError,
    PermissionError,
    ServerError,
    ValidationError,
    TimeoutError,
)
from src.reddit.normalizer import (
    ResponseNormalizer,
    normalizer,
    normalize_post,
    normalize_comment,
    normalize_user,
    normalize_subreddit,
    normalize_post_batch,
)
from src.reddit.rate_limiter import TokenBucketRateLimiter

__all__ = [
    # Client management
    "RedditClientManager",
    "reddit_client_manager",
    "get_reddit_client",
    # Exceptions
    "RedditAPIError",
    "AuthenticationError",
    "RateLimitError",
    "NotFoundError",
    "PermissionError",
    "ServerError",
    "ValidationError",
    "TimeoutError",
    # Normalizers
    "ResponseNormalizer",
    "normalizer",
    "normalize_post",
    "normalize_comment",
    "normalize_user",
    "normalize_subreddit",
    "normalize_post_batch",
    # Rate limiting
    "TokenBucketRateLimiter",
]
