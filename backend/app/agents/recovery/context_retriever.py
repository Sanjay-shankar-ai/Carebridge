"""
CareBridge Multi-Source Context Retriever (Phase 7)
Retrieves comprehensive 8-dimensional operational and clinical context:
1. Case history & events
2. Patient conversations & messages
3. Previous communication attempts
4. Referral status & clinic handoffs
5. Appointment history (no-shows, cancellations, attendance)
6. Patient preferences (language, channel, caregiver, accessibility)
7. Outstanding tasks & overdue milestones
8. SLA context & deadline telemetry
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.care_case import CareCase, Task
from app.models.patient import Patient
from app.models.communication import Communication, ConversationSession
from app.models.referral import Referral
from app.models.appointment import Appointment
from app.models.event_audit import CaseEvent
from app.workflows.rules import _ensure_utc, evaluate_sla_status

logger = logging.getLogger("carebridge.recovery.context")


class MultiSourceContextRetriever:
    """Retrieves and consolidates all 8 operational context dimensions for care recovery reasoning."""

    @classmethod
    def retrieve_full_context(cls, db: Session, case_id: str) -> Dict[str, Any]:
        """
        Retrieves the complete 8-source context dictionary for a given case_id.
        """
        c_uuid = uuid.UUID(case_id) if isinstance(case_id, str) else case_id
        now = datetime.now(timezone.utc)

        # 1. Case Record
        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            raise ValueError(f"Care case {case_id} not found")

        # Patient Record
        patient = db.query(Patient).filter(Patient.id == case.patient_id).first()
        if not patient:
            raise ValueError(f"Patient {case.patient_id} not found for case {case_id}")

        # -------------------------------------------------------------
        # Source 1: Case History & Events
        # -------------------------------------------------------------
        events = (
            db.query(CaseEvent)
            .filter(CaseEvent.case_id == c_uuid)
            .order_by(CaseEvent.timestamp.asc())
            .all()
        )
        events_list = [
            {
                "event_id": str(e.id),
                "event_type": e.event_type,
                "description": e.description,
                "event_data": e.event_data or {},
                "timestamp": e.timestamp.isoformat() if e.timestamp else None
            }
            for e in events
        ]
        owner_name = case.current_owner.name if case.current_owner else "Unassigned"
        ctx_data = dict(case.case_context or {})
        case_history = {
            "case_id": str(case.id),
            "case_number": case.case_number,
            "status": case.status,
            "priority": case.priority,
            "pathway": getattr(case, "clinical_pathway", "general"),
            "case_notes": ctx_data.get("notes", []),
            "case_context": ctx_data,
            "created_at": case.created_at.isoformat() if case.created_at else None,
            "updated_at": case.updated_at.isoformat() if case.updated_at else None,
            "current_owner_id": str(case.current_owner_id) if case.current_owner_id else None,
            "current_owner_name": owner_name,
            "events_count": len(events_list),
            "timeline": events_list
        }

        # -------------------------------------------------------------
        # Source 2: Patient Conversations & Messages
        # -------------------------------------------------------------
        comms = (
            db.query(Communication)
            .filter(Communication.case_id == c_uuid)
            .order_by(Communication.created_at.asc())
            .all()
        )
        conv_sessions = (
            db.query(ConversationSession)
            .filter(ConversationSession.patient_id == patient.id)
            .order_by(ConversationSession.created_at.desc())
            .all()
        )
        patient_messages = [
            {
                "id": str(c.id),
                "sender": c.sender,
                "channel": c.channel,
                "language": c.language,
                "content": c.content,
                "acknowledged": c.acknowledged,
                "sent_at": c.sent_at.isoformat() if c.sent_at else None
            }
            for c in comms
        ]
        active_session = conv_sessions[0] if conv_sessions else None
        conversation_context = {
            "total_messages": len(comms),
            "messages": patient_messages,
            "latest_patient_message": next(
                (c.content for c in reversed(comms) if c.sender == "patient"), None
            ),
            "active_session_id": str(active_session.id) if active_session else None,
            "session_unanswered_questions": active_session.unanswered_questions if active_session else [],
            "session_commitments": active_session.patient_commitments if active_session else []
        }

        # -------------------------------------------------------------
        # Source 3: Previous Communication Attempts
        # -------------------------------------------------------------
        outreach_attempts = [c for c in comms if c.sender in ("ai_coordinator", "human_coordinator")]
        inbound_replies = [c for c in comms if c.sender == "patient"]
        last_outreach = outreach_attempts[-1] if outreach_attempts else None
        last_reply = inbound_replies[-1] if inbound_replies else None

        hours_since_last_outreach = None
        if last_outreach and last_outreach.sent_at:
            hours_since_last_outreach = (now - _ensure_utc(last_outreach.sent_at)).total_seconds() / 3600.0

        previous_attempts = {
            "outreach_count": len(outreach_attempts),
            "inbound_reply_count": len(inbound_replies),
            "has_replied": len(inbound_replies) > 0,
            "last_outreach_at": last_outreach.sent_at.isoformat() if last_outreach and last_outreach.sent_at else None,
            "last_outreach_channel": last_outreach.channel if last_outreach else None,
            "hours_since_last_outreach": round(hours_since_last_outreach, 1) if hours_since_last_outreach is not None else None,
            "last_reply_at": last_reply.sent_at.isoformat() if last_reply and last_reply.sent_at else None,
            "channels_used": list(set(c.channel for c in outreach_attempts))
        }

        # -------------------------------------------------------------
        # Source 4: Referral Status & Clinic Handoffs
        # -------------------------------------------------------------
        referrals = (
            db.query(Referral)
            .filter(Referral.case_id == c_uuid)
            .order_by(Referral.created_at.desc())
            .all()
        )
        referral_list = []
        is_referral_stalled = False
        for ref in referrals:
            ref_deadline = _ensure_utc(ref.acceptance_deadline)
            is_overdue = now > ref_deadline and ref.status in ("draft", "sent")
            if is_overdue or (ref.status == "sent" and (now - _ensure_utc(ref.created_at)).total_seconds() > 172800):
                is_referral_stalled = True
            referral_list.append({
                "referral_id": str(ref.id),
                "specialty": ref.specialty,
                "target_facility": ref.target_facility,
                "status": ref.status,
                "reason": ref.reason_for_referral,
                "rejection_reason": ref.rejection_reason,
                "acceptance_deadline": ref.acceptance_deadline.isoformat() if ref.acceptance_deadline else None,
                "is_overdue": is_overdue,
                "created_at": ref.created_at.isoformat() if ref.created_at else None
            })
        referral_status = {
            "total_referrals": len(referrals),
            "active_referral": referral_list[0] if referral_list else None,
            "is_stalled": is_referral_stalled,
            "all_referrals": referral_list
        }

        # -------------------------------------------------------------
        # Source 5: Appointment History
        # -------------------------------------------------------------
        appointments = (
            db.query(Appointment)
            .filter(Appointment.case_id == c_uuid)
            .order_by(Appointment.scheduled_time.desc())
            .all()
        )
        app_list = []
        no_show_count = 0
        cancelled_count = 0
        attended_count = 0
        has_active_booked = False

        for app in appointments:
            if app.status == "no_show":
                no_show_count += 1
            elif app.status == "cancelled":
                cancelled_count += 1
            elif app.status == "attended":
                attended_count += 1
            elif app.status == "booked":
                has_active_booked = True

            app_list.append({
                "appointment_id": str(app.id),
                "facility": app.facility,
                "provider_name": app.provider_name,
                "appointment_type": app.appointment_type,
                "scheduled_time": app.scheduled_time.isoformat() if app.scheduled_time else None,
                "status": app.status,
                "cancellation_reason": app.cancellation_reason,
                "cancellation_outcome": app.cancellation_outcome,
                "rescheduled_from_id": str(app.rescheduled_from_id) if app.rescheduled_from_id else None
            })

        latest_appointment = app_list[0] if app_list else None
        appointment_history = {
            "total_appointments": len(appointments),
            "attended_count": attended_count,
            "no_show_count": no_show_count,
            "cancelled_count": cancelled_count,
            "has_active_booked": has_active_booked,
            "latest_appointment": latest_appointment,
            "appointments": app_list
        }

        # -------------------------------------------------------------
        # Source 6: Patient Preferences & Profile Context
        # -------------------------------------------------------------
        p_ctx = patient.patient_context or {}
        patient_preferences = {
            "patient_id": str(patient.id),
            "full_name": f"{patient.first_name} {patient.last_name}",
            "phone": patient.phone,
            "preferred_language": patient.preferred_language or "en",
            "communication_channel": patient.communication_channel or "sms",
            "accessibility_requirements": patient.accessibility_requirements or {},
            "caregiver_name": p_ctx.get("caregiver_name"),
            "caregiver_phone": p_ctx.get("caregiver_phone"),
            "transportation_support_needed": not p_ctx.get("transportation_support", True),
            "profile_known_barriers": p_ctx.get("known_barriers", [])
        }

        # -------------------------------------------------------------
        # Source 7: Outstanding Tasks & Overdue Milestones
        # -------------------------------------------------------------
        tasks = (
            db.query(Task)
            .filter(Task.case_id == c_uuid)
            .order_by(Task.due_date.asc())
            .all()
        )
        pending_tasks = []
        overdue_tasks = []
        for t in tasks:
            t_due = _ensure_utc(t.due_date)
            is_overdue = t.status == "pending" and now > t_due
            t_dict = {
                "task_id": str(t.id),
                "title": t.title,
                "task_type": t.task_type,
                "status": t.status,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "assigned_role": t.assigned_role,
                "is_overdue": is_overdue
            }
            if t.status == "pending":
                pending_tasks.append(t_dict)
            if is_overdue:
                overdue_tasks.append(t_dict)

        outstanding_tasks = {
            "total_tasks": len(tasks),
            "pending_count": len(pending_tasks),
            "overdue_count": len(overdue_tasks),
            "pending_tasks": pending_tasks,
            "overdue_tasks": overdue_tasks
        }

        # -------------------------------------------------------------
        # Source 8: SLA Context & Telemetry
        # -------------------------------------------------------------
        sla_deadline = _ensure_utc(case.sla_deadline)
        sla_status = evaluate_sla_status(sla_deadline, now)
        hours_remaining = (sla_deadline - now).total_seconds() / 3600.0

        # Calculate inactivity
        latest_event = events[-1] if events else None
        last_activity_time = latest_event.timestamp if latest_event else case.updated_at
        days_inactive = (now - _ensure_utc(last_activity_time)).total_seconds() / 86400.0

        sla_context = {
            "urgency": case.priority,
            "sla_deadline": sla_deadline.isoformat(),
            "sla_status": sla_status,
            "hours_remaining": round(hours_remaining, 1),
            "is_breached": sla_status == "breached",
            "is_warning": sla_status == "warning",
            "days_inactive": round(days_inactive, 1)
        }

        # Aggregate full 8 dimensions
        return {
            "case_history": case_history,
            "patient_conversations": conversation_context,
            "previous_communication_attempts": previous_attempts,
            "referral_status": referral_status,
            "appointment_history": appointment_history,
            "patient_preferences": patient_preferences,
            "outstanding_tasks": outstanding_tasks,
            "sla_context": sla_context
        }
