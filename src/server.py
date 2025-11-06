"""
FastMCP Server initialization and configuration.

Sets up the MCP server with metadata, capabilities, error handling,
and monitoring hooks.

Story: MVP-005 (FastMCP Server Foundation)
"""
import os
import traceback
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import MCPError

from src.models.responses import ErrorResponse, HealthCheckResponse
from src.utils.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

# Server metadata
SERVER_NAME = "reddit-mcp-server"
SERVER_VERSION = "1.0.0"
SERVER_DESCRIPTION = "Enterprise Reddit MCP Server with caching and sentiment analysis"


# Custom error classes
class RedditMCPError(MCPError):
    """Base error for Reddit MCP server."""

    pass


class ValidationError(RedditMCPError):
    """Input validation failed."""

    def __init__(self, message: str, data: dict[str, Any] | None = None):
        super().__init__(code=-32602, message=message, data=data)


class RateLimitError(RedditMCPError):
    """Rate limit exceeded."""

    def __init__(self, message: str, data: dict[str, Any] | None = None):
        super().__init__(code=-32000, message=message, data=data)


class RedditAPIError(RedditMCPError):
    """Reddit API error."""

    def __init__(self, message: str, data: dict[str, Any] | None = None):
        super().__init__(code=-32001, message=message, data=data)


class CacheError(RedditMCPError):
    """Redis cache error."""

    def __init__(self, message: str, data: dict[str, Any] | None = None):
        super().__init__(code=-32002, message=message, data=data)


def create_mcp_server() -> FastMCP:
    """
    Create and configure the FastMCP server instance.

    Returns:
        Configured FastMCP server with capabilities and error handling

    Example:
        >>> server = create_mcp_server()
        >>> # Register tools here
        >>> await server.run()
    """
    # Initialize FastMCP server
    mcp = FastMCP(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        description=SERVER_DESCRIPTION,
    )

    # Configure capabilities (tools only for MVP)
    mcp.configure(
        capabilities={
            "tools": {},  # Tools will be registered via decorators
            "resources": {"subscribe": False},  # Future: real-time updates
            "prompts": {},  # Future: prompt templates
        }
    )

    logger.info(
        "mcp_server_initialized",
        name=SERVER_NAME,
        version=SERVER_VERSION,
        capabilities=["tools"],
    )

    # Register error handler middleware
    setup_error_handling(mcp)

    # Register health check endpoint (for Apify standby mode)
    register_health_check(mcp)

    return mcp


def setup_error_handling(mcp: FastMCP) -> None:
    """
    Configure error handling middleware for the MCP server.

    Catches and transforms exceptions into proper JSON-RPC error responses.

    Args:
        mcp: FastMCP server instance to configure
    """

    @mcp.error_handler
    async def handle_errors(error: Exception) -> ErrorResponse:
        """
        Global error handler for all tool executions.

        Args:
            error: Exception raised during tool execution

        Returns:
            ErrorResponse with appropriate code and message

        Error Codes:
            -32602: Invalid parameters (ValidationError)
            -32000: Rate limit exceeded (RateLimitError)
            -32001: Reddit API error (RedditAPIError)
            -32002: Cache error (CacheError)
            -32603: Internal server error (unexpected)
        """
        # Log error with context
        logger.error(
            "error_handler_triggered",
            error_type=type(error).__name__,
            error_message=str(error),
            exc_info=True,
        )

        # Handle known error types
        if isinstance(error, ValidationError):
            logger.warning("validation_error", message=str(error))
            return ErrorResponse(
                code=-32602,
                message="Invalid parameters",
                data={"reason": str(error)},
            )

        if isinstance(error, RateLimitError):
            logger.warning("rate_limit_error", message=str(error))
            return ErrorResponse(
                code=-32000,
                message="Rate limit exceeded",
                data={
                    "reason": str(error),
                    "retry_after_seconds": 60,
                },
            )

        if isinstance(error, RedditAPIError):
            logger.error("reddit_api_error", message=str(error))
            return ErrorResponse(
                code=-32001,
                message="Reddit API error",
                data={"reason": str(error)},
            )

        if isinstance(error, CacheError):
            logger.warning("cache_error", message=str(error))
            return ErrorResponse(
                code=-32002,
                message="Cache error (continuing without cache)",
                data={"reason": str(error)},
            )

        # Handle unexpected errors
        logger.error(
            "unexpected_error",
            error_type=type(error).__name__,
            error_message=str(error),
            traceback=traceback.format_exc(),
        )

        return ErrorResponse(
            code=-32603,
            message="Internal server error",
            data={
                "error_type": type(error).__name__,
                "environment": os.getenv("ENVIRONMENT", "production"),
            },
        )


def register_health_check(mcp: FastMCP) -> None:
    """
    Register health check endpoint for Apify standby mode.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool()
    async def health_check() -> dict[str, Any]:
        """
        Health check endpoint for monitoring.

        Returns server health status and component availability.

        Returns:
            Dictionary with status, version, and component health
        """
        # Check components (placeholder for now)
        # TODO MVP-002: Check Redis connection
        # TODO MVP-003: Check Reddit API client
        # TODO MVP-004: Check rate limiter state

        components = {
            "server": "healthy",
            "redis": "unknown",  # Will be implemented in MVP-002
            "reddit_api": "unknown",  # Will be implemented in MVP-003
            "rate_limiter": "unknown",  # Will be implemented in MVP-004
        }

        # Determine overall status
        if all(status == "healthy" for status in components.values()):
            overall_status = "healthy"
        elif any(status == "unhealthy" for status in components.values()):
            overall_status = "unhealthy"
        else:
            overall_status = "degraded"

        response = HealthCheckResponse(
            status=overall_status,
            version=SERVER_VERSION,
            components=components,
        )

        logger.debug("health_check_performed", status=overall_status)

        return response.dict()


# Create global MCP server instance (singleton)
mcp = create_mcp_server()
