"""
CareBridge AI Workflow Conditional Edges
Deterministic routing functions governing transitions across the 11 nodes.
Guarantees:
- No infinite loops
- Safe exits to checkpointer while awaiting patient or clinical events
- Clear clinical safety boundaries
"""

import uuid
from typing import Literal
from app.workflows.state import CareBridgeState
from app.database.session import get_sync_db
from app.models import CareCase, Appointment, Referral, Communication


def route_entry(state: CareBridgeState) -> str:
    """
    Intelligently routes entry from START to the appropriate lifecycle node.
    Enables direct resumption when external events, staff approvals, or scheduler checks arrive.
    """
    # 1. Explicit next step target
    target = state.get("next_step")
    if target and target in [
        "create_case", "select_approved_pathway", "draft_patient_communication",
        "record_acknowledgement", "coordinate_referral", "coordinate_appointment",
        "monitor_case", "detect_dropoff", "recovery_agent", "escalation", "verify_closure"
    ]:
        return target

    # 2. Closure authorization or verification requested
    if state.get("appointment_attended") or state.get("human_decision") or state.get("closure_checklist"):
        return "verify_closure"

    # 3. Dropoff evaluation or stalled case
    if state.get("dropoff_risk") or state.get("is_stalled"):
        return "detect_dropoff"

    # 4. Check existing case state in database
    case_id_str = state.get("case_id")
    if case_id_str:
        with get_sync_db() as db:
            try:
                c_uuid = uuid.UUID(case_id_str)
                case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
                if case:
                    if case.status in ("closed", "care_completed"):
                        return "verify_closure"
                    if case.status in ("ESCALATED", "UNASSIGNED_ESCALATED"):
                        return "escalation"
                    app = db.query(Appointment).filter(Appointment.case_id == c_uuid).first()
                    if app and app.status == "attended":
                        return "verify_closure"
                    if app:
                        return "monitor_case"
                    ref = db.query(Referral).filter(Referral.case_id == c_uuid).first()
                    if ref:
                        return "coordinate_appointment"
                    if case.case_context and case.case_context.get("patient_understanding_confirmed"):
                        return "coordinate_referral"
                    comm = db.query(Communication).filter(Communication.case_id == c_uuid).first()
                    if comm:
                        return "record_acknowledgement"
                    if case.clinical_pathway and case.clinical_pathway != "general_screening_followup":
                        return "draft_patient_communication"
                    return "select_approved_pathway"
            except Exception:
                pass

    return "create_case"


def route_after_acknowledgement(state: CareBridgeState) -> Literal["detect_dropoff", "coordinate_referral", "end"]:
    """
    Routes based on patient response to notification.
    - If confirmed: proceeds to referral and appointment coordination.
    - If dropoff flagged: routes to dropoff detection.
    - Otherwise: safely pauses at END awaiting patient message.
    """
    if state.get("patient_acknowledged", False):
        return "coordinate_referral"
    elif state.get("dropoff_risk", False):
        return "detect_dropoff"
    # Waiting for patient reply via SMS/portal
    return "end"


def route_after_monitor(state: CareBridgeState) -> Literal["verify_closure", "detect_dropoff", "end"]:
    """
    Routes based on ongoing monitoring and case progress.
    - If attended or evidence ready: attempts verified closure.
    - If stalled or SLA warning: routes to dropoff detection.
    - Otherwise: safely exits to wait for appointment date or external event.
    """
    if state.get("appointment_attended", False) or state.get("closure_checklist"):
        return "verify_closure"
    if state.get("is_stalled", False) or state.get("sla_status") in ("warning", "breached"):
        return "detect_dropoff"
    return "end"


def route_after_dropoff(state: CareBridgeState) -> Literal["escalation", "recovery_agent", "monitor_case"]:
    """
    Routes evaluated dropoff cases.
    - If recovery attempts exhausted (>= 3) or SLA breached: escalates immediately.
    - If dropoff risk present: initiates recovery playbook.
    - Else: returns to monitoring.
    """
    if state.get("dropoff_risk", False):
        attempts = state.get("recovery_attempts", 0)
        sla_status = state.get("sla_status", "normal")
        reasons = state.get("dropoff_reasons", [])

        if attempts >= 3 or sla_status == "breached" or "unowned_case_risk" in reasons:
            return "escalation"
        return "recovery_agent"

    return "monitor_case"


def route_after_closure(state: CareBridgeState) -> Literal["end"]:
    """
    All closure outcomes exit safely to END.
    If closure was verified, case is closed.
    If human approval is pending, state is saved in checkpointer awaiting clinical resume.
    """
    return "end"
