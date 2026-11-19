"""
CareBridge Doctor Subgraph Conditional Edges
Deterministic routing functions governing transitions in the Doctor workflow.
Guarantees:
- No infinite loops
- Unauthorized doctors are blocked at the gate
- Intent-based routing to appropriate management nodes
"""

from typing import Literal
from app.workflows.doctor_state import DoctorState


def route_after_doctor_auth(state: DoctorState) -> Literal["doctor_context_retrieval", "doctor_response"]:
    """
    Gates unauthorized doctors to response (blocked).
    Authorized doctors proceed to context retrieval.
    """
    if state.get("is_authorized", False):
        return "doctor_context_retrieval"
    return "doctor_response"


def route_doctor_intent(state: DoctorState) -> str:
    """
    Routes from context retrieval to the appropriate management node
    based on the parsed doctor intent.
    """
    intent = state.get("doctor_intent", "review_case")

    intent_to_node = {
        "review_case": "doctor_case_review",
        "accept_referral": "referral_management",
        "reject_referral": "referral_management",
        "reroute_referral": "referral_management",
        "cancel_appointment": "appointment_management",
        "reschedule_appointment": "appointment_management",
        "confirm_appointment": "appointment_management",
        "record_consultation": "consultation_management",
        "clinical_decision": "clinical_decision_review",
        "schedule_followup": "followup_management",
        "close_case": "closure_review",
        "general_query": "doctor_case_review",
    }

    return intent_to_node.get(intent, "doctor_case_review")
