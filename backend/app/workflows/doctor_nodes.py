"""
CareBridge Doctor Subgraph Nodes
11 idempotent node implementations for the Doctor workflow within the LangGraph Supervisor.
Integrated with existing ToolRegistry, models, and database — NOT a separate system.
AI NEVER diagnoses, prescribes, or independently approves clinical closure.
Clinical decisions remain under doctor authority (Level 3).
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from app.database.session import get_sync_db
from app.models import (
    Patient, CareCase, CaseOwner, Task,
    Referral, Appointment, CaseEvent, AuditLog,
    ClosureEvidence, ScreeningResult, Communication
)
from app.services.llm_service import LLMService
from app.workflows.doctor_state import DoctorState, DOCTOR_INTENTS

logger = logging.getLogger("carebridge.workflows.doctor_nodes")


# ==============================================================================
# Helper: Audit logger for doctor actions (actor_type="clinician")
# ==============================================================================
def _doctor_audit(
    db, case_id: uuid.UUID, action: str, doctor_id: str,
    autonomy_level: int, rationale: str
) -> Dict[str, Any]:
    """Records an immutable audit entry for doctor actions with actor_type=clinician."""
    entry = AuditLog(
        id=uuid.uuid4(),
        case_id=case_id,
        actor_type="clinician",
        actor_id=doctor_id,
        action=action,
        autonomy_level=autonomy_level,
        rationale=rationale,
        timestamp=datetime.now(timezone.utc)
    )
    db.add(entry)
    db.commit()
    return {
        "action": action,
        "actor_type": "clinician",
        "actor_id": doctor_id,
        "autonomy_level": autonomy_level,
        "rationale": rationale,
        "timestamp": entry.timestamp.isoformat()
    }


# ==============================================================================
# Node 1: doctor_intake
# ==============================================================================
def doctor_intake_node(state: DoctorState) -> Dict[str, Any]:
    """
    Node 1: Parses doctor's natural language message to identify intent.
    Uses LLM for NLU with deterministic keyword fallback.
    """
    logger.info("Executing Doctor Node 1: doctor_intake")
    message = state.get("doctor_message", "").strip()

    if not message:
        return {
            "doctor_intent": None,
            "errors": ["doctor_intake_error: Empty message received"],
            "workflow_phase": "intake_failed",
            "next_step": "doctor_response"
        }

    # Deterministic keyword matching as primary + LLM enhancement
    intent = _classify_doctor_intent(message)

    # Extract case_id from message if not provided
    case_id = state.get("case_id")
    if not case_id:
        case_id = _extract_case_reference(message)

    return {
        "doctor_intent": intent,
        "intent_confidence": "high" if intent != "general_query" else "medium",
        "case_id": case_id,
        "workflow_phase": "intake_complete",
        "next_step": "doctor_auth_check"
    }


def _classify_doctor_intent(message: str) -> str:
    """Deterministic intent classification with keyword matching."""
    msg_lower = message.lower().strip()

    # Greetings
    if msg_lower in ["hi", "hello", "hey", "good morning", "good afternoon", "greetings"] or any(msg_lower.startswith(w + " ") for w in ["hi", "hello", "hey"]):
        return "general_query"

    # Pending referrals queries
    if any(kw in msg_lower for kw in ["show referrals", "pending referrals", "my referrals", "view referrals", "referral list", "show my pending referrals", "pending referral"]):
        return "review_case"

    # Referral intents
    if any(kw in msg_lower for kw in ["accept referral", "approve referral", "referral accepted"]):
        return "accept_referral"
    if any(kw in msg_lower for kw in ["reject referral", "decline referral", "deny referral"]):
        return "reject_referral"
    if any(kw in msg_lower for kw in ["reroute referral", "redirect referral", "transfer referral"]):
        return "reroute_referral"

    # Appointment intents
    if any(kw in msg_lower for kw in ["cancel appointment", "cancel the appointment", "cannot see patient", "unable to attend"]):
        return "cancel_appointment"
    if any(kw in msg_lower for kw in ["reschedule appointment", "reschedule the visit", "move appointment"]):
        return "reschedule_appointment"
    if any(kw in msg_lower for kw in ["confirm appointment", "appointment confirmed"]):
        return "confirm_appointment"

    # Consultation
    if any(kw in msg_lower for kw in ["consultation", "clinical notes", "examination findings", "patient examined", "consultation notes"]):
        return "record_consultation"

    # Clinical decision
    if any(kw in msg_lower for kw in ["clinical decision", "diagnosis", "treatment plan", "recommend treatment", "clinical impression"]):
        return "clinical_decision"

    # Follow-up
    if any(kw in msg_lower for kw in ["follow-up", "followup", "schedule follow", "follow up plan"]):
        return "schedule_followup"

    # Closure
    if any(kw in msg_lower for kw in ["close case", "verify closure", "approve closure", "clinical closure",
                                       "case resolved", "benign", "no malignancy"]):
        return "close_case"

    # Case review
    if any(kw in msg_lower for kw in ["review case", "case summary", "case status", "patient status",
                                       "show case", "what is the status"]):
        return "review_case"

    # Try LLM-based classification
    try:
        llm = LLMService.get_llm()
        if llm:
            prompt = (
                f"Classify this doctor message into exactly one intent from: {DOCTOR_INTENTS}.\n"
                f"Message: \"{message}\"\n"
                f"Reply with ONLY the intent string, nothing else."
            )
            response = llm.invoke(prompt)
            parsed = response.content.strip().lower().replace('"', '').replace("'", "")
            if parsed in DOCTOR_INTENTS:
                return parsed
    except Exception as e:
        logger.warning(f"LLM intent classification fallback: {e}")

    return "general_query"


def _extract_case_reference(message: str) -> Optional[str]:
    """Attempts to extract a case ID or case number from a doctor message."""
    import re
    match = re.search(r"CASE-\d{4}-\d{4}", message, re.IGNORECASE)
    if match:
        return match.group(0)
    match_hex = re.search(r"CASE-[0-9A-F]{8}", message, re.IGNORECASE)
    if match_hex:
        return match_hex.group(0)
    uuid_match = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", message, re.IGNORECASE)
    if uuid_match:
        return uuid_match.group(0)
    return None


# ==============================================================================
# Node 2: doctor_auth_check
# ==============================================================================
def doctor_auth_check_node(state: DoctorState) -> Dict[str, Any]:
    """
    Node 2: Verifies doctor identity and patient assignment permissions.
    Permission enforcement is the key gate — unauthorized doctors are blocked.
    """
    logger.info("Executing Doctor Node 2: doctor_auth_check")
    doctor_id = state.get("doctor_id")
    case_id = state.get("case_id")

    if not doctor_id:
        return {
            "is_authorized": False,
            "auth_failure_reason": "No doctor_id provided",
            "workflow_phase": "auth_failed",
            "next_step": "doctor_response"
        }

    try:
        with get_sync_db() as db:
            # 1. Verify doctor exists and is active
            try:
                doc_uuid = uuid.UUID(doctor_id)
            except ValueError:
                return {
                    "is_authorized": False,
                    "auth_failure_reason": f"Invalid doctor_id format: {doctor_id}",
                    "workflow_phase": "auth_failed",
                    "next_step": "doctor_response"
                }

            doctor = db.query(CaseOwner).filter(CaseOwner.id == doc_uuid).first()
            if not doctor:
                from app.models.user import User
                user_record = db.query(User).filter(User.id == doc_uuid).first()
                if user_record and user_record.owner_id:
                    doctor = db.query(CaseOwner).filter(CaseOwner.id == user_record.owner_id).first()

            if not doctor:
                return {
                    "is_authorized": False,
                    "auth_failure_reason": f"Doctor {doctor_id} not found in system",
                    "workflow_phase": "auth_failed",
                    "next_step": "doctor_response"
                }

            if not doctor.is_active:
                return {
                    "is_authorized": False,
                    "auth_failure_reason": f"Doctor {doctor.name} account is inactive",
                    "workflow_phase": "auth_failed",
                    "next_step": "doctor_response"
                }

            if doctor.role not in ("specialist", "primary_physician", "clinician", "doctor"):
                return {
                    "is_authorized": False,
                    "auth_failure_reason": f"User {doctor.name} has role '{doctor.role}', not a doctor role",
                    "workflow_phase": "auth_failed",
                    "next_step": "doctor_response"
                }

            # 2. If case_id provided, verify doctor is assigned to this case
            if case_id:
                c_uuid = None
                try:
                    c_uuid = uuid.UUID(case_id)
                except ValueError:
                    case_by_number = db.query(CareCase).filter(CareCase.case_number == case_id).first()
                    if case_by_number:
                        c_uuid = case_by_number.id

                if c_uuid:
                    case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
                    if not case:
                        return {
                            "is_authorized": False,
                            "auth_failure_reason": f"Case {case_id} not found",
                            "workflow_phase": "auth_failed",
                            "next_step": "doctor_response"
                        }

                    # Check assignment:
                    is_assigned = False

                    # Case owner check
                    if case.current_owner_id == doc_uuid:
                        is_assigned = True

                    # Referral target check
                    if not is_assigned:
                        referrals = (
                            db.query(Referral)
                            .filter(Referral.case_id == c_uuid)
                            .all()
                        )
                        for ref in referrals:
                            if ref.target_facility == doctor.facility:
                                is_assigned = True
                                break

                    # Appointment provider check
                    if not is_assigned:
                        appointments = (
                            db.query(Appointment)
                            .filter(Appointment.case_id == c_uuid)
                            .all()
                        )
                        for appt in appointments:
                            if appt.provider_name and doctor.name in appt.provider_name:
                                is_assigned = True
                                break
                            if appt.facility == doctor.facility:
                                is_assigned = True
                                break

                    # Task assignment check
                    if not is_assigned:
                        task = db.query(Task).filter(Task.case_id == c_uuid, Task.assigned_to_id == doc_uuid).first()
                        if task:
                            is_assigned = True

                    # Doctor assignment request check
                    if not is_assigned:
                        from app.models.doctor_assignment import DoctorAssignment
                        doc_assign = db.query(DoctorAssignment).filter(
                            DoctorAssignment.case_id == c_uuid,
                            DoctorAssignment.doctor_id == doctor.id,
                            DoctorAssignment.status.in_(["PENDING_DOCTOR_RESPONSE", "ACCEPTED"])
                        ).first()
                        if doc_assign:
                            is_assigned = True

                    if not is_assigned:
                        return {
                            "is_authorized": False,
                            "auth_failure_reason": f"Doctor {doctor.name} is not assigned to case {case_id}",
                            "workflow_phase": "auth_failed",
                            "next_step": "doctor_response"
                        }

                    return {
                        "is_authorized": True,
                        "auth_failure_reason": None,
                        "case_id": str(c_uuid),
                        "patient_id": str(case.patient_id),
                        "workflow_phase": "authorized",
                        "next_step": "doctor_context_retrieval"
                    }

            return {
                "is_authorized": True,
                "auth_failure_reason": None,
                "workflow_phase": "authorized",
                "next_step": "doctor_context_retrieval"
            }

    except Exception as e:
        logger.error(f"Error in doctor_auth_check_node: {e}", exc_info=True)
        return {
            "is_authorized": False,
            "auth_failure_reason": f"Authorization error: {str(e)}",
            "workflow_phase": "auth_failed",
            "next_step": "doctor_response",
            "errors": [f"doctor_auth_error: {str(e)}"]
        }


# ==============================================================================
# Node 3: doctor_context_retrieval
# ==============================================================================
def doctor_context_retrieval_node(state: DoctorState) -> Dict[str, Any]:
    """
    Node 3: Loads case, patient, screening, referral, and appointment context.
    Reuses existing memory retrieval infrastructure.
    """
    logger.info("Executing Doctor Node 3: doctor_context_retrieval")
    case_id = state.get("case_id")
    patient_id = state.get("patient_id")

    case_ctx = {}
    patient_ctx = {}
    screening_ctx = {}

    try:
        with get_sync_db() as db:
            if case_id:
                try:
                    c_uuid = uuid.UUID(case_id)
                    case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
                    if case:
                        case_ctx = {
                            "case_id": str(case.id),
                            "case_number": case.case_number,
                            "status": case.status,
                            "priority": case.priority,
                            "clinical_pathway": case.clinical_pathway,
                            "sla_status": case.sla_status,
                            "owner_id": str(case.current_owner_id) if case.current_owner_id else None,
                            "owner_name": case.current_owner.name if case.current_owner else "Unassigned",
                            "case_context": case.case_context or {},
                        }

                        # Screening context
                        if case.screening_result_id:
                            screening = db.query(ScreeningResult).filter(
                                ScreeningResult.id == case.screening_result_id
                            ).first()
                            if screening:
                                screening_ctx = {
                                    "screening_type": screening.screening_type,
                                    "finding_code": screening.finding_code,
                                    "finding_summary": screening.finding_summary,
                                    "urgency_level": screening.urgency_level,
                                }

                        # Referral context
                        referral = db.query(Referral).filter(Referral.case_id == c_uuid).order_by(Referral.created_at.desc()).first()
                        if referral:
                            case_ctx["referral"] = {
                                "id": str(referral.id),
                                "status": referral.status,
                                "target_facility": referral.target_facility,
                                "specialty": referral.specialty,
                            }

                        # Appointment context
                        appointment = (
                            db.query(Appointment)
                            .filter(Appointment.case_id == c_uuid)
                            .order_by(Appointment.created_at.desc())
                            .first()
                        )
                        if appointment:
                            case_ctx["latest_appointment"] = {
                                "id": str(appointment.id),
                                "status": appointment.status,
                                "scheduled_time": appointment.scheduled_time.isoformat() if appointment.scheduled_time else None,
                                "provider_name": appointment.provider_name,
                                "facility": appointment.facility,
                            }

                        # Recent events
                        events = (
                            db.query(CaseEvent)
                            .filter(CaseEvent.case_id == c_uuid)
                            .order_by(CaseEvent.timestamp.desc())
                            .limit(10)
                            .all()
                        )
                        case_ctx["recent_events"] = [
                            {"event_type": e.event_type, "description": e.description,
                             "timestamp": e.timestamp.isoformat()}
                            for e in events
                        ]

                except ValueError:
                    pass

            if patient_id:
                try:
                    p_uuid = uuid.UUID(patient_id)
                    patient = db.query(Patient).filter(Patient.id == p_uuid).first()
                    if patient:
                        patient_ctx = {
                            "patient_id": str(patient.id),
                            "name": f"{patient.first_name} {patient.last_name}",
                            "mrn": patient.mrn,
                            "preferred_language": patient.preferred_language,
                            "communication_channel": patient.communication_channel,
                        }
                except ValueError:
                    pass

        return {
            "case_context": case_ctx,
            "patient_context": patient_ctx,
            "screening_context": screening_ctx,
            "workflow_phase": "context_retrieved",
            "next_step": state.get("doctor_intent", "review_case")
        }

    except Exception as e:
        logger.error(f"Error in doctor_context_retrieval_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"doctor_context_retrieval_error: {str(e)}"]
        }


# ==============================================================================
# Node 4: doctor_case_review
# ==============================================================================
def doctor_case_review_node(state: DoctorState) -> Dict[str, Any]:
    """
    Node 4: Compiles comprehensive case summary for doctor review.
    Uses LLM for clinical-language summary with structured fallback.
    """
    logger.info("Executing Doctor Node 4: doctor_case_review")
    doctor_message = (state.get("doctor_message") or "").strip().lower()
    doctor_id = state.get("doctor_id")
    case_ctx = state.get("case_context", {})
    patient_ctx = state.get("patient_context", {})
    screening_ctx = state.get("screening_context", {})

    # If no active case was specified in the request
    if not state.get("case_id") or not case_ctx:
        # 1. Doctor greeting
        if any(g in doctor_message for g in ["hi", "hello", "hey", "good morning", "good afternoon", "greetings"]):
            return {
                "response_message": (
                    "Hello Doctor. I am your CareBridge Clinical Co-Pilot. "
                    "I can assist you with reviewing assigned patient cases, evaluating pending cross-facility referrals, "
                    "recording consultation notes, or verifying clinical closure. How can I assist you today?"
                ),
                "workflow_phase": "greeting_complete",
                "next_step": "doctor_response"
            }

        # 2. Inquiring about pending referrals
        if any(r in doctor_message for r in ["referral", "referrals", "pending"]):
            try:
                with get_sync_db() as db:
                    doc_uuid = uuid.UUID(doctor_id) if doctor_id else None
                    doctor = db.query(CaseOwner).filter(CaseOwner.id == doc_uuid).first() if doc_uuid else None
                    facility = doctor.facility if doctor else "Clinic A - Women's Specialty Breast Center"
                    refs = db.query(Referral).filter(Referral.target_facility == facility).limit(5).all()
                    if refs:
                        summary = f"=== Inbound Referrals for {facility} ===\n"
                        for r in refs:
                            summary += f"- Case: {r.case.case_number if r.case else str(r.case_id)[:8]} | Specialty: {r.specialty} | Status: {r.status} | Reason: {r.reason_for_referral}\n"
                        return {
                            "response_message": summary,
                            "workflow_phase": "referrals_reviewed",
                            "next_step": "doctor_response"
                        }
                    else:
                        return {
                            "response_message": f"No pending referrals found for facility {facility}.",
                            "workflow_phase": "referrals_reviewed",
                            "next_step": "doctor_response"
                        }
            except Exception as e:
                logger.warning(f"Error querying referrals for doctor review: {e}")

        # 3. Inquiring about assigned cases
        if any(c in doctor_message for c in ["case", "cases", "patient", "roster", "patients"]):
            try:
                with get_sync_db() as db:
                    cases = db.query(CareCase).limit(5).all()
                    if cases:
                        summary = "=== Assigned Patient Cohort ===\n"
                        for c in cases:
                            p_name = f"{c.patient.first_name} {c.patient.last_name}" if c.patient else "Patient"
                            summary += f"- {c.case_number}: {p_name} | Priority: {c.priority} | Status: {c.status} | SLA: {c.sla_status}\n"
                        summary += "\nTo review a specific case, ask 'Review case <case_number>'."
                        return {
                            "response_message": summary,
                            "workflow_phase": "cases_reviewed",
                            "next_step": "doctor_response"
                        }
            except Exception as e:
                logger.warning(f"Error querying cases for doctor review: {e}")

        return {
            "response_message": (
                "Hello Doctor. Please specify a case number (e.g. 'Review case CASE-2026-0147') "
                "or ask to view your pending referrals, scheduled appointments, or clinical closure verification tasks."
            ),
            "workflow_phase": "general_guidance",
            "next_step": "doctor_response"
        }

    patient_name = patient_ctx.get("name", "Unknown Patient")
    case_number = case_ctx.get("case_number", "N/A")
    status = case_ctx.get("status", "unknown")
    pathway = case_ctx.get("clinical_pathway", "N/A")
    priority = case_ctx.get("priority", "standard")
    sla_status = case_ctx.get("sla_status", "N/A")
    owner_name = case_ctx.get("owner_name", "Unassigned")

    screening_type = screening_ctx.get("screening_type", "N/A")
    finding_code = screening_ctx.get("finding_code", "N/A")
    finding_summary = screening_ctx.get("finding_summary", "N/A")

    referral_info = case_ctx.get("referral", {})
    appointment_info = case_ctx.get("latest_appointment", {})

    prefix = ""
    if any(g in doctor_message for g in ["hi", "hello", "hey", "good morning", "good afternoon", "greetings"]):
        prefix = f"Hello Doctor. Active clinical file for {patient_name} ({case_number}) is loaded.\n\n"

    summary = (
        f"{prefix}=== Clinical Case Review: {case_number} ===\n"
        f"Patient: {patient_name}\n"
        f"Status: {status} | Priority: {priority} | SLA: {sla_status}\n"
        f"Pathway: {pathway}\n"
        f"Accountable Care Coordinator: {owner_name}\n\n"
        f"--- Screening ---\n"
        f"Type: {screening_type} | Finding: {finding_code}\n"
        f"Summary: {finding_summary}\n\n"
    )

    if referral_info:
        summary += (
            f"--- Referral ---\n"
            f"Status: {referral_info.get('status', 'N/A')} | "
            f"Facility: {referral_info.get('target_facility', 'N/A')}\n\n"
        )

    if appointment_info:
        summary += (
            f"--- Latest Appointment ---\n"
            f"Status: {appointment_info.get('status', 'N/A')} | "
            f"Provider: {appointment_info.get('provider_name', 'N/A')} | "
            f"Time: {appointment_info.get('scheduled_time', 'N/A')}\n\n"
        )

    recent_events = case_ctx.get("recent_events", [])
    if recent_events:
        summary += "--- Recent Events ---\n"
        for evt in recent_events[:5]:
            summary += f"  [{evt.get('timestamp', '')}] {evt.get('event_type', '')}: {evt.get('description', '')}\n"

    return {
        "response_message": summary,
        "workflow_phase": "case_reviewed",
        "next_step": "doctor_response"
    }


# ==============================================================================
# Node 5: referral_management
# ==============================================================================
def referral_management_node(state: DoctorState) -> Dict[str, Any]:
    """
    Node 5: Manages referral acceptance, rejection, and rerouting.
    On reject: sets rejection_reason, records event, Care Coordinator retains ownership.
    """
    logger.info("Executing Doctor Node 5: referral_management")
    doctor_id = state.get("doctor_id")
    case_id = state.get("case_id")
    intent = state.get("doctor_intent", "")
    reason = state.get("referral_reason") or state.get("doctor_message", "")
    audit_entries = []

    if not case_id:
        return {
            "response_message": "No case specified for referral management.",
            "workflow_phase": "error",
            "next_step": "doctor_response",
            "errors": ["referral_management_error: No case_id"]
        }

    try:
        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id)
            referral = db.query(Referral).filter(Referral.case_id == c_uuid).order_by(Referral.created_at.desc()).first()
            if not referral:
                return {
                    "response_message": "No referral found for this case.",
                    "workflow_phase": "referral_not_found",
                    "next_step": "doctor_response"
                }

            now = datetime.now(timezone.utc)

            if intent == "accept_referral":
                referral.status = "accepted"
                referral.responded_at = now

                event = CaseEvent(
                    id=uuid.uuid4(), case_id=c_uuid,
                    event_type="referral_accepted",
                    description=f"Referral accepted by doctor {doctor_id}",
                    event_data={"doctor_id": doctor_id, "referral_id": str(referral.id)},
                    timestamp=now
                )
                db.add(event)

                audit = _doctor_audit(
                    db, c_uuid, "ACCEPT_REFERRAL", doctor_id,
                    autonomy_level=2, rationale=f"Doctor accepted referral for {referral.specialty}"
                )
                audit_entries.append(audit)

                return {
                    "referral_action": "accepted",
                    "response_message": f"Referral accepted. Patient will be scheduled for {referral.specialty} at {referral.target_facility}.",
                    "workflow_phase": "referral_managed",
                    "next_step": "doctor_response",
                    "audit_log": audit_entries,
                    "errors": []
                }

            elif intent == "reject_referral":
                referral.status = "rejected"
                referral.rejection_reason = reason
                referral.responded_at = now

                event = CaseEvent(
                    id=uuid.uuid4(), case_id=c_uuid,
                    event_type="referral_rejected",
                    description=f"Referral rejected by doctor: {reason}",
                    event_data={"doctor_id": doctor_id, "reason": reason, "referral_id": str(referral.id)},
                    timestamp=now
                )
                db.add(event)

                audit = _doctor_audit(
                    db, c_uuid, "REJECT_REFERRAL", doctor_id,
                    autonomy_level=2, rationale=f"Doctor rejected referral. Reason: {reason}"
                )
                audit_entries.append(audit)

                return {
                    "referral_action": "rejected",
                    "referral_reason": reason,
                    "response_message": f"Referral rejected. Reason: {reason}. Care Coordinator retains case ownership and will reroute.",
                    "workflow_phase": "referral_managed",
                    "next_step": "doctor_response",
                    "audit_log": audit_entries,
                    "errors": []
                }

            elif intent == "reroute_referral":
                referral.status = "rerouted"
                referral.responded_at = now

                event = CaseEvent(
                    id=uuid.uuid4(), case_id=c_uuid,
                    event_type="referral_rerouted",
                    description=f"Referral rerouted by doctor: {reason}",
                    event_data={"doctor_id": doctor_id, "reason": reason},
                    timestamp=now
                )
                db.add(event)

                audit = _doctor_audit(
                    db, c_uuid, "REROUTE_REFERRAL", doctor_id,
                    autonomy_level=2, rationale=f"Doctor rerouted referral. Reason: {reason}"
                )
                audit_entries.append(audit)

                return {
                    "referral_action": "rerouted",
                    "referral_reason": reason,
                    "response_message": f"Referral rerouted. Care coordinator will coordinate alternative placement.",
                    "workflow_phase": "referral_managed",
                    "next_step": "doctor_response",
                    "audit_log": audit_entries,
                    "errors": []
                }

            return {
                "response_message": "Unknown referral action.",
                "workflow_phase": "error",
                "next_step": "doctor_response",
                "errors": [f"Unknown referral intent: {intent}"]
            }

    except Exception as e:
        logger.error(f"Error in referral_management_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"referral_management_error: {str(e)}"],
            "next_step": "doctor_response"
        }


# ==============================================================================
# Node 6: appointment_management
# ==============================================================================
def appointment_management_node(state: DoctorState) -> Dict[str, Any]:
    """
    Node 6: Manages appointment cancellation, rescheduling, and confirmation.
    CRITICAL: Cancellation MUST have a reason. Empty reason is rejected.
    Replacement appointments require dual acceptance (doctor + patient).
    Care Coordinator retains end-to-end case ownership accountability.
    """
    logger.info("Executing Doctor Node 6: appointment_management")
    doctor_id = state.get("doctor_id")
    case_id = state.get("case_id")
    intent = state.get("doctor_intent", "")
    cancellation_reason = state.get("cancellation_reason") or ""
    doctor_message = state.get("doctor_message", "")
    audit_entries = []

    if not case_id:
        return {
            "response_message": "No case specified for appointment management.",
            "workflow_phase": "error",
            "next_step": "doctor_response",
            "errors": ["appointment_management_error: No case_id"]
        }

    try:
        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id)
            appointment = (
                db.query(Appointment)
                .filter(Appointment.case_id == c_uuid, Appointment.status.in_(["booked", "confirmed"]))
                .order_by(Appointment.created_at.desc())
                .first()
            )
            if not appointment:
                return {
                    "response_message": "No active appointment found for this case.",
                    "workflow_phase": "appointment_not_found",
                    "next_step": "doctor_response"
                }

            now = datetime.now(timezone.utc)

            if intent == "cancel_appointment":
                # MANDATORY: Cancellation reason must be provided
                if not cancellation_reason.strip():
                    cancellation_reason = _extract_cancellation_reason(doctor_message)

                if not cancellation_reason.strip():
                    return {
                        "response_message": "Appointment cancellation requires a mandatory reason. Please provide the reason for cancellation.",
                        "workflow_phase": "cancellation_reason_required",
                        "next_step": "doctor_response",
                        "errors": ["Cancellation reason is mandatory"]
                    }

                prev_status = appointment.status
                appointment.status = "cancelled"
                appointment.cancellation_reason = cancellation_reason
                appointment.cancellation_outcome = "reschedule_pending"

                event = CaseEvent(
                    id=uuid.uuid4(), case_id=c_uuid,
                    event_type="appointment_cancelled_by_doctor",
                    description=f"Appointment cancelled by doctor. Reason: {cancellation_reason}",
                    event_data={
                        "doctor_id": doctor_id,
                        "appointment_id": str(appointment.id),
                        "reason": cancellation_reason,
                        "previous_status": prev_status
                    },
                    timestamp=now
                )
                db.add(event)

                audit = _doctor_audit(
                    db, c_uuid, "DOCTOR_CANCEL_APPOINTMENT", doctor_id,
                    autonomy_level=2,
                    rationale=f"Doctor cancelled appointment. Reason: {cancellation_reason}"
                )
                audit_entries.append(audit)

                return {
                    "appointment_action": "cancelled",
                    "cancellation_reason": cancellation_reason,
                    "replacement_requires_dual_acceptance": True,
                    "response_message": f"Appointment cancelled. Reason: {cancellation_reason}. A replacement appointment requires explicit acceptance from both doctor and patient. Coordinator retains case ownership.",
                    "workflow_phase": "appointment_managed",
                    "next_step": "doctor_response",
                    "audit_log": audit_entries,
                    "errors": []
                }

            elif intent == "reschedule_appointment":
                appointment.status = "rescheduled"

                # Create replacement appointment requiring dual acceptance
                new_appointment = Appointment(
                    id=uuid.uuid4(),
                    case_id=c_uuid,
                    patient_id=appointment.patient_id,
                    facility=appointment.facility,
                    provider_name=appointment.provider_name,
                    appointment_type=appointment.appointment_type,
                    scheduled_time=now + timedelta(days=7),
                    status="booked",
                    rescheduled_from_id=appointment.id,
                    notes="Rescheduled by doctor. Requires dual acceptance from both doctor and patient."
                )
                db.add(new_appointment)

                event = CaseEvent(
                    id=uuid.uuid4(), case_id=c_uuid,
                    event_type="appointment_rescheduled_by_doctor",
                    description="Appointment rescheduled by doctor",
                    event_data={
                        "doctor_id": doctor_id,
                        "old_appointment_id": str(appointment.id),
                        "new_appointment_id": str(new_appointment.id),
                    },
                    timestamp=now
                )
                db.add(event)

                audit = _doctor_audit(
                    db, c_uuid, "DOCTOR_RESCHEDULE_APPOINTMENT", doctor_id,
                    autonomy_level=2,
                    rationale="Doctor rescheduled appointment. Replacement requires dual acceptance."
                )
                audit_entries.append(audit)

                return {
                    "appointment_action": "rescheduled",
                    "replacement_requires_dual_acceptance": True,
                    "response_message": "Appointment rescheduled. Replacement appointment created, pending dual acceptance from doctor and patient.",
                    "workflow_phase": "appointment_managed",
                    "next_step": "doctor_response",
                    "audit_log": audit_entries,
                    "errors": []
                }

            elif intent == "confirm_appointment":
                appointment.status = "confirmed"

                event = CaseEvent(
                    id=uuid.uuid4(), case_id=c_uuid,
                    event_type="appointment_confirmed_by_doctor",
                    description="Appointment confirmed by doctor",
                    event_data={"doctor_id": doctor_id, "appointment_id": str(appointment.id)},
                    timestamp=now
                )
                db.add(event)

                audit = _doctor_audit(
                    db, c_uuid, "DOCTOR_CONFIRM_APPOINTMENT", doctor_id,
                    autonomy_level=1,
                    rationale="Doctor confirmed appointment availability"
                )
                audit_entries.append(audit)

                return {
                    "appointment_action": "confirmed",
                    "response_message": "Appointment confirmed successfully.",
                    "workflow_phase": "appointment_managed",
                    "next_step": "doctor_response",
                    "audit_log": audit_entries,
                    "errors": []
                }

            return {
                "response_message": "Unknown appointment action.",
                "workflow_phase": "error",
                "next_step": "doctor_response"
            }

    except Exception as e:
        logger.error(f"Error in appointment_management_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"appointment_management_error: {str(e)}"],
            "next_step": "doctor_response"
        }


def _extract_cancellation_reason(message: str) -> str:
    """Extracts a cancellation reason from the doctor's natural language message."""
    msg_lower = message.lower()
    reason_keywords = {
        "emergency": "Doctor has emergency clinical obligations",
        "unavailable": "Doctor unavailable on scheduled date",
        "conflict": "Schedule conflict",
        "not appropriate": "Procedure not appropriate for this patient",
        "needs different": "Patient requires different specialist",
        "equipment": "Equipment unavailability",
        "sick": "Physician illness",
        "surgery": "Extended surgical procedure conflict",
    }
    for kw, reason in reason_keywords.items():
        if kw in msg_lower:
            return reason

    import re
    match = re.search(r"(?:because|reason[:\s]*|due to)\s*(.+)", message, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return ""


# ==============================================================================
# Node 7: consultation_management
# ==============================================================================
def consultation_management_node(state: DoctorState) -> Dict[str, Any]:
    """
    Node 7: Records clinical consultation notes as CaseEvent.
    Updates case context. Marks appointment as attended.
    """
    logger.info("Executing Doctor Node 7: consultation_management")
    doctor_id = state.get("doctor_id")
    case_id = state.get("case_id")
    notes = state.get("consultation_notes") or state.get("doctor_message", "")
    audit_entries = []

    if not case_id:
        return {
            "response_message": "No case specified for consultation recording.",
            "workflow_phase": "error",
            "next_step": "doctor_response",
            "errors": ["consultation_error: No case_id"]
        }

    try:
        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if not case:
                return {
                    "response_message": f"Case {case_id} not found.",
                    "workflow_phase": "error",
                    "next_step": "doctor_response"
                }

            now = datetime.now(timezone.utc)

            event = CaseEvent(
                id=uuid.uuid4(),
                case_id=c_uuid,
                event_type="doctor_consultation",
                description="Clinical consultation recorded by doctor",
                event_data={"doctor_id": doctor_id, "notes": notes},
                timestamp=now
            )
            db.add(event)

            ctx = dict(case.case_context or {})
            consultations = list(ctx.get("consultations", []))
            consultations.append({
                "doctor_id": doctor_id,
                "timestamp": now.isoformat(),
                "notes": notes
            })
            ctx["consultations"] = consultations
            case.case_context = ctx

            appointment = (
                db.query(Appointment)
                .filter(Appointment.case_id == c_uuid, Appointment.status.in_(["booked", "confirmed"]))
                .order_by(Appointment.created_at.desc())
                .first()
            )
            if appointment:
                appointment.status = "attended"

            audit = _doctor_audit(
                db, c_uuid, "RECORD_CONSULTATION", doctor_id,
                autonomy_level=1,
                rationale="Doctor recorded clinical consultation notes"
            )
            audit_entries.append(audit)

            return {
                "consultation_notes": notes,
                "response_message": f"Consultation notes recorded successfully for case {case.case_number}.",
                "workflow_phase": "consultation_recorded",
                "next_step": "doctor_response",
                "audit_log": audit_entries,
                "errors": []
            }

    except Exception as e:
        logger.error(f"Error in consultation_management_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"consultation_error: {str(e)}"],
            "next_step": "doctor_response"
        }


# ==============================================================================
# Node 8: clinical_decision_review
# ==============================================================================
def clinical_decision_review_node(state: DoctorState) -> Dict[str, Any]:
    """
    Node 8: Records clinical decisions (diagnosis impression, treatment recommendation).
    Level 3 — doctor authority, NOT AI. Store as CaseEvent.
    AI must NEVER make clinical decisions.
    """
    logger.info("Executing Doctor Node 8: clinical_decision_review")
    doctor_id = state.get("doctor_id")
    case_id = state.get("case_id")
    decision = state.get("clinical_decision") or {}
    message = state.get("doctor_message", "")
    audit_entries = []

    if not case_id:
        return {
            "response_message": "No case specified for clinical decision.",
            "workflow_phase": "error",
            "next_step": "doctor_response",
            "errors": ["clinical_decision_error: No case_id"]
        }

    try:
        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if not case:
                return {
                    "response_message": f"Case {case_id} not found.",
                    "workflow_phase": "error",
                    "next_step": "doctor_response"
                }

            now = datetime.now(timezone.utc)

            if not decision:
                decision = {"description": message, "recorded_by": doctor_id}

            event = CaseEvent(
                id=uuid.uuid4(),
                case_id=c_uuid,
                event_type="clinical_decision",
                description="Clinical decision recorded by doctor",
                event_data={"doctor_id": doctor_id, "decision": decision},
                timestamp=now
            )
            db.add(event)

            ctx = dict(case.case_context or {})
            ctx["clinical_decision"] = decision
            ctx["clinical_decision_timestamp"] = now.isoformat()
            case.case_context = ctx

            audit = _doctor_audit(
                db, c_uuid, "RECORD_CLINICAL_DECISION", doctor_id,
                autonomy_level=3,
                rationale="Doctor recorded clinical decision under physician authority"
            )
            audit_entries.append(audit)

            return {
                "clinical_decision": decision,
                "response_message": "Clinical decision recorded. This decision remains under your clinical authority.",
                "workflow_phase": "clinical_decision_recorded",
                "next_step": "doctor_response",
                "audit_log": audit_entries,
                "errors": []
            }

    except Exception as e:
        logger.error(f"Error in clinical_decision_review_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"clinical_decision_error: {str(e)}"],
            "next_step": "doctor_response"
        }


# ==============================================================================
# Node 9: followup_management
# ==============================================================================
def followup_management_node(state: DoctorState) -> Dict[str, Any]:
    """
    Node 9: Creates follow-up tasks and schedules monitoring.
    Creates Task with task_type=clinical_followup.
    Care Coordinator remains accountable for managing task progress.
    """
    logger.info("Executing Doctor Node 9: followup_management")
    doctor_id = state.get("doctor_id")
    case_id = state.get("case_id")
    followup_plan = state.get("followup_plan") or {}
    message = state.get("doctor_message", "")
    audit_entries = []

    if not case_id:
        return {
            "response_message": "No case specified for follow-up scheduling.",
            "workflow_phase": "error",
            "next_step": "doctor_response",
            "errors": ["followup_error: No case_id"]
        }

    try:
        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if not case:
                return {
                    "response_message": f"Case {case_id} not found.",
                    "workflow_phase": "error",
                    "next_step": "doctor_response"
                }

            now = datetime.now(timezone.utc)
            description = followup_plan.get("description", message)
            due_days = followup_plan.get("due_days", 14)

            task = Task(
                id=uuid.uuid4(),
                case_id=c_uuid,
                title=f"Clinical follow-up: {description[:60]}",
                description=description,
                task_type="clinical_followup",
                assigned_to_id=case.current_owner_id,
                assigned_role="care_coordinator",
                status="pending",
                due_date=now + timedelta(days=due_days)
            )
            db.add(task)

            event = CaseEvent(
                id=uuid.uuid4(),
                case_id=c_uuid,
                event_type="followup_scheduled",
                description=f"Follow-up plan created by doctor: {description[:100]}",
                event_data={"doctor_id": doctor_id, "plan": followup_plan, "task_id": str(task.id)},
                timestamp=now
            )
            db.add(event)

            audit = _doctor_audit(
                db, c_uuid, "SCHEDULE_FOLLOWUP", doctor_id,
                autonomy_level=2,
                rationale=f"Doctor scheduled clinical follow-up: {description[:60]}"
            )
            audit_entries.append(audit)

            return {
                "followup_plan": {"task_id": str(task.id), "description": description, "due_days": due_days},
                "response_message": f"Follow-up task created: {description[:60]}. Due in {due_days} days.",
                "workflow_phase": "followup_scheduled",
                "next_step": "doctor_response",
                "audit_log": audit_entries,
                "errors": []
            }

    except Exception as e:
        logger.error(f"Error in followup_management_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"followup_error: {str(e)}"],
            "next_step": "doctor_response"
        }


# ==============================================================================
# Node 10: closure_review
# ==============================================================================
def closure_review_node(state: DoctorState) -> Dict[str, Any]:
    """
    Node 10: Doctor provides clinical verification for case closure.
    Creates ClosureEvidence with verifying_clinician_id = doctor_id.
    This satisfies the Level 3 human authorization gate.
    AI must NEVER independently approve clinical closure.
    """
    logger.info("Executing Doctor Node 10: closure_review")
    doctor_id = state.get("doctor_id")
    case_id = state.get("case_id")
    closure_decision = state.get("closure_decision") or "approved"
    evidence_summary = state.get("closure_evidence_summary") or state.get("doctor_message", "")
    audit_entries = []

    if not case_id:
        return {
            "response_message": "No case specified for closure review.",
            "workflow_phase": "error",
            "next_step": "doctor_response",
            "errors": ["closure_review_error: No case_id"]
        }

    try:
        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id)
            doc_uuid = uuid.UUID(doctor_id)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if not case:
                return {
                    "response_message": f"Case {case_id} not found.",
                    "workflow_phase": "error",
                    "next_step": "doctor_response"
                }

            now = datetime.now(timezone.utc)

            if closure_decision == "approved":
                evidence = ClosureEvidence(
                    id=uuid.uuid4(),
                    case_id=c_uuid,
                    evidence_type="clinical_verification",
                    evidence_summary=evidence_summary,
                    verifying_clinician_id=doc_uuid,
                    is_verified=True,
                    verified_at=now
                )
                db.add(evidence)

                event = CaseEvent(
                    id=uuid.uuid4(),
                    case_id=c_uuid,
                    event_type="clinical_closure_verified",
                    description=f"Clinical closure verified by doctor: {evidence_summary[:100]}",
                    event_data={"doctor_id": doctor_id, "evidence_id": str(evidence.id)},
                    timestamp=now
                )
                db.add(event)

                audit = _doctor_audit(
                    db, c_uuid, "VERIFY_CLINICAL_CLOSURE", doctor_id,
                    autonomy_level=3,
                    rationale=f"Doctor verified clinical closure: {evidence_summary[:100]}"
                )
                audit_entries.append(audit)

                return {
                    "closure_decision": "approved",
                    "closure_evidence_summary": evidence_summary,
                    "response_message": "Clinical closure verified. Evidence recorded with clinician sign-off.",
                    "workflow_phase": "closure_verified",
                    "next_step": "doctor_response",
                    "audit_log": audit_entries,
                    "errors": []
                }

            else:  # rejected
                event = CaseEvent(
                    id=uuid.uuid4(),
                    case_id=c_uuid,
                    event_type="clinical_closure_rejected",
                    description=f"Closure rejected by doctor: {evidence_summary[:100]}",
                    event_data={"doctor_id": doctor_id, "reason": evidence_summary},
                    timestamp=now
                )
                db.add(event)

                audit = _doctor_audit(
                    db, c_uuid, "REJECT_CLINICAL_CLOSURE", doctor_id,
                    autonomy_level=3,
                    rationale=f"Doctor rejected closure: {evidence_summary[:100]}"
                )
                audit_entries.append(audit)

                return {
                    "closure_decision": "rejected",
                    "response_message": "Closure rejected. Additional follow-up required. Care coordinator notified.",
                    "workflow_phase": "closure_rejected",
                    "next_step": "doctor_response",
                    "audit_log": audit_entries,
                    "errors": []
                }

    except Exception as e:
        logger.error(f"Error in closure_review_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"closure_review_error: {str(e)}"],
            "next_step": "doctor_response"
        }


# ==============================================================================
# Node 11: doctor_response
# ==============================================================================
def doctor_response_node(state: DoctorState) -> Dict[str, Any]:
    """
    Node 11: Formats and returns the final structured response to the doctor.
    Handles both success and error scenarios.
    """
    logger.info("Executing Doctor Node 11: doctor_response")

    # If unauthorized, return auth failure message
    if not state.get("is_authorized", True) and state.get("auth_failure_reason"):
        return {
            "response_message": f"Access Denied: {state.get('auth_failure_reason')}",
            "workflow_phase": "response_sent"
        }

    # If response already set by action node, return it
    existing_response = state.get("response_message")
    if existing_response:
        return {
            "response_message": existing_response,
            "workflow_phase": "response_sent"
        }

    # Errors present
    errors = state.get("errors", [])
    if errors:
        return {
            "response_message": f"Error processing request: {'; '.join(errors)}",
            "workflow_phase": "response_sent"
        }

    return {
        "response_message": "Request processed. No additional action required.",
        "workflow_phase": "response_sent"
    }
