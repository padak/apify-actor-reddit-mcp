# System Architecture - Reddit MCP Server

**Version:** 1.0
**Last Updated:** 2025-11-05
**Target:** Apify $1M Challenge - 5,000 MAU, Quality Score 65+

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [Component Breakdown](#2-component-breakdown)
3. [Data Models](#3-data-models)
4. [Component Interaction Flows](#4-component-interaction-flows)
5. [Technology Stack Justification](#5-technology-stack-justification)
6. [Performance & Scalability](#6-performance--scalability)
7. [Security Architecture](#7-security-architecture)
8. [Deployment Architecture](#8-deployment-architecture)

---

## 1. High-Level Architecture

### 1.1 System Overview (ASCII Diagram)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MCP CLIENT LAYER                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │  Claude  │  │ ChatGPT  │  │  Cursor  │  │  Other   │           │
│  │ Desktop  │  │   App    │  │   IDE    │  │  Clients │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       │             │              │              │                  │
│       └─────────────┴──────────────┴──────────────┘                  │
│                           │                                          │
│                    JSON-RPC 2.0                                      │
│                      (stdio/HTTP)                                    │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    MCP SERVER LAYER (FastMCP)                        │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                   Request Router                            │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐         │    │
│  │  │ Tool 1  │ │ Tool 2  │ │ Tool 3  │ │ Tool 8  │   ...   │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘         │    │
│  └────────────────────────┬───────────────────────────────────┘    │
│                           │                                          │
│  ┌────────────────────────▼───────────────────────────────────┐    │
│  │              Middleware Stack                               │    │
│  │  ┌─────────────────────────────────────────────────────┐   │    │
│  │  │  Input Validation (Pydantic)                        │   │    │
│  │  └─────────────────────────────────────────────────────┘   │    │
│  │  ┌─────────────────────────────────────────────────────┐   │    │
│  │  │  Authentication & Authorization                     │   │    │
│  │  └─────────────────────────────────────────────────────┘   │    │
│  │  ┌─────────────────────────────────────────────────────┐   │    │
│  │  │  Rate Limiting (User-level)                         │   │    │
│  │  └─────────────────────────────────────────────────────┘   │    │
│  │  ┌─────────────────────────────────────────────────────┐   │    │
│  │  │  Error Handler & Response Formatter                │   │    │
│  │  └─────────────────────────────────────────────────────┘   │    │
│  └────────────────────────┬───────────────────────────────────┘    │
└───────────────────────────┼──────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 REDDIT API INTEGRATION LAYER                         │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │                 Cache Manager (Redis)                       │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │    │
│  │  │ Check Cache │→ │ Hit: Return │  │ Miss: Fetch │        │    │
│  │  └─────────────┘  └─────────────┘  └──────┬──────┘        │    │
│  │                                             │                │    │
│  │  ┌──────────────────────────────────────────▼──────────┐   │    │
│  │  │  Cache Key Generator: reddit:{tool}:{hash}:{v}     │   │    │
│  │  └──────────────────────────────────────────────────────┘   │    │
│  └────────────────────────┬───────────────────────────────────┘    │
│                           │ Cache Miss                               │
│                           ▼                                          │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │              Reddit API Client (PRAW)                       │    │
│  │  ┌─────────────────────────────────────────────────────┐   │    │
│  │  │  OAuth2 Token Manager                               │   │    │
│  │  │  - Token refresh (expires 1h)                       │   │    │
│  │  │  - Credential rotation                              │   │    │
│  │  └─────────────────────────────────────────────────────┘   │    │
│  │  ┌─────────────────────────────────────────────────────┐   │    │
│  │  │  Rate Limit Manager (Token Bucket)                  │   │    │
│  │  │  - 100 QPM (free tier)                              │   │    │
│  │  │  - Priority queue                                   │   │    │
│  │  │  - Exponential backoff                              │   │    │
│  │  └─────────────────────────────────────────────────────┘   │    │
│  │  ┌─────────────────────────────────────────────────────┐   │    │
│  │  │  Request Queue & Deduplication                      │   │    │
│  │  │  - Coalesce identical requests                      │   │    │
│  │  │  - Priority: real-time > historical                │   │    │
│  │  └─────────────────────────────────────────────────────┘   │    │
│  │  ┌─────────────────────────────────────────────────────┐   │    │
│  │  │  Response Normalizer                                │   │    │
│  │  │  - Standard output format                           │   │    │
│  │  │  - Error mapping                                    │   │    │
│  │  └─────────────────────────────────────────────────────┘   │    │
│  └────────────────────────┬───────────────────────────────────┘    │
└───────────────────────────┼──────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    EXTERNAL SERVICES                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │  Reddit API  │  │ Redis Cloud  │  │ VADER NLP    │             │
│  │  (100 QPM)   │  │  (Caching)   │  │ (Sentiment)  │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
└─────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 APIFY ACTOR INFRASTRUCTURE                           │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  Standby Mode (Always-on HTTP endpoint)                    │    │
│  │  - Endpoint: https://{username}--{actor}.apify.actor/mcp   │    │
│  │  - SSE Transport for streaming                             │    │
│  │  - Pay-per-event billing                                   │    │
│  └────────────────────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  Monitoring & Analytics                                     │    │
│  │  - Usage tracking (Apify Datasets)                          │    │
│  │  - Performance metrics                                      │    │
│  │  - Error logs                                               │    │
│  └────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 Data Flow Summary

1. **Client Request** → MCP client sends JSON-RPC request via stdio or HTTP/SSE
2. **Server Routing** → FastMCP routes to appropriate tool based on method name
3. **Middleware Processing** → Validation, auth, rate limiting, logging
4. **Cache Check** → Redis lookup using hashed cache key
5. **Cache Hit** → Return cached response with metadata
6. **Cache Miss** → Forward to Reddit API Integration Layer
7. **API Request** → PRAW makes OAuth2-authenticated request to Reddit API
8. **Response Processing** → Normalize, cache, return to client
9. **Monitoring** → Log metrics to Apify datasets for analytics

---

## 2. Component Breakdown

### 2.1 MCP Server Layer (FastMCP)

#### A. Server Initialization

```python
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
import os

# Initialize MCP server with metadata
mcp = FastMCP(
    name="reddit-mcp-server",
    version="1.0.0",
    description="Enterprise Reddit MCP Server with caching and sentiment analysis"
)

# Configure capabilities
mcp.configure(
    capabilities={
        "tools": {},
        "resources": {"subscribe": False},  # Future: real-time updates
        "prompts": {}
    }
)
```

#### B. Tool Registration & Routing

Each tool is registered as a decorated function with input validation:

```python
from pydantic import BaseModel, Field, validator
from typing import Optional, Literal

class SearchRedditInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Search query")
    subreddit: Optional[str] = Field(None, pattern="^[A-Za-z0-9_]+$")
    time_filter: Literal["hour", "day", "week", "month", "year", "all"] = "week"
    sort: Literal["relevance", "hot", "top", "new", "comments"] = "relevance"
    limit: int = Field(25, ge=1, le=100)

    @validator('query')
    def sanitize_query(cls, v):
        return v.strip()

@mcp.tool()
async def search_reddit(params: SearchRedditInput) -> dict:
    """Search Reddit for posts matching query"""
    # Implementation in section 2.4
    pass
```

**Routing Logic:**
- FastMCP automatically maps JSON-RPC method names to Python functions
- Pattern: `tools/call` with `name: "search_reddit"` → `search_reddit()` function
- No manual routing code needed (framework handles it)

#### C. Request/Response Handling

**Request Flow:**
1. Receive JSON-RPC request
2. Validate method exists
3. Parse parameters against Pydantic model
4. Execute tool function
5. Serialize response
6. Return JSON-RPC response

**Response Format:**
```python
class ToolResponse(BaseModel):
    results: List[dict]
    metadata: ResponseMetadata

class ResponseMetadata(BaseModel):
    cached: bool
    cache_age_seconds: Optional[int]
    rate_limit_remaining: int
    execution_time_ms: float
    reddit_api_calls: int
```

#### D. Error Handling Architecture

**Error Hierarchy:**

```python
from mcp.types import MCPError

class RedditMCPError(MCPError):
    """Base error for Reddit MCP"""
    pass

class ValidationError(RedditMCPError):
    """Input validation failed"""
    code = -32602  # Invalid params

class RateLimitError(RedditMCPError):
    """Rate limit exceeded"""
    code = -32000  # Server error

class RedditAPIError(RedditMCPError):
    """Reddit API returned error"""
    code = -32001

class CacheError(RedditMCPError):
    """Redis cache unavailable"""
    code = -32002
```

**Error Handler Middleware:**

```python
import traceback
import logging

async def error_handler_middleware(func):
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ValidationError as e:
            logger.warning(f"Validation error: {e}")
            raise
        except RateLimitError as e:
            logger.warning(f"Rate limit hit: {e}")
            raise MCPError(
                code=-32000,
                message="Rate limit exceeded",
                data={
                    "retry_after_seconds": e.retry_after,
                    "rate_limit_tier": "free"
                }
            )
        except RedditAPIError as e:
            logger.error(f"Reddit API error: {e}")
            raise MCPError(
                code=-32001,
                message="Reddit API unavailable",
                data={"status_code": e.status_code}
            )
        except Exception as e:
            logger.error(f"Unexpected error: {traceback.format_exc()}")
            raise MCPError(
                code=-32603,
                message="Internal server error",
                data={"error_type": type(e).__name__}
            )
    return wrapper
```

#### E. Logging and Monitoring Hooks

```python
import structlog
from datetime import datetime

logger = structlog.get_logger()

class MonitoringMiddleware:
    async def log_request(self, tool_name: str, params: dict, user_id: str):
        logger.info(
            "tool_request",
            tool=tool_name,
            user_id=user_id,
            timestamp=datetime.utcnow().isoformat(),
            params_hash=hash_params(params)
        )

    async def log_response(self, tool_name: str, duration_ms: float,
                          cached: bool, error: Optional[str]):
        logger.info(
            "tool_response",
            tool=tool_name,
            duration_ms=duration_ms,
            cached=cached,
            error=error,
            timestamp=datetime.utcnow().isoformat()
        )

        # Send to Apify Dataset for analytics
        await Actor.push_data({
            "event": "tool_execution",
            "tool": tool_name,
            "duration_ms": duration_ms,
            "cached": cached,
            "error": error,
            "timestamp": datetime.utcnow().isoformat()
        })
```

---

### 2.2 Reddit API Integration Layer

#### A. PRAW Client Configuration

```python
import praw
from typing import Optional

class RedditClientManager:
    def __init__(self):
        self.client: Optional[praw.Reddit] = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize PRAW with OAuth2 credentials"""
        self.client = praw.Reddit(
            client_id=os.getenv("REDDIT_CLIENT_ID"),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
            user_agent=os.getenv(
                "REDDIT_USER_AGENT",
                "Reddit-MCP-Server/1.0 by /u/apify-mcp"
            ),
            # Read-only mode (no user auth needed for most operations)
            username=None,
            password=None
        )

        # Configure PRAW settings
        self.client.read_only = True
        self.client.config.timeout = 30  # seconds

        # Validate credentials
        try:
            self.client.user.me()  # Test auth
        except Exception as e:
            logger.error(f"Reddit auth failed: {e}")
            raise RedditAPIError("Authentication failed")

    def get_client(self) -> praw.Reddit:
        """Get Reddit client instance"""
        if not self.client:
            self._initialize_client()
        return self.client

# Singleton instance
reddit_client = RedditClientManager()
```

#### B. OAuth2 Authentication Flow

**Token Lifecycle:**
- Reddit OAuth2 tokens expire after 1 hour
- PRAW automatically refreshes tokens
- Fallback: Manual refresh if PRAW fails

```python
import time
from threading import Lock

class OAuth2TokenManager:
    def __init__(self):
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.expires_at: Optional[float] = None
        self.lock = Lock()

    def get_valid_token(self) -> str:
        """Get valid access token, refresh if needed"""
        with self.lock:
            if self._is_token_expired():
                self._refresh_token()
            return self.access_token

    def _is_token_expired(self) -> bool:
        """Check if token is expired or expiring soon (5 min buffer)"""
        if not self.expires_at:
            return True
        return time.time() >= (self.expires_at - 300)

    def _refresh_token(self):
        """Refresh OAuth2 token"""
        try:
            # PRAW handles this automatically, but manual fallback:
            response = requests.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": REDDIT_USER_AGENT}
            )
            data = response.json()
            self.access_token = data["access_token"]
            self.expires_at = time.time() + data["expires_in"]
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            raise RedditAPIError("Token refresh failed")
```

#### C. Rate Limit Manager (Token Bucket Algorithm)

```python
from collections import deque
from datetime import datetime, timedelta
import asyncio

class TokenBucketRateLimiter:
    def __init__(self, max_calls: int = 100, period_seconds: int = 60):
        """
        Token bucket algorithm for rate limiting

        Args:
            max_calls: Maximum calls per period (100 for Reddit free tier)
            period_seconds: Time period in seconds (60 for per-minute)
        """
        self.max_calls = max_calls
        self.period = timedelta(seconds=period_seconds)
        self.calls = deque()  # Store timestamps of API calls
        self.lock = asyncio.Lock()

    async def acquire(self, priority: int = 0) -> bool:
        """
        Acquire permission to make API call

        Args:
            priority: 0 = normal, 1 = high (real-time), -1 = low (background)

        Returns:
            True when permission granted
        """
        async with self.lock:
            # Remove old calls outside the time window
            now = datetime.utcnow()
            while self.calls and now - self.calls[0] > self.period:
                self.calls.popleft()

            # Check if we have capacity
            if len(self.calls) < self.max_calls:
                self.calls.append(now)
                return True

            # Wait until oldest call expires
            wait_time = (self.calls[0] + self.period - now).total_seconds()
            logger.warning(
                f"Rate limit reached, waiting {wait_time:.2f}s",
                calls_made=len(self.calls),
                max_calls=self.max_calls
            )
            await asyncio.sleep(wait_time + 0.1)  # Small buffer

            # Retry after waiting
            return await self.acquire(priority)

    def get_remaining(self) -> int:
        """Get remaining calls in current window"""
        now = datetime.utcnow()
        valid_calls = [c for c in self.calls if now - c <= self.period]
        return self.max_calls - len(valid_calls)

# Global rate limiter instance
rate_limiter = TokenBucketRateLimiter(max_calls=100, period_seconds=60)
```

#### D. Request Queue System

```python
from asyncio import PriorityQueue
import hashlib
import json

class RequestQueue:
    def __init__(self):
        self.queue = PriorityQueue()
        self.in_flight = {}  # Track duplicate requests
        self.lock = asyncio.Lock()

    def _hash_request(self, endpoint: str, params: dict) -> str:
        """Generate hash for request deduplication"""
        request_str = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
        return hashlib.sha256(request_str.encode()).hexdigest()

    async def enqueue(self, endpoint: str, params: dict,
                     priority: int = 0) -> str:
        """
        Add request to queue

        Args:
            endpoint: Reddit API endpoint
            params: Request parameters
            priority: 0 = normal, 1 = high, -1 = low

        Returns:
            Request hash for tracking
        """
        request_hash = self._hash_request(endpoint, params)

        async with self.lock:
            # Check if identical request is already in flight
            if request_hash in self.in_flight:
                logger.debug(
                    "Duplicate request detected, coalescing",
                    request_hash=request_hash
                )
                return request_hash

            # Add to queue (negative priority for ascending order)
            await self.queue.put((-priority, request_hash, endpoint, params))
            self.in_flight[request_hash] = {
                "status": "queued",
                "waiters": []
            }

        return request_hash

    async def dequeue(self) -> tuple:
        """Get next request from queue"""
        priority, request_hash, endpoint, params = await self.queue.get()
        return request_hash, endpoint, params

    async def complete(self, request_hash: str, result: any):
        """Mark request as completed and notify waiters"""
        async with self.lock:
            if request_hash in self.in_flight:
                self.in_flight[request_hash]["status"] = "completed"
                self.in_flight[request_hash]["result"] = result

                # Notify all waiting for this request
                for waiter in self.in_flight[request_hash]["waiters"]:
                    waiter.set_result(result)

                # Clean up after 60 seconds
                asyncio.create_task(self._cleanup_request(request_hash, 60))

request_queue = RequestQueue()
```

#### E. Retry Logic with Exponential Backoff

```python
import random
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)

class RetryableRedditRequest:
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((
            praw.exceptions.ServerError,
            praw.exceptions.RequestException
        )),
        reraise=True
    )
    async def execute(self, func, *args, **kwargs):
        """
        Execute Reddit API request with exponential backoff

        Retry on:
        - 500/502/503 (Reddit server errors)
        - Network timeouts
        - Temporary connection failures

        Do NOT retry on:
        - 401 (auth errors)
        - 403 (permission errors)
        - 404 (not found)
        - 422 (invalid params)
        """
        try:
            # Add jitter to prevent thundering herd
            await asyncio.sleep(random.uniform(0, 0.1))

            # Acquire rate limit token
            await rate_limiter.acquire()

            # Execute request
            result = await asyncio.to_thread(func, *args, **kwargs)
            return result

        except praw.exceptions.Forbidden as e:
            logger.error(f"Permission denied: {e}")
            raise RedditAPIError(f"Access forbidden: {e}")

        except praw.exceptions.NotFound as e:
            logger.warning(f"Resource not found: {e}")
            return None  # Return None for deleted/removed content

        except praw.exceptions.InvalidToken as e:
            logger.error(f"Invalid OAuth token: {e}")
            raise RedditAPIError("Authentication error")

retry_handler = RetryableRedditRequest()
```

#### F. Response Normalization

```python
from typing import Any, Dict
from datetime import datetime

class ResponseNormalizer:
    @staticmethod
    def normalize_post(submission) -> Dict[str, Any]:
        """Normalize Reddit submission to standard format"""
        return {
            "id": submission.id,
            "type": "post",
            "title": submission.title,
            "author": submission.author.name if submission.author else "[deleted]",
            "subreddit": submission.subreddit.display_name,
            "created_utc": int(submission.created_utc),
            "score": submission.score,
            "upvote_ratio": submission.upvote_ratio,
            "num_comments": submission.num_comments,
            "url": submission.url,
            "permalink": submission.permalink,
            "selftext": submission.selftext[:1000] if submission.selftext else "",
            "link_flair_text": submission.link_flair_text,
            "is_self": submission.is_self,
            "is_video": submission.is_video,
            "over_18": submission.over_18,
            "spoiler": submission.spoiler,
            "stickied": submission.stickied
        }

    @staticmethod
    def normalize_comment(comment) -> Dict[str, Any]:
        """Normalize Reddit comment to standard format"""
        return {
            "id": comment.id,
            "type": "comment",
            "author": comment.author.name if comment.author else "[deleted]",
            "body": comment.body,
            "score": comment.score,
            "created_utc": int(comment.created_utc),
            "depth": comment.depth,
            "parent_id": comment.parent_id,
            "is_submitter": comment.is_submitter,
            "stickied": comment.stickied,
            "distinguished": comment.distinguished
        }

    @staticmethod
    def normalize_user(redditor) -> Dict[str, Any]:
        """Normalize Reddit user to standard format"""
        return {
            "username": redditor.name,
            "created_utc": int(redditor.created_utc),
            "link_karma": redditor.link_karma,
            "comment_karma": redditor.comment_karma,
            "is_gold": redditor.is_gold,
            "is_mod": redditor.is_mod,
            "has_verified_email": redditor.has_verified_email
        }

    @staticmethod
    def normalize_subreddit(subreddit) -> Dict[str, Any]:
        """Normalize subreddit to standard format"""
        return {
            "name": subreddit.display_name,
            "title": subreddit.title,
            "description": subreddit.public_description,
            "subscribers": subreddit.subscribers,
            "active_users": subreddit.active_user_count,
            "created_utc": int(subreddit.created_utc),
            "over18": subreddit.over18,
            "url": subreddit.url
        }

normalizer = ResponseNormalizer()
```

---

### 2.3 Caching System (Redis)

#### A. Redis Configuration and Connection Pooling

```python
import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

class RedisCache:
    def __init__(self):
        self.pool: Optional[ConnectionPool] = None
        self.client: Optional[redis.Redis] = None
        self._initialize_pool()

    def _initialize_pool(self):
        """Initialize Redis connection pool"""
        redis_url = os.getenv(
            "REDIS_URL",
            "redis://localhost:6379/0"
        )

        self.pool = ConnectionPool.from_url(
            redis_url,
            max_connections=20,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True
        )

        self.client = redis.Redis(connection_pool=self.pool)

    async def ping(self) -> bool:
        """Check Redis connection"""
        try:
            return await self.client.ping()
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            return False

    async def close(self):
        """Close Redis connection pool"""
        if self.client:
            await self.client.close()
        if self.pool:
            await self.pool.disconnect()

cache = RedisCache()
```

#### B. Cache Key Strategy

**Pattern:** `reddit:{tool}:{params_hash}:{version}`

```python
import hashlib
import json

class CacheKeyGenerator:
    VERSION = "v1"  # Increment when response format changes

    @staticmethod
    def generate(tool_name: str, params: dict) -> str:
        """
        Generate cache key for Reddit tool request

        Args:
            tool_name: Name of the MCP tool
            params: Tool parameters (dict)

        Returns:
            Cache key string

        Examples:
            reddit:search:a3f8d9c2e1b4:v1
            reddit:subreddit_posts:7b2e4a1c9d3f:v1
        """
        # Sort params for consistent hashing
        params_str = json.dumps(params, sort_keys=True)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:12]

        return f"reddit:{tool_name}:{params_hash}:{CacheKeyGenerator.VERSION}"

    @staticmethod
    def parse(cache_key: str) -> dict:
        """Parse cache key back to components"""
        parts = cache_key.split(":")
        if len(parts) != 4:
            raise ValueError(f"Invalid cache key format: {cache_key}")

        return {
            "prefix": parts[0],
            "tool": parts[1],
            "params_hash": parts[2],
            "version": parts[3]
        }

key_generator = CacheKeyGenerator()
```

#### C. TTL Policies by Content Type

```python
from enum import Enum

class CacheTTL(Enum):
    """Cache TTL policies for different content types"""

    # Real-time content (changes rapidly)
    NEW_POSTS = 120  # 2 minutes
    HOT_POSTS = 300  # 5 minutes
    RISING_POSTS = 180  # 3 minutes

    # Historical content (stable)
    TOP_POSTS = 3600  # 1 hour
    SEARCH_RESULTS = 300  # 5 minutes

    # User/subreddit metadata (slow-changing)
    USER_INFO = 600  # 10 minutes
    SUBREDDIT_INFO = 3600  # 1 hour

    # Comments (relatively stable after initial activity)
    COMMENTS = 900  # 15 minutes

    # Trending/analysis (computationally expensive)
    TRENDING_TOPICS = 900  # 15 minutes
    SENTIMENT_ANALYSIS = 3600  # 1 hour

    @staticmethod
    def get_ttl(tool_name: str, params: dict) -> int:
        """Determine TTL based on tool and parameters"""
        if tool_name == "get_subreddit_posts":
            sort = params.get("sort", "hot")
            if sort == "new":
                return CacheTTL.NEW_POSTS.value
            elif sort == "hot":
                return CacheTTL.HOT_POSTS.value
            elif sort == "rising":
                return CacheTTL.RISING_POSTS.value
            else:  # top, controversial
                return CacheTTL.TOP_POSTS.value

        elif tool_name == "search_reddit":
            return CacheTTL.SEARCH_RESULTS.value

        elif tool_name == "get_post_comments":
            return CacheTTL.COMMENTS.value

        elif tool_name == "get_trending_topics":
            return CacheTTL.TRENDING_TOPICS.value

        elif tool_name == "get_user_info":
            return CacheTTL.USER_INFO.value

        elif tool_name == "get_subreddit_info":
            return CacheTTL.SUBREDDIT_INFO.value

        elif tool_name == "analyze_sentiment":
            return CacheTTL.SENTIMENT_ANALYSIS.value

        # Default fallback
        return 300  # 5 minutes
```

#### D. Cache Operations

```python
import pickle
from typing import Optional, Any

class CacheManager:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def get(self, key: str) -> Optional[dict]:
        """Retrieve cached value"""
        try:
            value = await self.redis.get(key)
            if value:
                # Parse stored data
                cached_data = json.loads(value)

                logger.debug(
                    "Cache hit",
                    key=key,
                    age_seconds=cached_data.get("age_seconds", 0)
                )

                return cached_data

            logger.debug("Cache miss", key=key)
            return None

        except Exception as e:
            logger.error(f"Cache get error: {e}", key=key)
            return None  # Fail open (don't break on cache errors)

    async def set(self, key: str, value: Any, ttl: int):
        """Store value in cache with TTL"""
        try:
            # Add metadata
            cached_data = {
                "data": value,
                "cached_at": datetime.utcnow().isoformat(),
                "ttl": ttl
            }

            # Store with expiration
            await self.redis.setex(
                key,
                ttl,
                json.dumps(cached_data)
            )

            logger.debug(
                "Cache set",
                key=key,
                ttl=ttl
            )

        except Exception as e:
            logger.error(f"Cache set error: {e}", key=key)
            # Fail silently (cache write failures shouldn't break requests)

    async def delete(self, key: str):
        """Delete cached value"""
        try:
            await self.redis.delete(key)
        except Exception as e:
            logger.error(f"Cache delete error: {e}", key=key)

    async def get_or_fetch(self, key: str, fetch_func, ttl: int) -> dict:
        """
        Get from cache or fetch and cache

        Args:
            key: Cache key
            fetch_func: Async function to fetch data if cache miss
            ttl: Time to live in seconds

        Returns:
            Cached or fetched data with metadata
        """
        # Try cache first
        cached = await self.get(key)
        if cached:
            cache_age = (
                datetime.utcnow() -
                datetime.fromisoformat(cached["cached_at"])
            ).total_seconds()

            return {
                "data": cached["data"],
                "metadata": {
                    "cached": True,
                    "cache_age_seconds": int(cache_age),
                    "ttl": cached["ttl"]
                }
            }

        # Cache miss - fetch data
        data = await fetch_func()

        # Store in cache
        await self.set(key, data, ttl)

        return {
            "data": data,
            "metadata": {
                "cached": False,
                "cache_age_seconds": 0,
                "ttl": ttl
            }
        }

cache_manager = CacheManager(cache.client)
```

#### E. Cache Warming Strategy

```python
class CacheWarmer:
    """Pre-populate cache with frequently accessed data"""

    WARM_SUBREDDITS = [
        "all", "popular", "news", "technology",
        "worldnews", "AskReddit", "programming"
    ]

    async def warm_cache(self):
        """Warm cache on server startup"""
        logger.info("Starting cache warming")

        tasks = []
        for subreddit in self.WARM_SUBREDDITS:
            # Warm hot posts
            tasks.append(self._warm_subreddit_posts(subreddit, "hot"))
            # Warm top posts
            tasks.append(self._warm_subreddit_posts(subreddit, "top"))

        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Cache warming completed")

    async def _warm_subreddit_posts(self, subreddit: str, sort: str):
        """Warm cache for specific subreddit"""
        try:
            params = {"subreddit": subreddit, "sort": sort, "limit": 25}
            key = key_generator.generate("get_subreddit_posts", params)
            ttl = CacheTTL.get_ttl("get_subreddit_posts", params)

            # Check if already cached
            if await cache_manager.get(key):
                return

            # Fetch and cache
            data = await self._fetch_subreddit_posts(params)
            await cache_manager.set(key, data, ttl)

            logger.debug(f"Warmed cache for r/{subreddit} ({sort})")

        except Exception as e:
            logger.warning(f"Cache warming failed for r/{subreddit}: {e}")

cache_warmer = CacheWarmer()
```

#### F. Cache Invalidation Logic

```python
class CacheInvalidator:
    """Handle cache invalidation scenarios"""

    async def invalidate_tool(self, tool_name: str):
        """Invalidate all cached entries for a tool"""
        pattern = f"reddit:{tool_name}:*"
        await self._delete_pattern(pattern)

    async def invalidate_subreddit(self, subreddit: str):
        """Invalidate all cached entries for a subreddit"""
        # This is complex - would need secondary indexing
        # For MVP: rely on TTL expiration
        pass

    async def invalidate_on_error(self, key: str):
        """Invalidate cache entry if data is stale/invalid"""
        await cache_manager.delete(key)

    async def _delete_pattern(self, pattern: str):
        """Delete all keys matching pattern"""
        cursor = 0
        while True:
            cursor, keys = await cache.client.scan(
                cursor=cursor,
                match=pattern,
                count=100
            )
            if keys:
                await cache.client.delete(*keys)
            if cursor == 0:
                break

cache_invalidator = CacheInvalidator()
```

---

### 2.4 Tool Implementation Layer

#### Tool 1: search_reddit

**Input Validation:**
```python
class SearchRedditInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    subreddit: Optional[str] = Field(None, pattern="^[A-Za-z0-9_]+$")
    time_filter: Literal["hour", "day", "week", "month", "year", "all"] = "week"
    sort: Literal["relevance", "hot", "top", "new", "comments"] = "relevance"
    limit: int = Field(25, ge=1, le=100)
```

**Business Logic:**
```python
@mcp.tool()
async def search_reddit(params: SearchRedditInput) -> dict:
    """Search Reddit for posts matching query"""

    # Generate cache key
    cache_key = key_generator.generate("search_reddit", params.dict())
    ttl = CacheTTL.get_ttl("search_reddit", params.dict())

    # Define fetch function
    async def fetch_results():
        reddit = reddit_client.get_client()

        # Build search query
        if params.subreddit:
            search_target = reddit.subreddit(params.subreddit)
        else:
            search_target = reddit.subreddit("all")

        # Execute search
        results = await retry_handler.execute(
            search_target.search,
            query=params.query,
            sort=params.sort,
            time_filter=params.time_filter,
            limit=params.limit
        )

        # Normalize results
        normalized = [
            normalizer.normalize_post(post)
            for post in results
        ]

        return {
            "results": normalized,
            "query": params.query,
            "total_found": len(normalized)
        }

    # Get from cache or fetch
    response = await cache_manager.get_or_fetch(cache_key, fetch_results, ttl)

    # Add rate limit info
    response["metadata"]["rate_limit_remaining"] = rate_limiter.get_remaining()

    return response
```

**Reddit API Calls:**
- Endpoint: `/search.json?q={query}&t={time}&sort={sort}&limit={limit}`
- Rate: 1 API call per request

**Caching Strategy:**
- TTL: 5 minutes (search results change moderately)
- Key pattern: `reddit:search_reddit:{hash}:v1`

**Error Handling:**
- Invalid query → ValidationError (422)
- Subreddit not found → Return empty results
- Rate limit → RateLimitError with retry_after

---

#### Tool 2: get_subreddit_posts

**Input Validation:**
```python
class GetSubredditPostsInput(BaseModel):
    subreddit: str = Field(..., pattern="^[A-Za-z0-9_]+$")
    sort: Literal["hot", "new", "top", "rising", "controversial"] = "hot"
    time_filter: Optional[Literal["hour", "day", "week", "month", "year", "all"]] = None
    limit: int = Field(25, ge=1, le=100)

    @validator('time_filter')
    def validate_time_filter(cls, v, values):
        if values.get('sort') in ['top', 'controversial'] and not v:
            raise ValueError("time_filter required for top/controversial")
        return v
```

**Business Logic:**
```python
@mcp.tool()
async def get_subreddit_posts(params: GetSubredditPostsInput) -> dict:
    """Get posts from a specific subreddit"""

    cache_key = key_generator.generate("get_subreddit_posts", params.dict())
    ttl = CacheTTL.get_ttl("get_subreddit_posts", params.dict())

    async def fetch_posts():
        reddit = reddit_client.get_client()
        subreddit = reddit.subreddit(params.subreddit)

        # Select sort method
        if params.sort == "hot":
            posts = subreddit.hot(limit=params.limit)
        elif params.sort == "new":
            posts = subreddit.new(limit=params.limit)
        elif params.sort == "top":
            posts = subreddit.top(time_filter=params.time_filter, limit=params.limit)
        elif params.sort == "rising":
            posts = subreddit.rising(limit=params.limit)
        elif params.sort == "controversial":
            posts = subreddit.controversial(time_filter=params.time_filter, limit=params.limit)

        # Execute with retry
        posts_list = await retry_handler.execute(lambda: list(posts))

        # Normalize
        normalized = [normalizer.normalize_post(post) for post in posts_list]

        return {
            "subreddit": params.subreddit,
            "sort": params.sort,
            "posts": normalized
        }

    response = await cache_manager.get_or_fetch(cache_key, fetch_posts, ttl)
    response["metadata"]["rate_limit_remaining"] = rate_limiter.get_remaining()

    return response
```

**Reddit API Calls:**
- Endpoint: `/r/{subreddit}/{sort}.json`
- Rate: 1 API call per request

**Caching Strategy:**
- TTL: Variable by sort type (2min for new, 5min for hot, 1h for top)
- High cache hit rate expected for popular subreddits

---

#### Tool 3: get_post_comments

**Business Logic:**
```python
@mcp.tool()
async def get_post_comments(params: GetPostCommentsInput) -> dict:
    """Get all comments from a Reddit post"""

    cache_key = key_generator.generate("get_post_comments", params.dict())
    ttl = CacheTTL.COMMENTS.value

    async def fetch_comments():
        reddit = reddit_client.get_client()

        # Extract post ID (handle t3_ prefix and URLs)
        post_id = params.post_id.replace("t3_", "")
        submission = reddit.submission(id=post_id)

        # Fetch with comment sort
        submission.comment_sort = params.sort

        # Expand all comment threads
        await retry_handler.execute(submission.comments.replace_more, limit=0)

        # Flatten comment forest
        all_comments = submission.comments.list()

        # Filter by max_depth if specified
        if params.max_depth > 0:
            all_comments = [c for c in all_comments if c.depth <= params.max_depth]

        # Build nested structure
        comments_tree = self._build_comment_tree(all_comments)

        return {
            "post": {
                "id": submission.id,
                "title": submission.title,
                "num_comments": submission.num_comments
            },
            "comments": comments_tree,
            "metadata": {
                "total_comments": len(all_comments),
                "returned_comments": len(comments_tree)
            }
        }

    response = await cache_manager.get_or_fetch(cache_key, fetch_comments, ttl)
    return response

def _build_comment_tree(comments: list) -> list:
    """Build nested comment structure"""
    comment_map = {}
    root_comments = []

    # First pass: create all comment nodes
    for comment in comments:
        normalized = normalizer.normalize_comment(comment)
        normalized["replies"] = []
        comment_map[comment.id] = normalized

    # Second pass: build tree
    for comment in comments:
        if comment.parent_id.startswith("t3_"):  # Top-level comment
            root_comments.append(comment_map[comment.id])
        else:
            parent_id = comment.parent_id.replace("t1_", "")
            if parent_id in comment_map:
                comment_map[parent_id]["replies"].append(comment_map[comment.id])

    return root_comments
```

**Reddit API Calls:**
- Endpoint: `/r/{subreddit}/comments/{id}.json`
- Additional: `/api/morechildren` (for expanding threads)
- Rate: 1-5 API calls (depends on thread size)

**Caching Strategy:**
- TTL: 15 minutes
- Comments are relatively stable after initial activity

---

#### Tool 4: get_trending_topics

**Business Logic:**
```python
@mcp.tool()
async def get_trending_topics(params: GetTrendingTopicsInput) -> dict:
    """Identify trending topics on Reddit"""

    cache_key = key_generator.generate("get_trending_topics", params.dict())
    ttl = CacheTTL.TRENDING_TOPICS.value

    async def analyze_trends():
        reddit = reddit_client.get_client()

        # Determine scope
        if params.scope == "subreddit":
            target = reddit.subreddit(params.subreddit)
        else:
            target = reddit.subreddit("all")

        # Fetch recent posts (last hour or day)
        if params.timeframe == "hour":
            posts = target.new(limit=100)
        else:
            posts = target.top(time_filter="day", limit=200)

        posts_list = await retry_handler.execute(lambda: list(posts))

        # Extract keywords from titles
        keyword_freq = {}
        keyword_posts = {}

        for post in posts_list:
            # Tokenize and extract keywords (simple approach)
            keywords = self._extract_keywords(post.title)

            for keyword in keywords:
                keyword_freq[keyword] = keyword_freq.get(keyword, 0) + 1
                if keyword not in keyword_posts:
                    keyword_posts[keyword] = []
                keyword_posts[keyword].append(post)

        # Calculate trending score (frequency + recency)
        trending = []
        for keyword, count in keyword_freq.items():
            if count >= 3:  # Minimum threshold
                sample_posts = keyword_posts[keyword][:3]

                trending.append({
                    "keyword": keyword,
                    "mentions": count,
                    "growth_rate": self._calculate_growth(keyword, posts_list),
                    "sentiment": await self._quick_sentiment(keyword, sample_posts),
                    "top_subreddits": self._top_subreddits(keyword_posts[keyword]),
                    "sample_posts": [
                        {
                            "id": p.id,
                            "title": p.title,
                            "score": p.score
                        }
                        for p in sample_posts
                    ]
                })

        # Sort by mentions
        trending.sort(key=lambda x: x["mentions"], reverse=True)

        return {
            "trending_topics": trending[:params.limit],
            "metadata": {
                "analysis_timestamp": int(datetime.utcnow().timestamp()),
                "posts_analyzed": len(posts_list),
                "unique_keywords": len(keyword_freq)
            }
        }

    response = await cache_manager.get_or_fetch(cache_key, analyze_trends, ttl)
    return response
```

**Reddit API Calls:**
- Endpoint: `/r/{subreddit}/new.json` or `/r/{subreddit}/top.json`
- Rate: 1-2 API calls

**Caching Strategy:**
- TTL: 15 minutes (computationally expensive)
- High value for cache hits

---

#### Tool 5: analyze_sentiment

**Business Logic:**
```python
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

class SentimentAnalyzer:
    def __init__(self):
        self.analyzer = SentimentIntensityAnalyzer()

    def analyze_text(self, text: str) -> dict:
        """Analyze sentiment of text using VADER"""
        scores = self.analyzer.polarity_scores(text)

        # Determine label
        if scores['compound'] >= 0.05:
            label = "positive"
        elif scores['compound'] <= -0.05:
            label = "negative"
        else:
            label = "neutral"

        return {
            "score": scores['compound'],
            "label": label,
            "confidence": max(scores['pos'], scores['neu'], scores['neg']),
            "distribution": {
                "positive": scores['pos'],
                "neutral": scores['neu'],
                "negative": scores['neg']
            }
        }

sentiment_analyzer = SentimentAnalyzer()

@mcp.tool()
async def analyze_sentiment(params: AnalyzeSentimentInput) -> dict:
    """Analyze sentiment of Reddit content"""

    cache_key = key_generator.generate("analyze_sentiment", params.dict())
    ttl = CacheTTL.SENTIMENT_ANALYSIS.value

    async def perform_analysis():
        # Fetch content based on content_type
        if params.content_type == "post":
            content = await self._fetch_post(params.content_id)
            texts = [content["title"], content.get("selftext", "")]

        elif params.content_type == "comment":
            content = await self._fetch_comment(params.content_id)
            texts = [content["body"]]

        elif params.content_type == "search_results":
            results = await search_reddit({
                "query": params.content_id,
                "time_filter": params.time_filter,
                "limit": 100
            })
            texts = [
                f"{r['title']} {r.get('selftext', '')}"
                for r in results["data"]["results"]
            ]

        # Analyze each text
        sentiments = [sentiment_analyzer.analyze_text(t) for t in texts if t]

        # Aggregate results
        avg_score = sum(s["score"] for s in sentiments) / len(sentiments)

        label_counts = {"positive": 0, "neutral": 0, "negative": 0}
        for s in sentiments:
            label_counts[s["label"]] += 1

        return {
            "overall_sentiment": {
                "score": round(avg_score, 3),
                "label": max(label_counts, key=label_counts.get),
                "confidence": round(max(label_counts.values()) / len(sentiments), 2),
                "distribution": {
                    k: round(v / len(sentiments), 2)
                    for k, v in label_counts.items()
                }
            },
            "analyzed_items": len(sentiments)
        }

    response = await cache_manager.get_or_fetch(cache_key, perform_analysis, ttl)
    return response
```

**Reddit API Calls:**
- Variable: 0-2 API calls (depending on cached content)

**Caching Strategy:**
- TTL: 1 hour (sentiment doesn't change for historical content)
- NLP processing is fast (VADER is rule-based)

---

#### Tool 6-8: get_user_info, get_subreddit_info, watch_keywords

Similar implementation patterns:
- Input validation with Pydantic
- Cache-first strategy
- Reddit API integration via PRAW
- Response normalization
- Error handling

**watch_keywords** is special:
- Requires persistent storage (Apify Dataset)
- Background job processing
- Webhook/notification system (future enhancement)

---

## 3. Data Models

### 3.1 Input Schemas (JSON Schema Format)

All tool inputs are defined using Pydantic models, which automatically generate JSON Schema:

```python
from pydantic import BaseModel, Field, validator
from typing import Optional, Literal, List

# Example: search_reddit input schema
class SearchRedditInput(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Search query or keywords",
        example="artificial intelligence"
    )
    subreddit: Optional[str] = Field(
        None,
        pattern="^[A-Za-z0-9_]+$",
        description="Limit search to specific subreddit",
        example="technology"
    )
    time_filter: Literal["hour", "day", "week", "month", "year", "all"] = Field(
        "week",
        description="Time range for search results"
    )
    sort: Literal["relevance", "hot", "top", "new", "comments"] = Field(
        "relevance",
        description="Sort order for results"
    )
    limit: int = Field(
        25,
        ge=1,
        le=100,
        description="Maximum number of results to return"
    )

    class Config:
        schema_extra = {
            "example": {
                "query": "machine learning",
                "subreddit": "MachineLearning",
                "time_filter": "week",
                "sort": "top",
                "limit": 50
            }
        }

# Auto-generate JSON Schema
search_reddit_schema = SearchRedditInput.schema_json(indent=2)
```

### 3.2 Output Schemas

```python
from typing import List, Dict, Any
from datetime import datetime

class RedditPost(BaseModel):
    id: str
    type: Literal["post"]
    title: str
    author: str
    subreddit: str
    created_utc: int
    score: int
    upvote_ratio: float
    num_comments: int
    url: str
    permalink: str
    selftext: str
    link_flair_text: Optional[str]
    is_self: bool
    is_video: bool
    over_18: bool
    spoiler: bool
    stickied: bool

class RedditComment(BaseModel):
    id: str
    type: Literal["comment"]
    author: str
    body: str
    score: int
    created_utc: int
    depth: int
    parent_id: str
    is_submitter: bool
    stickied: bool
    distinguished: Optional[str]
    replies: List['RedditComment'] = []

class ResponseMetadata(BaseModel):
    cached: bool
    cache_age_seconds: int
    ttl: int
    rate_limit_remaining: int
    execution_time_ms: float
    reddit_api_calls: int

class SearchRedditOutput(BaseModel):
    results: List[RedditPost]
    query: str
    total_found: int
    metadata: ResponseMetadata

class SentimentAnalysis(BaseModel):
    score: float = Field(..., ge=-1, le=1)
    label: Literal["positive", "neutral", "negative"]
    confidence: float = Field(..., ge=0, le=1)
    distribution: Dict[str, float]

class AnalyzeSentimentOutput(BaseModel):
    overall_sentiment: SentimentAnalysis
    analyzed_items: int
    key_themes: Optional[List[Dict[str, Any]]]
    metadata: ResponseMetadata
```

### 3.3 Cache Data Structures

```python
class CachedResponse(BaseModel):
    """Structure stored in Redis"""
    data: Any  # Actual response data
    cached_at: str  # ISO timestamp
    ttl: int  # Original TTL in seconds
    version: str = "v1"  # Schema version

class CacheMetrics(BaseModel):
    """Cache performance metrics"""
    total_requests: int
    cache_hits: int
    cache_misses: int
    hit_rate: float
    avg_cache_age_seconds: float

    @property
    def cache_hit_percentage(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.cache_hits / self.total_requests) * 100
```

### 3.4 Internal State Models

```python
class RateLimitState(BaseModel):
    """Track rate limit state"""
    calls_made: int
    window_start: datetime
    remaining_calls: int
    reset_at: datetime

class RequestQueueItem(BaseModel):
    """Item in request queue"""
    request_hash: str
    endpoint: str
    params: Dict[str, Any]
    priority: int
    queued_at: datetime
    status: Literal["queued", "processing", "completed", "failed"]

class OAuthTokenState(BaseModel):
    """OAuth token state"""
    access_token: str
    refresh_token: Optional[str]
    expires_at: datetime
    scopes: List[str]
```

---

## 4. Component Interaction Flows

### 4.1 Tool Execution Flow (Happy Path)

```
┌─────────┐
│ Client  │
└────┬────┘
     │ 1. JSON-RPC Request
     │    {"method": "tools/call", "params": {"name": "search_reddit", ...}}
     ▼
┌─────────────────┐
│  FastMCP Server │
└────┬────────────┘
     │ 2. Route to tool handler
     ▼
┌──────────────────┐
│ Input Validation │ (Pydantic)
└────┬─────────────┘
     │ 3. Validate params
     ▼
┌──────────────────┐
│ Middleware Stack │
└────┬─────────────┘
     │ 4. Check auth, rate limits
     ▼
┌──────────────────┐
│  Tool Function   │ (search_reddit)
└────┬─────────────┘
     │ 5. Generate cache key
     │    redis:search_reddit:a3f8d9c2:v1
     ▼
┌──────────────────┐
│  Cache Manager   │
└────┬─────────────┘
     │ 6. Check Redis
     ▼
    ┌─┴─┐
    │ ? │ Cache Hit?
    └─┬─┘
      │
      ├─── YES ────────────────────────┐
      │                                 │
      │                                 ▼
      │                         ┌──────────────┐
      │                         │ Return Cache │
      │                         │  + metadata  │
      │                         └──────┬───────┘
      │                                │
      │                                ├─────► Response
      │
      └─── NO ─────────────────────────┐
                                       │
                                       ▼
                              ┌─────────────────┐
                              │ Rate Limiter    │
                              │ (Token Bucket)  │
                              └────┬────────────┘
                                   │ 7. Acquire token (wait if needed)
                                   ▼
                              ┌─────────────────┐
                              │ Reddit API      │
                              │ Client (PRAW)   │
                              └────┬────────────┘
                                   │ 8. Execute request
                                   │    - OAuth2 auth
                                   │    - Retry with backoff
                                   ▼
                              ┌─────────────────┐
                              │ Reddit API      │
                              └────┬────────────┘
                                   │ 9. HTTP 200 + JSON
                                   ▼
                              ┌─────────────────┐
                              │ Response        │
                              │ Normalizer      │
                              └────┬────────────┘
                                   │ 10. Normalize to standard format
                                   ▼
                              ┌─────────────────┐
                              │ Cache Manager   │
                              └────┬────────────┘
                                   │ 11. Store in Redis (TTL=5min)
                                   ▼
                              ┌─────────────────┐
                              │ Add Metadata    │
                              │ - cached: false │
                              │ - api_calls: 1  │
                              └────┬────────────┘
                                   │
                                   └─────► Response
                                           │
                                           ▼
                                   ┌─────────────────┐
                                   │ Monitoring      │
                                   │ - Log metrics   │
                                   │ - Apify Dataset │
                                   └─────────────────┘
                                           │
                                           ▼
                                   ┌─────────────────┐
                                   │ Client          │
                                   │ (Receives data) │
                                   └─────────────────┘
```

**Text Sequence:**
1. Client sends JSON-RPC request to MCP server
2. FastMCP routes request to `search_reddit` tool
3. Pydantic validates input parameters
4. Middleware checks authentication and rate limits
5. Tool generates cache key: `reddit:search_reddit:{hash}:v1`
6. Cache Manager checks Redis for cached data
7. **Cache Hit:** Return cached response with metadata (age, TTL)
8. **Cache Miss:** Acquire rate limit token (may wait)
9. PRAW executes Reddit API request with OAuth2
10. Reddit API returns JSON response
11. Response Normalizer converts to standard format
12. Cache Manager stores result in Redis with TTL
13. Add metadata (cached: false, api_calls: 1)
14. Return response to client
15. Log metrics to monitoring system

---

### 4.2 Rate Limit Handling Flow

```
┌─────────────┐
│ Tool Exec   │
└──────┬──────┘
       │ Request needs API call
       ▼
┌──────────────────┐
│ Rate Limiter     │
│ (Token Bucket)   │
└──────┬───────────┘
       │ Check capacity
       ▼
   ┌───┴───┐
   │ Calls │ < 100?
   │ in    │
   │ window│
   └───┬───┘
       │
       ├─── YES ──────────────────────┐
       │                              │
       │                              ▼
       │                      ┌───────────────┐
       │                      │ Grant Token   │
       │                      │ - Add timestamp│
       │                      │ - Execute call│
       │                      └───────┬───────┘
       │                              │
       │                              └────► Continue
       │
       └─── NO ───────────────────────┐
                                      │
                                      ▼
                              ┌──────────────────┐
                              │ Calculate Wait   │
                              │ time = (oldest   │
                              │  call + 60s) -   │
                              │  now             │
                              └────┬─────────────┘
                                   │
                                   ▼
                              ┌──────────────────┐
                              │ Log Warning      │
                              │ "Rate limit hit, │
                              │  waiting Xs"     │
                              └────┬─────────────┘
                                   │
                                   ▼
                              ┌──────────────────┐
                              │ async sleep(X)   │
                              └────┬─────────────┘
                                   │
                                   ▼
                              ┌──────────────────┐
                              │ Retry acquire()  │
                              └────┬─────────────┘
                                   │
                                   └────► Continue

┌─────────────────────────────────────────────────┐
│ Alternative: Queue Request                      │
│                                                  │
│ If rate limit hit:                              │
│ 1. Add request to priority queue                │
│ 2. Return to client: "Queued, try again in Xs" │
│ 3. Background worker processes queue            │
│ 4. Client polls for result                      │
└─────────────────────────────────────────────────┘
```

**Rate Limit Error Response:**
```json
{
  "jsonrpc": "2.0",
  "id": 123,
  "error": {
    "code": -32000,
    "message": "Rate limit exceeded",
    "data": {
      "retry_after_seconds": 15,
      "rate_limit_tier": "free",
      "calls_made": 100,
      "window_reset_at": "2025-11-05T12:35:00Z"
    }
  }
}
```

---

### 4.3 Cache Hit/Miss Scenarios

**Scenario A: Cache Hit**
```
Request → Cache Check → Redis GET → Found
          ↓
          Parse cached data
          ↓
          Calculate age (now - cached_at)
          ↓
          Return {data, metadata: {cached: true, age: 120s}}

Total time: ~10-50ms
Reddit API calls: 0
```

**Scenario B: Cache Miss**
```
Request → Cache Check → Redis GET → Not Found
          ↓
          Execute fetch function
          ↓
          Rate limit check (may wait)
          ↓
          Reddit API call (1-3s)
          ↓
          Normalize response
          ↓
          Store in Redis (SET key value EX ttl)
          ↓
          Return {data, metadata: {cached: false, age: 0}}

Total time: ~1-5s
Reddit API calls: 1-5 (depending on tool)
```

**Scenario C: Cache Expired**
```
Request → Cache Check → Redis GET → Found but TTL expired
          ↓
          Redis auto-deleted (already gone)
          ↓
          Treat as Cache Miss
          ↓
          [Same as Scenario B]
```

**Scenario D: Cache Error (Fail Open)**
```
Request → Cache Check → Redis GET → Connection Error
          ↓
          Log error
          ↓
          Treat as Cache Miss (don't block request)
          ↓
          Execute fetch function
          ↓
          Try to cache (fail silently if Redis still down)
          ↓
          Return response (without cache metadata)

Note: System continues to function even if Redis is down
```

---

### 4.4 Error Recovery Flow

```
┌─────────────┐
│ Tool Exec   │
└──────┬──────┘
       │
       ▼
   Try Block
       │
       ├──► ValidationError (422)
       │    ↓
       │    Return JSON-RPC error {code: -32602, message: "Invalid params"}
       │
       ├──► RateLimitError (429)
       │    ↓
       │    Calculate retry_after from rate limiter
       │    ↓
       │    Return JSON-RPC error {code: -32000, data: {retry_after_seconds}}
       │
       ├──► RedditAPIError (500/502/503)
       │    ↓
       │    Check retry attempts
       │    ↓
       │    ┌─ Attempt < 3 ───► Exponential backoff
       │    │                    (wait 2^attempt seconds)
       │    │                    ↓
       │    │                    Retry request
       │    │
       │    └─ Attempt >= 3 ───► Return JSON-RPC error
       │                         {code: -32001, message: "Reddit API unavailable"}
       │
       ├──► NotFoundError (404)
       │    ↓
       │    Return empty results (not an error)
       │    ↓
       │    Return {results: [], metadata: {...}}
       │
       ├──► ForbiddenError (403)
       │    ↓
       │    Check if auth token expired
       │    ↓
       │    ┌─ Token expired ───► Refresh token
       │    │                      ↓
       │    │                      Retry request (once)
       │    │
       │    └─ Permission denied ─► Return JSON-RPC error
       │                           {code: -32001, message: "Access forbidden"}
       │
       ├──► CacheError
       │    ↓
       │    Log warning (cache unavailable)
       │    ↓
       │    Continue without cache (fail open)
       │    ↓
       │    Execute request normally
       │
       └──► Unexpected Error
            ↓
            Log full traceback
            ↓
            Return generic JSON-RPC error
            {code: -32603, message: "Internal server error"}

┌─────────────────────────────────────────────────┐
│ Circuit Breaker Pattern (Future Enhancement)    │
│                                                  │
│ Track Reddit API error rate:                    │
│ - If error rate > 50% over 1 minute             │
│ - Open circuit (stop calling API)               │
│ - Return cached data (even if stale)            │
│ - Retry after 30 seconds                        │
│ - Close circuit when healthy                    │
└─────────────────────────────────────────────────┘
```

---

## 5. Technology Stack Justification

### 5.1 Python 3.11 (Language)

**Why chosen:**
- **MCP SDK Support**: Official `mcp` Python SDK from Anthropic
- **Reddit API Library**: PRAW is the most mature Reddit API wrapper (Python-native)
- **Data Science Ecosystem**: VADER sentiment analysis, NLP tools
- **Async/Await**: Native async support (asyncio) for concurrent operations
- **Type Safety**: Type hints + Pydantic for robust validation
- **Apify SDK**: Full support for Apify Actor development

**Alternatives considered:**
- JavaScript/TypeScript: Good MCP support, but PRAW equivalent (Snoowrap) is unmaintained
- Go: Fast but less mature MCP ecosystem, no VADER equivalent

**Performance characteristics:**
- Async I/O: Handle 100+ concurrent requests
- Memory efficient: ~50-100MB base footprint
- Fast enough: <1ms overhead vs C/Rust for I/O-bound tasks

---

### 5.2 FastMCP (MCP Framework)

**Why chosen:**
- **Official Framework**: Developed by Anthropic specifically for Python MCP servers
- **Minimal Boilerplate**: Decorator-based tool registration
- **Auto-validation**: Integrates with Pydantic for input/output validation
- **Transport Agnostic**: Supports stdio (local) and HTTP/SSE (remote)
- **Active Development**: Regular updates, aligned with MCP spec changes

**Example benefit:**
```python
# Without FastMCP: 50+ lines of JSON-RPC handling
# With FastMCP:
@mcp.tool()
def search_reddit(query: str) -> dict:
    return {"results": []}  # Framework handles everything else
```

**Alternatives considered:**
- Custom JSON-RPC implementation: Too much overhead
- Generic RPC frameworks: Not MCP-specific

---

### 5.3 PRAW (Reddit API Client)

**Why chosen:**
- **Battle-tested**: 10+ years of development, used by thousands of apps
- **Auto Rate Limiting**: Built-in 30s caching and rate limit handling
- **OAuth2 Handling**: Automatic token refresh
- **Pythonic API**: Intuitive, well-documented
- **Active Maintenance**: Regular updates for Reddit API changes

**Example:**
```python
# PRAW: 3 lines
reddit = praw.Reddit(client_id=..., client_secret=...)
posts = reddit.subreddit("technology").hot(limit=25)

# Manual approach: 100+ lines (OAuth, pagination, error handling)
```

**Alternatives considered:**
- Raw requests: Too much manual work
- Snoowrap (JS): Unmaintained, last update 4 years ago

**Performance:**
- Handles pagination automatically
- Connection pooling built-in
- Lazy loading (doesn't fetch data until accessed)

---

### 5.4 Redis (Cache)

**Why chosen:**
- **Speed**: Sub-millisecond reads (avg 0.2ms)
- **TTL Support**: Built-in expiration (perfect for time-based caching)
- **Atomic Operations**: SET/GET are thread-safe
- **Persistence Options**: Can survive restarts (AOF/RDB)
- **Scalability**: Handles millions of keys easily
- **Apify Compatible**: Easy to deploy Redis Cloud instance

**Cache performance:**
```
Cache Hit:  10-50ms   (Redis GET + deserialization)
Cache Miss: 1,000-3,000ms  (Reddit API call)
Speedup:    20-300x faster
```

**Alternatives considered:**
- In-memory dict: Lost on restart, no TTL, not distributed
- Memcached: No persistence, less flexible data structures
- DynamoDB: Higher latency (~10ms), more expensive

**Configuration:**
- Connection pooling: 20 connections
- Maxmemory policy: `allkeys-lru` (evict least recently used)
- Persistence: AOF (append-only file) for durability

---

### 5.5 Pydantic (Data Validation)

**Why chosen:**
- **Type Safety**: Runtime validation of inputs/outputs
- **Auto JSON Schema**: Generate OpenAPI-compatible schemas
- **FastMCP Integration**: Native support in FastMCP
- **Error Messages**: Clear, actionable validation errors
- **Performance**: Fast (uses Rust under the hood in v2)

**Example:**
```python
class SearchInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(25, ge=1, le=100)

# Auto-validates:
try:
    params = SearchInput(query="", limit=500)  # Fails validation
except ValidationError as e:
    # Returns: {"query": ["ensure this value has at least 1 characters"]}
```

**Benefits:**
- Prevents invalid data from reaching Reddit API
- Generates documentation automatically
- Type hints improve IDE autocomplete

---

### 5.6 VADER (Sentiment Analysis)

**Why chosen:**
- **Speed**: Rule-based (no ML model), <1ms per text
- **Social Media Optimized**: Designed for Twitter/Reddit (handles slang, emojis)
- **No Training**: Works out-of-the-box
- **Lightweight**: 1MB library, no GPU needed
- **Academic Credibility**: 5,000+ citations

**Performance:**
```python
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

analyzer = SentimentIntensityAnalyzer()
analyzer.polarity_scores("This is amazing!")
# {'neg': 0.0, 'neu': 0.344, 'pos': 0.656, 'compound': 0.6588}
# Time: <1ms
```

**Alternatives considered:**
- Transformer models (BERT): 100-1000x slower, requires GPU
- TextBlob: Less accurate for social media
- Cloud APIs (AWS Comprehend): Expensive, adds latency

**Limitations:**
- No context understanding (sarcasm detection poor)
- English-only
- Good enough for MVP, can enhance later

---

### 5.7 Technology Stack Summary Table

| Component | Technology | Version | Purpose | Key Benefit |
|-----------|-----------|---------|---------|-------------|
| Language | Python | 3.11+ | Runtime | Async support, rich ecosystem |
| MCP Framework | FastMCP | 1.0+ | Server | Minimal boilerplate, official |
| Reddit Client | PRAW | 7.7+ | API | Auto rate limiting, OAuth2 |
| Cache | Redis | 7.0+ | Performance | Sub-ms reads, TTL support |
| Validation | Pydantic | 2.0+ | Data | Runtime validation, JSON Schema |
| Sentiment | VADER | 3.3+ | NLP | Fast, social media optimized |
| HTTP Server | Uvicorn | 0.25+ | ASGI | High performance async |
| Logging | structlog | 23.0+ | Observability | Structured JSON logs |
| Testing | pytest | 7.4+ | Quality | Async test support |
| Deployment | Apify Actor | Latest | Hosting | Standby mode, pay-per-event |

**Total Dependencies:** ~15 packages (lightweight)
**Docker Image Size:** ~200MB (Alpine-based)
**Memory Footprint:** ~100-150MB (idle)
**Startup Time:** <2 seconds

---

## 6. Performance & Scalability

### 6.1 Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Latency (cached) | <500ms | p95 |
| Latency (uncached) | <3s | p95 |
| Cache hit rate | >75% | Overall |
| Throughput | 100 req/min | Reddit API limit |
| Availability | 99.5% | Monthly uptime |
| Error rate | <1% | Of total requests |

### 6.2 Scalability Analysis

**Current Architecture (Single Instance):**
- Reddit API: 100 QPM limit
- With 75% cache hit: 400 effective QPM
- Avg user: 10 requests/day
- **Capacity: ~1,700 DAU** (400 * 60 * 24 / 10)

**Scaling Strategies:**

1. **Horizontal Scaling (Multiple Reddit Accounts)**
   - Deploy 5 instances with different Reddit API keys
   - Capacity: 8,500 DAU
   - Cost: $0 (free tier per account)

2. **Cache Optimization**
   - Improve cache hit rate to 90%
   - Capacity doubles: 3,400 DAU per instance

3. **Paid Reddit API Tier**
   - $0.24 per 1K calls = unlimited QPM
   - Capacity: Unlimited (budget-dependent)

### 6.3 Bottleneck Analysis

**Primary Bottleneck:** Reddit API rate limit (100 QPM)
- Mitigation: Aggressive caching (75%+ hit rate)
- Fallback: Queue requests, return "retry in X seconds"

**Secondary Bottleneck:** Redis throughput
- Redis capacity: 100K ops/sec
- Our usage: <100 ops/sec
- Not a concern until 1,000x scale

**Tertiary Bottleneck:** Sentiment analysis (NLP)
- VADER throughput: 10K texts/sec
- Our usage: <100 texts/sec
- Not a concern

---

## 7. Security Architecture

### 7.1 Authentication & Authorization

**Reddit API Credentials:**
- Stored in Apify Actor secrets (encrypted at rest)
- Rotated quarterly
- Never logged or exposed in responses

**User Authentication:**
- Phase 1 (MVP): No user auth (open access)
- Phase 2 (v1.0): API key per user
- Phase 3 (v2.0): OAuth2 for user-specific operations

**Authorization Levels:**
```python
class AccessTier(Enum):
    FREE = "free"       # 10K calls/month
    PRO = "pro"         # 100K calls/month
    BUSINESS = "business"  # 2M calls/month
    ENTERPRISE = "enterprise"  # Unlimited
```

### 7.2 Input Validation & Sanitization

**All inputs validated:**
- Length limits (prevent DoS)
- Pattern matching (prevent injection)
- Type checking (prevent crashes)

**Example:**
```python
class SearchInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)

    @validator('query')
    def sanitize(cls, v):
        # Remove null bytes
        v = v.replace('\x00', '')
        # Strip whitespace
        v = v.strip()
        # Limit to printable characters
        v = ''.join(c for c in v if c.isprintable())
        return v
```

### 7.3 Rate Limiting (User-Level)

```python
class UserRateLimiter:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def check_limit(self, user_id: str, tier: AccessTier) -> bool:
        """Check if user exceeded rate limit"""
        key = f"rate_limit:{user_id}:{datetime.utcnow().strftime('%Y-%m')}"

        # Get current usage
        usage = await self.redis.get(key) or 0

        # Check tier limit
        tier_limits = {
            AccessTier.FREE: 10_000,
            AccessTier.PRO: 100_000,
            AccessTier.BUSINESS: 2_000_000,
            AccessTier.ENTERPRISE: float('inf')
        }

        if int(usage) >= tier_limits[tier]:
            raise RateLimitError(f"Monthly limit exceeded")

        # Increment usage
        await self.redis.incr(key)
        await self.redis.expire(key, 31 * 24 * 60 * 60)  # 31 days

        return True
```

### 7.4 Data Privacy

**PII Handling:**
- No user data stored (stateless)
- Reddit usernames treated as public (per Reddit ToS)
- No email/IP logging
- GDPR-compliant (no personal data retention)

**Caching Privacy:**
- Cache keys hashed (don't expose query content)
- TTL-based expiration (no long-term storage)
- No cross-user data leakage

---

## 8. Deployment Architecture

### 8.1 Apify Actor Configuration

**Dockerfile:**
```dockerfile
FROM apify/actor-python:3.11

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./
CMD ["python", "src/main.py"]
```

**actor.json:**
```json
{
  "actorSpecification": 1,
  "name": "reddit-mcp-server",
  "title": "Reddit MCP Server",
  "version": "1.0.0",
  "usesStandbyMode": true,
  "webServerMcpPath": "/mcp",
  "environmentVariables": {
    "REDDIT_CLIENT_ID": {
      "type": "secret",
      "required": true
    },
    "REDDIT_CLIENT_SECRET": {
      "type": "secret",
      "required": true
    },
    "REDIS_URL": {
      "type": "string",
      "required": true
    }
  }
}
```

### 8.2 Infrastructure Components

```
┌─────────────────────────────────────────────────┐
│ Apify Platform                                  │
│                                                  │
│  ┌────────────────────────────────────────┐    │
│  │ Actor Instance (Standby Mode)          │    │
│  │ - Always-on HTTP endpoint               │    │
│  │ - Auto-scaling (1-10 instances)        │    │
│  │ - Health checks every 30s              │    │
│  └────────────────────────────────────────┘    │
│                                                  │
│  ┌────────────────────────────────────────┐    │
│  │ Key-Value Store (Actor secrets)        │    │
│  │ - Reddit credentials                    │    │
│  │ - API keys                              │    │
│  └────────────────────────────────────────┘    │
│                                                  │
│  ┌────────────────────────────────────────┐    │
│  │ Dataset (Analytics)                     │    │
│  │ - Request logs                          │    │
│  │ - Performance metrics                   │    │
│  └────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
         │
         │ Network
         ▼
┌─────────────────────────────────────────────────┐
│ Redis Cloud                                     │
│ - Plan: 250MB (Free tier)                      │
│ - Region: us-east-1                             │
│ - Eviction: allkeys-lru                         │
│ - Persistence: AOF                              │
└─────────────────────────────────────────────────┘
```

### 8.3 Monitoring & Observability

**Metrics Tracked:**
- Request count (by tool, by user)
- Latency (p50, p95, p99)
- Cache hit rate
- Error rate (by type)
- Reddit API quota usage

**Logging:**
```python
import structlog

logger = structlog.get_logger()

# Structured logs
logger.info(
    "tool_execution",
    tool="search_reddit",
    user_id="user_123",
    duration_ms=1234,
    cached=False,
    error=None
)
```

**Alerts:**
- Error rate >5% (1 minute)
- Cache hit rate <50% (5 minutes)
- Reddit API quota >80%
- Response time p95 >5s

### 8.4 Cost Estimate

| Component | Tier | Cost/Month |
|-----------|------|------------|
| Apify Actor | Free (10GB-hrs) | $0 |
| Apify Actor | Paid (overage) | $0-50 |
| Redis Cloud | 250MB | $0 |
| Reddit API | Free (100 QPM) | $0 |
| Reddit API | Paid (overage) | $0-200 |
| **Total (MVP)** | | **$0-250** |

**Break-even Analysis:**
- $19/month Pro tier: 50 users needed
- $99/month Business tier: 10 users needed
- Target: 100 paying users by Month 3 = $2,000 MRR

---

## Appendix: Implementation Checklist

### Week 1: MVP Foundation
- [ ] Set up Apify Actor project
- [ ] Configure Reddit API credentials
- [ ] Initialize FastMCP server
- [ ] Implement Redis caching layer
- [ ] Build rate limiter (token bucket)
- [ ] Create Tool 1: search_reddit
- [ ] Create Tool 2: get_subreddit_posts
- [ ] Write unit tests
- [ ] Deploy to Apify (standby mode)

### Week 2: Core Tools
- [ ] Create Tool 3: get_post_comments
- [ ] Create Tool 4: get_trending_topics
- [ ] Implement error handling middleware
- [ ] Add monitoring/logging (Apify datasets)
- [ ] Cache warming on startup
- [ ] Integration tests
- [ ] Documentation (README, API reference)
- [ ] Beta testing with 10 users

### Week 3: Monetization
- [ ] Create Tool 5: analyze_sentiment (VADER)
- [ ] Create Tool 6: get_user_info
- [ ] Implement user authentication (API keys)
- [ ] Usage tracking and billing integration
- [ ] Create landing page
- [ ] Pricing tier enforcement
- [ ] Analytics dashboard
- [ ] Submit to Apify Store

### Week 4: Polish & Launch
- [ ] Create Tool 7: get_subreddit_info
- [ ] Create Tool 8: watch_keywords (background jobs)
- [ ] Performance optimization (cache hit rate >75%)
- [ ] Security audit
- [ ] Load testing (100 concurrent users)
- [ ] Final documentation review
- [ ] Marketing push (Product Hunt, HN)
- [ ] Monitor metrics, iterate

---

**End of System Architecture Document**

**Version:** 1.0
**Status:** Ready for Implementation
**Next Steps:** Begin Week 1 development sprint
