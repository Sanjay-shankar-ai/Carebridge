"""
Communication and Conversation Session Relational Models
Tracks multilingual touchpoints, comprehension verification, and session memory.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import String, Text, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from app.database.session import Base, TimestampedUUIDMixin


class ConversationSession(Base, TimestampedUUIDMixin):
    """Encapsulates persistent conversation memory and commitments across patient touchpoints."""
    __tablename__ = "conversation_sessions"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    case_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("care_cases.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    channel: Mapped[str] = mapped_column(String(32), default="in_app_chat")
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unanswered_questions: Mapped[List[str]] = mapped_column(JSON, default=list)
    patient_commitments: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_interaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    patient: Mapped["Patient"] = relationship("Patient", back_populates="conversation_sessions")
    communications: Mapped[List["Communication"]] = relationship("Communication", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ConversationSession {self.id} for Patient {self.patient_id} (Active: {self.is_active})>"


class Communication(Base, TimestampedUUIDMixin):
    """FHIR-aligned Communication Model capturing patient exchanges and comprehension loops."""
    __tablename__ = "communications"

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
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("conversation_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    sender: Mapped[str] = mapped_column(String(32), nullable=False) # "ai_coordinator", "patient", "human_coordinator"
    channel: Mapped[str] = mapped_column(String(32), default="sms") # "sms", "whatsapp", "in_app_chat"
    language: Mapped[str] = mapped_column(String(16), default="en") # "en", "ta", "mixed"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    translated_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Acknowledgement & Comprehension Tracking
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledgement_details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    care_case: Mapped["CareCase"] = relationship("CareCase", back_populates="communications")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="communications")
    session: Mapped[Optional["ConversationSession"]] = relationship("ConversationSession", back_populates="communications")

    def __repr__(self) -> str:
        return f"<Communication from {self.sender} via {self.channel} ({self.language})>"
