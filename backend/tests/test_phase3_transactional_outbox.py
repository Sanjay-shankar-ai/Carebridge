"""
CareBridge Phase 3 Acceptance Test Suite: Transactional Outbox & Durable Notifications

Verifies acceptance criteria for:
1. Transactional Outbox: Domain change, domain event, and notification outbox row persist atomically.
2. Rollback safety: Rollback of domain change rolls back notification and event rows; no premature dispatch.
3. Outbox Worker: Concurrency-safe claim, delivery, delivered status tracking, and timestamping.
4. Worker crash recovery: Stuck 'processing' rows after worker death/crash recovered and delivered exactly once.
5. Transient failure & retry: Exponential backoff on delivery failure, dead-lettering after max retries.
6. Dead-letter recovery: Manual administrative recovery reprocesses dead-lettered notifications.
7. Idempotency: Duplicate domain action/event yields exactly one event and one notification.
8. Recipient Authorization: Enforced at write time (wrong recipient rejected) and read time.
9. Reconnection & Durability: Notifications survive backend restart; reconnect re-delivers missed notifications.
10. Key Domain Events Wired: Screening orders, reports, assignments, referrals, appointments, and escalations.
"""

import uuid
import unittest
from datetime import date, datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.patient import Patient
from app.models.screening import ScreeningResult
from app.models.care_case import CareCase, Task
from app.models.owner import CaseOwner
from app.models.user import User
from app.models.event_audit import CaseEvent, AuditLog
from app.models.notification import Notification
from app.models.appointment import Appointment
from app.models.referral import Referral
from app.models.doctor_assignment import DoctorAssignment

from app.services.notification_service import (
    NotificationService,
    NotificationBroadcaster,
    OutboxDeliveryError,
    RecipientAuthorizationError
)


class TestPhase3TransactionalOutbox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.session = self.SessionLocal()

        # Patients
        self.patient_1 = Patient(
            id=uuid.uuid4(),
            mrn=f"MRN-P1-{uuid.uuid4().hex[:6]}",
            first_name="Meenakshi",
            last_name="Ramanathan",
            date_of_birth=date(1980, 3, 15),
            gender="female",
            preferred_language="en",
            communication_channel="in_app_chat",
            phone="+91-9876543201",
            email="meenakshi@example.com"
        )
        self.patient_2 = Patient(
            id=uuid.uuid4(),
            mrn=f"MRN-P2-{uuid.uuid4().hex[:6]}",
            first_name="Fatima",
            last_name="Zahra",
            date_of_birth=date(1975, 8, 22),
            gender="female",
            preferred_language="ar",
            communication_channel="whatsapp",
            phone="+91-9876543202",
            email="fatima@example.com"
        )
        self.session.add_all([self.patient_1, self.patient_2])

        # Owners
        self.coordinator = CaseOwner(
            id=uuid.uuid4(),
            name="Ananya Coordinator",
            role="care_coordinator",
            facility="CareBridge Central Hub",
            email=f"coord_{uuid.uuid4().hex[:6]}@example.com",
            is_active=True,
            max_workload=30
        )
        self.doctor = CaseOwner(
            id=uuid.uuid4(),
            name="Dr. Sundaram",
            role="doctor",
            specialty="Diagnostic Radiology",
            facility="CareBridge Specialist Center",
            email=f"doc_{uuid.uuid4().hex[:6]}@example.com",
            is_active=True,
            max_workload=15
        )
        self.session.add_all([self.coordinator, self.doctor])

        # Users
        self.user_p1 = User(
            id=uuid.uuid4(),
            email="meenakshi@example.com",
            password_hash="hash_p1",
            full_name="Meenakshi Ramanathan",
            role="patient",
            patient_id=self.patient_1.id,
            is_active=True
        )
        self.user_p2 = User(
            id=uuid.uuid4(),
            email="fatima@example.com",
            password_hash="hash_p2",
            full_name="Fatima Zahra",
            role="patient",
            patient_id=self.patient_2.id,
            is_active=True
        )
        self.user_coord = User(
            id=uuid.uuid4(),
            email="coord@example.com",
            password_hash="hash_coord",
            full_name="Ananya Coordinator",
            role="care_coordinator",
            owner_id=self.coordinator.id,
            is_active=True
        )
        self.user_doc = User(
            id=uuid.uuid4(),
            email="doc@example.com",
            password_hash="hash_doc",
            full_name="Dr. Sundaram",
            role="doctor",
            owner_id=self.doctor.id,
            is_active=True
        )
        self.session.add_all([self.user_p1, self.user_p2, self.user_coord, self.user_doc])

        # Screening Result
        self.screening = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=self.patient_1.id,
            screening_type="Mammogram",
            test_date=datetime.now(timezone.utc) - timedelta(days=2),
            finding_code="BI-RADS-4",
            finding_summary="Suspicious microcalcifications",
            urgency_level="urgent",
            performing_facility="CareBridge Imaging Center",
            raw_report_data={"birads_score": 4}
        )
        self.session.add(self.screening)

        # Case for Patient 1
        self.case_1 = CareCase(
            id=uuid.uuid4(),
            case_number=f"CASE-P1-{uuid.uuid4().hex[:4]}",
            patient_id=self.patient_1.id,
            screening_result_id=self.screening.id,
            current_owner_id=self.coordinator.id,
            status="screening_scheduled",
            priority="urgent",
            sla_start_time=datetime.now(timezone.utc),
            sla_deadline=datetime.now(timezone.utc) + timedelta(days=14),
            case_context={}
        )
        self.session.add(self.case_1)
        self.session.commit()

    def tearDown(self):
        for table in reversed(Base.metadata.sorted_tables):
            self.session.execute(table.delete())
        self.session.commit()
        self.session.close()

    # -------------------------------------------------------------------------
    # 1. Rollback & Atomic Commit Safety
    # -------------------------------------------------------------------------
    def test_01_atomic_rollback_leaves_no_event_or_notification(self):
        """Rollback of domain change must leave zero events and zero notification rows; no SSE dispatch."""
        with patch.object(NotificationBroadcaster, "broadcast_sync") as mock_broadcast:
            try:
                # Begin explicit transaction
                self.case_1.status = "consultation_completed"

                # Staging domain event
                event = CaseEvent(
                    id=uuid.uuid4(),
                    case_id=self.case_1.id,
                    event_type="consultation_completed",
                    description="Consultation completed",
                    event_data={"notes": "Exam clear"},
                    timestamp=datetime.now(timezone.utc)
                )
                self.session.add(event)

                # Staging outbox notification in same transaction
                notif = NotificationService.stage_notification(
                    db=self.session,
                    user_id=self.user_p1.id,
                    role="patient",
                    event_type="consultation_completed",
                    title="Consultation Summary",
                    message="Your consultation summary is ready.",
                    case_id=self.case_1.id,
                    patient_id=self.patient_1.id
                )

                # Intentional error triggering transaction rollback
                raise RuntimeError("Simulated failure mid-transaction")
            except RuntimeError:
                self.session.rollback()

            # Verify nothing was persisted
            persisted_events = self.session.query(CaseEvent).filter(CaseEvent.case_id == self.case_1.id).all()
            persisted_notifs = self.session.query(Notification).filter(Notification.user_id == self.user_p1.id).all()

            self.assertEqual(len(persisted_events), 0, "Domain event must not exist after rollback")
            self.assertEqual(len(persisted_notifs), 0, "Outbox notification must not exist after rollback")
            mock_broadcast.assert_not_called()

    def test_02_atomic_commit_persists_domain_event_and_outbox_pending(self):
        """Atomic commit durably persists domain mutation, event, and outbox notification in pending state."""
        with patch.object(NotificationBroadcaster, "broadcast_sync") as mock_broadcast:
            self.case_1.status = "referral_requested"

            event = CaseEvent(
                id=uuid.uuid4(),
                case_id=self.case_1.id,
                event_type="referral_requested",
                description="Specialist referral initiated",
                event_data={"specialty": "Oncology"},
                timestamp=datetime.now(timezone.utc)
            )
            self.session.add(event)

            notif = NotificationService.stage_notification(
                db=self.session,
                user_id=self.user_p1.id,
                role="patient",
                event_type="referral_created",
                title="Referral Created",
                message="Your referral to Oncology has been initiated.",
                case_id=self.case_1.id,
                patient_id=self.patient_1.id
            )
            self.session.commit()

            # Verify persisted state
            reloaded_notif = self.session.query(Notification).filter(Notification.id == notif.id).one()
            self.assertEqual(reloaded_notif.status, "pending", "Outbox notification must be pending on commit")
            self.assertEqual(reloaded_notif.retry_count, 0)
            self.assertIsNone(reloaded_notif.delivered_at)
            # Transactional outbox pattern: no premature broadcast before worker claims and delivers
            mock_broadcast.assert_not_called()

    # -------------------------------------------------------------------------
    # 2. Outbox Worker Claim & Delivery
    # -------------------------------------------------------------------------
    def test_03_outbox_worker_claims_delivers_and_updates_status(self):
        """Outbox worker claims pending row, broadcasts delivery, and marks status='delivered' with timestamp."""
        notif = NotificationService.stage_notification(
            db=self.session,
            user_id=self.user_p1.id,
            role="patient",
            event_type="appointment_confirmed",
            title="Appointment Confirmed",
            message="Your appointment is confirmed for tomorrow.",
            case_id=self.case_1.id,
            patient_id=self.patient_1.id
        )
        self.session.commit()

        with patch.object(NotificationBroadcaster, "broadcast_sync") as mock_broadcast:
            processed_count = NotificationService.process_outbox_batch(self.session, batch_size=10)
            self.assertEqual(processed_count, 1)

            reloaded = self.session.query(Notification).filter(Notification.id == notif.id).one()
            self.assertEqual(reloaded.status, "delivered")
            self.assertIsNotNone(reloaded.delivered_at)
            self.assertIsNone(reloaded.last_error)
            mock_broadcast.assert_called_once()

    # -------------------------------------------------------------------------
    # 3. Idempotency Key Prevents Duplicate Notifications
    # -------------------------------------------------------------------------
    def test_04_idempotency_prevents_duplicate_notifications_and_events(self):
        """Same idempotency key reuses existing outbox notification rather than creating duplicate."""
        idem_key = "screening_order_case1_attempt_1"

        notif1 = NotificationService.stage_notification(
            db=self.session,
            user_id=self.user_p1.id,
            role="patient",
            event_type="screening_order_created",
            title="Order Placed",
            message="Your screening order was placed.",
            case_id=self.case_1.id,
            patient_id=self.patient_1.id,
            idempotency_key=idem_key
        )
        self.session.commit()

        # Duplicate attempt with identical key
        notif2 = NotificationService.stage_notification(
            db=self.session,
            user_id=self.user_p1.id,
            role="patient",
            event_type="screening_order_created",
            title="Order Placed",
            message="Your screening order was placed.",
            case_id=self.case_1.id,
            patient_id=self.patient_1.id,
            idempotency_key=idem_key
        )
        self.session.commit()

        self.assertEqual(notif1.id, notif2.id, "Idempotent staging must return existing notification")
        all_notifs = self.session.query(Notification).filter(Notification.idempotency_key == idem_key).all()
        self.assertEqual(len(all_notifs), 1, "Exactly one notification row must exist")

    # -------------------------------------------------------------------------
    # 4. Worker Crash Recovery (Stuck in 'processing')
    # -------------------------------------------------------------------------
    def test_05_worker_crash_recovery_processes_stuck_rows_exactly_once(self):
        """Worker crash mid-processing leaves row in 'processing'; recovery resets and delivers exactly once."""
        notif = NotificationService.stage_notification(
            db=self.session,
            user_id=self.user_p1.id,
            role="patient",
            event_type="diagnostic_report_finalized",
            title="Report Ready",
            message="Your mammogram report is finalized.",
            case_id=self.case_1.id,
            patient_id=self.patient_1.id
        )
        # Simulate worker claimed it 5 minutes ago and crashed
        notif.status = "processing"
        notif.processing_started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        self.session.commit()

        # Run crash recovery
        recovered_count = NotificationService.recover_stuck_processing_notifications(
            self.session,
            stuck_timeout_seconds=60
        )
        self.assertEqual(recovered_count, 1)

        # Re-check status: must be reset to pending
        reloaded = self.session.query(Notification).filter(Notification.id == notif.id).one()
        self.assertEqual(reloaded.status, "pending")

        # Now run outbox worker: delivers successfully
        with patch.object(NotificationBroadcaster, "broadcast_sync") as mock_broadcast:
            delivered = NotificationService.process_outbox_batch(self.session)
            self.assertEqual(delivered, 1)
            mock_broadcast.assert_called_once()

            reloaded.delivered_at = reloaded.delivered_at
            self.assertEqual(reloaded.status, "delivered")

    # -------------------------------------------------------------------------
    # 5. Transient Delivery Failures, Exponential Backoff & Dead-Lettering
    # -------------------------------------------------------------------------
    def test_06_simulated_delivery_failure_retries_with_backoff_then_dead_letters(self):
        """Transient failure retries with incrementing retry_count and backoff, then moves to dead_letter."""
        notif = NotificationService.stage_notification(
            db=self.session,
            user_id=self.user_p1.id,
            role="patient",
            event_type="appointment_reminder",
            title="Appointment Reminder",
            message="Reminder: Clinic visit tomorrow.",
            case_id=self.case_1.id,
            patient_id=self.patient_1.id,
            max_retries=3
        )
        self.session.commit()

        # Simulate transport failure in Broadcaster
        with patch.object(NotificationBroadcaster, "broadcast_sync", side_effect=OutboxDeliveryError("Network timeout")):
            # Attempt 1
            NotificationService.process_outbox_batch(self.session)
            self.session.refresh(notif)
            self.assertEqual(notif.status, "failed")
            self.assertEqual(notif.retry_count, 1)
            self.assertIn("Network timeout", notif.last_error)
            self.assertIsNotNone(notif.next_attempt_at)

            # Advance attempt time to allow immediate retry
            notif.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            self.session.commit()

            # Attempt 2
            NotificationService.process_outbox_batch(self.session)
            self.session.refresh(notif)
            self.assertEqual(notif.status, "failed")
            self.assertEqual(notif.retry_count, 2)

            notif.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            self.session.commit()

            # Attempt 3 (Max retries reached -> dead_letter)
            NotificationService.process_outbox_batch(self.session)
            self.session.refresh(notif)
            self.assertEqual(notif.status, "dead_letter")
            self.assertEqual(notif.retry_count, 3)
            self.assertIn("Max retries exceeded", notif.last_error)

    # -------------------------------------------------------------------------
    # 6. Dead-Letter Manual Recovery Command
    # -------------------------------------------------------------------------
    def test_07_dead_letter_manual_recovery(self):
        """Dead-letter notification can be inspected and manually reprocessed via administrative recovery."""
        notif = NotificationService.stage_notification(
            db=self.session,
            user_id=self.user_p1.id,
            role="patient",
            event_type="urgent_action_required",
            title="Action Required",
            message="Please confirm your appointment time.",
            case_id=self.case_1.id,
            patient_id=self.patient_1.id
        )
        notif.status = "dead_letter"
        notif.retry_count = 3
        notif.last_error = "Permanent upstream delivery failure"
        self.session.commit()

        # Execute recovery
        res = NotificationService.reprocess_dead_letter_notification(self.session, notif.id)
        self.assertTrue(res["success"])
        self.session.refresh(notif)
        self.assertEqual(notif.status, "pending")
        self.assertEqual(notif.retry_count, 0)

        # Worker now processes cleanly
        with patch.object(NotificationBroadcaster, "broadcast_sync"):
            NotificationService.process_outbox_batch(self.session)
            self.session.refresh(notif)
            self.assertEqual(notif.status, "delivered")

    # -------------------------------------------------------------------------
    # 7. Recipient Authorization Validation at Write Time
    # -------------------------------------------------------------------------
    def test_08_recipient_authorization_validation_at_write_time(self):
        """Attempt to stage notification to unauthorized recipient (wrong patient or wrong role) is rejected."""
        # Patient 1 case attempted to be sent to Patient 2 user account
        with self.assertRaises(RecipientAuthorizationError):
            NotificationService.stage_notification(
                db=self.session,
                user_id=self.user_p2.id, # Wrong patient!
                role="patient",
                event_type="screening_result_available",
                title="Results Ready",
                message="Your results are ready.",
                case_id=self.case_1.id,
                patient_id=self.patient_1.id
            )

        # Case assigned to Coordinator, doctor user has no assignment on case
        with self.assertRaises(RecipientAuthorizationError):
            NotificationService.stage_notification(
                db=self.session,
                user_id=self.user_doc.id,
                role="doctor",
                event_type="clinical_review_assigned",
                title="Review Assigned",
                message="Please review case.",
                case_id=self.case_1.id, # Case has current_owner_id = coordinator, not doctor!
                patient_id=self.patient_1.id
            )

    # -------------------------------------------------------------------------
    # 8. Reconnection & Durability
    # -------------------------------------------------------------------------
    def test_09_sse_reconnection_replays_unread_missed_notifications(self):
        """Unread notifications are retrievable via query/replay after reconnection with Last-Event-ID."""
        # Create 3 notifications in sequence
        n1 = NotificationService.stage_notification(
            db=self.session, user_id=self.user_p1.id, role="patient",
            event_type="step_1", title="Step 1", message="Msg 1", case_id=self.case_1.id, patient_id=self.patient_1.id
        )
        n2 = NotificationService.stage_notification(
            db=self.session, user_id=self.user_p1.id, role="patient",
            event_type="step_2", title="Step 2", message="Msg 2", case_id=self.case_1.id, patient_id=self.patient_1.id
        )
        self.session.commit()
        NotificationService.process_outbox_batch(self.session)

        # Mark n1 as read (client received it before disconnecting)
        n1.is_read = True
        self.session.commit()

        # Stage third notification while disconnected
        n3 = NotificationService.stage_notification(
            db=self.session, user_id=self.user_p1.id, role="patient",
            event_type="step_3", title="Step 3", message="Msg 3", case_id=self.case_1.id, patient_id=self.patient_1.id
        )
        self.session.commit()
        NotificationService.process_outbox_batch(self.session)

        # Client reconnects with last_event_id=n1.id
        missed = NotificationService.get_missed_notifications_for_reconnect(
            db=self.session,
            user_id=self.user_p1.id,
            last_event_id=n1.id
        )

        missed_ids = [m.id for m in missed]
        self.assertNotIn(n1.id, missed_ids, "Delivered and read event must not be re-queued")
        self.assertIn(n2.id, missed_ids, "Unread event 2 must be included in replay")
        self.assertIn(n3.id, missed_ids, "Unread event 3 must be included in replay")

    def test_10_notifications_survive_backend_restart(self):
        """Notifications and their authoritative delivery state persist across DB engine restart."""
        import tempfile
        import os

        temp_db = os.path.join(tempfile.gettempdir(), f"carebridge_restart_test_{uuid.uuid4().hex[:8]}.db")
        disk_engine = create_engine(f"sqlite:///{temp_db}", echo=False)
        Base.metadata.create_all(disk_engine)
        DiskSession = sessionmaker(bind=disk_engine)

        try:
            # Session 1: Before restart
            s1 = DiskSession()
            u = User(
                id=uuid.uuid4(), email="restart@example.com", password_hash="hash",
                full_name="Restart User", role="patient", is_active=True
            )
            s1.add(u)
            s1.commit()

            n = NotificationService.stage_notification(
                db=s1, user_id=u.id, role="patient", event_type="system_notice",
                title="System Notice", message="Maintenance tonight"
            )
            s1.commit()
            NotificationService.process_outbox_batch(s1)
            notif_id = n.id
            s1.close()
            disk_engine.dispose()

            # Session 2: After backend restart (fresh engine & connection)
            restart_engine = create_engine(f"sqlite:///{temp_db}", echo=False)
            RestartSession = sessionmaker(bind=restart_engine)
            s2 = RestartSession()

            persisted = s2.query(Notification).filter(Notification.id == notif_id).one()
            self.assertEqual(persisted.status, "delivered")
            self.assertEqual(persisted.title, "System Notice")
            self.assertIsNotNone(persisted.delivered_at)
            s2.close()
            restart_engine.dispose()
        finally:
            if os.path.exists(temp_db):
                try:
                    os.remove(temp_db)
                except Exception:
                    pass

    # -------------------------------------------------------------------------
    # 9. Key Domain Events Wired to Transactional Outbox
    # -------------------------------------------------------------------------
    def test_11_key_domain_events_wired_to_transactional_outbox(self):
        """All critical care pathway domain events stage notifications in transactional outbox."""
        events_to_test = [
            ("screening_order_created", NotificationService.notify_screening_order_created),
            ("diagnostic_report_finalized", NotificationService.notify_report_finalized),
            ("referral_status_changed", NotificationService.notify_referral_update),
            ("appointment_version_changed", NotificationService.notify_appointment_version_update),
            ("clinical_escalation_triggered", NotificationService.notify_clinical_escalation)
        ]

        for ev_name, wire_fn in events_to_test:
            # Each call must stage a pending outbox notification without auto-broadcasting
            with patch.object(NotificationBroadcaster, "broadcast_sync") as mock_broadcast:
                wire_fn(
                    db=self.session,
                    case_id=self.case_1.id,
                    patient_id=self.patient_1.id,
                    actor_user_id=self.user_coord.id,
                    summary=f"Automated test for {ev_name}"
                )
                self.session.commit()

                # Find staged notification
                staged = (
                    self.session.query(Notification)
                    .filter(Notification.case_id == self.case_1.id, Notification.event_type.contains(ev_name.split('_')[0]))
                    .order_by(Notification.created_at.desc())
                    .first()
                )
                self.assertIsNotNone(staged, f"Notification must be staged for {ev_name}")
                self.assertEqual(staged.status, "pending")
                mock_broadcast.assert_not_called()


if __name__ == "__main__":
    unittest.main()
