"""
CareBridge Appointment Domain Service
Enforces the 10-state appointment machine, dual-confirmation with versioning,
double-booking conflict detection, post-closure booking guards, and lifecycle advancement.

States:
  PROPOSED
  PENDING_DOCTOR_CONFIRMATION
  PENDING_PATIENT_CONFIRMATION
  CONFIRMED
  DECLINED_BY_DOCTOR
  DECLINED_BY_PATIENT
  RESCHEDULE_REQUESTED
  CANCELLED
  COMPLETED
  NO_SHOW
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_

from app.models.appointment import Appointment
from app.models.care_case import CareCase
from app.models.patient import Patient
from app.models.event_audit import CaseEvent, AuditLog

logger = logging.getLogger("carebridge.services.appointment")


class AppointmentError(Exception):
    """Base exception for appointment domain errors."""
    pass


class AppointmentConflictError(AppointmentError):
    """Raised when double-booking or provider/patient schedule collision occurs."""
    pass


class AppointmentClosedCaseError(AppointmentError):
    """Raised when an appointment is proposed for an already closed case."""
    pass


class AppointmentConfirmationError(AppointmentError):
    """Raised when version mismatch or invalid actor attempts confirmation."""
    pass


class AppointmentService:
    """Authoritative appointment domain service."""

    @classmethod
    def check_schedule_conflict(
        cls,
        db: Session,
        provider_name: str,
        patient_id: uuid.UUID,
        scheduled_time: datetime,
        exclude_appointment_id: Optional[uuid.UUID] = None,
        buffer_minutes: int = 30
    ) -> None:
        """
        Verifies neither the provider nor the patient is double-booked within the buffer window.
        """
        start_win = scheduled_time - timedelta(minutes=buffer_minutes)
        end_win = scheduled_time + timedelta(minutes=buffer_minutes)

        active_statuses = [
            "PROPOSED",
            "PENDING_DOCTOR_CONFIRMATION",
            "PENDING_PATIENT_CONFIRMATION",
            "CONFIRMED",
            "booked",
            "confirmed"
        ]

        # Check provider conflict
        prov_query = db.query(Appointment).filter(
            Appointment.provider_name == provider_name,
            Appointment.status.in_(active_statuses),
            Appointment.scheduled_time >= start_win,
            Appointment.scheduled_time <= end_win
        )
        if exclude_appointment_id:
            prov_query = prov_query.filter(Appointment.id != exclude_appointment_id)

        prov_conflict = prov_query.first()
        if prov_conflict:
            raise AppointmentConflictError(
                f"Provider {provider_name} already has an appointment booked at "
                f"{prov_conflict.scheduled_time.isoformat()} (conflict within {buffer_minutes}m buffer)."
            )

        # Check patient conflict
        pat_query = db.query(Appointment).filter(
            Appointment.patient_id == patient_id,
            Appointment.status.in_(active_statuses),
            Appointment.scheduled_time >= start_win,
            Appointment.scheduled_time <= end_win
        )
        if exclude_appointment_id:
            pat_query = pat_query.filter(Appointment.id != exclude_appointment_id)

        pat_conflict = pat_query.first()
        if pat_conflict:
            raise AppointmentConflictError(
                f"Patient already has an appointment booked at {pat_conflict.scheduled_time.isoformat()}."
            )

    @classmethod
    def create_appointment_proposal(
        cls,
        db: Session,
        case_id: uuid.UUID,
        patient_id: uuid.UUID,
        facility: str,
        provider_name: str,
        appointment_type: str,
        scheduled_time: datetime,
        proposed_by_role: str = "care_coordinator",
        proposed_by_id: Optional[str] = None,
        notes: Optional[str] = None,
        idempotency_key: Optional[str] = None
    ) -> Appointment:
        """
        Creates a proposed appointment in PROPOSED status at version 1.
        Validates case is not closed and verifies zero provider/patient schedule collisions.
        """
        case = db.query(CareCase).filter(CareCase.id == case_id).first()
        if not case:
            raise ValueError(f"Case {case_id} not found")

        if case.status in ("closed", "VERIFIED_CLINICAL_CLOSURE"):
            raise AppointmentClosedCaseError(
                f"Cannot create appointment on closed case {case.case_number} without authorized reopening."
            )

        # Check idempotency
        if idempotency_key:
            existing = db.query(Appointment).filter(Appointment.idempotency_key == idempotency_key).first()
            if existing:
                return existing

        # Check collision
        cls.check_schedule_conflict(db, provider_name, patient_id, scheduled_time)

        now = datetime.now(timezone.utc)
        appt = Appointment(
            id=uuid.uuid4(),
            case_id=case_id,
            patient_id=patient_id,
            facility=facility,
            provider_name=provider_name,
            appointment_type=appointment_type,
            scheduled_time=scheduled_time,
            status="PROPOSED",
            version=1,
            doctor_confirmed=False,
            patient_confirmed=False,
            proposed_by_role=proposed_by_role,
            proposed_by_id=proposed_by_id,
            notes=notes,
            idempotency_key=idempotency_key
        )
        db.add(appt)

        # Log case event
        ev = CaseEvent(
            id=uuid.uuid4(),
            case_id=case_id,
            event_type="appointment_proposed",
            description=f"Appointment proposed: {appointment_type} with {provider_name} at {facility}",
            event_data={
                "appointment_id": str(appt.id),
                "scheduled_time": scheduled_time.isoformat(),
                "proposed_by": proposed_by_role,
                "version": 1
            },
            timestamp=now
        )
        db.add(ev)

        return appt

    @classmethod
    def confirm_appointment(
        cls,
        db: Session,
        appointment_id: uuid.UUID,
        actor_role: str,
        actor_id: str,
        version: int
    ) -> Appointment:
        """
        Records a doctor or patient confirmation for an appointment.
        CONFIRMED requires doctor AND patient confirming the exact same appointment version.
        """
        appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if not appt:
            raise ValueError(f"Appointment {appointment_id} not found")

        case = db.query(CareCase).filter(CareCase.id == appt.case_id).first()
        if case and case.status in ("closed", "VERIFIED_CLINICAL_CLOSURE"):
            raise AppointmentClosedCaseError("Cannot confirm appointment on closed case.")

        if version != appt.version:
            raise AppointmentConfirmationError(
                f"Version mismatch: Attempted to confirm version {version}, but current appointment is version {appt.version}."
            )

        now = datetime.now(timezone.utc)
        norm_role = actor_role.lower()

        if norm_role in ("doctor", "clinician", "specialist"):
            appt.doctor_confirmed = True
            appt.doctor_confirmed_at = now
            appt.doctor_confirmed_version = version
        elif norm_role in ("patient",):
            appt.patient_confirmed = True
            appt.patient_confirmed_at = now
            appt.patient_confirmed_version = version
        else:
            raise AppointmentConfirmationError(
                f"Role '{actor_role}' is not authorized to confirm appointments directly. Must be doctor or patient."
            )

        # Dual Confirmation Check
        if (
            appt.doctor_confirmed
            and appt.patient_confirmed
            and appt.doctor_confirmed_version == appt.version
            and appt.patient_confirmed_version == appt.version
        ):
            appt.status = "CONFIRMED"

            # Advance Lifecycle Stage 9 if available
            try:
                from app.services.lifecycle_service import LifecycleService
                LifecycleService.advance_stage(
                    db=db,
                    case_id=appt.case_id,
                    stage_ident=9,
                    actor_role=actor_role,
                    actor_id=actor_id,
                    evidence={
                        "appointment_id": str(appt.id),
                        "status": "CONFIRMED",
                        "version": appt.version,
                        "scheduled_time": appt.scheduled_time.isoformat(),
                        "facility": appt.facility,
                        "provider_name": appt.provider_name
                    },
                    notes=f"Dual confirmation verified for version {appt.version}."
                )
            except Exception as e:
                logger.warning(f"Could not auto-advance lifecycle stage 9: {e}")

        elif appt.doctor_confirmed and not appt.patient_confirmed:
            appt.status = "PENDING_PATIENT_CONFIRMATION"
        elif appt.patient_confirmed and not appt.doctor_confirmed:
            appt.status = "PENDING_DOCTOR_CONFIRMATION"

        return appt

    @classmethod
    def reschedule_appointment(
        cls,
        db: Session,
        appointment_id: uuid.UUID,
        new_scheduled_time: datetime,
        actor_role: str,
        actor_id: str,
        reason: Optional[str] = None
    ) -> Appointment:
        """
        Reschedules an appointment: increments version, resets confirmations, and validates conflicts.
        """
        appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if not appt:
            raise ValueError(f"Appointment {appointment_id} not found")

        case = db.query(CareCase).filter(CareCase.id == appt.case_id).first()
        if case and case.status in ("closed", "VERIFIED_CLINICAL_CLOSURE"):
            raise AppointmentClosedCaseError("Cannot reschedule appointment on closed case.")

        cls.check_schedule_conflict(db, appt.provider_name, appt.patient_id, new_scheduled_time, exclude_appointment_id=appt.id)

        now = datetime.now(timezone.utc)
        appt.scheduled_time = new_scheduled_time
        appt.version += 1
        appt.status = "RESCHEDULE_REQUESTED"
        appt.notes = f"{appt.notes or ''}\nRescheduled by {actor_role} to {new_scheduled_time.isoformat()} (v{appt.version}): {reason or 'No reason provided'}".strip()

        # Reset confirmations for the new version
        appt.doctor_confirmed = False
        appt.doctor_confirmed_at = None
        appt.doctor_confirmed_version = None
        appt.patient_confirmed = False
        appt.patient_confirmed_at = None
        appt.patient_confirmed_version = None

        norm_role = actor_role.lower()
        if norm_role in ("doctor", "clinician"):
            appt.doctor_confirmed = True
            appt.doctor_confirmed_at = now
            appt.doctor_confirmed_version = appt.version
            appt.status = "PENDING_PATIENT_CONFIRMATION"
        elif norm_role == "patient":
            appt.patient_confirmed = True
            appt.patient_confirmed_at = now
            appt.patient_confirmed_version = appt.version
            appt.status = "PENDING_DOCTOR_CONFIRMATION"

        # Automatically resync any active transport request for this appointment
        try:
            from app.services.transport_service import TransportService
            TransportService.sync_on_reschedule(db, appt)
        except Exception as sync_err:
            logger.warning(f"Transport resync notice on reschedule: {sync_err}")

        # Notify assigned doctor of the rescheduled version
        try:
            from app.services.notification_service import NotificationService
            new_utc = new_scheduled_time.replace(tzinfo=timezone.utc) if new_scheduled_time.tzinfo is None else new_scheduled_time.astimezone(timezone.utc)
            for d_user in NotificationService.get_assigned_doctor_users(db, appt.case_id, provider_name=appt.provider_name):
                NotificationService.stage_notification(
                    db=db,
                    user_id=d_user.id,
                    role=d_user.role,
                    event_type="appointment_rescheduled",
                    title="Appointment Rescheduled — Confirmation Needed",
                    message=(
                        f"Appointment moved to {new_utc.strftime('%Y-%m-%d %H:%M UTC')} "
                        f"(v{appt.version}). Reason: {reason or 'Schedule update'}. Please confirm."
                    ),
                    priority="normal",
                    case_id=appt.case_id,
                    patient_id=appt.patient_id,
                    action_link=f"/cases/{appt.case_id}",
                    idempotency_key=f"appt_resched_doc_{d_user.id}_{appt.id}_v{appt.version}",
                    metadata_json={"appointment_id": str(appt.id), "version": appt.version},
                )
        except Exception as notif_err:
            logger.warning(f"Doctor reschedule notification notice: {notif_err}")

        return appt

    @classmethod
    def decline_appointment(
        cls,
        db: Session,
        appointment_id: uuid.UUID,
        actor_role: str,
        actor_id: str,
        reason: str
    ) -> Appointment:
        """Records doctor or patient decline."""
        appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if not appt:
            raise ValueError(f"Appointment {appointment_id} not found")

        norm_role = actor_role.lower()
        if norm_role in ("doctor", "clinician"):
            appt.status = "DECLINED_BY_DOCTOR"
        else:
            appt.status = "DECLINED_BY_PATIENT"

        appt.cancellation_reason = reason
        return appt

    @classmethod
    def record_consultation_completion(
        cls,
        db: Session,
        appointment_id: uuid.UUID,
        doctor_id: str,
        doctor_name: str,
        consultation_notes: str,
        procedure_performed: Optional[str] = None
    ) -> Appointment:
        """
        Marks appointment as COMPLETED, records attendance timestamp,
        and advances lifecycle Stage 10 (CONSULTATION_COMPLETED).
        """
        appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if not appt:
            raise ValueError(f"Appointment {appointment_id} not found")

        now = datetime.now(timezone.utc)
        appt.status = "COMPLETED"
        appt.attendance_recorded_at = now

        # Advance Stage 10
        from app.services.lifecycle_service import LifecycleService
        LifecycleService.advance_stage(
            db=db,
            case_id=appt.case_id,
            stage_ident=10,
            actor_role="doctor",
            actor_id=doctor_id,
            actor_name=doctor_name,
            evidence={
                "appointment_id": str(appt.id),
                "consultation_notes": consultation_notes,
                "procedure_performed": procedure_performed or appt.appointment_type,
                "completed_at": now.isoformat()
            },
            notes=f"Consultation completed by Dr. {doctor_name}"
        )

        return appt

    @classmethod
    def get_available_slots(
        cls,
        db: Session,
        doctor: Any,
        constraints: Optional[Dict[str, Any]] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Tool `get_available_slots(doctor, constraints)` (B3).
        Returns up to `limit` REAL slots from the doctor's persisted schedule_slots in PostgreSQL,
        excluding past times and colliding appointments. NEVER invents slots.
        """
        from app.models.owner import CaseOwner

        constraints = constraints or {}
        doc_owner = None
        if isinstance(doctor, CaseOwner):
            doc_owner = doctor
        else:
            doc_str = str(doctor or "").strip()
            try:
                doc_uuid = uuid.UUID(doc_str)
                doc_owner = db.query(CaseOwner).filter(CaseOwner.id == doc_uuid).first()
            except (ValueError, TypeError):
                doc_owner = None
            if not doc_owner and doc_str:
                doc_owner = db.query(CaseOwner).filter(CaseOwner.name == doc_str).first()
            if not doc_owner and doc_str:
                doc_owner = db.query(CaseOwner).filter(CaseOwner.name.ilike(f"%{doc_str}%")).first()

        if not doc_owner or not doc_owner.is_active or doc_owner.on_leave:
            return []

        raw_slots = (doc_owner.working_hours or {}).get("schedule_slots") or []
        if not raw_slots:
            return []

        now = datetime.now(timezone.utc)
        time_of_day = (constraints.get("time_of_day") or "").lower().strip()
        wanted_days = [d.lower().strip() for d in (constraints.get("days") or []) if d]
        weekday_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

        active_statuses = (
            "PROPOSED", "PENDING_DOCTOR_CONFIRMATION", "PENDING_PATIENT_CONFIRMATION",
            "CONFIRMED", "RESCHEDULE_REQUESTED", "booked", "confirmed",
        )
        booked = (
            db.query(Appointment)
            .filter(
                Appointment.provider_name == doc_owner.name,
                Appointment.status.in_(active_statuses),
                Appointment.scheduled_time >= now - timedelta(hours=1),
            )
            .all()
        )
        booked_times = [
            b.scheduled_time.replace(tzinfo=timezone.utc) if b.scheduled_time.tzinfo is None else b.scheduled_time.astimezone(timezone.utc)
            for b in booked
        ]

        results: List[Dict[str, Any]] = []
        for s in raw_slots:
            try:
                dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
            except Exception:
                continue

            if dt <= now + timedelta(minutes=15):
                continue

            if any(abs((dt - bt).total_seconds()) < 1800 for bt in booked_times):
                continue

            day_name = weekday_names[dt.weekday()]
            if wanted_days:
                if "weekend" in wanted_days and day_name not in ("saturday", "sunday"):
                    continue
                if "weekday" in wanted_days and day_name in ("saturday", "sunday"):
                    continue
                explicit_days = [d for d in wanted_days if d in weekday_names]
                if explicit_days and day_name not in explicit_days:
                    continue

            hour = dt.hour
            if time_of_day == "morning" and not (6 <= hour < 12):
                continue
            if time_of_day == "afternoon" and not (12 <= hour < 17):
                continue
            if time_of_day == "evening" and not (17 <= hour <= 22):
                continue

            results.append({
                "iso": dt.isoformat(),
                "display": dt.strftime("%A %Y-%m-%d at %H:%M UTC"),
                "hhmm": dt.strftime("%H:%M"),
                "day": day_name,
                "provider_name": doc_owner.name,
                "facility": doc_owner.facility,
            })
            if len(results) >= limit:
                break

        return results

    @classmethod
    def cancel_appointment(
        cls,
        db: Session,
        appointment_id: Any,
        reason: str,
        *,
        reason_category: Optional[str] = None,
        patient_id: Optional[Any] = None,
        actor_role: str = "patient",
        actor_id: str = "patient",
    ) -> Dict[str, Any]:
        """
        Cancels an appointment -> status CANCELLED, stores cancellation_reason, notifies doctor AND
        coordinator through the outbox, opens a Recovery Agent task within SLA, cancels linked
        transport, and NEVER closes a case or completes a lifecycle stage.
        """
        from app.core.config import settings
        from app.models.transport import TransportRequest
        from app.services.notification_service import NotificationService
        from app.services.task_service import TaskService

        appt_uuid = appointment_id if isinstance(appointment_id, uuid.UUID) else uuid.UUID(str(appointment_id))
        appt = db.query(Appointment).filter(Appointment.id == appt_uuid).first()
        if not appt:
            return {"success": False, "error": f"Appointment {appointment_id} not found."}

        if patient_id is not None:
            pid = patient_id if isinstance(patient_id, uuid.UUID) else uuid.UUID(str(patient_id))
            if appt.patient_id != pid:
                raise PermissionError("Forbidden: Cannot cancel another patient's appointment.")

        now = datetime.now(timezone.utc)
        prev_status = appt.status
        stored_reason = f"{reason_category}: {reason}" if (reason_category and reason_category not in reason.lower()) else reason
        appt.status = "CANCELLED"
        appt.cancellation_reason = stored_reason
        appt.cancellation_outcome = "recovery_pending"

        active_trs = (
            db.query(TransportRequest)
            .filter(
                TransportRequest.appointment_id == appt.id,
                TransportRequest.status.in_(("REQUESTED", "CONFIRMED")),
            )
            .all()
        )
        for tr in active_trs:
            tr.status = "CANCELLED"

        case = db.query(CareCase).filter(CareCase.id == appt.case_id).first()
        patient = db.query(Patient).filter(Patient.id == appt.patient_id).first()
        p_name = f"{patient.first_name} {patient.last_name}" if patient else "Patient"

        if case:
            ctx = dict(case.case_context or {})
            hist = list(ctx.get("cancellation_history") or [])
            hist.append({
                "appointment_id": str(appt.id),
                "cancelled_at": now.isoformat(),
                "reason_category": reason_category or "other",
                "reason": stored_reason,
                "previous_status": prev_status,
            })
            ctx["cancellation_history"] = hist
            case.case_context = ctx

        recovery_task = TaskService.create_recovery_task(
            db=db,
            case_id=appt.case_id,
            patient_id=appt.patient_id,
            barrier_type=reason_category or "appointment_cancelled",
            barrier_description=(
                f"Appointment {appt.id} was cancelled by {actor_role}. Reason: {stored_reason}. "
                f"Re-engage patient within {settings.RECOVERY_REENGAGE_SLA_HOURS}h SLA."
            ),
            idempotency_key=f"recovery_cancel_{appt.id}_v{appt.version}",
            priority="urgent",
        )
        recovery_task.due_date = now + timedelta(hours=settings.RECOVERY_REENGAGE_SLA_HOURS)

        for c_user in NotificationService.get_coordinator_users(db):
            NotificationService.stage_notification(
                db=db,
                user_id=c_user.id,
                role="care_coordinator",
                event_type="appointment_cancelled",
                title="Appointment Cancelled — Recovery Needed",
                message=f"{p_name} cancelled their appointment. Reason: {stored_reason}. Recovery task opened.",
                priority="urgent",
                case_id=appt.case_id,
                patient_id=appt.patient_id,
                action_link=f"/cases/{appt.case_id}",
                idempotency_key=f"cancel_coord_{c_user.id}_{appt.id}_v{appt.version}",
                metadata_json={"appointment_id": str(appt.id), "reason": stored_reason},
            )

        for d_user in NotificationService.get_assigned_doctor_users(db, appt.case_id, provider_name=appt.provider_name):
            NotificationService.stage_notification(
                db=db,
                user_id=d_user.id,
                role=d_user.role,
                event_type="appointment_cancelled",
                title="Patient Appointment Cancelled",
                message=f"Appointment for {p_name} has been cancelled. Reason: {stored_reason}.",
                priority="normal",
                case_id=appt.case_id,
                patient_id=appt.patient_id,
                action_link=f"/cases/{appt.case_id}",
                idempotency_key=f"cancel_doc_{d_user.id}_{appt.id}_v{appt.version}",
                metadata_json={"appointment_id": str(appt.id), "reason": stored_reason},
            )

        db.add(CaseEvent(
            id=uuid.uuid4(),
            case_id=appt.case_id,
            event_type="appointment_cancelled",
            description=f"Appointment {appt.id} cancelled ({stored_reason}). Doctor and coordinator notified; recovery task opened.",
            event_data={
                "appointment_id": str(appt.id),
                "reason_category": reason_category or "other",
                "reason": stored_reason,
                "recovery_task_id": str(recovery_task.id),
            },
            timestamp=now,
        ))
        db.add(AuditLog(
            id=uuid.uuid4(),
            case_id=appt.case_id,
            patient_id=appt.patient_id,
            actor_type=actor_role,
            actor_id=str(actor_id),
            action="CANCEL_APPOINTMENT",
            autonomy_level=2,
            rationale=f"Cancelled appointment {appt.id} after explicit patient confirmation. Reason: {stored_reason}.",
            previous_state={"status": prev_status},
            new_state={"status": "CANCELLED", "reason": stored_reason, "recovery_task_id": str(recovery_task.id)},
            timestamp=now,
        ))
        db.commit()

        return {
            "success": True,
            "appointment_id": str(appt.id),
            "status": "CANCELLED",
            "cancellation_reason": stored_reason,
            "reason_category": reason_category or "other",
            "recovery_task_id": str(recovery_task.id),
        }
