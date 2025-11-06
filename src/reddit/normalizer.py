"""
Response normalization for Reddit API data.

This module provides functions to normalize Reddit API responses
(posts, comments, users, subreddits) into standardized dictionaries,
following the system architecture specification in Section 2.2.F.
"""

from typing import Any, Dict, Optional
from datetime import datetime

import praw


class ResponseNormalizer:
    """
    Normalizer for Reddit API responses.

    Converts PRAW objects into standardized dictionary formats
    for consistent output across all MCP tools.

    All normalization methods are static and can be called without
    instantiation.

    Example:
        >>> normalizer = ResponseNormalizer()
        >>> post_dict = normalizer.normalize_post(submission)
        >>> comment_dict = normalizer.normalize_comment(comment)
    """

    @staticmethod
    def normalize_post(submission: praw.models.Submission) -> Dict[str, Any]:
        """
        Normalize Reddit submission (post) to standard format.

        Converts a PRAW Submission object into a dictionary with
        standardized fields. Handles deleted authors and missing data.

        Args:
            submission: PRAW Submission object

        Returns:
            Dictionary with standardized post fields

        Example:
            >>> reddit = get_reddit_client()
            >>> submission = reddit.submission(id="abc123")
            >>> normalized = ResponseNormalizer.normalize_post(submission)
            >>> print(normalized['title'])
            "Example Post Title"
        """
        return {
            "id": submission.id,
            "type": "post",
            "title": submission.title,
            "author": (
                submission.author.name
                if submission.author
                else "[deleted]"
            ),
            "subreddit": submission.subreddit.display_name,
            "created_utc": int(submission.created_utc),
            "score": submission.score,
            "upvote_ratio": submission.upvote_ratio,
            "num_comments": submission.num_comments,
            "url": submission.url,
            "permalink": f"https://reddit.com{submission.permalink}",
            "selftext": (
                submission.selftext[:1000]
                if submission.selftext
                else ""
            ),
            "link_flair_text": submission.link_flair_text,
            "is_self": submission.is_self,
            "is_video": submission.is_video,
            "over_18": submission.over_18,
            "spoiler": submission.spoiler,
            "stickied": submission.stickied,
            "locked": submission.locked,
            "archived": submission.archived,
        }

    @staticmethod
    def normalize_comment(comment: praw.models.Comment) -> Dict[str, Any]:
        """
        Normalize Reddit comment to standard format.

        Converts a PRAW Comment object into a dictionary with
        standardized fields. Handles deleted comments and nested replies.

        Args:
            comment: PRAW Comment object

        Returns:
            Dictionary with standardized comment fields

        Example:
            >>> reddit = get_reddit_client()
            >>> submission = reddit.submission(id="abc123")
            >>> comment = submission.comments[0]
            >>> normalized = ResponseNormalizer.normalize_comment(comment)
            >>> print(normalized['body'])
            "This is a comment"
        """
        return {
            "id": comment.id,
            "type": "comment",
            "author": (
                comment.author.name
                if comment.author
                else "[deleted]"
            ),
            "body": comment.body if comment.body else "[removed]",
            "score": comment.score,
            "created_utc": int(comment.created_utc),
            "depth": comment.depth if hasattr(comment, 'depth') else 0,
            "parent_id": comment.parent_id,
            "is_submitter": comment.is_submitter,
            "stickied": comment.stickied,
            "distinguished": comment.distinguished,
            "edited": (
                int(comment.edited)
                if isinstance(comment.edited, (int, float))
                else False
            ),
            "controversiality": (
                comment.controversiality
                if hasattr(comment, 'controversiality')
                else 0
            ),
        }

    @staticmethod
    def normalize_user(redditor: praw.models.Redditor) -> Dict[str, Any]:
        """
        Normalize Reddit user (Redditor) to standard format.

        Converts a PRAW Redditor object into a dictionary with
        standardized user fields.

        Args:
            redditor: PRAW Redditor object

        Returns:
            Dictionary with standardized user fields

        Example:
            >>> reddit = get_reddit_client()
            >>> redditor = reddit.redditor("spez")
            >>> normalized = ResponseNormalizer.normalize_user(redditor)
            >>> print(normalized['username'])
            "spez"
        """
        return {
            "username": redditor.name,
            "id": redditor.id if hasattr(redditor, 'id') else None,
            "created_utc": int(redditor.created_utc),
            "link_karma": redditor.link_karma,
            "comment_karma": redditor.comment_karma,
            "is_gold": (
                redditor.is_gold
                if hasattr(redditor, 'is_gold')
                else False
            ),
            "is_mod": (
                redditor.is_mod
                if hasattr(redditor, 'is_mod')
                else False
            ),
            "has_verified_email": (
                redditor.has_verified_email
                if hasattr(redditor, 'has_verified_email')
                else False
            ),
            "icon_img": (
                redditor.icon_img
                if hasattr(redditor, 'icon_img')
                else None
            ),
        }

    @staticmethod
    def normalize_subreddit(subreddit: praw.models.Subreddit) -> Dict[str, Any]:
        """
        Normalize Reddit subreddit to standard format.

        Converts a PRAW Subreddit object into a dictionary with
        standardized subreddit fields.

        Args:
            subreddit: PRAW Subreddit object

        Returns:
            Dictionary with standardized subreddit fields

        Example:
            >>> reddit = get_reddit_client()
            >>> subreddit = reddit.subreddit("python")
            >>> normalized = ResponseNormalizer.normalize_subreddit(subreddit)
            >>> print(normalized['name'])
            "python"
        """
        return {
            "name": subreddit.display_name,
            "id": subreddit.id if hasattr(subreddit, 'id') else None,
            "title": subreddit.title,
            "description": subreddit.public_description,
            "subscribers": subreddit.subscribers,
            "active_users": (
                subreddit.active_user_count
                if hasattr(subreddit, 'active_user_count')
                else None
            ),
            "created_utc": int(subreddit.created_utc),
            "over18": subreddit.over18,
            "url": f"https://reddit.com{subreddit.url}",
            "icon_img": (
                subreddit.icon_img
                if hasattr(subreddit, 'icon_img')
                else None
            ),
            "community_icon": (
                subreddit.community_icon
                if hasattr(subreddit, 'community_icon')
                else None
            ),
            "submission_type": (
                subreddit.submission_type
                if hasattr(subreddit, 'submission_type')
                else "any"
            ),
        }

    @staticmethod
    def normalize_post_batch(
        submissions: list[praw.models.Submission]
    ) -> list[Dict[str, Any]]:
        """
        Normalize a batch of posts.

        Convenience method for normalizing multiple submissions at once.

        Args:
            submissions: List of PRAW Submission objects

        Returns:
            List of normalized post dictionaries

        Example:
            >>> reddit = get_reddit_client()
            >>> posts = list(reddit.subreddit("python").hot(limit=10))
            >>> normalized = ResponseNormalizer.normalize_post_batch(posts)
            >>> print(len(normalized))
            10
        """
        return [
            ResponseNormalizer.normalize_post(submission)
            for submission in submissions
        ]

    @staticmethod
    def normalize_comment_batch(
        comments: list[praw.models.Comment]
    ) -> list[Dict[str, Any]]:
        """
        Normalize a batch of comments.

        Convenience method for normalizing multiple comments at once.

        Args:
            comments: List of PRAW Comment objects

        Returns:
            List of normalized comment dictionaries

        Example:
            >>> reddit = get_reddit_client()
            >>> submission = reddit.submission(id="abc123")
            >>> comments = list(submission.comments)
            >>> normalized = ResponseNormalizer.normalize_comment_batch(comments)
        """
        return [
            ResponseNormalizer.normalize_comment(comment)
            for comment in comments
        ]

    @staticmethod
    def add_metadata(
        data: Dict[str, Any],
        cached: bool = False,
        cache_age_seconds: int = 0,
        rate_limit_remaining: Optional[int] = None,
        execution_time_ms: Optional[float] = None,
        reddit_api_calls: int = 0,
    ) -> Dict[str, Any]:
        """
        Add metadata to normalized response.

        Augments a normalized data dictionary with operational metadata
        about caching, rate limiting, and performance.

        Args:
            data: Normalized data dictionary
            cached: Whether response came from cache
            cache_age_seconds: Age of cached data in seconds
            rate_limit_remaining: Remaining Reddit API calls in window
            execution_time_ms: Request execution time in milliseconds
            reddit_api_calls: Number of Reddit API calls made

        Returns:
            Dictionary with data and metadata fields

        Example:
            >>> normalized = ResponseNormalizer.normalize_post(submission)
            >>> with_metadata = ResponseNormalizer.add_metadata(
            ...     normalized,
            ...     cached=True,
            ...     cache_age_seconds=120,
            ...     rate_limit_remaining=85
            ... )
            >>> print(with_metadata['metadata']['cached'])
            True
        """
        return {
            "data": data,
            "metadata": {
                "cached": cached,
                "cache_age_seconds": cache_age_seconds,
                "rate_limit_remaining": rate_limit_remaining,
                "execution_time_ms": execution_time_ms,
                "reddit_api_calls": reddit_api_calls,
                "timestamp": datetime.utcnow().isoformat(),
            }
        }


# Create singleton instance for convenient import
normalizer = ResponseNormalizer()


# Convenience functions for direct import
def normalize_post(submission: praw.models.Submission) -> Dict[str, Any]:
    """
    Normalize a Reddit post.

    Convenience function that calls ResponseNormalizer.normalize_post().

    Args:
        submission: PRAW Submission object

    Returns:
        Normalized post dictionary

    Example:
        >>> from src.reddit.normalizer import normalize_post
        >>> normalized = normalize_post(submission)
    """
    return ResponseNormalizer.normalize_post(submission)


def normalize_comment(comment: praw.models.Comment) -> Dict[str, Any]:
    """
    Normalize a Reddit comment.

    Convenience function that calls ResponseNormalizer.normalize_comment().

    Args:
        comment: PRAW Comment object

    Returns:
        Normalized comment dictionary

    Example:
        >>> from src.reddit.normalizer import normalize_comment
        >>> normalized = normalize_comment(comment)
    """
    return ResponseNormalizer.normalize_comment(comment)


def normalize_user(redditor: praw.models.Redditor) -> Dict[str, Any]:
    """
    Normalize a Reddit user.

    Convenience function that calls ResponseNormalizer.normalize_user().

    Args:
        redditor: PRAW Redditor object

    Returns:
        Normalized user dictionary

    Example:
        >>> from src.reddit.normalizer import normalize_user
        >>> normalized = normalize_user(redditor)
    """
    return ResponseNormalizer.normalize_user(redditor)


def normalize_subreddit(subreddit: praw.models.Subreddit) -> Dict[str, Any]:
    """
    Normalize a Reddit subreddit.

    Convenience function that calls ResponseNormalizer.normalize_subreddit().

    Args:
        subreddit: PRAW Subreddit object

    Returns:
        Normalized subreddit dictionary

    Example:
        >>> from src.reddit.normalizer import normalize_subreddit
        >>> normalized = normalize_subreddit(subreddit)
    """
    return ResponseNormalizer.normalize_subreddit(subreddit)
