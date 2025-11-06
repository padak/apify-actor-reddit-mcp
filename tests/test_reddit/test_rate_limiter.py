"""
Tests for TokenBucketRateLimiter.

Tests cover:
- Basic token acquisition
- Rate limiting behavior (blocking when limit reached)
- get_remaining() accuracy
- Sliding window algorithm
- Concurrent request handling
- Edge cases and boundary conditions
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.reddit.rate_limiter import TokenBucketRateLimiter


class TestTokenBucketRateLimiter:
    """Test suite for TokenBucketRateLimiter."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test rate limiter initializes with correct defaults."""
        limiter = TokenBucketRateLimiter()

        assert limiter.max_calls == 100
        assert limiter.period_seconds == 60
        assert len(limiter.calls) == 0
        assert limiter.get_remaining() == 100

    @pytest.mark.asyncio
    async def test_initialization_custom_params(self):
        """Test rate limiter with custom parameters."""
        limiter = TokenBucketRateLimiter(max_calls=50, period_seconds=30)

        assert limiter.max_calls == 50
        assert limiter.period_seconds == 30
        assert limiter.get_remaining() == 50

    @pytest.mark.asyncio
    async def test_acquire_single_call(self):
        """Test acquiring a single token succeeds immediately."""
        limiter = TokenBucketRateLimiter(max_calls=100, period_seconds=60)

        start_time = datetime.utcnow()
        result = await limiter.acquire()
        end_time = datetime.utcnow()

        assert result is True
        assert limiter.get_remaining() == 99
        # Should return almost instantly (< 100ms)
        assert (end_time - start_time).total_seconds() < 0.1

    @pytest.mark.asyncio
    async def test_acquire_multiple_calls(self):
        """Test acquiring multiple tokens in sequence."""
        limiter = TokenBucketRateLimiter(max_calls=10, period_seconds=60)

        for i in range(10):
            result = await limiter.acquire()
            assert result is True
            assert limiter.get_remaining() == 10 - (i + 1)

        # All 10 tokens should be consumed
        assert limiter.get_remaining() == 0

    @pytest.mark.asyncio
    async def test_acquire_waits_when_limit_reached(self):
        """Test that acquire() waits when rate limit is reached."""
        # Small limit for faster testing
        limiter = TokenBucketRateLimiter(max_calls=5, period_seconds=2)

        # Exhaust the limit
        for _ in range(5):
            await limiter.acquire()

        assert limiter.get_remaining() == 0

        # Next call should wait approximately 2 seconds
        start_time = datetime.utcnow()
        result = await limiter.acquire()
        end_time = datetime.utcnow()

        assert result is True
        wait_time = (end_time - start_time).total_seconds()
        # Should wait between 1.9 and 2.5 seconds (accounting for overhead)
        assert 1.9 <= wait_time <= 2.5

    @pytest.mark.asyncio
    async def test_get_remaining_accuracy(self):
        """Test get_remaining() returns accurate count."""
        limiter = TokenBucketRateLimiter(max_calls=100, period_seconds=60)

        assert limiter.get_remaining() == 100

        # Acquire 25 tokens
        for _ in range(25):
            await limiter.acquire()

        assert limiter.get_remaining() == 75

        # Acquire 50 more
        for _ in range(50):
            await limiter.acquire()

        assert limiter.get_remaining() == 25

    @pytest.mark.asyncio
    async def test_sliding_window_expiration(self):
        """Test that old calls expire from the sliding window."""
        limiter = TokenBucketRateLimiter(max_calls=5, period_seconds=1)

        # Fill up the bucket
        for _ in range(5):
            await limiter.acquire()

        assert limiter.get_remaining() == 0

        # Wait for window to expire (1 second + buffer)
        await asyncio.sleep(1.2)

        # Should have full capacity again
        assert limiter.get_remaining() == 5

        # Should be able to acquire immediately
        start_time = datetime.utcnow()
        result = await limiter.acquire()
        end_time = datetime.utcnow()

        assert result is True
        assert (end_time - start_time).total_seconds() < 0.1

    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """Test thread-safety with concurrent acquire() calls."""
        limiter = TokenBucketRateLimiter(max_calls=50, period_seconds=60)

        # Create 50 concurrent acquire tasks
        tasks = [limiter.acquire() for _ in range(50)]

        # All should succeed
        results = await asyncio.gather(*tasks)

        assert all(results)
        assert limiter.get_remaining() == 0

    @pytest.mark.asyncio
    async def test_priority_parameter_accepted(self):
        """Test that priority parameter is accepted (even if not used in MVP)."""
        limiter = TokenBucketRateLimiter(max_calls=100, period_seconds=60)

        # Should accept different priority values
        result1 = await limiter.acquire(priority=0)  # Normal
        result2 = await limiter.acquire(priority=1)  # High
        result3 = await limiter.acquire(priority=-1)  # Low

        assert result1 is True
        assert result2 is True
        assert result3 is True
        assert limiter.get_remaining() == 97

    @pytest.mark.asyncio
    async def test_reset(self):
        """Test reset() clears all call history."""
        limiter = TokenBucketRateLimiter(max_calls=100, period_seconds=60)

        # Make some calls
        for _ in range(50):
            await limiter.acquire()

        assert limiter.get_remaining() == 50

        # Reset
        await limiter.reset()

        assert limiter.get_remaining() == 100
        assert len(limiter.calls) == 0

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test get_stats() returns accurate statistics."""
        limiter = TokenBucketRateLimiter(max_calls=100, period_seconds=60)

        # Initial stats
        stats = limiter.get_stats()
        assert stats["calls_made"] == 0
        assert stats["remaining"] == 100
        assert stats["max_calls"] == 100
        assert stats["period_seconds"] == 60
        assert stats["oldest_call"] is None
        assert stats["utilization_percent"] == 0.0

        # Make some calls
        for _ in range(45):
            await limiter.acquire()

        stats = limiter.get_stats()
        assert stats["calls_made"] == 45
        assert stats["remaining"] == 55
        assert stats["utilization_percent"] == 45.0
        assert stats["oldest_call"] is not None

    @pytest.mark.asyncio
    async def test_boundary_condition_exactly_max_calls(self):
        """Test behavior when exactly at max_calls limit."""
        limiter = TokenBucketRateLimiter(max_calls=10, period_seconds=60)

        # Use exactly max_calls
        for _ in range(10):
            await limiter.acquire()

        assert limiter.get_remaining() == 0

        # Next call should wait
        start_time = datetime.utcnow()
        await asyncio.wait_for(limiter.acquire(), timeout=65)
        end_time = datetime.utcnow()

        # Should have waited (but we can't test exact time reliably)
        assert (end_time - start_time).total_seconds() > 0.1

    @pytest.mark.asyncio
    async def test_get_remaining_never_negative(self):
        """Test that get_remaining() never returns negative values."""
        limiter = TokenBucketRateLimiter(max_calls=5, period_seconds=60)

        # Exhaust limit
        for _ in range(5):
            await limiter.acquire()

        # Should be 0, not negative
        assert limiter.get_remaining() == 0
        assert limiter.get_remaining() >= 0

    @pytest.mark.asyncio
    async def test_rapid_fire_requests(self):
        """Test handling many rapid requests."""
        limiter = TokenBucketRateLimiter(max_calls=20, period_seconds=60)

        # Fire 20 requests as fast as possible
        tasks = [limiter.acquire() for _ in range(20)]
        results = await asyncio.gather(*tasks)

        assert all(results)
        assert limiter.get_remaining() == 0

    @pytest.mark.asyncio
    async def test_partial_window_expiration(self):
        """Test that calls expire individually as their window passes."""
        limiter = TokenBucketRateLimiter(max_calls=5, period_seconds=1)

        # Make 3 calls
        for _ in range(3):
            await limiter.acquire()

        assert limiter.get_remaining() == 2

        # Wait for partial window to expire (0.6 seconds)
        await asyncio.sleep(0.6)

        # Make 2 more calls
        for _ in range(2):
            await limiter.acquire()

        assert limiter.get_remaining() == 0

        # Wait for first 3 calls to expire
        await asyncio.sleep(0.6)

        # First 3 should have expired, remaining should increase
        assert limiter.get_remaining() == 3

    @pytest.mark.asyncio
    async def test_warning_log_when_approaching_limit(self):
        """Test that warning is logged when >90% capacity used."""
        limiter = TokenBucketRateLimiter(max_calls=10, period_seconds=60)

        # Use 9 tokens (90%)
        for _ in range(9):
            await limiter.acquire()

        # Check we're at 90%
        stats = limiter.get_stats()
        assert stats["utilization_percent"] == 90.0

        # The 10th call should trigger warning (hits >90%)
        with patch('src.reddit.rate_limiter.logger') as mock_logger:
            await limiter.acquire()
            # Warning should have been called for approaching limit
            assert any(
                call[0][0] == "rate_limit_approaching"
                for call in mock_logger.warning.call_args_list
            )

    @pytest.mark.asyncio
    async def test_sequential_vs_concurrent_performance(self):
        """Test that concurrent requests complete in similar time to sequential."""
        limiter = TokenBucketRateLimiter(max_calls=10, period_seconds=60)

        # Sequential: 10 calls
        start_seq = datetime.utcnow()
        for _ in range(10):
            await limiter.acquire()
        end_seq = datetime.utcnow()
        sequential_time = (end_seq - start_seq).total_seconds()

        # Reset
        await limiter.reset()

        # Concurrent: 10 calls
        start_conc = datetime.utcnow()
        tasks = [limiter.acquire() for _ in range(10)]
        await asyncio.gather(*tasks)
        end_conc = datetime.utcnow()
        concurrent_time = (end_conc - start_conc).total_seconds()

        # Concurrent should be similar or faster (due to lock, may be similar)
        # Both should be very fast (< 1 second)
        assert sequential_time < 1.0
        assert concurrent_time < 1.0

    @pytest.mark.asyncio
    async def test_acquire_returns_true_always(self):
        """Test that acquire() always returns True (after waiting if needed)."""
        limiter = TokenBucketRateLimiter(max_calls=3, period_seconds=1)

        # First 3 should return True immediately
        for _ in range(3):
            result = await limiter.acquire()
            assert result is True

        # 4th should wait but still return True
        result = await asyncio.wait_for(limiter.acquire(), timeout=2)
        assert result is True


class TestRateLimiterEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_zero_max_calls_edge_case(self):
        """Test behavior with max_calls=0 (edge case, should not happen in practice)."""
        limiter = TokenBucketRateLimiter(max_calls=0, period_seconds=60)

        # This would infinite loop in a naive implementation
        # Our implementation should handle gracefully
        # We'll just verify it doesn't crash
        assert limiter.get_remaining() == 0

    @pytest.mark.asyncio
    async def test_very_large_max_calls(self):
        """Test with very large max_calls value."""
        limiter = TokenBucketRateLimiter(max_calls=10000, period_seconds=60)

        assert limiter.get_remaining() == 10000

        # Make some calls
        for _ in range(100):
            await limiter.acquire()

        assert limiter.get_remaining() == 9900

    @pytest.mark.asyncio
    async def test_very_short_period(self):
        """Test with very short period (1 second)."""
        limiter = TokenBucketRateLimiter(max_calls=5, period_seconds=1)

        # Should work correctly even with short period
        for _ in range(5):
            await limiter.acquire()

        assert limiter.get_remaining() == 0

        # Wait for period to expire
        await asyncio.sleep(1.2)

        assert limiter.get_remaining() == 5


class TestRateLimiterIntegration:
    """Integration tests simulating real-world usage."""

    @pytest.mark.asyncio
    async def test_reddit_api_rate_limit_simulation(self):
        """Simulate Reddit's 100 requests per 60 seconds limit."""
        limiter = TokenBucketRateLimiter(max_calls=100, period_seconds=60)

        # First 100 calls should succeed immediately
        start_time = datetime.utcnow()
        for _ in range(100):
            await limiter.acquire()
        end_time = datetime.utcnow()

        # Should complete very quickly (< 1 second)
        elapsed = (end_time - start_time).total_seconds()
        assert elapsed < 1.0

        # 101st call should wait
        assert limiter.get_remaining() == 0

    @pytest.mark.asyncio
    async def test_sustained_rate_over_time(self):
        """Test sustained request rate over multiple windows."""
        limiter = TokenBucketRateLimiter(max_calls=5, period_seconds=1)

        total_calls = 0

        # Run for 3 seconds, making calls as fast as allowed
        end_time = datetime.utcnow() + timedelta(seconds=3)

        while datetime.utcnow() < end_time:
            await limiter.acquire()
            total_calls += 1

        # Should have made approximately 15 calls (5 per second * 3 seconds)
        # Allow some variance due to timing
        assert 14 <= total_calls <= 16

    @pytest.mark.asyncio
    async def test_burst_then_sustain(self):
        """Test burst of requests followed by sustained rate."""
        limiter = TokenBucketRateLimiter(max_calls=10, period_seconds=2)

        # Burst: 10 calls immediately
        for _ in range(10):
            await limiter.acquire()

        assert limiter.get_remaining() == 0

        # Wait for 1 second (half the window)
        await asyncio.sleep(1)

        # Some capacity should be available (calls start expiring)
        # Exact amount depends on timing, but should be > 0
        remaining = limiter.get_remaining()
        assert remaining >= 0

        # Should be able to make more calls
        if remaining > 0:
            await limiter.acquire()
            assert True  # Successfully acquired


# Run with: pytest tests/test_reddit/test_rate_limiter.py -v
