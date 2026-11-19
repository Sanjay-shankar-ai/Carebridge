"""
Case Event and Audit Log Relational Models
Provides timeline observability and tamper-evident audit history across all AI and human actions.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import String, Text, DateTime, Integer, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from app.database.session import Base, TimestampedUUIDMixin


class CaseEvent(Base, TimestampedUUIDMixin):
    """Timeline event capturing state changes, communications, and milestones."""
    __tablename__ = "case_events"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("care_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relationships
    care_case: Mapped["CareCase"] = relationship("CareCase", back_populates="case_events")

    def __repr__(self) -> str:
        return f"<CaseEvent {self.event_type} at {self.timestamp}>"


class AuditLog(Base, TimestampedUUIDMixin):
    """FHIR-aligned AuditEvent Model capturing actor, autonomy level, state deltas, and rationale."""
    __tablename__ = "audit_logs"

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
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False) # "ai_agent", "human_coordinator", "clinician", "system_scheduler"
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(128), index=True, nullable=False) # e.g. "SCHEDULE_VISIT", "REROUTE_REFERRAL", "VERIFY_CLOSURE"
    autonomy_level: Mapped[int] = mapped_column(Integer, default=1) # 1 = Autonomous, 2 = Constrained, 3 = Human Authorized
    previous_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    new_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Tracing (Phase 6)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    workflow_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)

    # Relationships
    care_case: Mapped[Optional["CareCase"]] = relationship("CareCase", back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} by {self.actor_type}:{self.actor_id} (Level {self.autonomy_level})>"
