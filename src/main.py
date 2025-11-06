"""
Reddit MCP Server - Main Entry Point

Initializes and runs the FastMCP server with Redis caching
and Reddit API integration.

Story: MVP-005 (FastMCP Server Foundation)
"""
import asyncio
import os
import signal
import sys

from apify import Actor

from src.server import create_mcp_server
from src.utils.logger import get_logger, setup_logging

# Initialize logger (will be reconfigured in main())
logger = get_logger(__name__)


async def main() -> None:
    """
    Main entry point for Apify Actor.

    Initializes:
        1. Structured logging
        2. FastMCP server
        3. TODO MVP-002: Redis caching layer
        4. TODO MVP-003: Reddit API client
        5. TODO MVP-004: Rate limiter

    Runs in Apify Actor context for standby mode support.
    """
    # Setup structured logging
    log_level = os.getenv("LOG_LEVEL", "INFO")
    setup_logging(level=log_level)

    logger.info(
        "server_starting",
        version="1.0.0",
        environment=os.getenv("ENVIRONMENT", "production"),
        log_level=log_level,
    )

    async with Actor:
        # Create MCP server
        server = create_mcp_server()

        logger.info(
            "mcp_server_created",
            name=server.name,
            version=server.version,
        )

        # TODO MVP-002: Initialize Redis cache
        # from src.cache.manager import CacheManager
        # cache = CacheManager()
        # await cache.connect()

        # TODO MVP-003: Initialize Reddit API client
        # from src.reddit.client import RedditClientManager
        # reddit_client = RedditClientManager()

        # TODO MVP-004: Initialize rate limiter
        # from src.reddit.rate_limiter import TokenBucketRateLimiter
        # rate_limiter = TokenBucketRateLimiter(max_calls=100, period_seconds=60)

        # Register graceful shutdown
        def signal_handler(sig: int, frame: any) -> None:
            """Handle shutdown signals gracefully."""
            logger.info("shutdown_signal_received", signal=sig)
            # TODO: Add cleanup logic (close Redis, etc.)
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Run FastMCP server
        # For Apify standby mode, server runs on stdio or HTTP
        transport = os.getenv("MCP_TRANSPORT", "stdio")

        logger.info(
            "starting_mcp_server",
            transport=transport,
            standby_mode=os.getenv("APIFY_IS_AT_HOME", "false") == "true",
        )

        try:
            # Run server (blocks until shutdown)
            await server.run(transport=transport)
        except Exception as e:
            logger.error(
                "server_error",
                error=str(e),
                exc_info=True,
            )
            raise
        finally:
            logger.info("server_shutdown_complete")


if __name__ == "__main__":
    asyncio.run(main())
