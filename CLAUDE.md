# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Reddit MCP Server** - an enterprise-grade Model Context Protocol server that provides Reddit data access through 4 production MCP tools. Built as an Apify Actor for the $1M Challenge.

**Status**: MVP complete (9/10 stories done, ~40h development time)
**Target**: 5,000 MAU by Month 6

## Essential Commands

### Development Setup
```bash
# Install dependencies
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDIS_URL

# Start Redis (required)
docker run -d -p 6379:6379 redis:7-alpine
```

### Running the Server
```bash
# Run MCP server
python -m src.main

# Verify Redis connection
redis-cli ping  # Should return PONG
```

### Testing
```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest --cov=src --cov-report=html tests/

# Run specific test category
pytest tests/test_tools/  # Tool tests only
pytest tests/test_cache/  # Cache tests only
pytest tests/test_reddit/ # Reddit API tests only

# Run single test file
pytest tests/test_tools/test_search_reddit.py -v
```

### Code Quality
```bash
# Format code (required before commit)
black src/ tests/

# Lint (must pass)
ruff check src/ tests/

# Type check (strict mode)
mypy src/ --strict

# Run all quality checks
black src/ tests/ && ruff check src/ tests/ && mypy src/ --strict
```

### Apify Deployment
```bash
# Deploy to Apify platform
apify login
apify push

# Test Actor locally
apify run
```

## Architecture Overview

### High-Level Data Flow
```
MCP Client → FastMCP Server → Tool Implementation
                ↓
            Cache Check (Redis)
                ↓
         Cache Hit? → Return cached data
                ↓ No
         Rate Limiter (100 QPM)
                ↓
         Reddit API (PRAW)
                ↓
         Response Normalizer
                ↓
         Store in Cache → Return to Client
```

### Core Components

**MCP Tools** (`src/tools/`):
- `search_reddit.py` - Search all of Reddit with filters
- `get_subreddit_posts.py` - Monitor subreddits (5 sort types)
- `get_post_comments.py` - Nested comment tree builder
- `get_trending_topics.py` - Keyword analysis (100-200 posts)

**Reddit Integration** (`src/reddit/`):
- `client.py` - PRAW singleton client manager
- `rate_limiter.py` - Token bucket (100 requests/60s)
- `normalizer.py` - Convert Reddit objects to standard dicts
- `exceptions.py` - Custom error hierarchy

**Caching Layer** (`src/cache/`):
- `connection.py` - Redis connection pool
- `manager.py` - Cache-aside pattern implementation
- `keys.py` - Deterministic cache key generation (`reddit:{tool}:{hash}:v1`)
- `ttl.py` - Content-aware TTL policies (2min - 1hr)

**Server Foundation** (`src/`):
- `server.py` - FastMCP initialization, tool registration
- `main.py` - Entry point, Apify Actor integration
- `models/responses.py` - Pydantic response models
- `utils/logger.py` - Structured logging (structlog)

### Critical Patterns

**1. Cache-Aside Pattern** (Used in ALL tools):
```python
cache_key = key_generator.generate(tool_name, params)
ttl = CacheTTL.get_ttl(tool_name, params)

async def fetch_from_reddit():
    await rate_limiter.acquire()  # ALWAYS before API call
    # ... Reddit API call ...
    return normalized_data

response = await cache_manager.get_or_fetch(cache_key, fetch_from_reddit, ttl)
```

**2. Async Wrapper for PRAW** (PRAW is synchronous):
```python
import asyncio

# Wrap sync PRAW calls
posts = await asyncio.to_thread(
    lambda: list(reddit.subreddit("python").hot(limit=25))
)
```

**3. Response Structure** (ALL tools return this):
```python
{
    "data": { ... },  # Actual results
    "metadata": {
        "cached": bool,
        "cache_age_seconds": int,
        "ttl": int,
        "rate_limit_remaining": int,
        "execution_time_ms": float,
        "reddit_api_calls": int
    }
}
```

## Key Implementation Rules

### Type Hints (Mandatory)
- **ALL** functions require complete type hints
- Run `mypy src/ --strict` - must pass with zero errors
- Use `Optional[T]` for nullable values
- Use `Literal` for enum-like strings

### Async/Await (Critical)
- All I/O operations MUST be async
- Never use `time.sleep()` - use `await asyncio.sleep()`
- PRAW calls must be wrapped with `asyncio.to_thread()`
- Never block the event loop

### Error Handling
- Use custom exception hierarchy from `src/reddit/exceptions.py`
- Always log errors with structured logging
- Fail-open for cache errors (continue without cache)
- Never swallow exceptions with bare `except:`

### Testing Requirements
- Each tool needs 20+ tests (see existing test files for pattern)
- Test both cache hit and miss scenarios
- Mock `rate_limiter.acquire()` in tests
- Test input validation edge cases
- Integration tests marked with `@pytest.mark.integration`

### Cache TTL Strategy
Variable by content type (defined in `src/cache/ttl.py`):
- New posts: 120s (2 min) - changes rapidly
- Hot posts: 300s (5 min) - moderately dynamic
- Top posts: 3600s (1 hour) - historical, stable
- Search: 300s (5 min) - balance freshness vs API calls

## Tool Implementation Template

When adding a new MCP tool, follow this exact pattern (see `src/tools/search_reddit.py` as reference):

```python
from src.server import mcp
from src.cache import cache_manager, key_generator, CacheTTL
from src.reddit import get_reddit_client, normalize_post_batch, rate_limiter
from src.models.responses import ToolResponse, ResponseMetadata

class MyToolInput(BaseModel):
    # Pydantic validation model
    pass

@mcp.tool()
async def my_tool(params: MyToolInput) -> ToolResponse:
    """Tool docstring."""

    # 1. Generate cache key
    cache_key = key_generator.generate("my_tool", params.dict())
    ttl = CacheTTL.get_ttl("my_tool", params.dict())

    # 2. Define fetch function
    async def fetch_from_reddit():
        await rate_limiter.acquire()  # CRITICAL
        reddit = get_reddit_client()
        # ... Reddit API calls ...
        return normalized_results

    # 3. Get from cache or fetch
    response = await cache_manager.get_or_fetch(cache_key, fetch_from_reddit, ttl)

    # 4. Build metadata
    metadata = ResponseMetadata(
        cached=response["metadata"]["cached"],
        cache_age_seconds=response["metadata"]["cache_age_seconds"],
        ttl=ttl,
        rate_limit_remaining=rate_limiter.get_remaining(),
        execution_time_ms=...,
        reddit_api_calls=0 if response["metadata"]["cached"] else 1
    )

    return ToolResponse(data=response["data"], metadata=metadata)
```

## Dependencies & Constraints

### Reddit API Limits
- **100 requests/minute** (free tier) - enforced by `TokenBucketRateLimiter`
- OAuth2 tokens expire after 1 hour (PRAW auto-refreshes)
- Target 75%+ cache hit rate to stay under limit

### Redis Cache
- Required for production (fail-open if unavailable)
- Keys pattern: `reddit:{tool}:{md5_hash}:{version}`
- Eviction policy: `allkeys-lru`
- Local dev: `redis://localhost:6379`

### Python Dependencies (8 core)
- `fastmcp>=1.0.0` - MCP framework
- `praw>=7.7.0` - Reddit API
- `redis[asyncio]>=5.0.0` - Caching
- `pydantic>=2.0.0` - Validation
- `apify>=1.6.0` - Apify platform
- `uvicorn>=0.25.0` - HTTP server
- `structlog>=23.0.0` - Logging
- `python-dotenv>=1.0.0` - Config

## Debugging Tips

### Redis Connection Issues
```bash
# Check Redis is running
redis-cli ping

# Test connection
redis-cli -u redis://localhost:6379 ping

# View cached keys
redis-cli keys "reddit:*"
```

### Rate Limit Testing
```python
# Check remaining quota
remaining = rate_limiter.get_remaining()
print(f"Remaining calls: {remaining}/100")

# View rate limiter stats
stats = rate_limiter.get_stats()
print(stats)  # Shows utilization, calls made, etc.
```

### Tool Testing Pattern
```python
# Test tool with mocked dependencies
@pytest.mark.asyncio
async def test_my_tool(mocker):
    # Mock rate limiter
    mocker.patch("src.tools.my_tool.rate_limiter.acquire", return_value=None)

    # Mock Reddit API
    mocker.patch("src.tools.my_tool.get_reddit_client", return_value=mock_reddit)

    # Test the tool
    result = await my_tool(params)
    assert result["metadata"]["cached"] is False
```

## Common Pitfalls

### Don't Do This
```python
# ❌ Blocking call in async function
def fetch_data():
    time.sleep(5)  # WRONG

# ❌ No rate limiting before API call
result = reddit.subreddit("python").hot()  # WRONG

# ❌ Missing type hints
def process(data):  # WRONG
    return data

# ❌ Swallowing exceptions
try:
    risky_operation()
except:  # WRONG
    pass
```

### Do This Instead
```python
# ✅ Async sleep
async def fetch_data():
    await asyncio.sleep(5)  # CORRECT

# ✅ Rate limit before API call
await rate_limiter.acquire()
result = await asyncio.to_thread(
    lambda: list(reddit.subreddit("python").hot())
)

# ✅ Complete type hints
def process(data: dict[str, Any]) -> dict[str, str]:  # CORRECT
    return data

# ✅ Specific exception handling with logging
try:
    risky_operation()
except SpecificError as e:  # CORRECT
    logger.error("Operation failed", error=str(e))
    raise
```

## File Locations Reference

### Most Frequently Modified
- `src/tools/` - Add new MCP tools here
- `tests/test_tools/` - Add tests for new tools
- `src/models/responses.py` - Add new Pydantic models
- `.env` - Local configuration (NEVER commit)

### Configuration Files
- `actor.json` - Apify Actor manifest
- `requirements.txt` - Python dependencies
- `pyproject.toml` - Black, Ruff, mypy config
- `Dockerfile` - Container definition

### Documentation
- `docs/architecture/` - Tech stack, coding standards, source tree
- `docs/prd/prd.md` - Product requirements
- `docs/stories/epic-01-mvp-foundation.md` - 10 development stories
- `docs/progress.md` - Current development status

## Quick Reference

### Test a Single Tool
```bash
pytest tests/test_tools/test_search_reddit.py::test_search_with_cache_hit -v
```

### Add Environment Variable
1. Add to `.env.example`
2. Add to `actor.json` → `environmentVariables`
3. Document in README.md

### Create New MCP Tool
1. Copy pattern from `src/tools/search_reddit.py`
2. Create Pydantic input model
3. Implement cache-aside pattern
4. Add rate limiter before API calls
5. Create 20+ tests in `tests/test_tools/`
6. Update `src/tools/__init__.py` exports
