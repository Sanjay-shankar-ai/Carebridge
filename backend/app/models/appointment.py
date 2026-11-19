"""
Appointment Relational Model
FHIR Appointment alignment for tracking visits, no-shows, and attendance verification.
"""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from app.database.session import Base, TimestampedUUIDMixin


class Appointment(Base, TimestampedUUIDMixin):
    __tablename__ = "appointments"

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
    facility: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False)
    appointment_type: Mapped[str] = mapped_column(String(128), nullable=False) # "consultation", "biopsy", "ultrasound", "surveillance"
    scheduled_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)

    # 10-State Machine & Dual-Confirmation Versioning
    status: Mapped[str] = mapped_column(
        String(64),
        default="PROPOSED",
        index=True,
        nullable=False
    ) # "PROPOSED", "PENDING_DOCTOR_CONFIRMATION", "PENDING_PATIENT_CONFIRMATION", "CONFIRMED",
      # "DECLINED_BY_DOCTOR", "DECLINED_BY_PATIENT", "RESCHEDULE_REQUESTED", "CANCELLED", "COMPLETED", "NO_SHOW"
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    doctor_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    doctor_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    doctor_confirmed_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    patient_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    patient_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    patient_confirmed_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    proposed_by_role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    proposed_by_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    rescheduled_from_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("appointments.id", ondelete="SET NULL"),
        nullable=True
    )
    attendance_recorded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cancellation_outcome: Mapped[Optional[str]] = mapped_column(String(255), nullable=True) # "reschedule_pending", "patient_refused", "escalated_to_coordinator"
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    care_case: Mapped["CareCase"] = relationship("CareCase", back_populates="appointments")

    def __repr__(self) -> str:
        return f"<Appointment at {self.facility} on {self.scheduled_time} ({self.status})>"
