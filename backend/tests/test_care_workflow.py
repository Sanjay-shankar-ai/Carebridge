"""
CareBridge End-to-End Care Coordination Workflow Tests
Validates the complete 11-node StateGraph execution, conditional routing,
thread persistence, resumption after events, dropoff recovery, and human clinical closure gate.
"""

import unittest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from langgraph.checkpoint.memory import MemorySaver

from app.database.session import Base
import app.database.session as session_module
from app.database.seed import seed_database
from app.models import (
    Patient, CareCase, CaseOwner, ScreeningResult, Appointment,
    Task, Referral, Communication, ClosureEvidence
)
from app.core.config import settings
from app.workflows import (
    create_carebridge_workflow,
    run_carebridge_workflow,
    resume_carebridge_workflow
)


class TestCareWorkflowIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings.LLM_PROVIDER = "mock"
        cls.engine = create_engine("sqlite:///:memory:")
        cls.SessionFactory = sessionmaker(bind=cls.engine)
        session_module.sync_session_factory = cls.SessionFactory

    def setUp(self):
        Base.metadata.create_all(self.engine)
        self.session = self.SessionFactory()
        seed_database(self.session)

        self.patient = self.session.query(Patient).first()
        self.screening = self.session.query(ScreeningResult).filter(ScreeningResult.patient_id == self.patient.id).first()
        self.case = self.session.query(CareCase).filter(CareCase.patient_id == self.patient.id).first()
        self.checkpointer = MemorySaver()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)

    # --------------------------------------------------------------------------
    # Test 1: Intake to Outreach (Unacknowledged pauses safely at END)
    # --------------------------------------------------------------------------
    def test_01_intake_to_outreach_unacknowledged_safe_pause(self):
        # Create a fresh abnormal screening result
        new_screening = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=self.patient.id,
            screening_type="Mammogram",
            test_date=datetime.now(timezone.utc),
            finding_code="BI-RADS-4",
            finding_summary="Suspicious lesion in upper outer quadrant",
            urgency_level="urgent",
            performing_facility="Metropolitan Breast Center"
        )
        self.session.add(new_screening)
        self.session.commit()

        case_id = str(uuid.uuid4())
        result = run_carebridge_workflow(
            screening_result_id=str(new_screening.id),
            case_id=case_id,
            patient_id=str(self.patient.id),
            patient_acknowledged=False,
            checkpointer=self.checkpointer
        )

        # Graph should have created case, matched pathway, sent communication, and paused awaiting ack
        self.assertEqual(result.get("workflow_phase"), "acknowledgement_pending")
        self.assertFalse(result.get("patient_acknowledged"))
        self.assertIn("mammogram", result.get("clinical_pathway", ""))
        self.assertIsNotNone(result.get("drafted_communication"))

        # Verify DB state
        self.session.expire_all()
        db_case = self.session.query(CareCase).filter(CareCase.id == uuid.UUID(case_id)).first()
        self.assertIsNotNone(db_case)
        self.assertEqual(db_case.clinical_pathway, result.get("clinical_pathway"))

    # --------------------------------------------------------------------------
    # Test 2: Resumption after Patient Acknowledges -> Referral -> Appointment
    # --------------------------------------------------------------------------
    def test_02_patient_acknowledgement_resumes_to_appointment(self):
        # Create fresh screening to test full forward progression
        ack_screening = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=self.patient.id,
            screening_type="Mammogram",
            test_date=datetime.now(timezone.utc),
            finding_code="BI-RADS-4",
            finding_summary="Follow-up diagnostic workup required",
            urgency_level="standard",
            performing_facility="Chennai Diagnostics"
        )
        self.session.add(ack_screening)
        self.session.commit()

        case_id = str(uuid.uuid4())
        result = run_carebridge_workflow(
            screening_result_id=str(ack_screening.id),
            case_id=case_id,
            patient_id=str(self.patient.id),
            patient_acknowledged=True,
            latest_patient_message="Yes, I understand my results and want to book the earliest appointment.",
            checkpointer=self.checkpointer
        )

        # Graph should progress through referral, appointment, and monitoring
        self.assertTrue(result.get("patient_acknowledged"))
        self.assertIn(result.get("referral_status"), ["sent", "accepted"])
        self.assertIsNotNone(result.get("referral_id"))
        self.assertIn(result.get("appointment_status"), ["booked", "confirmed"])
        self.assertIsNotNone(result.get("appointment_id"))
        self.assertEqual(result.get("workflow_phase"), "monitored")

        # Verify DB reflects scheduled appointment
        self.session.expire_all()
        db_app = self.session.query(Appointment).filter(Appointment.case_id == uuid.UUID(case_id)).first()
        self.assertIsNotNone(db_app)

    # --------------------------------------------------------------------------
    # Test 3: Dropoff Detection & Proactive Recovery Playbook
    # --------------------------------------------------------------------------
    def test_03_stalled_dropoff_triggers_proactive_recovery(self):
        case_id = str(self.case.id)
        # Seed transport barrier
        ctx = dict(self.case.case_context or {})
        ctx["inferred_barriers"] = [{"barrier_type": "transportation", "severity": "high"}]
        ctx["recovery_attempts"] = 0
        self.case.case_context = ctx
        self.session.commit()

        # Resume workflow with stalled status
        updates = {
            "case_id": case_id,
            "patient_acknowledged": False,
            "is_stalled": True,
            "days_inactive": 6.0,
            "next_step": "detect_dropoff"
        }
        result = resume_carebridge_workflow(case_id, updates, checkpointer=self.checkpointer)

        self.assertTrue(result.get("dropoff_risk"))
        self.assertEqual(result.get("workflow_phase"), "recovery_initiated")
        self.assertEqual(result.get("recovery_attempts"), 1)
        self.assertEqual(result.get("recovery_strategy"), "transportation_assistance_navigation")

        # Verify recovery task created in DB
        self.session.expire_all()
        recovery_task = (
            self.session.query(Task)
            .filter(Task.case_id == self.case.id, Task.task_type == "recovery_play")
            .first()
        )
        self.assertIsNotNone(recovery_task)

    # --------------------------------------------------------------------------
    # Test 4: Exhausted Recovery Triggers Escalation
    # --------------------------------------------------------------------------
    def test_04_exhausted_recovery_triggers_escalation(self):
        case_id = str(self.case.id)
        # Set attempts to 3 (exhausted)
        ctx = dict(self.case.case_context or {})
        ctx["recovery_attempts"] = 3
        self.case.case_context = ctx
        self.session.commit()

        updates = {
            "case_id": case_id,
            "dropoff_risk": True,
            "recovery_attempts": 3,
            "dropoff_reasons": ["multiple_no_shows_after_3_attempts"],
            "next_step": "detect_dropoff"
        }
        result = resume_carebridge_workflow(case_id, updates, checkpointer=self.checkpointer)

        self.assertEqual(result.get("workflow_phase"), "escalated")
        self.assertEqual(result.get("priority"), "critical")
        self.assertEqual(result.get("escalation_level"), "critical")

        # Verify DB case status
        self.session.expire_all()
        db_case = self.session.query(CareCase).filter(CareCase.id == self.case.id).first()
        self.assertEqual(db_case.priority, "critical")

    # --------------------------------------------------------------------------
    # Test 5: Human Clinical Approval Gate for Case Closure
    # --------------------------------------------------------------------------
    def test_05_closure_safety_and_human_approval_gate(self):
        case_id = str(self.case.id)

        # 1. Without clinician sign-off, closure must NOT be approved by AI
        updates_unverified = {
            "case_id": case_id,
            "appointment_attended": True,
            "human_decision": None,
            "next_step": "verify_closure"
        }
        res_unverified = resume_carebridge_workflow(case_id, updates_unverified, checkpointer=self.checkpointer)

        self.assertFalse(res_unverified.get("closure_verified"))
        self.assertTrue(res_unverified.get("requires_human_approval"))
        self.assertEqual(res_unverified.get("workflow_phase"), "closure_pending_human_signoff")

        # 2. Resuming with authorized human clinical sign-off safely closes case
        updates_approved = {
            "case_id": case_id,
            "human_decision": "approved",
            "next_step": "verify_closure"
        }
        res_approved = resume_carebridge_workflow(case_id, updates_approved, checkpointer=self.checkpointer)

        self.assertTrue(res_approved.get("closure_verified"))
        self.assertEqual(res_approved.get("status"), "closed")
        self.assertEqual(res_approved.get("workflow_phase"), "closed")

        # Verify DB case is closed
        self.session.expire_all()
        db_case = self.session.query(CareCase).filter(CareCase.id == self.case.id).first()
        self.assertEqual(db_case.status, "closed")

    # --------------------------------------------------------------------------
    # Test 6: Workflow Idempotency Across Re-runs
    # --------------------------------------------------------------------------
    def test_06_workflow_idempotency_no_duplicate_records(self):
        case_id = str(self.case.id)

        # First run
        run_carebridge_workflow(
            screening_result_id=str(self.screening.id),
            case_id=case_id,
            patient_id=str(self.patient.id),
            patient_acknowledged=True,
            checkpointer=self.checkpointer
        )

        app_count_1 = self.session.query(Appointment).filter(Appointment.case_id == self.case.id).count()
        ref_count_1 = self.session.query(Referral).filter(Referral.case_id == self.case.id).count()

        # Second run with exact same parameters
        run_carebridge_workflow(
            screening_result_id=str(self.screening.id),
            case_id=case_id,
            patient_id=str(self.patient.id),
            patient_acknowledged=True,
            checkpointer=self.checkpointer
        )

        app_count_2 = self.session.query(Appointment).filter(Appointment.case_id == self.case.id).count()
        ref_count_2 = self.session.query(Referral).filter(Referral.case_id == self.case.id).count()

        self.assertEqual(app_count_1, app_count_2)
        self.assertEqual(ref_count_1, ref_count_2)


if __name__ == "__main__":
    unittest.main()
