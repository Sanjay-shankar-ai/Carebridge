"""
CareBridge Care Recovery Agent State Definitions (Phase 7)
Defines strongly-typed State schemas for the multi-source context retrieval,
fact vs assumption reasoning, dynamic playbooks, and adaptive recovery cycles.
"""

from typing import TypedDict, List, Dict, Any, Optional


class RecoveryState(TypedDict, total=False):
    """
    State maintained across the Care Recovery Agent's LangGraph reasoning cycle.
    """
    # Core Identifiers
    case_id: str
    patient_id: str
    actor_role: str

    # 1. Stalled Detection Signals
    stalled_signals: List[Dict[str, Any]]
    is_stalled: bool

    # 2. Multi-Source Context (8 Distinct Dimensions)
    # Includes: case_history, patient_conversations, previous_attempts,
    # referral_status, appointment_history, patient_preferences,
    # outstanding_tasks, sla_context
    context: Dict[str, Any]

    # 3. Reasoning: Facts vs Assumptions
    known_facts: List[Dict[str, Any]]
    assumptions: List[Dict[str, Any]]
    needs_clarification: bool
    clarification_prompt: Optional[str]
    clarification_sent: bool

    # 4. Detected Barriers & Attempts
    detected_barriers: List[str]
    recovery_attempts: int

    # 5. Playbook Selection & Action Planning
    selected_playbook: str
    action_plan: List[Dict[str, Any]]

    # 6. Tool Execution & Human Gates
    tool_actions_executed: List[Dict[str, Any]]
    requires_human_authorization: bool
    human_approval_request: Optional[Dict[str, Any]]

    # 7. Observation & Adaptation
    observation: Dict[str, Any]
    outcome_status: str  # "clarification_pending", "recovery_in_progress", "recovered", "escalated", "coordinator_intervening"

    # 8. Ownership Continuity & Governance
    coordinator_notified: bool
    accountable_owner_id: Optional[str]
    accountable_owner_name: Optional[str]

    # 9. Audit & Telemetry
    audit_entries: List[Dict[str, Any]]
    errors: List[str]
