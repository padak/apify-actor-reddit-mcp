# Coding Standards - Reddit MCP Server

**Version:** 1.0 MVP
**Last Updated:** 2025-11-05
**Principles:** KISS, YAGNI, Readability over cleverness

---

## Overview

This document defines minimal, practical coding standards for the Reddit MCP Server MVP. Focus on clarity, type safety, and async patterns.

---

## 1. Python Style Guide

### Base Standard
Follow **PEP 8** with these specific guidelines:
- Line length: 100 characters (not 79)
- Use Black formatter (no configuration needed)
- Use Ruff for linting (replaces flake8/pylint)

### Formatting (Black)
```bash
# Format all code
black src/

# Check formatting
black --check src/
```

### Linting (Ruff)
```bash
# Run linter
ruff check src/

# Fix auto-fixable issues
ruff check --fix src/
```

---

## 2. Type Hints

### Always Use Type Hints
Type hints are **required** for all functions, methods, and class attributes.

**Good:**
```python
from typing import Optional, List
import asyncio

async def search_reddit(
    query: str,
    subreddit: Optional[str] = None,
    limit: int = 25
) -> dict[str, any]:
    """Search Reddit for posts matching query."""
    results: List[dict] = await fetch_results(query)
    return {"results": results}
```

**Bad:**
```python
async def search_reddit(query, subreddit=None, limit=25):
    results = await fetch_results(query)
    return {"results": results}
```

### Type Checking
Run mypy for static type checking:
```bash
mypy src/ --strict
```

### Common Type Patterns
```python
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime

# Optional values
def get_user(username: str) -> Optional[dict]: ...

# Literals for enums
def sort_posts(sort: Literal["hot", "new", "top"]) -> List[dict]: ...

# Any for dynamic data (use sparingly)
def normalize_response(data: Any) -> dict[str, Any]: ...

# Generic collections (Python 3.9+)
def process_posts(posts: list[dict]) -> dict[str, list[str]]: ...
```

---

## 3. Async/Await Patterns

### Always Async for I/O
All I/O operations (Reddit API, Redis, file I/O) must be async.

**Correct Pattern:**
```python
async def get_cached_or_fetch(cache_key: str) -> dict:
    # Check cache (async)
    cached = await cache.get(cache_key)
    if cached:
        return cached

    # Fetch from API (async)
    data = await fetch_from_reddit()

    # Store in cache (async)
    await cache.set(cache_key, data, ttl=300)

    return data
```

### Never Block the Event Loop
**Bad - Blocks event loop:**
```python
import time

async def bad_function():
    time.sleep(5)  # WRONG - blocks everything
```

**Good - Async sleep:**
```python
import asyncio

async def good_function():
    await asyncio.sleep(5)  # Correct - allows other tasks to run
```

### Sync to Async Wrapper
For PRAW (which is synchronous), use asyncio.to_thread:
```python
import asyncio

async def fetch_posts(subreddit: str) -> list:
    reddit = get_reddit_client()

    # Run sync PRAW call in thread pool
    posts = await asyncio.to_thread(
        lambda: list(reddit.subreddit(subreddit).hot(limit=25))
    )

    return posts
```

### Concurrent Operations
Use `asyncio.gather()` for parallel operations:
```python
async def fetch_multiple_subreddits(subreddits: list[str]) -> dict:
    tasks = [fetch_subreddit_posts(sr) for sr in subreddits]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    return {sr: result for sr, result in zip(subreddits, results)}
```

---

## 4. Error Handling

### Custom Exception Hierarchy
Define clear exception hierarchy:
```python
from mcp.types import MCPError

class RedditMCPError(MCPError):
    """Base exception for Reddit MCP."""
    pass

class ValidationError(RedditMCPError):
    """Input validation failed."""
    code = -32602

class RateLimitError(RedditMCPError):
    """Rate limit exceeded."""
    code = -32000

class RedditAPIError(RedditMCPError):
    """Reddit API error."""
    code = -32001
```

### Try-Except Pattern
Be specific with exceptions:
```python
import logging

logger = logging.getLogger(__name__)

async def fetch_data(post_id: str) -> dict:
    try:
        data = await reddit_api.get_post(post_id)
        return data

    except praw.exceptions.NotFound:
        # Expected error - return empty
        logger.info(f"Post not found: {post_id}")
        return {}

    except praw.exceptions.ServerError as e:
        # Retryable error
        logger.warning(f"Reddit server error: {e}")
        raise RedditAPIError("Reddit unavailable") from e

    except Exception as e:
        # Unexpected error
        logger.error(f"Unexpected error fetching post: {e}", exc_info=True)
        raise RedditMCPError("Internal error") from e
```

### Never Swallow Exceptions
**Bad:**
```python
try:
    risky_operation()
except:
    pass  # WRONG - silently fails
```

**Good:**
```python
try:
    risky_operation()
except SpecificError as e:
    logger.error(f"Operation failed: {e}")
    raise  # Re-raise or handle appropriately
```

---

## 5. Naming Conventions

### Functions and Variables
```python
# Snake case for functions, variables, methods
def get_subreddit_posts():
    user_count = 100
    total_score = calculate_score()
```

### Classes
```python
# PascalCase for classes
class RedditAPIClient:
    pass

class CacheManager:
    pass
```

### Constants
```python
# UPPER_SNAKE_CASE for constants
MAX_RETRY_ATTEMPTS = 3
DEFAULT_CACHE_TTL = 300
REDDIT_API_BASE_URL = "https://oauth.reddit.com"
```

### Private Members
```python
class CacheManager:
    def __init__(self):
        self._redis_client = redis.Redis()  # Private (internal use)
        self.__secret_key = "..."  # Name-mangled (avoid unless necessary)

    def _internal_helper(self):  # Private method
        pass

    def public_method(self):  # Public API
        pass
```

### Tool Names (MCP Convention)
```python
# Use snake_case, be descriptive
@mcp.tool()
async def search_reddit(): ...

@mcp.tool()
async def get_subreddit_posts(): ...

@mcp.tool()
async def get_post_comments(): ...
```

---

## 6. Docstrings

### Required for Public Functions
Use Google-style docstrings:
```python
async def search_reddit(
    query: str,
    subreddit: Optional[str] = None,
    limit: int = 25
) -> dict:
    """
    Search Reddit for posts matching query.

    Args:
        query: Search keywords or phrase
        subreddit: Optional subreddit to limit search to
        limit: Maximum number of results (1-100)

    Returns:
        Dictionary with 'results' list and 'metadata' dict

    Raises:
        ValidationError: If query is empty or limit out of range
        RateLimitError: If Reddit API rate limit exceeded

    Example:
        >>> results = await search_reddit("python programming", limit=10)
        >>> print(results['metadata']['total_found'])
        523
    """
    # Implementation...
```

### Minimal for Private Functions
```python
def _build_cache_key(tool: str, params: dict) -> str:
    """Generate cache key from tool name and params."""
    # One-line docstring for simple internal functions
```

---

## 7. Pydantic Models

### Use for All Input/Output Validation
```python
from pydantic import BaseModel, Field, validator

class SearchRedditInput(BaseModel):
    """Input schema for search_reddit tool."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Search query"
    )

    subreddit: Optional[str] = Field(
        None,
        pattern="^[A-Za-z0-9_]+$",
        description="Target subreddit"
    )

    limit: int = Field(25, ge=1, le=100)

    @validator('query')
    def sanitize_query(cls, v: str) -> str:
        """Remove dangerous characters."""
        return v.strip().replace('\x00', '')

    class Config:
        # Example for documentation
        schema_extra = {
            "example": {
                "query": "machine learning",
                "limit": 50
            }
        }
```

---

## 8. Logging

### Use Structured Logging
```python
import structlog

logger = structlog.get_logger(__name__)

async def process_request(tool: str, params: dict):
    logger.info(
        "tool_request",
        tool=tool,
        param_count=len(params),
        timestamp=datetime.utcnow().isoformat()
    )

    try:
        result = await execute_tool(tool, params)

        logger.info(
            "tool_success",
            tool=tool,
            result_count=len(result.get('results', []))
        )

        return result

    except Exception as e:
        logger.error(
            "tool_error",
            tool=tool,
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        raise
```

### Log Levels
- **DEBUG**: Cache hits/misses, detailed flow
- **INFO**: Tool requests, successful operations
- **WARNING**: Rate limit proximity, cache errors (non-blocking)
- **ERROR**: Tool failures, API errors
- **CRITICAL**: System failures (Redis down, auth failed)

---

## 9. Testing Patterns

### Test File Structure
```
tests/
├── unit/
│   ├── test_cache.py
│   ├── test_validators.py
│   └── test_tools.py
├── integration/
│   ├── test_reddit_api.py
│   └── test_mcp_server.py
└── conftest.py  # Shared fixtures
```

### Async Test Example
```python
import pytest

@pytest.mark.asyncio
async def test_search_reddit_cached():
    """Test search returns cached results when available."""
    # Arrange
    cache_key = "test_key"
    expected = {"results": [{"id": "1"}]}
    await cache.set(cache_key, expected, ttl=60)

    # Act
    result = await search_reddit(query="test")

    # Assert
    assert result['data'] == expected
    assert result['metadata']['cached'] is True
```

### Use Fixtures
```python
# conftest.py
import pytest

@pytest.fixture
async def redis_client():
    """Provide test Redis client."""
    client = redis.Redis.from_url("redis://localhost:6379/1")
    yield client
    await client.flushdb()  # Clean up
```

---

## 10. File Organization

### Project Structure
```
src/
├── main.py              # Entry point, server initialization
├── tools/               # MCP tool implementations
│   ├── __init__.py
│   ├── search.py        # search_reddit
│   ├── posts.py         # get_subreddit_posts
│   └── comments.py      # get_post_comments
├── reddit/              # Reddit API integration
│   ├── __init__.py
│   ├── client.py        # PRAW client management
│   └── normalizer.py    # Response normalization
├── cache/               # Caching layer
│   ├── __init__.py
│   ├── manager.py       # Redis operations
│   └── keys.py          # Cache key generation
├── models/              # Pydantic models
│   ├── __init__.py
│   ├── inputs.py        # Tool input schemas
│   └── outputs.py       # Tool output schemas
└── utils/               # Utilities
    ├── __init__.py
    ├── rate_limiter.py  # Rate limiting
    └── logger.py        # Logging setup
```

### Import Order
```python
# 1. Standard library
import asyncio
import logging
from datetime import datetime
from typing import Optional

# 2. Third-party packages
import praw
import redis
from pydantic import BaseModel

# 3. Local imports
from src.cache import CacheManager
from src.models import SearchRedditInput
```

---

## Summary Checklist

Before committing code, ensure:
- [ ] All functions have type hints
- [ ] Public functions have docstrings
- [ ] All I/O is async (no blocking calls)
- [ ] Exceptions are specific and logged
- [ ] Code formatted with Black
- [ ] Linting passes (Ruff)
- [ ] Type checking passes (mypy --strict)
- [ ] Tests written for new features

**Golden Rule: If it's confusing to you now, it will be confusing to others later. Write clear, boring code.**
