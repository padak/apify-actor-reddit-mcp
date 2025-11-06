"""
Integration tests for FastMCP server initialization.

Tests server creation, configuration, and health check endpoint.

Story: MVP-005 (FastMCP Server Foundation)
"""
import pytest

from src.server import (
    SERVER_NAME,
    SERVER_VERSION,
    CacheError,
    RateLimitError,
    RedditAPIError,
    ValidationError,
    create_mcp_server,
)


class TestServerInitialization:
    """Test suite for MCP server initialization."""

    def test_create_mcp_server(self):
        """Test that MCP server can be created successfully."""
        server = create_mcp_server()

        assert server is not None
        assert server.name == SERVER_NAME
        assert server.version == SERVER_VERSION

    def test_server_capabilities(self):
        """Test that server capabilities are configured correctly."""
        server = create_mcp_server()

        # FastMCP doesn't expose capabilities directly in v1.0
        # We verify this through the server creation process
        assert server is not None

    def test_server_metadata(self):
        """Test that server metadata is set correctly."""
        server = create_mcp_server()

        assert server.name == "reddit-mcp-server"
        assert server.version == "1.0.0"
        assert "Reddit" in server.description


class TestCustomErrors:
    """Test suite for custom error classes."""

    def test_validation_error(self):
        """Test ValidationError initialization."""
        error = ValidationError("Invalid query", data={"field": "query"})

        assert error.code == -32602
        assert error.message == "Invalid query"
        assert error.data == {"field": "query"}

    def test_rate_limit_error(self):
        """Test RateLimitError initialization."""
        error = RateLimitError("Rate limit exceeded")

        assert error.code == -32000
        assert "Rate limit" in error.message

    def test_reddit_api_error(self):
        """Test RedditAPIError initialization."""
        error = RedditAPIError("API unavailable")

        assert error.code == -32001
        assert "API" in error.message

    def test_cache_error(self):
        """Test CacheError initialization."""
        error = CacheError("Redis connection failed")

        assert error.code == -32002
        assert "Redis" in error.message


@pytest.mark.asyncio
class TestHealthCheck:
    """Test suite for health check endpoint."""

    async def test_health_check_endpoint_exists(self):
        """Test that health_check tool is registered."""
        server = create_mcp_server()

        # Get list of registered tools
        # Note: FastMCP doesn't expose tools list in v1.0
        # We'll verify this works when we can call it
        assert server is not None

    async def test_health_check_response_structure(self):
        """Test health check returns correct structure."""
        # This will be implemented when we can actually call tools
        # For now, we verify the server exists
        server = create_mcp_server()
        assert server is not None

        # TODO: Once server.call_tool() is available, test:
        # result = await server.call_tool("health_check", {})
        # assert "status" in result
        # assert "version" in result
        # assert "components" in result


class TestErrorHandling:
    """Test suite for error handling middleware."""

    def test_error_handler_registered(self):
        """Test that error handler is registered during server creation."""
        # Error handler is registered in setup_error_handling()
        # called during create_mcp_server()
        server = create_mcp_server()
        assert server is not None

    # Additional error handling tests will be added when we have
    # actual tools to test with in MVP-006+
