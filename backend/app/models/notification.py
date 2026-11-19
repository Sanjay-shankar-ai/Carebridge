"""
CareBridge Persistent Notification Relational Model (Phase 7)
Stores role-scoped, database-backed notifications with idempotency keys,
safe clinical previews, read tracking, and audit references.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import String, Text, DateTime, Boolean, Integer, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from app.database.session import Base, TimestampedUUIDMixin


class Notification(Base, TimestampedUUIDMixin):
    """
    Persistent, PostgreSQL-backed notification record for Patient, Doctor, and Coordinator roles.
    Enforces strict user ownership, prevents duplicate alerts via idempotency keys,
    and safeguards patient privacy with de-identified, action-oriented previews.
    """
    __tablename__ = "notifications"

    # Recipient user ID (foreign key to users table)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Recipient application role: "patient", "doctor", "care_coordinator"
    role: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # Event type enum
    # e.g.: "screening_result_available", "referral_created", "referral_accepted",
    #       "referral_delayed", "appointment_booked", "appointment_changed",
    #       "appointment_cancelled", "appointment_reminder", "missed_appointment",
    #       "recovery_outreach", "patient_message", "clinical_escalation",
    #       "doctor_review_completed", "case_closure_approved", "sla_warning"
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    # Safe display title (no exposed clinical staging/sensitive raw data)
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    # User-facing notification message
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Urgency tier: "normal", "urgent", "critical"
    priority: Mapped[str] = mapped_column(String(32), default="normal", nullable=False, index=True)

    # Optional foreign key references for action routing
    case_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("care_cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Read state tracking
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Transactional Outbox Lifecycle Fields (Phase 3)
    # States: "pending", "processing", "delivered", "failed", "dead_letter"
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    processing_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Direct in-app navigation link (e.g. "/patient", "/doctor", "/cases/uuid")
    action_link: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Idempotency key to prevent duplicate notifications from repeated events/reconnects
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=True
    )

    # Additional contextual metadata (appointment ID, facility, channel, etc.)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    care_case: Mapped[Optional["CareCase"]] = relationship("CareCase", foreign_keys=[case_id])
    patient: Mapped[Optional["Patient"]] = relationship("Patient", foreign_keys=[patient_id])

    def __repr__(self) -> str:
        return f"<Notification {self.id} for User {self.user_id} ({self.event_type}) is_read={self.is_read}>"
