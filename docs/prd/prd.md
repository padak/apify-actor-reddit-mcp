# Product Requirements Document (PRD)
# Reddit MCP Server - MVP (Week 1-2)

**Version:** 1.0
**Date:** 2025-11-05
**Status:** Approved for Development
**Target:** Apify $1M Challenge (5,000 MAU by Month 6)

---

## Executive Summary

The Reddit MCP Server is an enterprise-grade Model Context Protocol server that enables AI agents and developers to seamlessly access Reddit's 73M daily active users and 100K+ communities. This MVP (Week 1-2) delivers 4 core tools for read-only Reddit data access with aggressive caching to maximize performance and minimize API costs. The MVP establishes the technical foundation for monetization (v1.0, Week 3-4) and enterprise features (v2.0, Month 2+).

**Key Differentiator:** First monetized, production-ready Reddit MCP server with enterprise-grade caching and reliability.

---

## Goals & Success Metrics (Week 1-2 Only)

### Primary Goals
1. **Technical Validation**: Prove the architecture works end-to-end (MCP server + Redis cache + Reddit API)
2. **Performance Baseline**: Achieve 75%+ cache hit rate, <3s uncached latency
3. **Quality Foundation**: 65+ Apify quality score readiness (comprehensive docs, error handling)
4. **User Readiness**: Beta test with 10 users to validate core use cases

### Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Cache Hit Rate | >75% | Redis metrics after 100 requests |
| Latency (cached) | <500ms | p95 response time |
| Latency (uncached) | <3s | p95 response time |
| Error Rate | <1% | Failed requests / total requests |
| Test Coverage | >80% | Code coverage on core tools |
| Beta User Satisfaction | 8/10 avg | Post-test survey (10 users) |

### Non-Goals (Out of Scope for MVP)
- Monetization/pricing tiers (v1.0)
- Sentiment analysis (v1.0)
- User authentication (v1.0)
- Write operations (v2.0)
- Real-time monitoring (v2.0)
- Advanced analytics (v2.0)

---

## User Stories (MVP Only)

### Primary Persona: AI/LLM Developer

**US-1: Search Reddit**
**As an** AI developer
**I want to** search all of Reddit for keywords
**So that** my agent can gather relevant discussions for context
**Acceptance**: Can search with query, subreddit filter, time range, sort order, and limit

**US-2: Get Subreddit Posts**
**As a** brand manager
**I want to** monitor specific subreddits for new posts
**So that** I can track brand mentions in real-time
**Acceptance**: Can fetch hot/new/top/rising posts from any subreddit

**US-3: Read Post Comments**
**As a** product manager
**I want to** read all comments on a specific post
**So that** I can understand user sentiment and feedback
**Acceptance**: Can fetch nested comments with sorting options

**US-4: Discover Trending Topics**
**As a** content creator
**I want to** discover what's trending on Reddit
**So that** I can create timely content
**Acceptance**: Can get trending keywords with mentions, growth rate, and sample posts

---

## Functional Requirements (MVP)

### FR-1: Core MCP Tools (4 Required)

#### 1.1 search_reddit
- **Input**: query (1-500 chars), subreddit (optional), time_filter, sort, limit (1-100)
- **Output**: List of posts with metadata (id, title, author, score, comments, etc.)
- **Cache**: 5 minutes TTL
- **Performance**: <2s uncached, <500ms cached

#### 1.2 get_subreddit_posts
- **Input**: subreddit (required), sort (hot/new/top/rising/controversial), time_filter (for top/controversial), limit
- **Output**: List of posts from subreddit
- **Cache**: Variable (2min for new, 5min for hot, 1hr for top)
- **Performance**: <1s uncached, <300ms cached

#### 1.3 get_post_comments
- **Input**: post_id (or URL), sort (best/top/new/controversial/old), max_depth (0=all)
- **Output**: Nested comment tree with replies
- **Cache**: 15 minutes TTL
- **Performance**: <5s for large threads, <2s typical

#### 1.4 get_trending_topics
- **Input**: scope (all/subreddit), subreddit (if scope=subreddit), timeframe (hour/day), limit
- **Output**: List of trending keywords with mentions, growth rate, sentiment, sample posts
- **Cache**: 15 minutes TTL (expensive computation)
- **Performance**: <5s first run, <500ms cached

### FR-2: Caching System (Redis)

- **Requirement**: All Reddit API responses must be cached to minimize rate limit usage
- **TTL Strategy**: Variable by content type (2min to 1hr, see feature-specifications.md)
- **Cache Keys**: Hashed pattern `reddit:{tool}:{params_hash}:v1`
- **Metadata**: All responses include cache status (hit/miss, age, TTL)
- **Fail-Open**: If Redis unavailable, continue without caching (don't block requests)

### FR-3: Rate Limiting (Reddit API)

- **Limit**: 100 requests/minute (Reddit free tier)
- **Algorithm**: Token bucket with async wait
- **Behavior**: Queue requests when limit reached, wait until token available
- **Monitoring**: Include rate_limit_remaining in all responses

### FR-4: Error Handling

- **Input Validation**: All tool inputs validated with Pydantic (422 for invalid params)
- **Rate Limit**: Return JSON-RPC error with retry_after_seconds
- **API Errors**: Retry 3x with exponential backoff for 500/502/503
- **Not Found**: Return empty results (not an error) for deleted/removed content
- **Logging**: All errors logged with structured context

### FR-5: Response Format

All tools return standardized format:
```json
{
  "data": { /* tool-specific results */ },
  "metadata": {
    "cached": true/false,
    "cache_age_seconds": 120,
    "rate_limit_remaining": 58,
    "execution_time_ms": 234.5
  }
}
```

---

## Non-Functional Requirements

### NFR-1: Performance
- **Latency**: p95 <500ms (cached), <3s (uncached)
- **Throughput**: 100 req/min sustained (Reddit API limit)
- **Cache Hit Rate**: >75% after warm-up (100 requests)
- **Startup Time**: <2 seconds (Apify standby mode)

### NFR-2: Reliability
- **Availability**: 99.5% uptime (MVP target)
- **Error Rate**: <1% of all requests
- **Retry Logic**: 3 attempts with exponential backoff for transient errors
- **Graceful Degradation**: Continue if Redis down (no caching)

### NFR-3: Security
- **Credentials**: Reddit API keys stored in Apify Actor secrets (encrypted)
- **Input Validation**: All inputs sanitized (prevent injection attacks)
- **No PII**: No user data stored (stateless server)
- **HTTPS Only**: All external communications encrypted

### NFR-4: Observability
- **Structured Logging**: JSON logs with context (tool, params, duration, errors)
- **Metrics**: Track cache hit rate, latency, error rate per tool
- **Analytics**: Log all requests to Apify Dataset for usage analysis
- **Health Checks**: Apify standby mode health endpoint

### NFR-5: Maintainability
- **Type Safety**: 100% type hints on all functions
- **Documentation**: Docstrings on all public functions (Google style)
- **Test Coverage**: >80% coverage on core logic
- **Code Quality**: Black formatting, Ruff linting, mypy type checking

---

## Out of Scope (MVP)

### Explicitly NOT in Week 1-2:
- User authentication/API keys (add in v1.0)
- Sentiment analysis tool (add in v1.0)
- User info tool (add in v1.0)
- Subreddit info tool (add in v1.0)
- Write operations (post/comment/vote) (add in v2.0)
- Real-time keyword monitoring (add in v2.0)
- Pricing/billing integration (add in v1.0)
- Usage analytics dashboard (add in v1.0)
- Advanced NLP (BERT/transformers) (maybe v2.0+)
- WebSocket/SSE streaming (stick to HTTP for MVP)

### Deferred to Post-MVP:
- Horizontal scaling (multiple Reddit API accounts)
- Circuit breaker pattern (rely on retries for MVP)
- Request deduplication (nice-to-have, not critical)
- Cache warming on startup (add if cache hit rate <75%)

---

## Definition of Done (MVP Complete)

The MVP is complete when ALL of the following are true:

### Code Complete
- [ ] All 4 core tools implemented and tested
- [ ] Redis caching layer functional with TTL policies
- [ ] Rate limiter prevents exceeding 100 QPM
- [ ] Error handling covers all expected scenarios
- [ ] Type checking passes (mypy --strict)
- [ ] Code formatting passes (Black)
- [ ] Linting passes (Ruff)

### Quality Complete
- [ ] Test coverage >80% on src/tools, src/reddit, src/cache
- [ ] All tests passing (unit + integration)
- [ ] Manual testing with 10 real Reddit queries
- [ ] No critical bugs (P0/P1)
- [ ] Error rate <1% in testing

### Performance Complete
- [ ] Cache hit rate >75% after 100 requests
- [ ] p95 latency <500ms (cached), <3s (uncached)
- [ ] Startup time <2s
- [ ] Memory usage <150MB

### Documentation Complete
- [ ] README.md with setup instructions
- [ ] API documentation (tool inputs/outputs)
- [ ] Architecture diagrams in docs/
- [ ] Deployment guide for Apify
- [ ] Beta tester onboarding doc

### Deployment Complete
- [ ] Dockerfile builds successfully
- [ ] Deploys to Apify standby mode
- [ ] Environment variables configured
- [ ] Redis Cloud instance connected
- [ ] Health check endpoint responding

### Validation Complete
- [ ] Beta test with 10 users completed
- [ ] Average user satisfaction >8/10
- [ ] All critical user feedback documented
- [ ] Go/No-Go decision for v1.0 made

---

## Assumptions & Dependencies

### Assumptions
1. Reddit API free tier (100 QPM) is sufficient for MVP
2. Redis Cloud free tier (250MB) is sufficient for cache
3. Apify free tier (10GB-hrs) is sufficient for testing
4. 10 beta users will provide meaningful feedback
5. PRAW library remains stable and maintained

### External Dependencies
- **Reddit API**: Must remain accessible and within rate limits
- **Redis Cloud**: Free tier must remain available
- **Apify Platform**: Standby mode must work as documented
- **FastMCP Framework**: No breaking changes during development

### Internal Dependencies
- Developer availability: Full-time for Week 1-2
- Reddit API credentials: Obtained before Week 1 start
- Test users: 10 volunteers recruited before Week 2

---

## Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Reddit API rate limits too restrictive | Medium | High | Aggressive caching (>75% hit rate) |
| Redis unreliable in free tier | Low | Medium | Fail-open design (continue without cache) |
| PRAW library bugs | Low | Medium | Comprehensive error handling, version pinning |
| Cache hit rate <75% | Medium | Medium | Tune TTL policies, add cache warming |
| Beta users don't engage | Medium | Low | Incentivize with early access to v1.0 |

---

## Acceptance Criteria Summary

**The MVP is accepted when:**
1. All 4 tools work correctly with real Reddit data
2. Cache hit rate >75% and latency targets met
3. Error handling prevents all known failure modes
4. 10 beta users successfully complete test scenarios
5. Code quality meets standards (tests, types, docs)
6. Deploys to Apify standby mode successfully

---

## References

- [System Architecture](../system-architecture.md) - Detailed technical design
- [Feature Specifications](../feature-specifications.md) - Tool input/output schemas
- [Tech Stack](../architecture/tech-stack.md) - Technology choices
- [Coding Standards](../architecture/coding-standards.md) - Implementation guidelines
- [Source Tree](../architecture/source-tree.md) - Project structure

---

**Approval:**
- Product Manager: _________________ Date: _______
- Tech Lead: _________________ Date: _______
- Stakeholders: _________________ Date: _______
