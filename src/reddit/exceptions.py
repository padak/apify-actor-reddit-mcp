"""
Custom exceptions for Reddit API integration.

This module defines a hierarchy of exceptions for handling errors
during Reddit API interactions, following the system architecture
specification in Section 2.1.D.
"""

from typing import Optional


class RedditAPIError(Exception):
    """
    Base exception for all Reddit API related errors.

    This is the parent class for all Reddit-specific exceptions.
    Use this for catching any Reddit-related error.
    """

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        """
        Initialize RedditAPIError.

        Args:
            message: Error description
            status_code: Optional HTTP status code from Reddit API
        """
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class AuthenticationError(RedditAPIError):
    """
    Raised when Reddit API authentication fails.

    This occurs when:
    - Invalid client_id or client_secret
    - OAuth2 token is invalid or expired
    - Credentials are missing

    Example:
        >>> raise AuthenticationError("Invalid Reddit credentials")
    """

    def __init__(self, message: str = "Reddit authentication failed") -> None:
        """
        Initialize AuthenticationError.

        Args:
            message: Error description (default: "Reddit authentication failed")
        """
        super().__init__(message, status_code=401)


class RateLimitError(RedditAPIError):
    """
    Raised when Reddit API rate limit is exceeded.

    Reddit enforces a limit of 100 requests per minute for free tier.
    This exception includes retry information.

    Attributes:
        retry_after: Number of seconds to wait before retrying
        calls_made: Number of calls made in current window

    Example:
        >>> raise RateLimitError(retry_after=15, calls_made=100)
    """

    def __init__(
        self,
        retry_after: int,
        calls_made: int = 100,
        message: str = "Reddit API rate limit exceeded"
    ) -> None:
        """
        Initialize RateLimitError.

        Args:
            retry_after: Seconds to wait before retrying
            calls_made: Number of calls made in current window
            message: Error description
        """
        self.retry_after = retry_after
        self.calls_made = calls_made
        super().__init__(message, status_code=429)

    def __str__(self) -> str:
        """Return formatted error message with retry information."""
        return f"{self.message} (retry after {self.retry_after}s, calls: {self.calls_made})"


class NotFoundError(RedditAPIError):
    """
    Raised when requested Reddit resource is not found.

    This occurs when:
    - Subreddit doesn't exist or is banned/quarantined
    - Post has been deleted or removed
    - User account is suspended or deleted

    Note: This is not always an error condition. Deleted content
    is common on Reddit and should be handled gracefully.

    Example:
        >>> raise NotFoundError("Subreddit 'invalidname' not found")
    """

    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        message: Optional[str] = None
    ) -> None:
        """
        Initialize NotFoundError.

        Args:
            resource_type: Type of resource (e.g., "subreddit", "post", "user")
            resource_id: Identifier of the resource
            message: Optional custom error message
        """
        self.resource_type = resource_type
        self.resource_id = resource_id

        if message is None:
            message = f"{resource_type.capitalize()} '{resource_id}' not found"

        super().__init__(message, status_code=404)


class PermissionError(RedditAPIError):
    """
    Raised when access to Reddit resource is forbidden.

    This occurs when:
    - Subreddit is private and client lacks access
    - Content requires authentication (read-only mode limitation)
    - User is banned from subreddit

    Example:
        >>> raise PermissionError("Cannot access private subreddit")
    """

    def __init__(self, message: str = "Access to Reddit resource forbidden") -> None:
        """
        Initialize PermissionError.

        Args:
            message: Error description
        """
        super().__init__(message, status_code=403)


class ServerError(RedditAPIError):
    """
    Raised when Reddit API returns a server error.

    This occurs when Reddit's servers are:
    - Experiencing high load (503)
    - Encountering internal errors (500)
    - Temporarily unavailable (502)

    These errors are typically transient and should be retried
    with exponential backoff.

    Example:
        >>> raise ServerError("Reddit API returned 503", status_code=503)
    """

    def __init__(self, message: str, status_code: int = 500) -> None:
        """
        Initialize ServerError.

        Args:
            message: Error description
            status_code: HTTP status code (500, 502, or 503)
        """
        super().__init__(message, status_code=status_code)


class ValidationError(RedditAPIError):
    """
    Raised when request parameters are invalid.

    This occurs when:
    - Required parameters are missing
    - Parameters have invalid values
    - Parameters violate Reddit API constraints

    This is a client-side error and should not be retried.

    Example:
        >>> raise ValidationError("Limit must be between 1 and 100")
    """

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        """
        Initialize ValidationError.

        Args:
            message: Error description
            field: Optional field name that failed validation
        """
        self.field = field

        if field:
            message = f"{field}: {message}"

        super().__init__(message, status_code=422)


class TimeoutError(RedditAPIError):
    """
    Raised when Reddit API request times out.

    The default timeout is 30 seconds. If exceeded, this error
    is raised. This is typically transient and should be retried.

    Example:
        >>> raise TimeoutError("Request timed out after 30 seconds")
    """

    def __init__(
        self,
        message: str = "Reddit API request timed out",
        timeout_seconds: int = 30
    ) -> None:
        """
        Initialize TimeoutError.

        Args:
            message: Error description
            timeout_seconds: Timeout duration
        """
        self.timeout_seconds = timeout_seconds
        super().__init__(f"{message} ({timeout_seconds}s)", status_code=408)
