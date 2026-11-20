"""
CareBridge Transport Request Service (AI Behaviour B2)
Manages patient ride requests linked to appointment versions, coordinator handoff tasks,
outbox notifications, confirmation gating, and automatic resync on reschedule.
"""

import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.appointment import Appointment
from app.models.care_case import CareCase, Task
from app.models.event_audit import CaseEvent, AuditLog
from app.models.owner import CaseOwner
from app.models.patient import Patient
from app.models.transport import TransportRequest
from app.services.notification_service import NotificationService
from app.services.task_service import TaskService

logger = logging.getLogger("carebridge.services.transport")

ACTIVE_APPT_STATUSES = (
    "CONFIRMED",
    "PENDING_DOCTOR_CONFIRMATION",
    "PENDING_PATIENT_CONFIRMATION",
    "PROPOSED",
    "RESCHEDULE_REQUESTED",
    "booked",
    "confirmed",
    "pending",
    "pending_approval",
)

AUTHORIZED_CONFIRM_ROLES = ("care_coordinator", "coordinator", "transport_integration", "system")


class TransportAuthorizationError(PermissionError):
    """Raised when an unauthorized role attempts to confirm or access another patient's transport."""


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


class TransportService:
    """Authoritative domain service for patient transport requests."""

    @classmethod
    def compute_pickup_time(cls, appointment_start: datetime, lead_minutes: Optional[int] = None) -> datetime:
        """Computes pickup time = appointment start minus configured TRANSPORT_LEAD_MINUTES (default 60)."""
        mins = lead_minutes if lead_minutes is not None else settings.TRANSPORT_LEAD_MINUTES
        return _utc(appointment_start) - timedelta(minutes=mins)

    @classmethod
    def find_candidate_appointments(cls, db: Session, patient_id: uuid.UUID) -> List[Appointment]:
        """Returns upcoming CONFIRMED or PENDING appointments for the patient, ordered soonest first."""
        pid = patient_id if isinstance(patient_id, uuid.UUID) else uuid.UUID(str(patient_id))
        now = datetime.now(timezone.utc)
        return (
            db.query(Appointment)
            .filter(
                Appointment.patient_id == pid,
                Appointment.status.in_(ACTIVE_APPT_STATUSES),
                Appointment.scheduled_time >= now - timedelta(minutes=15),
            )
            .order_by(Appointment.scheduled_time.asc())
            .all()
        )

    @classmethod
    def get_coordinator_name(cls, db: Session, case: Optional[CareCase]) -> str:
        if case and case.current_owner_id:
            owner = db.query(CaseOwner).filter(CaseOwner.id == case.current_owner_id).first()
            if owner and owner.role == "care_coordinator":
                return owner.name
        coord = db.query(CaseOwner).filter(CaseOwner.role == "care_coordinator", CaseOwner.is_active.is_(True)).first()
        return coord.name if coord else "your care coordinator"

    @classmethod
    def create_transport_request(
        cls,
        db: Session,
        appointment_id: Any,
        pickup_time: Optional[datetime] = None,
        address: str = "",
        companion: bool = False,
        *,
        patient_id: Optional[Any] = None,
        actor_role: str = "patient",
        actor_id: str = "ai_coordinator",
    ) -> Dict[str, Any]:
        """
        Tool `create_transport_request(appointment_id, pickup_time, address, companion)`.
        Creates a TransportRequest (status=REQUESTED), linked to appointment.version,
        a Care Coordinator Task, and a coordinator outbox notification.
        Never claims the ride is confirmed. On failure, records a recoverable task.
        """
        appt_uuid = appointment_id if isinstance(appointment_id, uuid.UUID) else uuid.UUID(str(appointment_id))
        appt = db.query(Appointment).filter(Appointment.id == appt_uuid).first()
        if not appt:
            return {"success": False, "error": f"Appointment {appointment_id} not found."}

        if patient_id is not None:
            pid = patient_id if isinstance(patient_id, uuid.UUID) else uuid.UUID(str(patient_id))
            if appt.patient_id != pid:
                raise TransportAuthorizationError(
                    "Forbidden: Cannot create a transport request for another patient's appointment."
                )

        if appt.status.upper() in ("CANCELLED", "COMPLETED", "NO_SHOW"):
            return {"success": False, "error": f"Appointment is {appt.status} and cannot accept a transport request."}

        clean_address = (address or "").strip()
        if not clean_address:
            patient = db.query(Patient).filter(Patient.id == appt.patient_id).first()
            if patient and isinstance(patient.patient_context, dict):
                clean_address = (patient.patient_context.get("address") or "").strip()
        if not clean_address:
            return {"success": False, "error": "Pickup address is required."}

        computed_pickup = _utc(pickup_time) if pickup_time else cls.compute_pickup_time(appt.scheduled_time)
        appt_utc = _utc(appt.scheduled_time)

        case = db.query(CareCase).filter(CareCase.id == appt.case_id).first()
        coordinator_name = cls.get_coordinator_name(db, case)
        idemp_key = f"transport_{appt.id}_v{appt.version}"

        try:
            tr = db.query(TransportRequest).filter(TransportRequest.idempotency_key == idemp_key).first()
            if tr:
                tr.pickup_time = computed_pickup
                tr.pickup_address = clean_address
                tr.companion = bool(companion)
                if tr.status == "CANCELLED":
                    tr.status = "REQUESTED"
            else:
                tr = TransportRequest(
                    id=uuid.uuid4(),
                    appointment_id=appt.id,
                    appointment_version=appt.version,
                    case_id=appt.case_id,
                    patient_id=appt.patient_id,
                    pickup_time=computed_pickup,
                    pickup_address=clean_address,
                    companion=bool(companion),
                    status="REQUESTED",
                    idempotency_key=idemp_key,
                )
                db.add(tr)
                db.flush()

            # Coordinator task
            companion_text = "Yes (caregiver/companion travelling)" if companion else "No companion"
            task = TaskService.create_task(
                db=db,
                case_id=appt.case_id,
                patient_id=appt.patient_id,
                title=f"Confirm Transport Pickup ({computed_pickup.strftime('%H:%M')} UTC)",
                description=(
                    f"Patient requested medical transport for appointment {appt.id} (v{appt.version}) "
                    f"at {appt.facility} on {appt.scheduled_time.strftime('%Y-%m-%d %H:%M UTC')}.\n"
                    f"Pickup time: {computed_pickup.strftime('%Y-%m-%d %H:%M UTC')}\n"
                    f"Pickup address: {clean_address}\n"
                    f"Companion: {companion_text}\n"
                    f"Please confirm transport and update status to CONFIRMED."
                ),
                task_type="transport_request",
                assigned_role="care_coordinator",
                priority="urgent",
                due_date=min(computed_pickup, datetime.now(timezone.utc) + timedelta(hours=12)),
                idempotency_key=f"task_transport_{appt.id}_v{appt.version}",
                initial_context={
                    "transport_request_id": str(tr.id),
                    "appointment_id": str(appt.id),
                    "appointment_version": appt.version,
                    "pickup_time": computed_pickup.isoformat(),
                    "pickup_address": clean_address,
                    "companion": bool(companion),
                },
            )
            tr.task_id = task.id

            # Notify care coordinator(s) through the transactional outbox
            coords = NotificationService.get_coordinator_users(db)
            for c_user in coords:
                NotificationService.stage_notification(
                    db=db,
                    user_id=c_user.id,
                    role="care_coordinator",
                    event_type="transport_requested",
                    title="Transport Request Pending Confirmation",
                    message=(
                        f"Transport requested for pickup at {computed_pickup.strftime('%H:%M')} "
                        f"from {clean_address} (companion: {'yes' if companion else 'no'}) "
                        f"for appointment v{appt.version}."
                    ),
                    priority="urgent",
                    case_id=appt.case_id,
                    patient_id=appt.patient_id,
                    action_link=f"/cases/{appt.case_id}",
                    idempotency_key=f"notif_transport_req_{c_user.id}_{appt.id}_v{appt.version}",
                    metadata_json={
                        "transport_request_id": str(tr.id),
                        "appointment_id": str(appt.id),
                        "appointment_version": appt.version,
                        "pickup_time": computed_pickup.isoformat(),
                    },
                )

            now = datetime.now(timezone.utc)
            db.add(CaseEvent(
                id=uuid.uuid4(),
                case_id=appt.case_id,
                event_type="transport_requested",
                description=(
                    f"Transport requested for appointment v{appt.version}: pickup at "
                    f"{computed_pickup.strftime('%H:%M')} from {clean_address}."
                ),
                event_data={
                    "transport_request_id": str(tr.id),
                    "appointment_id": str(appt.id),
                    "appointment_version": appt.version,
                    "pickup_time": computed_pickup.isoformat(),
                    "pickup_address": clean_address,
                    "companion": bool(companion),
                    "status": tr.status,
                },
                timestamp=now,
            ))
            db.add(AuditLog(
                id=uuid.uuid4(),
                case_id=appt.case_id,
                patient_id=appt.patient_id,
                actor_type="ai_agent" if actor_role == "patient" else actor_role,
                actor_id=str(actor_id),
                action="CREATE_TRANSPORT_REQUEST",
                autonomy_level=2,
                rationale=f"Created transport request {tr.id} (status=REQUESTED) for appointment v{appt.version}.",
                new_state={"transport_request_id": str(tr.id), "status": tr.status, "pickup_time": computed_pickup.isoformat()},
                timestamp=now,
            ))
            db.commit()

            return {
                "success": True,
                "transport_request_id": str(tr.id),
                "task_id": str(task.id),
                "appointment_id": str(appt.id),
                "appointment_version": appt.version,
                "pickup_time": computed_pickup.isoformat(),
                "pickup_hhmm": computed_pickup.strftime("%H:%M"),
                "pickup_address": clean_address,
                "companion": bool(companion),
                "status": tr.status,
                "coordinator_name": coordinator_name,
            }
        except Exception as exc:
            logger.error(f"create_transport_request failed: {exc}", exc_info=True)
            db.rollback()
            recoverable = TaskService.record_failed_tool_handoff(
                db=db,
                case_id=appt.case_id,
                patient_id=appt.patient_id,
                tool_name="create_transport_request",
                tool_arguments={
                    "appointment_id": str(appt.id),
                    "pickup_time": computed_pickup.isoformat(),
                    "address": clean_address,
                    "companion": bool(companion),
                },
                error_message=str(exc),
            )
            db.commit()
            return {
                "success": False,
                "error": "Could not save the transport request right now.",
                "recoverable_task_id": str(recoverable.id),
                "coordinator_name": coordinator_name,
            }

    @classmethod
    def confirm_transport_request(
        cls,
        db: Session,
        transport_request_id: Any,
        actor_role: str,
        actor_id: str,
    ) -> Dict[str, Any]:
        """Coordinator or transport integration confirms a transport request and notifies the patient."""
        if (actor_role or "").lower() not in AUTHORIZED_CONFIRM_ROLES:
            raise TransportAuthorizationError(
                f"Role '{actor_role}' is not authorized to confirm transport requests."
            )

        tr_uuid = transport_request_id if isinstance(transport_request_id, uuid.UUID) else uuid.UUID(str(transport_request_id))
        tr = db.query(TransportRequest).filter(TransportRequest.id == tr_uuid).first()
        if not tr:
            return {"success": False, "error": f"Transport request {transport_request_id} not found."}

        now = datetime.now(timezone.utc)
        tr.status = "CONFIRMED"
        tr.confirmed_by = str(actor_id)
        tr.confirmed_at = now

        if tr.task_id:
            task = db.query(Task).filter(Task.id == tr.task_id).first()
            if task and task.status != "completed":
                task.status = "completed"
                task.completed_at = now
                task.completed_by_id = str(actor_id)
                task.completed_by_role = actor_role

        # Notify the patient through the transactional outbox
        p_user = NotificationService.get_patient_user(db, tr.patient_id)
        if p_user:
            NotificationService.stage_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="transport_confirmed",
                title="Transport Confirmed",
                message=(
                    f"Your ride is confirmed for pickup at {_utc(tr.pickup_time).strftime('%H:%M')} "
                    f"from {tr.pickup_address}."
                ),
                priority="normal",
                case_id=tr.case_id,
                patient_id=tr.patient_id,
                action_link="/appointments",
                idempotency_key=f"notif_transport_conf_{tr.id}_v{tr.appointment_version}",
                metadata_json={
                    "transport_request_id": str(tr.id),
                    "appointment_id": str(tr.appointment_id),
                    "pickup_time": tr.pickup_time.isoformat(),
                    "status": "CONFIRMED",
                },
            )

        db.add(CaseEvent(
            id=uuid.uuid4(),
            case_id=tr.case_id,
            event_type="transport_confirmed",
            description=f"Transport request {tr.id} confirmed by {actor_role} for pickup at {tr.pickup_time.strftime('%H:%M')}.",
            event_data={"transport_request_id": str(tr.id), "confirmed_by": str(actor_id)},
            timestamp=now,
        ))
        db.commit()
        return {
            "success": True,
            "transport_request_id": str(tr.id),
            "status": tr.status,
            "pickup_time": _utc(tr.pickup_time).isoformat(),
            "pickup_hhmm": _utc(tr.pickup_time).strftime("%H:%M"),
        }

    @classmethod
    def sync_on_reschedule(cls, db: Session, appointment: Appointment) -> Optional[TransportRequest]:
        """
        Automatically updates active transport requests when an appointment is rescheduled.
        Moves pickup to new_time - TRANSPORT_LEAD_MINUTES, links new appointment version,
        resets status to REQUESTED, updates coordinator task, and notifies patient & coordinator.
        """
        active_tr = (
            db.query(TransportRequest)
            .filter(
                TransportRequest.appointment_id == appointment.id,
                TransportRequest.status.in_(("REQUESTED", "CONFIRMED")),
            )
            .order_by(TransportRequest.created_at.desc())
            .first()
        )
        if not active_tr:
            return None

        new_pickup = cls.compute_pickup_time(appointment.scheduled_time)
        old_pickup_hhmm = _utc(active_tr.pickup_time).strftime("%H:%M")
        new_pickup_hhmm = new_pickup.strftime("%H:%M")
        appt_utc = _utc(appointment.scheduled_time)

        active_tr.pickup_time = new_pickup
        active_tr.appointment_version = appointment.version
        active_tr.status = "REQUESTED"
        active_tr.confirmed_by = None
        active_tr.confirmed_at = None
        active_tr.idempotency_key = f"transport_{appointment.id}_v{appointment.version}"

        # Create/refresh coordinator task for the updated version
        task = TaskService.create_task(
            db=db,
            case_id=appointment.case_id,
            patient_id=appointment.patient_id,
            title=f"Re-confirm Transport Pickup ({new_pickup_hhmm} UTC - v{appointment.version})",
            description=(
                f"Appointment {appointment.id} rescheduled to {appointment.scheduled_time.strftime('%Y-%m-%d %H:%M UTC')} "
                f"(v{appointment.version}). Transport pickup moved from {old_pickup_hhmm} to {new_pickup_hhmm} "
                f"at {active_tr.pickup_address}."
            ),
            task_type="transport_request",
            assigned_role="care_coordinator",
            priority="urgent",
            due_date=min(new_pickup, datetime.now(timezone.utc) + timedelta(hours=12)),
            idempotency_key=f"task_transport_{appointment.id}_v{appointment.version}",
            initial_context={
                "transport_request_id": str(active_tr.id),
                "appointment_id": str(appointment.id),
                "appointment_version": appointment.version,
                "pickup_time": new_pickup.isoformat(),
                "pickup_address": active_tr.pickup_address,
                "companion": active_tr.companion,
            },
        )
        active_tr.task_id = task.id

        # Notify patient about the moved pickup time
        p_user = NotificationService.get_patient_user(db, appointment.patient_id)
        if p_user:
            NotificationService.stage_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="transport_rescheduled",
                title="Transport Pickup Time Updated",
                message=(
                    f"Because your appointment moved to {appt_utc.strftime('%H:%M')}, "
                    f"your pickup request has been updated to {new_pickup_hhmm} (1 hour before) "
                    f"and sent to your coordinator to confirm."
                ),
                priority="normal",
                case_id=appointment.case_id,
                patient_id=appointment.patient_id,
                action_link="/appointments",
                idempotency_key=f"notif_transport_resched_pat_{appointment.id}_v{appointment.version}",
                metadata_json={
                    "transport_request_id": str(active_tr.id),
                    "appointment_id": str(appointment.id),
                    "appointment_version": appointment.version,
                    "pickup_time": new_pickup.isoformat(),
                },
            )

        # Notify coordinator(s)
        for c_user in NotificationService.get_coordinator_users(db):
            NotificationService.stage_notification(
                db=db,
                user_id=c_user.id,
                role="care_coordinator",
                event_type="transport_rescheduled",
                title="Transport Request Updated After Reschedule",
                message=(
                    f"Appointment v{appointment.version} rescheduled. Pickup moved from {old_pickup_hhmm} "
                    f"to {new_pickup_hhmm} from {active_tr.pickup_address}. Please re-confirm."
                ),
                priority="urgent",
                case_id=appointment.case_id,
                patient_id=appointment.patient_id,
                action_link=f"/cases/{appointment.case_id}",
                idempotency_key=f"notif_transport_resched_coord_{c_user.id}_{appointment.id}_v{appointment.version}",
            )

        db.add(CaseEvent(
            id=uuid.uuid4(),
            case_id=appointment.case_id,
            event_type="transport_rescheduled",
            description=f"Transport pickup moved from {old_pickup_hhmm} to {new_pickup_hhmm} for appointment v{appointment.version}.",
            event_data={
                "transport_request_id": str(active_tr.id),
                "old_pickup_hhmm": old_pickup_hhmm,
                "new_pickup_hhmm": new_pickup_hhmm,
                "appointment_version": appointment.version,
            },
            timestamp=datetime.now(timezone.utc),
        ))
        db.flush()
        return active_tr
