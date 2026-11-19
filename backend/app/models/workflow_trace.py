"""
CareBridge Workflow Execution Trace Relational Model (Phase 8)
Captures granular step-by-step telemetry, node durations, input/output summaries,
failure contexts, and coordinator-readable human explanations for long-running workflows.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import String, Text, DateTime, Integer, Float, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from app.database.session import Base, TimestampedUUIDMixin


class WorkflowExecutionTrace(Base, TimestampedUUIDMixin):
    """
    Granular execution trace capturing node-level telemetry and coordinator-readable explanations.
    """
    __tablename__ = "workflow_execution_traces"

    case_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("care_cases.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    thread_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    workflow_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    node_name: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    step_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Status & Telemetry
    status: Mapped[str] = mapped_column(
        String(32),
        default="success",
        index=True,
        nullable=False
    ) # "started", "success", "failed", "interrupted", "retried"
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    input_summary: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    output_summary: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Coordinator Observability: Plain-language human-readable description
    coordinator_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False
    )

    # Tracing & Actor Attribution (Phase 6)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    workflow_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    intent: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    routing_decision: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    selected_agent: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    tool_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    domain_action: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    db_result: Mapped[Optional[str]] = mapped_column(String(32), default="ok", nullable=True)
    event_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    notification_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    lifecycle_transition: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    care_case: Mapped[Optional["CareCase"]] = relationship("CareCase", back_populates="workflow_traces")

    def __repr__(self) -> str:
        return (
            f"<WorkflowTrace {self.workflow_name}::{self.node_name} "
            f"Run={self.run_id[:8]} Status={self.status} ({self.duration_ms:.1f}ms)>"
        )
