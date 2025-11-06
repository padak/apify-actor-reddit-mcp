# Reddit API Deep Dive - Technical Research

## Executive Summary

Reddit API provides programmatic access via OAuth2 with 100 QPM free tier. Key limitations: 1,000 item cap, NSFW blocked since 2023, Pushshift shutdown impacts historical data access.

## Authentication & Rate Limits

### OAuth2 Flow
- **Free Tier**: 100 queries per minute (QPM) per OAuth client ID
- **Paid Tier**: $0.24 per 1,000 API calls (commercial use)
- **Authentication**: OAuth2 required, no unauthenticated access
- **Rate Limit Window**: 10-minute rolling average

### Best Libraries
- **Python**: PRAW (Python Reddit API Wrapper) - mature, handles auth/rate limits automatically
- **JavaScript**: Snoowrap - async/promise-based (last update 4 years ago)

## Key Endpoints

### Posts/Submissions
- `/r/{subreddit}/hot.json` - Hot posts
- `/r/{subreddit}/new.json` - New posts
- `/r/{subreddit}/top.json?t={time}` - Top posts (hour/day/week/month/year/all)
- `/r/{subreddit}/rising.json` - Rising posts
- `/search.json?q={query}` - Site-wide search

### Comments
- `/r/{subreddit}/comments/{id}.json` - Post with comments
- `/api/morechildren` - Fetch additional nested comments

### Users & Subreddits
- `/user/{username}/about.json` - User profile
- `/r/{subreddit}/about.json` - Subreddit metadata

## Critical Limitations

### 1,000 Item Cap
- Cannot retrieve more than ~1,000 items per listing
- Pagination stops after 1,000 items regardless of actual count
- **Workaround**: Time-based filtering, multiple queries

### NSFW Content Blocked
- All NSFW content inaccessible via API since mid-2023
- No workaround available

### Pushshift Shutdown (May 2023)
- Historical data archive no longer operational
- Impacted 1,700+ academic research papers
- **Alternative**: Static Pushshift dumps (outdated)

## Rate Limit Management

### Token Bucket Algorithm
```python
class RateLimiter:
    def __init__(self, max_calls=100, period=60):
        self.max_calls = max_calls
        self.period = period
        self.calls = []

    def wait_if_needed(self):
        now = datetime.now()
        self.calls = [c for c in self.calls
                      if now - c < timedelta(seconds=self.period)]

        if len(self.calls) >= self.max_calls:
            sleep_time = (self.calls[0] + timedelta(seconds=self.period) - now).total_seconds()
            time.sleep(max(0, sleep_time))
            self.calls = []

        self.calls.append(now)
```

### PRAW Built-in Rate Limiting
- Automatic 30-second caching
- Exponential backoff on 429 errors
- Respects `X-Ratelimit-*` headers

## Caching Strategy

### Recommended TTLs
| Content Type | Cache Duration | Reasoning |
|-------------|----------------|-----------|
| Hot posts | 5 minutes | Changes rapidly |
| New posts | 2 minutes | Real-time monitoring |
| Top posts (historical) | 1 hour | Stable over time |
| Comments | 15 minutes | Relatively static after initial activity |
| User profiles | 10 minutes | Changes slowly |
| Subreddit info | 1 hour | Very stable |

### Cache Key Pattern
```
reddit:{endpoint}:{params_hash}:{version}
```

## Cost Analysis

### Free Tier Economics
- 100 QPM = 6,000 requests/hour = 144,000 requests/day
- Sufficient for **500-1,000 moderate users**
- With 75% cache hit rate: **2,000-4,000 users** sustainable

### Paid Tier Costs
- $0.24 per 1,000 calls
- 1M calls/month = $240/month
- Typical user: 50 calls/day = 1,500/month
- 1,000 users = 1.5M calls = $360/month

### Optimization Strategy
1. Aggressive caching (75%+ hit rate target)
2. Request deduplication (coalesce identical queries)
3. Batch operations where possible
4. Use `.json` endpoints for public data (no auth needed, 10 QPM limit)

## Error Handling

### Common Errors
- **429 Too Many Requests**: Rate limit exceeded - exponential backoff
- **401 Unauthorized**: Token expired - refresh OAuth token
- **403 Forbidden**: Insufficient permissions - check scopes
- **404 Not Found**: Deleted/removed content - return cached if available
- **500/502/503**: Reddit server errors - retry with backoff

### Retry Strategy
```python
for attempt in range(max_retries):
    try:
        response = api_request()
        return response
    except RateLimitError as e:
        wait = int(e.retry_after)
        time.sleep(wait)
    except ServerError as e:
        wait = (2 ** attempt) + random.uniform(0, 1)
        time.sleep(wait)
```

## Data Structure

### Post Object (Key Fields)
```json
{
  "id": "t3_abc123",
  "title": "Post title",
  "author": "username",
  "subreddit": "technology",
  "created_utc": 1699123456,
  "score": 1234,
  "upvote_ratio": 0.94,
  "num_comments": 567,
  "url": "https://...",
  "selftext": "Post content...",
  "permalink": "/r/technology/comments/..."
}
```

### Comment Object (Key Fields)
```json
{
  "id": "t1_def456",
  "author": "commenter",
  "body": "Comment text",
  "score": 89,
  "created_utc": 1699123789,
  "depth": 0,
  "parent_id": "t3_abc123",
  "replies": []
}
```

## Best Practices

1. **User-Agent**: Always set unique, descriptive User-Agent
2. **OAuth Tokens**: Store securely, refresh before expiration
3. **Respect robots.txt**: Reddit updates regularly
4. **Cache Aggressively**: 30+ second minimum for all responses
5. **Batch Requests**: Group operations to minimize API calls
6. **Monitor Headers**: Track `X-Ratelimit-Remaining` proactively
7. **Handle Deletion**: Detect and purge deleted content from cache
8. **Comply with ToS**: No model training without permission

## Technical Constraints for MCP Server

### Must Address
- ✅ Rate limit management (100 QPM free tier)
- ✅ 1,000 item pagination cap
- ✅ OAuth token lifecycle management
- ✅ Intelligent caching (target 75%+ hit rate)
- ✅ Error handling with user-friendly messages
- ✅ Deleted content detection

### Cannot Solve
- ❌ NSFW content access (blocked by Reddit)
- ❌ Historical data beyond 1,000 items (Pushshift shutdown)
- ❌ Rate limit increases (fixed by Reddit)

## Implementation Recommendations

1. Use **PRAW** for Python (battle-tested, handles complexity)
2. Implement **Redis caching** with TTL-based invalidation
3. Build **request queue** with priority levels
4. Add **circuit breaker** for Reddit API failures
5. Monitor **cache hit rates** and optimize TTLs
6. Provide **transparent rate limit feedback** to users

## References

- Reddit API Docs: https://www.reddit.com/dev/api/
- PRAW Documentation: https://praw.readthedocs.io/
- OAuth2 Spec: https://github.com/reddit-archive/reddit/wiki/OAuth2
- Rate Limits: https://support.reddithelp.com/hc/en-us/articles/16160319875092
