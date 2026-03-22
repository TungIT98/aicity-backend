"""
Rate Limiting Middleware for AI City API.

Vercel-compatible rate limiting using:
- Upstash Redis for production (serverless-friendly)
- In-memory fallback for local development

Usage:
    # In main.py:
    from api.rate_limiter import RateLimitMiddleware, rate_limit
    app.add_middleware(RateLimitMiddleware)
"""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse
from typing import Callable, Optional
import os
import time
import hashlib
from collections import defaultdict
from dataclasses import dataclass
import logging

log = logging.getLogger(__name__)

# ─── Configuration ──────────────────────────────────────────────────────────────

UPSTASH_REDIS_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")

# Rate limits per endpoint group (requests per window)
RATE_LIMITS = {
    "default": {"requests": 1000, "window": 60},       # 1000/minute
    "search": {"requests": 100, "window": 60},        # 100/minute for search
    "auth": {"requests": 20, "window": 60},           # 20/minute for auth
    "write": {"requests": 200, "window": 60},          # 200/minute for writes
}

# Exempt paths (no rate limiting)
EXEMPT_PATHS = {"/", "/health", "/api/docs", "/api/redoc", "/api/openapi.json"}


# ─── In-Memory Store (local dev only) ─────────────────────────────────────────

class InMemoryStore:
    """In-memory rate limit store. Not suitable for production/Vercel."""

    def __init__(self):
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        """Check if request is allowed. Returns (allowed, remaining, reset_at)."""
        now = time.time()
        # Remove expired entries
        self.requests[key] = [t for t in self.requests[key] if now - t < window]

        current = len(self.requests[key])
        if current >= limit:
            oldest = min(self.requests[key]) if self.requests[key] else now
            reset_at = int(oldest + window)
            return False, 0, reset_at

        self.requests[key].append(now)
        remaining = limit - current - 1
        reset_at = int(now + window)
        return True, remaining, reset_at


# ─── Upstash Redis Store (production/Vercel) ───────────────────────────────────

class UpstashStore:
    """Upstash Redis rate limiting store. Production-ready for serverless."""

    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token

    def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        """Atomic rate limit check using Upstash REST API."""
        import httpx

        # Use sliding window with Upstash
        now = time.time()
        window_sec = window
        window_key = f"rl:{key}:{int(now // window_sec)}"

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        # Atomic increment and expire
        body = [
            ["ZREMRANGEBYSCORE", window_key, "0", str(now - window_sec)],
            ["ZADD", window_key, str(now), f"{now}:{id(self)}"],
            ["EXPIRE", window_key, str(window_sec)],
            ["ZCARD", window_key],
        ]

        try:
            with httpx.Client(timeout=5) as client:
                resp = client.post(
                    f"{self.url}/pipeline",
                    headers=headers,
                    json=body,
                )

            if resp.status_code != 200:
                # Fallback: allow on error
                return True, limit - 1, int(now + window)

            result = resp.json()
            current = result[3].get("result", 0) if isinstance(result, list) else 0

            if current >= limit:
                return False, 0, int(now + window_sec)

            return True, limit - current - 1, int(now + window_sec)
        except Exception as e:
            log.warning(f"Upstash rate limit error: {e}")
            return True, limit - 1, int(now + window)


# ─── Rate Limit Store Factory ─────────────────────────────────────────────────

def get_rate_limit_store() -> Optional[object]:
    """Get the appropriate rate limit store based on environment."""
    if UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN:
        return UpstashStore(UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN)
    return InMemoryStore()


# ─── Rate Limit Key Generation ────────────────────────────────────────────────

def get_client_key(request: Request) -> str:
    """Generate rate limit key for a request."""
    # Use X-Forwarded-For header behind Vercel proxy, else client host
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"

    # Include user ID for authenticated requests
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"
    return f"ip:{ip}"


def get_limit_for_path(path: str) -> dict:
    """Determine rate limit config for a request path."""
    if path.startswith("/search") or path.startswith("/api/search"):
        return RATE_LIMITS["search"]
    elif path.startswith("/api/auth/"):
        return RATE_LIMITS["auth"]
    elif request.method in ("POST", "PUT", "PATCH", "DELETE"):
        return RATE_LIMITS["write"]
    return RATE_LIMITS["default"]


# ─── FastAPI Dependency ───────────────────────────────────────────────────────

class RateLimitInfo:
    """Rate limit info attached to request state."""

    def __init__(self, allowed: bool, remaining: int, limit: int, reset_at: int):
        self.allowed = allowed
        self.remaining = remaining
        self.limit = limit
        self.reset_at = reset_at


async def check_rate_limit(
    request: Request,
    limit_type: Optional[str] = None,
) -> RateLimitInfo:
    """
    FastAPI dependency to check and enforce rate limits.

    Usage:
        @app.post("/search")
        async def search(req: Request, _: RateLimitInfo = Depends(check_rate_limit)):
            ...
    """
    # Skip for exempt paths
    if request.url.path in EXEMPT_PATHS:
        return RateLimitInfo(allowed=True, remaining=9999, limit=9999, reset_at=0)

    # Determine limit type
    if limit_type:
        limits = RATE_LIMITS.get(limit_type, RATE_LIMITS["default"])
    else:
        path = request.url.path
        if path.startswith("/search") or path.startswith("/api/search"):
            limits = RATE_LIMITS["search"]
        elif path.startswith("/api/auth/"):
            limits = RATE_LIMITS["auth"]
        elif request.method in ("POST", "PUT", "PATCH", "DELETE"):
            limits = RATE_LIMITS["write"]
        else:
            limits = RATE_LIMITS["default"]

    key = get_client_key(request)
    store = get_rate_limit_store()

    if store is None:
        return RateLimitInfo(allowed=True, remaining=limits["requests"], limit=limits["requests"], reset_at=0)

    allowed, remaining, reset_at = store.is_allowed(key, limits["requests"], limits["window"])
    return RateLimitInfo(allowed=allowed, remaining=remaining, limit=limits["requests"], reset_at=reset_at)


# ─── Middleware ────────────────────────────────────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Automatic rate limiting middleware.

    Adds rate limit headers to every response:
    - X-RateLimit-Limit: max requests
    - X-RateLimit-Remaining: remaining requests
    - X-RateLimit-Reset: reset timestamp (Unix)

    Returns 429 Too Many Requests when limit exceeded.
    """

    def __init__(self, app, default_limits: Optional[dict] = None):
        super().__init__(app)
        self.default_limits = default_limits or RATE_LIMITS["default"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip exempt paths
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        # Determine limits
        path = request.url.path
        if path.startswith("/search") or path.startswith("/api/search"):
            limits = RATE_LIMITS["search"]
        elif path.startswith("/api/auth/"):
            limits = RATE_LIMITS["auth"]
        elif request.method in ("POST", "PUT", "PATCH", "DELETE"):
            limits = RATE_LIMITS["write"]
        else:
            limits = RATE_LIMITS["default"]

        key = get_client_key(request)
        store = get_rate_limit_store()

        if store:
            allowed, remaining, reset_at = store.is_allowed(key, limits["requests"], limits["window"])

            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "Too Many Requests",
                        "message": f"Rate limit exceeded. Try again in {reset_at - int(time.time())} seconds.",
                        "limit": limits["requests"],
                        "window_seconds": limits["window"],
                        "reset_at": reset_at,
                    },
                    headers={
                        "X-RateLimit-Limit": str(limits["requests"]),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset_at),
                        "Retry-After": str(max(1, reset_at - int(time.time()))),
                    },
                )
        else:
            # No store configured - allow all
            remaining = limits["requests"]
            reset_at = int(time.time()) + limits["window"]

        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(limits["requests"])
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(reset_at)

        return response


# ─── Per-Endpoint Rate Limit Decorator ────────────────────────────────────────

def rate_limit(limit_type: str = "default"):
    """
    Decorator-style rate limiting for specific endpoints.

    Usage:
        @router.get("/search")
        @rate_limit("search")
        async def search():
            ...
    """
    async def dependency(request: Request) -> None:
        limits = RATE_LIMITS.get(limit_type, RATE_LIMITS["default"])
        key = get_client_key(request)
        store = get_rate_limit_store()

        if store:
            allowed, remaining, reset_at = store.is_allowed(key, limits["requests"], limits["window"])
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded for {limit_type}. Try again later.",
                    headers={
                        "X-RateLimit-Limit": str(limits["requests"]),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset_at),
                        "Retry-After": str(max(1, reset_at - int(time.time()))),
                    },
                )

    return dependency
