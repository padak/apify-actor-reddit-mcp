"""
Pydantic response models for MCP tools.

Defines standardized response structures for all tools including
metadata, error responses, and tool-specific outputs.

Story: MVP-005 (FastMCP Server Foundation)
"""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


class ResponseMetadata(BaseModel):
    """
    Metadata included in all tool responses.

    Provides information about caching, rate limits, and execution metrics.
    """

    cached: bool = Field(
        ...,
        description="Whether result was served from cache",
    )
    cache_age_seconds: int = Field(
        0,
        ge=0,
        description="Age of cached data in seconds (0 if not cached)",
    )
    ttl: int = Field(
        0,
        ge=0,
        description="Cache TTL in seconds",
    )
    rate_limit_remaining: int = Field(
        ...,
        ge=0,
        description="Remaining Reddit API calls in current window",
    )
    execution_time_ms: float = Field(
        ...,
        ge=0,
        description="Tool execution time in milliseconds",
    )
    reddit_api_calls: int = Field(
        0,
        ge=0,
        description="Number of Reddit API calls made",
    )

    class Config:
        schema_extra = {
            "example": {
                "cached": True,
                "cache_age_seconds": 120,
                "ttl": 300,
                "rate_limit_remaining": 87,
                "execution_time_ms": 45.2,
                "reddit_api_calls": 0,
            }
        }


# Generic type for tool result data
T = TypeVar("T")


class ToolResponse(BaseModel, Generic[T]):
    """
    Generic response wrapper for all MCP tools.

    Wraps tool-specific data with standard metadata.

    Type Parameters:
        T: Type of the data field (tool-specific)

    Example:
        >>> response = ToolResponse(
        ...     data={"results": [...]},
        ...     metadata=ResponseMetadata(
        ...         cached=False,
        ...         rate_limit_remaining=95,
        ...         execution_time_ms=1234.5
        ...     )
        ... )
    """

    data: T = Field(
        ...,
        description="Tool-specific result data",
    )
    metadata: ResponseMetadata = Field(
        ...,
        description="Response metadata (caching, rate limits, etc.)",
    )

    class Config:
        schema_extra = {
            "example": {
                "data": {
                    "results": [
                        {
                            "id": "abc123",
                            "title": "Example post",
                            "score": 1234,
                        }
                    ]
                },
                "metadata": {
                    "cached": False,
                    "cache_age_seconds": 0,
                    "ttl": 300,
                    "rate_limit_remaining": 95,
                    "execution_time_ms": 1234.5,
                    "reddit_api_calls": 1,
                },
            }
        }


class ErrorResponse(BaseModel):
    """
    Standardized error response structure.

    Used for JSON-RPC error responses following MCP protocol.

    Attributes:
        code: JSON-RPC error code
        message: Human-readable error message
        data: Optional additional error context
    """

    code: int = Field(
        ...,
        description="JSON-RPC error code",
    )
    message: str = Field(
        ...,
        min_length=1,
        description="Human-readable error message",
    )
    data: dict[str, Any] | None = Field(
        None,
        description="Additional error context",
    )

    class Config:
        schema_extra = {
            "example": {
                "code": -32602,
                "message": "Invalid parameters",
                "data": {
                    "field": "query",
                    "reason": "Query length must be between 1 and 500 characters",
                },
            }
        }


class HealthCheckResponse(BaseModel):
    """
    Health check response for Apify standby mode.

    Used to verify server is running and components are healthy.
    """

    status: str = Field(
        ...,
        description="Overall health status (healthy, degraded, unhealthy)",
    )
    version: str = Field(
        ...,
        description="Server version",
    )
    components: dict[str, str] = Field(
        ...,
        description="Health status of individual components",
    )

    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "components": {
                    "redis": "healthy",
                    "reddit_api": "healthy",
                    "rate_limiter": "healthy",
                },
            }
        }
