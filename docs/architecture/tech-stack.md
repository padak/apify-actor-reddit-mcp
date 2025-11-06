# Technology Stack - Reddit MCP Server

**Version:** 1.0 MVP
**Last Updated:** 2025-11-05
**Focus:** Week 1-2 MVP essentials only

---

## Overview

This document defines the minimal technology stack for the Reddit MCP Server MVP. Following KISS and YAGNI principles, we only include dependencies essential for core functionality.

---

## Core Technologies

### 1. Runtime & Language

**Python 3.11+**
- **Why**: Official MCP SDK support, mature Reddit API client (PRAW), async/await native support
- **Version**: 3.11+ (for improved performance and type hints)
- **Key Features Used**: asyncio, type hints, dataclasses

### 2. MCP Framework

**FastMCP 1.0+**
- **Why**: Official Anthropic framework, decorator-based tool registration, minimal boilerplate
- **Purpose**: Handles JSON-RPC protocol, request routing, transport (stdio/HTTP)
- **MVP Usage**: Tool registration, input validation integration
- **Installation**: `pip install mcp`

### 3. Reddit API Client

**PRAW 7.7+** (Python Reddit API Wrapper)
- **Why**: Battle-tested (10+ years), auto rate limiting, OAuth2 handling, Pythonic API
- **Purpose**: All Reddit API interactions (search, posts, comments, subreddit data)
- **Key Benefits**: Built-in 30s caching, automatic token refresh, connection pooling
- **Installation**: `pip install praw`

### 4. Caching Layer

**Redis 7.0+** (via redis-py)
- **Why**: Sub-millisecond reads, built-in TTL, atomic operations, Apify-compatible
- **Purpose**: Cache Reddit API responses to minimize rate limit usage
- **Client Library**: `redis[asyncio]` (async support)
- **MVP Usage**: Simple GET/SET with TTL, no advanced features needed
- **Installation**: `pip install redis[asyncio]`

### 5. Data Validation

**Pydantic 2.0+**
- **Why**: FastMCP integration, runtime validation, auto JSON schema generation
- **Purpose**: Input/output validation for all MCP tools
- **Key Features**: Field validators, type coercion, clear error messages
- **Installation**: `pip install pydantic`

### 6. Apify SDK

**Apify Python SDK (latest)**
- **Why**: Required for Apify Actor deployment, monitoring, dataset logging
- **Purpose**: Actor lifecycle management, usage tracking, standby mode
- **Installation**: `pip install apify`

---

## Supporting Libraries

### HTTP Server

**Uvicorn 0.25+** (ASGI server)
- **Purpose**: Production HTTP server for standby mode
- **Why**: High performance, async support, widely adopted
- **Installation**: `pip install uvicorn`

### Logging

**structlog 23.0+**
- **Purpose**: Structured JSON logging for better monitoring
- **Why**: Machine-readable logs, context preservation, Apify-friendly
- **Installation**: `pip install structlog`

---

## Optional: Post-MVP (v1.0)

### Sentiment Analysis

**vaderSentiment 3.3+**
- **Purpose**: Social media sentiment analysis for `analyze_sentiment` tool
- **Why**: Fast (rule-based), social media optimized, no ML model needed
- **When**: Add in Week 3 for v1.0 release
- **Installation**: `pip install vaderSentiment`

### Rate Limiting

**Built-in** (Python asyncio + Redis)
- **Purpose**: Token bucket rate limiter for Reddit API
- **Why**: No external library needed, simple implementation
- **Implementation**: Custom TokenBucketRateLimiter class

---

## Complete Requirements.txt (MVP)

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

# Python Standard Enhancements
python-dotenv>=1.0.0  # Environment variable management
```

**Total Core Dependencies: 8 packages**

---

## Infrastructure Dependencies

### Redis Instance
- **Provider**: Redis Cloud (free tier) or Apify-compatible Redis
- **Plan**: 250MB free tier (sufficient for MVP)
- **Configuration**: allkeys-lru eviction, AOF persistence
- **Cost**: $0 (free tier)

### Reddit API Credentials
- **Type**: Application OAuth2 (read-only)
- **Rate Limit**: 100 requests/minute (free tier)
- **Storage**: Apify Actor secrets (encrypted)
- **Cost**: $0

---

## Development Tools (Not in Production)

```txt
# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0

# Code Quality
black>=23.0.0  # Code formatting
mypy>=1.5.0    # Type checking
ruff>=0.1.0    # Fast linting
```

---

## Technology Decisions & Rationale

### Why NOT Include These?

**Excluded from MVP:**
- ~~Transformer models~~ - Too slow, requires GPU (add in v2.0 if needed)
- ~~Celery/RQ~~ - No background jobs in MVP (add for watch_keywords in v1.0)
- ~~SQLAlchemy/database~~ - No persistent storage needed in MVP (Redis is sufficient)
- ~~Prometheus~~ - Use Apify built-in monitoring for MVP
- ~~Docker Compose~~ - Apify handles deployment
- ~~GraphQL~~ - MCP uses JSON-RPC, no need for GraphQL

### Why These Specific Versions?

- **Python 3.11+**: Performance improvements, better error messages
- **Pydantic 2.x**: 5-50x faster than v1 (Rust core)
- **Redis 7.x**: Improved memory efficiency, better persistence
- **PRAW 7.7+**: Latest Reddit API compatibility

---

## Performance Characteristics

| Component | Memory (MB) | Startup Time | Throughput |
|-----------|-------------|--------------|------------|
| Python 3.11 | ~50 | <1s | N/A |
| FastMCP | ~10 | <0.5s | 1000+ req/s |
| PRAW | ~20 | <0.5s | 100 req/min (API limit) |
| Redis Client | ~5 | <0.1s | 100K ops/s |
| Pydantic | ~5 | <0.1s | 10K validations/s |
| **Total MVP** | ~**100MB** | ~**2s** | **100 req/min** |

---

## Deployment Stack (Apify)

### Dockerfile Base
```dockerfile
FROM apify/actor-python:3.11
```
- Pre-configured Python 3.11 environment
- Apify SDK pre-installed
- Optimized for fast startup

### Environment Variables
- `REDDIT_CLIENT_ID` (secret)
- `REDDIT_CLIENT_SECRET` (secret)
- `REDIS_URL` (connection string)
- `LOG_LEVEL` (default: INFO)

---

## Migration Path (Future)

### To v1.0 (Week 3-4)
- Add: `vaderSentiment` (sentiment analysis)
- Add: Background job processing (simple asyncio tasks)
- Add: User authentication (API keys)

### To v2.0 (Month 2+)
- Consider: Task queue (Celery/RQ) for watch_keywords
- Consider: PostgreSQL for analytics (if Apify datasets insufficient)
- Consider: Advanced NLP (BERT) for better sentiment (if customers request)

---

## Security Considerations

### Dependency Management
- Pin all versions in requirements.txt
- Regular security audits with `pip-audit`
- Update dependencies monthly (security patches)

### Secrets Management
- Never commit credentials to git
- Use Apify Actor secrets for all sensitive data
- Rotate Reddit API credentials quarterly

---

## Summary

This minimal tech stack provides everything needed for a production-ready MVP while maintaining:
- **Simplicity**: 8 core dependencies
- **Performance**: <2s startup, 100MB memory
- **Reliability**: Battle-tested libraries only
- **Cost**: $0 infrastructure for MVP
- **Scalability**: Ready for 5,000+ MAU

**Next Step**: See `source-tree.md` for project structure and `coding-standards.md` for implementation guidelines.
