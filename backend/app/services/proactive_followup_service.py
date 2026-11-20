"""
CareBridge Proactive Follow-Up Service (AI Behaviour B5)
Background job evaluated every 15 minutes per patient:
- UPCOMING (24h and 2h windows, configurable)
- MISSED (start + 30m with no check-in/consultation; never auto-marks NO_SHOW, never completes a stage)
- OVERDUE FOLLOW-UP (follow-up scheduled_date passed without recorded completion)

Every message is idempotent (appointment_id + trigger + version), delivered through the
transactional outbox, respects quiet hours (default 21:00-08:00 local), and is traced.
"""

import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.care_case import CareCase
from app.models.communication import Communication, ConversationSession
from app.models.notification import Notification
from app.services.notification_service import NotificationService
from app.services.task_service import TaskService
from app.workflows.persistence.traces import WorkflowTraceLogger

logger = logging.getLogger("carebridge.services.proactive_followup")

UPCOMING_STATUSES = (
    "CONFIRMED",
    "PENDING_DOCTOR_CONFIRMATION",
    "PENDING_PATIENT_CONFIRMATION",
    "PROPOSED",
    "RESCHEDULE_REQUESTED",
    "booked",
    "confirmed",
)

MISSED_CANDIDATE_STATUSES = ("CONFIRMED", "booked", "confirmed")


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


class ProactiveFollowupService:
    """Idempotent proactive patient follow-up evaluator."""

    @classmethod
    def is_quiet_hours(
        cls,
        now_utc: datetime,
        tz_offset_minutes: Optional[int] = None,
        quiet_start: Optional[int] = None,
        quiet_end: Optional[int] = None,
    ) -> bool:
        """Returns True if local time falls within configured quiet hours (default 21:00-08:00)."""
        offset = settings.FOLLOWUP_TIMEZONE_OFFSET_MINUTES if tz_offset_minutes is None else tz_offset_minutes
        start_h = settings.FOLLOWUP_QUIET_HOURS_START if quiet_start is None else quiet_start
        end_h = settings.FOLLOWUP_QUIET_HOURS_END if quiet_end is None else quiet_end
        local_dt = _utc(now_utc) + timedelta(minutes=offset)
        h = local_dt.hour
        if start_h > end_h:
            return h >= start_h or h < end_h
        return start_h <= h < end_h

    @classmethod
    def _get_or_create_patient_session(
        cls, db: Session, patient_id: uuid.UUID, case_id: uuid.UUID, now: datetime
    ) -> Optional[ConversationSession]:
        p_user = NotificationService.get_patient_user(db, patient_id)
        sess = (
            db.query(ConversationSession)
            .filter(
                ConversationSession.patient_id == patient_id,
                ConversationSession.role == "patient",
                ConversationSession.is_active.is_(True),
            )
            .order_by(ConversationSession.last_interaction_at.desc())
            .first()
        )
        if sess:
            sess.last_interaction_at = now
            return sess
        if not p_user:
            return None
        sess = ConversationSession(
            id=uuid.uuid4(),
            user_id=p_user.id,
            role="patient",
            title="Care Check-In",
            patient_id=patient_id,
            case_id=case_id,
            channel="in_app_chat",
            is_active=True,
            last_interaction_at=now,
        )
        db.add(sess)
        db.flush()
        return sess

    @classmethod
    def _dispatch_patient_followup(
        cls,
        db: Session,
        *,
        case_id: uuid.UUID,
        patient_id: uuid.UUID,
        idempotency_key: str,
        event_type: str,
        title: str,
        message: str,
        trigger: str,
        now: datetime,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Idempotently stages an outbox Notification + AI chat Communication + workflow trace.
        Returns True if a new message was created, False if already sent for this key.
        """
        existing = db.query(Notification).filter(Notification.idempotency_key == idempotency_key).first()
        if existing:
            return False

        p_user = NotificationService.get_patient_user(db, patient_id)
        if not p_user:
            return False

        NotificationService.stage_notification(
            db=db,
            user_id=p_user.id,
            role="patient",
            event_type=event_type,
            title=title,
            message=message,
            priority="normal",
            case_id=case_id,
            patient_id=patient_id,
            action_link="/chat",
            idempotency_key=idempotency_key,
            metadata_json={**(metadata or {}), "trigger": trigger},
        )

        session = cls._get_or_create_patient_session(db, patient_id, case_id, now)
        comm = Communication(
            id=uuid.uuid4(),
            user_id=p_user.id,
            role="patient",
            case_id=case_id,
            patient_id=patient_id,
            session_id=session.id if session else None,
            sender="ai_coordinator",
            channel="in_app_chat",
            language="en",
            content=message,
            acknowledged=False,
            acknowledgement_details={"idempotency_key": idempotency_key, "trigger": trigger},
            sent_at=now,
        )
        db.add(comm)

        try:
            WorkflowTraceLogger.log_node_trace(
                db=db,
                case_id=str(case_id),
                thread_id=f"proactive_followup_{patient_id}",
                run_id=idempotency_key,
                workflow_name="proactive_followup",
                node_name=trigger,
                step_number=1,
                status="completed",
                duration_ms=0.0,
                coordinator_note=f"Dispatched {trigger} check-in ({idempotency_key})",
            )
        except Exception as trace_err:
            logger.debug(f"Follow-up trace notice: {trace_err}")

        return True

    @classmethod
    def evaluate_all(
        cls,
        db: Session,
        *,
        now: Optional[datetime] = None,
        tz_offset_minutes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Evaluates UPCOMING (24h & 2h), MISSED (+30m), and OVERDUE FOLLOW-UP triggers."""
        now_utc = _utc(now) if now else datetime.now(timezone.utc)

        if cls.is_quiet_hours(now_utc, tz_offset_minutes=tz_offset_minutes):
            logger.info("[ProactiveFollowup] Quiet hours active; deferring outbound patient check-ins.")
            return {
                "job_name": "run_proactive_followups",
                "executed_at": now_utc.isoformat(),
                "skipped_quiet_hours": True,
                "upcoming_24h_sent": 0,
                "upcoming_2h_sent": 0,
                "missed_sent": 0,
                "overdue_followup_sent": 0,
                "recovery_tasks_created": 0,
            }

        upcoming_24h_sent = 0
        upcoming_2h_sent = 0
        missed_sent = 0
        overdue_followup_sent = 0
        recovery_tasks_created = 0

        soon_win = timedelta(hours=settings.FOLLOWUP_SOON_HOURS)
        day_win = timedelta(hours=settings.FOLLOWUP_UPCOMING_HOURS)
        missed_grace = timedelta(minutes=settings.FOLLOWUP_MISSED_GRACE_MINUTES)

        # 1. UPCOMING (24h and 2h windows)
        upcoming_appts = (
            db.query(Appointment)
            .filter(
                Appointment.status.in_(UPCOMING_STATUSES),
                Appointment.scheduled_time > now_utc,
                Appointment.scheduled_time <= now_utc + day_win,
            )
            .all()
        )
        for appt in upcoming_appts:
            sched_utc = _utc(appt.scheduled_time)
            delta = sched_utc - now_utc
            if delta <= soon_win:
                trigger = "upcoming_2h"
                when_str = f"in about {max(1, int(delta.total_seconds() // 60))} minutes ({sched_utc.strftime('%H:%M UTC')})"
            else:
                trigger = "upcoming_24h"
                when_str = f"on {sched_utc.strftime('%Y-%m-%d at %H:%M UTC')}"

            idemp_key = f"{appt.id}:{trigger}:v{appt.version}"
            msg = (
                f"Your appointment with {appt.provider_name} is {when_str}. "
                "Would you like help with a ride, someone to come with you, or anything else to prepare?"
            )
            sent = cls._dispatch_patient_followup(
                db,
                case_id=appt.case_id,
                patient_id=appt.patient_id,
                idempotency_key=idemp_key,
                event_type="proactive_followup_upcoming",
                title="Upcoming Appointment Check-In",
                message=msg,
                trigger=trigger,
                now=now_utc,
                metadata={"appointment_id": str(appt.id), "version": appt.version},
            )
            if sent:
                if trigger == "upcoming_2h":
                    upcoming_2h_sent += 1
                else:
                    upcoming_24h_sent += 1

        # 2. MISSED (start + 30m with no attendance/consultation; NEVER auto-mark NO_SHOW or complete stage)
        missed_appts = (
            db.query(Appointment)
            .filter(
                Appointment.status.in_(MISSED_CANDIDATE_STATUSES),
                Appointment.attendance_recorded_at.is_(None),
                Appointment.scheduled_time <= now_utc - missed_grace,
            )
            .all()
        )
        for appt in missed_appts:
            trigger = "missed"
            idemp_key = f"{appt.id}:{trigger}:v{appt.version}"
            msg = (
                "We missed you today. Is everything okay? "
                "I can help find a new time or arrange a ride."
            )
            sent = cls._dispatch_patient_followup(
                db,
                case_id=appt.case_id,
                patient_id=appt.patient_id,
                idempotency_key=idemp_key,
                event_type="proactive_followup_missed",
                title="Missed Appointment Check-In",
                message=msg,
                trigger=trigger,
                now=now_utc,
                metadata={"appointment_id": str(appt.id), "version": appt.version},
            )
            if sent:
                missed_sent += 1
                TaskService.create_recovery_task(
                    db=db,
                    case_id=appt.case_id,
                    patient_id=appt.patient_id,
                    barrier_type="missed_appointment",
                    barrier_description=(
                        f"Patient did not check in within {settings.FOLLOWUP_MISSED_GRACE_MINUTES}m of appointment "
                        f"{appt.id} ({_utc(appt.scheduled_time).strftime('%Y-%m-%d %H:%M UTC')}). "
                        "Gentle AI check-in sent; authorized staff must confirm any NO_SHOW status."
                    ),
                    idempotency_key=f"recovery_missed_{appt.id}_v{appt.version}",
                    priority="urgent",
                )
                recovery_tasks_created += 1

        # 3. OVERDUE FOLLOW-UP (follow_up.scheduled_date passed without recorded follow-up)
        open_cases = (
            db.query(CareCase)
            .filter(CareCase.status.notin_(("closed", "VERIFIED_CLINICAL_CLOSURE")))
            .all()
        )
        for case in open_cases:
            fu = (case.case_context or {}).get("follow_up") or {}
            sched_raw = fu.get("scheduled_date")
            if not sched_raw or fu.get("status") == "completed":
                continue
            try:
                fu_dt = _utc(datetime.fromisoformat(str(sched_raw).replace("Z", "+00:00")))
            except Exception:
                continue
            if fu_dt > now_utc - missed_grace:
                continue

            trigger = "overdue_followup"
            idemp_key = f"{case.id}:{trigger}:v{case.version}:{fu_dt.strftime('%Y%m%d')}"
            msg = (
                "We noticed your follow-up date has passed and wanted to check in. "
                "Is everything okay? I can help find a new time or arrange a ride."
            )
            sent = cls._dispatch_patient_followup(
                db,
                case_id=case.id,
                patient_id=case.patient_id,
                idempotency_key=idemp_key,
                event_type="proactive_followup_overdue",
                title="Overdue Follow-Up Check-In",
                message=msg,
                trigger=trigger,
                now=now_utc,
                metadata={"follow_up_date": fu_dt.isoformat()},
            )
            if sent:
                overdue_followup_sent += 1
                TaskService.create_recovery_task(
                    db=db,
                    case_id=case.id,
                    patient_id=case.patient_id,
                    barrier_type="overdue_followup",
                    barrier_description=(
                        f"Scheduled follow-up ({fu_dt.strftime('%Y-%m-%d')}) passed with no recorded follow-up "
                        f"on case {case.case_number}. Gentle AI check-in sent."
                    ),
                    idempotency_key=f"recovery_overdue_fu_{case.id}_{fu_dt.strftime('%Y%m%d')}",
                    priority="urgent",
                )
                recovery_tasks_created += 1

        db.commit()
        return {
            "job_name": "run_proactive_followups",
            "executed_at": now_utc.isoformat(),
            "skipped_quiet_hours": False,
            "upcoming_24h_sent": upcoming_24h_sent,
            "upcoming_2h_sent": upcoming_2h_sent,
            "missed_sent": missed_sent,
            "overdue_followup_sent": overdue_followup_sent,
            "recovery_tasks_created": recovery_tasks_created,
        }
