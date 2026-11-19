"""
Closure Evidence Relational Model
Guarantees verified closed-loop care coordination with documented clinical evidence.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import String, Text, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from app.database.session import Base, TimestampedUUIDMixin


class ClosureEvidence(Base, TimestampedUUIDMixin):
    """Enforces evidence-based closure rules. AI can propose closure, but verified sign-off is required."""
    __tablename__ = "closure_evidences"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("care_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False) # "consultation_note", "pathology_report", "surveillance_imaging", "authorized_human_signoff"
    evidence_summary: Mapped[str] = mapped_column(Text, nullable=False)
    verifying_clinician_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("case_owners.id", ondelete="SET NULL"),
        nullable=True
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Relationships
    care_case: Mapped["CareCase"] = relationship("CareCase", back_populates="closure_evidences")
    verifying_clinician: Mapped[Optional["CaseOwner"]] = relationship("CaseOwner", back_populates="verified_closures")

    def __repr__(self) -> str:
        return f"<ClosureEvidence {self.evidence_type} (Verified: {self.is_verified})>"
