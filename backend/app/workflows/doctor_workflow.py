"""
CareBridge Doctor Subgraph Workflow
Assembled LangGraph StateGraph connecting all 11 doctor nodes with intent-based routing.
Integrated into the existing CareBridge Supervisor architecture.
"""

import uuid
import logging
from typing import Dict, Any, Optional

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.workflows.doctor_state import DoctorState
from app.workflows.checkpointer import get_workflow_checkpointer, get_thread_config
from app.workflows.doctor_nodes import (
    doctor_intake_node,
    doctor_auth_check_node,
    doctor_context_retrieval_node,
    doctor_case_review_node,
    referral_management_node,
    appointment_management_node,
    consultation_management_node,
    clinical_decision_review_node,
    followup_management_node,
    closure_review_node,
    doctor_response_node,
)
from app.workflows.doctor_edges import (
    route_after_doctor_auth,
    route_doctor_intent,
)

logger = logging.getLogger("carebridge.workflows.doctor_workflow")


def create_doctor_workflow(checkpointer: Optional[BaseCheckpointSaver] = None):
    """
    Assembles and compiles the 11-node Doctor Subgraph.

    Graph structure:
      START → doctor_intake → doctor_auth_check
                                → (blocked → doctor_response → END)
                                → doctor_context_retrieval → route_doctor_intent
                                    → doctor_case_review → doctor_response → END
                                    → referral_management → doctor_response → END
                                    → appointment_management → doctor_response → END
                                    → consultation_management → doctor_response → END
                                    → clinical_decision_review → doctor_response → END
                                    → followup_management → doctor_response → END
                                    → closure_review → doctor_response → END
    """
    workflow = StateGraph(DoctorState)

    # 1. Register the 11 Doctor Nodes
    workflow.add_node("doctor_intake", doctor_intake_node)
    workflow.add_node("doctor_auth_check", doctor_auth_check_node)
    workflow.add_node("doctor_context_retrieval", doctor_context_retrieval_node)
    workflow.add_node("doctor_case_review", doctor_case_review_node)
    workflow.add_node("referral_management", referral_management_node)
    workflow.add_node("appointment_management", appointment_management_node)
    workflow.add_node("consultation_management", consultation_management_node)
    workflow.add_node("clinical_decision_review", clinical_decision_review_node)
    workflow.add_node("followup_management", followup_management_node)
    workflow.add_node("closure_review", closure_review_node)
    workflow.add_node("doctor_response", doctor_response_node)

    # 2. Linear: START → intake → auth_check
    workflow.add_edge(START, "doctor_intake")
    workflow.add_edge("doctor_intake", "doctor_auth_check")

    # 3. Auth gate: authorized → context_retrieval, blocked → response
    workflow.add_conditional_edges(
        "doctor_auth_check",
        route_after_doctor_auth,
        {
            "doctor_context_retrieval": "doctor_context_retrieval",
            "doctor_response": "doctor_response",
        }
    )

    # 4. Intent-based routing from context retrieval
    workflow.add_conditional_edges(
        "doctor_context_retrieval",
        route_doctor_intent,
        {
            "doctor_case_review": "doctor_case_review",
            "referral_management": "referral_management",
            "appointment_management": "appointment_management",
            "consultation_management": "consultation_management",
            "clinical_decision_review": "clinical_decision_review",
            "followup_management": "followup_management",
            "closure_review": "closure_review",
        }
    )

    # 5. All action nodes → doctor_response → END
    for node in [
        "doctor_case_review", "referral_management", "appointment_management",
        "consultation_management", "clinical_decision_review",
        "followup_management", "closure_review"
    ]:
        workflow.add_edge(node, "doctor_response")

    workflow.add_edge("doctor_response", END)

    # Compile with checkpointer
    cp = checkpointer or get_workflow_checkpointer()
    return workflow.compile(checkpointer=cp)


def run_doctor_workflow(
    doctor_id: str,
    message: str,
    case_id: Optional[str] = None,
    cancellation_reason: Optional[str] = None,
    consultation_notes: Optional[str] = None,
    clinical_decision: Optional[Dict[str, Any]] = None,
    followup_plan: Optional[Dict[str, Any]] = None,
    closure_decision: Optional[str] = None,
    closure_evidence_summary: Optional[str] = None,
    referral_reason: Optional[str] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None
) -> Dict[str, Any]:
    """
    Executes the Doctor Subgraph workflow for a single doctor interaction.
    Uses a unique thread_id per invocation.
    """
    thread_id = f"doctor-{doctor_id}-{uuid.uuid4().hex[:8]}"
    config = get_thread_config(thread_id)
    graph = create_doctor_workflow(checkpointer=checkpointer)

    initial_state: DoctorState = {
        "doctor_id": doctor_id,
        "doctor_message": message,
        "doctor_intent": None,
        "intent_confidence": None,
        "case_id": case_id,
        "patient_id": None,
        "is_authorized": False,
        "auth_failure_reason": None,
        "case_context": None,
        "patient_context": None,
        "screening_context": None,
        "referral_action": None,
        "referral_reason": referral_reason,
        "appointment_action": None,
        "cancellation_reason": cancellation_reason,
        "consultation_notes": consultation_notes,
        "clinical_decision": clinical_decision,
        "followup_plan": followup_plan,
        "closure_decision": closure_decision,
        "closure_evidence_summary": closure_evidence_summary,
        "replacement_requires_dual_acceptance": False,
        "response_message": None,
        "workflow_phase": "start",
        "next_step": None,
        "audit_log": [],
        "errors": [],
    }

    result = graph.invoke(initial_state, config=config)
    return result
