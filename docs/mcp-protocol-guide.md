# MCP Protocol Guide - Implementation Reference

## Executive Summary

Model Context Protocol (MCP) is an open standard by Anthropic (Nov 2024) enabling AI agents to access external tools and data. Current adoption: 8M downloads, 5,000+ servers, integrated by OpenAI, Google, Microsoft, AWS.

## Protocol Basics

### Architecture
```
┌─────────────────┐
│   MCP Host      │ (Claude, ChatGPT)
│  ┌───────────┐  │
│  │  Client   │  │
│  └─────┬─────┘  │
└────────┼────────┘
         │ JSON-RPC 2.0
    ┌────▼─────┐
    │  Server  │ (Our Reddit MCP)
    └──────────┘
```

### Protocol Specification
- **Base**: JSON-RPC 2.0
- **Version**: 2024-11-05 (current stable)
- **Transport**: stdio (local) or HTTP/SSE (remote)
- **Message Types**: Requests, Responses, Notifications

## Three Core Primitives

### 1. Tools (Functions AI Can Execute)
```python
@mcp.tool()
def search_reddit(query: str, limit: int = 25) -> dict:
    """Search Reddit for posts matching query"""
    return {"results": [...]}
```

**Tool Structure:**
- Name: Unique identifier
- Description: Human-readable explanation
- InputSchema: JSON Schema for parameters
- Implementation: Actual function logic

### 2. Resources (Read-Only Data Sources)
```python
@mcp.resource("subreddit://{name}")
def get_subreddit_info(name: str) -> dict:
    """Get subreddit metadata"""
    return {"subscribers": 1000000, ...}
```

**Resource Characteristics:**
- URI-based addressing
- No side effects (read-only)
- Can be subscribed to for updates
- Template parameters supported

### 3. Prompts (Reusable Templates)
```python
@mcp.prompt()
def analyze_sentiment(text: str) -> str:
    """Generate sentiment analysis prompt"""
    return f"Analyze sentiment of: {text}"
```

## Lifecycle & Initialization

### Three-Phase Handshake
```
1. Client → initialize → Server
2. Server → initialized response → Client
3. Client → initialized notification → Server
```

### Capability Negotiation
```json
{
  "capabilities": {
    "tools": {},
    "resources": {"subscribe": true},
    "prompts": {}
  }
}
```

## Python Implementation (FastMCP)

### Installation
```bash
pip install "mcp[cli]"
# or with UV
uv add "mcp[cli]"
```

### Basic Server
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("reddit-mcp-server")

@mcp.tool()
def search_reddit(query: str) -> dict:
    """Search Reddit posts"""
    return {"results": []}

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### Tool with Validation
```python
from pydantic import BaseModel, Field

class SearchParams(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(10, ge=1, le=100)

@mcp.tool()
def search_reddit(params: SearchParams) -> dict:
    return {"results": []}
```

## Apify Actor Integration

### Standby Mode Configuration
```json
{
  "actorSpecification": 1,
  "name": "reddit-mcp-server",
  "usesStandbyMode": true,
  "webServerMcpPath": "/mcp"
}
```

### Streamable HTTP Transport
```python
from mcp.server.sse import SseServerTransport
import express

app = express()

@app.post('/mcp')
async def mcp_endpoint(req, res):
    transport = SseServerTransport('/mcp', res)
    await server.connect(transport)

# Endpoint: https://username--actor.apify.actor/mcp
```

### Pay-Per-Event Monetization
```json
{
  "tool-request": {
    "eventTitle": "Tool Request",
    "eventPriceUsd": 0.05
  }
}
```

Trigger in code:
```python
await Actor.charge({"eventName": "tool-request"})
```

## Error Handling

### Standard Error Codes
- `-32700`: Parse error (invalid JSON)
- `-32600`: Invalid request
- `-32601`: Method not found
- `-32602`: Invalid parameters
- `-32603`: Internal error

### Error Response Format
```json
{
  "jsonrpc": "2.0",
  "id": 123,
  "error": {
    "code": -32602,
    "message": "Invalid parameters",
    "data": {"reason": "Query too long"}
  }
}
```

### Implementation
```python
from mcp.types import MCPError

@mcp.tool()
def search_reddit(query: str) -> dict:
    if len(query) > 500:
        raise MCPError(
            code=-32602,
            message="Query too long",
            data={"max_length": 500}
        )
    return {"results": []}
```

## Caching with MCP

### Response Metadata
```json
{
  "results": [...],
  "metadata": {
    "cached": true,
    "cache_age_seconds": 180,
    "rate_limit_remaining": 42
  }
}
```

### Cache Transparency
Always include cache indicators so AI can inform users about data freshness.

## Testing MCP Servers

### 1. MCP Inspector (Official Tool)
```bash
npm install -g @modelcontextprotocol/inspector
mcp-inspector python server.py
```

### 2. Claude Desktop Configuration
```json
{
  "mcpServers": {
    "reddit-mcp": {
      "command": "python",
      "args": ["/path/to/server.py"],
      "env": {
        "REDDIT_CLIENT_ID": "...",
        "REDDIT_CLIENT_SECRET": "..."
      }
    }
  }
}
```

Config location:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

### 3. Unit Testing
```python
import pytest

@pytest.mark.asyncio
async def test_search_reddit(server):
    result = await server.call_tool("search_reddit", {"query": "test"})
    assert "results" in result
```

## Performance Optimization

### Request Batching
MCP supports JSON-RPC batch operations (v2025-03-26):
```json
[
  {"method": "tools/call", "params": {...}, "id": 1},
  {"method": "tools/call", "params": {...}, "id": 2}
]
```

### Streaming Large Responses
For large datasets, consider pagination:
```python
@mcp.tool()
def search_reddit(query: str, offset: int = 0, limit: int = 25):
    return {
        "results": results[offset:offset+limit],
        "pagination": {"next_offset": offset + limit}
    }
```

## Security Best Practices

1. **Never expose secrets in code**
   ```python
   # ❌ BAD
   REDDIT_CLIENT_SECRET = "abc123"

   # ✅ GOOD
   REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
   ```

2. **Validate all inputs**
   ```python
   from pydantic import validator

   @validator('query')
   def sanitize_query(cls, v):
       return v.strip()[:500]  # Limit length
   ```

3. **Rate limit per-user**
   ```python
   @mcp.tool()
   async def search_reddit(context, query: str):
       user_id = context.user_id
       if not rate_limiter.check(user_id):
           raise MCPError(-32000, "Rate limit exceeded")
   ```

4. **Audit logging**
   ```python
   logger.info(json.dumps({
       "event": "tool_execution",
       "user": user_id,
       "tool": "search_reddit",
       "timestamp": datetime.utcnow().isoformat()
   }))
   ```

## Deployment Checklist

- [ ] MCP server implements all required tools
- [ ] Input/output schemas validated
- [ ] Error handling comprehensive
- [ ] Caching implemented (target 75%+ hit rate)
- [ ] Rate limiting configured
- [ ] Secrets management via env vars
- [ ] Logging and monitoring set up
- [ ] Testing (unit + integration)
- [ ] Documentation complete
- [ ] Apify standby mode configured
- [ ] Performance benchmarked (<1s latency target)

## Common Pitfalls

1. **Forgetting to handle rate limits**
   - Always implement retry with exponential backoff

2. **Not providing cache transparency**
   - Users need to know if data is stale

3. **Overly complex tool schemas**
   - Keep input parameters simple and optional

4. **Missing error context**
   - Provide actionable error messages

5. **Ignoring MCP version changes**
   - Monitor specification updates

## Resources

- MCP Specification: https://modelcontextprotocol.io
- FastMCP Framework: https://github.com/modelcontextprotocol/python-sdk
- Apify MCP Guide: https://blog.apify.com/build-and-deploy-mcp-servers-typescript/
- Example Servers: https://github.com/modelcontextprotocol/servers
- Claude Desktop Integration: https://docs.anthropic.com/claude/docs/mcp
