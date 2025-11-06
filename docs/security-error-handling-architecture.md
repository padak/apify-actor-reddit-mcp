# Security & Error Handling Architecture
## Reddit MCP Server - Production-Grade Design

**Version**: 1.0
**Last Updated**: 2025-11-05
**Status**: Architecture Specification

---

## Table of Contents

1. [Security Architecture](#1-security-architecture)
2. [Error Handling Architecture](#2-error-handling-architecture)
3. [Rate Limit Management](#3-rate-limit-management)
4. [Monitoring & Observability](#4-monitoring--observability)
5. [Fault Tolerance & Recovery](#5-fault-tolerance--recovery)
6. [Implementation Checklist](#6-implementation-checklist)

---

## 1. Security Architecture

### 1.1 Authentication & Authorization

#### OAuth2 Flow for Reddit API

**Implementation Strategy:**
```python
# src/auth/reddit_oauth.py

from typing import Optional
from datetime import datetime, timedelta
import httpx
from pydantic import BaseModel, SecretStr

class RedditOAuthConfig(BaseModel):
    """Secure configuration for Reddit OAuth."""
    client_id: str
    client_secret: SecretStr  # Never logged or printed
    redirect_uri: str
    user_agent: str

class OAuthToken(BaseModel):
    """OAuth token with metadata."""
    access_token: SecretStr
    refresh_token: Optional[SecretStr] = None
    expires_at: datetime
    token_type: str = "bearer"
    scope: str

class RedditAuthManager:
    """Handles Reddit OAuth2 authentication lifecycle."""

    def __init__(self, config: RedditOAuthConfig, kv_store):
        self.config = config
        self.kv_store = kv_store  # Apify KV Store for encrypted storage
        self._current_token: Optional[OAuthToken] = None

    async def get_authorization_url(self, state: str) -> str:
        """Generate OAuth2 authorization URL for user consent."""
        params = {
            "client_id": self.config.client_id,
            "response_type": "code",
            "state": state,  # CSRF protection
            "redirect_uri": self.config.redirect_uri,
            "duration": "permanent",  # Get refresh token
            "scope": "read identity mysubreddits"
        }
        return f"https://www.reddit.com/api/v1/authorize?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> OAuthToken:
        """Exchange authorization code for access token."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(self.config.client_id, self.config.client_secret.get_secret_value()),
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.config.redirect_uri
                },
                headers={"User-Agent": self.config.user_agent}
            )
            response.raise_for_status()
            data = response.json()

            token = OAuthToken(
                access_token=SecretStr(data["access_token"]),
                refresh_token=SecretStr(data.get("refresh_token")),
                expires_at=datetime.utcnow() + timedelta(seconds=data["expires_in"]),
                scope=data["scope"]
            )

            # Store encrypted in Apify KV Store
            await self._store_token(token)
            return token

    async def get_valid_token(self) -> str:
        """Get valid access token, refreshing if needed."""
        if not self._current_token:
            self._current_token = await self._load_token()

        # Check if token expires in next 5 minutes
        if datetime.utcnow() >= (self._current_token.expires_at - timedelta(minutes=5)):
            self._current_token = await self._refresh_token()

        return self._current_token.access_token.get_secret_value()

    async def _refresh_token(self) -> OAuthToken:
        """Refresh expired OAuth token."""
        if not self._current_token or not self._current_token.refresh_token:
            raise AuthenticationError("No refresh token available")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(self.config.client_id, self.config.client_secret.get_secret_value()),
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._current_token.refresh_token.get_secret_value()
                },
                headers={"User-Agent": self.config.user_agent}
            )
            response.raise_for_status()
            data = response.json()

            new_token = OAuthToken(
                access_token=SecretStr(data["access_token"]),
                refresh_token=self._current_token.refresh_token,  # Reuse existing
                expires_at=datetime.utcnow() + timedelta(seconds=data["expires_in"]),
                scope=data["scope"]
            )

            await self._store_token(new_token)
            return new_token

    async def _store_token(self, token: OAuthToken) -> None:
        """Store token encrypted in Apify KV Store."""
        # Apify KV Store handles encryption at rest
        await self.kv_store.set_value(
            "reddit_oauth_token",
            {
                "access_token": token.access_token.get_secret_value(),
                "refresh_token": token.refresh_token.get_secret_value() if token.refresh_token else None,
                "expires_at": token.expires_at.isoformat(),
                "scope": token.scope
            }
        )

    async def _load_token(self) -> OAuthToken:
        """Load token from KV Store."""
        data = await self.kv_store.get_value("reddit_oauth_token")
        if not data:
            raise AuthenticationError("No stored token found")

        return OAuthToken(
            access_token=SecretStr(data["access_token"]),
            refresh_token=SecretStr(data["refresh_token"]) if data.get("refresh_token") else None,
            expires_at=datetime.fromisoformat(data["expires_at"]),
            scope=data["scope"]
        )
```

#### MCP Client Authentication

**Bearer Token Authentication for MCP Clients:**
```python
# src/auth/mcp_auth.py

from typing import Optional
import hashlib
import secrets
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

class MCPAuthManager:
    """Authenticates MCP clients connecting to the server."""

    def __init__(self, kv_store):
        self.kv_store = kv_store
        self.valid_tokens: dict[str, dict] = {}  # In-memory cache

    async def generate_api_key(self, user_id: str, name: str) -> str:
        """Generate a new API key for a user."""
        # Generate cryptographically secure random token
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        # Store hash (never store plaintext!)
        await self.kv_store.set_value(
            f"api_key:{token_hash}",
            {
                "user_id": user_id,
                "name": name,
                "created_at": datetime.utcnow().isoformat(),
                "last_used": None,
                "rate_limit_tier": "free"  # or "paid"
            }
        )

        return token  # Return once, never stored

    async def validate_token(
        self,
        credentials: HTTPAuthorizationCredentials = Security(security)
    ) -> dict:
        """Validate bearer token and return user info."""
        token = credentials.credentials
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        # Check cache first
        if token_hash in self.valid_tokens:
            return self.valid_tokens[token_hash]

        # Load from KV Store
        token_data = await self.kv_store.get_value(f"api_key:{token_hash}")
        if not token_data:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Update last used timestamp
        token_data["last_used"] = datetime.utcnow().isoformat()
        await self.kv_store.set_value(f"api_key:{token_hash}", token_data)

        # Cache for 5 minutes
        self.valid_tokens[token_hash] = token_data

        return token_data
```

#### Rate Limiting Per User

**Per-User Rate Limiting:**
```python
# src/auth/rate_limiter.py

from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional
import asyncio

class UserRateLimiter:
    """Rate limiter with per-user quotas."""

    def __init__(self, kv_store):
        self.kv_store = kv_store
        self.quotas = {
            "free": {"requests_per_minute": 10, "requests_per_hour": 300},
            "paid": {"requests_per_minute": 50, "requests_per_hour": 2000}
        }

    async def check_rate_limit(self, user_id: str, tier: str) -> dict:
        """Check if user has exceeded rate limit."""
        now = datetime.utcnow()
        key = f"rate_limit:{user_id}"

        # Get current usage
        usage = await self.kv_store.get_value(key) or {
            "minute_requests": [],
            "hour_requests": []
        }

        # Clean old entries
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)

        usage["minute_requests"] = [
            req for req in usage["minute_requests"]
            if datetime.fromisoformat(req) > minute_ago
        ]
        usage["hour_requests"] = [
            req for req in usage["hour_requests"]
            if datetime.fromisoformat(req) > hour_ago
        ]

        # Check limits
        quota = self.quotas[tier]
        minute_count = len(usage["minute_requests"])
        hour_count = len(usage["hour_requests"])

        if minute_count >= quota["requests_per_minute"]:
            return {
                "allowed": False,
                "reason": "Rate limit exceeded (per minute)",
                "retry_after_seconds": 60,
                "quota_remaining": 0,
                "quota_limit": quota["requests_per_minute"]
            }

        if hour_count >= quota["requests_per_hour"]:
            return {
                "allowed": False,
                "reason": "Rate limit exceeded (per hour)",
                "retry_after_seconds": 3600,
                "quota_remaining": 0,
                "quota_limit": quota["requests_per_hour"]
            }

        # Record this request
        usage["minute_requests"].append(now.isoformat())
        usage["hour_requests"].append(now.isoformat())
        await self.kv_store.set_value(key, usage, expiration_ttl=3600)

        return {
            "allowed": True,
            "quota_remaining": quota["requests_per_minute"] - minute_count - 1,
            "quota_limit": quota["requests_per_minute"]
        }
```

---

### 1.2 Secrets Management

#### Apify Console Configuration

**Environment Variable Strategy:**

```yaml
# .actor/actor.json
{
  "name": "reddit-mcp-server",
  "version": "1.0.0",
  "environmentVariables": {
    "REDDIT_CLIENT_ID": {
      "type": "string",
      "description": "Reddit OAuth2 Client ID",
      "isSecret": true
    },
    "REDDIT_CLIENT_SECRET": {
      "type": "string",
      "description": "Reddit OAuth2 Client Secret",
      "isSecret": true
    },
    "MCP_MASTER_KEY": {
      "type": "string",
      "description": "Master key for encrypting API keys",
      "isSecret": true
    },
    "REDIS_URL": {
      "type": "string",
      "description": "Redis connection URL with credentials",
      "isSecret": true
    },
    "SENTRY_DSN": {
      "type": "string",
      "description": "Sentry error tracking DSN",
      "isSecret": true,
      "optional": true
    }
  }
}
```

**Configuration Loader:**
```python
# src/config/settings.py

from pydantic import BaseSettings, SecretStr, validator
from typing import Optional

class Settings(BaseSettings):
    """Application settings with secure defaults."""

    # Reddit OAuth
    reddit_client_id: str
    reddit_client_secret: SecretStr
    reddit_redirect_uri: str = "http://localhost:3000/auth/callback"
    reddit_user_agent: str = "RedditMCPServer/1.0"

    # MCP Server
    mcp_master_key: SecretStr
    mcp_server_host: str = "0.0.0.0"
    mcp_server_port: int = 8080

    # Redis Cache
    redis_url: SecretStr
    redis_key_prefix: str = "reddit_mcp:"

    # Monitoring
    sentry_dsn: Optional[SecretStr] = None
    log_level: str = "INFO"
    environment: str = "production"

    # Security
    cors_origins: list[str] = ["http://localhost:3000"]
    max_request_size: int = 1_000_000  # 1MB

    @validator("environment")
    def validate_environment(cls, v):
        allowed = ["development", "staging", "production"]
        if v not in allowed:
            raise ValueError(f"Environment must be one of {allowed}")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

        # Prevent secrets from appearing in repr()
        json_encoders = {
            SecretStr: lambda v: "***REDACTED***" if v else None
        }

# Global settings instance
settings = Settings()

# Validate on startup
def validate_secrets():
    """Ensure all required secrets are present."""
    required = [
        "reddit_client_id",
        "reddit_client_secret",
        "mcp_master_key",
        "redis_url"
    ]

    missing = [key for key in required if not getattr(settings, key)]
    if missing:
        raise ValueError(f"Missing required secrets: {missing}")
```

#### Secret Rotation Strategy

**Monthly Secret Rotation Plan:**

```python
# src/auth/rotation.py

from datetime import datetime, timedelta
from typing import Optional

class SecretRotationManager:
    """Manages secret rotation lifecycle."""

    def __init__(self, kv_store):
        self.kv_store = kv_store
        self.rotation_period = timedelta(days=90)  # 90 days

    async def check_rotation_needed(self, secret_name: str) -> bool:
        """Check if secret needs rotation."""
        metadata = await self.kv_store.get_value(f"secret_metadata:{secret_name}")
        if not metadata:
            return False

        last_rotated = datetime.fromisoformat(metadata["last_rotated"])
        return datetime.utcnow() - last_rotated > self.rotation_period

    async def rotate_api_keys(self) -> dict:
        """Rotate all API keys gracefully."""
        # Step 1: Generate new keys
        new_keys = await self._generate_new_keys()

        # Step 2: Dual-run period (both old and new valid for 7 days)
        await self._enable_dual_mode(new_keys)

        # Step 3: Notify users
        await self._notify_users_of_rotation()

        # Step 4: Schedule old key deactivation
        deactivation_date = datetime.utcnow() + timedelta(days=7)
        await self._schedule_deactivation(deactivation_date)

        return {
            "status": "rotation_initiated",
            "dual_mode_until": deactivation_date.isoformat(),
            "affected_users": len(new_keys)
        }

# Automated rotation check (runs daily)
async def rotation_check_task():
    """Background task to check for needed rotations."""
    manager = SecretRotationManager(kv_store)

    secrets_to_check = [
        "reddit_oauth_token",
        "mcp_master_key",
        "redis_password"
    ]

    for secret in secrets_to_check:
        if await manager.check_rotation_needed(secret):
            logger.warning(
                f"Secret rotation needed: {secret}",
                extra={"secret_name": secret}
            )
            # Trigger alert in monitoring system
```

---

### 1.3 Data Privacy & Compliance

#### GDPR Compliance

**Data Subject Rights Implementation:**

```python
# src/privacy/gdpr.py

from typing import Optional
from datetime import datetime, timedelta

class GDPRManager:
    """Handles GDPR compliance operations."""

    def __init__(self, kv_store, datasets):
        self.kv_store = kv_store
        self.datasets = datasets

    async def export_user_data(self, user_id: str) -> dict:
        """Export all data for a user (Right to Data Portability)."""
        return {
            "user_id": user_id,
            "exported_at": datetime.utcnow().isoformat(),
            "data": {
                "profile": await self._get_user_profile(user_id),
                "api_keys": await self._get_api_keys(user_id),
                "request_history": await self._get_request_history(user_id),
                "cached_data": await self._get_cached_data(user_id)
            }
        }

    async def delete_user_data(self, user_id: str) -> dict:
        """Delete all user data (Right to Erasure)."""
        deleted = {
            "profile": await self._delete_user_profile(user_id),
            "api_keys": await self._revoke_all_keys(user_id),
            "request_history": await self._delete_request_history(user_id),
            "cached_data": await self._delete_cached_data(user_id)
        }

        # Log deletion for audit trail (keep for 1 year)
        await self.kv_store.set_value(
            f"gdpr_deletion:{user_id}",
            {
                "deleted_at": datetime.utcnow().isoformat(),
                "items_deleted": deleted
            },
            expiration_ttl=31536000  # 1 year
        )

        return deleted

    async def anonymize_logs(self, user_id: str) -> int:
        """Anonymize user data in logs (Right to Erasure)."""
        # Replace user_id with anonymous identifier in logs
        anon_id = hashlib.sha256(f"{user_id}:salt".encode()).hexdigest()[:16]

        # This would integrate with your logging system
        # Example: Update Elasticsearch/CloudWatch logs
        count = await self._update_log_entries(user_id, anon_id)

        return count
```

#### Data Retention Policies

**Automatic Data Cleanup:**

```python
# src/privacy/retention.py

from datetime import datetime, timedelta

class RetentionPolicy:
    """Enforces data retention policies."""

    RETENTION_PERIODS = {
        "request_logs": timedelta(days=30),
        "error_logs": timedelta(days=90),
        "cached_reddit_data": timedelta(hours=24),
        "user_activity": timedelta(days=365),
        "audit_logs": timedelta(days=2555),  # 7 years (compliance)
    }

    def __init__(self, kv_store, datasets):
        self.kv_store = kv_store
        self.datasets = datasets

    async def cleanup_expired_data(self) -> dict:
        """Remove data past retention period."""
        now = datetime.utcnow()
        results = {}

        for data_type, retention_period in self.RETENTION_PERIODS.items():
            cutoff_date = now - retention_period
            deleted = await self._delete_before_date(data_type, cutoff_date)
            results[data_type] = deleted

        return results

    async def _delete_before_date(self, data_type: str, cutoff: datetime) -> int:
        """Delete records older than cutoff date."""
        # Implementation depends on storage backend
        if data_type == "cached_reddit_data":
            # Redis handles this with TTL automatically
            return 0

        # For Apify datasets
        query = f"created_at < '{cutoff.isoformat()}'"
        deleted_count = await self.datasets.delete_items(query)

        return deleted_count

# Daily cleanup task
async def retention_cleanup_task():
    """Background task for data cleanup."""
    policy = RetentionPolicy(kv_store, datasets)
    results = await policy.cleanup_expired_data()

    logger.info(
        "Data retention cleanup completed",
        extra={"deleted_counts": results}
    )
```

#### Logging Restrictions (No PII)

**PII-Safe Logging:**

```python
# src/logging/safe_logger.py

import logging
import re
from typing import Any
import json

class PIISafeLogger:
    """Logger that automatically redacts PII."""

    PII_PATTERNS = {
        "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        "reddit_username": re.compile(r'(?:^|/)u/([A-Za-z0-9_-]+)'),
        "api_key": re.compile(r'Bearer\s+([A-Za-z0-9_-]{20,})'),
        "token": re.compile(r'token["\']?\s*[:=]\s*["\']?([A-Za-z0-9_-]{20,})'),
        "password": re.compile(r'password["\']?\s*[:=]\s*["\']?([^\s"\']+)'),
    }

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def _redact_pii(self, message: str) -> str:
        """Redact PII from log messages."""
        for pii_type, pattern in self.PII_PATTERNS.items():
            message = pattern.sub(f"[REDACTED:{pii_type.upper()}]", message)
        return message

    def _redact_dict(self, data: dict) -> dict:
        """Recursively redact PII from dictionaries."""
        redacted = {}
        sensitive_keys = {"password", "token", "api_key", "secret", "authorization"}

        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                redacted[key] = "***REDACTED***"
            elif isinstance(value, dict):
                redacted[key] = self._redact_dict(value)
            elif isinstance(value, str):
                redacted[key] = self._redact_pii(value)
            else:
                redacted[key] = value

        return redacted

    def info(self, message: str, extra: dict = None):
        """Log info with PII redaction."""
        safe_message = self._redact_pii(message)
        safe_extra = self._redact_dict(extra) if extra else None
        self.logger.info(safe_message, extra=safe_extra)

    def error(self, message: str, exc_info: bool = False, extra: dict = None):
        """Log error with PII redaction."""
        safe_message = self._redact_pii(message)
        safe_extra = self._redact_dict(extra) if extra else None
        self.logger.error(safe_message, exc_info=exc_info, extra=safe_extra)

# Usage
logger = PIISafeLogger(__name__)
logger.info(
    "User request processed",
    extra={
        "user_id": user_id,  # Hash or UUID (not username)
        "tool": "search_reddit",
        "query": "AI trends",  # Safe to log
        "api_key": api_key  # Will be redacted
    }
)
```

---

### 1.4 Input Validation

#### Pydantic Models for All Inputs

**Comprehensive Validation Models:**

```python
# src/validation/models.py

from pydantic import BaseModel, Field, validator, constr
from typing import Optional, Literal
from datetime import datetime

class SearchRedditInput(BaseModel):
    """Validated input for search_reddit tool."""

    query: constr(min_length=1, max_length=500) = Field(
        ...,
        description="Search query or keywords",
        example="artificial intelligence"
    )

    subreddit: Optional[constr(regex=r'^[A-Za-z0-9_]+$', max_length=21)] = Field(
        None,
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
        description="Maximum number of results"
    )

    @validator("query")
    def sanitize_query(cls, v):
        """Sanitize query for SQL injection and XSS."""
        # Remove potentially dangerous characters
        dangerous = ["<", ">", "'", '"', ";", "--", "/*", "*/"]
        for char in dangerous:
            if char in v:
                raise ValueError(f"Query contains forbidden character: {char}")

        # Trim whitespace
        v = v.strip()

        if not v:
            raise ValueError("Query cannot be empty after sanitization")

        return v

    @validator("subreddit")
    def validate_subreddit(cls, v):
        """Validate subreddit name format."""
        if v is None:
            return v

        # Reddit subreddit rules
        if len(v) < 3:
            raise ValueError("Subreddit name must be at least 3 characters")

        if v.startswith("_") or v.endswith("_"):
            raise ValueError("Subreddit name cannot start or end with underscore")

        return v

class GetPostCommentsInput(BaseModel):
    """Validated input for get_post_comments tool."""

    post_id: constr(regex=r'^(t3_)?[a-z0-9]{5,7}$') = Field(
        ...,
        description="Reddit post ID (with or without t3_ prefix)",
        example="t3_abc123"
    )

    sort: Literal["best", "top", "new", "controversial", "old"] = Field(
        "best",
        description="Comment sort order"
    )

    max_depth: int = Field(
        0,
        ge=0,
        le=10,
        description="Maximum comment nesting depth (0 = unlimited)"
    )

    @validator("post_id")
    def normalize_post_id(cls, v):
        """Ensure post_id has t3_ prefix."""
        if not v.startswith("t3_"):
            return f"t3_{v}"
        return v

class WatchKeywordsInput(BaseModel):
    """Validated input for watch_keywords tool."""

    keywords: list[constr(min_length=1, max_length=100)] = Field(
        ...,
        description="Keywords to monitor",
        min_items=1,
        max_items=10
    )

    subreddits: Optional[list[constr(regex=r'^[A-Za-z0-9_]+$')]] = Field(
        None,
        description="Subreddits to monitor (all if empty)",
        max_items=20
    )

    alert_threshold: Literal["any", "high_engagement", "viral"] = Field(
        "high_engagement",
        description="When to trigger alerts"
    )

    check_interval: int = Field(
        15,
        ge=5,
        le=1440,
        description="Minutes between checks"
    )

    @validator("keywords")
    def validate_keywords(cls, v):
        """Validate and sanitize keywords."""
        sanitized = []
        for keyword in v:
            # Remove special regex characters
            clean = re.sub(r'[^\w\s-]', '', keyword)
            if clean:
                sanitized.append(clean.lower())

        if not sanitized:
            raise ValueError("No valid keywords after sanitization")

        # Remove duplicates
        return list(set(sanitized))

# Validation middleware
async def validate_input(tool_name: str, raw_input: dict) -> BaseModel:
    """Validate input based on tool name."""
    validation_map = {
        "search_reddit": SearchRedditInput,
        "get_post_comments": GetPostCommentsInput,
        "watch_keywords": WatchKeywordsInput,
        # ... add all tools
    }

    validator_class = validation_map.get(tool_name)
    if not validator_class:
        raise ValueError(f"No validator for tool: {tool_name}")

    try:
        return validator_class(**raw_input)
    except ValidationError as e:
        # Transform Pydantic error to MCP error format
        raise MCPValidationError(
            code=-32602,
            message="Invalid parameters",
            data={"errors": e.errors()}
        )
```

#### Length Limits & Pattern Validation

**Security Limits Configuration:**

```python
# src/validation/limits.py

from dataclasses import dataclass

@dataclass
class SecurityLimits:
    """Security limits for inputs."""

    # String lengths
    MAX_QUERY_LENGTH: int = 500
    MAX_SUBREDDIT_NAME: int = 21  # Reddit's limit
    MAX_USERNAME_LENGTH: int = 20  # Reddit's limit
    MAX_POST_ID_LENGTH: int = 10
    MAX_KEYWORDS_PER_WATCH: int = 10
    MAX_SUBREDDITS_PER_WATCH: int = 20

    # Array sizes
    MAX_SEARCH_RESULTS: int = 100
    MAX_COMMENTS_DEPTH: int = 10
    MAX_BATCH_REQUESTS: int = 5

    # Rate limits
    MAX_REQUESTS_PER_MINUTE: int = 10  # Free tier
    MAX_REQUESTS_PER_HOUR: int = 300

    # Payload sizes
    MAX_REQUEST_BODY_SIZE: int = 1_000_000  # 1MB
    MAX_CACHE_VALUE_SIZE: int = 10_000_000  # 10MB

    # Timeouts
    REQUEST_TIMEOUT_SECONDS: int = 30
    CACHE_TTL_MAX: int = 86400  # 24 hours

LIMITS = SecurityLimits()

# Validation decorator
def enforce_limits(func):
    """Decorator to enforce security limits."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Check request size
        request_size = len(json.dumps(kwargs).encode())
        if request_size > LIMITS.MAX_REQUEST_BODY_SIZE:
            raise RequestTooLargeError(
                f"Request body exceeds {LIMITS.MAX_REQUEST_BODY_SIZE} bytes"
            )

        return await func(*args, **kwargs)

    return wrapper
```

---

## 2. Error Handling Architecture

### 2.1 Error Classification

**Hierarchical Error System:**

```python
# src/errors/exceptions.py

from enum import Enum
from typing import Optional, Any

class ErrorCategory(Enum):
    """Error categories for classification."""
    CLIENT_ERROR = "client_error"  # 4xx
    SERVER_ERROR = "server_error"  # 5xx
    RATE_LIMIT = "rate_limit"  # 429
    EXTERNAL_API = "external_api"  # Reddit API issues
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    TIMEOUT = "timeout"

class MCPError(Exception):
    """Base exception for all MCP errors."""

    def __init__(
        self,
        code: int,
        message: str,
        category: ErrorCategory,
        data: Optional[dict] = None,
        retry_after: Optional[int] = None
    ):
        self.code = code
        self.message = message
        self.category = category
        self.data = data or {}
        self.retry_after = retry_after
        super().__init__(message)

    def to_json_rpc(self) -> dict:
        """Convert to JSON-RPC 2.0 error format."""
        error = {
            "code": self.code,
            "message": self.message,
            "data": {
                "category": self.category.value,
                **self.data
            }
        }

        if self.retry_after:
            error["data"]["retry_after_seconds"] = self.retry_after

        return {"error": error}

# Client Errors (4xx)
class ValidationError(MCPError):
    """Invalid input parameters."""
    def __init__(self, message: str, field: str = None, **kwargs):
        data = {"field": field} if field else {}
        data.update(kwargs)
        super().__init__(
            code=-32602,  # Invalid params
            message=message,
            category=ErrorCategory.VALIDATION,
            data=data
        )

class AuthenticationError(MCPError):
    """Authentication failed."""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            code=-32001,  # Custom: Unauthorized
            message=message,
            category=ErrorCategory.AUTHENTICATION
        )

class AuthorizationError(MCPError):
    """Insufficient permissions."""
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            code=-32002,  # Custom: Forbidden
            message=message,
            category=ErrorCategory.AUTHENTICATION
        )

class NotFoundError(MCPError):
    """Resource not found."""
    def __init__(self, resource: str):
        super().__init__(
            code=-32003,  # Custom: Not Found
            message=f"{resource} not found",
            category=ErrorCategory.CLIENT_ERROR,
            data={"resource": resource}
        )

# Rate Limit Errors
class RateLimitError(MCPError):
    """Rate limit exceeded."""
    def __init__(self, retry_after: int, limit_type: str = "user"):
        super().__init__(
            code=-32004,  # Custom: Rate Limited
            message=f"Rate limit exceeded. Please retry after {retry_after} seconds",
            category=ErrorCategory.RATE_LIMIT,
            retry_after=retry_after,
            data={"limit_type": limit_type}
        )

class RedditRateLimitError(RateLimitError):
    """Reddit API rate limit."""
    def __init__(self, retry_after: int):
        super().__init__(
            retry_after=retry_after,
            limit_type="reddit_api"
        )
        self.message = f"Reddit API rate limit reached. Request queued, estimated wait: {retry_after}s"

# Server Errors (5xx)
class InternalServerError(MCPError):
    """Unexpected server error."""
    def __init__(self, message: str = "Internal server error", trace_id: str = None):
        super().__init__(
            code=-32603,  # Internal error
            message=message,
            category=ErrorCategory.SERVER_ERROR,
            data={"trace_id": trace_id} if trace_id else {}
        )

class ServiceUnavailableError(MCPError):
    """Service temporarily unavailable."""
    def __init__(self, service: str, retry_after: int = 60):
        super().__init__(
            code=-32005,  # Custom: Service Unavailable
            message=f"{service} is temporarily unavailable",
            category=ErrorCategory.SERVER_ERROR,
            retry_after=retry_after,
            data={"service": service}
        )

# External Errors
class RedditAPIError(MCPError):
    """Reddit API returned an error."""
    def __init__(self, status_code: int, message: str):
        super().__init__(
            code=-32006,  # Custom: External API Error
            message=f"Reddit API error: {message}",
            category=ErrorCategory.EXTERNAL_API,
            data={
                "status_code": status_code,
                "upstream_service": "reddit"
            }
        )

class TimeoutError(MCPError):
    """Request timeout."""
    def __init__(self, operation: str, timeout_seconds: int):
        super().__init__(
            code=-32007,  # Custom: Timeout
            message=f"Operation '{operation}' timed out after {timeout_seconds}s",
            category=ErrorCategory.TIMEOUT,
            data={"operation": operation, "timeout": timeout_seconds}
        )
```

### 2.2 Error Response Format

**Standardized MCP Error Responses:**

```python
# src/errors/formatter.py

from typing import Optional
import traceback
import uuid

class ErrorResponseFormatter:
    """Formats errors for MCP responses."""

    def __init__(self, environment: str):
        self.environment = environment
        self.include_traces = environment == "development"

    def format_error(
        self,
        error: Exception,
        request_id: str = None
    ) -> dict:
        """Format error for JSON-RPC 2.0 response."""

        # Generate trace ID for error tracking
        trace_id = request_id or str(uuid.uuid4())

        # Handle known MCP errors
        if isinstance(error, MCPError):
            response = error.to_json_rpc()
            response["error"]["data"]["trace_id"] = trace_id

            if self.include_traces:
                response["error"]["data"]["stack_trace"] = traceback.format_exc()

            return response

        # Handle unexpected errors
        return {
            "error": {
                "code": -32603,
                "message": self._get_safe_message(error),
                "data": {
                    "category": "server_error",
                    "trace_id": trace_id,
                    "error_type": type(error).__name__,
                    **({"stack_trace": traceback.format_exc()} if self.include_traces else {})
                }
            }
        }

    def _get_safe_message(self, error: Exception) -> str:
        """Get user-safe error message."""
        if self.environment == "production":
            return "An unexpected error occurred. Please contact support with trace ID."
        return str(error)

# Global error handler
async def handle_error(
    error: Exception,
    request_id: str,
    logger: PIISafeLogger
) -> dict:
    """Global error handling pipeline."""

    formatter = ErrorResponseFormatter(settings.environment)
    response = formatter.format_error(error, request_id)

    # Log error with appropriate severity
    log_level = "error" if isinstance(error, MCPError) else "critical"

    logger_method = getattr(logger, log_level)
    logger_method(
        f"Error in request {request_id}",
        exc_info=True,
        extra={
            "trace_id": request_id,
            "error_code": response["error"]["code"],
            "error_category": response["error"]["data"].get("category")
        }
    )

    # Send to error tracking (Sentry)
    if settings.sentry_dsn:
        sentry_sdk.capture_exception(error)

    return response
```

### 2.3 Retry Strategy

**Exponential Backoff with Jitter:**

```python
# src/retry/backoff.py

import asyncio
import random
from typing import Callable, TypeVar, Optional
from functools import wraps

T = TypeVar('T')

class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for attempt with exponential backoff and jitter."""
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay
        )

        if self.jitter:
            # Add random jitter (±25%)
            jitter_range = delay * 0.25
            delay += random.uniform(-jitter_range, jitter_range)

        return max(0, delay)

class RetryStrategy:
    """Intelligent retry strategy with circuit breaker."""

    # Different retry configs for different error types
    RETRY_CONFIGS = {
        ErrorCategory.RATE_LIMIT: RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=300.0
        ),
        ErrorCategory.EXTERNAL_API: RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            max_delay=30.0
        ),
        ErrorCategory.TIMEOUT: RetryConfig(
            max_attempts=2,
            base_delay=0.5,
            max_delay=10.0
        ),
    }

    # Don't retry these error types
    NO_RETRY_CATEGORIES = {
        ErrorCategory.CLIENT_ERROR,
        ErrorCategory.VALIDATION,
        ErrorCategory.AUTHENTICATION
    }

    def __init__(self, logger: PIISafeLogger):
        self.logger = logger

    async def execute_with_retry(
        self,
        func: Callable[..., T],
        *args,
        operation_name: str = None,
        **kwargs
    ) -> T:
        """Execute function with retry logic."""

        operation_name = operation_name or func.__name__
        attempt = 0

        while True:
            try:
                result = await func(*args, **kwargs)

                if attempt > 0:
                    self.logger.info(
                        f"Operation '{operation_name}' succeeded after {attempt} retries"
                    )

                return result

            except MCPError as error:
                # Check if error is retryable
                if error.category in self.NO_RETRY_CATEGORIES:
                    self.logger.info(
                        f"Non-retryable error in '{operation_name}': {error.message}"
                    )
                    raise

                # Get retry config for this error type
                config = self.RETRY_CONFIGS.get(
                    error.category,
                    RetryConfig()  # Default config
                )

                attempt += 1

                if attempt >= config.max_attempts:
                    self.logger.error(
                        f"Operation '{operation_name}' failed after {attempt} attempts",
                        extra={"error": str(error)}
                    )
                    raise

                # Calculate delay
                if error.retry_after:
                    delay = error.retry_after
                else:
                    delay = config.calculate_delay(attempt)

                self.logger.warning(
                    f"Retrying '{operation_name}' after {delay:.2f}s (attempt {attempt}/{config.max_attempts})",
                    extra={"error_category": error.category.value}
                )

                await asyncio.sleep(delay)

            except Exception as error:
                # Unexpected error - retry once
                if attempt > 0:
                    self.logger.error(
                        f"Unexpected error in '{operation_name}' after retry",
                        exc_info=True
                    )
                    raise

                attempt += 1
                delay = 1.0

                self.logger.warning(
                    f"Unexpected error in '{operation_name}', retrying after {delay}s",
                    exc_info=True
                )

                await asyncio.sleep(delay)

# Decorator for easy retry
def with_retry(
    operation_name: str = None,
    max_attempts: int = 3
):
    """Decorator to add retry logic to async functions."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            strategy = RetryStrategy(logger)
            return await strategy.execute_with_retry(
                func,
                *args,
                operation_name=operation_name or func.__name__,
                **kwargs
            )
        return wrapper
    return decorator

# Usage example
@with_retry(operation_name="fetch_reddit_posts", max_attempts=3)
async def fetch_posts_from_reddit(subreddit: str):
    """Fetch posts with automatic retry."""
    async with reddit_client.get(f"/r/{subreddit}/hot.json") as response:
        if response.status == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            raise RedditRateLimitError(retry_after)

        response.raise_for_status()
        return await response.json()
```

### 2.4 Circuit Breaker Pattern

**Fault Isolation:**

```python
# src/resilience/circuit_breaker.py

from enum import Enum
from datetime import datetime, timedelta
from typing import Callable, TypeVar
from collections import deque

T = TypeVar('T')

class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered

class CircuitBreaker:
    """Circuit breaker for external service calls."""

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_requests: int = 3,
        success_threshold: int = 2
    ):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = timedelta(seconds=recovery_timeout)
        self.half_open_requests = half_open_requests
        self.success_threshold = success_threshold

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_attempts = 0

        # Track recent errors for monitoring
        self.recent_errors = deque(maxlen=100)

    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection."""

        # Check circuit state
        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if datetime.utcnow() - self.last_failure_time > self.recovery_timeout:
                logger.info(f"Circuit breaker for {self.service_name}: OPEN -> HALF_OPEN")
                self.state = CircuitState.HALF_OPEN
                self.half_open_attempts = 0
            else:
                raise ServiceUnavailableError(
                    service=self.service_name,
                    retry_after=int(self.recovery_timeout.total_seconds())
                )

        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_attempts >= self.half_open_requests:
                raise ServiceUnavailableError(
                    service=self.service_name,
                    retry_after=30
                )
            self.half_open_attempts += 1

        # Execute the function
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result

        except Exception as error:
            self._on_failure(error)
            raise

    def _on_success(self):
        """Handle successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1

            if self.success_count >= self.success_threshold:
                logger.info(f"Circuit breaker for {self.service_name}: HALF_OPEN -> CLOSED")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0

        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = max(0, self.failure_count - 1)

    def _on_failure(self, error: Exception):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        self.recent_errors.append({
            "timestamp": self.last_failure_time.isoformat(),
            "error": str(error)
        })

        if self.state == CircuitState.HALF_OPEN:
            logger.warning(f"Circuit breaker for {self.service_name}: HALF_OPEN -> OPEN")
            self.state = CircuitState.OPEN
            self.success_count = 0

        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                logger.error(
                    f"Circuit breaker for {self.service_name}: CLOSED -> OPEN "
                    f"({self.failure_count} failures)"
                )
                self.state = CircuitState.OPEN

    def get_status(self) -> dict:
        """Get current circuit breaker status."""
        return {
            "service": self.service_name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "recent_errors": list(self.recent_errors)
        }

# Global circuit breakers
class CircuitBreakerManager:
    """Manages circuit breakers for all services."""

    def __init__(self):
        self.breakers: dict[str, CircuitBreaker] = {}

    def get_breaker(self, service_name: str) -> CircuitBreaker:
        """Get or create circuit breaker for service."""
        if service_name not in self.breakers:
            self.breakers[service_name] = CircuitBreaker(service_name)
        return self.breakers[service_name]

    def get_all_status(self) -> dict:
        """Get status of all circuit breakers."""
        return {
            name: breaker.get_status()
            for name, breaker in self.breakers.items()
        }

# Global instance
circuit_breakers = CircuitBreakerManager()

# Usage decorator
def with_circuit_breaker(service_name: str):
    """Decorator to add circuit breaker protection."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            breaker = circuit_breakers.get_breaker(service_name)
            return await breaker.call(func, *args, **kwargs)
        return wrapper
    return decorator

# Example usage
@with_circuit_breaker("reddit_api")
async def fetch_from_reddit(endpoint: str):
    """Fetch data from Reddit with circuit breaker."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://oauth.reddit.com{endpoint}")
        response.raise_for_status()
        return response.json()
```

---

## 3. Rate Limit Management

### 3.1 Token Bucket Algorithm

**Efficient Rate Limiting:**

```python
# src/ratelimit/token_bucket.py

import asyncio
from datetime import datetime, timedelta
from typing import Optional
import time

class TokenBucket:
    """Token bucket algorithm for rate limiting."""

    def __init__(
        self,
        capacity: int,
        refill_rate: float,
        initial_tokens: Optional[int] = None
    ):
        """
        Initialize token bucket.

        Args:
            capacity: Maximum number of tokens
            refill_rate: Tokens added per second
            initial_tokens: Starting tokens (defaults to capacity)
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = initial_tokens if initial_tokens is not None else capacity
        self.last_refill = time.monotonic()
        self.lock = asyncio.Lock()

    async def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens from bucket.

        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        async with self.lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            return False

    async def wait_for_token(self, tokens: int = 1) -> float:
        """
        Wait until tokens are available.

        Returns:
            Wait time in seconds (0 if immediate)
        """
        async with self.lock:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0

            # Calculate wait time
            tokens_needed = tokens - self.tokens
            wait_seconds = tokens_needed / self.refill_rate

            # Wait and refill
            await asyncio.sleep(wait_seconds)
            self._refill()
            self.tokens -= tokens

            return wait_seconds

    def _refill(self):
        """Refill tokens based on time elapsed."""
        now = time.monotonic()
        elapsed = now - self.last_refill

        # Calculate new tokens
        new_tokens = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill = now

    def get_status(self) -> dict:
        """Get current bucket status."""
        return {
            "tokens_available": int(self.tokens),
            "capacity": self.capacity,
            "refill_rate": self.refill_rate,
            "utilization": 1 - (self.tokens / self.capacity)
        }

class HierarchicalRateLimiter:
    """Rate limiter with multiple tiers (user, app, Reddit API)."""

    def __init__(self):
        # Reddit API limit: 100 requests per minute
        self.reddit_bucket = TokenBucket(
            capacity=100,
            refill_rate=100/60  # 1.67 per second
        )

        # Per-user limits stored in Redis
        self.user_buckets: dict[str, TokenBucket] = {}

    def get_user_bucket(self, user_id: str, tier: str) -> TokenBucket:
        """Get or create token bucket for user."""
        key = f"{user_id}:{tier}"

        if key not in self.user_buckets:
            # Free tier: 10 per minute, Paid: 50 per minute
            limits = {
                "free": (10, 10/60),
                "paid": (50, 50/60)
            }
            capacity, rate = limits.get(tier, limits["free"])

            self.user_buckets[key] = TokenBucket(capacity, rate)

        return self.user_buckets[key]

    async def check_limits(self, user_id: str, tier: str) -> dict:
        """Check all rate limits for request."""
        user_bucket = self.get_user_bucket(user_id, tier)

        # Check user limit first (faster fail)
        user_ok = await user_bucket.consume()
        if not user_ok:
            return {
                "allowed": False,
                "limited_by": "user_quota",
                "retry_after": await self._calculate_retry_time(user_bucket)
            }

        # Check Reddit API limit
        reddit_ok = await self.reddit_bucket.consume()
        if not reddit_ok:
            # Refund user token
            async with user_bucket.lock:
                user_bucket.tokens += 1

            return {
                "allowed": False,
                "limited_by": "reddit_api",
                "retry_after": await self._calculate_retry_time(self.reddit_bucket)
            }

        return {
            "allowed": True,
            "user_tokens_remaining": int(user_bucket.tokens),
            "reddit_tokens_remaining": int(self.reddit_bucket.tokens)
        }

    async def _calculate_retry_time(self, bucket: TokenBucket) -> int:
        """Calculate seconds until token available."""
        if bucket.tokens >= 1:
            return 0

        tokens_needed = 1 - bucket.tokens
        return int(tokens_needed / bucket.refill_rate) + 1

    def get_global_status(self) -> dict:
        """Get status of all rate limiters."""
        return {
            "reddit_api": self.reddit_bucket.get_status(),
            "active_users": len(self.user_buckets)
        }

# Global rate limiter
rate_limiter = HierarchicalRateLimiter()

# Middleware for rate limiting
async def rate_limit_middleware(user_id: str, tier: str):
    """Middleware to enforce rate limits."""
    result = await rate_limiter.check_limits(user_id, tier)

    if not result["allowed"]:
        raise RateLimitError(
            retry_after=result["retry_after"],
            limit_type=result["limited_by"]
        )

    return result
```

### 3.2 Request Queuing

**Priority Queue System:**

```python
# src/queue/priority_queue.py

import asyncio
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Optional, Callable, Any
from datetime import datetime
import uuid

class Priority(IntEnum):
    """Request priority levels."""
    CRITICAL = 0  # Alerts, health checks
    HIGH = 1      # User-facing real-time queries
    NORMAL = 2    # Standard user requests
    LOW = 3       # Background jobs, analytics

@dataclass(order=True)
class QueuedRequest:
    """Request in the queue."""
    priority: Priority = field(compare=True)
    timestamp: datetime = field(compare=True)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()), compare=False)
    user_id: str = field(compare=False)
    tool_name: str = field(compare=False)
    args: dict = field(default_factory=dict, compare=False)
    callback: Optional[Callable] = field(default=None, compare=False)

class RequestQueue:
    """Priority queue for Reddit API requests."""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.queue = asyncio.PriorityQueue(maxsize=max_size)
        self.processing = {}  # request_id -> task
        self.results = {}     # request_id -> result
        self.worker_task: Optional[asyncio.Task] = None

    async def start_worker(self):
        """Start background worker to process queue."""
        if self.worker_task and not self.worker_task.done():
            return

        self.worker_task = asyncio.create_task(self._process_queue())
        logger.info("Request queue worker started")

    async def stop_worker(self):
        """Stop the background worker."""
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Request queue worker stopped")

    async def enqueue(
        self,
        user_id: str,
        tool_name: str,
        args: dict,
        priority: Priority = Priority.NORMAL
    ) -> str:
        """Add request to queue."""

        if self.queue.full():
            raise ServiceUnavailableError(
                service="request_queue",
                retry_after=30
            )

        request = QueuedRequest(
            priority=priority,
            timestamp=datetime.utcnow(),
            user_id=user_id,
            tool_name=tool_name,
            args=args
        )

        await self.queue.put(request)

        logger.info(
            f"Request queued: {request.request_id}",
            extra={
                "user_id": user_id,
                "tool": tool_name,
                "priority": priority.name,
                "queue_size": self.queue.qsize()
            }
        )

        return request.request_id

    async def get_result(
        self,
        request_id: str,
        timeout: int = 300
    ) -> Any:
        """Wait for and retrieve request result."""

        start_time = datetime.utcnow()

        while True:
            # Check if result is ready
            if request_id in self.results:
                result = self.results.pop(request_id)

                if isinstance(result, Exception):
                    raise result

                return result

            # Check timeout
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            if elapsed > timeout:
                raise TimeoutError(
                    operation="queue_wait",
                    timeout_seconds=timeout
                )

            # Wait a bit
            await asyncio.sleep(0.1)

    async def get_status(self, request_id: str) -> dict:
        """Get status of queued request."""

        if request_id in self.results:
            return {
                "status": "completed",
                "request_id": request_id
            }

        if request_id in self.processing:
            return {
                "status": "processing",
                "request_id": request_id
            }

        # Check if still in queue (linear search - could be optimized)
        position = 0
        for item in list(self.queue._queue):
            position += 1
            if item.request_id == request_id:
                estimated_wait = position * 2  # ~2s per request
                return {
                    "status": "queued",
                    "request_id": request_id,
                    "position": position,
                    "estimated_wait_seconds": estimated_wait
                }

        return {
            "status": "not_found",
            "request_id": request_id
        }

    async def _process_queue(self):
        """Background worker to process queued requests."""

        while True:
            try:
                # Get next request
                request = await self.queue.get()

                # Mark as processing
                self.processing[request.request_id] = asyncio.current_task()

                logger.info(
                    f"Processing request: {request.request_id}",
                    extra={
                        "tool": request.tool_name,
                        "queue_size": self.queue.qsize()
                    }
                )

                # Wait for rate limit
                await rate_limiter.reddit_bucket.wait_for_token()

                # Execute the request
                try:
                    # Import and execute tool
                    tool = get_tool(request.tool_name)
                    result = await tool.execute(**request.args)

                    self.results[request.request_id] = result

                except Exception as error:
                    self.results[request.request_id] = error
                    logger.error(
                        f"Request failed: {request.request_id}",
                        exc_info=True
                    )

                finally:
                    # Clean up
                    self.processing.pop(request.request_id, None)
                    self.queue.task_done()

            except asyncio.CancelledError:
                logger.info("Queue processor cancelled")
                break

            except Exception as error:
                logger.error("Queue processor error", exc_info=True)
                await asyncio.sleep(1)  # Prevent tight loop on error

# Global queue
request_queue = RequestQueue()

# Queue management decorator
def queue_if_rate_limited(priority: Priority = Priority.NORMAL):
    """Decorator to automatically queue requests when rate limited."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(user_id: str, *args, **kwargs):
            try:
                # Try direct execution
                return await func(user_id, *args, **kwargs)

            except RateLimitError as error:
                # Queue the request
                logger.info(
                    f"Rate limited, queueing request",
                    extra={"user_id": user_id}
                )

                request_id = await request_queue.enqueue(
                    user_id=user_id,
                    tool_name=func.__name__,
                    args=kwargs,
                    priority=priority
                )

                # Return status
                return {
                    "status": "queued",
                    "request_id": request_id,
                    "message": f"Request queued due to rate limit. Retry after {error.retry_after}s",
                    "check_status_url": f"/api/queue/status/{request_id}"
                }

        return wrapper
    return decorator
```

### 3.3 Graceful Degradation

**Serving Stale Cache During Rate Limits:**

```python
# src/cache/graceful_degradation.py

from typing import Optional, Any
from datetime import datetime, timedelta

class GracefulCacheManager:
    """Cache manager with graceful degradation."""

    def __init__(self, redis_client):
        self.redis = redis_client

    async def get_with_fallback(
        self,
        key: str,
        max_stale_age: timedelta = timedelta(hours=24)
    ) -> Optional[dict]:
        """Get cached value, allowing stale data during outages."""

        # Try to get fresh cache
        cached = await self.redis.get(key)

        if cached:
            data = json.loads(cached)
            cached_at = datetime.fromisoformat(data["cached_at"])
            age = datetime.utcnow() - cached_at

            return {
                "data": data["value"],
                "cached_at": data["cached_at"],
                "age_seconds": int(age.total_seconds()),
                "is_stale": False
            }

        # No fresh cache, try stale cache
        stale_key = f"{key}:stale"
        stale_cached = await self.redis.get(stale_key)

        if stale_cached:
            data = json.loads(stale_cached)
            cached_at = datetime.fromisoformat(data["cached_at"])
            age = datetime.utcnow() - cached_at

            # Check if stale data is too old
            if age > max_stale_age:
                return None

            logger.warning(
                f"Serving stale cache for {key}",
                extra={"age_hours": age.total_seconds() / 3600}
            )

            return {
                "data": data["value"],
                "cached_at": data["cached_at"],
                "age_seconds": int(age.total_seconds()),
                "is_stale": True
            }

        return None

    async def set_with_stale_backup(
        self,
        key: str,
        value: Any,
        ttl: int,
        stale_ttl: int = 86400  # 24 hours
    ):
        """Set cache with long-lived stale backup."""

        cache_data = {
            "value": value,
            "cached_at": datetime.utcnow().isoformat()
        }

        # Set fresh cache
        await self.redis.setex(
            key,
            ttl,
            json.dumps(cache_data)
        )

        # Set stale backup (longer TTL)
        await self.redis.setex(
            f"{key}:stale",
            stale_ttl,
            json.dumps(cache_data)
        )

# Graceful degradation wrapper
async def fetch_with_degradation(
    cache_key: str,
    fetch_func: Callable,
    cache_ttl: int = 300
):
    """Fetch data with graceful degradation."""

    cache_manager = GracefulCacheManager(redis_client)

    try:
        # Try to fetch fresh data
        data = await fetch_func()

        # Cache it
        await cache_manager.set_with_stale_backup(
            cache_key,
            data,
            ttl=cache_ttl
        )

        return {
            "data": data,
            "from_cache": False,
            "is_stale": False
        }

    except RateLimitError:
        # Try to serve from cache
        cached = await cache_manager.get_with_fallback(cache_key)

        if cached:
            return cached

        # No cache available, queue request
        raise

    except RedditAPIError:
        # Reddit is down, serve stale cache
        cached = await cache_manager.get_with_fallback(
            cache_key,
            max_stale_age=timedelta(hours=48)  # More lenient during outages
        )

        if cached:
            return cached

        raise ServiceUnavailableError(
            service="reddit_api",
            retry_after=300
        )
```

---

## 4. Monitoring & Observability

### 4.1 Metrics Collection

**Comprehensive Metrics Tracking:**

```python
# src/monitoring/metrics.py

from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional
import time

@dataclass
class Metrics:
    """Metrics snapshot."""
    timestamp: datetime
    request_count: int
    error_count: int
    cache_hits: int
    cache_misses: int
    latency_p50: float
    latency_p95: float
    latency_p99: float
    rate_limit_hits: int
    active_users: int

class MetricsCollector:
    """Collects and aggregates metrics."""

    def __init__(self):
        self.requests_by_tool = defaultdict(int)
        self.errors_by_type = defaultdict(int)
        self.cache_stats = {"hits": 0, "misses": 0}
        self.latencies = []  # Rolling window
        self.rate_limit_hits = 0
        self.active_users = set()

        # Time series data (last 24 hours)
        self.time_series = []
        self.window_size = 300  # 5 minutes

    def record_request(
        self,
        user_id: str,
        tool_name: str,
        latency_ms: float,
        cached: bool,
        error: Optional[str] = None
    ):
        """Record request metrics."""

        # Count requests
        self.requests_by_tool[tool_name] += 1
        self.active_users.add(user_id)

        # Record latency
        self.latencies.append(latency_ms)

        # Keep only recent latencies (last 1000)
        if len(self.latencies) > 1000:
            self.latencies = self.latencies[-1000:]

        # Cache stats
        if cached:
            self.cache_stats["hits"] += 1
        else:
            self.cache_stats["misses"] += 1

        # Error tracking
        if error:
            self.errors_by_type[error] += 1

    def record_rate_limit(self):
        """Record rate limit hit."""
        self.rate_limit_hits += 1

    def get_snapshot(self) -> Metrics:
        """Get current metrics snapshot."""

        # Calculate percentiles
        if self.latencies:
            sorted_latencies = sorted(self.latencies)
            p50 = sorted_latencies[len(sorted_latencies) // 2]
            p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
            p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        else:
            p50 = p95 = p99 = 0.0

        total_requests = sum(self.requests_by_tool.values())
        total_errors = sum(self.errors_by_type.values())

        return Metrics(
            timestamp=datetime.utcnow(),
            request_count=total_requests,
            error_count=total_errors,
            cache_hits=self.cache_stats["hits"],
            cache_misses=self.cache_stats["misses"],
            latency_p50=p50,
            latency_p95=p95,
            latency_p99=p99,
            rate_limit_hits=self.rate_limit_hits,
            active_users=len(self.active_users)
        )

    def get_detailed_stats(self) -> dict:
        """Get detailed statistics."""

        snapshot = self.get_snapshot()

        # Calculate cache hit rate
        total_cache_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        cache_hit_rate = (
            self.cache_stats["hits"] / total_cache_requests
            if total_cache_requests > 0
            else 0.0
        )

        # Error rate
        error_rate = (
            snapshot.error_count / snapshot.request_count
            if snapshot.request_count > 0
            else 0.0
        )

        return {
            "overview": {
                "total_requests": snapshot.request_count,
                "error_count": snapshot.error_count,
                "error_rate": error_rate,
                "active_users": snapshot.active_users,
                "rate_limit_hits": snapshot.rate_limit_hits
            },
            "latency": {
                "p50_ms": snapshot.latency_p50,
                "p95_ms": snapshot.latency_p95,
                "p99_ms": snapshot.latency_p99
            },
            "cache": {
                "hits": self.cache_stats["hits"],
                "misses": self.cache_stats["misses"],
                "hit_rate": cache_hit_rate
            },
            "requests_by_tool": dict(self.requests_by_tool),
            "errors_by_type": dict(self.errors_by_type)
        }

    def reset_window(self):
        """Reset metrics for new time window."""
        # Save snapshot to time series
        self.time_series.append(self.get_snapshot())

        # Keep only last 24 hours
        cutoff = datetime.utcnow() - timedelta(hours=24)
        self.time_series = [
            m for m in self.time_series
            if m.timestamp > cutoff
        ]

        # Reset counters
        self.requests_by_tool.clear()
        self.errors_by_type.clear()
        self.cache_stats = {"hits": 0, "misses": 0}
        self.latencies.clear()
        self.rate_limit_hits = 0
        self.active_users.clear()

# Global metrics collector
metrics_collector = MetricsCollector()

# Metrics collection decorator
def track_metrics(tool_name: str):
    """Decorator to automatically track metrics."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(user_id: str, *args, **kwargs):
            start_time = time.time()
            error = None
            cached = False

            try:
                result = await func(user_id, *args, **kwargs)

                # Check if result was cached
                if isinstance(result, dict):
                    cached = result.get("metadata", {}).get("cached", False)

                return result

            except MCPError as e:
                error = e.category.value
                raise

            finally:
                # Record metrics
                latency_ms = (time.time() - start_time) * 1000

                metrics_collector.record_request(
                    user_id=user_id,
                    tool_name=tool_name,
                    latency_ms=latency_ms,
                    cached=cached,
                    error=error
                )

        return wrapper
    return decorator
```

### 4.2 Structured Logging

**JSON Logging with Context:**

```python
# src/logging/structured_logger.py

import logging
import json
from datetime import datetime
from typing import Any, Optional
import traceback
import sys

class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""

        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "environment": settings.environment
        }

        # Add exception info
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }

        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)

        return json.dumps(log_data)

def setup_logging():
    """Configure structured logging."""

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(console_handler)

    # File handler for production
    if settings.environment == "production":
        file_handler = logging.FileHandler("/var/log/reddit-mcp/app.log")
        file_handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(file_handler)

# Usage example
logger = PIISafeLogger(__name__)

logger.info(
    "Tool execution started",
    extra={
        "event": "tool_execution_start",
        "tool": "search_reddit",
        "user_id": user_id,
        "request_id": request_id,
        "query": query
    }
)
```

### 4.3 Alerting Rules

**Automated Alert System:**

```python
# src/monitoring/alerts.py

from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, List

class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class AlertRule:
    """Alert rule definition."""
    name: str
    condition: Callable[[Metrics], bool]
    severity: AlertSeverity
    message: str
    cooldown: timedelta = timedelta(minutes=15)
    last_triggered: Optional[datetime] = None

class AlertManager:
    """Manages alerts based on metrics."""

    def __init__(self):
        self.rules = self._define_rules()
        self.alert_channels = []  # Email, Slack, PagerDuty, etc.

    def _define_rules(self) -> List[AlertRule]:
        """Define alert rules."""
        return [
            # High error rate
            AlertRule(
                name="high_error_rate",
                condition=lambda m: (
                    m.error_count / m.request_count > 0.05
                    if m.request_count > 100 else False
                ),
                severity=AlertSeverity.ERROR,
                message="Error rate exceeded 5% (last 5 minutes)"
            ),

            # Rate limit near exhaustion
            AlertRule(
                name="rate_limit_high",
                condition=lambda m: (
                    rate_limiter.reddit_bucket.get_status()["utilization"] > 0.9
                ),
                severity=AlertSeverity.WARNING,
                message="Reddit API rate limit >90% utilized"
            ),

            # Low cache hit rate
            AlertRule(
                name="low_cache_hit_rate",
                condition=lambda m: (
                    m.cache_hits / (m.cache_hits + m.cache_misses) < 0.6
                    if (m.cache_hits + m.cache_misses) > 50 else False
                ),
                severity=AlertSeverity.WARNING,
                message="Cache hit rate below 60%"
            ),

            # High latency
            AlertRule(
                name="high_latency_p95",
                condition=lambda m: m.latency_p95 > 2000,  # 2 seconds
                severity=AlertSeverity.WARNING,
                message="P95 latency exceeded 2 seconds"
            ),

            # Circuit breaker open
            AlertRule(
                name="circuit_breaker_open",
                condition=lambda m: any(
                    breaker.state == CircuitState.OPEN
                    for breaker in circuit_breakers.breakers.values()
                ),
                severity=AlertSeverity.CRITICAL,
                message="Circuit breaker opened - service degraded"
            ),

            # Queue size high
            AlertRule(
                name="request_queue_full",
                condition=lambda m: (
                    request_queue.queue.qsize() > request_queue.max_size * 0.8
                ),
                severity=AlertSeverity.WARNING,
                message="Request queue >80% full"
            )
        ]

    async def check_alerts(self, metrics: Metrics):
        """Check all alert rules and trigger if needed."""

        now = datetime.utcnow()

        for rule in self.rules:
            # Skip if in cooldown
            if rule.last_triggered:
                if now - rule.last_triggered < rule.cooldown:
                    continue

            # Check condition
            try:
                if rule.condition(metrics):
                    await self._trigger_alert(rule, metrics)
                    rule.last_triggered = now

            except Exception as error:
                logger.error(
                    f"Error checking alert rule: {rule.name}",
                    exc_info=True
                )

    async def _trigger_alert(self, rule: AlertRule, metrics: Metrics):
        """Trigger an alert."""

        alert_data = {
            "rule": rule.name,
            "severity": rule.severity.value,
            "message": rule.message,
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": {
                "error_rate": metrics.error_count / metrics.request_count if metrics.request_count > 0 else 0,
                "latency_p95": metrics.latency_p95,
                "cache_hit_rate": metrics.cache_hits / (metrics.cache_hits + metrics.cache_misses) if (metrics.cache_hits + metrics.cache_misses) > 0 else 0
            }
        }

        # Log alert
        logger.error(
            f"ALERT: {rule.message}",
            extra=alert_data
        )

        # Send to alert channels
        for channel in self.alert_channels:
            try:
                await channel.send_alert(alert_data)
            except Exception as error:
                logger.error(
                    f"Failed to send alert to {channel}",
                    exc_info=True
                )

# Global alert manager
alert_manager = AlertManager()

# Background task to check alerts
async def alert_monitoring_task():
    """Background task to monitor and trigger alerts."""
    while True:
        try:
            metrics = metrics_collector.get_snapshot()
            await alert_manager.check_alerts(metrics)

            await asyncio.sleep(60)  # Check every minute

        except Exception as error:
            logger.error("Alert monitoring task error", exc_info=True)
            await asyncio.sleep(60)
```

---

## 5. Fault Tolerance & Recovery

### 5.1 Health Checks

**Comprehensive Health Monitoring:**

```python
# src/health/checks.py

from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
import asyncio

class HealthStatus(Enum):
    """Health check status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

@dataclass
class ComponentHealth:
    """Health status of a component."""
    name: str
    status: HealthStatus
    message: str
    last_check: datetime
    response_time_ms: Optional[float] = None
    details: Optional[dict] = None

class HealthChecker:
    """Performs health checks on dependencies."""

    async def check_redis(self) -> ComponentHealth:
        """Check Redis connectivity."""
        start = time.time()

        try:
            await redis_client.ping()
            response_time = (time.time() - start) * 1000

            return ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                message="Redis connection OK",
                last_check=datetime.utcnow(),
                response_time_ms=response_time
            )

        except Exception as error:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=f"Redis connection failed: {str(error)}",
                last_check=datetime.utcnow()
            )

    async def check_reddit_api(self) -> ComponentHealth:
        """Check Reddit API availability."""
        start = time.time()

        try:
            # Try to fetch Reddit status
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://www.reddit.com/api/v1/me",
                    headers={"Authorization": f"Bearer {await auth_manager.get_valid_token()}"},
                    timeout=5.0
                )

                response_time = (time.time() - start) * 1000

                if response.status_code == 200:
                    status = HealthStatus.HEALTHY
                    message = "Reddit API responding"
                elif response.status_code == 401:
                    status = HealthStatus.DEGRADED
                    message = "Reddit API auth issue"
                else:
                    status = HealthStatus.DEGRADED
                    message = f"Reddit API returned {response.status_code}"

                return ComponentHealth(
                    name="reddit_api",
                    status=status,
                    message=message,
                    last_check=datetime.utcnow(),
                    response_time_ms=response_time
                )

        except asyncio.TimeoutError:
            return ComponentHealth(
                name="reddit_api",
                status=HealthStatus.UNHEALTHY,
                message="Reddit API timeout",
                last_check=datetime.utcnow()
            )

        except Exception as error:
            return ComponentHealth(
                name="reddit_api",
                status=HealthStatus.UNHEALTHY,
                message=f"Reddit API error: {str(error)}",
                last_check=datetime.utcnow()
            )

    async def check_apify_kv_store(self) -> ComponentHealth:
        """Check Apify KV Store."""
        start = time.time()

        try:
            # Try to read/write test value
            test_key = "health_check"
            test_value = datetime.utcnow().isoformat()

            await kv_store.set_value(test_key, test_value)
            result = await kv_store.get_value(test_key)

            response_time = (time.time() - start) * 1000

            if result == test_value:
                return ComponentHealth(
                    name="apify_kv_store",
                    status=HealthStatus.HEALTHY,
                    message="KV Store read/write OK",
                    last_check=datetime.utcnow(),
                    response_time_ms=response_time
                )
            else:
                return ComponentHealth(
                    name="apify_kv_store",
                    status=HealthStatus.DEGRADED,
                    message="KV Store data mismatch",
                    last_check=datetime.utcnow()
                )

        except Exception as error:
            return ComponentHealth(
                name="apify_kv_store",
                status=HealthStatus.UNHEALTHY,
                message=f"KV Store error: {str(error)}",
                last_check=datetime.utcnow()
            )

    async def check_all(self) -> dict:
        """Run all health checks."""

        checks = await asyncio.gather(
            self.check_redis(),
            self.check_reddit_api(),
            self.check_apify_kv_store(),
            return_exceptions=True
        )

        components = {}
        overall_status = HealthStatus.HEALTHY

        for check in checks:
            if isinstance(check, Exception):
                overall_status = HealthStatus.UNHEALTHY
                continue

            components[check.name] = {
                "status": check.status.value,
                "message": check.message,
                "response_time_ms": check.response_time_ms,
                "last_check": check.last_check.isoformat()
            }

            # Determine overall status
            if check.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
            elif check.status == HealthStatus.DEGRADED and overall_status != HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.DEGRADED

        return {
            "status": overall_status.value,
            "timestamp": datetime.utcnow().isoformat(),
            "components": components
        }

# Health check endpoint
health_checker = HealthChecker()

@app.get("/health")
async def health_endpoint():
    """Health check endpoint."""
    health = await health_checker.check_all()

    # Return appropriate HTTP status
    status_code = {
        "healthy": 200,
        "degraded": 200,  # Still accepting requests
        "unhealthy": 503
    }[health["status"]]

    return JSONResponse(health, status_code=status_code)

@app.get("/health/ready")
async def readiness_endpoint():
    """Readiness check (can accept traffic)."""
    health = await health_checker.check_all()

    if health["status"] == "unhealthy":
        return JSONResponse(
            {"ready": False, "reason": "Dependencies unhealthy"},
            status_code=503
        )

    return {"ready": True}

@app.get("/health/live")
async def liveness_endpoint():
    """Liveness check (process is running)."""
    return {"alive": True}
```

### 5.2 Recovery Strategies

**Automated Recovery Procedures:**

```python
# src/resilience/recovery.py

from typing import Callable, Any
from datetime import datetime
import asyncio

class RecoveryStrategy:
    """Automated recovery strategies."""

    def __init__(self):
        self.recovery_attempts = {}

    async def recover_redis_connection(self) -> bool:
        """Attempt to reconnect to Redis."""
        logger.info("Attempting Redis recovery")

        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                # Recreate Redis client
                global redis_client
                redis_client = await create_redis_client()

                # Test connection
                await redis_client.ping()

                logger.info(f"Redis recovery successful (attempt {attempt + 1})")
                return True

            except Exception as error:
                logger.warning(
                    f"Redis recovery attempt {attempt + 1} failed: {error}"
                )
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

        logger.error("Redis recovery failed after all attempts")
        return False

    async def recover_reddit_oauth(self) -> bool:
        """Refresh Reddit OAuth token."""
        logger.info("Attempting Reddit OAuth recovery")

        try:
            await auth_manager._refresh_token()
            logger.info("Reddit OAuth recovery successful")
            return True

        except Exception as error:
            logger.error(f"Reddit OAuth recovery failed: {error}")
            return False

    async def switch_to_degraded_mode(self):
        """Switch to degraded mode (cache-only)."""
        logger.warning("Switching to degraded mode")

        # Set flag for degraded mode
        global DEGRADED_MODE
        DEGRADED_MODE = True

        # Notify users
        await self._notify_degraded_mode()

    async def exit_degraded_mode(self):
        """Exit degraded mode."""
        logger.info("Exiting degraded mode")

        global DEGRADED_MODE
        DEGRADED_MODE = False

        # Notify recovery
        await self._notify_recovery()

    async def _notify_degraded_mode(self):
        """Notify users of degraded mode."""
        # Send to monitoring channels
        notification = {
            "type": "service_degradation",
            "message": "Reddit MCP Server in degraded mode - serving cached data only",
            "timestamp": datetime.utcnow().isoformat()
        }

        logger.warning("Service degradation notification sent", extra=notification)

    async def _notify_recovery(self):
        """Notify users of service recovery."""
        notification = {
            "type": "service_recovery",
            "message": "Reddit MCP Server recovered - full functionality restored",
            "timestamp": datetime.utcnow().isoformat()
        }

        logger.info("Service recovery notification sent", extra=notification)

# Global recovery strategy
recovery_strategy = RecoveryStrategy()

# Background recovery task
async def automatic_recovery_task():
    """Background task for automatic recovery."""

    while True:
        try:
            # Check health
            health = await health_checker.check_all()

            # Attempt recovery for unhealthy components
            if health["status"] == "unhealthy":
                logger.warning("Unhealthy components detected, attempting recovery")

                for component_name, component in health["components"].items():
                    if component["status"] == "unhealthy":
                        if component_name == "redis":
                            await recovery_strategy.recover_redis_connection()
                        elif component_name == "reddit_api":
                            await recovery_strategy.recover_reddit_oauth()

                # If still unhealthy, switch to degraded mode
                health_after = await health_checker.check_all()
                if health_after["status"] == "unhealthy":
                    await recovery_strategy.switch_to_degraded_mode()

            # If healthy and in degraded mode, exit it
            elif health["status"] == "healthy" and DEGRADED_MODE:
                await recovery_strategy.exit_degraded_mode()

            # Sleep before next check
            await asyncio.sleep(30)

        except Exception as error:
            logger.error("Recovery task error", exc_info=True)
            await asyncio.sleep(30)
```

---

## 6. Implementation Checklist

### Phase 1: Foundation (Week 1)

- [ ] **Security Basics**
  - [ ] Implement OAuth2 flow for Reddit
  - [ ] Set up Apify KV Store for encrypted token storage
  - [ ] Configure environment variables in Apify Console
  - [ ] Create MCP client authentication (Bearer tokens)
  - [ ] Add PII-safe logging system

- [ ] **Error Handling Core**
  - [ ] Define error hierarchy (MCPError base class)
  - [ ] Implement error formatter for JSON-RPC responses
  - [ ] Add global error handler
  - [ ] Create retry strategy with exponential backoff
  - [ ] Test error responses for all tools

### Phase 2: Rate Limiting (Week 2)

- [ ] **Rate Limit Implementation**
  - [ ] Implement token bucket algorithm
  - [ ] Add per-user rate limiting (free vs paid tiers)
  - [ ] Create Reddit API rate limiter
  - [ ] Build priority request queue
  - [ ] Add queue status endpoint

- [ ] **Graceful Degradation**
  - [ ] Implement stale cache fallback
  - [ ] Add degraded mode flag
  - [ ] Create user notifications for queued requests
  - [ ] Test rate limit scenarios

### Phase 3: Monitoring (Week 3)

- [ ] **Metrics & Logging**
  - [ ] Set up structured JSON logging
  - [ ] Implement metrics collector
  - [ ] Add latency tracking (P50, P95, P99)
  - [ ] Track cache hit/miss rates
  - [ ] Create metrics dashboard endpoint

- [ ] **Alerting**
  - [ ] Define alert rules
  - [ ] Implement alert manager
  - [ ] Set up Sentry error tracking
  - [ ] Configure alert channels (email, Slack)
  - [ ] Test alert triggers

### Phase 4: Resilience (Week 4)

- [ ] **Fault Tolerance**
  - [ ] Implement circuit breaker pattern
  - [ ] Add health check endpoints (/health, /ready, /live)
  - [ ] Create automated recovery strategies
  - [ ] Test failure scenarios
  - [ ] Document manual intervention procedures

- [ ] **Input Validation**
  - [ ] Create Pydantic models for all tool inputs
  - [ ] Add sanitization for SQL injection/XSS
  - [ ] Enforce length limits
  - [ ] Test validation edge cases

### Phase 5: Compliance (Ongoing)

- [ ] **Data Privacy**
  - [ ] Implement GDPR data export
  - [ ] Add GDPR data deletion
  - [ ] Create retention policy enforcement
  - [ ] Document data handling procedures
  - [ ] Add privacy policy

- [ ] **Security Hardening**
  - [ ] Security audit of all endpoints
  - [ ] Penetration testing
  - [ ] Dependency vulnerability scan
  - [ ] Secret rotation procedures
  - [ ] Incident response plan

---

## Configuration Examples

### Apify Actor Configuration

```json
{
  "name": "reddit-mcp-server",
  "version": "1.0.0",
  "buildTag": "latest",
  "environmentVariables": {
    "REDDIT_CLIENT_ID": "your_client_id",
    "REDDIT_CLIENT_SECRET": "your_client_secret",
    "REDIS_URL": "redis://redis:6379",
    "MCP_MASTER_KEY": "generate_with_secrets_token_hex_32",
    "SENTRY_DSN": "https://your-sentry-dsn",
    "LOG_LEVEL": "INFO",
    "ENVIRONMENT": "production"
  },
  "resourceRequirements": {
    "memoryMbytes": 2048,
    "diskMbytes": 1024
  }
}
```

### Redis Configuration

```yaml
# docker-compose.yml
services:
  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3
```

### Sentry Configuration

```python
# src/monitoring/sentry.py

import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

def init_sentry():
    """Initialize Sentry error tracking."""

    if not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment,
        integrations=[
            AsyncioIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)
        ],
        traces_sample_rate=0.1,  # 10% of transactions
        profiles_sample_rate=0.1,
        before_send=filter_sensitive_data,
        ignore_errors=[ValidationError, RateLimitError]  # Don't report client errors
    )

def filter_sensitive_data(event, hint):
    """Filter sensitive data from Sentry events."""

    # Remove authorization headers
    if "request" in event and "headers" in event["request"]:
        headers = event["request"]["headers"]
        if "Authorization" in headers:
            headers["Authorization"] = "[REDACTED]"

    # Remove user data
    if "user" in event:
        event["user"] = {"id": event["user"].get("id")}  # Keep only ID

    return event
```

---

## Testing Strategy

### Security Testing

```python
# tests/test_security.py

import pytest
from src.auth.mcp_auth import MCPAuthManager

@pytest.mark.asyncio
async def test_invalid_api_key():
    """Test that invalid API keys are rejected."""
    with pytest.raises(HTTPException) as exc_info:
        await auth_manager.validate_token("invalid_key")

    assert exc_info.value.status_code == 401

@pytest.mark.asyncio
async def test_sql_injection_protection():
    """Test SQL injection prevention in inputs."""
    malicious_input = "'; DROP TABLE users; --"

    with pytest.raises(ValidationError):
        SearchRedditInput(query=malicious_input)

@pytest.mark.asyncio
async def test_xss_protection():
    """Test XSS prevention in inputs."""
    malicious_input = "<script>alert('xss')</script>"

    with pytest.raises(ValidationError):
        SearchRedditInput(query=malicious_input)

@pytest.mark.asyncio
async def test_pii_redaction_in_logs(caplog):
    """Test that PII is redacted from logs."""
    logger.info("User email@example.com made request with token abc123")

    assert "email@example.com" not in caplog.text
    assert "abc123" not in caplog.text
    assert "[REDACTED" in caplog.text
```

### Error Handling Testing

```python
# tests/test_error_handling.py

import pytest
from src.errors.exceptions import *

@pytest.mark.asyncio
async def test_rate_limit_error_format():
    """Test rate limit error format."""
    error = RateLimitError(retry_after=60)
    response = error.to_json_rpc()

    assert response["error"]["code"] == -32004
    assert response["error"]["data"]["retry_after_seconds"] == 60

@pytest.mark.asyncio
async def test_retry_on_transient_error():
    """Test retry logic for transient errors."""
    attempts = 0

    async def flaky_function():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RedditAPIError(503, "Service unavailable")
        return "success"

    result = await retry_strategy.execute_with_retry(flaky_function)

    assert result == "success"
    assert attempts == 3

@pytest.mark.asyncio
async def test_circuit_breaker_opens():
    """Test circuit breaker opens after failures."""
    breaker = CircuitBreaker("test_service", failure_threshold=3)

    # Trigger failures
    for _ in range(3):
        try:
            await breaker.call(lambda: raise RedditAPIError(500, "Error"))
        except:
            pass

    assert breaker.state == CircuitState.OPEN

    # Next call should fail fast
    with pytest.raises(ServiceUnavailableError):
        await breaker.call(lambda: "success")
```

---

**End of Security & Error Handling Architecture**

This architecture provides production-grade security, comprehensive error handling, intelligent rate limiting, and robust monitoring for the Reddit MCP Server. All components are designed to work together to create a resilient, secure, and observable system.
