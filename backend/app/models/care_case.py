"""
Care Case and Task Relational Models
The core aggregate root representing the end-to-end closed-loop care journey.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import String, Integer, DateTime, JSON, ForeignKey, Text, Boolean, event, select
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from app.database.session import Base, TimestampedUUIDMixin


class CareCase(Base, TimestampedUUIDMixin):
    __tablename__ = "care_cases"

    case_number: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    screening_result_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("screening_results.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )
    current_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("case_owners.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # State Machine & Pathway Tracking
    status: Mapped[str] = mapped_column(
        String(64),
        default="result_received",
        index=True,
        nullable=False
    )
    clinical_pathway: Mapped[str] = mapped_column(String(128), default="general_screening_followup", nullable=False)
    priority: Mapped[str] = mapped_column(String(32), default="standard", index=True) # "standard", "urgent", "critical"

    # SLA Clocks
    sla_start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    sla_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sla_status: Mapped[str] = mapped_column(String(32), default="normal", index=True) # "normal", "warning", "breached"

    # Optimistic Concurrency Control (Phase 6)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Dynamic Case Memory (Structured JSON)
    case_context: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {
            "inferred_barriers": [],
            "recovery_attempts": 0,
            "last_recovery_strategy": None,
            "patient_understanding_confirmed": False,
            "notes": []
        }
    )

    # Relationships
    patient: Mapped["Patient"] = relationship("Patient", back_populates="care_cases")
    screening_result: Mapped["ScreeningResult"] = relationship("ScreeningResult", back_populates="care_case")
    current_owner: Mapped[Optional["CaseOwner"]] = relationship("CaseOwner", back_populates="owned_cases")
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="care_case", cascade="all, delete-orphan")
    referrals: Mapped[List["Referral"]] = relationship("Referral", back_populates="care_case", cascade="all, delete-orphan")
    appointments: Mapped[List["Appointment"]] = relationship("Appointment", back_populates="care_case", cascade="all, delete-orphan")
    communications: Mapped[List["Communication"]] = relationship("Communication", back_populates="care_case", cascade="all, delete-orphan")
    case_events: Mapped[List["CaseEvent"]] = relationship("CaseEvent", back_populates="care_case", cascade="all, delete-orphan")
    closure_evidences: Mapped[List["ClosureEvidence"]] = relationship("ClosureEvidence", back_populates="care_case", cascade="all, delete-orphan")
    ownership_history: Mapped[List["CaseOwnershipHistory"]] = relationship("CaseOwnershipHistory", back_populates="care_case", cascade="all, delete-orphan")
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="care_case")
    workflow_traces: Mapped[List["WorkflowExecutionTrace"]] = relationship("WorkflowExecutionTrace", back_populates="care_case", cascade="all, delete-orphan")
    doctor_assignments: Mapped[List["DoctorAssignment"]] = relationship("DoctorAssignment", back_populates="care_case", cascade="all, delete-orphan")
    lifecycle_stage_records: Mapped[List["CaseLifecycleStage"]] = relationship("CaseLifecycleStage", back_populates="care_case", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<CareCase {self.case_number} - Status: {self.status} (SLA: {self.sla_status})>"


class Task(Base, TimestampedUUIDMixin):
    """FHIR-aligned Task Model representing work items along the care journey."""
    __tablename__ = "tasks"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("care_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False) # "patient_outreach", "referral_routing", "recovery_play", "clinical_review"
    assigned_to_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("case_owners.id", ondelete="SET NULL"),
        nullable=True
    )
    assigned_role: Mapped[str] = mapped_column(String(64), default="ai_coordinator") # "ai_coordinator", "care_coordinator", "clinician"
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True) # "pending", "in_progress", "completed", "cancelled", "overdue"
    priority: Mapped[str] = mapped_column(String(32), default="standard", index=True) # "standard", "urgent", "critical"
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    completed_by_role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    completion_evidence: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)

    # Relationships
    care_case: Mapped["CareCase"] = relationship("CareCase", back_populates="tasks")
    patient: Mapped[Optional["Patient"]] = relationship("Patient", back_populates="tasks")
    assigned_to: Mapped[Optional["CaseOwner"]] = relationship("CaseOwner", back_populates="assigned_tasks")

    @property
    def due_at(self) -> datetime:
        return self.due_date

    @property
    def responsible_role(self) -> str:
        return self.assigned_role

    @property
    def responsible_user_id(self) -> Optional[uuid.UUID]:
        return self.assigned_to_id

    @property
    def task_metadata(self) -> Dict[str, Any]:
        return self.completion_evidence or {}

    def __repr__(self) -> str:
        return f"<Task {self.title} ({self.status}) Assigned to: {self.assigned_role}>"


@event.listens_for(Task, "before_insert")
def set_task_patient_id(mapper, connection, target):
    """Guarantees patient_id is automatically backfilled from CareCase if omitted."""
    if not target.patient_id and target.case_id:
        try:
            row = connection.execute(
                select(CareCase.patient_id).where(CareCase.id == target.case_id)
            ).first()
            if row and row[0]:
                target.patient_id = row[0]
        except Exception:
            pass


class CaseOwnershipHistory(Base, TimestampedUUIDMixin):
    """Tracks the continuous, unbroken chain of case coordinator ownership from intake to closure."""
    __tablename__ = "case_ownership_history"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("care_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    previous_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("case_owners.id", ondelete="SET NULL"),
        nullable=True
    )
    new_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("case_owners.id", ondelete="SET NULL"),
        nullable=True
    )
    transferred_by: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Relationships
    care_case: Mapped["CareCase"] = relationship("CareCase", back_populates="ownership_history")
    previous_owner: Mapped[Optional["CaseOwner"]] = relationship("CaseOwner", foreign_keys=[previous_owner_id])
    new_owner: Mapped[Optional["CaseOwner"]] = relationship("CaseOwner", foreign_keys=[new_owner_id])

    def __repr__(self) -> str:
        return f"<CaseOwnershipHistory Case={self.case_id} Owner={self.new_owner_id} Active={self.is_active}>"
