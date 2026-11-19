"""
Patient and Consent Relational Models
"""

import uuid
from datetime import date, datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import String, Date, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from app.database.session import Base, TimestampedUUIDMixin


class Patient(Base, TimestampedUUIDMixin):
    __tablename__ = "patients"

    mrn: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    last_name: Mapped[str] = mapped_column(String(128), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[str] = mapped_column(String(32), default="unknown")
    
    # Patient Memory Attributes
    preferred_language: Mapped[str] = mapped_column(String(16), default="en", index=True) # "en", "ta", "mixed"
    communication_channel: Mapped[str] = mapped_column(String(32), default="sms") # "sms", "whatsapp", "call"
    accessibility_requirements: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {"large_text": False, "voice_preferred": False, "mobility_assistance": False}
    )
    patient_context: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {
            "caregiver_name": None,
            "caregiver_phone": None,
            "transportation_support": True,
            "known_barriers": []
        }
    )

    # Relationships
    care_cases: Mapped[List["CareCase"]] = relationship("CareCase", back_populates="patient", cascade="all, delete-orphan")
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="patient", cascade="all, delete-orphan")
    screening_results: Mapped[List["ScreeningResult"]] = relationship("ScreeningResult", back_populates="patient", cascade="all, delete-orphan")
    consents: Mapped[List["Consent"]] = relationship("Consent", back_populates="patient", cascade="all, delete-orphan")
    communications: Mapped[List["Communication"]] = relationship("Communication", back_populates="patient", cascade="all, delete-orphan")
    conversation_sessions: Mapped[List["ConversationSession"]] = relationship("ConversationSession", back_populates="patient", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Patient {self.mrn}: {self.first_name} {self.last_name} ({self.preferred_language})>"


class Consent(Base, TimestampedUUIDMixin):
    """FHIR-aligned Consent Model for granular data access and outreach permissions."""
    __tablename__ = "consents"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    scope: Mapped[str] = mapped_column(String(128), nullable=False) # e.g. "care_coordination", "sms_outreach", "referral_sharing"
    status: Mapped[str] = mapped_column(String(32), default="active") # "active", "revoked", "pending"
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    patient: Mapped["Patient"] = relationship("Patient", back_populates="consents")

    def __repr__(self) -> str:
        return f"<Consent {self.scope}: {self.status}>"
