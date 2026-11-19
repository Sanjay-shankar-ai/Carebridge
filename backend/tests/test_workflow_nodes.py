"""
CareBridge AI Workflow - Individual Node Unit Tests
Verifies each of the 11 workflow nodes in complete isolation before graph assembly:
1. create_case (with idempotency)
2. select_approved_pathway (deterministic matching)
3. draft_patient_communication (empathetic multilingual formulation & idempotency)
4. record_acknowledgement (outreach task completion)
5. coordinate_referral (inter-facility routing & idempotency)
6. coordinate_appointment (clinic scheduling & idempotency)
7. monitor_case (SLA evaluation & inactivity)
8. detect_dropoff (rule-based dropoff detection)
9. recovery_agent (tailored recovery playbook & attempt tracking)
10. escalation (critical priority & unowned case escalation)
11. verify_closure (clinical safety: AI cannot independently approve without human signoff)
"""

import unittest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
import app.database.session as session_module
from app.database.seed import seed_database
from app.models import (
    Patient, CareCase, CaseOwner, ScreeningResult, Appointment,
    Task, Referral, Communication, ClosureEvidence
)
from app.core.config import settings
from app.workflows.nodes import (
    create_case_node, select_approved_pathway_node, draft_patient_communication_node,
    record_acknowledgement_node, coordinate_referral_node, coordinate_appointment_node,
    monitor_case_node, detect_dropoff_node, recovery_agent_node,
    escalation_node, verify_closure_node
)
from app.workflows.state import CareBridgeState


class TestWorkflowNodes(unittest.TestCase):
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
        self.owner = self.session.query(CaseOwner).first()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)

    # --------------------------------------------------------------------------
    # Node 1: create_case
    # --------------------------------------------------------------------------
    def test_01_create_case_new_and_idempotent(self):
        # Create a new screening result
        new_screening = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=self.patient.id,
            screening_type="Mammogram",
            test_date=datetime.now(timezone.utc),
            finding_code="BI-RADS-4",
            finding_summary="Suspicious microcalcifications right breast",
            urgency_level="urgent",
            performing_facility="Chennai Breast Center"
        )
        self.session.add(new_screening)
        self.session.commit()

        initial_state: CareBridgeState = {
            "case_id": None,
            "patient_id": str(self.patient.id),
            "screening_result_id": str(new_screening.id),
            "current_owner_id": None,
            "status": "pending",
            "clinical_pathway": None,
            "priority": "urgent",
            "sla_start_time": None,
            "sla_deadline": None,
            "sla_status": "normal",
            "patient_language": "en",
            "latest_patient_message": None,
            "drafted_communication": None,
            "patient_acknowledged": False,
            "acknowledgement_channel": None,
            "acknowledgement_timestamp": None,
            "referral_id": None,
            "referral_status": None,
            "target_facility": None,
            "appointment_id": None,
            "appointment_status": None,
            "scheduled_appointment_time": None,
            "appointment_attended": False,
            "is_stalled": False,
            "days_inactive": 0.0,
            "dropoff_risk": False,
            "dropoff_reasons": [],
            "recovery_attempts": 0,
            "recovery_strategy": None,
            "escalation_level": None,
            "escalation_reason": None,
            "requires_human_approval": False,
            "approval_type": None,
            "human_decision": None,
            "closure_checklist": None,
            "closure_verified": False,
            "workflow_phase": "init",
            "next_step": None,
            "audit_log": [],
            "errors": []
        }

        # First run: should create new case
        out1 = create_case_node(initial_state)
        self.assertIsNotNone(out1.get("case_id"))
        self.assertEqual(out1.get("workflow_phase"), "case_created")
        created_case_id = out1["case_id"]

        # Verify DB has created outreach task
        tasks = self.session.query(Task).filter(Task.case_id == uuid.UUID(created_case_id)).all()
        self.assertTrue(len(tasks) >= 1)

        # Second run (idempotency): should not duplicate
        initial_state["case_id"] = created_case_id
        out2 = create_case_node(initial_state)
        self.assertEqual(out2.get("case_id"), created_case_id)
        self.assertEqual(out2.get("workflow_phase"), "case_created")

    # --------------------------------------------------------------------------
    # Node 2: select_approved_pathway
    # --------------------------------------------------------------------------
    def test_02_select_approved_pathway(self):
        state: CareBridgeState = {
            "case_id": str(self.case.id),
            "patient_id": str(self.patient.id),
            "screening_result_id": str(self.screening.id),
            "current_owner_id": str(self.case.current_owner_id),
            "status": "result_received",
            "clinical_pathway": "general_screening_followup", # default placeholder
            "priority": "standard",
            "sla_start_time": None,
            "sla_deadline": None,
            "sla_status": "normal",
            "patient_language": "en",
            "latest_patient_message": None,
            "drafted_communication": None,
            "patient_acknowledged": False,
            "acknowledgement_channel": None,
            "acknowledgement_timestamp": None,
            "referral_id": None,
            "referral_status": None,
            "target_facility": None,
            "appointment_id": None,
            "appointment_status": None,
            "scheduled_appointment_time": None,
            "appointment_attended": False,
            "is_stalled": False,
            "days_inactive": 0.0,
            "dropoff_risk": False,
            "dropoff_reasons": [],
            "recovery_attempts": 0,
            "recovery_strategy": None,
            "escalation_level": None,
            "escalation_reason": None,
            "requires_human_approval": False,
            "approval_type": None,
            "human_decision": None,
            "closure_checklist": None,
            "closure_verified": False,
            "workflow_phase": "case_created",
            "next_step": None,
            "audit_log": [],
            "errors": []
        }

        # Clear case pathway to force matching
        self.case.clinical_pathway = "general_screening_followup"
        self.session.commit()

        out = select_approved_pathway_node(state)
        self.assertEqual(out.get("workflow_phase"), "pathway_selected")
        self.assertIn("mammogram", out.get("clinical_pathway"))

    # --------------------------------------------------------------------------
    # Node 3: draft_patient_communication
    # --------------------------------------------------------------------------
    def test_03_draft_patient_communication_idempotent(self):
        state = {"case_id": str(self.case.id)}
        out1 = draft_patient_communication_node(state)
        self.assertEqual(out1.get("workflow_phase"), "communication_sent")
        self.assertIsNotNone(out1.get("drafted_communication"))

        # Verify DB stored the communication
        comms = self.session.query(Communication).filter(Communication.case_id == self.case.id).all()
        initial_comm_count = len(comms)
        self.assertTrue(initial_comm_count >= 1)

        # Idempotency test: calling again does not create a duplicate communication
        out2 = draft_patient_communication_node(state)
        comms_after = self.session.query(Communication).filter(Communication.case_id == self.case.id).all()
        self.assertEqual(len(comms_after), initial_comm_count)

    # --------------------------------------------------------------------------
    # Node 4: record_acknowledgement
    # --------------------------------------------------------------------------
    def test_04_record_acknowledgement(self):
        state = {
            "case_id": str(self.case.id),
            "patient_acknowledged": True,
            "latest_patient_message": "Yes, I got your message. I am ready to schedule."
        }
        out = record_acknowledgement_node(state)
        self.assertTrue(out.get("patient_acknowledged"))
        self.assertEqual(out.get("workflow_phase"), "acknowledged")

        # Verify open outreach tasks are marked completed
        open_outreach = (
            self.session.query(Task)
            .filter(Task.case_id == self.case.id, Task.task_type == "patient_outreach", Task.status == "pending")
            .count()
        )
        self.assertEqual(open_outreach, 0)

    # --------------------------------------------------------------------------
    # Node 5: coordinate_referral
    # --------------------------------------------------------------------------
    def test_05_coordinate_referral_idempotent(self):
        state = {"case_id": str(self.case.id)}
        out1 = coordinate_referral_node(state)
        self.assertEqual(out1.get("workflow_phase"), "referral_coordinated")
        ref_id = out1.get("referral_id")
        self.assertIsNotNone(ref_id)

        # Idempotency check: re-running returns the same referral
        out2 = coordinate_referral_node(state)
        self.assertEqual(out2.get("referral_id"), ref_id)

    # --------------------------------------------------------------------------
    # Node 6: coordinate_appointment
    # --------------------------------------------------------------------------
    def test_06_coordinate_appointment_idempotent(self):
        state = {"case_id": str(self.case.id)}
        out1 = coordinate_appointment_node(state)
        self.assertEqual(out1.get("workflow_phase"), "appointment_coordinated")
        app_id = out1.get("appointment_id")
        self.assertIsNotNone(app_id)

        # Idempotency check
        out2 = coordinate_appointment_node(state)
        self.assertEqual(out2.get("appointment_id"), app_id)

    # --------------------------------------------------------------------------
    # Node 7: monitor_case
    # --------------------------------------------------------------------------
    def test_07_monitor_case(self):
        state = {"case_id": str(self.case.id)}
        out = monitor_case_node(state)
        self.assertEqual(out.get("workflow_phase"), "monitored")
        self.assertIn(out.get("sla_status"), ["normal", "warning", "breached"])
        self.assertIn("is_stalled", out)

    # --------------------------------------------------------------------------
    # Node 8: detect_dropoff
    # --------------------------------------------------------------------------
    def test_08_detect_dropoff(self):
        # Case with recorded barrier in context
        self.case.case_context = {
            "inferred_barriers": [{"barrier_type": "transportation", "severity": "high"}],
            "patient_understanding_confirmed": False
        }
        self.session.commit()

        state = {
            "case_id": str(self.case.id),
            "patient_acknowledged": False,
            "days_inactive": 6.0
        }
        out = detect_dropoff_node(state)
        self.assertEqual(out.get("workflow_phase"), "dropoff_evaluated")
        self.assertTrue(out.get("dropoff_risk"))
        self.assertTrue(len(out.get("dropoff_reasons")) > 0)

    # --------------------------------------------------------------------------
    # Node 9: recovery_agent
    # --------------------------------------------------------------------------
    def test_09_recovery_agent(self):
        # Reset recovery_attempts in case_context for clean unit test
        ctx = dict(self.case.case_context or {})
        ctx["recovery_attempts"] = 0
        self.case.case_context = ctx
        self.session.commit()

        state = {
            "case_id": str(self.case.id),
            "dropoff_reasons": ["patient_barrier_transportation", "case_inactive_6_days"]
        }
        out = recovery_agent_node(state)
        self.assertEqual(out.get("workflow_phase"), "recovery_initiated")
        self.assertEqual(out.get("recovery_attempts"), 1)
        self.assertEqual(out.get("recovery_strategy"), "transportation_assistance_navigation")

    # --------------------------------------------------------------------------
    # Node 10: escalation
    # --------------------------------------------------------------------------
    def test_10_escalation(self):
        state = {
            "case_id": str(self.case.id),
            "dropoff_reasons": ["sla_breached", "patient_unresponsive_after_3_attempts"]
        }
        out = escalation_node(state)
        self.assertEqual(out.get("workflow_phase"), "escalated")
        self.assertEqual(out.get("priority"), "critical")
        self.assertEqual(out.get("status"), "ESCALATED")

        # Verify case in DB is set to critical
        self.session.expire_all()
        db_case = self.session.query(CareCase).filter(CareCase.id == self.case.id).first()
        self.assertEqual(db_case.priority, "critical")

    # --------------------------------------------------------------------------
    # Node 11: verify_closure (Human Clinical Gatekeeping)
    # --------------------------------------------------------------------------
    def test_11_verify_closure_clinical_safety_gate(self):
        state = {"case_id": str(self.case.id)}

        # 1. Without clinician verified sign-off, AI CANNOT close case
        out_unverified = verify_closure_node(state)
        self.assertFalse(out_unverified.get("closure_verified"))
        self.assertTrue(out_unverified.get("requires_human_approval"))
        self.assertEqual(out_unverified.get("workflow_phase"), "closure_pending_human_signoff")

        # 2. When human clinician decision is approved, case closes safely
        state_approved = {
            "case_id": str(self.case.id),
            "human_decision": "approved"
        }
        out_approved = verify_closure_node(state_approved)
        self.assertTrue(out_approved.get("closure_verified"))
        self.assertEqual(out_approved.get("status"), "closed")
        self.assertEqual(out_approved.get("workflow_phase"), "closed")


if __name__ == "__main__":
    unittest.main()
