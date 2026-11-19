"""
CareBridge Doctor Subgraph State Schema
Defines the strongly-typed state for the Doctor Subgraph within the LangGraph Supervisor.
Integrated with the existing CareBridge architecture — NOT a separate disconnected system.
"""

from typing import List, Dict, Any, Optional, TypedDict, Annotated
import operator


# Valid doctor intents recognized by the intake node
DOCTOR_INTENTS = [
    "review_case",
    "accept_referral",
    "reject_referral",
    "reroute_referral",
    "cancel_appointment",
    "reschedule_appointment",
    "confirm_appointment",
    "record_consultation",
    "clinical_decision",
    "schedule_followup",
    "close_case",
    "general_query",
]


class DoctorState(TypedDict):
    """
    Strongly-typed state dictionary for the Doctor Subgraph.
    Shares database models and tools with the Care Coordination workflow.
    """
    # Doctor Identity
    doctor_id: str                          # CaseOwner UUID (role=specialist/primary_physician)
    doctor_message: str                     # Natural language input from doctor

    # Parsed Intent
    doctor_intent: Optional[str]            # One of DOCTOR_INTENTS
    intent_confidence: Optional[str]        # "high", "medium", "low"

    # Case & Patient Context
    case_id: Optional[str]
    patient_id: Optional[str]

    # Authorization
    is_authorized: bool
    auth_failure_reason: Optional[str]

    # Retrieved Context
    case_context: Optional[Dict[str, Any]]      # Case memory snapshot
    patient_context: Optional[Dict[str, Any]]   # Patient memory snapshot
    screening_context: Optional[Dict[str, Any]] # Screening result data

    # Action-Specific Fields
    referral_action: Optional[str]              # "accept" / "reject" / "reroute"
    referral_reason: Optional[str]              # Rejection/reroute reason
    appointment_action: Optional[str]           # "cancel" / "reschedule" / "confirm"
    cancellation_reason: Optional[str]          # Mandatory for appointment cancellation
    consultation_notes: Optional[str]           # Clinical consultation text
    clinical_decision: Optional[Dict[str, Any]] # Diagnosis impression, treatment recommendation
    followup_plan: Optional[Dict[str, Any]]     # Follow-up schedule and tasks
    closure_decision: Optional[str]             # "approved" / "rejected"
    closure_evidence_summary: Optional[str]     # Clinical evidence for closure

    # Doctor needs both doctor and patient acceptance for replacement appointments
    replacement_requires_dual_acceptance: bool

    # Response
    response_message: Optional[str]             # Formatted doctor response

    # Graph Navigation
    workflow_phase: str
    next_step: Optional[str]

    # Persistent Append-Only Channels
    audit_log: Annotated[List[Dict[str, Any]], operator.add]
    errors: Annotated[List[str], operator.add]
