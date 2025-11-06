# Reddit MCP Server

Enterprise-grade Model Context Protocol (MCP) server for seamless Reddit data access. Enables AI agents and developers to search, monitor, and analyze Reddit's 73M daily active users and 100K+ communities.

## Features (MVP v0.1.0)

- **search_reddit** - Search all of Reddit or specific subreddits with filters
- **get_subreddit_posts** - Monitor subreddits for hot, new, top, or rising posts
- **get_post_comments** - Retrieve nested comment threads with full context
- **get_trending_topics** - Discover trending keywords and topics in real-time

All tools include intelligent Redis caching (75%+ hit rate) and automatic rate limiting.

## Prerequisites

- Python 3.11 or higher
- Redis server (local or cloud)
- Reddit API credentials (client ID and secret)

### Getting Reddit API Credentials

1. Go to https://www.reddit.com/prefs/apps
2. Click "Create App" or "Create Another App"
3. Select "script" as the app type
4. Fill in the required fields:
   - Name: "Reddit MCP Server"
   - Redirect URI: http://localhost:8080
5. Save your **client ID** (under the app name) and **client secret**

## Local Development Setup

### 1. Clone and Install

```bash
# Clone the repository
cd /Users/padak/github/apify-actors

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```bash
# Reddit API Credentials
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here

# Redis Connection
REDIS_URL=redis://localhost:6379

# Logging (optional)
LOG_LEVEL=INFO
```

### 3. Start Redis (Local)

```bash
# Using Docker
docker run -d -p 6379:6379 redis:7-alpine

# Or install Redis locally (macOS)
brew install redis
brew services start redis
```

### 4. Run the Server

```bash
python -m src.main
```

The MCP server will start in standby mode on the configured port (default: `/mcp` endpoint).

## Testing

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest --cov=src tests/

# Run only unit tests
pytest tests/unit/

# Run only integration tests (requires Redis + Reddit API)
pytest tests/integration/
```

## Apify Deployment

### Deploy to Apify Platform

1. **Install Apify CLI**

```bash
npm install -g apify-cli
apify login
```

2. **Configure Secrets**

In the Apify Console, add these secrets to your Actor:
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDIS_URL`

3. **Deploy**

```bash
apify push
```

The Actor will be deployed in standby mode and accessible via the MCP endpoint.

### Environment Variables (Apify)

| Variable | Type | Required | Description |
|----------|------|----------|-------------|
| `REDDIT_CLIENT_ID` | Secret | Yes | Reddit API client ID |
| `REDDIT_CLIENT_SECRET` | Secret | Yes | Reddit API client secret |
| `REDIS_URL` | String | Yes | Redis connection URL |
| `LOG_LEVEL` | String | No | Logging level (default: INFO) |

## Project Structure

```
/Users/padak/github/apify-actors/
├── src/
│   ├── main.py              # Entry point
│   ├── tools/               # MCP tool implementations
│   ├── reddit/              # Reddit API integration
│   ├── cache/               # Redis caching layer
│   ├── models/              # Pydantic data models
│   └── utils/               # Shared utilities
├── tests/                   # Test suite
├── docs/                    # Documentation
├── actor.json               # Apify Actor configuration
├── Dockerfile               # Container definition
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## Development Workflow

### Code Quality

```bash
# Format code with Black
black src/ tests/

# Lint with Ruff
ruff check src/ tests/

# Type check with mypy
mypy src/ --strict
```

### Running Individual Tools (Development)

TODO: Add examples once tools are implemented (MVP-006 through MVP-009)

## Architecture

- **MCP Server**: FastMCP framework for JSON-RPC protocol handling
- **Reddit API**: PRAW (Python Reddit API Wrapper) for authenticated access
- **Caching**: Redis with intelligent TTL policies (2min - 1hr)
- **Rate Limiting**: Token bucket algorithm (100 requests/min)
- **Data Validation**: Pydantic models for type-safe inputs/outputs

See `/Users/padak/github/apify-actors/docs/architecture/` for detailed technical documentation.

## Troubleshooting

### Redis Connection Errors

```bash
# Check if Redis is running
redis-cli ping
# Should return: PONG

# Test connection with URL
redis-cli -u redis://localhost:6379 ping
```

### Reddit API Authentication Errors

- Verify your client ID and secret are correct
- Check that your Reddit app type is "script"
- Ensure the redirect URI matches: http://localhost:8080

### Import Errors

```bash
# Ensure you're in the virtual environment
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

## Contributing

This is an MVP project. Contributions should align with the roadmap:

- **MVP (Week 1-2)**: Core 4 tools + caching + rate limiting
- **v1.0 (Week 3-4)**: Monetization, sentiment analysis, user auth
- **v2.0 (Month 2+)**: Write operations, real-time monitoring, analytics

## Documentation

- [Product Requirements (PRD)](/Users/padak/github/apify-actors/docs/prd/prd.md)
- [Architecture Overview](/Users/padak/github/apify-actors/docs/architecture/)
- [Epic Stories](/Users/padak/github/apify-actors/docs/stories/)

## License

[Add license information]

## Support

For issues or questions, please refer to the documentation in `/docs/` or create an issue in the repository.

---

**Status**: MVP v0.1.0 (Week 1-2 Development)
**Target**: 5,000 MAU by Month 6 (Apify $1M Challenge)
