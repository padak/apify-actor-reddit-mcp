# Feature Specifications - Reddit MCP Tools

## MVP Tools (Week 1-2)

### Tool 1: search_reddit

**Priority**: MUST HAVE (MVP)
**User Story**: As an AI developer, I want to search all of Reddit for keywords so that I can gather relevant discussions for my agent's context.

**Input Parameters:**
```json
{
  "query": {
    "type": "string",
    "required": true,
    "minLength": 1,
    "maxLength": 500,
    "description": "Search query or keywords"
  },
  "subreddit": {
    "type": "string",
    "required": false,
    "pattern": "^[A-Za-z0-9_]+$",
    "description": "Limit search to specific subreddit"
  },
  "time_filter": {
    "type": "string",
    "enum": ["hour", "day", "week", "month", "year", "all"],
    "default": "week"
  },
  "sort": {
    "type": "string",
    "enum": ["relevance", "hot", "top", "new", "comments"],
    "default": "relevance"
  },
  "limit": {
    "type": "integer",
    "minimum": 1,
    "maximum": 100,
    "default": 25
  }
}
```

**Output Format:**
```json
{
  "results": [
    {
      "id": "t3_abc123",
      "type": "post",
      "title": "Post title",
      "author": "username",
      "subreddit": "technology",
      "created_utc": 1699123456,
      "score": 1234,
      "num_comments": 567,
      "url": "https://...",
      "permalink": "/r/technology/...",
      "selftext": "Post content preview..."
    }
  ],
  "metadata": {
    "total_found": 1523,
    "returned": 25,
    "cached": true,
    "cache_age_seconds": 120,
    "rate_limit_remaining": 58
  }
}
```

**Performance Requirements:**
- Latency: <2s (uncached), <500ms (cached)
- Cache TTL: 5 minutes
- Success Rate: 99%+

**Error Cases:**
- Query too long (>500 chars) → 422 Invalid Parameters
- Subreddit not found → Return empty results
- Rate limit exceeded → Queue request, return estimated wait time

---

### Tool 2: get_subreddit_posts

**Priority**: MUST HAVE (MVP)
**User Story**: As a brand manager, I want to monitor specific subreddits for brand mentions so that I can respond to customer feedback.

**Input Parameters:**
```json
{
  "subreddit": {
    "type": "string",
    "required": true,
    "pattern": "^[A-Za-z0-9_]+$"
  },
  "sort": {
    "type": "string",
    "enum": ["hot", "new", "top", "rising", "controversial"],
    "default": "hot"
  },
  "time_filter": {
    "type": "string",
    "enum": ["hour", "day", "week", "month", "year", "all"],
    "required": false,
    "description": "Required for 'top' and 'controversial' sorts"
  },
  "limit": {
    "type": "integer",
    "minimum": 1,
    "maximum": 100,
    "default": 25
  }
}
```

**Output Format:**
```json
{
  "subreddit": "technology",
  "sort": "hot",
  "posts": [
    {
      "id": "t3_xyz789",
      "title": "Breaking: New AI Model Released",
      "author": "tech_enthusiast",
      "created_utc": 1699123456,
      "score": 5432,
      "upvote_ratio": 0.94,
      "num_comments": 891,
      "url": "https://example.com/article",
      "is_self": false,
      "link_flair_text": "AI/ML"
    }
  ],
  "metadata": {
    "cached": true,
    "cache_age_seconds": 180
  }
}
```

**Performance Requirements:**
- Latency: <1s (uncached), <300ms (cached)
- Cache TTL: 5 min (hot), 2 min (new), 1 hour (top historical)

---

### Tool 3: get_post_comments

**Priority**: MUST HAVE (MVP)
**User Story**: As a product manager, I want to read all comments on a specific post so that I can understand user sentiment and feedback.

**Input Parameters:**
```json
{
  "post_id": {
    "type": "string",
    "required": true,
    "description": "Reddit post ID (with or without t3_ prefix) or full URL"
  },
  "sort": {
    "type": "string",
    "enum": ["best", "top", "new", "controversial", "old"],
    "default": "best"
  },
  "max_depth": {
    "type": "integer",
    "minimum": 0,
    "maximum": 10,
    "default": 0,
    "description": "0 = all levels"
  }
}
```

**Output Format:**
```json
{
  "post": {
    "id": "t3_abc123",
    "title": "What's your favorite productivity tool?",
    "num_comments": 156
  },
  "comments": [
    {
      "id": "t1_def456",
      "author": "commenter1",
      "body": "I love Notion for organizing everything",
      "score": 89,
      "depth": 0,
      "replies": [
        {
          "id": "t1_ghi789",
          "body": "Notion is great! Also check out Obsidian",
          "score": 34,
          "depth": 1
        }
      ]
    }
  ],
  "metadata": {
    "total_comments": 156,
    "returned_comments": 156,
    "cached": false
  }
}
```

**Performance Requirements:**
- Latency: <5s (large threads), <2s (small threads)
- Cache TTL: 15 minutes

---

### Tool 4: get_trending_topics

**Priority**: MUST HAVE (MVP)
**User Story**: As a content creator, I want to discover trending topics on Reddit so that I can create timely content.

**Input Parameters:**
```json
{
  "scope": {
    "type": "string",
    "enum": ["all", "subreddit"],
    "default": "all"
  },
  "subreddit": {
    "type": "string",
    "required": false,
    "description": "Required if scope='subreddit'"
  },
  "timeframe": {
    "type": "string",
    "enum": ["hour", "day"],
    "default": "day"
  },
  "limit": {
    "type": "integer",
    "minimum": 1,
    "maximum": 50,
    "default": 10
  }
}
```

**Output Format:**
```json
{
  "trending_topics": [
    {
      "keyword": "ChatGPT-5",
      "mentions": 1523,
      "growth_rate": 2.34,
      "sentiment": "positive",
      "top_subreddits": ["technology", "artificial"],
      "sample_posts": [
        {
          "id": "t3_xyz123",
          "title": "ChatGPT-5 leaked features",
          "score": 8934
        }
      ]
    }
  ],
  "metadata": {
    "analysis_timestamp": 1699123456,
    "cached": true,
    "cache_age_seconds": 900
  }
}
```

**Performance Requirements:**
- Latency: <5s (first run), <500ms (cached)
- Cache TTL: 15 minutes (computationally expensive)

---

## v1.0 Tools (Week 3-4)

### Tool 5: analyze_sentiment

**Priority**: SHOULD HAVE (v1.0)
**User Story**: As a brand manager, I want automatic sentiment analysis of Reddit posts so that I don't need external NLP tools.

**Input Parameters:**
```json
{
  "content_type": {
    "type": "string",
    "enum": ["post", "comment", "search_results", "subreddit"],
    "required": true
  },
  "content_id": {
    "type": "string",
    "required": true,
    "description": "Post/comment ID or search query"
  },
  "time_filter": {
    "type": "string",
    "enum": ["hour", "day", "week", "month"],
    "default": "week"
  }
}
```

**Output Format:**
```json
{
  "overall_sentiment": {
    "score": 0.68,
    "label": "positive",
    "confidence": 0.82,
    "distribution": {
      "positive": 0.65,
      "neutral": 0.25,
      "negative": 0.10
    }
  },
  "analyzed_items": 156,
  "key_themes": [
    {
      "theme": "product quality",
      "sentiment": "positive",
      "mentions": 45
    }
  ]
}
```

**Performance Requirements:**
- Latency: <3s for batch analysis
- Cache TTL: 1 hour
- NLP Model: VADER (fast, lightweight)

---

### Tool 6: get_user_info

**Priority**: SHOULD HAVE (v1.0)
**User Story**: As a marketer, I want to identify influential Reddit users in my niche so that I can engage with them.

**Input Parameters:**
```json
{
  "username": {
    "type": "string",
    "required": true
  },
  "include_posts": {
    "type": "boolean",
    "default": true
  },
  "include_comments": {
    "type": "boolean",
    "default": true
  },
  "limit": {
    "type": "integer",
    "default": 25,
    "maximum": 100
  }
}
```

**Output Format:**
```json
{
  "user": {
    "username": "tech_enthusiast",
    "created_utc": 1609459200,
    "link_karma": 12543,
    "comment_karma": 45678,
    "is_gold": true
  },
  "activity_summary": {
    "most_active_subreddits": [
      {"name": "technology", "post_count": 45}
    ],
    "avg_score": 67.8
  },
  "recent_posts": [],
  "recent_comments": []
}
```

**Performance Requirements:**
- Latency: <1.5s
- Cache TTL: 10 minutes

---

### Tool 7: get_subreddit_info

**Priority**: SHOULD HAVE (v1.0)
**User Story**: As a researcher, I want metadata about subreddits so that I can select appropriate communities for my study.

**Input Parameters:**
```json
{
  "subreddit": {
    "type": "string",
    "required": true
  },
  "include_rules": {
    "type": "boolean",
    "default": false
  }
}
```

**Output Format:**
```json
{
  "subreddit": {
    "name": "technology",
    "title": "r/Technology",
    "subscribers": 14523678,
    "active_users": 25341,
    "created_utc": 1201233600,
    "description": "..."
  },
  "statistics": {
    "avg_posts_per_day": 127,
    "engagement_score": 8.7
  }
}
```

**Performance Requirements:**
- Latency: <800ms
- Cache TTL: 1 hour

---

### Tool 8: watch_keywords

**Priority**: SHOULD HAVE (v1.0)
**User Story**: As a brand manager, I want to set up keyword monitoring so that I get alerted to new mentions of my brand.

**Input Parameters:**
```json
{
  "keywords": {
    "type": "array",
    "items": {"type": "string"},
    "required": true
  },
  "subreddits": {
    "type": "array",
    "items": {"type": "string"},
    "required": false
  },
  "alert_threshold": {
    "type": "string",
    "enum": ["any", "high_engagement", "viral"],
    "default": "high_engagement"
  },
  "check_interval": {
    "type": "integer",
    "minimum": 5,
    "maximum": 1440,
    "default": 15,
    "description": "Minutes between checks"
  }
}
```

**Output Format:**
```json
{
  "watch_id": "watch_abc123",
  "status": "active",
  "matches_since_last_check": 12,
  "new_alerts": [
    {
      "post_id": "t3_xyz789",
      "title": "MyBrand just announced...",
      "score": 5432,
      "alert_reason": "high_engagement"
    }
  ]
}
```

**Implementation Notes:**
- Requires persistent storage (Apify Dataset)
- Background job processing (async)
- Not real-time (polling-based)

---

## Quality Metrics

### Success Criteria per Tool
- **Availability**: 99.5%+ uptime
- **Latency**: 95th percentile < targets above
- **Cache Hit Rate**: 75%+ overall
- **Error Rate**: <1% of requests
- **User Satisfaction**: NPS >40

### Monitoring
- Track latency by tool
- Monitor cache hit/miss rates
- Alert on error rate spikes
- Rate limit proximity warnings

## Implementation Priority

**Week 1:**
1. search_reddit
2. get_subreddit_posts

**Week 2:**
3. get_post_comments
4. get_trending_topics

**Week 3:**
5. analyze_sentiment
6. get_user_info

**Week 4:**
7. get_subreddit_info
8. watch_keywords
