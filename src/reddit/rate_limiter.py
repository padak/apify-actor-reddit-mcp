"""
Token Bucket Rate Limiter for Reddit API.

Implements a token bucket algorithm to ensure we never exceed Reddit's
100 requests per 60 seconds limit (free tier).
"""

import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter for Reddit API requests.

    Implements a sliding window approach using a deque to track call timestamps.
    Ensures we never exceed max_calls within period_seconds window.

    Thread-safe using asyncio.Lock.
    """

    def __init__(self, max_calls: int = 100, period_seconds: int = 60) -> None:
        """
        Initialize the rate limiter.

        Args:
            max_calls: Maximum number of calls allowed in the time period (default: 100)
            period_seconds: Time period in seconds (default: 60)
        """
        self.max_calls = max_calls
        self.period = timedelta(seconds=period_seconds)
        self.period_seconds = period_seconds
        self.calls: deque[datetime] = deque()  # Store timestamps of API calls
        self.lock = asyncio.Lock()

        logger.info(
            "rate_limiter_initialized",
            max_calls=max_calls,
            period_seconds=period_seconds
        )

    async def acquire(self, priority: int = 0) -> bool:
        """
        Acquire permission to make an API call.

        Blocks (waits) if rate limit is currently exceeded, then grants permission.
        Implements a sliding window algorithm.

        Args:
            priority: Request priority (0=normal, 1=high, -1=low).
                     Currently for future use - all priorities are treated equally in MVP.

        Returns:
            True when permission is granted (always returns True, waits if needed)

        Example:
            >>> rate_limiter = TokenBucketRateLimiter(max_calls=100, period_seconds=60)
            >>> await rate_limiter.acquire()  # Returns immediately if capacity available
            True
            >>> # After 100 calls in 60 seconds:
            >>> await rate_limiter.acquire()  # Waits until oldest call expires
            True
        """
        async with self.lock:
            now = datetime.utcnow()

            # Remove calls outside the sliding window
            while self.calls and now - self.calls[0] > self.period:
                self.calls.popleft()

            # Check if we have capacity
            if len(self.calls) < self.max_calls:
                self.calls.append(now)
                remaining = self.max_calls - len(self.calls)

                logger.debug(
                    "rate_limit_acquired",
                    calls_made=len(self.calls),
                    remaining=remaining,
                    priority=priority
                )

                # Log warning when approaching limit (>90% used)
                if len(self.calls) > (self.max_calls * 0.9):
                    logger.warning(
                        "rate_limit_approaching",
                        calls_made=len(self.calls),
                        max_calls=self.max_calls,
                        remaining=remaining
                    )

                return True

            # Rate limit exceeded - calculate wait time
            oldest_call = self.calls[0]
            wait_until = oldest_call + self.period
            wait_time = (wait_until - now).total_seconds()

            # Add small buffer to avoid edge cases
            wait_time_buffered = wait_time + 0.1

            logger.warning(
                "rate_limit_hit",
                calls_made=len(self.calls),
                max_calls=self.max_calls,
                wait_seconds=round(wait_time_buffered, 2),
                oldest_call=oldest_call.isoformat(),
                priority=priority
            )

        # Release lock while waiting to allow other operations
        await asyncio.sleep(wait_time_buffered)

        # Recursively retry after waiting
        return await self.acquire(priority)

    def get_remaining(self) -> int:
        """
        Get the number of available calls in the current window.

        This is a synchronous method for quick status checks.
        For accurate results during concurrent operations, consider the race condition
        between checking and acquiring.

        Returns:
            Number of calls available before hitting rate limit

        Example:
            >>> rate_limiter = TokenBucketRateLimiter(max_calls=100, period_seconds=60)
            >>> rate_limiter.get_remaining()
            100
            >>> await rate_limiter.acquire()
            >>> rate_limiter.get_remaining()
            99
        """
        now = datetime.utcnow()

        # Count valid calls within the current window
        valid_calls = [c for c in self.calls if now - c <= self.period]
        remaining = self.max_calls - len(valid_calls)

        return max(0, remaining)  # Never return negative

    async def reset(self) -> None:
        """
        Reset the rate limiter state.

        Useful for testing or manual intervention.
        """
        async with self.lock:
            self.calls.clear()
            logger.info("rate_limiter_reset")

    def get_stats(self) -> dict[str, any]:
        """
        Get current rate limiter statistics.

        Returns:
            Dictionary with current stats including calls made, remaining capacity,
            window size, and oldest call timestamp.

        Example:
            >>> stats = rate_limiter.get_stats()
            >>> print(stats)
            {
                'calls_made': 45,
                'remaining': 55,
                'max_calls': 100,
                'period_seconds': 60,
                'oldest_call': '2025-11-05T12:34:56.789012',
                'utilization_percent': 45.0
            }
        """
        now = datetime.utcnow()
        valid_calls = [c for c in self.calls if now - c <= self.period]
        calls_made = len(valid_calls)
        remaining = self.max_calls - calls_made

        oldest_call: Optional[str] = None
        if valid_calls:
            oldest_call = min(valid_calls).isoformat()

        utilization = (calls_made / self.max_calls * 100) if self.max_calls > 0 else 0

        return {
            "calls_made": calls_made,
            "remaining": remaining,
            "max_calls": self.max_calls,
            "period_seconds": self.period_seconds,
            "oldest_call": oldest_call,
            "utilization_percent": round(utilization, 2)
        }
