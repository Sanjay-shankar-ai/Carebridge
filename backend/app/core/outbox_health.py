"""
Shared outbox health query logic used by both:
  - GET /health/outbox  (FastAPI endpoint)
  - python -m scripts.health_check  (CLI)

Notification.status values (from model):
  "pending"    — not yet dispatched
  "processing" — being dispatched right now
  "delivered"  — successfully sent
  "failed"     — transient failure, will retry
  "dead_letter"— exhausted retries
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.notification import Notification

PENDING_STATUSES = ("pending", "processing", "failed")
DEAD_LETTER_STATUS = "dead_letter"


class OutboxStats(TypedDict):
    pending_count: int
    dead_letter_count: int
    oldest_pending_seconds: float | None
    status: str            # "healthy" | "degraded" | "critical"


def get_outbox_stats(db: Session) -> OutboxStats:
    """
    Count pending / dead-lettered notifications and compute oldest pending age.
    Uses synchronous SQLAlchemy Session.
    """
    # Count pending (pending + processing + failed-but-retriable)
    pending_stmt = (
        select(func.count())
        .where(Notification.status.in_(PENDING_STATUSES))
    )
    pending_count: int = db.execute(pending_stmt).scalar_one()

    # Count dead-lettered
    dead_stmt = (
        select(func.count())
        .where(Notification.status == DEAD_LETTER_STATUS)
    )
    dead_letter_count: int = db.execute(dead_stmt).scalar_one()

    # Oldest pending age
    oldest_created_stmt = (
        select(func.min(Notification.created_at))
        .where(Notification.status.in_(PENDING_STATUSES))
    )
    oldest_created: datetime | None = db.execute(oldest_created_stmt).scalar_one()

    oldest_pending_seconds: float | None = None
    if oldest_created is not None:
        now = datetime.now(timezone.utc)
        if oldest_created.tzinfo is None:
            oldest_created = oldest_created.replace(tzinfo=timezone.utc)
        oldest_pending_seconds = (now - oldest_created).total_seconds()

    # Determine overall status
    if dead_letter_count > 0:
        status = "critical"
    elif pending_count > 50 or (oldest_pending_seconds is not None and oldest_pending_seconds > 300):
        status = "degraded"
    else:
        status = "healthy"

    return OutboxStats(
        pending_count=pending_count,
        dead_letter_count=dead_letter_count,
        oldest_pending_seconds=oldest_pending_seconds,
        status=status,
    )
