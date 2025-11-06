# Epic 01: MVP Foundation (Week 1-2)

**Epic ID:** EPIC-01
**Status:** Ready for Development
**Timeline:** Week 1-2 (10-14 days)
**Goal:** Deliver 4 core Reddit MCP tools with caching and rate limiting

---

## Epic Overview

This epic covers the complete MVP development for the Reddit MCP Server. It includes foundational infrastructure (project setup, caching, rate limiting), Reddit API integration, and implementation of 4 core MCP tools. The epic is designed to be completed in 2 weeks by a single developer.

**Success Criteria:**
- All 10 stories completed and tested
- Cache hit rate >75%
- All tests passing
- Deployable to Apify standby mode

---

## Stories (Priority Order)

### WEEK 1: Foundation (Stories 1-5)

## Story 1: Setup Apify Actor Project Structure

**Story ID:** MVP-001
**Priority:** P0 (Blocker)
**Estimated Effort:** M (4-6 hours)

### User Story
As a developer, I want the complete project structure set up so that I can start implementing features immediately.

### Acceptance Criteria
- [ ] Project follows source-tree.md structure exactly
- [ ] All directories created (src/tools, src/reddit, src/cache, src/models, src/utils, tests/)
- [ ] actor.json configured with correct settings (standby mode, environment variables)
- [ ] Dockerfile builds successfully using apify/actor-python:3.11 base
- [ ] requirements.txt includes all MVP dependencies (8 packages)
- [ ] .env.example created with all required environment variables
- [ ] pyproject.toml configured for Black, Ruff, mypy
- [ ] .gitignore excludes .env, __pycache__, venv/
- [ ] README.md created with project overview and setup instructions

### Technical Notes
- Reference: `/Users/padak/github/apify-actors/docs/architecture/source-tree.md`
- Use exact actor.json structure from source-tree.md lines 90-122
- Pin all dependency versions in requirements.txt (see tech-stack.md lines 103-129)
- Dockerfile must use multi-stage build if needed for optimization

### Definition of Done
- [ ] `docker build .` succeeds without errors
- [ ] All directories exist with __init__.py files
- [ ] `pip install -r requirements.txt` installs without conflicts
- [ ] Git repository initialized with clean .gitignore
- [ ] README.md includes prerequisites, setup steps, and run instructions

### Dependencies
None (first story)

---

## Story 2: Implement Redis Caching Layer

**Story ID:** MVP-002
**Priority:** P0 (Blocker)
**Estimated Effort:** M (4-6 hours)

### User Story
As a developer, I want a Redis caching layer so that I can minimize Reddit API calls and improve response times.

### Acceptance Criteria
- [ ] CacheManager class implemented in src/cache/manager.py
- [ ] Async methods: get(), set(), get_or_fetch()
- [ ] Connection pooling configured (max 20 connections)
- [ ] TTL policies defined in src/cache/ttl.py (CacheTTL enum)
- [ ] Cache key generation in src/cache/keys.py (pattern: reddit:{tool}:{hash}:v1)
- [ ] Fail-open behavior: continues if Redis unavailable
- [ ] All cache operations logged (debug level for hits/misses)

### Technical Notes
- Reference: system-architecture.md lines 719-1082 for implementation details
- Use redis[asyncio] library for async support
- Cache keys must be hashed with MD5 for consistency (max 12 chars of hash)
- TTL values from feature-specifications.md:
  - NEW_POSTS = 120s
  - HOT_POSTS = 300s
  - TOP_POSTS = 3600s
  - SEARCH_RESULTS = 300s
  - COMMENTS = 900s
  - TRENDING_TOPICS = 900s

### Definition of Done
- [ ] Unit tests for CacheManager.get(), set(), get_or_fetch()
- [ ] Test cache hit/miss scenarios
- [ ] Test Redis connection failure (fail-open)
- [ ] Test TTL expiration
- [ ] mypy type checking passes
- [ ] Cache key generation is deterministic (same params = same key)

### Dependencies
- MVP-001 (project structure)

---

## Story 3: Setup Reddit API Client (PRAW)

**Story ID:** MVP-003
**Priority:** P0 (Blocker)
**Estimated Effort:** S (2-3 hours)

### User Story
As a developer, I want a configured Reddit API client so that I can make authenticated requests to Reddit.

### Acceptance Criteria
- [ ] RedditClientManager class in src/reddit/client.py
- [ ] Singleton pattern (one client instance)
- [ ] OAuth2 credentials loaded from environment (REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)
- [ ] Client configured as read-only
- [ ] User agent follows Reddit guidelines (Reddit-MCP-Server/1.0)
- [ ] Client validates credentials on initialization
- [ ] Timeout set to 30 seconds
- [ ] Connection pooling enabled (PRAW default)

### Technical Notes
- Reference: system-architecture.md lines 346-388
- PRAW documentation: https://praw.readthedocs.io/
- Credentials stored in Apify Actor secrets (production) or .env (local)
- Initialize with `reddit.read_only = True` for MVP (no write operations)

### Definition of Done
- [ ] RedditClientManager.get_client() returns working PRAW instance
- [ ] Test authentication with valid credentials
- [ ] Test authentication failure with invalid credentials
- [ ] Client singleton verified (same instance returned)
- [ ] Credentials never logged or exposed

### Dependencies
- MVP-001 (project structure)

---

## Story 4: Implement Rate Limiter (Token Bucket)

**Story ID:** MVP-004
**Priority:** P0 (Blocker)
**Estimated Effort:** M (4-6 hours)

### User Story
As a developer, I want a rate limiter so that I never exceed Reddit's 100 requests/minute limit.

### Acceptance Criteria
- [ ] TokenBucketRateLimiter class in src/reddit/rate_limiter.py
- [ ] Async acquire() method blocks until token available
- [ ] Configured for 100 calls per 60 seconds
- [ ] Tracks call timestamps in deque (rolling window)
- [ ] get_remaining() returns available calls in current window
- [ ] Logs warnings when rate limit approached (>90 calls)
- [ ] Priority parameter (optional): 0=normal, 1=high, -1=low

### Technical Notes
- Reference: system-architecture.md lines 442-501
- Use asyncio.Lock for thread safety
- Use collections.deque for efficient timestamp tracking
- Algorithm: Remove timestamps older than 60s, check if <100 remaining, wait if needed
- Calculate wait time as: (oldest_timestamp + 60s - now)

### Definition of Done
- [ ] Unit test: 100 calls succeed immediately
- [ ] Unit test: 101st call waits ~1 second
- [ ] Unit test: get_remaining() returns correct count
- [ ] Integration test: Rate limiter prevents 429 errors from Reddit
- [ ] Logging shows wait time when limit hit

### Dependencies
- MVP-001 (project structure)

---

## Story 5: Create FastMCP Server Foundation

**Story ID:** MVP-005
**Priority:** P0 (Blocker)
**Estimated Effort:** S (2-3 hours)

### User Story
As a developer, I want the FastMCP server initialized so that I can register MCP tools.

### Acceptance Criteria
- [ ] FastMCP server created in src/server.py
- [ ] Server metadata configured (name, version, description)
- [ ] Capabilities declared (tools only, no resources/prompts for MVP)
- [ ] Error handler middleware attached
- [ ] Structured logging configured in src/utils/logger.py
- [ ] Main entry point in src/main.py starts server
- [ ] Server runs in Apify Actor context (async with Actor:)

### Technical Notes
- Reference: system-architecture.md lines 156-339
- FastMCP initialization pattern from docs
- Use structlog for JSON logging (see coding-standards.md lines 378-419)
- Entry point must use `asyncio.run(main())` pattern
- Apify Actor.init() required for standby mode

### Definition of Done
- [ ] Server starts without errors
- [ ] Health check responds (Apify standby mode)
- [ ] Logs output in JSON format
- [ ] No tools registered yet (that's next stories)
- [ ] Can run with: `python -m src.main`

### Dependencies
- MVP-001 (project structure)

---

### WEEK 1: First Tools (Stories 6-7)

## Story 6: Implement Tool - search_reddit

**Story ID:** MVP-006
**Priority:** P0 (Must Have)
**Estimated Effort:** L (6-8 hours)

### User Story
As an AI developer, I want to search all of Reddit for keywords so that my agent can gather relevant discussions.

### Acceptance Criteria
- [ ] SearchRedditInput model in src/models/inputs.py with validation
- [ ] search_reddit function in src/tools/search.py
- [ ] Tool registered in src/server.py
- [ ] Implements cache-aside pattern (check cache → fetch → cache result)
- [ ] Supports all parameters: query, subreddit, time_filter, sort, limit
- [ ] Returns standardized output format (results + metadata)
- [ ] Response normalization using ResponseNormalizer
- [ ] Metadata includes: cached, cache_age_seconds, rate_limit_remaining

### Technical Notes
- Reference: feature-specifications.md lines 5-82 for exact schema
- Reference: system-architecture.md lines 1087-1160 for implementation
- Input validation:
  - query: 1-500 chars, required
  - subreddit: optional, pattern ^[A-Za-z0-9_]+$
  - time_filter: enum [hour, day, week, month, year, all], default week
  - sort: enum [relevance, hot, top, new, comments], default relevance
  - limit: 1-100, default 25
- Cache TTL: 300 seconds (5 minutes)
- PRAW call: `reddit.subreddit('all').search(query=..., sort=..., time_filter=..., limit=...)`

### Definition of Done
- [ ] Unit test: Valid input succeeds
- [ ] Unit test: Invalid input raises ValidationError
- [ ] Integration test: Real Reddit search returns results
- [ ] Integration test: Second identical search returns cached (faster)
- [ ] Integration test: Deleted subreddit returns empty results
- [ ] Response format matches feature-specifications.md
- [ ] Cache hit rate >75% in manual testing (10 duplicate queries)

### Dependencies
- MVP-002 (caching)
- MVP-003 (Reddit client)
- MVP-004 (rate limiter)
- MVP-005 (FastMCP server)

---

## Story 7: Implement Tool - get_subreddit_posts

**Story ID:** MVP-007
**Priority:** P0 (Must Have)
**Estimated Effort:** M (4-6 hours)

### User Story
As a brand manager, I want to monitor specific subreddits for new posts so that I can track brand mentions.

### Acceptance Criteria
- [ ] GetSubredditPostsInput model with validation
- [ ] get_subreddit_posts function in src/tools/posts.py
- [ ] Tool registered in server
- [ ] Supports all sort options: hot, new, top, rising, controversial
- [ ] time_filter validated (required for top/controversial, optional otherwise)
- [ ] Variable TTL by sort type (2min for new, 5min for hot, 1hr for top)
- [ ] Response normalization (post objects)

### Technical Notes
- Reference: feature-specifications.md lines 85-147
- Reference: system-architecture.md lines 1164-1230
- Input validation:
  - subreddit: required, pattern ^[A-Za-z0-9_]+$
  - sort: enum [hot, new, top, rising, controversial], default hot
  - time_filter: enum, required ONLY if sort is top/controversial
  - limit: 1-100, default 25
- PRAW calls:
  - hot: `subreddit.hot(limit=...)`
  - new: `subreddit.new(limit=...)`
  - top: `subreddit.top(time_filter=..., limit=...)`
  - rising: `subreddit.rising(limit=...)`
  - controversial: `subreddit.controversial(time_filter=..., limit=...)`

### Definition of Done
- [ ] Unit test: Validator requires time_filter for top/controversial
- [ ] Unit test: Validator rejects invalid subreddit names
- [ ] Integration test: Each sort type returns correct ordering
- [ ] Integration test: Cache TTL varies by sort type
- [ ] Integration test: Private subreddit returns permission error
- [ ] Response includes upvote_ratio, link_flair_text

### Dependencies
- MVP-006 (similar pattern, can reuse normalizer)

---

### WEEK 2: Complete MVP (Stories 8-10)

## Story 8: Implement Tool - get_post_comments

**Story ID:** MVP-008
**Priority:** P0 (Must Have)
**Estimated Effort:** L (6-8 hours)

### User Story
As a product manager, I want to read all comments on a specific post so that I can understand user sentiment.

### Acceptance Criteria
- [ ] GetPostCommentsInput model with validation
- [ ] get_post_comments function in src/tools/comments.py
- [ ] Tool registered in server
- [ ] Accepts post_id with or without t3_ prefix
- [ ] Accepts full Reddit URL and extracts post_id
- [ ] Supports comment sorting: best, top, new, controversial, old
- [ ] max_depth parameter (0 = all levels, 1-10 = limit depth)
- [ ] Builds nested comment tree structure
- [ ] Handles "more comments" (PRAW replace_more)

### Technical Notes
- Reference: feature-specifications.md lines 150-214
- Reference: system-architecture.md lines 1233-1313
- Input validation:
  - post_id: required, can be ID or URL
  - sort: enum [best, top, new, controversial, old], default best
  - max_depth: 0-10, default 0 (all)
- Cache TTL: 900 seconds (15 minutes)
- PRAW calls:
  - `submission = reddit.submission(id=post_id)`
  - `submission.comment_sort = sort`
  - `submission.comments.replace_more(limit=0)` (expand all)
  - `submission.comments.list()` (flatten)
- Must build tree: parent_id determines nesting

### Definition of Done
- [ ] Unit test: URL parsing extracts correct post_id
- [ ] Unit test: max_depth filters comments correctly
- [ ] Integration test: Nested comments build correct tree
- [ ] Integration test: Deleted comments handled ([deleted] author)
- [ ] Integration test: Large thread (500+ comments) completes <5s
- [ ] Response includes comment depth, parent_id, replies array

### Dependencies
- MVP-007 (similar pattern)

---

## Story 9: Implement Tool - get_trending_topics

**Story ID:** MVP-009
**Priority:** P0 (Must Have)
**Estimated Effort:** L (6-8 hours)

### User Story
As a content creator, I want to discover trending topics on Reddit so that I can create timely content.

### Acceptance Criteria
- [ ] GetTrendingTopicsInput model with validation
- [ ] get_trending_topics function in src/tools/trending.py
- [ ] Tool registered in server
- [ ] Supports scope: all or specific subreddit
- [ ] Supports timeframe: hour or day
- [ ] Keyword extraction from post titles
- [ ] Frequency counting (mentions per keyword)
- [ ] Growth rate calculation (simple approach)
- [ ] Returns top N keywords with sample posts

### Technical Notes
- Reference: feature-specifications.md lines 217-279
- Reference: system-architecture.md lines 1317-1405
- Input validation:
  - scope: enum [all, subreddit], default all
  - subreddit: required if scope=subreddit
  - timeframe: enum [hour, day], default day
  - limit: 1-50, default 10
- Cache TTL: 900 seconds (15 minutes) - computationally expensive
- Algorithm (simplified for MVP):
  1. Fetch new/top posts (100-200 posts)
  2. Tokenize titles (simple word split, lowercase)
  3. Count keyword frequency
  4. Filter keywords (>3 mentions)
  5. Sort by frequency
  6. Return top N with sample posts
- Growth rate calculation: Simplified (mentions in last hour / mentions in previous hour)

### Definition of Done
- [ ] Unit test: Keyword extraction works on sample titles
- [ ] Unit test: Frequency counting correct
- [ ] Integration test: Returns trending keywords from r/all
- [ ] Integration test: Subreddit-specific trending works
- [ ] Integration test: Sample posts include title, score, id
- [ ] Performance: <5s on first run, <500ms cached
- [ ] Sentiment field populated (can be simple: "neutral" for MVP)

### Dependencies
- MVP-008 (similar caching pattern)

---

## Story 10: Testing & Documentation

**Story ID:** MVP-010
**Priority:** P0 (Must Have)
**Estimated Effort:** L (8-10 hours)

### User Story
As a developer, I want comprehensive tests and documentation so that the MVP is production-ready.

### Acceptance Criteria

#### Testing
- [ ] Unit tests for all cache operations (get, set, get_or_fetch, TTL)
- [ ] Unit tests for rate limiter (token bucket logic, get_remaining)
- [ ] Unit tests for all Pydantic input models (validation, sanitization)
- [ ] Unit tests for response normalization (post, comment)
- [ ] Integration tests for all 4 tools (real Reddit API)
- [ ] Integration test: Cache hit/miss flow end-to-end
- [ ] Integration test: Rate limiting prevents 429 errors
- [ ] Error scenario tests: Invalid subreddit, deleted post, rate limit hit, Redis down
- [ ] Test coverage >80% on src/tools, src/reddit, src/cache
- [ ] All tests passing in CI/CD

#### Documentation
- [ ] README.md: Setup instructions (prerequisites, install, run)
- [ ] README.md: Environment variables documented
- [ ] README.md: Testing instructions
- [ ] API documentation: Input/output schemas for all 4 tools
- [ ] Architecture diagram: High-level system flow
- [ ] Deployment guide: How to deploy to Apify
- [ ] Beta tester guide: Test scenarios and feedback form

### Technical Notes
- Use pytest with pytest-asyncio for async tests
- Mock PRAW calls in unit tests (use pytest fixtures)
- Use real Reddit API in integration tests (mark with @pytest.mark.integration)
- CI/CD: GitHub Actions workflow (.github/workflows/test.yml)
- Coverage tool: pytest-cov

### Definition of Done
- [ ] `pytest tests/` runs all tests successfully
- [ ] `pytest --cov=src tests/` shows >80% coverage
- [ ] README.md verified by fresh setup (new developer can run)
- [ ] All error scenarios documented in tests
- [ ] Beta tester guide includes 5 test scenarios
- [ ] Architecture diagram exported to docs/ as PNG/SVG

### Dependencies
- MVP-006, MVP-007, MVP-008, MVP-009 (all tools implemented)

---

## Epic Metrics

### Velocity Tracking
- Total Story Points: ~55 hours (assuming 1 point = 1 hour)
- Week 1: Stories 1-7 (~30 hours)
- Week 2: Stories 8-10 (~25 hours)

### Success Criteria (Epic Level)
- [ ] All 10 stories completed and in "Done" status
- [ ] Zero P0/P1 bugs remaining
- [ ] Cache hit rate >75% in production testing
- [ ] Latency targets met (p95 <500ms cached, <3s uncached)
- [ ] Deployed to Apify standby mode successfully
- [ ] 10 beta users complete testing

---

## Risk Register

| Risk | Impact | Mitigation | Owner |
|------|--------|-----------|-------|
| Reddit API changes during dev | High | Version pin PRAW, monitor Reddit changelog | Dev |
| Cache hit rate <75% | Medium | Tune TTL policies, add cache warming | Dev |
| Integration tests flaky | Medium | Add retry logic, use stable test subreddits | Dev |
| Week 1 scope creep | High | Strict adherence to MVP scope, defer to v1.0 | PM |

---

## Epic Retrospective (Post-Completion)

*To be filled after epic completion*

### What Went Well
-

### What Could Be Improved
-

### Action Items for Next Epic
-

---

**Epic Owner:** [Developer Name]
**Reviewed By:** [Tech Lead]
**Status:** Ready for Sprint Planning
