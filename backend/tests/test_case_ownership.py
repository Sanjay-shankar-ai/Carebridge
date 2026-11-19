"""
CareBridge End-to-End Care Case Ownership Test Suite
Validates:
1. Accountable Care Coordinator retrieval.
2. Ownership continuity during appointment cancellation and rescheduling.
3. Case owner assignment with history tracking.
4. Ownership transfer between coordinators with audit trail.
5. Pending coordination tasks and milestone retrieval.
6. Stalled care journey detection.
7. Care coordinator alert notifications.
8. Unowned case emergency escalation (UNASSIGNED_ESCALATED state).
9. Closure requirements checklist (5-point clinical & coordination verification).
10. LangGraph Supervisor integration with ownership awareness.
"""

import unittest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.session import Base
from app.database.seed import seed_database
from app.models import Patient, CareCase, CaseOwner, Appointment, Task, CaseOwnershipHistory, AuditLog, ScreeningResult
from app.tools.registry import ToolRegistry
from app.agents.graph import create_carebridge_graph
from langgraph.checkpoint.memory import MemorySaver


class TestCaseOwnership(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False, future=True)
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionFactory = sessionmaker(bind=cls.engine, autocommit=False, autoflush=False)

        import app.database.session
        app.database.session.sync_session_factory = cls.SessionFactory

        from app.core.config import settings
        settings.LLM_PROVIDER = "mock"

    def setUp(self):
        self.session = self.SessionFactory()
        seed_database(self.session)

        self.case = self.session.query(CareCase).filter(CareCase.case_number == "CASE-2026-0147").first()
        self.patient = self.session.query(Patient).filter(Patient.mrn == "MRN-2026-0147").first()
        self.owner = self.session.query(CaseOwner).filter(CaseOwner.name == "Priya Nair, RN").first()

    def tearDown(self):
        self.session.close()

    def test_01_get_case_owner(self):
        """1. Retrieves designated accountable Care Coordinator."""
        res = ToolRegistry.get_case_owner(self.session, str(self.case.id))
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["owner_id"], str(self.owner.id))
        self.assertEqual(res["data"]["name"], "Priya Nair, RN")
        self.assertEqual(res["data"]["role"], "care_coordinator")

    def test_02_ownership_continuity_during_cancellation_and_reschedule(self):
        """2. Core Principle: Coordinator retains ownership when appointments are cancelled or rescheduled."""
        initial_owner_id = self.case.current_owner_id
        self.assertIsNotNone(initial_owner_id)

        active_appt = self.session.query(Appointment).filter(Appointment.case_id == self.case.id).first()
        self.assertIsNotNone(active_appt)

        # Cancel appointment due to caregiver barrier
        cancel_res = ToolRegistry.cancel_appointment(
            db=self.session,
            appointment_id=str(active_appt.id),
            case_id=str(self.case.id),
            reason="caregiver_transport_unavailable",
            outcome="reschedule_pending"
        )
        self.assertTrue(cancel_res["success"])

        # Verify case owner is STILL Priya Nair
        updated_case = self.session.query(CareCase).filter(CareCase.id == self.case.id).first()
        self.assertEqual(updated_case.current_owner_id, initial_owner_id)
        self.assertEqual(updated_case.current_owner.name, "Priya Nair, RN")

    def test_03_assign_case_owner_with_history(self):
        """3. Assigning owner creates continuous history record and audit log."""
        new_coordinator = CaseOwner(
            id=uuid.uuid4(),
            name="Deepa Sundaram, RN",
            role="care_coordinator",
            email="deepa.sundaram@metrogovhealth.org",
            facility="Metropolitan Breast Center",
            is_active=True
        )
        self.session.add(new_coordinator)
        self.session.commit()

        res = ToolRegistry.assign_case_owner(
            db=self.session,
            case_id=str(self.case.id),
            new_owner_id=str(new_coordinator.id),
            assigned_by="clinical_supervisor",
            reason="Workload rebalancing"
        )
        self.assertTrue(res["success"])

        # Check history table
        hist = (
            self.session.query(CaseOwnershipHistory)
            .filter(CaseOwnershipHistory.case_id == self.case.id, CaseOwnershipHistory.is_active.is_(True))
            .first()
        )
        self.assertIsNotNone(hist)
        self.assertEqual(hist.new_owner_id, new_coordinator.id)
        self.assertEqual(hist.transferred_by, "clinical_supervisor")
        self.assertEqual(hist.reason, "Workload rebalancing")

    def test_04_transfer_case_ownership(self):
        """4. Ownership transfer closes old record and activates new record with audit trail."""
        alt_coordinator = CaseOwner(
            id=uuid.uuid4(),
            name="Kavitha Reddy, MSW",
            role="nurse_navigator",
            email="kavitha.reddy@metrogovhealth.org",
            facility="Metropolitan Breast Center",
            is_active=True
        )
        self.session.add(alt_coordinator)
        self.session.commit()

        res = ToolRegistry.transfer_case_ownership(
            db=self.session,
            case_id=str(self.case.id),
            from_owner_id=str(self.owner.id),
            to_owner_id=str(alt_coordinator.id),
            transferred_by="coordinator_priya",
            reason="Medical leave coverage"
        )
        self.assertTrue(res["success"])

        # Verify old record deactivated
        old_hist = (
            self.session.query(CaseOwnershipHistory)
            .filter(CaseOwnershipHistory.case_id == self.case.id, CaseOwnershipHistory.new_owner_id == self.owner.id)
            .first()
        )
        self.assertFalse(old_hist.is_active)
        self.assertIsNotNone(old_hist.effective_to)

        # Verify new record active
        new_hist = (
            self.session.query(CaseOwnershipHistory)
            .filter(CaseOwnershipHistory.case_id == self.case.id, CaseOwnershipHistory.new_owner_id == alt_coordinator.id)
            .first()
        )
        self.assertTrue(new_hist.is_active)

    def test_05_get_pending_case_tasks(self):
        """5. Retrieves pending milestones and tasks along the journey."""
        res = ToolRegistry.get_pending_case_tasks(self.session, str(self.case.id))
        self.assertTrue(res["success"])
        self.assertGreaterEqual(res["data"]["pending_task_count"], 1)
        tasks = res["data"]["tasks"]
        self.assertIn("Verify Clinic A", tasks[0]["title"])

    def test_06_detect_stalled_case(self):
        """6. Identifies stalled case when inactive for >= threshold days."""
        # Test active case (< 5 days)
        res_active = ToolRegistry.detect_stalled_case(self.session, str(self.case.id), days_threshold=10)
        self.assertFalse(res_active["data"]["stalled"])

        # Test stalled threshold
        res_stalled = ToolRegistry.detect_stalled_case(self.session, str(self.case.id), days_threshold=0)
        self.assertTrue(res_stalled["data"]["stalled"])
        self.assertIn("recommendation", res_stalled["data"])

    def test_07_notify_case_owner(self):
        """7. Alerts the accountable Care Coordinator when intervention is needed."""
        res = ToolRegistry.notify_case_owner(
            db=self.session,
            case_id=str(self.case.id),
            priority="urgent",
            message="Patient flagged transportation barrier. Need assistance booking Clinic A transport."
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["coordinator"], "Priya Nair, RN")

        # Verify alert task created
        alert_task = (
            self.session.query(Task)
            .filter(Task.case_id == self.case.id, Task.task_type == "coordinator_alert")
            .first()
        )
        self.assertIsNotNone(alert_task)
        self.assertEqual(alert_task.assigned_to_id, self.owner.id)

    def test_08_escalate_unowned_case(self):
        """8. Unowned case enters UNASSIGNED_ESCALATED state triggering admin alert."""
        # Create dedicated screening result for the unowned case (unique constraint)
        unowned_screening = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=self.patient.id,
            screening_type="Mammogram",
            test_date=datetime.now(timezone.utc),
            finding_code="BI-RADS-4",
            finding_summary="Suspicious unowned screening finding",
            urgency_level="standard",
            performing_facility="Chennai Diagnostics"
        )
        self.session.add(unowned_screening)
        self.session.flush()

        # Create unowned case
        unowned_case = CareCase(
            id=uuid.uuid4(),
            case_number="CASE-UNOWNED-TEST",
            patient_id=self.patient.id,
            screening_result_id=unowned_screening.id,
            current_owner_id=None, # UNOWNED
            status="result_received",
            clinical_pathway="mammogram_abnormal_bi_rads_4",
            priority="standard",
            sla_start_time=datetime.now(timezone.utc),
            sla_deadline=datetime.now(timezone.utc) + timedelta(days=14),
            sla_status="normal"
        )
        self.session.add(unowned_case)
        self.session.commit()

        # Check owner tool
        owner_res = ToolRegistry.get_case_owner(self.session, str(unowned_case.id))
        self.assertIsNone(owner_res["data"]["owner"])

        # Escalate unowned case
        esc_res = ToolRegistry.escalate_unowned_case(
            db=self.session,
            case_id=str(unowned_case.id),
            reason="Abnormal result with no assigned coordinator"
        )
        self.assertTrue(esc_res["success"])
        self.assertEqual(esc_res["data"]["status"], "UNASSIGNED_ESCALATED")
        self.assertEqual(esc_res["data"]["priority"], "critical")

        # Verify case status in DB
        db_case = self.session.query(CareCase).filter(CareCase.id == unowned_case.id).first()
        self.assertEqual(db_case.status, "UNASSIGNED_ESCALATED")

    def test_09_get_case_closure_requirements(self):
        """9. Evaluates mandatory 5-point checklist before clinical closure."""
        # Active case P-0147 has open tasks and no clinical biopsy sign-off -> NOT ready for closure
        res_open = ToolRegistry.get_case_closure_requirements(self.session, str(self.case.id))
        self.assertFalse(res_open["data"]["is_ready_for_closure"])
        self.assertIn("clinical_verification_signed", res_open["data"]["missing_requirements"])

        # Closed case P-0149 (completed biopsy, Dr. Thorne verified)
        case_p0149 = self.session.query(CareCase).filter(CareCase.case_number == "CASE-2026-0149").first()
        self.assertIsNotNone(case_p0149)

        res_closed = ToolRegistry.get_case_closure_requirements(self.session, str(case_p0149.id))
        self.assertTrue(res_closed["data"]["checklist"]["closure_evidence_recorded"])
        self.assertTrue(res_closed["data"]["checklist"]["clinical_verification_signed"])

    def test_10_langgraph_supervisor_ownership_retrieval(self):
        """10. LangGraph Supervisor retains case owner throughout cognitive execution."""
        graph = create_carebridge_graph(checkpointer=MemorySaver())
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        initial_state = {
            "case_id": str(self.case.id),
            "patient_id": str(self.patient.id),
            "inbound_message": "Can you check who my care coordinator is?",
            "inbound_channel": "sms",
            "inbound_sender": "patient",
            "patient_context": {},
            "case_context": {},
            "conversation_context": {},
            "intent_analysis": None,
            "coordination_plan": None,
            "pending_tool_calls": [],
            "tool_observations": [],
            "replanning_needed": False,
            "requires_human_approval": False,
            "approval_request": None,
            "human_decision": None,
            "outbound_message": None,
            "outbound_language": "en",
            "final_case_status": None,
            "audit_entries": [],
            "iteration_count": 0,
            "max_iterations": 5,
        }

        out = graph.invoke(initial_state, config=config)
        self.assertIsNotNone(out.get("case_context"))
        self.assertEqual(out["case_context"].get("current_owner_name"), "Priya Nair, RN")


if __name__ == "__main__":
    unittest.main()

