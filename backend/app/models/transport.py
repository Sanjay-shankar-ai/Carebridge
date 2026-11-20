"""
Transport Request and Conversation Flow State models (AI behaviours B2/B3).
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Text, DateTime, Boolean, Integer, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid
from app.database.session import Base, TimestampedUUIDMixin

TRANSPORT_STATUSES = ("REQUESTED", "CONFIRMED", "CANCELLED", "FAILED")


class TransportRequest(Base, TimestampedUUIDMixin):
    """A patient ride request linked to a specific appointment version.

    Status moves REQUESTED -> CONFIRMED only through a coordinator (or transport integration).
    """
    __tablename__ = "transport_requests"

    appointment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    appointment_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("care_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pickup_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pickup_address: Mapped[str] = mapped_column(Text, nullable=False)
    companion: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="REQUESTED", index=True, nullable=False)
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    confirmed_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)


class ConversationFlowState(Base, TimestampedUUIDMixin):
    """Per (conversation, user, role) state for multi-turn behaviour flows (e.g. cancellation WHY step)."""
    __tablename__ = "conversation_flow_states"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversation_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
