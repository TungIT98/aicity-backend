"""
Rate Limiting Module for AI City API
In-memory rate limiting with IP-based tracking
"""
import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Rate limit storage: {ip: [(timestamp, endpoint), ...]}
rate_limit_storage = defaultdict(list)

# Rate limits (requests per minute)
RATE_LIMITS = {
    'auth': 10,       # /api/auth/* endpoints - stricter (prevent brute force)
    'public': 120,     # /health, /leads - moderate
    'protected': 200,  # authenticated endpoints - higher
    'default': 60,     # all other endpoints
}

# Cleanup interval (seconds)
CLEANUP_INTERVAL = 60


def get_client_ip(request) -> str:
    """Extract client IP from request, handling proxies"""
    forwarded = request.headers.get('x-forwarded-for')
    if forwarded:
        return forwarded.split(',')[0].strip()
    real_ip = request.headers.get('x-real-ip')
    if real_ip:
        return real_ip
    if request.client:
        return request.client.host
    return 'unknown'


def is_rate_limited(ip: str, endpoint: str) -> tuple:
    """Check if IP is rate limited. Returns (is_limited, headers)."""
    current_time = time.time()
    window_start = current_time - CLEANUP_INTERVAL

    # Determine rate limit tier
    if '/auth/' in endpoint:
        limit = RATE_LIMITS['auth']
    elif endpoint in ['/', '/health'] or endpoint == '/leads':
        limit = RATE_LIMITS['public']
    elif endpoint.startswith('/api/'):
        limit = RATE_LIMITS['protected']
    else:
        limit = RATE_LIMITS['default']

    # Clean old entries
    ip_requests = rate_limit_storage[ip]
    ip_requests[:] = [(ts, ep) for ts, ep in ip_requests if ts > window_start]

    # Count requests to this endpoint
    endpoint_requests = sum(1 for ts, ep in ip_requests if ep == endpoint)

    if endpoint_requests >= limit:
        oldest = min((ts for ts, ep in ip_requests if ep == endpoint), default=current_time)
        reset_time = int(oldest + CLEANUP_INTERVAL - current_time)
        headers = {
            'X-RateLimit-Limit': str(limit),
            'X-RateLimit-Remaining': '0',
            'X-RateLimit-Reset': str(reset_time),
            'Retry-After': str(max(1, reset_time)),
        }
        return True, headers

    # Add this request
    ip_requests.append((current_time, endpoint))

    remaining = limit - endpoint_requests - 1
    headers = {
        'X-RateLimit-Limit': str(limit),
        'X-RateLimit-Remaining': str(max(0, remaining)),
        'X-RateLimit-Reset': str(CLEANUP_INTERVAL),
    }
    return False, headers


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware for FastAPI"""

    async def dispatch(self, request, call_next):
        # Skip OPTIONS (CORS preflight)
        if request.method == 'OPTIONS':
            return await call_next(request)

        ip = get_client_ip(request)
        endpoint = request.url.path

        is_limited, headers = is_rate_limited(ip, endpoint)

        if is_limited:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": f"Rate limit exceeded. Try again in {headers.get('Retry-After', 60)} seconds.",
                    "code": "RATE_LIMIT_EXCEEDED"
                },
                headers=headers
            )

        response = await call_next(request)

        for key, value in headers.items():
            response.headers[key] = value

        return response
