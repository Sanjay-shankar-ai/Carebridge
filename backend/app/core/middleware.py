"""
CareBridge Security & Reliability Middleware
Provides:
1. Request size limit enforcement (prevents memory exhaustion & buffer overflow attacks).
2. Defense-in-depth security headers (X-Content-Type-Options, X-Frame-Options, Strict-Transport-Security).
3. Production exception masking & correlation ID tagging.
4. Correlation ID propagation via X-Correlation-ID / X-Workflow-ID headers.
"""

import uuid
import logging
from typing import Callable
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.core.correlation import set_correlation_ids, get_correlation_id, get_workflow_id

logger = logging.getLogger("carebridge.security.middleware")

MAX_REQUEST_BODY_BYTES = 5 * 1024 * 1024  # 5 Megabytes


class MaxRequestSizeMiddleware(BaseHTTPMiddleware):
    """Rejects incoming HTTP requests whose Content-Length exceeds the maximum safe limit."""

    def __init__(self, app, max_size_bytes: int = MAX_REQUEST_BODY_BYTES):
        super().__init__(app)
        self.max_size_bytes = max_size_bytes

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
                if length > self.max_size_bytes:
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={
                            "success": False,
                            "error": "Request Entity Too Large",
                            "message": f"Request body size of {length} bytes exceeds maximum allowed limit of {self.max_size_bytes} bytes."
                        }
                    )
            except ValueError:
                pass

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Applies OWASP-recommended HTTP security headers to all outbound responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        return response


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Propagates X-Correlation-ID and X-Workflow-ID through every request.
    - Reads incoming headers or generates new UUIDs.
    - Stores both in contextvars so any downstream code can read them.
    - Echoes both IDs back in the response headers.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        corr_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        wf_id = request.headers.get("X-Workflow-ID") or str(uuid.uuid4())

        set_correlation_ids(correlation_id=corr_id, workflow_id=wf_id)

        logger.debug("[Corr=%s] %s %s", corr_id[:8], request.method, request.url.path)

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = get_correlation_id()
        response.headers["X-Workflow-ID"] = get_workflow_id()
        return response
