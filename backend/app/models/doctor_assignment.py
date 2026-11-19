"""
CareBridge Doctor Assignment Relational Model
Tracks the intelligent specialty-based allocation of patient cases to doctors,
including doctor response deadlines, acceptance, decline, automatic expiration,
and coordinator escalation.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import String, Text, DateTime, JSON, ForeignKey, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from app.database.session import Base, TimestampedUUIDMixin


class DoctorAssignment(Base, TimestampedUUIDMixin):
    """
    Persisted doctor assignment record with a discrete state machine:
    - PENDING_DOCTOR_RESPONSE
    - ACCEPTED
    - DECLINED
    - EXPIRED
    - ESCALATED_TO_COORDINATOR
    - REASSIGNMENT_PENDING
    - REASSIGNED
    - CANCELLED
    """
    __tablename__ = "doctor_assignments"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("care_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("case_owners.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # State Machine
    status: Mapped[str] = mapped_column(
        String(64),
        default="PENDING_DOCTOR_RESPONSE",
        index=True,
        nullable=False
    )

    # Allocation & Matching Data
    specialty_matched: Mapped[str] = mapped_column(String(128), nullable=False)
    subspecialty_matched: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    urgency_level: Mapped[str] = mapped_column(String(32), default="standard", index=True, nullable=False)
    allocation_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    allocation_factors: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Provenance
    assigned_by_role: Mapped[str] = mapped_column(String(64), default="ai_allocation_agent", nullable=False)
    assigned_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    reassignment_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Deadline & Timing
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decline_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    escalated_to_coordinator_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Concurrency and Idempotency
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Relationships
    care_case: Mapped["CareCase"] = relationship("CareCase", back_populates="doctor_assignments")
    doctor: Mapped["CaseOwner"] = relationship("CaseOwner", back_populates="doctor_assignments")

    def __repr__(self) -> str:
        return f"<DoctorAssignment Case={self.case_id} Doctor={self.doctor_id} Status={self.status} Score={self.allocation_score}>"
