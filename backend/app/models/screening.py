"""
Screening Result Relational Model
FHIR DiagnosticReport alignment for abnormal findings and laboratory results.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from app.database.session import Base, TimestampedUUIDMixin


class ScreeningResult(Base, TimestampedUUIDMixin):
    __tablename__ = "screening_results"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    screening_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False) # e.g. "Mammogram", "Cervical", "Colorectal"
    test_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finding_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False) # e.g. "BI-RADS-4", "BI-RADS-5", "Suspicious"
    finding_summary: Mapped[str] = mapped_column(Text, nullable=False)
    urgency_level: Mapped[str] = mapped_column(String(32), default="standard") # "standard", "urgent", "critical"
    performing_facility: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_report_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    # Relationships
    patient: Mapped["Patient"] = relationship("Patient", back_populates="screening_results")
    care_case: Mapped[Optional["CareCase"]] = relationship("CareCase", back_populates="screening_result", uselist=False)

    def __repr__(self) -> str:
        return f"<ScreeningResult {self.screening_type} ({self.finding_code}) - Urgency: {self.urgency_level}>"
