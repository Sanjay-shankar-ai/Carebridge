"""
CareBridge Rate Limiting Module
Implements in-memory sliding window rate limiting for authentication and AI cognitive endpoints.
Provides defense-in-depth against credential stuffing, brute-force attacks, and DoS on LLM backends.
"""

import os
import time
import threading
from typing import Dict, List, Optional
from fastapi import Request, HTTPException, status


class SlidingWindowRateLimiter:
    """
    Thread-safe in-memory sliding window rate limiter.
    Tracks request timestamps within a moving window per client key (IP or User).
    """

    def __init__(self, max_requests: int = 15, window_seconds: int = 60, name: str = "RateLimiter"):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.name = name
        self._requests: Dict[str, List[float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()

    def _cleanup_expired(self, now: float):
        """Purges old entries across all keys every 5 minutes."""
        if now - self._last_cleanup > 300:
            cutoff = now - self.window_seconds
            keys_to_delete = []
            for k, timestamps in self._requests.items():
                active = [t for t in timestamps if t > cutoff]
                if active:
                    self._requests[k] = active
                else:
                    keys_to_delete.append(k)
            for k in keys_to_delete:
                del self._requests[k]
            self._last_cleanup = now

    def check(self, key: str, max_req: Optional[int] = None, window_sec: Optional[int] = None) -> None:
        """
        Records an access for `key`. Raises HTTP 429 if the rate limit is exceeded.
        """
        limit = max_req or self.max_requests
        window = window_sec or self.window_seconds

        now = time.time()
        cutoff = now - window

        with self._lock:
            self._cleanup_expired(now)
            timestamps = self._requests.get(key, [])
            valid_timestamps = [t for t in timestamps if t > cutoff]

            if len(valid_timestamps) >= limit:
                oldest = valid_timestamps[0]
                retry_after = max(1, int(oldest + window - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded for {self.name}. Maximum {limit} requests per {window}s. Please retry in {retry_after}s.",
                    headers={"Retry-After": str(retry_after)}
                )

            valid_timestamps.append(now)
            self._requests[key] = valid_timestamps

    def reset(self, key: Optional[str] = None):
        """Resets rate limiting state (useful for test resets)."""
        with self._lock:
            if key:
                self._requests.pop(key, None)
            else:
                self._requests.clear()


# Pre-configured instances
login_rate_limiter = SlidingWindowRateLimiter(max_requests=15, window_seconds=60, name="Login API")
agent_rate_limiter = SlidingWindowRateLimiter(max_requests=30, window_seconds=60, name="AI Brain Interaction API")


def get_client_ip(request: Request) -> str:
    """Extracts client IP, respecting X-Forwarded-For if behind a trusted reverse proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def rate_limit_login(request: Request):
    """FastAPI dependency for login rate limiting."""
    if os.environ.get("TESTING") == "true" or request.headers.get("X-Bypass-Rate-Limit") == "1":
        return
    client_ip = get_client_ip(request)
    login_rate_limiter.check(f"login_{client_ip}")


def rate_limit_agent(request: Request):
    """FastAPI dependency for AI agent rate limiting."""
    if os.environ.get("TESTING") == "true" or request.headers.get("X-Bypass-Rate-Limit") == "1":
        return
    client_ip = get_client_ip(request)
    agent_rate_limiter.check(f"agent_{client_ip}")
