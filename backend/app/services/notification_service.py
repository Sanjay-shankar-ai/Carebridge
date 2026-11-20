"""
CareBridge Notification Service (Phase 7)
Orchestrates database-backed notification persistence, role-based recipient routing,
idempotency enforcement, real-time in-memory event dispatch, and appointment reminders.
"""

import uuid
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.models.notification import Notification
from app.models.user import User
from app.models.care_case import CareCase
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.models.referral import Referral
from app.models.event_audit import AuditLog

logger = logging.getLogger("carebridge.services.notifications")


class OutboxDeliveryError(Exception):
    """Raised when transport delivery of an outbox notification fails."""
    pass


class RecipientAuthorizationError(PermissionError):
    """Raised when an attempt is made to dispatch a notification to an unauthorized user."""
    pass


class NotificationBroadcaster:
    """In-memory event hub for Server-Sent Events (SSE) active subscriber connections."""
    _subscribers: Dict[str, Set[asyncio.Queue]] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def subscribe(cls, user_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        async with cls._lock:
            if user_id not in cls._subscribers:
                cls._subscribers[user_id] = set()
            cls._subscribers[user_id].add(queue)
        logger.debug(f"[Broadcaster] User {user_id} subscribed (active connections: {len(cls._subscribers[user_id])})")
        return queue

    @classmethod
    async def unsubscribe(cls, user_id: str, queue: asyncio.Queue) -> None:
        async with cls._lock:
            if user_id in cls._subscribers:
                cls._subscribers[user_id].discard(queue)
                if not cls._subscribers[user_id]:
                    del cls._subscribers[user_id]
        logger.debug(f"[Broadcaster] User {user_id} unsubscribed")

    @classmethod
    def broadcast_sync(cls, user_id: str, payload: Dict[str, Any]) -> None:
        """Pushes event payload to all open subscriber queues for user_id."""
        if user_id in cls._subscribers:
            for q in cls._subscribers[user_id]:
                try:
                    q.put_nowait(payload)
                except Exception as e:
                    logger.warning(f"Could not deliver SSE payload to user queue: {e}")


class NotificationService:
    """Core domain service for persistent, role-protected notification lifecycle."""

    @classmethod
    def validate_recipient_authorization(
        cls,
        db: Session,
        user: User,
        role: str,
        case_id: Optional[uuid.UUID] = None,
        patient_id: Optional[uuid.UUID] = None
    ) -> None:
        """
        Enforces strict recipient authorization at notification staging time.
        - Patient role must only receive notifications for their own patient profile and care cases.
        - Doctor role must only receive notifications for assigned cases (or operational reviews).
        - Coordinator role must only receive coordinator notifications.
        """
        user_role = user.role.lower()
        target_role = role.lower()

        if user_role != target_role:
            raise RecipientAuthorizationError(
                f"Recipient role mismatch: User {user.id} has role '{user_role}', "
                f"attempted to stage notification with role '{target_role}'."
            )

        if target_role == "patient":
            if patient_id and user.patient_id != patient_id:
                raise RecipientAuthorizationError(
                    f"Cross-patient violation: User {user.id} (patient_id={user.patient_id}) "
                    f"cannot receive notification for patient {patient_id}."
                )
            if case_id:
                care_case = db.query(CareCase).filter(CareCase.id == case_id).first()
                if care_case and care_case.patient_id != user.patient_id:
                    raise RecipientAuthorizationError(
                        f"Cross-patient case violation: Case {case_id} belongs to patient {care_case.patient_id}, "
                        f"not user {user.id} (patient_id={user.patient_id})."
                    )

        elif target_role in ("doctor", "clinician"):
            if case_id:
                care_case = db.query(CareCase).filter(CareCase.id == case_id).first()
                if care_case:
                    # Allow if doctor is assigned as current_owner, or has doctor_assignment record
                    is_owner = (care_case.current_owner_id is not None and care_case.current_owner_id == user.owner_id)
                    from app.models.doctor_assignment import DoctorAssignment
                    has_assignment = (
                        db.query(DoctorAssignment)
                        .filter(DoctorAssignment.case_id == case_id, DoctorAssignment.doctor_id == user.owner_id)
                        .first() is not None
                    )
                    is_appt_provider = False
                    if user.owner_id and not (is_owner or has_assignment):
                        from app.models.owner import CaseOwner
                        owner_rec = db.query(CaseOwner).filter(CaseOwner.id == user.owner_id).first()
                        if owner_rec:
                            is_appt_provider = (
                                db.query(Appointment)
                                .filter(
                                    Appointment.case_id == case_id,
                                    Appointment.provider_name == owner_rec.name,
                                )
                                .first() is not None
                            )
                    if not (is_owner or has_assignment or is_appt_provider):
                        raise RecipientAuthorizationError(
                            f"Doctor authorization violation: Doctor {user.id} is not assigned to Case {case_id}."
                        )

    @classmethod
    def stage_notification(
        cls,
        db: Session,
        user_id: uuid.UUID,
        role: str,
        event_type: str,
        title: str,
        message: str,
        priority: str = "normal",
        case_id: Optional[uuid.UUID] = None,
        patient_id: Optional[uuid.UUID] = None,
        action_link: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
        max_retries: int = 3
    ) -> Notification:
        """
        Stages an outbox notification within the caller's active database transaction.
        Enforces recipient authorization and idempotency.
        Does NOT commit or broadcast immediately; outbox worker handles durable delivery.
        """
        # 1. Idempotency Check
        if idempotency_key:
            existing = (
                db.query(Notification)
                .filter(Notification.idempotency_key == idempotency_key)
                .first()
            )
            if existing:
                logger.info(f"[NotificationService] Idempotency hit: {idempotency_key}. Reusing notification {existing.id}.")
                try:
                    from app.workflows.persistence.traces import WorkflowTraceLogger
                    WorkflowTraceLogger.log_node_trace(
                        db=db,
                        case_id=str(case_id) if case_id else None,
                        thread_id="notification",
                        run_id=idempotency_key,
                        workflow_name="notification_delivery",
                        node_name="idempotency_check",
                        step_number=1,
                        status="duplicate_ignored",
                        duration_ms=0.0,
                        coordinator_note="Duplicate event ignored due to active idempotency key",
                        notification_id=str(existing.id)
                    )
                except Exception as trace_err:
                    logger.debug(f"Idempotency trace logging notice: {trace_err}")
                return existing

        # 2. Verify Recipient User and Role Authorization
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"Recipient user {user_id} does not exist.")

        cls.validate_recipient_authorization(
            db=db,
            user=user,
            role=role,
            case_id=case_id,
            patient_id=patient_id
        )

        # 3. Create Notification in 'pending' state
        now = datetime.now(timezone.utc)
        notif = Notification(
            id=uuid.uuid4(),
            user_id=user_id,
            role=role.lower(),
            event_type=event_type,
            title=title,
            message=message,
            priority=priority,
            case_id=case_id,
            patient_id=patient_id,
            is_read=False,
            status="pending",
            retry_count=0,
            max_retries=max_retries,
            last_error=None,
            next_attempt_at=now,
            processing_started_at=None,
            delivered_at=None,
            action_link=action_link,
            idempotency_key=idempotency_key,
            metadata_json=metadata_json or {},
            created_at=now,
            updated_at=now
        )
        db.add(notif)
        db.flush()

        # Audit Log for High-Priority Alerts
        if priority in ("urgent", "critical"):
            audit = AuditLog(
                id=uuid.uuid4(),
                case_id=case_id,
                patient_id=patient_id,
                actor_type="system",
                actor_id="outbox_service",
                action="STAGE_NOTIFICATION",
                autonomy_level=1,
                rationale=f"Staged outbox alert ({event_type}): {title}",
                new_state={"notification_id": str(notif.id), "event_type": event_type, "recipient_role": role},
                timestamp=now
            )
            db.add(audit)
            db.flush()

        return notif

    @classmethod
    def create_notification(
        cls,
        db: Session,
        user_id: uuid.UUID,
        role: str,
        event_type: str,
        title: str,
        message: str,
        priority: str = "normal",
        case_id: Optional[uuid.UUID] = None,
        patient_id: Optional[uuid.UUID] = None,
        action_link: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
        commit: bool = True
    ) -> Notification:
        """
        Backward-compatible notification creation.
        Stages in outbox; if commit=True, commits transaction.
        """
        notif = cls.stage_notification(
            db=db,
            user_id=user_id,
            role=role,
            event_type=event_type,
            title=title,
            message=message,
            priority=priority,
            case_id=case_id,
            patient_id=patient_id,
            action_link=action_link,
            idempotency_key=idempotency_key,
            metadata_json=metadata_json
        )
        if commit:
            db.commit()
            db.refresh(notif)
        return notif

    @classmethod
    def process_outbox_batch(
        cls,
        db: Session,
        batch_size: int = 20
    ) -> int:
        """
        Polls and claims pending or retry-ready failed outbox notifications,
        delivers them via broadcaster, and transitions to 'delivered' or 'failed'/'dead_letter'.
        Concurrency-safe claiming: uses SKIP LOCKED where supported by the dialect.
        """
        now = datetime.now(timezone.utc)
        query = (
            db.query(Notification)
            .filter(
                (Notification.status == "pending") |
                ((Notification.status == "failed") & (Notification.next_attempt_at <= now))
            )
            .order_by(Notification.created_at.asc())
            .limit(batch_size)
        )

        try:
            bind = db.get_bind()
            if bind and bind.dialect.name == "postgresql":
                query = query.with_for_update(skip_locked=True)
        except Exception:
            pass

        batch = query.all()
        if not batch:
            return 0

        import time as _time

        delivered_count = 0
        for notif in batch:
            notif.status = "processing"
            notif.processing_started_at = now
            db.commit()

            # --- Retry loop: up to 3 attempts with 1 s sleep between failures ---
            max_inline_attempts = 3
            last_exc: Optional[Exception] = None
            delivery_succeeded = False

            for attempt in range(1, max_inline_attempts + 1):
                try:
                    payload = cls.serialize_notification(notif)
                    NotificationBroadcaster.broadcast_sync(str(notif.user_id), payload)
                    delivery_succeeded = True
                    break
                except Exception as exc:
                    last_exc = exc
                    logger.warning(
                        f"[Outbox] Delivery attempt {attempt}/{max_inline_attempts} "
                        f"failed for notification {notif.id}: {exc}"
                    )
                    if attempt < max_inline_attempts:
                        _time.sleep(1)

            if delivery_succeeded:
                notif.status = "delivered"
                notif.delivered_at = datetime.now(timezone.utc)
                notif.last_error = None
                delivered_count += 1
            else:
                # All inline attempts exhausted → dead-letter immediately
                notif.retry_count += 1
                notif.status = "dead_letter"
                notif.last_error = f"Dead-lettered after {max_inline_attempts} attempts: {str(last_exc)}"
                logger.error(
                    f"[Outbox] Notification {notif.id} dead-lettered after "
                    f"{max_inline_attempts} attempts. Last error: {last_exc}"
                )
                try:
                    from app.workflows.persistence.traces import WorkflowTraceLogger
                    WorkflowTraceLogger.log_node_trace(
                        db=db,
                        case_id=str(notif.case_id) if notif.case_id else None,
                        thread_id="notification_outbox",
                        run_id=str(notif.id),
                        workflow_name="notification_delivery",
                        node_name="outbox_transport",
                        step_number=notif.retry_count,
                        status="dead_lettered",
                        duration_ms=0.0,
                        error_message=str(last_exc),
                        coordinator_note=f"Outbox transport failed after {max_inline_attempts} attempts; dead-lettered",
                        notification_id=str(notif.id)
                    )
                except Exception as trace_err:
                    logger.debug(f"Dead letter trace notice: {trace_err}")

            db.commit()

        return delivered_count

    @classmethod
    def recover_stuck_processing_notifications(
        cls,
        db: Session,
        stuck_timeout_seconds: int = 60
    ) -> int:
        """
        Recovers notifications left in 'processing' state due to a worker crash or unexpected termination.
        Resets them to 'pending' so they can be reclaimed cleanly.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=stuck_timeout_seconds)
        stuck = (
            db.query(Notification)
            .filter(
                Notification.status == "processing",
                Notification.processing_started_at < cutoff
            )
            .all()
        )
        count = len(stuck)
        for notif in stuck:
            logger.warning(
                f"[Outbox Recovery] Recovering stuck notification {notif.id} (processing since {notif.processing_started_at})"
            )
            notif.status = "pending"
            notif.processing_started_at = None
        if count > 0:
            db.commit()
        return count

    @classmethod
    def reprocess_dead_letter_notification(
        cls,
        db: Session,
        notification_id: uuid.UUID
    ) -> Dict[str, Any]:
        """
        Manually re-queues a dead-lettered notification for administrative recovery.
        """
        notif = db.query(Notification).filter(Notification.id == notification_id).first()
        if not notif:
            return {"success": False, "error": f"Notification {notification_id} not found"}
        if notif.status != "dead_letter":
            return {"success": False, "error": f"Notification {notification_id} is in status '{notif.status}', not 'dead_letter'"}

        notif.status = "pending"
        notif.retry_count = 0
        notif.next_attempt_at = datetime.now(timezone.utc)
        notif.last_error = f"Recovered from dead_letter on {datetime.now(timezone.utc).isoformat()}"
        db.commit()
        return {"success": True, "notification_id": str(notif.id), "status": "pending"}

    @classmethod
    def get_missed_notifications_for_reconnect(
        cls,
        db: Session,
        user_id: uuid.UUID,
        last_event_id: Optional[uuid.UUID] = None
    ) -> List[Notification]:
        """
        Retrieves unread notifications missed during a disconnection.
        If last_event_id is provided, returns all unread notifications excluding last_event_id
        that were created on or after last_event_id.
        """
        query = (
            db.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.is_read == False,
                Notification.status == "delivered"
            )
        )

        if last_event_id:
            last_notif = db.query(Notification).filter(Notification.id == last_event_id).first()
            if last_notif:
                query = query.filter(
                    Notification.id != last_event_id,
                    Notification.created_at >= last_notif.created_at
                )

        return query.order_by(Notification.created_at.asc()).all()

    @classmethod
    def serialize_notification(cls, notif: Notification) -> Dict[str, Any]:
        """Serializes notification model for API delivery."""
        return {
            "id": str(notif.id),
            "user_id": str(notif.user_id),
            "role": notif.role,
            "event_type": notif.event_type,
            "title": notif.title,
            "message": notif.message,
            "priority": notif.priority,
            "case_id": str(notif.case_id) if notif.case_id else None,
            "patient_id": str(notif.patient_id) if notif.patient_id else None,
            "is_read": notif.is_read,
            "read_at": notif.read_at.isoformat() if notif.read_at else None,
            "action_link": notif.action_link,
            "idempotency_key": notif.idempotency_key,
            "metadata": notif.metadata_json or {},
            "created_at": notif.created_at.isoformat() if notif.created_at else None,
        }

    # =========================================================================
    # User Lookup Helpers
    # =========================================================================

    @classmethod
    def get_patient_user(cls, db: Session, patient_id: uuid.UUID) -> Optional[User]:
        """Finds authenticated User corresponding to a patient record."""
        return db.query(User).filter(User.patient_id == patient_id).first()

    @classmethod
    def get_doctor_users(cls, db: Session, case_owner_id: Optional[uuid.UUID] = None) -> List[User]:
        """Finds doctor User accounts."""
        if case_owner_id:
            assigned = db.query(User).filter(User.owner_id == case_owner_id).all()
            if assigned:
                return assigned
        return db.query(User).filter(User.role.in_(["doctor", "clinician"])).all()

    @classmethod
    def get_coordinator_users(cls, db: Session, case_owner_id: Optional[uuid.UUID] = None) -> List[User]:
        """Finds care coordinator User accounts."""
        if case_owner_id:
            assigned = db.query(User).filter(User.owner_id == case_owner_id).all()
            if assigned:
                return assigned
        return db.query(User).filter(User.role == "care_coordinator").all()

    # =========================================================================
    # Specialized Event Dispatchers
    # =========================================================================

    @classmethod
    def notify_screening_result_available(
        cls, db: Session, case_id: uuid.UUID, patient_id: uuid.UUID, screening_type: str, finding_code: str
    ) -> List[Notification]:
        """Event: New screening result available."""
        notifs = []
        # 1. Patient Notification (safe phrasing)
        p_user = cls.get_patient_user(db, patient_id)
        if p_user:
            n = cls.create_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="screening_result_available",
                title="Screening Results Ready",
                message=f"Your {screening_type} results are available. Your care team has coordinated your next steps.",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link="/patient",
                idempotency_key=f"screening_pat_{case_id}_{finding_code}",
                metadata_json={"screening_type": screening_type, "finding_code": finding_code}
            )
            notifs.append(n)

        # 2. Coordinator Notification
        coords = cls.get_coordinator_users(db)
        for c_user in coords:
            n = cls.create_notification(
                db=db,
                user_id=c_user.id,
                role="care_coordinator",
                event_type="screening_result_available",
                title="New Screening Result Received",
                message=f"New {screening_type} ({finding_code}) received. Initial outreach pathway initiated.",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link=f"/cases/{case_id}",
                idempotency_key=f"screening_coord_{c_user.id}_{case_id}",
                metadata_json={"screening_type": screening_type, "finding_code": finding_code}
            )
            notifs.append(n)
        return notifs

    @classmethod
    def notify_referral_created(
        cls, db: Session, case_id: uuid.UUID, referral_id: uuid.UUID, patient_id: uuid.UUID,
        target_facility: str, specialty: str, patient_name: str
    ) -> List[Notification]:
        """Event: Referral created."""
        notifs = []
        # 1. Patient
        p_user = cls.get_patient_user(db, patient_id)
        if p_user:
            n = cls.create_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="referral_created",
                title="Specialist Referral Coordinated",
                message=f"A specialist referral to {target_facility} for {specialty} has been sent by your care team.",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link="/referrals",
                idempotency_key=f"ref_created_pat_{referral_id}",
                metadata_json={"referral_id": str(referral_id), "facility": target_facility}
            )
            notifs.append(n)

        # 2. Doctor (Attending Oncology Specialist)
        docs = cls.get_doctor_users(db)
        for d_user in docs:
            n = cls.create_notification(
                db=db,
                user_id=d_user.id,
                role="doctor",
                event_type="referral_created",
                title="Inbound Specialist Referral",
                message=f"Inbound referral for {patient_name}: {specialty} at {target_facility}. Turnaround SLA: 48h.",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link="/referrals",
                idempotency_key=f"ref_created_doc_{d_user.id}_{referral_id}",
                metadata_json={"referral_id": str(referral_id), "patient_name": patient_name}
            )
            notifs.append(n)
        return notifs

    @classmethod
    def notify_appointment_booked(
        cls, db: Session, case_id: uuid.UUID, appointment_id: uuid.UUID, patient_id: uuid.UUID,
        provider_name: str, facility: str, scheduled_time: datetime, patient_name: Optional[str] = None
    ) -> List[Notification]:
        """Event: Appointment booked."""
        notifs = []
        formatted_time = scheduled_time.strftime("%A, %b %d at %I:%M %p")

        # 1. Patient
        p_user = cls.get_patient_user(db, patient_id)
        if p_user:
            n = cls.create_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="appointment_booked",
                title="Appointment Confirmed",
                message=f"Your visit with {provider_name} at {facility} is scheduled for {formatted_time}.",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link="/appointments",
                idempotency_key=f"appt_booked_pat_{appointment_id}",
                metadata_json={"appointment_id": str(appointment_id), "scheduled_time": scheduled_time.isoformat()}
            )
            notifs.append(n)

        # 2. Doctor
        docs = cls.get_doctor_users(db)
        for d_user in docs:
            n = cls.create_notification(
                db=db,
                user_id=d_user.id,
                role="doctor",
                event_type="appointment_booked",
                title="Procedure Visit Scheduled",
                message=f"Visit scheduled: {patient_name or 'Patient'} with {provider_name} on {formatted_time}.",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link="/doctor",
                idempotency_key=f"appt_booked_doc_{d_user.id}_{appointment_id}",
                metadata_json={"appointment_id": str(appointment_id), "scheduled_time": scheduled_time.isoformat()}
            )
            notifs.append(n)

        # 3. Care Coordinator
        coords = cls.get_coordinator_users(db)
        for c_user in coords:
            n = cls.create_notification(
                db=db,
                user_id=c_user.id,
                role="care_coordinator",
                event_type="appointment_booked",
                title="Appointment Coordinated",
                message=f"Appointment coordinated for {patient_name or 'Patient'} on {formatted_time} at {facility}.",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link="/coordinator",
                idempotency_key=f"appt_booked_coord_{c_user.id}_{appointment_id}",
                metadata_json={"appointment_id": str(appointment_id)}
            )
            notifs.append(n)

        return notifs

    @classmethod
    def notify_appointment_cancelled(
        cls, db: Session, case_id: uuid.UUID, appointment_id: uuid.UUID, patient_id: uuid.UUID,
        reason: str, cancelled_by: str, patient_name: Optional[str] = None
    ) -> List[Notification]:
        """Event: Appointment cancelled with logged reason."""
        notifs = []

        # 1. Patient Notification
        p_user = cls.get_patient_user(db, patient_id)
        if p_user:
            n = cls.create_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="appointment_cancelled",
                title="Appointment Rescheduling Needed",
                message=f"Your upcoming procedure visit has been cancelled ({reason}). Your care coordinator will contact you promptly to reschedule.",
                priority="urgent",
                case_id=case_id,
                patient_id=patient_id,
                action_link="/appointments",
                idempotency_key=f"appt_cancelled_pat_{appointment_id}",
                metadata_json={"appointment_id": str(appointment_id), "reason": reason}
            )
            notifs.append(n)

        # 2. Coordinator Notification (triggers recovery focus)
        coords = cls.get_coordinator_users(db)
        for c_user in coords:
            n = cls.create_notification(
                db=db,
                user_id=c_user.id,
                role="care_coordinator",
                event_type="appointment_cancelled",
                title="Action Required: Visit Cancelled",
                message=f"Visit for {patient_name or 'Patient'} was cancelled by {cancelled_by}. Reason: {reason}. Proactive recovery triggered.",
                priority="urgent",
                case_id=case_id,
                patient_id=patient_id,
                action_link=f"/cases/{case_id}",
                idempotency_key=f"appt_cancelled_coord_{c_user.id}_{appointment_id}",
                metadata_json={"appointment_id": str(appointment_id), "reason": reason}
            )
            notifs.append(n)

        # 3. Assigned Doctor Notification
        appt = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        doc_users = cls.get_assigned_doctor_users(db, case_id, provider_name=appt.provider_name if appt else None)
        for d_user in doc_users:
            try:
                n = cls.create_notification(
                    db=db,
                    user_id=d_user.id,
                    role=d_user.role,
                    event_type="appointment_cancelled",
                    title="Patient Appointment Cancelled",
                    message=f"Appointment for {patient_name or 'Patient'} was cancelled ({reason}).",
                    priority="normal",
                    case_id=case_id,
                    patient_id=patient_id,
                    action_link=f"/cases/{case_id}",
                    idempotency_key=f"appt_cancelled_doc_{d_user.id}_{appointment_id}",
                    metadata_json={"appointment_id": str(appointment_id), "reason": reason},
                )
                notifs.append(n)
            except RecipientAuthorizationError:
                pass

        return notifs

    @classmethod
    def get_assigned_doctor_users(
        cls, db: Session, case_id: uuid.UUID, provider_name: Optional[str] = None
    ) -> List[User]:
        """Returns doctor User accounts authorized for a specific case (via owner, assignment, or provider_name)."""
        from app.models.doctor_assignment import DoctorAssignment
        from app.models.owner import CaseOwner

        owner_ids = set()
        case = db.query(CareCase).filter(CareCase.id == case_id).first()
        if case and case.current_owner_id:
            owner_ids.add(case.current_owner_id)
        for da in db.query(DoctorAssignment).filter(DoctorAssignment.case_id == case_id).all():
            owner_ids.add(da.doctor_id)
        if provider_name:
            prov = db.query(CaseOwner).filter(CaseOwner.name == provider_name).first()
            if prov:
                owner_ids.add(prov.id)
        if not owner_ids:
            return []
        return (
            db.query(User)
            .filter(User.owner_id.in_(list(owner_ids)), User.role.in_(["doctor", "clinician"]))
            .all()
        )

    @classmethod
    def notify_appointment_reminder(
        cls, db: Session, appointment_id: uuid.UUID, patient_id: uuid.UUID,
        facility: str, provider_name: str, scheduled_time: datetime
    ) -> Optional[Notification]:
        """Event: Appointment reminder for patient."""
        p_user = cls.get_patient_user(db, patient_id)
        if not p_user:
            return None

        formatted_time = scheduled_time.strftime("%A, %b %d at %I:%M %p")
        # Idempotency key per appointment date to prevent duplicate reminders
        idemp = f"reminder_{appointment_id}_{scheduled_time.strftime('%Y%m%d%H%M')}"
        return cls.create_notification(
            db=db,
            user_id=p_user.id,
            role="patient",
            event_type="appointment_reminder",
            title="Upcoming Appointment Reminder",
            message=f"Friendly reminder: Your procedure visit with {provider_name} at {facility} is scheduled for {formatted_time}. Please bring family or support if desired.",
            priority="normal",
            patient_id=patient_id,
            action_link="/patient",
            idempotency_key=idemp,
            metadata_json={"appointment_id": str(appointment_id), "scheduled_time": scheduled_time.isoformat()}
        )

    @classmethod
    def notify_clinical_escalation(
        cls,
        db: Session,
        case_id: uuid.UUID,
        patient_id: uuid.UUID,
        patient_name: Optional[str] = None,
        reason: Optional[str] = None,
        actor_user_id: Optional[uuid.UUID] = None,
        summary: Optional[str] = None,
        **kwargs
    ) -> List[Notification]:
        """Event: Clinical escalation and doctor handoff (CRITICAL priority)."""
        notifs = []
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        p_name = patient_name or "Patient"
        effective_reason = reason or summary or "Critical symptom report requiring urgent physician review."

        # 1. Attending Doctor (Level 3 Clinical Escalation Queue, if assigned)
        care_case = db.query(CareCase).filter(CareCase.id == case_id).first()
        doctor_owner_id = care_case.current_owner_id if care_case else None
        if doctor_owner_id:
            assigned_doc = db.query(User).filter(User.owner_id == doctor_owner_id, User.role.in_(["doctor", "clinician"])).first()
            if assigned_doc:
                n = cls.stage_notification(
                    db=db,
                    user_id=assigned_doc.id,
                    role="doctor",
                    event_type="clinical_escalation_triggered",
                    title="URGENT: Clinical Escalation & Doctor Handoff",
                    message=f"Critical symptom report for {p_name}: {effective_reason}. Direct physician review required.",
                    priority="critical",
                    case_id=case_id,
                    patient_id=patient_id,
                    action_link=f"/cases/{case_id}",
                    idempotency_key=f"escalation_doc_{assigned_doc.id}_{case_id}_{now_str}",
                    metadata_json={"reason": effective_reason, "escalated_at": datetime.now(timezone.utc).isoformat()}
                )
                notifs.append(n)

        # 2. Coordinator Notification
        coords = cls.get_coordinator_users(db)
        for c_user in coords:
            n = cls.stage_notification(
                db=db,
                user_id=c_user.id,
                role="care_coordinator",
                event_type="clinical_escalation_triggered",
                title="Doctor Handoff Active",
                message=f"Case #{case_id} ({p_name}) escalated to attending oncologist: {effective_reason}.",
                priority="urgent",
                case_id=case_id,
                patient_id=patient_id,
                action_link=f"/cases/{case_id}",
                idempotency_key=f"escalation_coord_{c_user.id}_{case_id}_{now_str}",
                metadata_json={"reason": effective_reason}
            )
            notifs.append(n)

        return notifs

    @classmethod
    def notify_screening_order_created(
        cls,
        db: Session,
        case_id: uuid.UUID,
        patient_id: uuid.UUID,
        actor_user_id: Optional[uuid.UUID] = None,
        summary: str = "Screening order created",
        **kwargs
    ) -> List[Notification]:
        """Event: Screening order created."""
        notifs = []
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        p_user = cls.get_patient_user(db, patient_id)
        if p_user:
            n = cls.stage_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="screening_order_created",
                title="Screening Order Placed",
                message="Your physician has placed your screening examination order.",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link="/patient",
                idempotency_key=f"order_pat_{case_id}_{now_str}"
            )
            notifs.append(n)
        coords = cls.get_coordinator_users(db)
        for c_user in coords:
            n = cls.stage_notification(
                db=db,
                user_id=c_user.id,
                role="care_coordinator",
                event_type="screening_order_created",
                title="Screening Order Submitted",
                message=f"Screening order submitted for case #{case_id}: {summary}",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link=f"/cases/{case_id}",
                idempotency_key=f"order_coord_{c_user.id}_{case_id}_{now_str}"
            )
            notifs.append(n)
        return notifs

    @classmethod
    def notify_report_finalized(
        cls,
        db: Session,
        case_id: uuid.UUID,
        patient_id: uuid.UUID,
        actor_user_id: Optional[uuid.UUID] = None,
        summary: str = "Diagnostic report finalized",
        **kwargs
    ) -> List[Notification]:
        """Event: Diagnostic report finalized."""
        notifs = []
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        p_user = cls.get_patient_user(db, patient_id)
        if p_user:
            n = cls.stage_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="diagnostic_report_finalized",
                title="Diagnostic Report Finalized",
                message="Your latest diagnostic imaging report has been finalized by your physician.",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link="/patient",
                idempotency_key=f"rep_final_pat_{case_id}_{now_str}"
            )
            notifs.append(n)
        coords = cls.get_coordinator_users(db)
        for c_user in coords:
            n = cls.stage_notification(
                db=db,
                user_id=c_user.id,
                role="care_coordinator",
                event_type="diagnostic_report_finalized",
                title="Diagnostic Report Finalized",
                message=f"Diagnostic report finalized for case #{case_id}: {summary}",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link=f"/cases/{case_id}",
                idempotency_key=f"rep_final_coord_{c_user.id}_{case_id}_{now_str}"
            )
            notifs.append(n)
        return notifs

    @classmethod
    def notify_referral_update(
        cls,
        db: Session,
        case_id: uuid.UUID,
        patient_id: uuid.UUID,
        actor_user_id: Optional[uuid.UUID] = None,
        summary: str = "Referral status updated",
        **kwargs
    ) -> List[Notification]:
        """Event: Referral status changed."""
        notifs = []
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        p_user = cls.get_patient_user(db, patient_id)
        if p_user:
            n = cls.stage_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="referral_status_changed",
                title="Referral Status Update",
                message=f"Update regarding your specialist referral: {summary}",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link="/referrals",
                idempotency_key=f"ref_upd_pat_{case_id}_{now_str}"
            )
            notifs.append(n)
        coords = cls.get_coordinator_users(db)
        for c_user in coords:
            n = cls.stage_notification(
                db=db,
                user_id=c_user.id,
                role="care_coordinator",
                event_type="referral_status_changed",
                title="Referral Status Changed",
                message=f"Referral status changed for case #{case_id}: {summary}",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link=f"/cases/{case_id}",
                idempotency_key=f"ref_upd_coord_{c_user.id}_{case_id}_{now_str}"
            )
            notifs.append(n)
        return notifs

    @classmethod
    def notify_appointment_version_update(
        cls,
        db: Session,
        case_id: uuid.UUID,
        patient_id: uuid.UUID,
        actor_user_id: Optional[uuid.UUID] = None,
        summary: str = "Appointment version updated",
        **kwargs
    ) -> List[Notification]:
        """Event: Appointment version changed."""
        notifs = []
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        p_user = cls.get_patient_user(db, patient_id)
        if p_user:
            n = cls.stage_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="appointment_version_changed",
                title="Appointment Schedule Update",
                message=f"Your appointment schedule has a new proposed version: {summary}. Please review and confirm.",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link="/patient",
                idempotency_key=f"appt_ver_pat_{case_id}_{now_str}"
            )
            notifs.append(n)
        coords = cls.get_coordinator_users(db)
        for c_user in coords:
            n = cls.stage_notification(
                db=db,
                user_id=c_user.id,
                role="care_coordinator",
                event_type="appointment_version_changed",
                title="Appointment Version Changed",
                message=f"Appointment version updated for case #{case_id}: {summary}",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link=f"/cases/{case_id}",
                idempotency_key=f"appt_ver_coord_{c_user.id}_{case_id}_{now_str}"
            )
            notifs.append(n)
        return notifs

    @classmethod
    def notify_doctor_review_completed(
        cls, db: Session, case_id: uuid.UUID, patient_id: uuid.UUID, doctor_name: str, summary: str, patient_name: Optional[str] = None
    ) -> List[Notification]:
        """Event: Doctor review completed."""
        notifs = []
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")

        # 1. Care Coordinator
        coords = cls.get_coordinator_users(db)
        for c_user in coords:
            n = cls.create_notification(
                db=db,
                user_id=c_user.id,
                role="care_coordinator",
                event_type="doctor_review_completed",
                title="Physician Consultation Completed",
                message=f"{doctor_name} has completed clinical evaluation for {patient_name or 'Patient'}. Case status updated.",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link=f"/cases/{case_id}",
                idempotency_key=f"doc_rev_coord_{c_user.id}_{case_id}_{now_str}",
                metadata_json={"doctor_name": doctor_name}
            )
            notifs.append(n)

        # 2. Patient
        p_user = cls.get_patient_user(db, patient_id)
        if p_user:
            n = cls.create_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="doctor_review_completed",
                title="Care Plan Updated by Specialist",
                message=f"Dr. {doctor_name} has reviewed your diagnostic results. Your care coordinator is following up on your recommendations.",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link="/patient",
                idempotency_key=f"doc_rev_pat_{case_id}_{now_str}",
                metadata_json={"doctor_name": doctor_name}
            )
            notifs.append(n)

        return notifs

    @classmethod
    def notify_consultation_completed(
        cls, db: Session, case_id: uuid.UUID, patient_id: uuid.UUID, doctor_name: str, patient_name: Optional[str] = None, summary: Optional[str] = None
    ) -> List[Notification]:
        """Event: Doctor completed consultation and procedure."""
        notifs = []
        p_user = cls.get_patient_user(db, patient_id)
        if p_user:
            n = cls.create_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="consultation_completed",
                title="Consultation Completed",
                message=f"Your procedure visit with {doctor_name} has been completed. Your care coordinator is tracking next steps.",
                priority="normal",
                action_link="/patient",
                case_id=case_id,
                patient_id=patient_id,
                metadata_json={"doctor_name": doctor_name, "summary": summary}
            )
            notifs.append(n)
        return notifs

    @classmethod
    def notify_test_report_updated(
        cls, db: Session, case_id: uuid.UUID, patient_id: uuid.UUID, disease_condition: str, finding_code: str, patient_name: Optional[str] = None
    ) -> List[Notification]:
        """Event: Care coordinator updated test report."""
        notifs = []
        p_user = cls.get_patient_user(db, patient_id)
        if p_user:
            n = cls.create_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="screening_result_available",
                title="Screening Result Updated",
                message=f"Your screening result ({disease_condition} - {finding_code}) has been updated. Click to review your findings and download your diagnostic report.",
                priority="high",
                action_link="/patient",
                case_id=case_id,
                patient_id=patient_id,
                metadata_json={"disease_condition": disease_condition, "finding_code": finding_code}
            )
            notifs.append(n)
        return notifs

    @classmethod
    def notify_screening_scheduled(
        cls, db: Session, case_id: uuid.UUID, patient_id: uuid.UUID, facility: str, scheduled_time: datetime, patient_name: Optional[str] = None
    ) -> List[Notification]:
        """Event: Care coordinator scheduled screening appointment."""
        notifs = []
        p_user = cls.get_patient_user(db, patient_id)
        time_str = scheduled_time.strftime("%A, %B %d at %I:%M %p")
        if p_user:
            n = cls.create_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="appointment_booked",
                title="Screening Visit Scheduled",
                message=f"Your hospital Care Coordinator has scheduled your screening visit for {time_str} at {facility}. Click to review appointment details.",
                priority="high",
                action_link="/patient",
                case_id=case_id,
                patient_id=patient_id,
                metadata_json={"scheduled_time": scheduled_time.isoformat(), "facility": facility}
            )
            notifs.append(n)
        return notifs

    @classmethod
    def notify_screening_completed(
        cls, db: Session, case_id: uuid.UUID, patient_id: uuid.UUID, facility: str, patient_name: Optional[str] = None
    ) -> List[Notification]:
        """Event: Care coordinator manually entered screening completion."""
        notifs = []
        p_user = cls.get_patient_user(db, patient_id)
        if p_user:
            n = cls.create_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="screening_completed",
                title="Screening Visit Completed",
                message=f"Your screening at {facility} has been completed and verified. Your Care Coordinator is processing your diagnostic findings.",
                priority="normal",
                action_link="/patient",
                case_id=case_id,
                patient_id=patient_id,
                metadata_json={"facility": facility}
            )
            notifs.append(n)
        return notifs

    @classmethod
    def notify_screening_missed(
        cls, db: Session, case_id: uuid.UUID, patient_id: uuid.UUID, facility: str, scheduled_time: datetime, coordinator_name: str, patient_name: Optional[str] = None
    ) -> List[Notification]:
        """Event: Patient missed screening visit or post-screening task."""
        notifs = []
        time_str = scheduled_time.strftime("%A, %B %d at %I:%M %p")
        p_user = cls.get_patient_user(db, patient_id)
        if p_user:
            n = cls.create_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="appointment_no_show",
                title="Important: Missed Screening Visit",
                message=f"You missed your scheduled screening appointment on {time_str} at {facility}. Your hospital Care Coordinator ({coordinator_name}) and AI assistant are ready to help you reschedule without delay.",
                priority="critical",
                action_link="/chat",
                case_id=case_id,
                patient_id=patient_id,
                metadata_json={"missed_time": scheduled_time.isoformat(), "facility": facility, "coordinator": coordinator_name}
            )
            notifs.append(n)
        return notifs

    @classmethod
    def notify_case_closure_approved(
        cls, db: Session, case_id: uuid.UUID, patient_id: uuid.UUID, doctor_name: str, patient_name: Optional[str] = None
    ) -> List[Notification]:
        """Event: Case closure approved."""
        notifs = []

        # 1. Patient
        p_user = cls.get_patient_user(db, patient_id)
        if p_user:
            n = cls.create_notification(
                db=db,
                user_id=p_user.id,
                role="patient",
                event_type="case_closure_approved",
                title="Care Pathway Safely Completed",
                message=f"Your diagnostic follow-up pathway is complete and verified by Dr. {doctor_name}. All evidence has been documented.",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link="/patient",
                idempotency_key=f"closure_pat_{case_id}",
                metadata_json={"closing_doctor": doctor_name}
            )
            notifs.append(n)

        # 2. Coordinator
        coords = cls.get_coordinator_users(db)
        for c_user in coords:
            n = cls.create_notification(
                db=db,
                user_id=c_user.id,
                role="care_coordinator",
                event_type="case_closure_approved",
                title="Case Closure Verified",
                message=f"Care case for {patient_name or 'Patient'} formally closed with Level 3 physician sign-off ({doctor_name}).",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link=f"/cases/{case_id}",
                idempotency_key=f"closure_coord_{c_user.id}_{case_id}",
                metadata_json={"closing_doctor": doctor_name}
            )
            notifs.append(n)

        return notifs

    @classmethod
    def notify_sla_warning(
        cls, db: Session, case_id: uuid.UUID, case_number: str, patient_name: str, hours_remaining: int
    ) -> List[Notification]:
        """Event: SLA deadline warning or breach for care coordinator."""
        notifs = []
        is_breach = hours_remaining <= 0
        title = "SLA Deadline Breached" if is_breach else "SLA Deadline Warning (< 72h)"
        msg = (
            f"Case #{case_number} ({patient_name}) has breached its care pathway SLA deadline."
            if is_breach
            else f"Case #{case_number} ({patient_name}) has {hours_remaining}h remaining before SLA deadline."
        )
        priority = "critical" if is_breach else "urgent"
        date_key = datetime.now(timezone.utc).strftime("%Y%m%d")

        coords = cls.get_coordinator_users(db)
        for c_user in coords:
            n = cls.create_notification(
                db=db,
                user_id=c_user.id,
                role="care_coordinator",
                event_type="sla_warning",
                title=title,
                message=msg,
                priority=priority,
                case_id=case_id,
                action_link=f"/cases/{case_id}",
                idempotency_key=f"sla_{c_user.id}_{case_id}_{date_key}",
                metadata_json={"hours_remaining": hours_remaining, "is_breach": is_breach}
            )
            notifs.append(n)

        return notifs

    @classmethod
    def notify_recovery_outreach(
        cls, db: Session, case_id: uuid.UUID, patient_id: uuid.UUID, playbook_name: str
    ) -> Optional[Notification]:
        """Event: Missed appointment recovery outreach."""
        p_user = cls.get_patient_user(db, patient_id)
        if not p_user:
            return None

        date_key = datetime.now(timezone.utc).strftime("%Y%m%d%H")
        return cls.create_notification(
            db=db,
            user_id=p_user.id,
            role="patient",
            event_type="recovery_outreach",
            title="Care Support & Assistance",
            message="We noticed you might need help coordinating your visit. Transportation support and flexible appointment slots are available.",
            priority="normal",
            case_id=case_id,
            patient_id=patient_id,
            action_link="/chat",
            idempotency_key=f"recovery_pat_{case_id}_{date_key}",
            metadata_json={"playbook": playbook_name}
        )

    @classmethod
    def notify_patient_message(
        cls, db: Session, case_id: Optional[uuid.UUID], patient_id: uuid.UUID, patient_name: str, message_preview: str
    ) -> List[Notification]:
        """Event: Inbound patient message received."""
        notifs = []
        safe_preview = (message_preview[:60] + "...") if len(message_preview) > 60 else message_preview
        msg_key = uuid.uuid4().hex[:8]

        coords = cls.get_coordinator_users(db)
        for c_user in coords:
            n = cls.create_notification(
                db=db,
                user_id=c_user.id,
                role="care_coordinator",
                event_type="patient_message",
                title="New Patient Message",
                message=f"Message from {patient_name}: \"{safe_preview}\"",
                priority="normal",
                case_id=case_id,
                patient_id=patient_id,
                action_link=f"/cases/{case_id}" if case_id else "/chat",
                idempotency_key=f"pat_msg_{c_user.id}_{msg_key}",
                metadata_json={"patient_name": patient_name}
            )
            notifs.append(n)
        return notifs

    # =========================================================================
    # Background Appointment Reminder Processor
    # =========================================================================

    @classmethod
    def scan_and_send_appointment_reminders(
        cls, db: Session, hours_ahead: int = 48
    ) -> Dict[str, Any]:
        """
        Background job: Queries booked appointments within the upcoming hours_ahead window
        and creates reminder notifications with idempotency keys.
        """
        now = datetime.now(timezone.utc)
        target_window = now + timedelta(hours=hours_ahead)

        upcoming_appts = (
            db.query(Appointment)
            .filter(
                Appointment.status.in_(["booked", "confirmed"]),
                Appointment.scheduled_time >= now,
                Appointment.scheduled_time <= target_window
            )
            .all()
        )

        reminders_sent = 0
        for appt in upcoming_appts:
            try:
                idemp = f"reminder_{appt.id}_{appt.scheduled_time.strftime('%Y%m%d%H%M')}"
                already_exists = db.query(Notification).filter(Notification.idempotency_key == idemp).first()
                if already_exists:
                    continue

                res = cls.notify_appointment_reminder(
                    db=db,
                    appointment_id=appt.id,
                    patient_id=appt.patient_id,
                    facility=appt.facility,
                    provider_name=appt.provider_name,
                    scheduled_time=appt.scheduled_time
                )
                if res:
                    reminders_sent += 1
            except Exception as e:
                logger.error(f"Error dispatching reminder for appointment {appt.id}: {e}", exc_info=True)

        logger.info(f"[NotificationService] Reminder scan completed: {reminders_sent} reminder(s) generated.")
        return {
            "scanned_count": len(upcoming_appts),
            "reminders_sent": reminders_sent,
            "window_hours": hours_ahead,
            "scanned_at": now.isoformat()
        }


class OutboxWorker:
    """
    Background worker that continuously claims and delivers outbox notifications.
    Safely recovers rows stuck in 'processing' upon crash/restart, and retries failures.
    """
    _running: bool = False
    _task: Optional[asyncio.Task] = None

    @classmethod
    async def start(cls, poll_interval_seconds: float = 2.0):
        if cls._running:
            return
        cls._running = True
        cls._task = asyncio.create_task(cls._run_loop(poll_interval_seconds))
        logger.info("OutboxWorker background service started.")

    @classmethod
    async def stop(cls):
        cls._running = False
        if cls._task:
            cls._task.cancel()
            try:
                await cls._task
            except asyncio.CancelledError:
                pass
        logger.info("OutboxWorker background service stopped.")

    @classmethod
    async def _run_loop(cls, poll_interval: float):
        from app.database.session import get_sync_db
        while cls._running:
            try:
                with get_sync_db() as db:
                    # 1. Recover stuck rows
                    NotificationService.recover_stuck_processing_notifications(db, stuck_timeout_seconds=60)
                    # 2. Process batch
                    NotificationService.process_outbox_batch(db, batch_size=25)
            except Exception as e:
                logger.warning(f"OutboxWorker iteration warning: {e}")
            await asyncio.sleep(poll_interval)


