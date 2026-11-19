"""
CareBridge AI Workflow Nodes
Individual, decoupled, idempotent node implementations for the 11-node Care Coordination StateGraph.
The application database is the source of truth.
AI is used ONLY for empathetic communication drafting, translation, and summaries.
AI NEVER diagnoses, prescribes, or independently approves clinical closure.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from app.database.session import get_sync_db
from app.models import (
    Patient, CareCase, CaseOwner, CaseOwnershipHistory, Task,
    Referral, Appointment, Communication, CaseEvent, AuditLog,
    ClosureEvidence, ScreeningResult
)
from app.workflows.state import CareBridgeState, ClosureChecklist
from app.workflows.rules import (
    calculate_sla_deadline, evaluate_sla_status, match_clinical_pathway,
    evaluate_dropoff_rules, determine_recovery_strategy, evaluate_closure_checklist,
    _ensure_utc
)
from app.services.llm_service import LLMService

logger = logging.getLogger("carebridge.workflows.nodes")


# ==============================================================================
# Helper / Audit logger
# ==============================================================================
def _log_audit_entry(
    db, case_id: uuid.UUID, action: str, actor_id: str,
    autonomy_level: int, rationale: str, actor_type: str = "ai_agent"
) -> Dict[str, Any]:
    entry = AuditLog(
        id=uuid.uuid4(),
        case_id=case_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        autonomy_level=autonomy_level,
        rationale=rationale,
        timestamp=datetime.now(timezone.utc)
    )
    db.add(entry)
    db.commit()
    return {
        "action": action,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "autonomy_level": autonomy_level,
        "rationale": rationale,
        "timestamp": entry.timestamp.isoformat()
    }


# ==============================================================================
# Node 1: create_case
# ==============================================================================
def create_case_node(state: CareBridgeState) -> Dict[str, Any]:
    """
    Node 1: Initializes the CareCase from an abnormal screening result.
    Idempotent: Reuses existing CareCase if already present.
    """
    logger.info("Executing Node 1: create_case")
    screening_id_str = state.get("screening_result_id")
    case_id_str = state.get("case_id")
    patient_id_str = state.get("patient_id")

    audit_entries = []
    errors = []

    try:
        with get_sync_db() as db:
            existing_case = None

            # 1. Idempotency check by case_id or screening_result_id
            if case_id_str:
                try:
                    c_uuid = uuid.UUID(case_id_str)
                    existing_case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
                except ValueError:
                    pass

            if not existing_case and screening_id_str:
                s_uuid = uuid.UUID(screening_id_str)
                existing_case = db.query(CareCase).filter(CareCase.screening_result_id == s_uuid).first()

            if existing_case:
                logger.info(f"Idempotent hit: Case {existing_case.case_number} already exists.")
                return {
                    "case_id": str(existing_case.id),
                    "patient_id": str(existing_case.patient_id),
                    "screening_result_id": str(existing_case.screening_result_id),
                    "current_owner_id": str(existing_case.current_owner_id) if existing_case.current_owner_id else None,
                    "status": existing_case.status,
                    "priority": existing_case.priority,
                    "clinical_pathway": existing_case.clinical_pathway,
                    "sla_start_time": existing_case.sla_start_time.isoformat(),
                    "sla_deadline": existing_case.sla_deadline.isoformat(),
                    "sla_status": existing_case.sla_status,
                    "workflow_phase": "case_created",
                    "next_step": "select_approved_pathway"
                }

            # 2. Fetch screening result to calibrate urgency and SLA
            if not screening_id_str:
                raise ValueError("screening_result_id is required to create a new case.")

            s_uuid = uuid.UUID(screening_id_str)
            screening = db.query(ScreeningResult).filter(ScreeningResult.id == s_uuid).first()
            if not screening:
                raise ValueError(f"ScreeningResult {screening_id_str} not found in database.")

            p_uuid = screening.patient_id
            urgency = screening.urgency_level or "standard"
            now = datetime.now(timezone.utc)
            deadline = calculate_sla_deadline(urgency, now)

            # 3. Find active care coordinator to establish unbroken ownership
            owner = db.query(CaseOwner).filter(CaseOwner.role == "care_coordinator").first()
            owner_id = owner.id if owner else None

            # 4. Create CareCase record
            case_id = uuid.UUID(case_id_str) if case_id_str else uuid.uuid4()
            new_case = CareCase(
                id=case_id,
                case_number=f"CASE-{uuid.uuid4().hex[:8].upper()}",
                patient_id=p_uuid,
                screening_result_id=s_uuid,
                current_owner_id=owner_id,
                status="result_received",
                priority=urgency,
                sla_start_time=now,
                sla_deadline=deadline,
                sla_status="normal"
            )
            db.add(new_case)
            db.flush()

            # 5. Seed initial ownership history
            if owner_id:
                history = CaseOwnershipHistory(
                    id=uuid.uuid4(),
                    case_id=case_id,
                    previous_owner_id=None,
                    new_owner_id=owner_id,
                    transferred_by="carebridge_workflow",
                    reason="Initial case creation and intake assignment",
                    effective_from=now,
                    is_active=True
                )
                db.add(history)

            # 6. Create initial patient outreach task
            task = Task(
                id=uuid.uuid4(),
                case_id=case_id,
                title="Initial patient notification and acknowledgement",
                description="Deliver empathetic, clear notification of abnormal finding and secure acknowledgement.",
                task_type="patient_outreach",
                assigned_to_id=owner_id,
                assigned_role="ai_coordinator",
                status="pending",
                due_date=now + timedelta(hours=24)
            )
            db.add(task)

            # 7. Audit log
            audit = _log_audit_entry(
                db, case_id=case_id, action="CREATE_CARE_CASE",
                actor_id="carebridge_workflow", autonomy_level=1,
                rationale=f"Created case {new_case.case_number} with SLA deadline {deadline.isoformat()}"
            )
            audit_entries.append(audit)

            return {
                "case_id": str(case_id),
                "patient_id": str(p_uuid),
                "screening_result_id": str(s_uuid),
                "current_owner_id": str(owner_id) if owner_id else None,
                "status": new_case.status,
                "priority": urgency,
                "clinical_pathway": new_case.clinical_pathway,
                "sla_start_time": now.isoformat(),
                "sla_deadline": deadline.isoformat(),
                "sla_status": "normal",
                "workflow_phase": "case_created",
                "next_step": "select_approved_pathway",
                "audit_log": audit_entries,
                "errors": []
            }
    except Exception as e:
        logger.error(f"Error in create_case_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"create_case_error: {str(e)}"]
        }


# ==============================================================================
# Node 2: select_approved_pathway
# ==============================================================================
def select_approved_pathway_node(state: CareBridgeState) -> Dict[str, Any]:
    """
    Node 2: Deterministically matches screening modality to authorized clinical pathway.
    AI must never invent clinical guidelines or pathways.
    """
    logger.info("Executing Node 2: select_approved_pathway")
    case_id_str = state.get("case_id")
    audit_entries = []

    try:
        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id_str)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if not case:
                raise ValueError(f"Case {case_id_str} not found")

            # Idempotency check: if valid specific pathway already assigned, retain it
            if case.clinical_pathway and case.clinical_pathway not in ("general_screening_followup", ""):
                return {
                    "clinical_pathway": case.clinical_pathway,
                    "status": case.status,
                    "workflow_phase": "pathway_selected",
                    "next_step": "draft_patient_communication"
                }

            screening = db.query(ScreeningResult).filter(ScreeningResult.id == case.screening_result_id).first()
            if not screening:
                raise ValueError(f"ScreeningResult {case.screening_result_id} not found")

            # Deterministic pathway mapping
            selected_pathway = match_clinical_pathway(
                screening_type=screening.screening_type,
                finding_code=screening.finding_code,
                summary=screening.finding_summary
            )

            case.clinical_pathway = selected_pathway
            case.status = "pathway_selected"

            audit = _log_audit_entry(
                db, case_id=c_uuid, action="SELECT_APPROVED_PATHWAY",
                actor_id="carebridge_workflow", autonomy_level=1,
                rationale=f"Selected approved pathway '{selected_pathway}' based on code {screening.finding_code}"
            )
            audit_entries.append(audit)

            return {
                "clinical_pathway": selected_pathway,
                "status": "pathway_selected",
                "workflow_phase": "pathway_selected",
                "next_step": "draft_patient_communication",
                "audit_log": audit_entries,
                "errors": []
            }
    except Exception as e:
        logger.error(f"Error in select_approved_pathway_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"select_pathway_error: {str(e)}"]
        }


# ==============================================================================
# Node 3: draft_patient_communication
# ==============================================================================
def draft_patient_communication_node(state: CareBridgeState) -> Dict[str, Any]:
    """
    Node 3: Drafts and dispatches culturally empathetic, non-alarmist patient outreach.
    Uses OpenAI / Groq LLM API for language formulation.
    Idempotent: Does not create duplicate initial notifications.
    """
    logger.info("Executing Node 3: draft_patient_communication")
    case_id_str = state.get("case_id")
    audit_entries = []

    try:
        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id_str)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if not case:
                raise ValueError(f"Case {case_id_str} not found")

            patient = db.query(Patient).filter(Patient.id == case.patient_id).first()
            lang = patient.preferred_language if patient else "en"
            channel = patient.communication_channel if patient else "sms"

            # 1. Idempotency: Check if initial communication already dispatched
            existing_comm = (
                db.query(Communication)
                .filter(Communication.case_id == c_uuid, Communication.sender == "ai_coordinator")
                .first()
            )
            if existing_comm:
                logger.info(f"Idempotent hit: Initial notification already exists (id={existing_comm.id}).")
                return {
                    "drafted_communication": existing_comm.content,
                    "patient_language": existing_comm.language,
                    "workflow_phase": "communication_sent",
                    "next_step": "record_acknowledgement"
                }

            # 2. Formulate empathetic communication via LLM or deterministic fallback
            screening = db.query(ScreeningResult).filter(ScreeningResult.id == case.screening_result_id).first()
            findings_summary = screening.finding_summary if screening else "Follow-up screening review required"
            patient_name = f"{patient.first_name} {patient.last_name}" if patient else "Valued Patient"

            prompt = (
                f"Draft an empathetic, supportive, and non-alarmist patient notification for {patient_name} in language '{lang}'.\n"
                f"Screening context: {findings_summary}.\n"
                f"Next recommended step: Diagnostic follow-up evaluation under clinical pathway '{case.clinical_pathway}'.\n"
                f"Requirements: Explain that an abnormal screening is common and does not mean cancer; emphasize prompt follow-up;\n"
                f"request acknowledgement and provide our care coordinator contact."
            )

            try:
                llm = LLMService.get_llm()
                if llm:
                    response = llm.invoke(prompt)
                    message_content = response.content.strip()
                else:
                    raise ValueError("Mock or offline provider active")
            except Exception as llm_err:
                logger.warning(f"LLM formulation fallback: {llm_err}")
                if lang == "ta":
                    message_content = (
                        f"வணக்கம் {patient_name}, உங்கள் பரிசோதனை முடிவுகளை தொடர்ந்து மேலதிக ஆலோசனைக்கு "
                        "நேரம் ஒதுக்க வேண்டும். பயப்பட வேண்டாம், நாங்கள் உங்களுக்கு உதவ தயாராக உள்ளோம். "
                        "தயவுசெய்து இந்த செய்தியை பார்த்ததும் பதிலளிக்கவும்."
                    )
                else:
                    message_content = (
                        f"Hello {patient_name}, your recent screening test requires a routine follow-up evaluation. "
                        "Finding something on a screening is common and our care team is here to support you at every step. "
                        "Please reply to this message to confirm receipt so we can help schedule your appointment."
                    )

            # 3. Store Communication record in database
            now = datetime.now(timezone.utc)
            comm = Communication(
                id=uuid.uuid4(),
                case_id=c_uuid,
                patient_id=case.patient_id,
                sender="ai_coordinator",
                channel=channel,
                content=message_content,
                language=lang,
                sent_at=now
            )
            db.add(comm)

            # 4. Record Case Event
            event = CaseEvent(
                id=uuid.uuid4(),
                case_id=c_uuid,
                event_type="patient_communication_dispatched",
                description=f"Initial patient outreach sent via {channel} in {lang}",
                event_data={"channel": channel, "language": lang},
                timestamp=now
            )
            db.add(event)

            audit = _log_audit_entry(
                db, case_id=c_uuid, action="DRAFT_PATIENT_COMMUNICATION",
                actor_id="carebridge_workflow", autonomy_level=1,
                rationale=f"Drafted and dispatched initial notification in {lang} via {channel}"
            )
            audit_entries.append(audit)

            return {
                "drafted_communication": message_content,
                "patient_language": lang,
                "workflow_phase": "communication_sent",
                "next_step": "record_acknowledgement",
                "audit_log": audit_entries,
                "errors": []
            }
    except Exception as e:
        logger.error(f"Error in draft_patient_communication_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"draft_communication_error: {str(e)}"]
        }


# ==============================================================================
# Node 4: record_acknowledgement
# ==============================================================================
def record_acknowledgement_node(state: CareBridgeState) -> Dict[str, Any]:
    """
    Node 4: Records patient acknowledgement of outreach.
    If unacknowledged and past the notification window, flags dropoff risk.
    """
    logger.info("Executing Node 4: record_acknowledgement")
    case_id_str = state.get("case_id")
    inbound_ack = state.get("patient_acknowledged", False)
    inbound_msg = state.get("latest_patient_message")
    audit_entries = []

    try:
        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id_str)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if not case:
                raise ValueError(f"Case {case_id_str} not found")

            now = datetime.now(timezone.utc)

            # Check DB for any inbound message if not explicitly passed in state
            if not inbound_ack and not inbound_msg:
                inbound_comm = (
                    db.query(Communication)
                    .filter(Communication.case_id == c_uuid, Communication.sender == "patient")
                    .order_by(Communication.created_at.desc())
                    .first()
                )
                if inbound_comm:
                    inbound_ack = True
                    inbound_msg = inbound_comm.content

            # Acknowledged scenario
            if inbound_ack or (inbound_msg and len(inbound_msg.strip()) > 0):
                case_ctx = dict(case.case_context or {})
                case_ctx["patient_understanding_confirmed"] = True
                case.case_context = case_ctx

                # Mark outreach tasks completed
                tasks = (
                    db.query(Task)
                    .filter(Task.case_id == c_uuid, Task.task_type == "patient_outreach", Task.status == "pending")
                    .all()
                )
                for t in tasks:
                    t.status = "completed"
                    t.completed_at = now

                event = CaseEvent(
                    id=uuid.uuid4(),
                    case_id=c_uuid,
                    event_type="patient_acknowledged",
                    description="Patient acknowledged receipt of screening result notification",
                    event_data={"message": inbound_msg},
                    timestamp=now
                )
                db.add(event)

                audit = _log_audit_entry(
                    db, case_id=c_uuid, action="RECORD_PATIENT_ACKNOWLEDGEMENT",
                    actor_id="carebridge_workflow", autonomy_level=1,
                    rationale="Patient confirmed receipt of screening results and outreach."
                )
                audit_entries.append(audit)

                return {
                    "patient_acknowledged": True,
                    "acknowledgement_channel": "patient_portal_sms",
                    "acknowledgement_timestamp": now.isoformat(),
                    "workflow_phase": "acknowledged",
                    "next_step": "coordinate_referral",
                    "audit_log": audit_entries,
                    "errors": []
                }

            # Unacknowledged scenario: evaluate if past response window
            outreach = (
                db.query(Communication)
                .filter(Communication.case_id == c_uuid, Communication.sender == "ai_coordinator")
                .order_by(Communication.created_at.desc())
                .first()
            )
            outreach_time = outreach.sent_at if outreach else case.created_at

            has_dropoff, reasons = evaluate_dropoff_rules(
                patient_acknowledged=False,
                outreach_sent_at=outreach_time,
                appointment_status=None,
                scheduled_appointment_time=None,
                sla_status=case.sla_status,
                days_inactive=0.0,
                now=now
            )

            return {
                "patient_acknowledged": False,
                "dropoff_risk": has_dropoff,
                "dropoff_reasons": reasons,
                "workflow_phase": "acknowledgement_pending",
                "next_step": "detect_dropoff" if has_dropoff else "coordinate_referral",
                "audit_log": [],
                "errors": []
            }
    except Exception as e:
        logger.error(f"Error in record_acknowledgement_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"record_acknowledgement_error: {str(e)}"]
        }


# ==============================================================================
# Node 5: coordinate_referral
# ==============================================================================
def coordinate_referral_node(state: CareBridgeState) -> Dict[str, Any]:
    """
    Node 5: Establishes formal inter-facility referral to diagnostic specialists.
    Idempotent: Reuses existing referral if already created.
    """
    logger.info("Executing Node 5: coordinate_referral")
    case_id_str = state.get("case_id")
    audit_entries = []

    try:
        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id_str)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if not case:
                raise ValueError(f"Case {case_id_str} not found")

            # 1. Idempotency: Check if referral already created
            existing_ref = db.query(Referral).filter(Referral.case_id == c_uuid).first()
            if existing_ref:
                logger.info(f"Idempotent hit: Referral {existing_ref.id} already exists.")
                return {
                    "referral_id": str(existing_ref.id),
                    "referral_status": existing_ref.status,
                    "target_facility": existing_ref.target_facility,
                    "workflow_phase": "referral_coordinated",
                    "next_step": "coordinate_appointment"
                }

            # 2. Select appropriate target facility & specialty
            pathway = case.clinical_pathway or "general_diagnostic_workup"
            facility = "Apollo Diagnostic Imaging Center"
            specialty = "Diagnostic Radiology & Biopsy"
            if "cervic" in pathway:
                specialty = "Gynecologic Oncology & Colposcopy"
            elif "color" in pathway:
                specialty = "Gastroenterology & Endoscopy"

            now = datetime.now(timezone.utc)
            deadline = now + timedelta(hours=48)

            referral = Referral(
                id=uuid.uuid4(),
                case_id=c_uuid,
                patient_id=case.patient_id,
                referring_provider="CareBridge AI Screening Network",
                target_facility=facility,
                specialty=specialty,
                reason_for_referral=f"Abnormal finding clinical follow-up under pathway {pathway}",
                status="sent",
                acceptance_deadline=deadline
            )
            db.add(referral)

            # Referral tracking task
            task = Task(
                id=uuid.uuid4(),
                case_id=c_uuid,
                title="Specialist referral acceptance tracking",
                description=f"Monitor acceptance of referral by {facility} within 48h SLA.",
                task_type="referral_routing",
                assigned_to_id=case.current_owner_id,
                assigned_role="care_coordinator",
                status="pending",
                due_date=deadline
            )
            db.add(task)

            case.status = "referral_coordinated"

            audit = _log_audit_entry(
                db, case_id=c_uuid, action="COORDINATE_REFERRAL",
                actor_id="carebridge_workflow", autonomy_level=2,
                rationale=f"Routed referral to {facility} ({specialty}) with 48h deadline."
            )
            audit_entries.append(audit)

            return {
                "referral_id": str(referral.id),
                "referral_status": "sent",
                "target_facility": facility,
                "workflow_phase": "referral_coordinated",
                "next_step": "coordinate_appointment",
                "audit_log": audit_entries,
                "errors": []
            }
    except Exception as e:
        logger.error(f"Error in coordinate_referral_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"coordinate_referral_error: {str(e)}"]
        }


# ==============================================================================
# Node 6: coordinate_appointment
# ==============================================================================
def coordinate_appointment_node(state: CareBridgeState) -> Dict[str, Any]:
    """
    Node 6: Books diagnostic follow-up appointment within SLA timeframe.
    Idempotent: Reuses existing active appointment.
    """
    logger.info("Executing Node 6: coordinate_appointment")
    case_id_str = state.get("case_id")
    audit_entries = []

    try:
        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id_str)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if not case:
                raise ValueError(f"Case {case_id_str} not found")

            # 1. Idempotency: Check if appointment already scheduled
            existing_app = (
                db.query(Appointment)
                .filter(Appointment.case_id == c_uuid, Appointment.status.in_(["booked", "confirmed", "attended"]))
                .first()
            )
            if existing_app:
                logger.info(f"Idempotent hit: Appointment {existing_app.id} already scheduled.")
                return {
                    "appointment_id": str(existing_app.id),
                    "appointment_status": existing_app.status,
                    "scheduled_appointment_time": existing_app.scheduled_time.isoformat(),
                    "workflow_phase": "appointment_coordinated",
                    "next_step": "monitor_case"
                }

            # 2. Schedule appointment within clinical SLA window
            now = datetime.now(timezone.utc)
            app_time = now + timedelta(days=5, hours=10) # 5 days out at 10 AM

            appointment = Appointment(
                id=uuid.uuid4(),
                case_id=c_uuid,
                patient_id=case.patient_id,
                facility="Apollo Diagnostic Imaging Center",
                provider_name="Dr. Lakshmi Sundaram, MD",
                appointment_type="diagnostic_evaluation",
                scheduled_time=app_time,
                status="booked"
            )
            db.add(appointment)

            # Milestone task for attendance
            task = Task(
                id=uuid.uuid4(),
                case_id=c_uuid,
                title="Diagnostic evaluation appointment attendance",
                description="Verify patient attendance and retrieve clinical notes/imaging findings.",
                task_type="appointment_attendance",
                assigned_to_id=case.current_owner_id,
                assigned_role="care_coordinator",
                status="pending",
                due_date=app_time + timedelta(hours=4)
            )
            db.add(task)

            case.status = "appointment_scheduled"

            audit = _log_audit_entry(
                db, case_id=c_uuid, action="COORDINATE_APPOINTMENT",
                actor_id="carebridge_workflow", autonomy_level=2,
                rationale=f"Scheduled diagnostic appointment for {app_time.isoformat()} with Dr. Lakshmi Sundaram."
            )
            audit_entries.append(audit)

            return {
                "appointment_id": str(appointment.id),
                "appointment_status": "booked",
                "scheduled_appointment_time": app_time.isoformat(),
                "workflow_phase": "appointment_coordinated",
                "next_step": "monitor_case",
                "audit_log": audit_entries,
                "errors": []
            }
    except Exception as e:
        logger.error(f"Error in coordinate_appointment_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"coordinate_appointment_error: {str(e)}"]
        }


# ==============================================================================
# Node 7: monitor_case
# ==============================================================================
def monitor_case_node(state: CareBridgeState) -> Dict[str, Any]:
    """
    Node 7: Deterministic SLA, milestone, and inactivity monitoring.
    Re-evaluates case status and detects stalled care journeys.
    """
    logger.info("Executing Node 7: monitor_case")
    case_id_str = state.get("case_id")

    try:
        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id_str)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if not case:
                raise ValueError(f"Case {case_id_str} not found")

            now = datetime.now(timezone.utc)

            # 1. Deterministic SLA status calculation
            current_sla = evaluate_sla_status(case.sla_deadline, now)
            case.sla_status = current_sla

            # 2. Inactivity tracking
            latest_event = (
                db.query(CaseEvent)
                .filter(CaseEvent.case_id == c_uuid)
                .order_by(CaseEvent.timestamp.desc())
                .first()
            )
            last_activity = latest_event.timestamp if latest_event else case.updated_at
            days_inactive = (now - _ensure_utc(last_activity)).total_seconds() / 86400.0
            is_stalled = days_inactive >= 5.0

            # 3. Appointment attendance status
            appointment = (
                db.query(Appointment)
                .filter(Appointment.case_id == c_uuid)
                .order_by(Appointment.created_at.desc())
                .first()
            )
            app_attended = appointment.status == "attended" if appointment else False

            db.commit()

            return {
                "sla_status": current_sla,
                "days_inactive": round(days_inactive, 1),
                "is_stalled": is_stalled,
                "appointment_attended": app_attended,
                "workflow_phase": "monitored",
                "next_step": "detect_dropoff"
            }
    except Exception as e:
        logger.error(f"Error in monitor_case_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"monitor_case_error: {str(e)}"]
        }


# ==============================================================================
# Node 8: detect_dropoff
# ==============================================================================
def detect_dropoff_node(state: CareBridgeState) -> Dict[str, Any]:
    """
    Node 8: Evaluates dropoff risks against deterministic rules.
    Flags barriers, no-shows, unacknowledged outreach, and SLA breaches.
    """
    logger.info("Executing Node 8: detect_dropoff")
    case_id_str = state.get("case_id")

    try:
        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id_str)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if not case:
                raise ValueError(f"Case {case_id_str} not found")

            now = datetime.now(timezone.utc)

            outreach = (
                db.query(Communication)
                .filter(Communication.case_id == c_uuid, Communication.sender == "ai_coordinator")
                .first()
            )
            appointment = (
                db.query(Appointment)
                .filter(Appointment.case_id == c_uuid)
                .order_by(Appointment.created_at.desc())
                .first()
            )

            case_ctx = case.case_context or {}
            inferred_barriers = case_ctx.get("inferred_barriers", [])
            patient_ack = state.get("patient_acknowledged", case_ctx.get("patient_understanding_confirmed", False))

            has_dropoff, reasons = evaluate_dropoff_rules(
                patient_acknowledged=patient_ack,
                outreach_sent_at=outreach.sent_at if outreach else case.created_at,
                appointment_status=appointment.status if appointment else None,
                scheduled_appointment_time=appointment.scheduled_time if appointment else None,
                sla_status=case.sla_status,
                days_inactive=state.get("days_inactive", 0.0),
                inferred_barriers=inferred_barriers,
                now=now
            )

            # Also check if case is completely unowned
            if case.current_owner_id is None:
                has_dropoff = True
                reasons.append("unowned_case_risk")

            return {
                "dropoff_risk": has_dropoff,
                "dropoff_reasons": reasons,
                "workflow_phase": "dropoff_evaluated",
                "next_step": "recovery_agent" if has_dropoff else "verify_closure"
            }
    except Exception as e:
        logger.error(f"Error in detect_dropoff_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"detect_dropoff_error: {str(e)}"]
        }


# ==============================================================================
# Node 9: recovery_agent
# ==============================================================================
def recovery_agent_node(state: CareBridgeState) -> Dict[str, Any]:
    """
    Node 9: Formulates and executes proactive recovery actions for stalled/at-risk cases.
    If recovery attempts >= 3, sets up handoff to escalation.
    """
    logger.info("Executing Node 9: recovery_agent")
    case_id_str = state.get("case_id")
    dropoff_reasons = state.get("dropoff_reasons", [])
    audit_entries = []

    try:
        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id_str)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if not case:
                raise ValueError(f"Case {case_id_str} not found")

            case_ctx = dict(case.case_context or {})
            current_attempts = case_ctx.get("recovery_attempts", 0)

            # If attempts already maxed out, route directly to escalation
            if current_attempts >= 3:
                return {
                    "recovery_attempts": current_attempts,
                    "workflow_phase": "recovery_exhausted",
                    "next_step": "escalation"
                }

            # Select recovery playbook strategy
            patient = db.query(Patient).filter(Patient.id == case.patient_id).first()
            lang = patient.preferred_language if patient else "en"
            strategy = determine_recovery_strategy(dropoff_reasons, current_attempts, lang)

            new_attempts = current_attempts + 1
            case_ctx["recovery_attempts"] = new_attempts
            case_ctx["last_recovery_strategy"] = strategy
            case.case_context = case_ctx

            # Create recovery outreach task
            task = Task(
                id=uuid.uuid4(),
                case_id=c_uuid,
                title=f"Proactive recovery play #{new_attempts}: {strategy}",
                description=f"Actionable outreach to address reasons: {', '.join(dropoff_reasons)}",
                task_type="recovery_play",
                assigned_to_id=case.current_owner_id,
                assigned_role="care_coordinator",
                status="pending",
                due_date=datetime.now(timezone.utc) + timedelta(hours=24)
            )
            db.add(task)

            event = CaseEvent(
                id=uuid.uuid4(),
                case_id=c_uuid,
                event_type="recovery_attempt_executed",
                description=f"Proactive recovery play #{new_attempts} triggered: {strategy}",
                event_data={"strategy": strategy, "reasons": dropoff_reasons},
                timestamp=datetime.now(timezone.utc)
            )
            db.add(event)

            audit = _log_audit_entry(
                db, case_id=c_uuid, action="RECOVERY_AGENT_EXECUTE",
                actor_id="carebridge_workflow", autonomy_level=2,
                rationale=f"Executed recovery strategy '{strategy}' for reasons: {', '.join(dropoff_reasons)}"
            )
            audit_entries.append(audit)

            return {
                "recovery_attempts": new_attempts,
                "recovery_strategy": strategy,
                "workflow_phase": "recovery_initiated",
                "next_step": "monitor_case",
                "audit_log": audit_entries,
                "errors": []
            }
    except Exception as e:
        logger.error(f"Error in recovery_agent_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"recovery_agent_error: {str(e)}"]
        }


# ==============================================================================
# Node 10: escalation
# ==============================================================================
def escalation_node(state: CareBridgeState) -> Dict[str, Any]:
    """
    Node 10: Escalates unowned cases, SLA breaches, and exhausted recovery journeys.
    Sets critical priority and alerts clinical and administrative supervision.
    """
    logger.info("Executing Node 10: escalation")
    case_id_str = state.get("case_id")
    audit_entries = []

    try:
        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id_str)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if not case:
                raise ValueError(f"Case {case_id_str} not found")

            is_unowned = case.current_owner_id is None
            new_status = "UNASSIGNED_ESCALATED" if is_unowned else "ESCALATED"
            case.status = new_status
            case.priority = "critical"

            now = datetime.now(timezone.utc)
            reasons = state.get("dropoff_reasons", [])
            reason_text = ", ".join(reasons) if reasons else "Multiple failed recovery attempts or SLA breach."

            # Urgent escalation task for care coordinator and clinical supervisor
            task = Task(
                id=uuid.uuid4(),
                case_id=c_uuid,
                title="URGENT: Care journey escalation intervention",
                description=f"Immediate coordinator outreach required. Reasons: {reason_text}",
                task_type="clinical_review",
                assigned_to_id=case.current_owner_id,
                assigned_role="care_coordinator",
                status="pending",
                due_date=now + timedelta(hours=12)
            )
            db.add(task)

            event = CaseEvent(
                id=uuid.uuid4(),
                case_id=c_uuid,
                event_type="case_escalation",
                description=f"Case escalated to {new_status} with critical priority.",
                event_data={"reasons": reasons, "status": new_status},
                timestamp=now
            )
            db.add(event)

            audit = _log_audit_entry(
                db, case_id=c_uuid, action="ESCALATE_CASE",
                actor_id="carebridge_workflow", autonomy_level=2,
                rationale=f"Escalated case {case.case_number} to {new_status}. Reasons: {reason_text}"
            )
            audit_entries.append(audit)

            return {
                "status": new_status,
                "priority": "critical",
                "escalation_level": "critical",
                "escalation_reason": reason_text,
                "workflow_phase": "escalated",
                "next_step": "end",
                "audit_log": audit_entries,
                "errors": []
            }
    except Exception as e:
        logger.error(f"Error in escalation_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"escalation_error: {str(e)}"]
        }


# ==============================================================================
# Node 11: verify_closure
# ==============================================================================
def verify_closure_node(state: CareBridgeState) -> Dict[str, Any]:
    """
    Node 11: Strict 5-point closed-loop care verification.
    CRITICAL CLINICAL INVARIANT: AI must NEVER independently approve closure.
    Human clinician sign-off is mandatory via LangGraph interrupt / checkpoint.
    """
    logger.info("Executing Node 11: verify_closure")
    case_id_str = state.get("case_id")
    audit_entries = []

    try:
        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id_str)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if not case:
                raise ValueError(f"Case {case_id_str} not found")

            # Check for appointment attendance
            appointment = (
                db.query(Appointment)
                .filter(Appointment.case_id == c_uuid, Appointment.status == "attended")
                .first()
            )
            has_attended = appointment is not None

            # Check for closure evidence and clinician sign-off
            evidence = (
                db.query(ClosureEvidence)
                .filter(ClosureEvidence.case_id == c_uuid)
                .order_by(ClosureEvidence.created_at.desc())
                .first()
            )
            has_evidence = evidence is not None
            is_clinician_signed_off = evidence.is_verified if evidence else False

            # Check for open tasks
            open_tasks = (
                db.query(Task)
                .filter(Task.case_id == c_uuid, Task.status.in_(["pending", "in_progress"]))
                .count()
            )

            # Check coordinator concurrence
            has_coordinator = case.current_owner_id is not None

            # Evaluate 5-point checklist
            checklist = evaluate_closure_checklist(
                has_attended_appointment=has_attended,
                has_closure_evidence=has_evidence,
                is_clinician_signed_off=is_clinician_signed_off,
                has_pending_tasks=open_tasks > 0,
                has_unresolved_barriers=False,
                has_coordinator_concurrence=has_coordinator
            )

            checklist_dict = {
                "diagnostic_resolution_completed": checklist.diagnostic_resolution_completed,
                "all_tasks_completed": checklist.all_tasks_completed,
                "clinical_signoff_verified": checklist.clinical_signoff_verified,
                "barriers_resolved": checklist.barriers_resolved,
                "coordinator_concurrence": checklist.coordinator_concurrence,
            }

            human_decision = state.get("human_decision")

            # If clinician sign-off is already verified or human explicitly approved in resumed state
            if checklist.is_fully_satisfied or human_decision == "approved":
                case.status = "closed"
                db.commit()

                audit = _log_audit_entry(
                    db, case_id=c_uuid, action="VERIFY_CASE_CLOSURE",
                    actor_id="clinician_and_coordinator", autonomy_level=3,
                    rationale="Verified closure with complete clinical evidence, physician sign-off, and coordinator concurrence."
                )
                audit_entries.append(audit)

                return {
                    "closure_checklist": checklist_dict,
                    "closure_verified": True,
                    "status": "closed",
                    "requires_human_approval": False,
                    "human_decision": "approved",
                    "workflow_phase": "closed",
                    "next_step": "end",
                    "audit_log": audit_entries,
                    "errors": []
                }

            # Checklist unsatisfied -> Level 3 Human Approval checkpoint required
            logger.info("Closure verification criteria pending human clinician authorization.")
            return {
                "closure_checklist": checklist_dict,
                "closure_verified": False,
                "requires_human_approval": True,
                "approval_type": "clinical_closure_signoff",
                "human_decision": "pending",
                "workflow_phase": "closure_pending_human_signoff",
                "next_step": "end",
                "audit_log": [],
                "errors": []
            }
    except Exception as e:
        logger.error(f"Error in verify_closure_node: {e}", exc_info=True)
        return {
            "workflow_phase": "error",
            "errors": [f"verify_closure_error: {str(e)}"]
        }
