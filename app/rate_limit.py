"""
Rate Limiting Module for PriceScout API
Implementation of fixed-window rate limiting for all API endpoints.

Provides:
- FixedWindowRateLimiter: In-memory rate limiter (Redis-ready)
- rate_limit_middleware: FastAPI middleware for global application
"""

import time
import logging
from collections import defaultdict
from typing import Dict, Tuple, Optional
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app import config

logger = logging.getLogger(__name__)

class FixedWindowRateLimiter:
    """
    In-memory fixed window rate limiter.
    
    Tracks requests per key (usually IP) within a fixed time window.
    """
    
    def __init__(self, limit: int = 100, window_seconds: int = 60):
        self.limit = limit
        self.window_seconds = window_seconds
        # key -> (count, window_start_timestamp)
        self.windows: Dict[str, Tuple[int, float]] = defaultdict(lambda: (0, time.time()))

    def is_allowed(self, key: str) -> Tuple[bool, int, int]:
        """
        Check if request is allowed for the given key.
        
        Returns:
            (is_allowed, remaining, reset_time)
        """
        now = time.time()
        count, window_start = self.windows[key]
        
        # If window has expired, reset it
        if now - window_start > self.window_seconds:
            count = 0
            window_start = now
            self.windows[key] = (0, now)
        
        # Increment count
        count += 1
        self.windows[key] = (count, window_start)
        
        is_allowed = count <= self.limit
        remaining = max(0, self.limit - count)
        reset_time = int(window_start + self.window_seconds)
        
        return is_allowed, remaining, reset_time

# Global rate limiter instance
# Default: 200 requests per minute per IP
global_limiter = FixedWindowRateLimiter(
    limit=int(config.os.getenv('GLOBAL_RATE_LIMIT', '200')),
    window_seconds=int(config.os.getenv('GLOBAL_RATE_WINDOW', '60'))
)

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware to apply global rate limiting.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks and docs
        path = request.url.path
        if path.startswith("/api/v1/health") or path in ["/docs", "/redoc", "/api/v1/openapi.json", "/"]:
            return await call_next(request)
            
        # Get client IP (handle proxy headers)
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.client.host if request.client else "unknown"
            
        # Use API key if present, otherwise IP
        api_key = request.headers.get("X-API-Key")
        key = f"api_key:{api_key}" if api_key else f"ip:{client_ip}"
        
        allowed, remaining, reset = global_limiter.is_allowed(key)
        
        if not allowed:
            logger.warning(f"Rate limit exceeded for {key} on {path}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "type": "https://api.pricescout.io/problems/rate-limited",
                    "title": "Rate Limit Exceeded",
                    "status": 429,
                    "detail": f"Rate limit of {global_limiter.limit} requests per {global_limiter.window_seconds} seconds exceeded.",
                    "instance": path
                },
                headers={
                    "Retry-After": str(reset - int(time.time())),
                    "X-RateLimit-Limit": str(global_limiter.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset)
                }
            )
            
        response = await call_next(request)
        
        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(global_limiter.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset)
        
        return response
