from fastapi import APIRouter
from app.core.config import settings
from app.schemas.common import HealthResponse, ApiResponseEnvelope
from app.core.observability import get_observability_status
from app.core.outbox_health import get_outbox_stats
from app.database.session import get_sync_db

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="Service Health Probe")
async def health_check() -> HealthResponse:
    """
    Returns the health status, app metadata, and current timestamp.
    Used for container readiness and monitoring.
    """
    return HealthResponse(
        status="healthy",
        app_name=settings.APP_NAME,
        environment=settings.ENVIRONMENT,
        version="0.1.0"
    )


@router.get("/health/observability", summary="LangSmith AI Observability Status")
async def observability_check():
    """
    Returns live LangSmith tracing and observability status.
    """
    status_data = get_observability_status()
    return ApiResponseEnvelope.success_response(
        data=status_data,
        message="Observability status retrieved."
    )


@router.get("/health/outbox", summary="Outbox Health Check")
async def outbox_health():
    """
    Returns the current state of the notification outbox:
    - pending_count: notifications awaiting delivery (pending/processing/failed)
    - dead_letter_count: notifications that have exhausted all retries
    - oldest_pending_seconds: age in seconds of the oldest undelivered notification
    - status: 'healthy' | 'degraded' | 'critical'
    """
    db = get_sync_db()
    try:
        stats = get_outbox_stats(db)
    finally:
        db.close()

    return ApiResponseEnvelope.success_response(
        data={
            "pending_count": stats["pending_count"],
            "dead_letter_count": stats["dead_letter_count"],
            "oldest_pending_seconds": stats["oldest_pending_seconds"],
            "status": stats["status"],
        },
        message="Outbox health retrieved."
    )
