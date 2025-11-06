"""
Reddit API client manager using PRAW.

This module provides a singleton RedditClientManager for managing
Reddit API authentication and client lifecycle, following the
system architecture specification in Section 2.2.A.
"""

import os
import logging
from typing import Optional

import praw
from praw.exceptions import (
    PRAWException,
    InvalidToken,
    ResponseException,
    RequestException,
)

from .exceptions import (
    AuthenticationError,
    RedditAPIError,
    ServerError,
)


logger = logging.getLogger(__name__)


class RedditClientManager:
    """
    Singleton manager for Reddit API client (PRAW).

    This class ensures only one Reddit client instance exists throughout
    the application lifecycle. It handles OAuth2 authentication, connection
    pooling, and credential validation.

    Attributes:
        _instance: Singleton instance
        _client: PRAW Reddit client
        _initialized: Flag indicating successful initialization

    Example:
        >>> manager = RedditClientManager()
        >>> reddit = manager.get_client()
        >>> posts = reddit.subreddit("python").hot(limit=10)
    """

    _instance: Optional["RedditClientManager"] = None
    _client: Optional[praw.Reddit] = None
    _initialized: bool = False

    def __new__(cls) -> "RedditClientManager":
        """
        Create or return singleton instance.

        Returns:
            RedditClientManager singleton instance
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """
        Initialize RedditClientManager.

        Only initializes once (singleton pattern). Subsequent calls
        are no-ops.
        """
        # Only initialize once
        if not self._initialized:
            self._initialize_client()
            self._initialized = True

    def _initialize_client(self) -> None:
        """
        Initialize PRAW Reddit client with OAuth2 credentials.

        Loads credentials from environment variables and validates
        authentication by making a test request.

        Raises:
            AuthenticationError: If credentials are missing or invalid
            RedditAPIError: If Reddit API is unreachable
        """
        # Load credentials from environment
        client_id = os.getenv("REDDIT_CLIENT_ID")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        user_agent = os.getenv(
            "REDDIT_USER_AGENT",
            "Reddit-MCP-Server/1.0 (by /u/apify-mcp)"
        )

        # Validate required credentials
        if not client_id:
            logger.error("REDDIT_CLIENT_ID environment variable not set")
            raise AuthenticationError("REDDIT_CLIENT_ID is required")

        if not client_secret:
            logger.error("REDDIT_CLIENT_SECRET environment variable not set")
            raise AuthenticationError("REDDIT_CLIENT_SECRET is required")

        logger.info(
            "Initializing Reddit client",
            extra={
                "user_agent": user_agent,
                "client_id": f"{client_id[:8]}...",  # Partial log for security
            }
        )

        try:
            # Initialize PRAW with OAuth2
            self._client = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
                # Read-only mode (no user authentication needed for MVP)
                username=None,
                password=None,
            )

            # Configure PRAW settings
            self._client.read_only = True  # Explicitly set read-only
            self._client.config.timeout = 30  # 30 second timeout

            # Validate credentials by making a test request
            self._validate_credentials()

            logger.info(
                "Reddit client initialized successfully",
                extra={"read_only": self._client.read_only}
            )

        except InvalidToken as e:
            logger.error(f"Invalid Reddit OAuth token: {e}")
            raise AuthenticationError("Invalid Reddit credentials") from e

        except RequestException as e:
            logger.error(f"Reddit API request failed during init: {e}")
            raise RedditAPIError("Failed to connect to Reddit API") from e

        except PRAWException as e:
            logger.error(f"PRAW error during initialization: {e}")
            raise RedditAPIError(f"Reddit client initialization failed: {e}") from e

    def _validate_credentials(self) -> None:
        """
        Validate Reddit API credentials by making a test request.

        Tests authentication by fetching the authenticated user (which should
        be None in read-only mode) or fetching r/all metadata.

        Raises:
            AuthenticationError: If credentials are invalid
            ServerError: If Reddit API returns server error
            RedditAPIError: If validation fails for other reasons
        """
        try:
            # In read-only mode, we can't use user.me()
            # Instead, fetch r/all metadata as a validation
            test_subreddit = self._client.subreddit("all")

            # Access a property to force API call
            _ = test_subreddit.display_name

            logger.debug("Credential validation successful")

        except InvalidToken as e:
            raise AuthenticationError("Invalid Reddit OAuth token") from e

        except ResponseException as e:
            if e.response.status_code >= 500:
                raise ServerError(
                    "Reddit API unavailable during validation",
                    status_code=e.response.status_code
                ) from e
            raise AuthenticationError(
                f"Authentication failed: {e.response.status_code}"
            ) from e

        except PRAWException as e:
            raise RedditAPIError(f"Credential validation failed: {e}") from e

    def get_client(self) -> praw.Reddit:
        """
        Get the Reddit API client instance.

        Returns a singleton PRAW Reddit client. If not initialized,
        initializes it first.

        Returns:
            praw.Reddit: Authenticated Reddit API client

        Raises:
            AuthenticationError: If client initialization fails
            RedditAPIError: If client is unavailable

        Example:
            >>> manager = RedditClientManager()
            >>> reddit = manager.get_client()
            >>> posts = list(reddit.subreddit("python").hot(limit=5))
        """
        if self._client is None:
            logger.warning("Client not initialized, initializing now")
            self._initialize_client()

        if self._client is None:
            raise RedditAPIError("Reddit client initialization failed")

        return self._client

    def reset_client(self) -> None:
        """
        Reset the Reddit client instance.

        Forces re-initialization on next get_client() call. Useful for:
        - Credential rotation
        - Recovering from auth errors
        - Testing

        Example:
            >>> manager = RedditClientManager()
            >>> manager.reset_client()
            >>> reddit = manager.get_client()  # Re-initializes
        """
        logger.info("Resetting Reddit client")
        self._client = None
        self._initialized = False

    def is_initialized(self) -> bool:
        """
        Check if client is initialized.

        Returns:
            bool: True if client is initialized and ready

        Example:
            >>> manager = RedditClientManager()
            >>> if manager.is_initialized():
            ...     reddit = manager.get_client()
        """
        return self._initialized and self._client is not None

    @property
    def client(self) -> praw.Reddit:
        """
        Property accessor for Reddit client.

        Provides convenient property-style access to the client.

        Returns:
            praw.Reddit: Authenticated Reddit API client

        Example:
            >>> manager = RedditClientManager()
            >>> reddit = manager.client
            >>> print(reddit.read_only)
            True
        """
        return self.get_client()


# Singleton instance for convenient import
reddit_client_manager = RedditClientManager()


def get_reddit_client() -> praw.Reddit:
    """
    Convenience function to get Reddit client.

    This is a module-level function that returns the singleton client,
    providing a simpler import pattern.

    Returns:
        praw.Reddit: Authenticated Reddit API client

    Example:
        >>> from src.reddit.client import get_reddit_client
        >>> reddit = get_reddit_client()
        >>> posts = reddit.subreddit("python").hot(limit=10)
    """
    return reddit_client_manager.get_client()
