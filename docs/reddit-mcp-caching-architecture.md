# Reddit MCP Server - Caching & Performance Architecture

## Executive Summary

This document outlines a comprehensive multi-tier caching and performance optimization strategy for the Reddit MCP Server to achieve:
- **75%+ cache hit rate** (target: 80%)
- **Support for 5,000+ MAU** with 100 QPM free tier
- **Sub-second latency** for cached queries (P95 < 500ms)
- **3-5x cost efficiency** through intelligent caching

Given Reddit API's strict rate limit (100 QPM free tier), aggressive caching is not optional—it's the foundation of our business viability.

---

## 1. Multi-Tier Caching Architecture

### Overview

We implement a three-tier caching hierarchy optimized for different access patterns and data lifecycles.

```
┌─────────────────────────────────────────────────────────────┐
│                      CLIENT REQUEST                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  TIER 1: Hot Cache (In-Memory)                              │
│  - Ultra-low latency (< 1ms)                                │
│  - Frequently accessed data                                 │
│  - Limited capacity (512 MB)                                │
└──────────────────────┬──────────────────────────────────────┘
                       │ Cache Miss
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  TIER 2: Warm Cache (Redis)                                 │
│  - Low latency (< 10ms)                                     │
│  - Shared across instances                                  │
│  - Larger capacity (4 GB)                                   │
└──────────────────────┬──────────────────────────────────────┘
                       │ Cache Miss
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  TIER 3: Cold Storage (Optional - Future)                   │
│  - Historical data (> 24 hours old)                         │
│  - S3-compatible storage                                    │
│  - Unlimited capacity                                       │
└──────────────────────┬──────────────────────────────────────┘
                       │ Cache Miss
                       ▼
                  REDDIT API
```

### Tier 1: Hot Cache (In-Memory)

**Purpose**: Ultra-fast access to frequently requested data within a single Actor instance.

**Implementation**: Python `cachetools.TTLCache`

**Configuration**:
```python
from cachetools import TTLCache
import threading

hot_cache = TTLCache(
    maxsize=1000,           # Max 1,000 entries
    ttl=60                  # 60 seconds default TTL
)
cache_lock = threading.RLock()  # Thread-safe access
```

**Content Types & TTLs**:

| Content Type | TTL | Max Entries | Size Estimate | Reasoning |
|-------------|-----|-------------|---------------|-----------|
| Trending posts | 30s | 100 | ~500 KB | Changes every 30-60s |
| Hot posts (top 25) | 60s | 200 | ~1 MB | Refreshed frequently |
| Active comment threads | 45s | 300 | ~2 MB | Real-time conversations |
| Search results (popular) | 90s | 200 | ~1 MB | Repetitive queries |
| Subreddit metadata | 300s | 200 | ~100 KB | Very stable |

**Size Limits**:
- **Total capacity**: 512 MB per Actor instance
- **Entry size limit**: 1 MB (automatically promoted to Tier 2 if larger)
- **Memory monitoring**: Alert at 80% capacity, evict at 95%

**Eviction Policy**:
- **Algorithm**: LRU (Least Recently Used) with TTL expiration
- **Priority**: TTL expiration first, then LRU for capacity management
- **Protected entries**: None (all subject to eviction)

**When to Use**:
- Same query repeated within 60 seconds
- Multiple users requesting identical data (e.g., /r/all hot posts)
- User performing exploratory searches with similar parameters

### Tier 2: Warm Cache (Redis)

**Purpose**: Persistent, shared cache across all Actor instances with larger capacity.

**Implementation**: Redis 7.x with `redis-py` client

**Configuration**:
```python
import redis
from redis.retry import Retry
from redis.backoff import ExponentialBackoff

redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST'),
    port=6379,
    db=0,
    decode_responses=False,  # Binary for compression
    socket_keepalive=True,
    socket_timeout=5,
    retry=Retry(ExponentialBackoff(), 3),
    max_connections=50
)
```

**Content Types & TTLs**:

| Content Type | TTL | Storage Format | Compression | Reasoning |
|-------------|-----|----------------|-------------|-----------|
| Hot posts | 5 min | JSON (gzip) | Yes (3:1) | Balances freshness & API usage |
| New posts | 2 min | JSON (gzip) | Yes (3:1) | Real-time monitoring needs |
| Top posts (hour) | 15 min | JSON (gzip) | Yes (3:1) | Relatively stable ranking |
| Top posts (day) | 1 hour | JSON (gzip) | Yes (3:1) | Historical stability |
| Top posts (week+) | 6 hours | JSON (gzip) | Yes (3:1) | Very stable over time |
| Comments | 10 min | JSON (gzip) | Yes (4:1) | Activity tapers quickly |
| User profiles | 15 min | JSON (gzip) | Yes (2:1) | Moderate change rate |
| Subreddit info | 1 hour | JSON (gzip) | Yes (2:1) | Rarely changes |
| Search results | 10 min | JSON (gzip) | Yes (3:1) | Depends on query popularity |
| Trending topics | 3 min | JSON (gzip) | Yes (3:1) | Viral content detection |

**Storage Optimization**:
```python
import gzip
import json

def cache_set(key: str, value: dict, ttl: int):
    """Compress and cache with TTL"""
    json_str = json.dumps(value, separators=(',', ':'))
    compressed = gzip.compress(json_str.encode('utf-8'))
    redis_client.setex(key, ttl, compressed)

def cache_get(key: str) -> dict:
    """Retrieve and decompress"""
    compressed = redis_client.get(key)
    if not compressed:
        return None
    json_str = gzip.decompress(compressed).decode('utf-8')
    return json.loads(json_str)
```

**Size Limits**:
- **Total capacity**: 4 GB Redis instance (Upstash or Redis Cloud)
- **Entry size limit**: 10 MB per key (reject larger)
- **Max keys**: ~100,000 keys (avg 40 KB compressed)
- **Memory policy**: `allkeys-lru` (evict least recently used when full)

**Eviction Policy**:
- **Algorithm**: Redis `allkeys-lru` with TTL expiration
- **Monitoring**: Track eviction rate (alert if > 5% of operations)
- **Priority tiers**: Use Redis sorted sets for priority queues (future)

**When to Use**:
- Data requested across different Actor instances
- Cache misses from Tier 1
- Persistent storage between Actor restarts
- Shared state for request deduplication

### Tier 3: Cold Storage (Optional - Future Enhancement)

**Purpose**: Long-term archival of historical data for analytics and compliance.

**Implementation**: S3-compatible storage (Cloudflare R2, AWS S3)

**Content Types**:
- Historical posts (> 24 hours old)
- Deleted content (for audit trails)
- Usage analytics aggregates
- Compliance logs

**Archive Strategy**:
```python
# Daily job to archive old cache entries
def archive_cold_data():
    # Get keys older than 24 hours
    old_keys = redis_client.scan_iter(match="reddit:*", count=100)
    for key in old_keys:
        ttl = redis_client.ttl(key)
        if ttl < 0 or ttl > 86400:  # Expired or very long TTL
            data = cache_get(key)
            if data:
                # Upload to S3
                s3_key = f"archive/{datetime.now().strftime('%Y/%m/%d')}/{key}"
                s3_client.put_object(Bucket='reddit-mcp-archive', Key=s3_key, Body=json.dumps(data))
                # Delete from Redis
                redis_client.delete(key)
```

**When to Use**:
- Historical data analysis (trends over months)
- Compliance requirements (data retention policies)
- Cost optimization (S3 cheaper than Redis for infrequent access)
- Not implemented in MVP (Phase 3 feature)

---

## 2. Cache Key Strategy

### Design Principles

1. **Collision-Free**: Use structured namespacing and parameter hashing
2. **Consistent**: Same input always produces same key
3. **Human-Readable**: Debug-friendly key structure
4. **Versioned**: Support schema changes without conflicts
5. **Efficient**: Short keys to minimize Redis memory overhead

### Key Pattern

```
reddit:{tool}:{params_hash}:{version}
```

**Components**:
- `reddit`: Namespace prefix (prevents conflicts with other services)
- `{tool}`: Tool name (e.g., `search`, `posts`, `comments`)
- `{params_hash}`: SHA-256 hash of sorted parameters (first 16 chars)
- `{version}`: Schema version (e.g., `v1`, `v2`)

### Parameter Hashing

```python
import hashlib
import json

def generate_cache_key(tool: str, params: dict, version: str = "v1") -> str:
    """Generate consistent cache key from tool name and parameters"""
    # Sort parameters for consistency
    sorted_params = json.dumps(params, sort_keys=True, separators=(',', ':'))

    # Hash parameters (SHA-256, first 16 chars)
    params_hash = hashlib.sha256(sorted_params.encode()).hexdigest()[:16]

    # Construct key
    key = f"reddit:{tool}:{params_hash}:{version}"

    return key

# Example
key = generate_cache_key(
    tool="search",
    params={"query": "artificial intelligence", "subreddit": "technology", "limit": 100},
    version="v1"
)
# Output: reddit:search:7f3a8c9d2e1b4f6a:v1
```

### Cache Keys by Tool

#### 1. `search_reddit`
```python
# Parameters
{
    "query": str,
    "subreddit": Optional[str],
    "sort": str,  # relevance, hot, top, new, comments
    "time_filter": str,  # hour, day, week, month, year, all
    "limit": int
}

# Example Key
reddit:search:a4f8c2e9d1b7f3a6:v1

# Full Example
key = generate_cache_key(
    tool="search",
    params={
        "query": "machine learning",
        "subreddit": "MachineLearning",
        "sort": "top",
        "time_filter": "week",
        "limit": 50
    }
)
# reddit:search:8d4f6a2c9e1b7f3a:v1
```

#### 2. `get_subreddit_posts`
```python
# Parameters
{
    "subreddit": str,
    "sort": str,  # hot, new, top, rising, controversial
    "time_filter": Optional[str],  # For 'top' and 'controversial'
    "limit": int
}

# Example Key
reddit:posts:b9e3f7c1d5a8f2e6:v1

# Full Example
key = generate_cache_key(
    tool="posts",
    params={
        "subreddit": "python",
        "sort": "hot",
        "limit": 25
    }
)
# reddit:posts:2c7f9e4b1d6a8f3c:v1
```

#### 3. `get_post_comments`
```python
# Parameters
{
    "post_id": str,
    "sort": str,  # confidence, top, new, controversial, old, qa
    "limit": int,
    "depth": Optional[int]  # Max comment tree depth
}

# Example Key
reddit:comments:f3e8c9d2a7b1f6e4:v1

# Full Example
key = generate_cache_key(
    tool="comments",
    params={
        "post_id": "t3_abc123",
        "sort": "top",
        "limit": 100,
        "depth": 3
    }
)
# reddit:comments:6f2a9c8e4b7d1f3a:v1
```

#### 4. `get_trending_topics`
```python
# Parameters
{
    "subreddit": Optional[str],  # None = all of Reddit
    "time_window": str,  # 1h, 6h, 24h
    "min_score": int,
    "limit": int
}

# Example Key
reddit:trending:e7c4f9a2d8b6f1e3:v1

# Full Example
key = generate_cache_key(
    tool="trending",
    params={
        "subreddit": None,
        "time_window": "6h",
        "min_score": 1000,
        "limit": 50
    }
)
# reddit:trending:9e6c2f7a8d4b1f3e:v1
```

#### 5. `analyze_sentiment`
```python
# Parameters
{
    "text": str,  # Hash full text
    "model": str  # sentiment-analysis-model version
}

# Example Key
reddit:sentiment:c8f2e9a7d4b6f1e3:v1

# Special Case: Hash entire text content
def generate_sentiment_key(text: str, model: str = "default") -> str:
    text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
    return f"reddit:sentiment:{text_hash}:{model}:v1"

# Full Example
key = generate_sentiment_key(
    text="This product is amazing! I highly recommend it to everyone.",
    model="distilbert-base"
)
# reddit:sentiment:a7f3e9c2d8b6f1e4:distilbert-base:v1
```

#### 6. `get_user_info`
```python
# Parameters
{
    "username": str,
    "include_posts": bool,
    "include_comments": bool,
    "limit": int
}

# Example Key
reddit:user:f9e2c8d7a4b6f1e3:v1

# Full Example
key = generate_cache_key(
    tool="user",
    params={
        "username": "spez",
        "include_posts": True,
        "include_comments": False,
        "limit": 25
    }
)
# reddit:user:3f8c9e2d7a6b1f4e:v1
```

#### 7. `get_subreddit_info`
```python
# Parameters
{
    "subreddit": str,
    "include_rules": bool,
    "include_moderators": bool
}

# Example Key
reddit:subreddit:d4f8c9e2a7b6f1e3:v1

# Full Example
key = generate_cache_key(
    tool="subreddit",
    params={
        "subreddit": "technology",
        "include_rules": True,
        "include_moderators": False
    }
)
# reddit:subreddit:8e4f9c2a7d6b1f3e:v1
```

#### 8. `watch_keywords` (Real-time monitoring - Phase 2)
```python
# Parameters
{
    "keywords": List[str],  # Sorted for consistency
    "subreddits": Optional[List[str]],  # Sorted
    "alert_threshold": int
}

# Example Key
reddit:watch:e2f9c8d7a4b6f1e3:v1

# Full Example
key = generate_cache_key(
    tool="watch",
    params={
        "keywords": sorted(["data breach", "security incident"]),
        "subreddits": sorted(["technology", "cybersecurity"]),
        "alert_threshold": 5
    }
)
# reddit:watch:7f4c9e2a8d6b1f3e:v1

# Note: This stores watch state, not results
# Results use separate keys: reddit:watch:{watch_id}:results:{timestamp}:v1
```

### Key Metadata Pattern

For debugging and cache management, store metadata alongside cached data:

```python
# Metadata key pattern
reddit:meta:{params_hash}:v1

# Metadata content
{
    "tool": "search",
    "params": {...},  # Original parameters
    "created_at": "2025-11-05T14:30:00Z",
    "accessed_count": 42,
    "last_accessed": "2025-11-05T15:45:00Z",
    "ttl_seconds": 300,
    "size_bytes": 15420
}
```

### Version Management

When API responses or schemas change:

```python
# Current version
CACHE_VERSION = "v1"

# When breaking changes occur, increment version
CACHE_VERSION = "v2"

# Old keys (v1) will naturally expire
# New keys (v2) won't collide with old data

# Gradual migration
def get_cached_data(tool: str, params: dict):
    # Try current version first
    key_v2 = generate_cache_key(tool, params, "v2")
    data = cache_get(key_v2)

    if data is None:
        # Fallback to previous version
        key_v1 = generate_cache_key(tool, params, "v1")
        data = cache_get(key_v1)

        if data:
            # Migrate to new version
            cache_set(key_v2, data, ttl=get_ttl(tool))

    return data
```

### Cache Key Statistics

Track key patterns for optimization:

```python
# Use Redis HyperLogLog for cardinality estimation
def track_key_pattern(tool: str):
    redis_client.pfadd(f"reddit:stats:keys:{tool}", generate_cache_key(tool, params))

def get_unique_key_count(tool: str) -> int:
    return redis_client.pfcount(f"reddit:stats:keys:{tool}")

# Example: How many unique search queries are cached?
unique_searches = get_unique_key_count("search")
# 3,472 unique search queries cached
```

---

## 3. TTL Policies by Content Type

### Dynamic TTL Calculation

TTLs should adapt based on content characteristics and user behavior.

```python
from typing import Dict, Callable
from datetime import datetime, timedelta

def calculate_dynamic_ttl(
    content_type: str,
    data: dict,
    base_ttl: int
) -> int:
    """Calculate TTL based on content characteristics"""

    # Age of content (older = longer cache)
    if 'created_utc' in data:
        age_hours = (datetime.utcnow().timestamp() - data['created_utc']) / 3600
        if age_hours > 24:
            return base_ttl * 3  # 3x longer for day-old content
        elif age_hours > 6:
            return base_ttl * 2  # 2x longer for 6hr+ old content

    # Activity level (high activity = shorter cache)
    if 'num_comments' in data and content_type == 'post':
        comments = data['num_comments']
        if comments > 500:
            return base_ttl // 2  # 50% shorter for viral posts
        elif comments < 10:
            return base_ttl * 2  # 2x longer for low-activity posts

    # Score velocity (rapid growth = shorter cache)
    if 'score' in data and 'created_utc' in data:
        age_minutes = (datetime.utcnow().timestamp() - data['created_utc']) / 60
        if age_minutes > 0:
            score_per_minute = data['score'] / age_minutes
            if score_per_minute > 10:
                return base_ttl // 2  # Trending fast

    return base_ttl
```

### TTL Configuration Table

| Content Type | Base TTL | Min TTL | Max TTL | Dynamic Factor | Reasoning |
|-------------|----------|---------|---------|----------------|-----------|
| **Posts: Hot** | 5 min | 2 min | 15 min | Activity level | Balances freshness with API efficiency; high-traffic posts refresh faster |
| **Posts: New** | 2 min | 1 min | 5 min | Submission rate | Real-time monitoring needs; short cache for breaking content |
| **Posts: Top (hour)** | 15 min | 5 min | 30 min | Age of content | Rankings stabilize after initial surge |
| **Posts: Top (day)** | 1 hour | 30 min | 3 hours | Age of content | Daily rankings change slowly; safe to cache longer |
| **Posts: Top (week)** | 6 hours | 3 hours | 12 hours | Age of content | Weekly rankings very stable; maximize cache hits |
| **Posts: Top (month+)** | 24 hours | 12 hours | 48 hours | Age of content | Historical data rarely changes; aggressive caching |
| **Posts: Rising** | 3 min | 1 min | 10 min | Score velocity | Identifies emerging trends; needs frequent refresh |
| **Posts: Controversial** | 30 min | 15 min | 2 hours | Activity level | Less popular sort; longer cache acceptable |
| **Comments: Active thread** | 5 min | 2 min | 15 min | Comment rate | Ongoing discussions need freshness |
| **Comments: Old thread** | 1 hour | 30 min | 6 hours | Thread age | Archived threads rarely get new comments |
| **Comments: Specific thread** | 10 min | 5 min | 30 min | Upvote ratio | Popular threads update more; cache accordingly |
| **User profile** | 15 min | 10 min | 1 hour | Activity level | Users post sporadically; 15min balances staleness |
| **User recent posts** | 10 min | 5 min | 30 min | Post frequency | Active users post more; adjust TTL dynamically |
| **User karma** | 30 min | 15 min | 2 hours | Karma growth | Karma changes slowly for most users |
| **Subreddit info** | 1 hour | 30 min | 24 hours | Subscriber count | Metadata rarely changes; long cache safe |
| **Subreddit rules** | 6 hours | 3 hours | 7 days | Rule change rate | Rules updated infrequently; aggressive caching |
| **Subreddit moderators** | 12 hours | 6 hours | 7 days | Mod turnover | Mod lists stable; very long cache |
| **Search: Recent** | 10 min | 5 min | 30 min | Result count | Popular searches cached longer |
| **Search: Historical** | 1 hour | 30 min | 6 hours | Time filter | Old search results stable; safe to cache |
| **Trending topics** | 3 min | 1 min | 10 min | Trend velocity | Viral content detection needs freshness |
| **Sentiment analysis** | 24 hours | 12 hours | 7 days | Text length | Text sentiment doesn't change; permanent cache |
| **Watch results** | 1 min | 30 sec | 5 min | Alert threshold | Real-time monitoring; ultra-short TTL |

### TTL Implementation

```python
from enum import Enum

class ContentType(Enum):
    POST_HOT = "post_hot"
    POST_NEW = "post_new"
    POST_TOP_HOUR = "post_top_hour"
    POST_TOP_DAY = "post_top_day"
    POST_TOP_WEEK = "post_top_week"
    POST_TOP_MONTH_PLUS = "post_top_month_plus"
    POST_RISING = "post_rising"
    POST_CONTROVERSIAL = "post_controversial"
    COMMENTS_ACTIVE = "comments_active"
    COMMENTS_OLD = "comments_old"
    USER_PROFILE = "user_profile"
    USER_POSTS = "user_posts"
    SUBREDDIT_INFO = "subreddit_info"
    SUBREDDIT_RULES = "subreddit_rules"
    SEARCH_RECENT = "search_recent"
    SEARCH_HISTORICAL = "search_historical"
    TRENDING = "trending"
    SENTIMENT = "sentiment"
    WATCH = "watch"

TTL_CONFIG: Dict[ContentType, Dict[str, int]] = {
    ContentType.POST_HOT: {"base": 300, "min": 120, "max": 900},
    ContentType.POST_NEW: {"base": 120, "min": 60, "max": 300},
    ContentType.POST_TOP_HOUR: {"base": 900, "min": 300, "max": 1800},
    ContentType.POST_TOP_DAY: {"base": 3600, "min": 1800, "max": 10800},
    ContentType.POST_TOP_WEEK: {"base": 21600, "min": 10800, "max": 43200},
    ContentType.POST_TOP_MONTH_PLUS: {"base": 86400, "min": 43200, "max": 172800},
    ContentType.POST_RISING: {"base": 180, "min": 60, "max": 600},
    ContentType.POST_CONTROVERSIAL: {"base": 1800, "min": 900, "max": 7200},
    ContentType.COMMENTS_ACTIVE: {"base": 300, "min": 120, "max": 900},
    ContentType.COMMENTS_OLD: {"base": 3600, "min": 1800, "max": 21600},
    ContentType.USER_PROFILE: {"base": 900, "min": 600, "max": 3600},
    ContentType.USER_POSTS: {"base": 600, "min": 300, "max": 1800},
    ContentType.SUBREDDIT_INFO: {"base": 3600, "min": 1800, "max": 86400},
    ContentType.SUBREDDIT_RULES: {"base": 21600, "min": 10800, "max": 604800},
    ContentType.SEARCH_RECENT: {"base": 600, "min": 300, "max": 1800},
    ContentType.SEARCH_HISTORICAL: {"base": 3600, "min": 1800, "max": 21600},
    ContentType.TRENDING: {"base": 180, "min": 60, "max": 600},
    ContentType.SENTIMENT: {"base": 86400, "min": 43200, "max": 604800},
    ContentType.WATCH: {"base": 60, "min": 30, "max": 300},
}

def get_ttl(content_type: ContentType, data: dict = None) -> int:
    """Get TTL for content type, optionally adjusted dynamically"""
    config = TTL_CONFIG[content_type]
    base_ttl = config["base"]

    if data:
        dynamic_ttl = calculate_dynamic_ttl(content_type.value, data, base_ttl)
        return max(config["min"], min(config["max"], dynamic_ttl))

    return base_ttl
```

### TTL Adjustment Strategy

Monitor cache effectiveness and adjust TTLs:

```python
from collections import defaultdict

class TTLOptimizer:
    def __init__(self):
        self.hit_rates = defaultdict(list)
        self.adjustment_threshold = 0.1  # Adjust if hit rate changes > 10%

    def record_hit(self, content_type: ContentType, is_hit: bool):
        self.hit_rates[content_type].append(1 if is_hit else 0)

        # Keep last 1000 requests
        if len(self.hit_rates[content_type]) > 1000:
            self.hit_rates[content_type].pop(0)

    def get_hit_rate(self, content_type: ContentType) -> float:
        rates = self.hit_rates[content_type]
        return sum(rates) / len(rates) if rates else 0.0

    def suggest_ttl_adjustment(self, content_type: ContentType) -> Optional[str]:
        hit_rate = self.get_hit_rate(content_type)

        if hit_rate < 0.5:
            return "INCREASE_TTL"  # Too many misses, cache longer
        elif hit_rate > 0.95:
            return "DECREASE_TTL"  # Very high hits, may be stale
        else:
            return None  # TTL is optimal

# Usage
optimizer = TTLOptimizer()

def cached_query(content_type: ContentType, key: str):
    data = cache_get(key)
    is_hit = data is not None

    optimizer.record_hit(content_type, is_hit)

    if not is_hit:
        data = fetch_from_reddit()
        ttl = get_ttl(content_type, data)
        cache_set(key, data, ttl)

    # Periodic adjustment check
    suggestion = optimizer.suggest_ttl_adjustment(content_type)
    if suggestion:
        log_ttl_suggestion(content_type, suggestion)

    return data
```

### Cache Warming Schedule

Proactively cache popular content to maximize hit rates:

```python
from apscheduler.schedulers.background import BackgroundScheduler

def warm_popular_subreddits():
    """Pre-cache hot posts from top 100 subreddits"""
    popular_subreddits = [
        'all', 'popular', 'AskReddit', 'worldnews', 'technology',
        'science', 'gaming', 'movies', 'music', 'books',
        # ... top 100 subreddits by traffic
    ]

    for subreddit in popular_subreddits:
        key = generate_cache_key("posts", {
            "subreddit": subreddit,
            "sort": "hot",
            "limit": 25
        })

        # Check if already cached
        if not cache_get(key):
            data = fetch_subreddit_posts(subreddit, "hot", 25)
            ttl = get_ttl(ContentType.POST_HOT, data)
            cache_set(key, data, ttl)

# Schedule cache warming
scheduler = BackgroundScheduler()
scheduler.add_job(warm_popular_subreddits, 'interval', minutes=5)
scheduler.start()
```

---

## 4. Cache Warming Strategy

### Objectives

1. **Maximize initial hit rate**: Pre-populate cache with likely queries
2. **Reduce cold start latency**: Eliminate first-request delays
3. **Optimize API usage**: Batch warm-up operations
4. **Prioritize high-value content**: Focus on popular subreddits and trending topics

### What to Pre-Cache

#### Priority 1: Universal Content (Highest Traffic)

```python
UNIVERSAL_CONTENT = {
    "subreddits": [
        {"name": "all", "sort": "hot", "limit": 100},
        {"name": "popular", "sort": "hot", "limit": 100},
    ],
    "trending": [
        {"time_window": "6h", "min_score": 1000, "limit": 50},
    ]
}
```

**Estimated API calls**: 3 requests
**Cache hit benefit**: 20-30% of all queries
**Refresh frequency**: Every 5 minutes

#### Priority 2: Top Subreddits (High Traffic)

```python
TOP_SUBREDDITS = [
    # News & Current Events (25%)
    'worldnews', 'news', 'politics', 'technology',

    # Entertainment (20%)
    'gaming', 'movies', 'television', 'music', 'books',

    # Discussion (15%)
    'AskReddit', 'explainlikeimfive', 'todayilearned', 'LifeProTips',

    # Tech & Development (15%)
    'programming', 'python', 'javascript', 'MachineLearning', 'datascience',

    # Business & Finance (10%)
    'business', 'stocks', 'cryptocurrency', 'personalfinance',

    # Sports (5%)
    'nba', 'nfl', 'soccer', 'sports',

    # Lifestyle (10%)
    'fitness', 'food', 'DIY', 'travel', 'photography'
]  # 30 subreddits

for subreddit in TOP_SUBREDDITS:
    warm_cache("posts", {
        "subreddit": subreddit,
        "sort": "hot",
        "limit": 25
    })
```

**Estimated API calls**: 30 requests
**Cache hit benefit**: 40-50% of queries
**Refresh frequency**: Every 5-10 minutes

#### Priority 3: Popular Search Queries

```python
POPULAR_SEARCHES = [
    {"query": "artificial intelligence", "sort": "top", "time_filter": "week"},
    {"query": "data breach", "sort": "new", "time_filter": "day"},
    {"query": "stock market", "sort": "hot", "time_filter": "day"},
    {"query": "climate change", "sort": "top", "time_filter": "month"},
    {"query": "cryptocurrency", "sort": "hot", "time_filter": "week"},
    # ... top 20 queries based on historical data
]  # 20 queries

for search in POPULAR_SEARCHES:
    warm_cache("search", search)
```

**Estimated API calls**: 20 requests
**Cache hit benefit**: 10-15% of search queries
**Refresh frequency**: Every 10-15 minutes

#### Priority 4: Subreddit Metadata

```python
# Cache metadata for top 100 subreddits
for subreddit in TOP_SUBREDDITS:
    warm_cache("subreddit", {
        "subreddit": subreddit,
        "include_rules": True,
        "include_moderators": False
    })
```

**Estimated API calls**: 30 requests
**Cache hit benefit**: 5-10% of queries
**Refresh frequency**: Every 1 hour

### When to Warm Cache

#### 1. Actor Startup (Cold Start)

```python
async def on_actor_startup():
    """Pre-populate cache when Actor initializes"""
    logger.info("Starting cache warm-up...")

    # Priority 1: Universal content (highest value)
    await warm_universal_content()

    # Priority 2: Top subreddits (if time permits)
    await warm_top_subreddits(limit=10)  # Top 10 only on startup

    logger.info("Cache warm-up complete")

# Total: ~15 API calls, completes in ~10 seconds
```

#### 2. Scheduled Refresh

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# Universal content: Every 5 minutes
scheduler.add_job(
    warm_universal_content,
    'interval',
    minutes=5,
    id='warm_universal'
)

# Top 30 subreddits: Every 10 minutes
scheduler.add_job(
    lambda: warm_top_subreddits(limit=30),
    'interval',
    minutes=10,
    id='warm_top_subreddits'
)

# Popular searches: Every 15 minutes
scheduler.add_job(
    warm_popular_searches,
    'interval',
    minutes=15,
    id='warm_searches'
)

# Subreddit metadata: Every 1 hour
scheduler.add_job(
    warm_subreddit_metadata,
    'interval',
    hours=1,
    id='warm_metadata'
)

scheduler.start()
```

#### 3. Predictive Warming (Machine Learning - Future)

```python
from sklearn.ensemble import RandomForestClassifier
import numpy as np

class PredictiveWarmer:
    """Predict which content to pre-cache based on usage patterns"""

    def __init__(self):
        self.model = RandomForestClassifier()
        self.feature_history = []

    def record_query(self, tool: str, params: dict, timestamp: datetime):
        """Track query patterns"""
        features = self.extract_features(tool, params, timestamp)
        self.feature_history.append(features)

    def extract_features(self, tool: str, params: dict, timestamp: datetime) -> np.array:
        """Extract features for prediction"""
        return np.array([
            timestamp.hour,  # Time of day
            timestamp.weekday(),  # Day of week
            len(str(params)),  # Complexity
            hash(str(params)) % 1000,  # Query pattern ID
        ])

    def predict_hot_queries(self, n: int = 20) -> List[dict]:
        """Predict queries likely to be requested soon"""
        # Train on historical data
        X = np.array([f for f, _ in self.feature_history])
        y = np.array([1 if self.was_repeated(f) else 0 for f, _ in self.feature_history])

        self.model.fit(X, y)

        # Predict future queries
        current_features = self.extract_features(None, {}, datetime.now())
        predictions = self.model.predict_proba([current_features])

        # Return top N predictions
        # (Implementation details omitted for brevity)
        return []

# Usage
warmer = PredictiveWarmer()

# Record every query
def track_query(tool, params):
    warmer.record_query(tool, params, datetime.now())

# Periodically warm predicted queries
scheduler.add_job(
    lambda: warm_predicted_queries(warmer.predict_hot_queries(20)),
    'interval',
    minutes=10,
    id='predictive_warming'
)
```

### Prioritization Algorithm

When warming cache with limited API quota:

```python
from typing import List, Tuple
import heapq

def prioritize_warming_tasks(tasks: List[dict], api_budget: int) -> List[dict]:
    """Select cache warming tasks based on priority"""

    # Calculate priority score for each task
    scored_tasks = []
    for task in tasks:
        score = calculate_priority_score(task)
        heapq.heappush(scored_tasks, (-score, task))  # Max heap

    # Select tasks within budget
    selected = []
    total_cost = 0

    while scored_tasks and total_cost < api_budget:
        score, task = heapq.heappop(scored_tasks)
        cost = estimate_api_cost(task)

        if total_cost + cost <= api_budget:
            selected.append(task)
            total_cost += cost

    return selected

def calculate_priority_score(task: dict) -> float:
    """Calculate priority score (0-100)"""
    score = 0.0

    # Factor 1: Historical hit rate (40% weight)
    hit_rate = get_historical_hit_rate(task)
    score += hit_rate * 40

    # Factor 2: Query frequency (30% weight)
    frequency = get_query_frequency(task)
    score += frequency * 30

    # Factor 3: Data freshness requirement (20% weight)
    freshness = get_freshness_requirement(task)
    score += freshness * 20

    # Factor 4: User impact (10% weight)
    impact = get_user_impact(task)
    score += impact * 10

    return score

def estimate_api_cost(task: dict) -> int:
    """Estimate API calls needed for task"""
    tool = task['tool']
    params = task['params']

    if tool == 'posts':
        return 1  # Single API call
    elif tool == 'comments':
        limit = params.get('limit', 100)
        return 1 + (limit // 100)  # Pagination
    elif tool == 'search':
        return 1
    else:
        return 1

# Example usage
warming_tasks = [
    {"tool": "posts", "params": {"subreddit": "all", "sort": "hot", "limit": 25}},
    {"tool": "posts", "params": {"subreddit": "python", "sort": "hot", "limit": 25}},
    {"tool": "trending", "params": {"time_window": "6h", "min_score": 1000}},
    # ... 100 more tasks
]

# Budget: 50 API calls for warming
selected_tasks = prioritize_warming_tasks(warming_tasks, api_budget=50)
```

### Warming Performance Metrics

Track effectiveness of cache warming:

```python
class WarmingMetrics:
    def __init__(self):
        self.metrics = {
            "tasks_executed": 0,
            "api_calls_used": 0,
            "cache_entries_created": 0,
            "warming_duration_ms": 0,
            "hit_rate_improvement": 0.0,
        }

    def record_warming_cycle(
        self,
        tasks: List[dict],
        api_calls: int,
        duration_ms: int,
        hit_rate_before: float,
        hit_rate_after: float
    ):
        self.metrics["tasks_executed"] += len(tasks)
        self.metrics["api_calls_used"] += api_calls
        self.metrics["cache_entries_created"] += len(tasks)
        self.metrics["warming_duration_ms"] += duration_ms
        self.metrics["hit_rate_improvement"] += (hit_rate_after - hit_rate_before)

    def get_roi(self) -> float:
        """Calculate ROI: (cache hits gained) / (API calls spent)"""
        if self.metrics["api_calls_used"] == 0:
            return 0.0

        # Estimate cache hits gained from warming
        estimated_hits = self.metrics["cache_entries_created"] * self.metrics["hit_rate_improvement"]

        return estimated_hits / self.metrics["api_calls_used"]

# Usage
metrics = WarmingMetrics()

def warm_cache_with_tracking():
    start = datetime.now()
    hit_rate_before = get_overall_hit_rate()

    tasks = prioritize_warming_tasks(generate_warming_tasks(), api_budget=50)
    api_calls = execute_warming_tasks(tasks)

    hit_rate_after = get_overall_hit_rate()
    duration_ms = (datetime.now() - start).total_seconds() * 1000

    metrics.record_warming_cycle(tasks, api_calls, duration_ms, hit_rate_before, hit_rate_after)

    logger.info(f"Cache warming ROI: {metrics.get_roi():.2f}x")
```

### API Budget Management

Ensure cache warming doesn't exhaust rate limits:

```python
class APIBudgetManager:
    def __init__(self, total_qpm: int = 100):
        self.total_qpm = total_qpm
        self.reserved_for_users = int(total_qpm * 0.7)  # 70% for user queries
        self.available_for_warming = total_qpm - self.reserved_for_users  # 30% for warming

    def get_warming_budget(self, window_minutes: int = 5) -> int:
        """Calculate API calls available for warming in given window"""
        return self.available_for_warming * window_minutes

    def should_throttle_warming(self, current_qpm: int) -> bool:
        """Check if warming should be paused"""
        return current_qpm > self.reserved_for_users

# Usage
budget_manager = APIBudgetManager(total_qpm=100)

def smart_cache_warming():
    current_qpm = get_current_qpm_usage()

    if budget_manager.should_throttle_warming(current_qpm):
        logger.warning("High user traffic, pausing cache warming")
        return

    budget = budget_manager.get_warming_budget(window_minutes=5)
    tasks = prioritize_warming_tasks(generate_warming_tasks(), api_budget=budget)

    execute_warming_tasks(tasks)
```

---

## 5. Performance Optimization Techniques

### 5.1 Request Deduplication

Coalesce identical concurrent queries to avoid redundant API calls.

```python
import asyncio
from collections import defaultdict
from typing import Dict, Awaitable, Any

class RequestDeduplicator:
    """Coalesce identical concurrent requests"""

    def __init__(self):
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.lock = asyncio.Lock()

    async def deduplicate(self, key: str, fetch_fn: Awaitable[Any]) -> Any:
        """Execute fetch_fn only once for concurrent identical requests"""

        async with self.lock:
            # Check if request already in flight
            if key in self.pending_requests:
                logger.info(f"Deduplicating request: {key}")
                return await self.pending_requests[key]

            # Create new future for this request
            future = asyncio.Future()
            self.pending_requests[key] = future

        try:
            # Execute the fetch function
            result = await fetch_fn()
            future.set_result(result)
            return result
        except Exception as e:
            future.set_exception(e)
            raise
        finally:
            # Clean up
            async with self.lock:
                del self.pending_requests[key]

# Usage
deduplicator = RequestDeduplicator()

async def get_subreddit_posts(subreddit: str, sort: str, limit: int):
    key = generate_cache_key("posts", {"subreddit": subreddit, "sort": sort, "limit": limit})

    # Check cache first
    cached = cache_get(key)
    if cached:
        return cached

    # Deduplicate API call
    async def fetch():
        return await reddit_api.get_posts(subreddit, sort, limit)

    data = await deduplicator.deduplicate(key, fetch)

    # Cache result
    cache_set(key, data, ttl=get_ttl(ContentType.POST_HOT))

    return data

# Example: 10 concurrent identical requests → 1 API call
# Without deduplication: 10 API calls
# With deduplication: 1 API call
# Savings: 90%
```

**Performance Impact**:
- **API call reduction**: 60-80% for popular queries
- **Latency improvement**: 0ms (waiting for existing request) vs 200-500ms (new API call)
- **Cost savings**: Significant during traffic spikes

### 5.2 Batch Operations

Group multiple Reddit API requests into efficient batches.

```python
from typing import List
import asyncio

class BatchProcessor:
    """Batch multiple requests into efficient API calls"""

    def __init__(self, batch_size: int = 10, batch_delay_ms: int = 100):
        self.batch_size = batch_size
        self.batch_delay_ms = batch_delay_ms
        self.pending_batch = []
        self.batch_lock = asyncio.Lock()

    async def add_to_batch(self, request: dict) -> Any:
        """Add request to batch and wait for execution"""
        async with self.batch_lock:
            self.pending_batch.append(request)

            # Create future for this request
            future = asyncio.Future()
            request['future'] = future

            # Execute batch if full
            if len(self.pending_batch) >= self.batch_size:
                await self.execute_batch()

        # Wait for batch execution
        return await future

    async def execute_batch(self):
        """Execute all pending requests in batch"""
        if not self.pending_batch:
            return

        batch = self.pending_batch
        self.pending_batch = []

        logger.info(f"Executing batch of {len(batch)} requests")

        # Execute batch (implementation depends on Reddit API support)
        # Reddit API doesn't support true batching, but we can:
        # 1. Execute in parallel with asyncio.gather()
        # 2. Use HTTP/2 multiplexing

        results = await asyncio.gather(
            *[self.execute_single(req) for req in batch],
            return_exceptions=True
        )

        # Resolve futures
        for req, result in zip(batch, results):
            if isinstance(result, Exception):
                req['future'].set_exception(result)
            else:
                req['future'].set_result(result)

batch_processor = BatchProcessor()

# Example: Fetch multiple user profiles efficiently
async def get_multiple_user_profiles(usernames: List[str]):
    """Fetch multiple user profiles in batch"""
    tasks = [
        batch_processor.add_to_batch({
            'type': 'user_profile',
            'username': username
        })
        for username in usernames
    ]

    return await asyncio.gather(*tasks)

# Without batching: 10 sequential API calls = 2-5 seconds
# With batching: 10 parallel API calls = 200-500ms
```

**Reddit API Batch Support**:
- Reddit API doesn't support true batching
- **Workaround**: Parallel execution with `asyncio.gather()`
- **Limitation**: Still counts as N API calls for rate limiting
- **Benefit**: Reduced latency (parallel vs sequential)

### 5.3 Lazy Loading Strategies

Defer loading of non-critical data to optimize initial response times.

```python
from typing import Optional

class LazyLoadedPost:
    """Post object with lazy-loaded comments"""

    def __init__(self, post_data: dict):
        self.post_data = post_data
        self._comments = None  # Not loaded initially

    @property
    def title(self) -> str:
        return self.post_data['title']

    @property
    def score(self) -> int:
        return self.post_data['score']

    @property
    async def comments(self) -> List[dict]:
        """Load comments on demand"""
        if self._comments is None:
            self._comments = await fetch_post_comments(self.post_data['id'])
        return self._comments

# MCP tool implementation
async def get_post_with_comments(post_id: str, include_comments: bool = True):
    """Get post, optionally including comments"""

    # Always fetch post (fast, ~50ms)
    post = await fetch_post(post_id)

    # Only fetch comments if requested (slow, 200-500ms)
    if include_comments:
        comments = await fetch_post_comments(post_id)
        post['comments'] = comments
    else:
        post['comments'] = None  # Client can request later

    return post

# Initial response: 50ms (post only)
# With comments: 300ms (post + comments)
# Savings: 250ms for users who don't need comments
```

**Lazy Loading Patterns**:

1. **Comments**: Load on demand (saves 200-500ms)
2. **User karma history**: Fetch only when needed
3. **Subreddit rules**: Load separately from subreddit info
4. **Large image previews**: Return URLs, not base64 data

### 5.4 Pagination Optimization

Efficiently handle Reddit's 1,000 item pagination limit.

```python
from typing import AsyncIterator, Optional

class PaginationOptimizer:
    """Optimize pagination for Reddit API"""

    def __init__(self):
        self.page_cache = {}  # Cache individual pages

    async def paginate(
        self,
        fetch_fn: Callable,
        limit: int = 100,
        max_pages: int = 10
    ) -> AsyncIterator[List[dict]]:
        """Fetch paginated results efficiently"""

        after = None
        page_num = 0

        while page_num < max_pages:
            # Check page cache
            page_key = f"page_{page_num}_{after}"
            cached_page = self.page_cache.get(page_key)

            if cached_page:
                yield cached_page['data']
                after = cached_page['after']
            else:
                # Fetch page
                data, after = await fetch_fn(limit=limit, after=after)

                # Cache page
                self.page_cache[page_key] = {'data': data, 'after': after}

                yield data

            # Stop if no more pages
            if not after:
                break

            page_num += 1

# Usage
paginator = PaginationOptimizer()

async def get_all_posts(subreddit: str, sort: str, max_items: int = 1000):
    """Get up to 1,000 posts (Reddit's limit)"""
    all_posts = []

    async def fetch_page(limit: int, after: Optional[str]):
        return await reddit_api.get_posts(subreddit, sort, limit, after)

    async for page in paginator.paginate(fetch_page, limit=100, max_pages=10):
        all_posts.extend(page)

        if len(all_posts) >= max_items:
            break

    return all_posts[:max_items]

# Optimization: Cache each page independently
# User requests posts 1-100: Fetch page 1, cache
# User requests posts 101-200: Fetch page 2, cache
# User requests posts 1-200: Retrieve from cache (0 API calls)
```

**Pagination Best Practices**:

1. **Cache pages independently**: Maximize cache hits for overlapping ranges
2. **Stream results**: Don't wait for all pages before returning
3. **Smart prefetching**: Predict next page request and pre-cache
4. **Compress pages**: Reduce Redis memory usage

### 5.5 Connection Pooling

Reuse HTTP connections to minimize latency and overhead.

```python
import aiohttp
from aiohttp import TCPConnector

class ConnectionPoolManager:
    """Manage HTTP connection pools for Reddit API"""

    def __init__(self):
        self.connector = TCPConnector(
            limit=100,              # Max 100 connections total
            limit_per_host=30,      # Max 30 connections to Reddit
            ttl_dns_cache=300,      # Cache DNS for 5 minutes
            keepalive_timeout=120,  # Keep connections alive for 2 minutes
        )

        self.session = aiohttp.ClientSession(
            connector=self.connector,
            timeout=aiohttp.ClientTimeout(total=10),
            headers={
                'User-Agent': 'Reddit-MCP-Server/1.0',
            }
        )

    async def close(self):
        await self.session.close()
        await self.connector.close()

# Redis connection pooling
import redis.asyncio as aioredis

class RedisConnectionPool:
    """Manage Redis connection pool"""

    def __init__(self):
        self.pool = aioredis.ConnectionPool(
            host=os.getenv('REDIS_HOST'),
            port=6379,
            db=0,
            max_connections=50,
            socket_keepalive=True,
            socket_keepalive_options={
                1: 1,  # TCP_KEEPIDLE
                2: 1,  # TCP_KEEPINTVL
                3: 3,  # TCP_KEEPCNT
            },
        )

        self.client = aioredis.Redis(connection_pool=self.pool)

    async def close(self):
        await self.pool.disconnect()

# Global instances
http_pool = ConnectionPoolManager()
redis_pool = RedisConnectionPool()

# Performance impact:
# Without pooling: 50-100ms per request (TCP handshake + TLS)
# With pooling: 10-20ms per request (reuse existing connections)
# Improvement: 3-5x faster
```

### 5.6 Response Compression

Compress API responses to reduce bandwidth and Redis memory usage.

```python
import gzip
import json
from typing import Any

class CompressionManager:
    """Manage response compression"""

    @staticmethod
    def compress(data: Any) -> bytes:
        """Compress JSON data with gzip"""
        json_str = json.dumps(data, separators=(',', ':'))
        compressed = gzip.compress(json_str.encode('utf-8'), compresslevel=6)
        return compressed

    @staticmethod
    def decompress(compressed: bytes) -> Any:
        """Decompress gzip data to JSON"""
        json_str = gzip.decompress(compressed).decode('utf-8')
        return json.loads(json_str)

    @staticmethod
    def get_compression_ratio(data: Any) -> float:
        """Calculate compression ratio"""
        original_size = len(json.dumps(data).encode('utf-8'))
        compressed_size = len(CompressionManager.compress(data))
        return original_size / compressed_size

# Usage in cache layer
def cache_set_compressed(key: str, data: Any, ttl: int):
    compressed = CompressionManager.compress(data)
    redis_client.setex(key, ttl, compressed)

def cache_get_compressed(key: str) -> Any:
    compressed = redis_client.get(key)
    if not compressed:
        return None
    return CompressionManager.decompress(compressed)

# Compression ratios:
# Posts: 3:1 (30% of original size)
# Comments: 4:1 (25% of original size)
# User profiles: 2.5:1 (40% of original size)
#
# 4 GB Redis → stores ~12-16 GB uncompressed data
```

### 5.7 Intelligent Prefetching

Predict and pre-fetch data users are likely to request next.

```python
from collections import deque

class PrefetchPredictor:
    """Predict next requests based on patterns"""

    def __init__(self):
        self.access_patterns = deque(maxlen=1000)  # Last 1000 requests

    def record_access(self, tool: str, params: dict):
        """Record access pattern"""
        self.access_patterns.append({
            'tool': tool,
            'params': params,
            'timestamp': datetime.now()
        })

    def predict_next(self, current_tool: str, current_params: dict) -> List[dict]:
        """Predict likely next requests"""
        predictions = []

        # Pattern 1: Browsing subreddit → likely to view comments
        if current_tool == "posts":
            # User viewed posts, likely to click top post
            predictions.append({
                'tool': 'comments',
                'params': {
                    'post_id': 'top_post_id',  # Replace with actual top post
                    'sort': 'top',
                    'limit': 100
                }
            })

        # Pattern 2: Viewing comments → likely to view user profile
        if current_tool == "comments":
            # User reading comments, might check author profiles
            predictions.append({
                'tool': 'user',
                'params': {
                    'username': 'top_commenter',  # Replace with actual
                    'include_posts': True,
                    'limit': 25
                }
            })

        # Pattern 3: Searching → likely to refine search
        if current_tool == "search":
            query = current_params.get('query', '')
            # Suggest related searches
            predictions.append({
                'tool': 'search',
                'params': {
                    'query': f"{query} tutorial",  # Expand query
                    'sort': 'top',
                    'time_filter': 'month'
                }
            })

        return predictions

    async def prefetch(self, tool: str, params: dict):
        """Prefetch predicted next requests"""
        predictions = self.predict_next(tool, params)

        for pred in predictions[:3]:  # Limit to top 3 predictions
            key = generate_cache_key(pred['tool'], pred['params'])

            # Only prefetch if not already cached
            if not cache_get(key):
                # Fetch in background (don't wait)
                asyncio.create_task(self.fetch_and_cache(pred))

    async def fetch_and_cache(self, pred: dict):
        """Fetch predicted data and cache it"""
        try:
            data = await fetch_data(pred['tool'], pred['params'])
            key = generate_cache_key(pred['tool'], pred['params'])
            ttl = get_ttl_for_tool(pred['tool'])
            cache_set(key, data, ttl)
            logger.info(f"Prefetched: {key}")
        except Exception as e:
            logger.warning(f"Prefetch failed: {e}")

# Usage
predictor = PrefetchPredictor()

async def handle_request(tool: str, params: dict):
    # Handle current request
    data = await get_data(tool, params)

    # Record access pattern
    predictor.record_access(tool, params)

    # Prefetch predicted next requests (background)
    asyncio.create_task(predictor.prefetch(tool, params))

    return data

# Performance impact:
# Without prefetching: 200-500ms per request
# With prefetching: 10-50ms for predicted requests (95% cache hit)
# User perceives instant responses
```

---

## 6. Performance Metrics & Monitoring

### 6.1 Key Metrics

#### Cache Performance Metrics

| Metric | Target | Critical Threshold | Measurement Method |
|--------|--------|-------------------|-------------------|
| **Cache Hit Rate** | 75-80% | < 60% | `(hits / (hits + misses)) * 100` |
| **Cache Miss Rate** | 20-25% | > 40% | `(misses / (hits + misses)) * 100` |
| **Hot Cache Hit Rate** | 40-50% | < 30% | Tier 1 hits / total requests |
| **Warm Cache Hit Rate** | 30-35% | < 20% | Tier 2 hits / Tier 1 misses |
| **Cache Eviction Rate** | < 5% | > 15% | Evictions / writes |
| **Average TTL Effectiveness** | 80%+ | < 60% | Requests served before expiration |

#### Latency Metrics

| Metric | Target | Critical Threshold | Measurement Method |
|--------|--------|-------------------|-------------------|
| **P50 Latency (cached)** | < 50ms | > 200ms | 50th percentile response time |
| **P95 Latency (cached)** | < 500ms | > 2s | 95th percentile response time |
| **P99 Latency (cached)** | < 1s | > 5s | 99th percentile response time |
| **P50 Latency (uncached)** | < 500ms | > 2s | Reddit API call latency |
| **P95 Latency (uncached)** | < 2s | > 5s | Slow Reddit API responses |
| **Cache Lookup Time** | < 5ms | > 20ms | Redis GET operation |
| **Cache Write Time** | < 10ms | > 50ms | Redis SET operation |

#### Throughput Metrics

| Metric | Target | Critical Threshold | Measurement Method |
|--------|--------|-------------------|-------------------|
| **Requests per Second** | 50-100 RPS | > 150 RPS | Total MCP tool calls / second |
| **Reddit API QPM** | < 70 QPM | > 90 QPM | Actual API calls / minute |
| **Redis Operations per Second** | 500-1000 | > 2000 | Redis commands / second |
| **Deduplication Rate** | 10-20% | < 5% | Deduplicated requests / total |
| **Concurrent Connections** | 20-50 | > 100 | Active Actor instances |

#### Resource Metrics

| Metric | Target | Critical Threshold | Measurement Method |
|--------|--------|-------------------|-------------------|
| **Redis Memory Usage** | < 70% | > 90% | `INFO memory` used_memory_human |
| **Redis Key Count** | 50K-100K | > 150K | `DBSIZE` |
| **Actor Memory Usage** | < 512 MB | > 1 GB | Container memory stats |
| **Actor CPU Usage** | < 50% | > 80% | Container CPU stats |

### 6.2 Monitoring Implementation

```python
from prometheus_client import Counter, Histogram, Gauge
import time

# Cache metrics
cache_hits = Counter('cache_hits_total', 'Total cache hits', ['tier', 'tool'])
cache_misses = Counter('cache_misses_total', 'Total cache misses', ['tool'])
cache_evictions = Counter('cache_evictions_total', 'Total cache evictions', ['tier'])
cache_size = Gauge('cache_size_bytes', 'Cache size in bytes', ['tier'])
cache_keys = Gauge('cache_keys_count', 'Number of keys in cache', ['tier'])

# Latency metrics
request_latency = Histogram(
    'request_latency_seconds',
    'Request latency in seconds',
    ['tool', 'cached'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Throughput metrics
request_count = Counter('requests_total', 'Total requests', ['tool', 'status'])
reddit_api_calls = Counter('reddit_api_calls_total', 'Total Reddit API calls', ['endpoint'])
deduplication_count = Counter('deduplicated_requests_total', 'Deduplicated requests', ['tool'])

# Resource metrics
redis_memory = Gauge('redis_memory_bytes', 'Redis memory usage in bytes')
actor_memory = Gauge('actor_memory_bytes', 'Actor memory usage in bytes')

class MetricsCollector:
    """Collect and export metrics"""

    def __init__(self):
        self.request_times = {}

    def start_request(self, request_id: str):
        """Record request start time"""
        self.request_times[request_id] = time.time()

    def end_request(
        self,
        request_id: str,
        tool: str,
        is_cached: bool,
        tier: Optional[str] = None
    ):
        """Record request completion"""
        start_time = self.request_times.pop(request_id, None)
        if not start_time:
            return

        latency = time.time() - start_time

        # Record latency
        request_latency.labels(
            tool=tool,
            cached='yes' if is_cached else 'no'
        ).observe(latency)

        # Record cache hit/miss
        if is_cached:
            cache_hits.labels(tier=tier, tool=tool).inc()
        else:
            cache_misses.labels(tool=tool).inc()

        # Record request count
        request_count.labels(tool=tool, status='success').inc()

    def record_cache_eviction(self, tier: str):
        """Record cache eviction"""
        cache_evictions.labels(tier=tier).inc()

    def record_deduplication(self, tool: str):
        """Record request deduplication"""
        deduplication_count.labels(tool=tool).inc()

    def record_reddit_api_call(self, endpoint: str):
        """Record Reddit API call"""
        reddit_api_calls.labels(endpoint=endpoint).inc()

    async def collect_redis_metrics(self):
        """Collect Redis metrics"""
        info = await redis_client.info('memory')
        redis_memory.set(info['used_memory'])

        dbsize = await redis_client.dbsize()
        cache_keys.labels(tier='redis').set(dbsize)

    async def collect_cache_size_metrics(self):
        """Estimate cache sizes"""
        # Hot cache size
        hot_size = sum(len(str(v)) for v in hot_cache.values())
        cache_size.labels(tier='hot').set(hot_size)

        # Redis cache size
        await self.collect_redis_metrics()

# Global metrics collector
metrics = MetricsCollector()

# Usage in MCP tools
async def search_reddit(query: str, **params):
    request_id = generate_request_id()
    metrics.start_request(request_id)

    try:
        # Check cache
        key = generate_cache_key("search", params)
        cached_data = cache_get(key)

        if cached_data:
            metrics.end_request(request_id, "search", is_cached=True, tier="redis")
            return cached_data

        # Fetch from Reddit API
        metrics.record_reddit_api_call("search")
        data = await reddit_api.search(query, **params)

        # Cache result
        cache_set(key, data, ttl=get_ttl(ContentType.SEARCH_RECENT))

        metrics.end_request(request_id, "search", is_cached=False)
        return data

    except Exception as e:
        request_count.labels(tool="search", status="error").inc()
        raise
```

### 6.3 Alerting Rules

```yaml
# Prometheus alerting rules
groups:
  - name: reddit_mcp_cache
    rules:
      # Cache hit rate too low
      - alert: LowCacheHitRate
        expr: |
          (
            sum(rate(cache_hits_total[5m])) /
            (sum(rate(cache_hits_total[5m])) + sum(rate(cache_misses_total[5m])))
          ) < 0.60
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Cache hit rate below 60%"
          description: "Cache hit rate is {{ $value | humanizePercentage }}, target is 75%+"

      # Reddit API rate limit approaching
      - alert: HighRedditAPIUsage
        expr: rate(reddit_api_calls_total[1m]) * 60 > 90
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Reddit API usage approaching rate limit"
          description: "Current QPM is {{ $value }}, limit is 100 QPM"

      # High latency
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95,
            sum(rate(request_latency_seconds_bucket{cached="yes"}[5m])) by (le)
          ) > 1.0
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "P95 cached latency above 1 second"
          description: "P95 latency is {{ $value }}s, target is < 500ms"

      # Redis memory high
      - alert: HighRedisMemory
        expr: redis_memory_bytes / (4 * 1024 * 1024 * 1024) > 0.90
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Redis memory usage above 90%"
          description: "Redis using {{ $value | humanizePercentage }} of 4GB"

      # High cache eviction rate
      - alert: HighCacheEvictionRate
        expr: rate(cache_evictions_total[5m]) > 10
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High cache eviction rate"
          description: "{{ $value }} evictions per second"
```

### 6.4 Dashboard Configuration

```python
# Grafana dashboard JSON (simplified)
GRAFANA_DASHBOARD = {
    "dashboard": {
        "title": "Reddit MCP Server - Cache Performance",
        "panels": [
            {
                "title": "Cache Hit Rate",
                "targets": [{
                    "expr": """
                        (
                            sum(rate(cache_hits_total[5m])) /
                            (sum(rate(cache_hits_total[5m])) + sum(rate(cache_misses_total[5m])))
                        ) * 100
                    """,
                    "legendFormat": "Overall Hit Rate"
                }],
                "yAxisLabel": "Hit Rate (%)",
                "threshold": [
                    {"value": 75, "color": "green"},
                    {"value": 60, "color": "yellow"},
                    {"value": 0, "color": "red"}
                ]
            },
            {
                "title": "Request Latency (P50, P95, P99)",
                "targets": [
                    {
                        "expr": """
                            histogram_quantile(0.50,
                                sum(rate(request_latency_seconds_bucket{cached="yes"}[5m])) by (le)
                            ) * 1000
                        """,
                        "legendFormat": "P50 Cached"
                    },
                    {
                        "expr": """
                            histogram_quantile(0.95,
                                sum(rate(request_latency_seconds_bucket{cached="yes"}[5m])) by (le)
                            ) * 1000
                        """,
                        "legendFormat": "P95 Cached"
                    },
                    {
                        "expr": """
                            histogram_quantile(0.99,
                                sum(rate(request_latency_seconds_bucket[5m])) by (le)
                            ) * 1000
                        """,
                        "legendFormat": "P99 All"
                    }
                ],
                "yAxisLabel": "Latency (ms)"
            },
            {
                "title": "Reddit API Usage vs Rate Limit",
                "targets": [
                    {
                        "expr": "rate(reddit_api_calls_total[1m]) * 60",
                        "legendFormat": "Current QPM"
                    },
                    {
                        "expr": "100",
                        "legendFormat": "Rate Limit"
                    }
                ],
                "yAxisLabel": "Queries per Minute"
            },
            {
                "title": "Cache Size & Evictions",
                "targets": [
                    {
                        "expr": "cache_keys_count{tier='redis'}",
                        "legendFormat": "Redis Keys"
                    },
                    {
                        "expr": "rate(cache_evictions_total[5m])",
                        "legendFormat": "Evictions/sec"
                    }
                ]
            }
        ]
    }
}
```

### 6.5 Logging Strategy

```python
import structlog
import logging

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Log cache operations
def log_cache_operation(operation: str, key: str, tier: str, hit: bool = None, latency_ms: float = None):
    logger.info(
        "cache_operation",
        operation=operation,
        key=key,
        tier=tier,
        hit=hit,
        latency_ms=latency_ms
    )

# Log API calls
def log_reddit_api_call(endpoint: str, params: dict, latency_ms: float, status_code: int):
    logger.info(
        "reddit_api_call",
        endpoint=endpoint,
        params=params,
        latency_ms=latency_ms,
        status_code=status_code
    )

# Log performance issues
def log_performance_issue(issue_type: str, details: dict):
    logger.warning(
        "performance_issue",
        issue_type=issue_type,
        **details
    )

# Example usage
async def get_cached_data(key: str):
    start = time.time()

    # Try hot cache
    data = hot_cache.get(key)
    if data:
        latency_ms = (time.time() - start) * 1000
        log_cache_operation("get", key, "hot", hit=True, latency_ms=latency_ms)
        return data

    # Try Redis
    data = cache_get(key)
    if data:
        latency_ms = (time.time() - start) * 1000
        log_cache_operation("get", key, "redis", hit=True, latency_ms=latency_ms)
        return data

    # Cache miss
    latency_ms = (time.time() - start) * 1000
    log_cache_operation("get", key, "all", hit=False, latency_ms=latency_ms)

    return None
```

---

## 7. Scalability Analysis

### 7.1 Capacity Calculations

#### Baseline (No Caching)

```
Reddit API Rate Limit: 100 QPM
Average queries per user: 10 QPM (active user)
Sustainable users: 100 QPM / 10 QPM = 10 users
```

**Conclusion**: Without caching, Reddit MCP can only support ~10 concurrent active users.

#### With 75% Cache Hit Rate

```
Effective API capacity: 100 QPM actual calls
Cache hit rate: 75%
Actual user queries: 100 QPM / (1 - 0.75) = 400 QPM total queries

Average queries per user: 10 QPM
Sustainable users: 400 QPM / 10 QPM = 40 users (concurrent)
```

**Monthly Active Users (MAU) calculation**:
```
Concurrent users: 40
Peak hour: 20% of daily users
Daily active users (DAU): 40 / 0.20 = 200 DAU
Monthly active users (MAU): 200 * 30 = 6,000 MAU
```

**Conclusion**: With 75% cache hit rate, Reddit MCP can support **6,000 MAU** on free tier.

#### With 80% Cache Hit Rate (Target)

```
Effective API capacity: 100 QPM actual calls
Cache hit rate: 80%
Actual user queries: 100 QPM / (1 - 0.80) = 500 QPM total queries

Average queries per user: 10 QPM
Sustainable users: 500 QPM / 10 QPM = 50 users (concurrent)

DAU: 50 / 0.20 = 250 DAU
MAU: 250 * 30 = 7,500 MAU
```

**Conclusion**: With 80% cache hit rate, Reddit MCP can support **7,500+ MAU** on free tier.

### 7.2 Scalability Scenarios

#### Scenario 1: Organic Growth (1,000 → 5,000 MAU)

**Timeline**: Month 1-6

**Infrastructure Evolution**:

| Month | MAU | DAU | Concurrent | Redis Size | Actor Instances |
|-------|-----|-----|------------|------------|----------------|
| 1 | 1,000 | 33 | 7 | 1 GB | 1-2 |
| 2 | 2,000 | 67 | 13 | 2 GB | 2-3 |
| 3 | 3,000 | 100 | 20 | 3 GB | 3-4 |
| 4 | 4,000 | 133 | 27 | 4 GB | 4-5 |
| 5 | 5,000 | 167 | 33 | 5 GB | 5-6 |

**Actions Required**:
- **Month 1**: Deploy with 1 GB Redis, monitor cache hit rate
- **Month 2**: Scale Redis to 2 GB, add second Actor instance
- **Month 3**: Optimize TTLs based on actual usage patterns
- **Month 4**: Implement predictive caching (ML-based)
- **Month 5**: Upgrade Redis to 6 GB, 6-8 Actor instances

**Cost Estimate**:
```
Redis (4 GB): $25/mo (Upstash)
Actor compute: $50/mo (5-6 instances @ $8-10 each)
Monitoring: $10/mo (Prometheus Cloud)
Total: ~$85/mo
```

#### Scenario 2: Viral Growth (5,000 → 20,000 MAU in 1 month)

**Challenge**: Sudden 4x traffic spike

**Infrastructure Response**:

1. **Immediate (Day 1-3)**:
   - Auto-scale Actor instances to 20+
   - Upgrade Redis to 16 GB
   - Enable aggressive cache warming
   - Implement request throttling for free tier

2. **Short-term (Week 1-2)**:
   - Deploy Redis Cluster (3 nodes)
   - Implement read replicas for cache
   - Optimize cache eviction policies
   - Add CDN for static responses

3. **Long-term (Week 3-4)**:
   - Negotiate higher Reddit API limits ($0.24/1K calls)
   - Implement tiered caching (hot/warm/cold)
   - Add predictive prefetching
   - Deploy multi-region infrastructure

**Cost Estimate (Viral Scenario)**:
```
Redis Cluster (16 GB): $150/mo
Actor compute: $200/mo (20 instances)
Reddit API paid tier: $200/mo (additional calls)
Monitoring & CDN: $50/mo
Total: ~$600/mo
```

#### Scenario 3: Enterprise Scale (50,000+ MAU)

**Requirements**:
- 50,000 MAU = 1,667 DAU = 333 concurrent users
- 333 concurrent × 10 QPM = 3,330 QPM total queries
- With 80% cache: 666 QPM actual API calls
- **Problem**: Exceeds 100 QPM free tier by 6.6x

**Solution**: Paid Reddit API tier + multi-account strategy

```
Option A: Single Paid Account
- Reddit API: $0.24/1,000 calls
- 666 QPM × 60 min × 24 hr × 30 days = 28.8M calls/month
- Cost: 28.8M × $0.24/1,000 = $6,912/mo

Option B: Multi-Account Strategy (10 free accounts)
- 10 accounts × 100 QPM = 1,000 QPM capacity
- 666 QPM actual usage = within limit
- Cost: $0/mo (free tier)
- Trade-off: Complexity, potential ToS issues

Option C: Hybrid (5 free + 1 paid)
- 5 free accounts: 500 QPM
- 1 paid account: 200 QPM additional
- 200 QPM × 60 × 24 × 30 = 8.64M calls/month
- Paid cost: 8.64M × $0.24/1,000 = $2,074/mo
- Total cost: $2,074/mo
```

**Recommended**: Option C (Hybrid) for enterprise scale.

### 7.3 Bottleneck Analysis

#### Bottleneck 1: Reddit API Rate Limit

**Impact**: Highest impact bottleneck

**Mitigation**:
1. **Increase cache hit rate**: 75% → 85% (doubles capacity)
2. **Request deduplication**: Save 10-20% of API calls
3. **Multi-account strategy**: Multiply capacity by N accounts
4. **Paid tier**: $0.24/1K calls for unlimited capacity
5. **User tier throttling**: Free users = lower QPM allocation

#### Bottleneck 2: Redis Memory

**Impact**: Medium impact

**Current Capacity**:
```
4 GB Redis = ~100K keys (avg 40 KB compressed)
100K keys × 5 min avg TTL = 333 keys/sec insertion rate
Supports ~20,000 QPM total queries
```

**Mitigation**:
1. **Increase Redis size**: 4 GB → 16 GB (4x capacity)
2. **Optimize compression**: Improve 3:1 → 5:1 ratio
3. **Smarter eviction**: Priority-based LRU
4. **Redis Cluster**: Horizontal scaling

#### Bottleneck 3: Actor Compute

**Impact**: Low impact (easily scalable)

**Current Capacity**:
```
1 Actor instance = ~100 RPS (cached queries)
5 Actor instances = 500 RPS = 30,000 QPM
```

**Mitigation**:
1. **Auto-scaling**: Scale to 20+ instances during peak
2. **Optimize code**: Reduce CPU per request
3. **Connection pooling**: Reuse HTTP/Redis connections

#### Bottleneck 4: Network Latency

**Impact**: Low-medium impact

**Current Performance**:
```
Redis RTT: 5-20ms (within region)
Reddit API RTT: 100-300ms (US East)
```

**Mitigation**:
1. **Multi-region deployment**: Deploy Actors near users
2. **CDN for cache hits**: Cloudflare Workers KV
3. **HTTP/2 multiplexing**: Reduce connection overhead

### 7.4 Scale Testing Plan

#### Phase 1: Baseline (Week 1)

**Test**: 100 MAU, 70% cache hit rate

**Metrics to collect**:
- Cache hit rate by tool
- P95 latency by cache status
- Reddit API QPM usage
- Redis memory usage

#### Phase 2: Target Load (Week 2-3)

**Test**: 5,000 MAU, 75% cache hit rate

**Scenarios**:
1. **Steady state**: Constant 167 DAU, 33 concurrent
2. **Peak hour**: 50 concurrent for 1 hour
3. **Burst**: 100 concurrent for 5 minutes

**Pass criteria**:
- Cache hit rate > 75%
- P95 latency < 500ms (cached)
- Reddit API usage < 90 QPM
- No errors or timeouts

#### Phase 3: Stress Test (Week 4)

**Test**: 10,000 MAU, 80% cache hit rate

**Scenarios**:
1. **Sustained load**: 333 DAU, 67 concurrent for 24 hours
2. **Cache invalidation**: Flush cache and measure recovery
3. **Reddit API outage**: Simulate 503 errors

**Pass criteria**:
- Graceful degradation under stress
- Recovery time < 5 minutes after cache flush
- Circuit breaker activates on API errors

### 7.5 Cost Optimization Strategies

#### Strategy 1: Adaptive TTLs

Increase TTLs during high traffic to reduce API usage:

```python
def get_adaptive_ttl(content_type: ContentType, current_qpm: int) -> int:
    base_ttl = TTL_CONFIG[content_type]["base"]

    # Increase TTL if approaching rate limit
    if current_qpm > 80:
        return base_ttl * 2  # Double TTL during high traffic
    elif current_qpm > 60:
        return int(base_ttl * 1.5)  # 1.5x TTL
    else:
        return base_ttl
```

**Impact**: Reduces API usage by 20-30% during peaks

#### Strategy 2: User Tier Prioritization

Allocate API quota based on user tier:

```python
USER_TIER_QUOTAS = {
    "free": 5,      # 5 QPM per free user
    "pro": 20,      # 20 QPM per pro user
    "business": 50, # 50 QPM per business user
    "enterprise": None,  # Unlimited (dedicated infrastructure)
}

def rate_limit_user(user_id: str, user_tier: str) -> bool:
    quota = USER_TIER_QUOTAS[user_tier]
    current_usage = get_user_qpm(user_id)

    if quota and current_usage >= quota:
        return False  # Rate limited

    return True  # Allowed
```

**Impact**: Protects paid users, encourages upgrades

#### Strategy 3: Off-Peak Cache Warming

Schedule intensive cache warming during off-peak hours:

```python
def is_peak_hour() -> bool:
    hour = datetime.now().hour
    # Peak: 9am-5pm EST
    return 9 <= hour <= 17

# Warm cache more aggressively during off-peak
if not is_peak_hour():
    warm_cache_budget = 50  # 50 API calls
else:
    warm_cache_budget = 20  # 20 API calls (conserve quota)
```

**Impact**: Saves 30-40 API calls per hour during peak

---

## 8. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)

**Deliverables**:
- [ ] Implement Tier 1 (hot cache) with cachetools
- [ ] Implement Tier 2 (Redis) with compression
- [ ] Cache key generation with consistent hashing
- [ ] Basic TTL policies for all content types
- [ ] Prometheus metrics collection
- [ ] Unit tests for cache layer

**Success Criteria**:
- 60%+ cache hit rate
- P95 latency < 1s (cached)
- All 8 tools using cache

### Phase 2: Optimization (Week 3-4)

**Deliverables**:
- [ ] Request deduplication
- [ ] Cache warming on Actor startup
- [ ] Dynamic TTL calculation
- [ ] Grafana dashboards
- [ ] Alerting rules (Prometheus)
- [ ] Load testing (1,000 MAU)

**Success Criteria**:
- 75%+ cache hit rate
- P95 latency < 500ms (cached)
- Deduplication saving 10%+ API calls

### Phase 3: Scale (Week 5-8)

**Deliverables**:
- [ ] Predictive prefetching
- [ ] Redis clustering
- [ ] Multi-account API management
- [ ] Adaptive TTLs
- [ ] User tier quotas
- [ ] Load testing (5,000+ MAU)

**Success Criteria**:
- 80%+ cache hit rate
- Support 5,000+ MAU on free tier
- P95 latency < 200ms (cached)

---

## 9. Conclusion

This caching and performance architecture provides a comprehensive strategy to achieve:

1. **75-80% cache hit rate** through multi-tier caching and intelligent TTL policies
2. **Support for 5,000+ MAU** on Reddit's 100 QPM free tier
3. **Sub-second latency** for cached queries (P95 < 500ms)
4. **Scalability to 50,000+ MAU** with hybrid free/paid API strategy

**Key Success Factors**:
- Aggressive caching with dynamic TTLs
- Request deduplication and batching
- Proactive cache warming
- Continuous monitoring and optimization

**Next Steps**:
1. Implement Phase 1 (Foundation) in first 2 weeks
2. Deploy to production with 100 MAU beta
3. Monitor metrics and optimize TTLs based on real usage
4. Scale to 5,000+ MAU over 6 months

This architecture positions Reddit MCP Server to win the Apify $1M Challenge by supporting massive user growth while maintaining excellent performance and cost efficiency.
