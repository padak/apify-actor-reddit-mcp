"""
Structured logging configuration using structlog.

Provides JSON-formatted logging with context processors for
request tracking, timestamps, and log levels.

Story: MVP-005 (FastMCP Server Foundation)
"""
import logging
import os
import sys
from typing import Any

import structlog


def setup_logging(level: str = "INFO") -> None:
    """
    Configure structured logging with structlog.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Sets up:
        - JSON output format for production
        - Console output with colors for development
        - Context processors for timestamps and metadata
        - Integration with standard library logging
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Determine if we're in development mode
    is_dev = os.getenv("ENVIRONMENT", "production") == "development"

    # Configure structlog processors
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    if is_dev:
        # Development: Human-readable console output with colors
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        # Production: JSON output
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (typically __name__ of calling module)

    Returns:
        Configured structlog logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("tool_request", tool="search_reddit", params={"query": "test"})
    """
    return structlog.get_logger(name)


def log_tool_execution(
    tool_name: str,
    duration_ms: float,
    cached: bool,
    error: str | None = None,
    **extra: Any,
) -> None:
    """
    Log tool execution metrics in structured format.

    Args:
        tool_name: Name of the MCP tool executed
        duration_ms: Execution time in milliseconds
        cached: Whether result was served from cache
        error: Error message if execution failed
        **extra: Additional context to log

    Example:
        >>> log_tool_execution(
        ...     tool_name="search_reddit",
        ...     duration_ms=1234.5,
        ...     cached=False,
        ...     result_count=25
        ... )
    """
    logger = get_logger("tool_execution")

    log_data = {
        "event": "tool_execution",
        "tool": tool_name,
        "duration_ms": round(duration_ms, 2),
        "cached": cached,
        "error": error,
        **extra,
    }

    if error:
        logger.error("tool_execution_failed", **log_data)
    else:
        logger.info("tool_execution_success", **log_data)
