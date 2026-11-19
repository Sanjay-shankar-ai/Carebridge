"""
CareBridge Tool Execution Registry
Executes coordination actions deterministically with safety boundaries, consent validation, and audit tracking.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from app.models import (
    Patient, CareCase, Task, Referral, Appointment,
    Communication, CaseEvent, AuditLog, ClosureEvidence, CaseOwner,
    CaseOwnershipHistory
)
from app.tools.base import validate_tool_permission, ToolExecutionError
from app.memory.patient_memory import get_patient_memory_sync
from app.memory.case_memory import get_case_memory_sync


def _ensure_utc(dt: Optional[datetime]) -> datetime:
    """Safely normalizes datetime to UTC across SQLite and PostgreSQL."""
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_scheduled_datetime(scheduled_time: Any) -> datetime:
    """Robustly converts ISO strings, datetime objects, and conversational relative times to a UTC datetime."""
    if isinstance(scheduled_time, datetime):
        return _ensure_utc(scheduled_time)
    s = str(scheduled_time or "").strip()
    try:
        return _ensure_utc(datetime.fromisoformat(s.replace("Z", "+00:00")))
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    s_lower = s.lower()

    # Determine time of day
    hour = 10
    minute = 0
    if "9:00" in s_lower or "9 am" in s_lower:
        hour = 9
    elif "10:30" in s_lower:
        hour = 10
        minute = 30
    elif "10:00" in s_lower or "10 am" in s_lower:
        hour = 10
    elif "11:00" in s_lower or "11 am" in s_lower:
        hour = 11
    elif "2:00" in s_lower or "2 pm" in s_lower or "14:00" in s_lower:
        hour = 14
    elif "3:30" in s_lower or "15:30" in s_lower:
        hour = 15
        minute = 30
    elif "afternoon" in s_lower or "pm" in s_lower:
        hour = 14
    elif "morning" in s_lower or "am" in s_lower:
        hour = 10

    # Determine date offset
    days_ahead = 2
    if "tomorrow" in s_lower:
        days_ahead = 1
    elif "today" in s_lower:
        days_ahead = 0
    else:
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        current_wd = now.weekday()
        for idx, day_name in enumerate(weekdays):
            if day_name in s_lower:
                diff = (idx - current_wd) % 7
                days_ahead = diff if diff > 0 else 7
                if "next " in s_lower:
                    days_ahead += 7
                break

    target_dt = (now + timedelta(days=days_ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return _ensure_utc(target_dt)


class ToolExecutionResult:
    def __init__(self, success: bool, data: Any, message: str, autonomy_level: int = 1):
        self.success = success
        self.data = data
        self.message = message
        self.autonomy_level = autonomy_level

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "autonomy_level": self.autonomy_level,
        }


class ToolRegistry:
    """Deterministic backend execution engine for CareBridge tools."""

    @staticmethod
    def log_audit(
        db: Session,
        action: str,
        actor_id: str,
        autonomy_level: int,
        rationale: str,
        case_id: Optional[uuid.UUID] = None,
        patient_id: Optional[uuid.UUID] = None,
        previous_state: Optional[Dict[str, Any]] = None,
        new_state: Optional[Dict[str, Any]] = None,
    ):
        audit = AuditLog(
            id=uuid.uuid4(),
            case_id=case_id,
            patient_id=patient_id,
            actor_type="ai_agent",
            actor_id=actor_id,
            action=action,
            autonomy_level=autonomy_level,
            previous_state=previous_state,
            new_state=new_state,
            rationale=rationale,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit)
        db.commit()

    # --------------------------------------------------------------------------
    # Tool: get_patient_context
    # --------------------------------------------------------------------------
    @classmethod
    def get_patient_context(cls, db: Session, patient_id: str) -> Dict[str, Any]:
        p_uuid = uuid.UUID(patient_id)
        mem = get_patient_memory_sync(p_uuid, db)
        if not mem:
            return ToolExecutionResult(False, None, f"Patient {patient_id} not found").to_dict()
        return ToolExecutionResult(True, mem.model_dump(), "Patient context retrieved successfully", 1).to_dict()

    # --------------------------------------------------------------------------
    # Tool: get_case_history
    # --------------------------------------------------------------------------
    @classmethod
    def get_case_history(cls, db: Session, case_id: str) -> Dict[str, Any]:
        c_uuid = uuid.UUID(case_id)
        mem = get_case_memory_sync(c_uuid, db)
        if not mem:
            return ToolExecutionResult(False, None, f"Case {case_id} not found").to_dict()
        return ToolExecutionResult(True, mem.model_dump(), "Case memory retrieved successfully", 1).to_dict()

    # --------------------------------------------------------------------------
    # Tool: get_case_status
    # --------------------------------------------------------------------------
    @classmethod
    def get_case_status(cls, db: Session, case_id: str) -> Dict[str, Any]:
        c_uuid = uuid.UUID(case_id)
        mem = get_case_memory_sync(c_uuid, db)
        if not mem:
            return ToolExecutionResult(False, None, f"Case {case_id} not found").to_dict()
        status_data = {
            "case_number": mem.case_number,
            "status": mem.status,
            "priority": mem.priority,
            "owner": mem.current_owner_name,
            "sla_deadline": mem.sla_deadline.isoformat(),
            "sla_status": mem.sla_status,
            "is_closed": mem.is_closed,
        }
        return ToolExecutionResult(True, status_data, "Case status retrieved successfully", 1).to_dict()

    # --------------------------------------------------------------------------
    # Tool: get_screening_result
    # --------------------------------------------------------------------------
    @classmethod
    def get_screening_result(cls, db: Session, case_id: str) -> Dict[str, Any]:
        c_uuid = uuid.UUID(case_id)
        mem = get_case_memory_sync(c_uuid, db)
        if not mem:
            return ToolExecutionResult(False, None, f"Case {case_id} not found").to_dict()
        result_data = {
            "screening_type": mem.screening_type,
            "finding_code": mem.finding_code,
            "finding_summary": mem.finding_summary,
            "urgency_level": mem.urgency_level,
        }
        return ToolExecutionResult(True, result_data, "Screening result retrieved successfully", 1).to_dict()

    # --------------------------------------------------------------------------
    # Tool: get_referral_status
    # --------------------------------------------------------------------------
    @classmethod
    def get_referral_status(cls, db: Session, case_id: str) -> Dict[str, Any]:
        c_uuid = uuid.UUID(case_id)
        mem = get_case_memory_sync(c_uuid, db)
        if not mem:
            return ToolExecutionResult(False, None, f"Case {case_id} not found").to_dict()
        if not mem.active_referral and not mem.all_referrals:
            return ToolExecutionResult(True, {"referral": None}, "No referrals currently recorded for this case", 1).to_dict()
        active = mem.active_referral.model_dump() if mem.active_referral else None
        return ToolExecutionResult(True, {"active_referral": active, "all_referrals": [r.model_dump() for r in mem.all_referrals]}, "Referral status retrieved", 1).to_dict()

    # --------------------------------------------------------------------------
    # Tool: record_case_event
    # --------------------------------------------------------------------------
    @classmethod
    def record_case_event(
        cls, db: Session, case_id: str, event_type: str, description: str, event_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        c_uuid = uuid.UUID(case_id)
        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=c_uuid,
            event_type=event_type,
            description=description,
            event_data=event_data or {},
            timestamp=datetime.now(timezone.utc)
        )
        db.add(event)
        db.commit()
        return ToolExecutionResult(True, {"event_id": str(event.id), "event_type": event_type}, "Case event recorded successfully", 1).to_dict()

    # --------------------------------------------------------------------------
    # Tool: update_case_notes
    # --------------------------------------------------------------------------
    @classmethod
    def update_case_notes(
        cls, db: Session, case_id: str, note: str, barrier_detected: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            c_uuid = uuid.UUID(str(case_id))
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        except (ValueError, TypeError):
            case = db.query(CareCase).order_by(CareCase.created_at.desc()).first()
            c_uuid = case.id if case else None
        if not case:
            return ToolExecutionResult(False, None, f"Case {case_id} not found").to_dict()

        ctx = dict(case.case_context or {})
        notes = list(ctx.get("notes", []))
        timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        notes.append(f"[{timestamp_str}] {note}")
        ctx["notes"] = notes

        if barrier_detected:
            barriers = list(ctx.get("inferred_barriers", []))
            if barrier_detected not in barriers:
                barriers.append(barrier_detected)
            ctx["inferred_barriers"] = barriers
            
            # Record CaseEvent
            event = CaseEvent(
                id=uuid.uuid4(),
                case_id=c_uuid,
                event_type="barrier_identified",
                description=f"AI identified patient barrier: {barrier_detected}",
                event_data={"barrier": barrier_detected, "note": note},
                timestamp=datetime.now(timezone.utc)
            )
            db.add(event)

        case.case_context = ctx
        db.commit()

        cls.log_audit(
            db, action="UPDATE_CASE_NOTES", actor_id="supervisor_agent",
            autonomy_level=1, rationale=f"Appended progress note. Barrier flagged: {barrier_detected}",
            case_id=c_uuid, patient_id=case.patient_id
        )

        return ToolExecutionResult(True, {"updated_barriers": ctx.get("inferred_barriers", [])}, "Case notes updated successfully", 1).to_dict()

    # --------------------------------------------------------------------------
    # Tool: send_patient_message
    # --------------------------------------------------------------------------
    @classmethod
    def send_patient_message(
        cls, db: Session, case_id: str, patient_id: str, message: str, language: str = "en", channel: str = "sms", session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        c_uuid = uuid.UUID(case_id)
        p_uuid = uuid.UUID(patient_id)
        s_uuid = uuid.UUID(session_id) if session_id else None

        # Deterministic Consent Check (in_app_chat represents active user engagement)
        patient = db.query(Patient).filter(Patient.id == p_uuid).first()
        if not patient:
            return ToolExecutionResult(False, None, "Patient not found").to_dict()

        has_consent = any(c.status == "active" for c in patient.consents if "outreach" in c.scope)
        if not has_consent and patient.consents and channel != "in_app_chat":
            return ToolExecutionResult(False, None, "Consent missing for automated outreach", 1).to_dict()

        comm = Communication(
            id=uuid.uuid4(),
            case_id=c_uuid,
            patient_id=p_uuid,
            session_id=s_uuid,
            sender="ai_coordinator",
            channel=channel,
            language=language,
            content=message,
            acknowledged=False,
            sent_at=datetime.now(timezone.utc)
        )
        db.add(comm)
        db.commit()

        cls.log_audit(
            db, action="SEND_PATIENT_MESSAGE", actor_id="supervisor_agent",
            autonomy_level=1, rationale=f"Sent proactive multilingual patient guidance ({language} via {channel})",
            case_id=c_uuid, patient_id=p_uuid
        )

        return ToolExecutionResult(True, {"communication_id": str(comm.id), "status": "sent"}, "Message sent to patient", 1).to_dict()

    # --------------------------------------------------------------------------
    # Tool: search_available_appointments / search_appointments
    # --------------------------------------------------------------------------
    @classmethod
    def search_available_appointments(
        cls, db: Session, facility: str, specialty: str, timeframe: str = "next_14_days"
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        # Deterministic simulation of open clinic slots within the clinical SLA window
        available_slots = [
            (now + timedelta(days=2, hours=10)).isoformat(),
            (now + timedelta(days=4, hours=14)).isoformat(),
            (now + timedelta(days=7, hours=11)).isoformat(),
            (now + timedelta(days=9, hours=9)).isoformat(),
        ]
        return ToolExecutionResult(
            True,
            {"facility": facility, "specialty": specialty, "slots": available_slots},
            f"Found {len(available_slots)} available slots within SLA window",
            1
        ).to_dict()

    @classmethod
    def search_appointments(
        cls, db: Session, facility: str, specialty: str, timeframe: str = "next_14_days"
    ) -> Dict[str, Any]:
        return cls.search_available_appointments(db, facility, specialty, timeframe)

    # --------------------------------------------------------------------------
    # Tool: book_appointment (Level 2 - Autonomous with constraints)
    # --------------------------------------------------------------------------
    @classmethod
    def book_appointment(
        cls, db: Session, case_id: str, patient_id: str, facility: str,
        scheduled_time: str, appointment_type: str = "Diagnostic Evaluation",
        notes: Optional[str] = None, provider_name: Optional[str] = None,
        status: str = "booked"
    ) -> Dict[str, Any]:
        c_uuid = uuid.UUID(case_id)
        p_uuid = uuid.UUID(patient_id)
        dt = _parse_scheduled_datetime(scheduled_time)

        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return ToolExecutionResult(False, None, "Case not found").to_dict()

        # Guard against booking on closed care cases
        if case.status == "closed":
            return ToolExecutionResult(
                False, None, "Cannot book appointment on closed care case. A physician must formally reopen it.", 2
            ).to_dict()

        # Idempotency check: Reuse existing active appointment for same facility
        existing_appt = (
            db.query(Appointment)
            .filter(
                Appointment.case_id == c_uuid,
                Appointment.facility == facility,
                Appointment.status.in_(["booked", "confirmed", "pending_approval", "proposed"])
            )
            .first()
        )
        if existing_appt:
            return ToolExecutionResult(
                True,
                {"appointment_id": str(existing_appt.id), "scheduled_time": existing_appt.scheduled_time.isoformat(), "status": existing_appt.status, "idempotent": True},
                f"Idempotent hit: Active appointment already exists at {facility}",
                2
            ).to_dict()

        # Deterministic SLA constraint validation: Must not schedule past SLA deadline
        sla_dl = _ensure_utc(case.sla_deadline)
        if dt > sla_dl:
            return ToolExecutionResult(
                False, None, f"Proposed date {scheduled_time} exceeds case SLA deadline {sla_dl.isoformat()}", 2
            ).to_dict()

        actual_status = status if status in ["booked", "confirmed", "pending_approval", "proposed"] else "booked"
        clinician_name = provider_name or "Dr. Aris Thorne"

        appt = Appointment(
            id=uuid.uuid4(),
            case_id=c_uuid,
            patient_id=p_uuid,
            facility=facility,
            provider_name=clinician_name,
            appointment_type=appointment_type,
            scheduled_time=dt,
            status=actual_status,
            notes=notes
        )
        db.add(appt)
        case.status = "appointment_booked"
        db.commit()

        cls.log_audit(
            db, action="BOOK_APPOINTMENT", actor_id="supervisor_agent",
            autonomy_level=2, rationale=f"Reserved/booked {appointment_type} with {clinician_name} within SLA limits at {facility} ({actual_status})",
            case_id=c_uuid, patient_id=p_uuid
        )

        return ToolExecutionResult(
            True, {"appointment_id": str(appt.id), "scheduled_time": dt.isoformat(), "status": actual_status, "provider_name": clinician_name},
            f"Appointment successfully registered ({actual_status})", 2
        ).to_dict()

    # --------------------------------------------------------------------------
    # Tool: cancel_appointment (Level 2 - Reason & Outcome Tracking)
    # --------------------------------------------------------------------------
    @classmethod
    def cancel_appointment(
        cls,
        db: Session,
        appointment_id: str,
        case_id: str,
        reason: str,
        outcome: str = "reschedule_pending",
        detailed_notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancels an appointment while strictly recording the specific reason and the resulting care outcome.
        Ensures the patient's actionable result is not abandoned.
        """
        appt_uuid = uuid.UUID(appointment_id)
        c_uuid = uuid.UUID(case_id)

        appt = db.query(Appointment).filter(Appointment.id == appt_uuid).first()
        if not appt:
            return ToolExecutionResult(False, None, f"Appointment {appointment_id} not found").to_dict()

        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return ToolExecutionResult(False, None, f"Case {case_id} not found").to_dict()

        # 1. Update Appointment with cancellation reason and outcome
        prev_status = appt.status
        appt.status = "cancelled"
        appt.cancellation_reason = reason
        appt.cancellation_outcome = outcome
        if detailed_notes:
            appt.notes = f"{appt.notes or ''} [Cancelled: {reason} | Outcome: {outcome} | {detailed_notes}]"

        # 2. Update Case State based on the outcome
        ctx = dict(case.case_context or {})
        cancellation_log = ctx.get("cancellation_history", [])
        cancellation_log.append({
            "appointment_id": str(appt_uuid),
            "cancelled_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "outcome": outcome,
            "notes": detailed_notes
        })
        ctx["cancellation_history"] = cancellation_log
        case.case_context = ctx

        if outcome == "care_declined":
            case.status = "escalated"
            case.priority = "urgent"
        elif outcome in ["reschedule_pending", "recovery_play_initiated"]:
            case.status = "recovering"

        # 3. Add to Case Timeline Events
        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=c_uuid,
            event_type="appointment_cancelled",
            description=f"Appointment cancelled. Reason: {reason}. Next Outcome: {outcome}",
            event_data={
                "appointment_id": str(appt_uuid),
                "reason": reason,
                "outcome": outcome,
                "previous_status": prev_status
            },
            timestamp=datetime.now(timezone.utc)
        )
        db.add(event)
        db.commit()

        # 4. Record Immutable Audit Log
        cls.log_audit(
            db,
            action="CANCEL_APPOINTMENT",
            actor_id="supervisor_agent",
            autonomy_level=2,
            rationale=f"Appointment cancelled due to: {reason}. Outcome action designated as: {outcome}.",
            case_id=c_uuid,
            patient_id=case.patient_id,
            previous_state={"appointment_status": prev_status},
            new_state={"appointment_status": "cancelled", "reason": reason, "outcome": outcome}
        )

        return ToolExecutionResult(
            True,
            {
                "appointment_id": str(appt_uuid),
                "status": "cancelled",
                "cancellation_reason": reason,
                "cancellation_outcome": outcome,
                "case_status": case.status
            },
            f"Appointment cancelled with documented reason: '{reason}' and outcome: '{outcome}'",
            2
        ).to_dict()

    # --------------------------------------------------------------------------
    # Tool: create_referral_request (Level 2)
    # --------------------------------------------------------------------------
    @classmethod
    def create_referral_request(
        cls,
        db: Session,
        case_id: str,
        patient_id: str,
        target_facility: str,
        specialty: str,
        reason: Optional[str] = None,
        reason_for_referral: Optional[str] = None,
        actor_role: Optional[str] = "care_coordinator",
        actor_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Creates and dispatches an inter-facility referral request with role-based checks and audit logging."""
        try:
            validate_tool_permission(actor_role, autonomy_level=2)
        except ToolExecutionError as tee:
            return {
                "success": False,
                "error_code": tee.error_code,
                "message": tee.message,
                "autonomy_level": tee.autonomy_level
            }

        actual_reason = reason or reason_for_referral or kwargs.get("referral_reason") or "Clinical referral based on screening finding"
        c_uuid = uuid.UUID(case_id)
        p_uuid = uuid.UUID(patient_id)
        now = datetime.now(timezone.utc)

        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return {
                "success": False,
                "error_code": "CASE_NOT_FOUND",
                "message": f"Case {case_id} not found",
                "autonomy_level": 2
            }

        # Consent enforcement: verify patient has active consent for referral data sharing
        patient = db.query(Patient).filter(Patient.id == p_uuid).first()
        if patient and patient.consents:
            has_referral_consent = any(
                c.status == "active" and ("referral" in c.scope or "sharing" in c.scope)
                for c in patient.consents
            )
            if not has_referral_consent:
                return {
                    "success": False,
                    "error_code": "CONSENT_MISSING",
                    "message": "Consent missing for cross-facility referral sharing",
                    "autonomy_level": 2
                }

        # Idempotency check: Reuse existing active referral for same target facility
        existing_ref = (
            db.query(Referral)
            .filter(
                Referral.case_id == c_uuid,
                Referral.target_facility == target_facility,
                Referral.status.in_(["sent", "accepted"])
            )
            .first()
        )
        if existing_ref:
            return {
                "success": True,
                "data": {
                    "referral_id": str(existing_ref.id),
                    "case_id": str(c_uuid),
                    "patient_id": str(p_uuid),
                    "target_facility": existing_ref.target_facility,
                    "specialty": existing_ref.specialty,
                    "status": existing_ref.status,
                    "acceptance_deadline": existing_ref.acceptance_deadline.isoformat() if existing_ref.acceptance_deadline else None,
                    "idempotent": True
                },
                "message": f"Idempotent hit: Active referral already exists for {target_facility}",
                "autonomy_level": 2
            }

        # Create Referral record
        deadline = now + timedelta(hours=48)
        referral = Referral(
            id=uuid.uuid4(),
            case_id=c_uuid,
            patient_id=p_uuid,
            referring_provider="CareBridge AI Screening Network",
            target_facility=target_facility,
            specialty=specialty,
            reason_for_referral=actual_reason,
            status="sent",
            acceptance_deadline=deadline
        )
        db.add(referral)

        # Create referral tracking task for Care Coordinator
        task = Task(
            id=uuid.uuid4(),
            case_id=c_uuid,
            title=f"Track referral acceptance: {target_facility}",
            description=f"Monitor acceptance of referral for {specialty} within 48h SLA.",
            task_type="referral_routing",
            assigned_to_id=case.current_owner_id,
            assigned_role="care_coordinator",
            status="pending",
            due_date=deadline
        )
        db.add(task)

        # Update case state
        case.status = "referral_coordinated"

        # Record timeline event
        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=c_uuid,
            event_type="referral_created",
            description=f"Referral dispatched to {target_facility} for {specialty}. Acceptance SLA window: 48 hours.",
            event_data={
                "referral_id": str(referral.id),
                "target_facility": target_facility,
                "specialty": specialty,
                "reason": actual_reason
            },
            timestamp=now
        )
        db.add(event)

        # Audit Log
        cls.log_audit(
            db, action="CREATE_REFERRAL", actor_id=actor_id or "carebridge_referral_service",
            autonomy_level=2, rationale=f"Created referral handoff to {target_facility} for {specialty}: {actual_reason}",
            case_id=c_uuid, patient_id=p_uuid
        )

        db.commit()

        return {
            "success": True,
            "data": {
                "referral_id": str(referral.id),
                "case_id": str(c_uuid),
                "patient_id": str(p_uuid),
                "target_facility": target_facility,
                "specialty": specialty,
                "status": "sent",
                "acceptance_deadline": deadline.isoformat()
            },
            "message": f"Referral dispatched to {target_facility}",
            "autonomy_level": 2
        }

    # --------------------------------------------------------------------------
    # Tool: reopen_case (Level 3 - Gatekept)
    # --------------------------------------------------------------------------
    @classmethod
    def reopen_case(
        cls, db: Session, case_id: str, clinician_id: str, rationale: str, actor_role: Optional[str] = "doctor"
    ) -> Dict[str, Any]:
        """Authorized clinical reopening of a closed case (Level 3 Gate)."""
        role = (actor_role or "doctor").lower().strip()
        if role not in ("doctor", "clinician", "specialist", "primary_physician"):
            return {
                "success": False,
                "error_code": "PERMISSION_DENIED",
                "message": f"Role '{actor_role}' lacks Level 3 clinical authority to reopen cases.",
                "autonomy_level": 3
            }

        c_uuid = uuid.UUID(case_id)
        doc_uuid = uuid.UUID(clinician_id)
        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return {"success": False, "error_code": "CASE_NOT_FOUND", "message": f"Case {case_id} not found", "autonomy_level": 3}

        if case.status != "closed":
            return {
                "success": False,
                "error_code": "CASE_NOT_CLOSED",
                "message": f"Case #{case.case_number} is not closed (status: {case.status}).",
                "autonomy_level": 3
            }

        now = datetime.now(timezone.utc)
        case.status = "reopened"
        case.priority = "urgent"

        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=c_uuid,
            event_type="case_reopened",
            description=f"Case reopened under physician authority: {rationale}",
            event_data={"clinician_id": str(doc_uuid), "rationale": rationale},
            timestamp=now
        )
        db.add(event)

        cls.log_audit(
            db, action="REOPEN_CASE", actor_id=str(doc_uuid),
            autonomy_level=3, rationale=f"Reopened closed case: {rationale}",
            case_id=c_uuid, patient_id=case.patient_id
        )
        db.commit()

        return {
            "success": True,
            "data": {"case_id": str(c_uuid), "status": "reopened", "priority": "urgent"},
            "message": f"Case #{case.case_number} reopened successfully.",
            "autonomy_level": 3
        }

    # --------------------------------------------------------------------------
    # Tool: create_followup_task
    # --------------------------------------------------------------------------
    @classmethod
    def create_followup_task(
        cls, db: Session, case_id: str, title: str, description: str,
        task_type: str, due_date: str, assigned_role: str = "ai_coordinator"
    ) -> Dict[str, Any]:
        c_uuid = uuid.UUID(case_id)
        dt = datetime.fromisoformat(due_date)

        # Idempotency check: Reuse existing active/pending task for same case and title
        existing_task = (
            db.query(Task)
            .filter(
                Task.case_id == c_uuid,
                Task.title == title,
                Task.status.in_(["pending", "in_progress"])
            )
            .first()
        )
        if existing_task:
            return ToolExecutionResult(
                True,
                {"task_id": str(existing_task.id), "status": existing_task.status, "idempotent": True},
                f"Idempotent hit: Task '{title}' already exists for this case.",
                1
            ).to_dict()

        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        task = Task(
            id=uuid.uuid4(),
            case_id=c_uuid,
            patient_id=case.patient_id if case else None,
            title=title,
            description=description,
            task_type=task_type,
            assigned_role=assigned_role,
            status="pending",
            due_date=dt
        )
        db.add(task)
        db.commit()

        return ToolExecutionResult(
            True, {"task_id": str(task.id), "title": title},
            f"Follow-up task created: {title}", 1
        ).to_dict()

    # --------------------------------------------------------------------------
    # Tool: escalate_case (Level 2/3)
    # --------------------------------------------------------------------------
    @classmethod
    def escalate_case(
        cls, db: Session, case_id: str, urgency: str = "critical", reason: str = "", actor_role: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        try:
            c_uuid = uuid.UUID(str(case_id))
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        except (ValueError, TypeError):
            case = db.query(CareCase).order_by(CareCase.created_at.desc()).first()
            c_uuid = case.id if case else None
        if not case:
            return ToolExecutionResult(False, None, "Case not found").to_dict()

        now = datetime.now(timezone.utc)
        case.status = "escalated"
        case.priority = urgency

        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=c_uuid,
            event_type="case_escalated",
            description=f"Case escalated to escalated. Urgency: {urgency}. Reason: {reason}",
            event_data={"status": "escalated", "urgency": urgency, "reason": reason},
            timestamp=now
        )
        db.add(event)

        # Critical Clinical Escalation: Create persisted urgent Task for human oversight
        esc_task = Task(
            id=uuid.uuid4(),
            case_id=c_uuid,
            patient_id=case.patient_id,
            title="CRITICAL CLINICAL ESCALATION: Immediate Patient Safety Review",
            description=f"Automated Clinical Escalation: {reason or 'Patient reported acute emergent symptoms'}. Immediate physician/coordinator oversight required.",
            task_type="clinical_review",
            priority="critical",
            status="pending",
            assigned_to_id=case.current_owner_id,
            assigned_role="care_coordinator",
            due_date=now
        )
        db.add(esc_task)
        db.commit()

        cls.log_audit(
            db, action="ESCALATE_CASE", actor_id="supervisor_agent",
            autonomy_level=2, rationale=f"Escalated case due to: {reason}",
            case_id=c_uuid, patient_id=case.patient_id
        )

        return ToolExecutionResult(
            True, {"case_id": str(c_uuid), "status": "escalated", "priority": urgency},
            f"Case successfully escalated to human coordinator queue: {reason}", 2
        ).to_dict()

    # --------------------------------------------------------------------------
    # Tool: request_closure_verification (Level 3 - Gatekept)
    # --------------------------------------------------------------------------
    @classmethod
    def request_closure_verification(
        cls, db: Session, case_id: str, evidence_type: str, evidence_summary: str, clinician_id: str, actor_role: Optional[str] = "care_coordinator"
    ) -> Dict[str, Any]:
        c_uuid = uuid.UUID(case_id)
        doc_uuid = uuid.UUID(clinician_id)

        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return {"success": False, "error_code": "CASE_NOT_FOUND", "message": "Case not found", "autonomy_level": 3}

        clinician = db.query(CaseOwner).filter(CaseOwner.id == doc_uuid).first()
        if not clinician or clinician.role not in ("specialist", "primary_physician", "doctor", "clinician"):
            return {
                "success": False,
                "error_code": "INVALID_CLINICIAN",
                "message": f"User {clinician_id} is not an authorized physician for closure sign-off.",
                "autonomy_level": 3
            }

        evidence = ClosureEvidence(
            id=uuid.uuid4(),
            case_id=c_uuid,
            evidence_type=evidence_type,
            evidence_summary=evidence_summary,
            verifying_clinician_id=doc_uuid,
            is_verified=False # Requires human sign-off!
        )
        db.add(evidence)
        db.commit()

        cls.log_audit(
            db, action="PROPOSE_CLOSURE_VERIFICATION", actor_id="supervisor_agent",
            autonomy_level=3, rationale="AI proposed case closure based on evidence. Clinical sign-off required.",
            case_id=c_uuid
        )

        return ToolExecutionResult(
            True, {"evidence_id": str(evidence.id), "is_verified": False, "requires_approval": True, "requires_human_approval": True},
            "Closure verification requested. Clinical human sign-off required to finalize closure.", 3
        ).to_dict()

    # --------------------------------------------------------------------------
    # Tool: discover_new_patients (Coordinator Discovery)
    # --------------------------------------------------------------------------
    @classmethod
    def discover_new_patients(
        cls,
        db: Session,
        actor_role: str = "care_coordinator",
        limit: int = 10
    ) -> Dict[str, Any]:
        """Queries database for new intake, unassigned, or recently screened patient cases."""
        from sqlalchemy import or_
        role = (actor_role or "care_coordinator").lower().strip()
        if role not in ("care_coordinator", "coordinator", "clinician", "doctor", "system"):
            return {
                "success": False,
                "error_code": "PERMISSION_DENIED",
                "message": f"Role '{actor_role}' is not authorized to access the new patient discovery queue.",
                "autonomy_level": 1
            }

        new_cases = (
            db.query(CareCase)
            .filter(
                or_(
                    CareCase.current_owner_id.is_(None),
                    CareCase.status.in_(["result_received", "screening_completed", "screening", "intake_submitted", "pending"])
                )
            )
            .order_by(CareCase.created_at.desc())
            .limit(limit)
            .all()
        )

        cases_data = []
        for c in new_cases:
            p_name = f"{c.patient.first_name} {c.patient.last_name}" if c.patient else "Unknown Patient"
            cases_data.append({
                "case_id": str(c.id),
                "case_number": c.case_number,
                "patient_id": str(c.patient_id),
                "patient_name": p_name,
                "status": c.status,
                "priority": c.priority,
                "finding_code": c.screening_result.finding_code if c.screening_result else "N/A",
                "screening_type": c.screening_result.screening_type if c.screening_result else "Screening",
                "is_unassigned": c.current_owner_id is None,
                "created_at": c.created_at.isoformat() if c.created_at else None
            })

        cls.log_audit(
            db, action="DISCOVER_NEW_PATIENTS", actor_id="coordinator_agent",
            autonomy_level=1, rationale=f"Retrieved {len(cases_data)} patient cases in discovery queue."
        )

        return {
            "success": True,
            "data": {
                "total_found": len(cases_data),
                "cases": cases_data
            },
            "message": f"Discovered {len(cases_data)} new patient case(s) requiring review or assignment.",
            "autonomy_level": 1
        }

    # --------------------------------------------------------------------------
    # Tool: select_patient_case (Coordinator / Doctor Explicit Selection)
    # --------------------------------------------------------------------------
    @classmethod
    def select_patient_case(
        cls,
        db: Session,
        case_id: Optional[str] = None,
        case_number: Optional[str] = None,
        patient_name: Optional[str] = None,
        actor_role: str = "care_coordinator",
        actor_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Sets authorized case context for care coordinator or doctor with selection evidence."""
        from sqlalchemy import or_
        query = db.query(CareCase)
        if case_id:
            try:
                c_uuid = uuid.UUID(str(case_id))
                query = query.filter(CareCase.id == c_uuid)
            except (ValueError, TypeError):
                pass
        elif case_number:
            query = query.filter(CareCase.case_number.ilike(f"%{case_number}%"))
        elif patient_name:
            query = query.join(Patient).filter(
                or_(
                    (Patient.first_name + " " + Patient.last_name).ilike(f"%{patient_name}%"),
                    Patient.first_name.ilike(f"%{patient_name}%"),
                    Patient.last_name.ilike(f"%{patient_name}%")
                )
            )

        case = query.first()
        if not case:
            return {
                "success": False,
                "error_code": "CASE_NOT_FOUND",
                "message": "Requested patient case could not be located in registry.",
                "autonomy_level": 1
            }

        now = datetime.now(timezone.utc)
        ev = CaseEvent(
            id=uuid.uuid4(),
            case_id=case.id,
            event_type="coordinator_case_selected",
            description=f"Case {case.case_number} selected for active management by {actor_role} ({actor_id or 'coordinator'}).",
            event_data={"actor_role": actor_role, "actor_id": actor_id, "selected_at": now.isoformat()},
            timestamp=now
        )
        db.add(ev)
        db.commit()

        p_name = f"{case.patient.first_name} {case.patient.last_name}" if case.patient else "Patient"
        return {
            "success": True,
            "data": {
                "case_id": str(case.id),
                "case_number": case.case_number,
                "patient_id": str(case.patient_id),
                "patient_name": p_name,
                "status": case.status,
                "priority": case.priority,
                "finding_code": case.screening_result.finding_code if case.screening_result else "N/A",
                "clinical_pathway": case.clinical_pathway
            },
            "message": f"Successfully loaded authorized care context for {p_name} ({case.case_number}).",
            "autonomy_level": 1
        }

    # --------------------------------------------------------------------------
    # Tool: get_case_owner
    # --------------------------------------------------------------------------
    @classmethod
    def get_case_owner(cls, db: Session, case_id: str) -> Dict[str, Any]:
        """Retrieves the designated accountable Care Coordinator for a case."""
        try:
            c_uuid = uuid.UUID(str(case_id))
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        except (ValueError, TypeError):
            case = db.query(CareCase).order_by(CareCase.created_at.desc()).first()
            c_uuid = case.id if case else None
        if not case:
            return ToolExecutionResult(False, None, f"Case {case_id} not found").to_dict()

        if not case.current_owner:
            return ToolExecutionResult(
                True,
                {"case_id": case_id, "owner": None, "is_unassigned_escalated": case.status == "UNASSIGNED_ESCALATED"},
                "Case currently has NO assigned owner. Immediate coordinator assignment required.", 1
            ).to_dict()

        owner = case.current_owner
        return ToolExecutionResult(
            True,
            {
                "case_id": case_id,
                "owner_id": str(owner.id),
                "name": owner.name,
                "role": owner.role,
                "email": owner.email,
                "facility": owner.facility,
                "is_active": owner.is_active,
            },
            f"Accountable Care Coordinator: {owner.name} ({owner.role})", 1
        ).to_dict()

    # --------------------------------------------------------------------------
    # Tool: assign_case_owner
    # --------------------------------------------------------------------------
    @classmethod
    def assign_case_owner(
        cls, db: Session, case_id: str, new_owner_id: str, assigned_by: str, reason: str
    ) -> Dict[str, Any]:
        """Assigns an accountable Care Coordinator and preserves continuous ownership history."""
        c_uuid = uuid.UUID(case_id)
        owner_uuid = uuid.UUID(new_owner_id)

        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return ToolExecutionResult(False, None, f"Case {case_id} not found").to_dict()

        new_owner = db.query(CaseOwner).filter(CaseOwner.id == owner_uuid).first()
        if not new_owner:
            return ToolExecutionResult(False, None, f"Coordinator {new_owner_id} not found").to_dict()

        prev_owner_id = case.current_owner_id
        now = datetime.now(timezone.utc)

        # Deactivate previous active history record
        active_hist = (
            db.query(CaseOwnershipHistory)
            .filter(CaseOwnershipHistory.case_id == c_uuid, CaseOwnershipHistory.is_active.is_(True))
            .all()
        )
        for h in active_hist:
            h.is_active = False
            h.effective_to = now

        # Create new ownership record
        new_hist = CaseOwnershipHistory(
            id=uuid.uuid4(),
            case_id=c_uuid,
            previous_owner_id=prev_owner_id,
            new_owner_id=owner_uuid,
            transferred_by=assigned_by,
            reason=reason,
            effective_from=now,
            is_active=True
        )
        db.add(new_hist)

        # Update case owner & recover from unassigned status
        case.current_owner_id = owner_uuid
        if case.status == "UNASSIGNED_ESCALATED":
            case.status = "recovering"

        # Record timeline event
        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=c_uuid,
            event_type="case_owner_assigned",
            description=f"Case assigned to {new_owner.name} by {assigned_by}. Reason: {reason}",
            event_data={"owner_id": str(owner_uuid), "assigned_by": assigned_by, "reason": reason},
            timestamp=now
        )
        db.add(event)
        db.commit()

        cls.log_audit(
            db, action="ASSIGN_CASE_OWNER", actor_id=assigned_by, autonomy_level=2,
            rationale=f"Assigned accountable coordinator {new_owner.name}. Reason: {reason}",
            case_id=c_uuid, patient_id=case.patient_id,
            previous_state={"current_owner_id": str(prev_owner_id) if prev_owner_id else None},
            new_state={"current_owner_id": str(owner_uuid), "owner_name": new_owner.name}
        )

        return ToolExecutionResult(
            True,
            {"case_id": case_id, "current_owner": new_owner.name, "assigned_by": assigned_by},
            f"Case ownership successfully assigned to {new_owner.name}", 2
        ).to_dict()

    # --------------------------------------------------------------------------
    # Tool: transfer_case_ownership
    # --------------------------------------------------------------------------
    @classmethod
    def transfer_case_ownership(
        cls, db: Session, case_id: str, from_owner_id: str, to_owner_id: str, transferred_by: str, reason: str
    ) -> Dict[str, Any]:
        """Executes an authorized ownership handoff with mandatory reason and audit record."""
        return cls.assign_case_owner(
            db=db,
            case_id=case_id,
            new_owner_id=to_owner_id,
            assigned_by=transferred_by,
            reason=f"Transfer from {from_owner_id}: {reason}"
        )

    # --------------------------------------------------------------------------
    # Tool: get_pending_case_tasks
    # --------------------------------------------------------------------------
    @classmethod
    def get_pending_case_tasks(cls, db: Session, case_id: str) -> Dict[str, Any]:
        """Retrieves outstanding coordination tasks, milestones, and overdue work items."""
        c_uuid = uuid.UUID(case_id)
        now = datetime.now(timezone.utc)

        tasks = (
            db.query(Task)
            .filter(Task.case_id == c_uuid, Task.status.in_(["pending", "in_progress", "overdue"]))
            .all()
        )

        task_list = [
            {
                "id": str(t.id),
                "title": t.title,
                "description": t.description,
                "task_type": t.task_type,
                "assigned_role": t.assigned_role,
                "status": t.status,
                "due_date": t.due_date.isoformat(),
                "is_overdue": _ensure_utc(t.due_date) < now
            }
            for t in tasks
        ]

        return ToolExecutionResult(
            True,
            {"case_id": case_id, "pending_task_count": len(task_list), "tasks": task_list},
            f"Retrieved {len(task_list)} pending tasks", 1
        ).to_dict()

    # --------------------------------------------------------------------------
    # Tool: detect_stalled_case
    # --------------------------------------------------------------------------
    @classmethod
    def detect_stalled_case(cls, db: Session, case_id: str, days_threshold: int = 5) -> Dict[str, Any]:
        """Identifies stalled care journeys with no recorded progress or patient touchpoints."""
        try:
            c_uuid = uuid.UUID(str(case_id))
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        except (ValueError, TypeError):
            case = db.query(CareCase).order_by(CareCase.created_at.desc()).first()
            c_uuid = case.id if case else None
        if not case:
            return ToolExecutionResult(False, None, "Case not found").to_dict()

        if case.status in ["closed", "care_completed"]:
            return ToolExecutionResult(True, {"stalled": False, "reason": "Case already closed"}, "Case is closed", 1).to_dict()

        now = datetime.now(timezone.utc)
        latest_event = (
            db.query(CaseEvent)
            .filter(CaseEvent.case_id == c_uuid)
            .order_by(CaseEvent.timestamp.desc())
            .first()
        )

        last_activity_time = latest_event.timestamp if latest_event else case.updated_at
        days_inactive = (now - _ensure_utc(last_activity_time)).total_seconds() / 86400.0

        is_stalled = days_inactive >= days_threshold

        owner_name = case.current_owner.name if case.current_owner else "Unassigned"

        return ToolExecutionResult(
            True,
            {
                "case_id": case_id,
                "stalled": is_stalled,
                "days_inactive": round(days_inactive, 1),
                "threshold_days": days_threshold,
                "last_activity_at": last_activity_time.isoformat(),
                "accountable_owner": owner_name,
                "recommendation": (
                    f"Notify coordinator {owner_name} to engage patient or trigger recovery play."
                    if is_stalled else "Case progress is on track."
                )
            },
            f"Case {'STALLED' if is_stalled else 'active'}: {round(days_inactive, 1)} days since last progress.", 1
        ).to_dict()

    # --------------------------------------------------------------------------
    # Tool: notify_case_owner
    # --------------------------------------------------------------------------
    @classmethod
    def notify_case_owner(cls, db: Session, case_id: str, priority: str, message: str) -> Dict[str, Any]:
        """Alerts the designated Care Coordinator when action or intervention is required."""
        try:
            c_uuid = uuid.UUID(str(case_id))
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        except (ValueError, TypeError):
            case = db.query(CareCase).order_by(CareCase.created_at.desc()).first()
            c_uuid = case.id if case else None
        if not case:
            return ToolExecutionResult(False, None, "Case not found").to_dict()

        if not case.current_owner:
            # If no owner exists, immediately escalate to unassigned emergency queue
            return cls.escalate_unowned_case(db, case_id, f"Cannot notify owner: {message}")

        now = datetime.now(timezone.utc)
        # Create an alert task assigned to the coordinator
        task = Task(
            id=uuid.uuid4(),
            case_id=c_uuid,
            title=f"[{priority.upper()} ALERT] {message[:60]}",
            description=message,
            task_type="coordinator_alert",
            assigned_to_id=case.current_owner_id,
            assigned_role="care_coordinator",
            status="pending",
            due_date=now + timedelta(hours=24)
        )
        db.add(task)

        # Log timeline event
        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=c_uuid,
            event_type="coordinator_notified",
            description=f"Alert dispatched to {case.current_owner.name}: {message}",
            event_data={"priority": priority, "owner_id": str(case.current_owner_id)},
            timestamp=now
        )
        db.add(event)
        db.commit()

        cls.log_audit(
            db, action="NOTIFY_CASE_OWNER", actor_id="supervisor_agent", autonomy_level=1,
            rationale=f"Notified {case.current_owner.name} of required coordination: {message}",
            case_id=c_uuid, patient_id=case.patient_id
        )

        return ToolExecutionResult(
            True,
            {"task_id": str(task.id), "coordinator": case.current_owner.name, "priority": priority},
            f"Coordinator {case.current_owner.name} notified successfully", 1
        ).to_dict()

    # --------------------------------------------------------------------------
    # Tool: escalate_unowned_case
    # --------------------------------------------------------------------------
    @classmethod
    def escalate_unowned_case(cls, db: Session, case_id: str, reason: str) -> Dict[str, Any]:
        """Places an unowned case into UNASSIGNED_ESCALATED state for immediate supervisor action."""
        try:
            c_uuid = uuid.UUID(str(case_id))
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        except (ValueError, TypeError):
            case = db.query(CareCase).order_by(CareCase.created_at.desc()).first()
            c_uuid = case.id if case else None
        if not case:
            return ToolExecutionResult(False, None, "Case not found").to_dict()

        now = datetime.now(timezone.utc)
        case.status = "UNASSIGNED_ESCALATED"
        case.priority = "critical"

        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=c_uuid,
            event_type="unassigned_case_escalation",
            description=f"EMERGENCY: Case lacks accountable coordinator. Reason: {reason}",
            event_data={"reason": reason},
            timestamp=now
        )
        db.add(event)
        db.commit()

        cls.log_audit(
            db, action="ESCALATE_UNOWNED_CASE", actor_id="supervisor_agent", autonomy_level=2,
            rationale=f"Unowned active case escalated to administrative supervision: {reason}",
            case_id=c_uuid, patient_id=case.patient_id
        )

        return ToolExecutionResult(
            True,
            {"case_id": case_id, "status": "UNASSIGNED_ESCALATED", "priority": "critical"},
            f"Case placed in UNASSIGNED_ESCALATED state: {reason}", 2
        ).to_dict()

    # --------------------------------------------------------------------------
    # Tool: get_case_closure_requirements
    # --------------------------------------------------------------------------
    @classmethod
    def get_case_closure_requirements(cls, db: Session, case_id: str) -> Dict[str, Any]:
        """
        Evaluates the mandatory 5-point checklist required before a case can be closed:
        1. All coordination tasks completed
        2. Relevant closure evidence recorded
        3. Authorized clinical verification signed
        4. Outstanding exceptions resolved
        5. Accountable owner sign-off
        """
        try:
            c_uuid = uuid.UUID(str(case_id))
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        except (ValueError, TypeError):
            case = db.query(CareCase).order_by(CareCase.created_at.desc()).first()
            c_uuid = case.id if case else None
        if not case:
            return ToolExecutionResult(False, None, "Case not found").to_dict()

        # 1. Pending tasks check
        pending_tasks = db.query(Task).filter(Task.case_id == c_uuid, Task.status != "completed").count()

        # 2. Closure evidence check
        evidences = db.query(ClosureEvidence).filter(ClosureEvidence.case_id == c_uuid).all()
        has_evidence = len(evidences) > 0

        # 3. Clinical verification check
        has_verified_evidence = any(e.is_verified for e in evidences)

        # 4. Inferred barriers check
        barriers = (case.case_context or {}).get("inferred_barriers", [])
        unresolved_barriers = len(barriers) > 0 and case.status == "recovering"

        # 5. Accountable owner exists
        has_owner = case.current_owner_id is not None

        checklist = {
            "all_coordination_tasks_completed": pending_tasks == 0,
            "closure_evidence_recorded": has_evidence,
            "clinical_verification_signed": has_verified_evidence,
            "exceptions_resolved": not unresolved_barriers,
            "accountable_owner_present": has_owner,
        }

        missing = [k for k, v in checklist.items() if not v]
        ready = len(missing) == 0

        return ToolExecutionResult(
            True,
            {
                "case_id": case_id,
                "is_ready_for_closure": ready,
                "checklist": checklist,
                "missing_requirements": missing,
                "accountable_owner": case.current_owner.name if case.current_owner else None,
                "governance_rule": "AI cannot close independently. Requires clinician verification and owner sign-off."
            },
            f"Closure Readiness: {'READY' if ready else 'INCOMPLETE'}. Missing: {missing}", 1
        ).to_dict()

    # --------------------------------------------------------------------------
    # Phase 5 Modular Tool Ecosystem Delegations
    # --------------------------------------------------------------------------
    @classmethod
    def retrieve_patient_profile(cls, db: Session, patient_id: str, actor_role: str = "ai_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import RetrievePatientProfileInput
        import app.tools.patient_tools as p_tools
        return p_tools.retrieve_patient_profile(db, RetrievePatientProfileInput(patient_id=patient_id, actor_role=actor_role)).model_dump()

    @classmethod
    def retrieve_patient_preferences(cls, db: Session, patient_id: str, actor_role: str = "ai_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import RetrievePatientPreferencesInput
        import app.tools.patient_tools as p_tools
        return p_tools.retrieve_patient_preferences(db, RetrievePatientPreferencesInput(patient_id=patient_id, actor_role=actor_role)).model_dump()

    @classmethod
    def retrieve_conversation_history(cls, db: Session, patient_id: str, case_id: Optional[str] = None, limit: int = 20, actor_role: str = "ai_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import RetrieveConversationHistoryInput
        import app.tools.patient_tools as p_tools
        return p_tools.retrieve_conversation_history(db, RetrieveConversationHistoryInput(patient_id=patient_id, case_id=case_id, limit=limit, actor_role=actor_role)).model_dump()

    @classmethod
    def create_care_case(cls, db: Session, patient_id: str, screening_result_id: str, clinical_pathway: Optional[str] = None, priority: str = "standard", initial_owner_id: Optional[str] = None, actor_role: str = "care_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import CreateCareCaseInput
        import app.tools.case_tools as c_tools
        return c_tools.create_care_case(db, CreateCareCaseInput(patient_id=patient_id, screening_result_id=screening_result_id, clinical_pathway=clinical_pathway, priority=priority, initial_owner_id=initial_owner_id, actor_role=actor_role)).model_dump()

    @classmethod
    def retrieve_case_details(cls, db: Session, case_id: str, actor_role: str = "ai_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import RetrieveCaseDetailsInput
        import app.tools.case_tools as c_tools
        return c_tools.retrieve_case_details(db, RetrieveCaseDetailsInput(case_id=case_id, actor_role=actor_role)).model_dump()

    @classmethod
    def retrieve_case_events(cls, db: Session, case_id: str, limit: int = 50, actor_role: str = "ai_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import RetrieveCaseEventsInput
        import app.tools.case_tools as c_tools
        return c_tools.retrieve_case_events(db, RetrieveCaseEventsInput(case_id=case_id, limit=limit, actor_role=actor_role)).model_dump()

    @classmethod
    def assign_administrative_ownership(cls, db: Session, case_id: str, new_owner_id: str, assigned_by: str, reason: str, actor_role: str = "care_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import AssignAdministrativeOwnershipInput
        import app.tools.case_tools as c_tools
        return c_tools.assign_administrative_ownership(db, AssignAdministrativeOwnershipInput(case_id=case_id, new_owner_id=new_owner_id, assigned_by=assigned_by, reason=reason, actor_role=actor_role)).model_dump()

    @classmethod
    def draft_patient_message(cls, db: Session, patient_id: str, case_id: str, message_purpose: str, clinical_context: Optional[str] = None, language: Optional[str] = None, actor_role: str = "ai_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import DraftPatientMessageInput
        import app.tools.communication_tools as comm_tools
        return comm_tools.draft_patient_message(db, DraftPatientMessageInput(patient_id=patient_id, case_id=case_id, message_purpose=message_purpose, clinical_context=clinical_context, language=language, actor_role=actor_role)).model_dump()

    @classmethod
    def translate_message(cls, db: Session, text: str, target_language: str, source_language: Optional[str] = "auto", actor_role: str = "ai_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import TranslateMessageInput
        import app.tools.communication_tools as comm_tools
        return comm_tools.translate_message(db, TranslateMessageInput(text=text, target_language=target_language, source_language=source_language, actor_role=actor_role)).model_dump()

    @classmethod
    def send_permitted_communication(cls, db: Session, case_id: str, patient_id: str, content: str, channel: Optional[str] = None, language: Optional[str] = "en", actor_role: str = "ai_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import SendPermittedCommunicationInput
        import app.tools.communication_tools as comm_tools
        return comm_tools.send_permitted_communication(db, SendPermittedCommunicationInput(case_id=case_id, patient_id=patient_id, content=content, channel=channel, language=language, actor_role=actor_role)).model_dump()

    @classmethod
    def record_acknowledgement(cls, db: Session, case_id: str, patient_id: str, acknowledged_via: str = "sms", patient_response: Optional[str] = None, actor_role: str = "ai_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import RecordAcknowledgementInput
        import app.tools.communication_tools as comm_tools
        return comm_tools.record_acknowledgement(db, RecordAcknowledgementInput(case_id=case_id, patient_id=patient_id, acknowledged_via=acknowledged_via, patient_response=patient_response, actor_role=actor_role)).model_dump()

    @classmethod
    def check_referral_status(cls, db: Session, referral_id: str, actor_role: str = "ai_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import CheckReferralStatusInput
        import app.tools.referral_tools as ref_tools
        return ref_tools.check_referral_status(db, CheckReferralStatusInput(referral_id=referral_id, actor_role=actor_role)).model_dump()

    @classmethod
    def retrieve_referral_information(cls, db: Session, case_id: str, actor_role: str = "ai_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import RetrieveReferralInformationInput
        import app.tools.referral_tools as ref_tools
        return ref_tools.retrieve_referral_information(db, RetrieveReferralInformationInput(case_id=case_id, actor_role=actor_role)).model_dump()

    @classmethod
    def reschedule_appointment(cls, db: Session, appointment_id: str, case_id: str, new_scheduled_time: str, reason: str, notes: Optional[str] = None, actor_role: str = "care_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import RescheduleAppointmentInput
        import app.tools.appointment_tools as a_tools
        return a_tools.reschedule_appointment(db, RescheduleAppointmentInput(appointment_id=appointment_id, case_id=case_id, new_scheduled_time=new_scheduled_time, reason=reason, notes=notes, actor_role=actor_role)).model_dump()

    @classmethod
    def retrieve_appointment_status(cls, db: Session, case_id: str, actor_role: str = "ai_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import RetrieveAppointmentStatusInput
        import app.tools.appointment_tools as a_tools
        return a_tools.retrieve_appointment_status(db, RetrieveAppointmentStatusInput(case_id=case_id, actor_role=actor_role)).model_dump()

    @classmethod
    def identify_stalled_cases(cls, db: Session, case_id: Optional[str] = None, days_threshold: int = 5, actor_role: str = "ai_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import IdentifyStalledCasesInput
        import app.tools.recovery_tools as rec_tools
        return rec_tools.identify_stalled_cases(db, IdentifyStalledCasesInput(case_id=case_id, days_threshold=days_threshold, actor_role=actor_role)).model_dump()

    @classmethod
    def propose_recovery_action(cls, db: Session, case_id: str, dropoff_reasons: Optional[List[str]] = None, actor_role: str = "ai_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import ProposeRecoveryActionInput
        import app.tools.recovery_tools as rec_tools
        return rec_tools.propose_recovery_action(db, ProposeRecoveryActionInput(case_id=case_id, dropoff_reasons=dropoff_reasons, actor_role=actor_role)).model_dump()

    @classmethod
    def retrieve_closure_evidence(cls, db: Session, case_id: str, actor_role: str = "ai_coordinator") -> Dict[str, Any]:
        from app.tools.schemas import RetrieveClosureEvidenceInput
        import app.tools.closure_tools as clos_tools
        return clos_tools.retrieve_closure_evidence(db, RetrieveClosureEvidenceInput(case_id=case_id, actor_role=actor_role)).model_dump()
