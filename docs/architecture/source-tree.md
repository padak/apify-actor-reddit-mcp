# Source Tree - Reddit MCP Server

**Version:** 1.0 MVP
**Last Updated:** 2025-11-05
**Principles:** Clear separation of concerns, Apify Actor conventions, minimal structure

---

## Project Root Structure

```
reddit-mcp-server/
├── .github/                    # GitHub Actions CI/CD
│   └── workflows/
│       └── test.yml            # Automated testing
│
├── docs/                       # Documentation
│   ├── architecture/           # Technical docs (this file)
│   │   ├── tech-stack.md
│   │   ├── coding-standards.md
│   │   └── source-tree.md
│   ├── system-architecture.md  # Detailed system design
│   ├── feature-specifications.md
│   └── README.md               # User-facing documentation
│
├── src/                        # Source code (main implementation)
│   ├── main.py                 # Entry point
│   ├── server.py               # FastMCP server initialization
│   │
│   ├── tools/                  # MCP tool implementations
│   │   ├── __init__.py
│   │   ├── search.py           # search_reddit
│   │   ├── posts.py            # get_subreddit_posts
│   │   ├── comments.py         # get_post_comments
│   │   └── trending.py         # get_trending_topics
│   │
│   ├── reddit/                 # Reddit API integration
│   │   ├── __init__.py
│   │   ├── client.py           # PRAW client manager
│   │   ├── auth.py             # OAuth2 token handling
│   │   ├── rate_limiter.py     # Token bucket rate limiter
│   │   └── normalizer.py       # Response normalization
│   │
│   ├── cache/                  # Caching layer
│   │   ├── __init__.py
│   │   ├── manager.py          # Redis operations
│   │   ├── keys.py             # Cache key generation
│   │   └── ttl.py              # TTL policies
│   │
│   ├── models/                 # Pydantic data models
│   │   ├── __init__.py
│   │   ├── inputs.py           # Tool input schemas
│   │   ├── outputs.py          # Tool output schemas
│   │   └── internal.py         # Internal state models
│   │
│   └── utils/                  # Shared utilities
│       ├── __init__.py
│       ├── logger.py           # Structured logging setup
│       ├── errors.py           # Custom exceptions
│       └── config.py           # Configuration management
│
├── tests/                      # Test suite
│   ├── unit/                   # Unit tests
│   │   ├── test_cache.py
│   │   ├── test_rate_limiter.py
│   │   └── test_normalizer.py
│   ├── integration/            # Integration tests
│   │   ├── test_reddit_api.py
│   │   ├── test_mcp_tools.py
│   │   └── test_caching_flow.py
│   └── conftest.py             # Pytest fixtures
│
├── .env.example                # Environment variables template
├── .gitignore                  # Git ignore rules
├── actor.json                  # Apify Actor configuration
├── Dockerfile                  # Container definition
├── requirements.txt            # Python dependencies
├── requirements-dev.txt        # Development dependencies
├── pyproject.toml              # Python project config (Black, Ruff, mypy)
└── README.md                   # Project overview
```

---

## Core Files Detail

### 1. Root Configuration Files

#### `actor.json` (Apify Actor Manifest)
```json
{
  "actorSpecification": 1,
  "name": "reddit-mcp-server",
  "title": "Reddit MCP Server",
  "version": "1.0.0",
  "description": "Enterprise-grade MCP server for Reddit integration",
  "usesStandbyMode": true,
  "webServerMcpPath": "/mcp",
  "environmentVariables": {
    "REDDIT_CLIENT_ID": {
      "type": "secret",
      "required": true,
      "description": "Reddit API client ID"
    },
    "REDDIT_CLIENT_SECRET": {
      "type": "secret",
      "required": true,
      "description": "Reddit API client secret"
    },
    "REDIS_URL": {
      "type": "string",
      "required": true,
      "description": "Redis connection URL"
    },
    "LOG_LEVEL": {
      "type": "string",
      "required": false,
      "default": "INFO"
    }
  }
}
```

#### `Dockerfile` (Apify Actor Container)
```dockerfile
FROM apify/actor-python:3.11

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src ./src

# Set working directory
WORKDIR /usr/src/app

# Run the MCP server
CMD ["python", "-m", "src.main"]
```

#### `requirements.txt`
```txt
# Core Framework
mcp>=1.0.0

# Reddit Integration
praw>=7.7.0

# Caching
redis[asyncio]>=5.0.0

# Data Validation
pydantic>=2.0.0

# Apify Platform
apify>=1.6.0

# HTTP Server
uvicorn>=0.25.0

# Logging
structlog>=23.0.0

# Utilities
python-dotenv>=1.0.0
```

---

## Source Code Structure

### `/src/main.py` - Entry Point
**Purpose**: Application initialization and startup
**Responsibilities**:
- Load environment variables
- Initialize logging
- Start FastMCP server
- Handle graceful shutdown

```python
"""
Reddit MCP Server - Main Entry Point

Initializes and runs the FastMCP server with Redis caching
and Reddit API integration.
"""
import asyncio
import os
from apify import Actor
from src.server import create_mcp_server
from src.utils.logger import setup_logging

async def main():
    """Main entry point for Apify Actor."""
    async with Actor:
        # Setup logging
        setup_logging(level=os.getenv("LOG_LEVEL", "INFO"))

        # Create and run MCP server
        server = create_mcp_server()
        await server.run()

if __name__ == "__main__":
    asyncio.run(main())
```

### `/src/server.py` - MCP Server Setup
**Purpose**: FastMCP server configuration and tool registration
**Responsibilities**:
- Initialize FastMCP instance
- Register all MCP tools
- Configure middleware
- Set up error handlers

### `/src/tools/` - MCP Tool Implementations

#### Structure
Each tool is a separate module for clarity:
- `search.py` - search_reddit
- `posts.py` - get_subreddit_posts
- `comments.py` - get_post_comments
- `trending.py` - get_trending_topics

#### Example: `search.py`
```python
"""
search_reddit MCP tool implementation.
"""
from src.models.inputs import SearchRedditInput
from src.cache.manager import cache_manager
from src.reddit.client import reddit_client
from mcp.server.fastmcp import FastMCP

async def search_reddit(mcp: FastMCP, params: SearchRedditInput) -> dict:
    """
    Search Reddit for posts matching query.

    See feature-specifications.md for full details.
    """
    # Implementation here
    pass
```

### `/src/reddit/` - Reddit API Layer

#### `client.py` - PRAW Client Manager
**Purpose**: Manage Reddit API client lifecycle
**Key Classes**:
- `RedditClientManager` - Singleton PRAW client
**Responsibilities**:
- Initialize PRAW with OAuth2
- Maintain connection pool
- Handle client errors

#### `auth.py` - OAuth2 Token Management
**Purpose**: Handle Reddit OAuth2 token lifecycle
**Key Classes**:
- `OAuth2TokenManager` - Token refresh logic
**Responsibilities**:
- Token expiration detection
- Automatic token refresh
- Credential validation

#### `rate_limiter.py` - Token Bucket Rate Limiter
**Purpose**: Prevent exceeding Reddit API rate limits
**Key Classes**:
- `TokenBucketRateLimiter` - 100 QPM rate limiting
**Responsibilities**:
- Track API call timestamps
- Wait/queue when limit reached
- Priority request handling

#### `normalizer.py` - Response Normalizer
**Purpose**: Convert Reddit API responses to standard format
**Key Functions**:
- `normalize_post()` - Standardize submission objects
- `normalize_comment()` - Standardize comment objects
- `normalize_user()` - Standardize redditor objects

### `/src/cache/` - Caching Layer

#### `manager.py` - Redis Cache Manager
**Purpose**: All Redis operations
**Key Classes**:
- `CacheManager` - Redis client wrapper
**Key Methods**:
- `get(key)` - Retrieve cached value
- `set(key, value, ttl)` - Store with expiration
- `get_or_fetch(key, fetch_fn, ttl)` - Cache-aside pattern

#### `keys.py` - Cache Key Generation
**Purpose**: Generate consistent cache keys
**Key Functions**:
- `generate_cache_key(tool, params)` - Create hashed key
- Pattern: `reddit:{tool}:{params_hash}:{version}`

#### `ttl.py` - TTL Policies
**Purpose**: Define cache expiration times
**Key Classes**:
- `CacheTTL` - Enum of TTL values per content type
**TTL Values**:
- NEW_POSTS = 120s
- HOT_POSTS = 300s
- TOP_POSTS = 3600s
- SEARCH_RESULTS = 300s

### `/src/models/` - Data Models

#### `inputs.py` - Tool Input Schemas
**Purpose**: Pydantic models for tool inputs
**Models**:
- `SearchRedditInput`
- `GetSubredditPostsInput`
- `GetPostCommentsInput`
- `GetTrendingTopicsInput`

#### `outputs.py` - Tool Output Schemas
**Purpose**: Pydantic models for tool outputs
**Models**:
- `RedditPost`
- `RedditComment`
- `ResponseMetadata`
- `SearchRedditOutput`

#### `internal.py` - Internal State Models
**Purpose**: Models for internal system state
**Models**:
- `RateLimitState`
- `CachedResponse`
- `OAuthTokenState`

### `/src/utils/` - Shared Utilities

#### `logger.py` - Logging Configuration
**Purpose**: Setup structured logging
**Key Functions**:
- `setup_logging(level)` - Configure structlog

#### `errors.py` - Custom Exceptions
**Purpose**: Define exception hierarchy
**Exceptions**:
- `RedditMCPError` - Base exception
- `ValidationError` - Input validation
- `RateLimitError` - Rate limit exceeded
- `RedditAPIError` - API errors
- `CacheError` - Redis errors

#### `config.py` - Configuration Management
**Purpose**: Load and validate environment config
**Key Functions**:
- `load_config()` - Load from environment
- `validate_config()` - Ensure required vars set

---

## Directory Responsibilities Summary

| Directory | Purpose | Key Files | Dependencies |
|-----------|---------|-----------|--------------|
| `/src/tools/` | MCP tool implementations | `search.py`, `posts.py` | models, cache, reddit |
| `/src/reddit/` | Reddit API integration | `client.py`, `rate_limiter.py` | praw, asyncio |
| `/src/cache/` | Caching layer | `manager.py`, `keys.py` | redis |
| `/src/models/` | Data validation | `inputs.py`, `outputs.py` | pydantic |
| `/src/utils/` | Shared utilities | `logger.py`, `errors.py` | structlog |

---

## File Naming Conventions

### Python Modules
- Use snake_case: `rate_limiter.py`, `cache_manager.py`
- One module per major class or related functions
- `__init__.py` for package exports

### Test Files
- Prefix with `test_`: `test_cache.py`
- Mirror source structure: `src/cache/manager.py` → `tests/unit/test_cache.py`

### Configuration Files
- Use standard names: `requirements.txt`, `Dockerfile`, `actor.json`
- Environment-specific: `.env.development`, `.env.production`

---

## Import Patterns

### Internal Imports
Always use absolute imports from `src`:
```python
# Good
from src.cache.manager import CacheManager
from src.models.inputs import SearchRedditInput

# Bad
from ..cache.manager import CacheManager  # Relative imports
```

### Module `__init__.py` Pattern
Export main classes/functions:
```python
# src/cache/__init__.py
from src.cache.manager import CacheManager
from src.cache.keys import generate_cache_key

__all__ = ["CacheManager", "generate_cache_key"]
```

---

## Testing Structure

### Test Organization
```
tests/
├── unit/                       # Fast, isolated tests
│   ├── test_cache.py           # Cache operations
│   ├── test_keys.py            # Key generation
│   ├── test_normalizer.py      # Response normalization
│   └── test_rate_limiter.py    # Rate limiting logic
│
├── integration/                # Slower, integration tests
│   ├── test_reddit_api.py      # Reddit API calls
│   ├── test_mcp_tools.py       # End-to-end tool tests
│   └── test_cache_flow.py      # Cache hit/miss flows
│
└── conftest.py                 # Shared fixtures
```

### Test File Naming
- Unit tests: `test_{module}.py`
- Integration tests: `test_{feature}_integration.py`

---

## Development Workflow

### Local Development Structure
```
# 1. Set up environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 2. Set environment variables
cp .env.example .env
# Edit .env with your credentials

# 3. Run tests
pytest tests/

# 4. Run server locally
python -m src.main

# 5. Format and lint
black src/ tests/
ruff check src/ tests/
mypy src/
```

---

## Deployment Structure (Apify)

### Apify Actor File Requirements
**Required files for deployment:**
1. `actor.json` - Actor manifest
2. `Dockerfile` - Container definition
3. `requirements.txt` - Python dependencies
4. `src/` - Source code directory

**Optional but recommended:**
1. `README.md` - User documentation
2. `INPUT_SCHEMA.json` - Actor input schema (auto-generated from Pydantic)
3. `.actor/` - Actor assets (screenshots, icons)

### Apify Directory Structure (Generated)
```
.actor/
├── actor.json              # Copy of actor.json
├── INPUT_SCHEMA.json       # Auto-generated from Pydantic models
├── README.md               # User-facing docs
└── screenshots/            # Actor store screenshots
    ├── screenshot-1.png
    └── screenshot-2.png
```

---

## Key Design Decisions

### Why This Structure?

1. **Flat Tool Organization**: Each tool is a separate file (not nested) for easy navigation
2. **Clear Layering**: tools → reddit/cache → models/utils (no circular dependencies)
3. **Minimal Nesting**: Max 2 levels deep (src/reddit/client.py)
4. **Apify-First**: Follows Apify Actor conventions (actor.json, Dockerfile at root)
5. **Test Mirroring**: Test structure mirrors source structure for clarity

### Anti-Patterns Avoided

- No monolithic `utils.py` - utilities organized by domain
- No deep nesting (src/lib/core/reddit/api/client.py)
- No mixing concerns (Reddit logic separate from cache logic)
- No circular imports (strict dependency hierarchy)

---

## Migration Path

### Adding New Tool (Week 3+)
1. Create `src/tools/new_tool.py`
2. Define input/output models in `src/models/inputs.py` and `outputs.py`
3. Register in `src/server.py`
4. Add tests in `tests/unit/test_new_tool.py`

### Adding New Feature Layer (v2.0+)
If adding background jobs:
```
src/
└── jobs/                   # Background job processing
    ├── __init__.py
    ├── scheduler.py        # Job scheduling
    └── watch_keywords.py   # Keyword monitoring job
```

---

## Summary

This source tree provides:
- **Clarity**: Clear responsibility per directory
- **Simplicity**: Minimal nesting, flat where possible
- **Scalability**: Easy to add new tools/features
- **Maintainability**: Obvious where to find things
- **Testability**: Mirrored test structure

**Golden Rule**: If you can't decide where a file goes, ask: "What is its primary responsibility?" Then place it in that domain's directory.

**Next Steps**: See `tech-stack.md` for dependencies and `coding-standards.md` for implementation guidelines.
