"""
Unit tests for Reddit client manager.

Tests the RedditClientManager singleton and client initialization.
"""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock

import praw
from praw.exceptions import InvalidToken, RequestException

from src.reddit.client import (
    RedditClientManager,
    reddit_client_manager,
    get_reddit_client,
)
from src.reddit.exceptions import (
    AuthenticationError,
    RedditAPIError,
)


class TestRedditClientManager:
    """Test RedditClientManager class."""

    def setup_method(self):
        """Reset singleton before each test."""
        # Reset singleton state
        RedditClientManager._instance = None
        RedditClientManager._client = None
        RedditClientManager._initialized = False

    def test_singleton_pattern(self):
        """Test that RedditClientManager is a singleton."""
        manager1 = RedditClientManager()
        manager2 = RedditClientManager()

        assert manager1 is manager2
        assert id(manager1) == id(manager2)

    @patch.dict(os.environ, {
        "REDDIT_CLIENT_ID": "test_client_id",
        "REDDIT_CLIENT_SECRET": "test_client_secret",
        "REDDIT_USER_AGENT": "test_agent"
    })
    @patch('praw.Reddit')
    def test_initialization_with_valid_credentials(self, mock_reddit):
        """Test successful initialization with valid credentials."""
        # Mock the Reddit client
        mock_client = MagicMock()
        mock_client.read_only = True
        mock_subreddit = MagicMock()
        mock_subreddit.display_name = "all"
        mock_client.subreddit.return_value = mock_subreddit
        mock_reddit.return_value = mock_client

        manager = RedditClientManager()

        assert manager.is_initialized()
        mock_reddit.assert_called_once()

        # Verify client configuration
        call_kwargs = mock_reddit.call_args[1]
        assert call_kwargs['client_id'] == "test_client_id"
        assert call_kwargs['client_secret'] == "test_client_secret"
        assert call_kwargs['user_agent'] == "test_agent"

    @patch.dict(os.environ, {}, clear=True)
    def test_initialization_missing_client_id(self):
        """Test initialization fails without client_id."""
        with pytest.raises(AuthenticationError) as exc_info:
            RedditClientManager()

        assert "REDDIT_CLIENT_ID" in str(exc_info.value)

    @patch.dict(os.environ, {"REDDIT_CLIENT_ID": "test_id"}, clear=True)
    def test_initialization_missing_client_secret(self):
        """Test initialization fails without client_secret."""
        with pytest.raises(AuthenticationError) as exc_info:
            RedditClientManager()

        assert "REDDIT_CLIENT_SECRET" in str(exc_info.value)

    @patch.dict(os.environ, {
        "REDDIT_CLIENT_ID": "test_id",
        "REDDIT_CLIENT_SECRET": "test_secret"
    })
    @patch('praw.Reddit')
    def test_default_user_agent(self, mock_reddit):
        """Test default user agent is set."""
        mock_client = MagicMock()
        mock_subreddit = MagicMock()
        mock_subreddit.display_name = "all"
        mock_client.subreddit.return_value = mock_subreddit
        mock_reddit.return_value = mock_client

        manager = RedditClientManager()

        call_kwargs = mock_reddit.call_args[1]
        assert "Reddit-MCP-Server" in call_kwargs['user_agent']

    @patch.dict(os.environ, {
        "REDDIT_CLIENT_ID": "test_id",
        "REDDIT_CLIENT_SECRET": "test_secret"
    })
    @patch('praw.Reddit')
    def test_invalid_token_raises_authentication_error(self, mock_reddit):
        """Test that invalid token raises AuthenticationError."""
        mock_reddit.side_effect = InvalidToken("Invalid token")

        with pytest.raises(AuthenticationError) as exc_info:
            RedditClientManager()

        assert "Invalid" in str(exc_info.value)

    @patch.dict(os.environ, {
        "REDDIT_CLIENT_ID": "test_id",
        "REDDIT_CLIENT_SECRET": "test_secret"
    })
    @patch('praw.Reddit')
    def test_request_exception_raises_api_error(self, mock_reddit):
        """Test that request exception raises RedditAPIError."""
        mock_reddit.side_effect = RequestException("Connection failed")

        with pytest.raises(RedditAPIError) as exc_info:
            RedditClientManager()

        assert "connect" in str(exc_info.value).lower()

    @patch.dict(os.environ, {
        "REDDIT_CLIENT_ID": "test_id",
        "REDDIT_CLIENT_SECRET": "test_secret"
    })
    @patch('praw.Reddit')
    def test_get_client_returns_instance(self, mock_reddit):
        """Test get_client returns PRAW instance."""
        mock_client = MagicMock()
        mock_subreddit = MagicMock()
        mock_subreddit.display_name = "all"
        mock_client.subreddit.return_value = mock_subreddit
        mock_reddit.return_value = mock_client

        manager = RedditClientManager()
        client = manager.get_client()

        assert client is not None
        assert client == mock_client

    @patch.dict(os.environ, {
        "REDDIT_CLIENT_ID": "test_id",
        "REDDIT_CLIENT_SECRET": "test_secret"
    })
    @patch('praw.Reddit')
    def test_get_client_returns_same_instance(self, mock_reddit):
        """Test get_client always returns same instance."""
        mock_client = MagicMock()
        mock_subreddit = MagicMock()
        mock_subreddit.display_name = "all"
        mock_client.subreddit.return_value = mock_subreddit
        mock_reddit.return_value = mock_client

        manager = RedditClientManager()
        client1 = manager.get_client()
        client2 = manager.get_client()

        assert client1 is client2

    @patch.dict(os.environ, {
        "REDDIT_CLIENT_ID": "test_id",
        "REDDIT_CLIENT_SECRET": "test_secret"
    })
    @patch('praw.Reddit')
    def test_reset_client(self, mock_reddit):
        """Test reset_client clears state."""
        mock_client = MagicMock()
        mock_subreddit = MagicMock()
        mock_subreddit.display_name = "all"
        mock_client.subreddit.return_value = mock_subreddit
        mock_reddit.return_value = mock_client

        manager = RedditClientManager()
        assert manager.is_initialized()

        manager.reset_client()

        assert not manager.is_initialized()
        assert manager._client is None

    @patch.dict(os.environ, {
        "REDDIT_CLIENT_ID": "test_id",
        "REDDIT_CLIENT_SECRET": "test_secret"
    })
    @patch('praw.Reddit')
    def test_client_property(self, mock_reddit):
        """Test client property accessor."""
        mock_client = MagicMock()
        mock_subreddit = MagicMock()
        mock_subreddit.display_name = "all"
        mock_client.subreddit.return_value = mock_subreddit
        mock_reddit.return_value = mock_client

        manager = RedditClientManager()
        client_via_method = manager.get_client()
        client_via_property = manager.client

        assert client_via_method is client_via_property

    @patch.dict(os.environ, {
        "REDDIT_CLIENT_ID": "test_id",
        "REDDIT_CLIENT_SECRET": "test_secret"
    })
    @patch('praw.Reddit')
    def test_read_only_mode_enabled(self, mock_reddit):
        """Test that client is configured in read-only mode."""
        mock_client = MagicMock()
        mock_subreddit = MagicMock()
        mock_subreddit.display_name = "all"
        mock_client.subreddit.return_value = mock_subreddit
        mock_reddit.return_value = mock_client

        manager = RedditClientManager()

        # Verify read_only is set to True
        assert mock_client.read_only is True

    @patch.dict(os.environ, {
        "REDDIT_CLIENT_ID": "test_id",
        "REDDIT_CLIENT_SECRET": "test_secret"
    })
    @patch('praw.Reddit')
    def test_timeout_configuration(self, mock_reddit):
        """Test that timeout is configured."""
        mock_client = MagicMock()
        mock_config = MagicMock()
        mock_client.config = mock_config
        mock_subreddit = MagicMock()
        mock_subreddit.display_name = "all"
        mock_client.subreddit.return_value = mock_subreddit
        mock_reddit.return_value = mock_client

        manager = RedditClientManager()

        # Verify timeout is set
        assert mock_config.timeout == 30


class TestModuleLevelFunctions:
    """Test module-level convenience functions."""

    def setup_method(self):
        """Reset singleton before each test."""
        RedditClientManager._instance = None
        RedditClientManager._client = None
        RedditClientManager._initialized = False

    @patch.dict(os.environ, {
        "REDDIT_CLIENT_ID": "test_id",
        "REDDIT_CLIENT_SECRET": "test_secret"
    })
    @patch('praw.Reddit')
    def test_get_reddit_client_function(self, mock_reddit):
        """Test get_reddit_client convenience function."""
        mock_client = MagicMock()
        mock_subreddit = MagicMock()
        mock_subreddit.display_name = "all"
        mock_client.subreddit.return_value = mock_subreddit
        mock_reddit.return_value = mock_client

        client = get_reddit_client()

        assert client is not None
        assert client == mock_client

    @patch.dict(os.environ, {
        "REDDIT_CLIENT_ID": "test_id",
        "REDDIT_CLIENT_SECRET": "test_secret"
    })
    @patch('praw.Reddit')
    def test_reddit_client_manager_singleton(self, mock_reddit):
        """Test module-level reddit_client_manager singleton."""
        mock_client = MagicMock()
        mock_subreddit = MagicMock()
        mock_subreddit.display_name = "all"
        mock_client.subreddit.return_value = mock_subreddit
        mock_reddit.return_value = mock_client

        # Import should create singleton
        from src.reddit.client import reddit_client_manager as manager

        assert manager is not None
        assert isinstance(manager, RedditClientManager)


class TestCredentialValidation:
    """Test credential validation logic."""

    def setup_method(self):
        """Reset singleton before each test."""
        RedditClientManager._instance = None
        RedditClientManager._client = None
        RedditClientManager._initialized = False

    @patch.dict(os.environ, {
        "REDDIT_CLIENT_ID": "test_id",
        "REDDIT_CLIENT_SECRET": "test_secret"
    })
    @patch('praw.Reddit')
    def test_validation_success(self, mock_reddit):
        """Test successful credential validation."""
        mock_client = MagicMock()
        mock_subreddit = MagicMock()
        mock_subreddit.display_name = "all"
        mock_client.subreddit.return_value = mock_subreddit
        mock_reddit.return_value = mock_client

        manager = RedditClientManager()

        # Should not raise exception
        assert manager.is_initialized()

    @patch.dict(os.environ, {
        "REDDIT_CLIENT_ID": "test_id",
        "REDDIT_CLIENT_SECRET": "test_secret"
    })
    @patch('praw.Reddit')
    def test_validation_invalid_token(self, mock_reddit):
        """Test validation with invalid token."""
        mock_client = MagicMock()
        mock_client.subreddit.side_effect = InvalidToken("Invalid")
        mock_reddit.return_value = mock_client

        with pytest.raises(AuthenticationError):
            RedditClientManager()
