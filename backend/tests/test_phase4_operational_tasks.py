"""
CareBridge Phase 4 Acceptance Test Suite: Operational Task Ownership & Handoffs

Verifies acceptance criteria for:
1. One Task Model: patient_id, case_id, task_type, assigned_role, assigned_to_id, status, priority, due_date, completed_at, completed_by_id, completed_by_role, completion_evidence, idempotency_key.
2. Patient AI Screening Handoff: Creates authoritative coordinator task in the same transaction as screening requirement. Notification is never a substitute for a task.
3. Coordinator to Doctor Handoff: Persists DoctorAssignment request (PENDING_DOCTOR_RESPONSE) and notifies doctor.
4. Doctor Accept/Decline & SLA: Doctor acceptance updates case owner to doctor and advances lifecycle stage. Doctor decline creates coordinator escalation task.
5. Doctor SLA Timeout: Scan and expire transitions timed out assignments to EXPIRED and creates coordinator escalation task idempotently.
6. Doctor Authorization Boundary: Doctor cannot see, accept, or decline unassigned cases.
7. Recovery Agent Missed Appointment Handoff: Missed appointment (NO_SHOW) triggers recovery task with barrier data (transport, scheduling, financial).
8. Clinical Escalation Handoff: Red-flag acute symptoms create urgent clinical task with preserved evidence deterministically without LLM.
9. Failed Tool Calls / Handoffs: Tool execution failure creates a recoverable task; never loses a handoff silently.
10. Evidence-Driven Closure: Tasks close only with completion evidence and completion actor (completed_by_id, completed_by_role).
11. Task SLA Background Job: Overdue tasks identified and escalated idempotently.
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
from app.models.doctor_assignment import DoctorAssignment
from app.models.case_lifecycle_stage import CaseLifecycleStage

from app.services.doctor_allocation_service import DoctorAllocationService
from app.services.lifecycle_service import LifecycleService, LifecycleTransitionError
from app.services.task_service import TaskService
from app.tools.registry import ToolRegistry, ToolExecutionResult


class TestPhase4OperationalTasks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.session = self.SessionLocal()

        # 1. Patient
        self.patient = Patient(
            id=uuid.uuid4(),
            mrn=f"MRN-P4-{uuid.uuid4().hex}",
            first_name="Meenakshi",
            last_name="Ramanathan",
            date_of_birth=date(1980, 3, 15),
            gender="female",
            phone=f"+1555{uuid.uuid4().hex[:7]}",
            preferred_language="en"
        )
        self.session.add(self.patient)

        # 2. Screening Result
        self.screening = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=self.patient.id,
            screening_type="Mammogram",
            test_date=datetime.now(timezone.utc) - timedelta(days=2),
            finding_code="BI-RADS-4",
            finding_summary="Suspicious mass in upper outer quadrant.",
            urgency_level="urgent",
            performing_facility="Boston Oncology Pavilion"
        )
        self.session.add(self.screening)

        # 3. Coordinator CaseOwner & User
        self.coord_owner = CaseOwner(
            id=uuid.uuid4(),
            name="Sarah Jenkins",
            role="care_coordinator",
            facility="CareBridge Hub",
            email=f"sarah_owner_{uuid.uuid4().hex}@carebridge.org",
            is_active=True
        )
        self.session.add(self.coord_owner)
        self.session.flush()

        self.coord_user = User(
            id=uuid.uuid4(),
            email=f"sarah_{uuid.uuid4().hex}@carebridge.org",
            role="care_coordinator",
            owner_id=self.coord_owner.id,
            is_active=True,
            password_hash="dummy_hash",
            full_name="Sarah Jenkins"
        )
        self.session.add(self.coord_user)

        # 4. Doctor A CaseOwner & User
        self.doctor_owner_a = CaseOwner(
            id=uuid.uuid4(),
            name="Dr. Jane Ellis",
            role="specialist",
            specialty="Breast Oncology",
            facility="Boston Oncology Pavilion",
            email=f"dr_ellis_owner_{uuid.uuid4().hex}@carebridge.org",
            is_active=True,
            eligibility_status="eligible",
            max_workload=20,
            response_deadline_hours=24
        )
        self.session.add(self.doctor_owner_a)
        self.session.flush()

        self.doctor_user_a = User(
            id=uuid.uuid4(),
            email=f"dr_ellis_{uuid.uuid4().hex}@carebridge.org",
            role="doctor",
            owner_id=self.doctor_owner_a.id,
            is_active=True,
            password_hash="dummy_hash",
            full_name="Dr. Jane Ellis"
        )
        self.session.add(self.doctor_user_a)

        # 5. Doctor B CaseOwner & User
        self.doctor_owner_b = CaseOwner(
            id=uuid.uuid4(),
            name="Dr. Robert Hayes",
            role="specialist",
            specialty="Breast Oncology",
            facility="Boston Oncology Pavilion",
            email=f"dr_hayes_owner_{uuid.uuid4().hex}@carebridge.org",
            is_active=True,
            eligibility_status="eligible",
            max_workload=20,
            response_deadline_hours=24
        )
        self.session.add(self.doctor_owner_b)
        self.session.flush()

        self.doctor_user_b = User(
            id=uuid.uuid4(),
            email=f"dr_hayes_{uuid.uuid4().hex}@carebridge.org",
            role="doctor",
            owner_id=self.doctor_owner_b.id,
            is_active=True,
            password_hash="dummy_hash",
            full_name="Dr. Robert Hayes"
        )
        self.session.add(self.doctor_user_b)

        # 6. Patient User
        self.patient_user = User(
            id=uuid.uuid4(),
            email=f"meenakshi_{uuid.uuid4().hex}@carebridge.org",
            role="patient",
            patient_id=self.patient.id,
            is_active=True,
            password_hash="dummy_hash",
            full_name="Meenakshi Ramanathan"
        )
        self.session.add(self.patient_user)

        # 7. CareCase
        now = datetime.now(timezone.utc)
        self.case = CareCase(
            id=uuid.uuid4(),
            case_number=f"CAS-P4-{uuid.uuid4().hex}",
            patient_id=self.patient.id,
            screening_result_id=self.screening.id,
            current_owner_id=self.coord_owner.id,
            status="active",
            clinical_pathway="breast_cancer_followup",
            priority="urgent",
            sla_start_time=now,
            sla_deadline=now + timedelta(days=7),
            sla_status="normal",
            case_context={"notes": []}
        )
        self.session.add(self.case)
        self.session.commit()

    def tearDown(self):
        self.session.close()

    def test_01_patient_ai_screening_handoff_creates_authoritative_coordinator_task(self):
        """1. Patient AI screening handoff creates real coordinator task in same transaction; notification alone is never a task."""
        # When patient intake identifies screening order requirement:
        task = TaskService.create_screening_handoff_task(
            db=self.session,
            case_id=self.case.id,
            patient_id=self.patient.id,
            screening_type="diagnostic_mammography",
            notes="Patient completed questionnaire; needs diagnostic mammography scheduled within SLA.",
            idempotency_key=f"screening_handoff_{self.case.id}"
        )
        self.session.commit()

        self.assertIsNotNone(task)
        self.assertEqual(task.patient_id, self.patient.id)
        self.assertEqual(task.case_id, self.case.id)
        self.assertEqual(task.assigned_role, "care_coordinator")
        self.assertEqual(task.status, "pending")
        self.assertEqual(task.task_type, "schedule_screening")
        self.assertIsNotNone(task.due_date)

        # Verify the task is queryable and not just a notification
        stored_task = self.session.query(Task).filter(Task.id == task.id).first()
        self.assertIsNotNone(stored_task)
        self.assertEqual(stored_task.assigned_role, "care_coordinator")

    def test_02_coordinator_to_doctor_handoff_persists_assignment_and_notifies_doctor(self):
        """2. Coordinator to Doctor handoff persists DoctorAssignment request (PENDING_DOCTOR_RESPONSE) and notifies doctor."""
        assignment = DoctorAllocationService.allocate_doctor_for_case(
            db=self.session,
            case_id=self.case.id,
            required_specialty="Breast Oncology",
            urgency_level="urgent",
            assigned_by_role="care_coordinator",
            assigned_by_id=str(self.coord_user.id)
        )
        self.session.commit()

        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.status, "PENDING_DOCTOR_RESPONSE")
        self.assertEqual(assignment.case_id, self.case.id)
        assigned_doc = self.session.query(CaseOwner).filter(CaseOwner.id == assignment.doctor_id).first()
        self.assertIsNotNone(assigned_doc)
        self.assertEqual(assigned_doc.specialty, "Breast Oncology")

        # Verify notification was queued for doctor
        notif = self.session.query(Notification).filter(
            Notification.case_id == self.case.id,
            Notification.event_type == "doctor_assignment_requested"
        ).first()
        self.assertIsNotNone(notif)

    def test_03_doctor_accept_updates_case_owner_and_advances_stage(self):
        """3. Doctor acceptance updates case owner to doctor, advances lifecycle stage, and notifies patient."""
        # Initialize lifecycle stages (Stages 1 and 2 auto-completed from screening result)
        LifecycleService.initialize_lifecycle(self.session, self.case, self.screening, self.patient)
        LifecycleService.advance_stage(
            self.session, case_id=self.case.id, stage_ident=3,
            actor_role="care_coordinator", actor_id=str(self.coord_owner.id),
            evidence={"notification_id": str(uuid.uuid4()), "delivery_status": "delivered", "channel": "sms"}
        )
        LifecycleService.advance_stage(
            self.session, case_id=self.case.id, stage_ident=4,
            actor_role="ai_coordinator", actor_id="carebridge_ai_companion",
            evidence={"explanation_summary": "Explained BI-RADS 4 finding in plain language", "patient_understanding_confirmed": True}
        )

        assignment = DoctorAllocationService.request_doctor_assignment(
            db=self.session,
            case_id=self.case.id,
            doctor_id=self.doctor_owner_a.id,
            specialty_matched="Breast Oncology",
            urgency_level="urgent",
            assigned_by_role="care_coordinator",
            assigned_by_id=self.coord_owner.id
        )

        accepted = DoctorAllocationService.doctor_accept_assignment(
            db=self.session,
            assignment_id=assignment.id,
            doctor_user_id=self.doctor_user_a.id
        )

        # Refresh case
        self.session.refresh(self.case)
        self.assertEqual(accepted.status, "ACCEPTED")
        self.assertEqual(self.case.current_owner_id, self.doctor_owner_a.id)

        # Lifecycle Stage 5 (CLINICAL_REVIEW) is completed upon doctor acceptance
        stages = LifecycleService.get_lifecycle_stages(self.case)
        stage_5 = next(s for s in stages if s.get("stage_number") == 5)
        self.assertEqual(stage_5.get("status"), "completed")
        self.assertEqual(stage_5.get("stage_id"), "CLINICAL_REVIEW")

        # Patient receives notification ONLY after acceptance
        pat_notif = self.session.query(Notification).filter(
            Notification.case_id == self.case.id,
            Notification.event_type == "specialist_doctor_confirmed"
        ).first()
        self.assertIsNotNone(pat_notif)
        self.assertEqual(pat_notif.user_id, self.patient_user.id)

    def test_04_doctor_decline_creates_coordinator_escalation_task(self):
        """4. Doctor decline creates coordinator escalation task and keeps coordinator case ownership."""
        assignment = DoctorAllocationService.request_doctor_assignment(
            db=self.session,
            case_id=self.case.id,
            doctor_id=self.doctor_owner_a.id,
            specialty_matched="Breast Oncology",
            urgency_level="urgent",
            assigned_by_role="care_coordinator",
            assigned_by_id=self.coord_owner.id
        )

        declined = DoctorAllocationService.doctor_decline_assignment(
            db=self.session,
            assignment_id=assignment.id,
            doctor_user_id=self.doctor_user_a.id,
            decline_reason="Clinical capacity exceeded for emergency surgical intake."
        )

        self.session.refresh(self.case)
        self.assertEqual(declined.status, "DECLINED")
        self.assertEqual(self.case.current_owner_id, self.coord_owner.id)

        # Escalation task exists for coordinator
        esc_task = self.session.query(Task).filter(
            Task.case_id == self.case.id,
            Task.task_type == "specialist_reassignment"
        ).first()
        self.assertIsNotNone(esc_task)
        self.assertEqual(esc_task.assigned_role, "care_coordinator")
        self.assertEqual(esc_task.patient_id, self.patient.id)
        self.assertEqual(esc_task.priority, "urgent")

    def test_05_doctor_sla_timeout_expires_and_escalates_to_coordinator(self):
        """5. SLA timeout marks assignment EXPIRED and creates coordinator escalation task idempotently."""
        now = datetime.now(timezone.utc)
        assignment = DoctorAssignment(
            id=uuid.uuid4(),
            case_id=self.case.id,
            doctor_id=self.doctor_owner_a.id,
            status="PENDING_DOCTOR_RESPONSE",
            specialty_matched="Breast Oncology",
            urgency_level="urgent",
            assigned_by_role="care_coordinator",
            deadline=now - timedelta(hours=2),  # Timed out
            allocation_score=35.0,
            idempotency_key=f"timeout_test_{uuid.uuid4().hex[:8]}"
        )
        self.session.add(assignment)
        self.session.commit()

        # Run scanner
        res = DoctorAllocationService.scan_and_expire_assignments(self.session)
        self.assertEqual(res["expired_count"], 1)

        self.session.refresh(assignment)
        self.assertEqual(assignment.status, "EXPIRED")

        timeout_task = self.session.query(Task).filter(
            Task.case_id == self.case.id,
            Task.task_type == "assignment_timeout_escalation"
        ).first()
        self.assertIsNotNone(timeout_task)
        self.assertEqual(timeout_task.assigned_role, "care_coordinator")
        self.assertEqual(timeout_task.patient_id, self.patient.id)

        # Running scan again is idempotent: 0 additional expired
        res2 = DoctorAllocationService.scan_and_expire_assignments(self.session)
        self.assertEqual(res2["expired_count"], 0)

    def test_06_doctor_cannot_view_or_accept_unassigned_cases(self):
        """6. Doctor B cannot accept an assignment directed to Doctor A."""
        assignment = DoctorAllocationService.request_doctor_assignment(
            db=self.session,
            case_id=self.case.id,
            doctor_id=self.doctor_owner_a.id,
            specialty_matched="Breast Oncology",
            urgency_level="urgent",
            assigned_by_role="care_coordinator",
            assigned_by_id=self.coord_owner.id
        )

        with self.assertRaises(PermissionError):
            DoctorAllocationService.doctor_accept_assignment(
                db=self.session,
                assignment_id=assignment.id,
                doctor_user_id=self.doctor_user_b.id  # Wrong doctor!
            )

    def test_07_recovery_agent_creates_recovery_task_with_barrier_data_on_no_show(self):
        """7. Recovery Agent: missed appointment (NO_SHOW) creates recovery task with barrier data."""
        # Create an appointment with status NO_SHOW
        appt = Appointment(
            id=uuid.uuid4(),
            patient_id=self.patient.id,
            case_id=self.case.id,
            appointment_type="consultation",
            scheduled_time=datetime.now(timezone.utc) - timedelta(days=1),
            provider_name="Dr. Jane Ellis",
            facility="Boston Oncology Pavilion",
            status="no_show"
        )
        self.session.add(appt)
        self.session.commit()

        # Trigger recovery task creation via TaskService
        recovery_task = TaskService.create_recovery_task(
            db=self.session,
            case_id=self.case.id,
            patient_id=self.patient.id,
            barrier_type="transportation_caregiver",
            barrier_description="Patient missed appointment due to family caregiver absence.",
            idempotency_key=f"recovery_noshow_{appt.id}"
        )
        self.session.commit()

        self.assertIsNotNone(recovery_task)
        self.assertEqual(recovery_task.task_type, "recovery_play")
        self.assertEqual(recovery_task.assigned_role, "care_coordinator")
        self.assertEqual(recovery_task.patient_id, self.patient.id)
        self.assertEqual(recovery_task.case_id, self.case.id)
        self.assertIn("transportation_caregiver", str(recovery_task.description))

        # Idempotency: re-running does not duplicate
        dup_task = TaskService.create_recovery_task(
            db=self.session,
            case_id=self.case.id,
            patient_id=self.patient.id,
            barrier_type="transportation_caregiver",
            barrier_description="Duplicate call",
            idempotency_key=f"recovery_noshow_{appt.id}"
        )
        self.assertEqual(dup_task.id, recovery_task.id)

    def test_08_clinical_escalation_creates_urgent_clinical_task_deterministic(self):
        """8. Red-flag acute symptoms create urgent clinical task with preserved evidence deterministically without LLM."""
        urgent_task = TaskService.create_clinical_escalation_task(
            db=self.session,
            case_id=self.case.id,
            patient_id=self.patient.id,
            red_flag_symptoms=["severe_uncontrolled_pain", "acute_post_op_bleeding"],
            patient_statement="I have heavy bleeding and severe 10/10 chest pain since this morning.",
            idempotency_key=f"clin_esc_{self.case.id}"
        )
        self.session.commit()

        self.assertIsNotNone(urgent_task)
        self.assertEqual(urgent_task.task_type, "clinical_escalation")
        self.assertEqual(urgent_task.priority, "critical")
        self.assertEqual(urgent_task.patient_id, self.patient.id)
        self.assertEqual(urgent_task.case_id, self.case.id)
        self.assertIn("severe_uncontrolled_pain", urgent_task.description)

        # Must notify clinical staff / doctor
        notif = self.session.query(Notification).filter(
            Notification.case_id == self.case.id,
            Notification.event_type == "clinical_escalation"
        ).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.priority, "urgent")

    def test_09_failed_tool_call_persists_recoverable_task(self):
        """9. If a tool call fails during execution, persist a recoverable task so handoffs are never silently lost."""
        failed_task = TaskService.record_failed_tool_handoff(
            db=self.session,
            case_id=self.case.id,
            patient_id=self.patient.id,
            tool_name="schedule_screening_appointment",
            tool_arguments={"slot_id": "SLOT-999", "patient_id": str(self.patient.id)},
            error_message="Upstream EHR scheduling connector timeout after 30s.",
            idempotency_key=f"tool_fail_{uuid.uuid4().hex[:8]}"
        )
        self.session.commit()

        self.assertIsNotNone(failed_task)
        self.assertEqual(failed_task.task_type, "failed_handoff_recovery")
        self.assertEqual(failed_task.assigned_role, "care_coordinator")
        self.assertEqual(failed_task.status, "pending")
        self.assertEqual(failed_task.priority, "urgent")
        self.assertEqual(failed_task.patient_id, self.patient.id)
        self.assertIn("schedule_screening_appointment", failed_task.description)

    def test_10_task_closure_requires_completion_evidence_and_actor(self):
        """10. Tasks close only with completion evidence and a completion actor (completed_by_id, completed_by_role)."""
        now = datetime.now(timezone.utc)
        task = Task(
            id=uuid.uuid4(),
            case_id=self.case.id,
            patient_id=self.patient.id,
            title="Coordinate transportation assistance",
            description="Arrange medical transit voucher for diagnostic appointment.",
            task_type="barrier_resolution",
            assigned_role="care_coordinator",
            status="in_progress",
            priority="standard",
            due_date=now + timedelta(days=2),
            idempotency_key=f"task_closure_test_{uuid.uuid4().hex[:8]}"
        )
        self.session.add(task)
        self.session.commit()

        # Attempt closure WITHOUT completion evidence -> Must fail
        with self.assertRaises(ValueError):
            TaskService.complete_task(
                db=self.session,
                task_id=task.id,
                completed_by_id=str(self.coord_user.id),
                completed_by_role="care_coordinator",
                completion_evidence=None  # Missing evidence!
            )

        # Attempt closure WITHOUT completion actor -> Must fail
        with self.assertRaises(ValueError):
            TaskService.complete_task(
                db=self.session,
                task_id=task.id,
                completed_by_id="",  # Missing actor!
                completed_by_role="",
                completion_evidence={"transit_voucher_issued": "TX-99881"}
            )

        # Successful closure with evidence and actor
        completed = TaskService.complete_task(
            db=self.session,
            task_id=task.id,
            completed_by_id=str(self.coord_user.id),
            completed_by_role="care_coordinator",
            completion_evidence={"transit_voucher_issued": "TX-99881", "ride_confirmed": True}
        )
        self.session.commit()

        self.assertEqual(completed.status, "completed")
        self.assertIsNotNone(completed.completed_at)
        self.assertEqual(completed.completed_by_id, str(self.coord_user.id))
        self.assertEqual(completed.completed_by_role, "care_coordinator")
        self.assertTrue(completed.completion_evidence["ride_confirmed"])

    def test_11_task_sla_background_job_identifies_overdue_tasks(self):
        """11. Task SLA background job scans and escalates overdue tasks idempotently."""
        now = datetime.now(timezone.utc)
        overdue_task = Task(
            id=uuid.uuid4(),
            case_id=self.case.id,
            patient_id=self.patient.id,
            title="Overdue biopsy follow-up",
            description="Pending biopsy scheduling past SLA.",
            task_type="patient_outreach",
            assigned_role="care_coordinator",
            status="pending",
            priority="standard",
            due_date=now - timedelta(hours=6),  # Overdue
            idempotency_key=f"overdue_test_{uuid.uuid4().hex[:8]}"
        )
        self.session.add(overdue_task)
        self.session.commit()

        report = TaskService.scan_and_escalate_overdue_tasks(self.session)
        self.assertGreaterEqual(report["overdue_count"], 1)

        self.session.refresh(overdue_task)
        self.assertIn(overdue_task.status, ["overdue", "escalated"])

        # Running again does not re-escalate already escalated tasks
        report2 = TaskService.scan_and_escalate_overdue_tasks(self.session)
        self.assertEqual(report2["escalated_count"], 0)
