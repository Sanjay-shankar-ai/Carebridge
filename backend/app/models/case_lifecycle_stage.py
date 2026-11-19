"""
Case Lifecycle Stage Relational Model
Authoritative, relational persistence for the 14-stage care coordination journey.
Ensures stages are backed by database state and verified evidence, not ephemeral JSON alone.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import String, Integer, DateTime, JSON, ForeignKey, Boolean, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from app.database.session import Base, TimestampedUUIDMixin


class CaseLifecycleStage(Base, TimestampedUUIDMixin):
    __tablename__ = "case_lifecycle_stages"
    __table_args__ = (
        UniqueConstraint("case_id", "stage_number", name="uq_case_stage_number"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("care_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    stage_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        index=True,
        nullable=False
    ) # "pending", "active", "completed", "skipped"

    responsible_role: Mapped[str] = mapped_column(String(64), nullable=False)
    responsible_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    responsible_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    evidence_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    evidence_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    evidence_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    patient_notification_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship back to CareCase
    care_case: Mapped["CareCase"] = relationship("CareCase", back_populates="lifecycle_stage_records")

    def __repr__(self) -> str:
        return f"<CaseLifecycleStage Case={self.case_id} Stage={self.stage_number} ({self.stage_id}) Status={self.status}>"
