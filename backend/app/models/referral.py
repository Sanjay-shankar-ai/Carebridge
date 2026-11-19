"""
Referral Relational Model
FHIR ServiceRequest alignment for inter-facility and specialist handoffs.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from app.database.session import Base, TimestampedUUIDMixin


class Referral(Base, TimestampedUUIDMixin):
    __tablename__ = "referrals"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("care_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    referring_provider: Mapped[str] = mapped_column(String(255), nullable=False)
    target_facility: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    specialty: Mapped[str] = mapped_column(String(128), nullable=False) # e.g. "Diagnostic Radiology", "Surgical Oncology"
    reason_for_referral: Mapped[str] = mapped_column(Text, nullable=False)
    clinical_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_educational_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Referral Lifecycle & Handoff Tracking
    status: Mapped[str] = mapped_column(
        String(32),
        default="draft",
        index=True,
        nullable=False
    ) # "draft", "sent", "accepted", "rejected", "rerouted", "completed"
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acceptance_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Patient Decision Tracking
    patient_decision: Mapped[Optional[str]] = mapped_column(String(32), nullable=True) # "accept", "wait", "alternative", "clarification"
    patient_decision_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    patient_decision_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Concurrency and Idempotency
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)

    # Relationships
    care_case: Mapped["CareCase"] = relationship("CareCase", back_populates="referrals")

    def __repr__(self) -> str:
        return f"<Referral to {self.target_facility} ({self.status})>"
