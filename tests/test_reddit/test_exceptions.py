"""
Unit tests for Reddit API exceptions.

Tests the custom exception hierarchy defined in src/reddit/exceptions.py.
"""

import pytest

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


class TestRedditAPIError:
    """Test base RedditAPIError exception."""

    def test_basic_initialization(self):
        """Test basic error initialization."""
        error = RedditAPIError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.status_code is None

    def test_with_status_code(self):
        """Test error with status code."""
        error = RedditAPIError("Test error", status_code=500)
        assert error.message == "Test error"
        assert error.status_code == 500

    def test_is_exception(self):
        """Test that RedditAPIError is an Exception."""
        error = RedditAPIError("Test")
        assert isinstance(error, Exception)


class TestAuthenticationError:
    """Test AuthenticationError exception."""

    def test_default_message(self):
        """Test default error message."""
        error = AuthenticationError()
        assert "authentication failed" in str(error).lower()
        assert error.status_code == 401

    def test_custom_message(self):
        """Test custom error message."""
        error = AuthenticationError("Custom auth error")
        assert str(error) == "Custom auth error"
        assert error.status_code == 401

    def test_inheritance(self):
        """Test that AuthenticationError inherits from RedditAPIError."""
        error = AuthenticationError()
        assert isinstance(error, RedditAPIError)
        assert isinstance(error, Exception)


class TestRateLimitError:
    """Test RateLimitError exception."""

    def test_initialization(self):
        """Test rate limit error initialization."""
        error = RateLimitError(retry_after=15, calls_made=100)
        assert error.retry_after == 15
        assert error.calls_made == 100
        assert error.status_code == 429

    def test_default_calls_made(self):
        """Test default calls_made value."""
        error = RateLimitError(retry_after=10)
        assert error.calls_made == 100  # Default value

    def test_custom_message(self):
        """Test custom error message."""
        error = RateLimitError(
            retry_after=20,
            calls_made=105,
            message="Too many requests"
        )
        assert "Too many requests" in str(error)
        assert "20s" in str(error)
        assert "105" in str(error)

    def test_string_representation(self):
        """Test string representation includes retry info."""
        error = RateLimitError(retry_after=30, calls_made=100)
        error_str = str(error)
        assert "30" in error_str
        assert "100" in error_str

    def test_inheritance(self):
        """Test inheritance from RedditAPIError."""
        error = RateLimitError(retry_after=10)
        assert isinstance(error, RedditAPIError)


class TestNotFoundError:
    """Test NotFoundError exception."""

    def test_initialization(self):
        """Test not found error initialization."""
        error = NotFoundError(
            resource_type="subreddit",
            resource_id="invalidname"
        )
        assert error.resource_type == "subreddit"
        assert error.resource_id == "invalidname"
        assert error.status_code == 404

    def test_default_message(self):
        """Test default error message format."""
        error = NotFoundError(resource_type="post", resource_id="abc123")
        error_msg = str(error)
        assert "Post" in error_msg
        assert "abc123" in error_msg
        assert "not found" in error_msg.lower()

    def test_custom_message(self):
        """Test custom error message."""
        error = NotFoundError(
            resource_type="user",
            resource_id="deleted_user",
            message="User account was deleted"
        )
        assert str(error) == "User account was deleted"

    def test_various_resource_types(self):
        """Test with various resource types."""
        types = ["subreddit", "post", "user", "comment"]
        for resource_type in types:
            error = NotFoundError(resource_type=resource_type, resource_id="test")
            assert resource_type.capitalize() in str(error)

    def test_inheritance(self):
        """Test inheritance from RedditAPIError."""
        error = NotFoundError(resource_type="post", resource_id="123")
        assert isinstance(error, RedditAPIError)


class TestPermissionError:
    """Test PermissionError exception."""

    def test_default_message(self):
        """Test default error message."""
        error = PermissionError()
        assert "forbidden" in str(error).lower()
        assert error.status_code == 403

    def test_custom_message(self):
        """Test custom error message."""
        error = PermissionError("Cannot access private subreddit")
        assert str(error) == "Cannot access private subreddit"
        assert error.status_code == 403

    def test_inheritance(self):
        """Test inheritance from RedditAPIError."""
        error = PermissionError()
        assert isinstance(error, RedditAPIError)


class TestServerError:
    """Test ServerError exception."""

    def test_initialization(self):
        """Test server error initialization."""
        error = ServerError("Reddit unavailable", status_code=503)
        assert str(error) == "Reddit unavailable"
        assert error.status_code == 503

    def test_default_status_code(self):
        """Test default status code."""
        error = ServerError("Server error")
        assert error.status_code == 500

    def test_various_status_codes(self):
        """Test with various server error codes."""
        codes = [500, 502, 503]
        for code in codes:
            error = ServerError("Error", status_code=code)
            assert error.status_code == code

    def test_inheritance(self):
        """Test inheritance from RedditAPIError."""
        error = ServerError("Error")
        assert isinstance(error, RedditAPIError)


class TestValidationError:
    """Test ValidationError exception."""

    def test_initialization(self):
        """Test validation error initialization."""
        error = ValidationError("Invalid limit", field="limit")
        assert error.field == "limit"
        assert error.status_code == 422

    def test_message_with_field(self):
        """Test error message includes field name."""
        error = ValidationError("Must be between 1 and 100", field="limit")
        error_msg = str(error)
        assert "limit" in error_msg
        assert "Must be between 1 and 100" in error_msg

    def test_message_without_field(self):
        """Test error message without field name."""
        error = ValidationError("Invalid request")
        assert str(error) == "Invalid request"
        assert error.field is None

    def test_inheritance(self):
        """Test inheritance from RedditAPIError."""
        error = ValidationError("Error")
        assert isinstance(error, RedditAPIError)


class TestTimeoutError:
    """Test TimeoutError exception."""

    def test_default_initialization(self):
        """Test default timeout error."""
        error = TimeoutError()
        assert "timed out" in str(error).lower()
        assert "30s" in str(error)
        assert error.timeout_seconds == 30
        assert error.status_code == 408

    def test_custom_timeout(self):
        """Test custom timeout duration."""
        error = TimeoutError("Custom timeout", timeout_seconds=60)
        assert "60s" in str(error)
        assert error.timeout_seconds == 60

    def test_inheritance(self):
        """Test inheritance from RedditAPIError."""
        error = TimeoutError()
        assert isinstance(error, RedditAPIError)


class TestExceptionHierarchy:
    """Test exception inheritance hierarchy."""

    def test_all_exceptions_inherit_from_base(self):
        """Test all custom exceptions inherit from RedditAPIError."""
        exceptions = [
            AuthenticationError(),
            RateLimitError(retry_after=10),
            NotFoundError(resource_type="post", resource_id="123"),
            PermissionError(),
            ServerError("Error"),
            ValidationError("Error"),
            TimeoutError(),
        ]

        for exc in exceptions:
            assert isinstance(exc, RedditAPIError)
            assert isinstance(exc, Exception)

    def test_exception_catching(self):
        """Test catching exceptions by base class."""
        def raise_auth_error():
            raise AuthenticationError("Test")

        with pytest.raises(RedditAPIError):
            raise_auth_error()

        with pytest.raises(Exception):
            raise_auth_error()

    def test_exception_status_codes(self):
        """Test all exceptions have appropriate status codes."""
        status_codes = {
            AuthenticationError(): 401,
            RateLimitError(retry_after=10): 429,
            NotFoundError(resource_type="post", resource_id="123"): 404,
            PermissionError(): 403,
            ServerError("Error"): 500,
            ValidationError("Error"): 422,
            TimeoutError(): 408,
        }

        for exc, expected_code in status_codes.items():
            assert exc.status_code == expected_code
