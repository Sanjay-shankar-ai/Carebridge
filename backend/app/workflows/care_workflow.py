"""
CareBridge End-to-End Care Coordination Workflow
Compiled LangGraph StateGraph connecting all 11 nodes with persistent checkpointing,
thread-level case_id isolation, conditional routing, and human-in-the-loop clinical gates.
"""

import uuid
import logging
from typing import Dict, Any, Optional

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.workflows.state import CareBridgeState
from app.workflows.checkpointer import get_workflow_checkpointer, get_thread_config
from app.workflows.nodes import (
    create_case_node,
    select_approved_pathway_node,
    draft_patient_communication_node,
    record_acknowledgement_node,
    coordinate_referral_node,
    coordinate_appointment_node,
    monitor_case_node,
    detect_dropoff_node,
    recovery_agent_node,
    escalation_node,
    verify_closure_node,
)
from app.workflows.edges import (
    route_entry,
    route_after_acknowledgement,
    route_after_monitor,
    route_after_dropoff,
    route_after_closure,
)

logger = logging.getLogger("carebridge.workflows.care_workflow")


def create_carebridge_workflow(checkpointer: Optional[BaseCheckpointSaver] = None):
    """
    Assembles and compiles the full 11-node CareBridge closed-loop coordination StateGraph.
    """
    workflow = StateGraph(CareBridgeState)

    # 1. Register the 11 Lifecycle Nodes
    workflow.add_node("create_case", create_case_node)
    workflow.add_node("select_approved_pathway", select_approved_pathway_node)
    workflow.add_node("draft_patient_communication", draft_patient_communication_node)
    workflow.add_node("record_acknowledgement", record_acknowledgement_node)
    workflow.add_node("coordinate_referral", coordinate_referral_node)
    workflow.add_node("coordinate_appointment", coordinate_appointment_node)
    workflow.add_node("monitor_case", monitor_case_node)
    workflow.add_node("detect_dropoff", detect_dropoff_node)
    workflow.add_node("recovery_agent", recovery_agent_node)
    workflow.add_node("escalation", escalation_node)
    workflow.add_node("verify_closure", verify_closure_node)

    # 2. Dynamic Entry Routing from START
    workflow.add_conditional_edges(
        START,
        route_entry,
        {
            "create_case": "create_case",
            "select_approved_pathway": "select_approved_pathway",
            "draft_patient_communication": "draft_patient_communication",
            "record_acknowledgement": "record_acknowledgement",
            "coordinate_referral": "coordinate_referral",
            "coordinate_appointment": "coordinate_appointment",
            "monitor_case": "monitor_case",
            "detect_dropoff": "detect_dropoff",
            "recovery_agent": "recovery_agent",
            "escalation": "escalation",
            "verify_closure": "verify_closure",
        }
    )
    workflow.add_edge("create_case", "select_approved_pathway")
    workflow.add_edge("select_approved_pathway", "draft_patient_communication")
    workflow.add_edge("draft_patient_communication", "record_acknowledgement")

    # 3. Conditional Decision: Acknowledgement & Dropoff Check
    workflow.add_conditional_edges(
        "record_acknowledgement",
        route_after_acknowledgement,
        {
            "coordinate_referral": "coordinate_referral",
            "detect_dropoff": "detect_dropoff",
            "end": END,
        }
    )

    workflow.add_edge("coordinate_referral", "coordinate_appointment")
    workflow.add_edge("coordinate_appointment", "monitor_case")

    # 4. Conditional Decision: Case Progress & Milestones
    workflow.add_conditional_edges(
        "monitor_case",
        route_after_monitor,
        {
            "verify_closure": "verify_closure",
            "detect_dropoff": "detect_dropoff",
            "end": END,
        }
    )

    # 5. Conditional Decision: Dropoff Triage & Escalation
    workflow.add_conditional_edges(
        "detect_dropoff",
        route_after_dropoff,
        {
            "escalation": "escalation",
            "recovery_agent": "recovery_agent",
            "monitor_case": "monitor_case",
        }
    )

    # 6. Safe Exits to Checkpointer (Never Infinite Loops)
    workflow.add_edge("recovery_agent", END)
    workflow.add_edge("escalation", END)
    workflow.add_edge("verify_closure", END)

    # Compile with persistent checkpointer
    cp = checkpointer or get_workflow_checkpointer()
    return workflow.compile(checkpointer=cp)


def run_carebridge_workflow(
    screening_result_id: str,
    case_id: Optional[str] = None,
    patient_id: Optional[str] = None,
    patient_acknowledged: bool = False,
    latest_patient_message: Optional[str] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None
) -> Dict[str, Any]:
    """
    Executes the CareBridge workflow starting from screening result intake.
    Uses case_id (or generated uuid) as the persistent thread identifier.
    """
    effective_case_id = case_id or str(uuid.uuid4())
    config = get_thread_config(effective_case_id)
    graph = create_carebridge_workflow(checkpointer=checkpointer)

    initial_state: CareBridgeState = {
        "case_id": effective_case_id,
        "patient_id": patient_id or "",
        "screening_result_id": screening_result_id,
        "current_owner_id": None,
        "status": "result_received",
        "clinical_pathway": None,
        "priority": "standard",
        "sla_start_time": None,
        "sla_deadline": None,
        "sla_status": "normal",
        "patient_language": "en",
        "latest_patient_message": latest_patient_message,
        "drafted_communication": None,
        "patient_acknowledged": patient_acknowledged,
        "acknowledgement_channel": None,
        "acknowledgement_timestamp": None,
        "referral_id": None,
        "referral_status": None,
        "target_facility": None,
        "appointment_id": None,
        "appointment_status": None,
        "scheduled_appointment_time": None,
        "appointment_attended": False,
        "is_stalled": False,
        "days_inactive": 0.0,
        "dropoff_risk": False,
        "dropoff_reasons": [],
        "recovery_attempts": 0,
        "recovery_strategy": None,
        "escalation_level": None,
        "escalation_reason": None,
        "requires_human_approval": False,
        "approval_type": None,
        "human_decision": None,
        "closure_checklist": None,
        "closure_verified": False,
        "workflow_phase": "start",
        "next_step": None,
        "audit_log": [],
        "errors": []
    }

    result = graph.invoke(initial_state, config=config)
    return result


def resume_carebridge_workflow(
    case_id: str,
    event_updates: Dict[str, Any],
    checkpointer: Optional[BaseCheckpointSaver] = None
) -> Dict[str, Any]:
    """
    Resumes an existing workflow case from its checkpoint after an external event:
    - Inbound patient message or acknowledgement
    - Specialist referral acceptance
    - Appointment attendance verification
    - Clinician human-in-the-loop approval
    """
    config = get_thread_config(case_id)
    graph = create_carebridge_workflow(checkpointer=checkpointer)

    # Resume graph execution with event updates applied to existing thread state
    result = graph.invoke(event_updates, config=config)
    return result
