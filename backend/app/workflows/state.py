"""
CareBridge AI Workflow State Schema
Defines the strongly-typed state for the 11-node LangGraph Care Coordination StateGraph.
"""

from typing import List, Dict, Any, Optional, TypedDict, Annotated
import operator
from pydantic import BaseModel, Field


class InferredDropoffReason(BaseModel):
    reason_code: str = Field(description="e.g. 'unacknowledged_outreach', 'missed_appointment', 'fear_anxiety', 'transportation_barrier'")
    severity: str = Field(description="'low', 'medium', 'high'")
    details: str = Field(description="Contextual explanation of why dropoff occurred")


class ClosureChecklist(BaseModel):
    diagnostic_resolution_completed: bool = False
    all_tasks_completed: bool = False
    clinical_signoff_verified: bool = False
    barriers_resolved: bool = False
    coordinator_concurrence: bool = False

    @property
    def is_fully_satisfied(self) -> bool:
        return (
            self.diagnostic_resolution_completed
            and self.all_tasks_completed
            and self.clinical_signoff_verified
            and self.barriers_resolved
            and self.coordinator_concurrence
        )


class CareBridgeState(TypedDict):
    """
    Strongly-typed state dictionary passed across all 11 nodes of the
    CareBridge closed-loop care coordination StateGraph.
    """
    # Core Entity Identifiers
    case_id: str
    patient_id: str
    screening_result_id: Optional[str]
    current_owner_id: Optional[str]

    # Lifecycle & Pathway Tracking
    status: str
    clinical_pathway: Optional[str]
    priority: str

    # Deterministic SLA Tracking
    sla_start_time: Optional[str]
    sla_deadline: Optional[str]
    sla_status: str # "normal", "warning", "breached"

    # Patient Outreach & Acknowledgement
    patient_language: str
    latest_patient_message: Optional[str]
    drafted_communication: Optional[str]
    patient_acknowledged: bool
    acknowledgement_channel: Optional[str]
    acknowledgement_timestamp: Optional[str]

    # Inter-Facility Referral
    referral_id: Optional[str]
    referral_status: Optional[str]
    target_facility: Optional[str]

    # Diagnostic Appointment Coordination
    appointment_id: Optional[str]
    appointment_status: Optional[str] # "booked", "confirmed", "attended", "no_show", "cancelled", "rescheduled"
    scheduled_appointment_time: Optional[str]
    appointment_attended: bool

    # Progress Monitoring & Inactivity
    is_stalled: bool
    days_inactive: float

    # Dropoff Detection & Proactive Recovery
    dropoff_risk: bool
    dropoff_reasons: List[str]
    recovery_attempts: int
    recovery_strategy: Optional[str]

    # Escalation
    escalation_level: Optional[str] # None, "standard", "critical"
    escalation_reason: Optional[str]

    # Human-in-the-Loop Clinical Verification & Closure
    requires_human_approval: bool
    approval_type: Optional[str] # "clinical_closure_signoff", "override_escalation"
    human_decision: Optional[str] # "pending", "approved", "rejected"
    closure_checklist: Optional[Dict[str, bool]]
    closure_verified: bool

    # Execution Graph Navigation
    workflow_phase: str
    next_step: Optional[str]

    # Persistent Append-Only Audit & Error Channels
    audit_log: Annotated[List[Dict[str, Any]], operator.add]
    errors: Annotated[List[str], operator.add]
