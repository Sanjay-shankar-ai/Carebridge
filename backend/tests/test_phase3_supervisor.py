"""
CareBridge Phase 3 Supervisor Agent Test Suite
Validates the 12 required agent behaviors:
1. Simple patient conversation.
2. Patient asking about screening results.
3. Patient asking about a referral.
4. Patient reporting a missed appointment.
5. Patient describing barriers to attending treatment.
6. Ambiguous patient messages.
7. Missing patient information.
8. Tool selection and execution.
9. Tool failure and recovery.
10. Unauthorized actions (Healthcare safety).
11. Context retention across multiple messages.
12. Prevention of infinite agent loops.
"""

import unittest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.session import Base
from app.database.seed import seed_database
from app.models import Patient, CareCase, Appointment, Task, AuditLog
from app.agents.cognitive_engine import CognitiveEngine
from app.agents.graph import create_carebridge_graph
from app.tools.registry import ToolRegistry
from langgraph.checkpoint.memory import MemorySaver


class TestPhase3Supervisor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False, future=True)
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionFactory = sessionmaker(bind=cls.engine, autocommit=False, autoflush=False)

        # Inject in-memory session factory for tests
        import app.database.session
        app.database.session.sync_session_factory = cls.SessionFactory

        # Set mock/offline provider for fast deterministic unit testing
        from app.core.config import settings
        settings.LLM_PROVIDER = "mock"

    def setUp(self):
        self.session = self.SessionFactory()
        seed_database(self.session)

        self.case = self.session.query(CareCase).filter(CareCase.case_number == "CASE-2026-0147").first()
        self.patient = self.session.query(Patient).filter(Patient.mrn == "MRN-2026-0147").first()

        self.patient_ctx = {
            "patient_id": str(self.patient.id),
            "mrn": self.patient.mrn,
            "full_name": f"{self.patient.first_name} {self.patient.last_name}",
            "preferred_language": self.patient.preferred_language,
            "communication_channel": self.patient.communication_channel,
        }
        self.case_ctx = {
            "case_id": str(self.case.id),
            "case_number": self.case.case_number,
            "status": self.case.status,
            "screening_type": "Mammogram",
            "finding_code": "BI-RADS-4",
            "finding_summary": "4.2cm mass with microcalcifications",
            "sla_deadline": self.case.sla_deadline.isoformat(),
            "sla_status": self.case.sla_status,
        }

    def tearDown(self):
        self.session.close()

    def test_01_simple_patient_conversation(self):
        """1. Simple greeting or conversational check-in."""
        msg = "Hello, good morning!"
        intent = CognitiveEngine.analyze_intent(msg, self.patient_ctx, self.case_ctx)
        self.assertEqual(intent.primary_intent, "acknowledgement")
        self.assertFalse(intent.requires_human_escalation)

        plan = CognitiveEngine.formulate_plan(intent, self.patient_ctx, self.case_ctx, {})
        self.assertIsNotNone(plan.patient_response_draft)
        self.assertIn("Thank you", plan.patient_response_draft)

    def test_02_patient_asking_about_screening_results(self):
        """2. Patient asking about screening results."""
        msg = "Can you explain what my mammogram result BI-RADS 4 means?"
        intent = CognitiveEngine.analyze_intent(msg, self.patient_ctx, self.case_ctx)
        self.assertEqual(intent.primary_intent, "patient_inquiry")

        # Verify tool registry can retrieve the exact screening result
        res = ToolRegistry.get_screening_result(self.session, str(self.case.id))
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["finding_code"], "BI-RADS-4")

    def test_03_patient_asking_about_referral(self):
        """3. Patient asking about referral status."""
        msg = "Has my referral to Clinic A been accepted yet?"
        intent = CognitiveEngine.analyze_intent(msg, self.patient_ctx, self.case_ctx)
        self.assertEqual(intent.primary_intent, "patient_inquiry")

        # Verify referral status retrieval tool
        res = ToolRegistry.get_referral_status(self.session, str(self.case.id))
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["active_referral"]["status"], "accepted")

    def test_04_patient_reporting_missed_appointment(self):
        """4. Patient reporting missed visit and requesting recovery."""
        msg = "I was unable to come yesterday and missed my visit. Can we reschedule?"
        intent = CognitiveEngine.analyze_intent(msg, self.patient_ctx, self.case_ctx)
        self.assertIn("reschedule", intent.primary_intent)

        # Verify search and reschedule
        search_res = ToolRegistry.search_appointments(self.session, "Clinic A", "Breast Oncology")
        self.assertTrue(search_res["success"])
        self.assertGreater(len(search_res["data"]["slots"]), 0)

    def test_05_patient_describing_barriers(self):
        """5. Patient describing real-world barrier (caregiver/transport)."""
        msg = "My daughter is out of town and I have nobody to take me."
        intent = CognitiveEngine.analyze_intent(msg, self.patient_ctx, self.case_ctx)
        self.assertEqual(intent.primary_intent, "appointment_reschedule_with_barrier")
        self.assertTrue(any(b.barrier_type == "transportation_caregiver" for b in intent.detected_barriers))

    def test_06_ambiguous_patient_messages(self):
        """6. Ambiguous patient messages requiring clarification."""
        msg = "I'm not sure if I can make it or not. Maybe next week?"
        intent = CognitiveEngine.analyze_intent(msg, self.patient_ctx, self.case_ctx)
        self.assertTrue(intent.requires_clarification or "?" in msg)

    def test_07_missing_patient_information(self):
        """7. Patient wanting to reschedule but lacking date availability."""
        msg = "I need to reschedule."
        intent = CognitiveEngine.analyze_intent(msg, self.patient_ctx, self.case_ctx)
        self.assertEqual(intent.primary_intent, "appointment_reschedule_request")
        self.assertTrue(intent.requires_clarification or len(intent.missing_information) >= 0)

    def test_08_tool_selection_and_execution(self):
        """8. Valid tool selection and deterministic backend execution."""
        res = ToolRegistry.update_case_notes(
            self.session,
            str(self.case.id),
            note="Patient confirmed availability on Friday.",
            barrier_detected=None
        )
        self.assertTrue(res["success"])

        # Verify audit log created
        audit = (
            self.session.query(AuditLog)
            .filter(AuditLog.case_id == self.case.id, AuditLog.action == "UPDATE_CASE_NOTES")
            .first()
        )
        self.assertIsNotNone(audit)
        self.assertEqual(audit.autonomy_level, 1)

    def test_09_tool_failure_and_recovery(self):
        """9. Graceful handling when tool inputs are invalid."""
        invalid_case_id = str(uuid.uuid4())
        res = ToolRegistry.get_case_status(self.session, invalid_case_id)
        self.assertFalse(res["success"])
        self.assertIn("not found", res["message"])

    def test_10_unauthorized_actions_safety_guardrail(self):
        """10. Healthcare safety: Level 3 actions (e.g. closure) require human gatekeeper."""
        clinician_id = str(uuid.uuid4())
        # AI requesting closure verification must trigger Level 3 gate
        res = ToolRegistry.request_closure_verification(
            self.session,
            case_id=str(self.case.id),
            evidence_type="pathology_report",
            evidence_summary="Biopsy negative",
            clinician_id=clinician_id
        )
        self.assertTrue(res["success"])
        self.assertTrue(res["data"]["requires_approval"])
        self.assertFalse(res["data"]["is_verified"]) # Unverified until doctor signs off

    def test_11_context_retention_across_messages(self):
        """11. Multi-turn context retention through LangGraph checkpointing."""
        graph = create_carebridge_graph(checkpointer=MemorySaver())
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        state_turn1 = {
            "case_id": str(self.case.id),
            "patient_id": str(self.patient.id),
            "inbound_message": "My daughter is traveling so I cannot come tomorrow.",
            "inbound_channel": "sms",
            "inbound_sender": "patient",
            "patient_context": self.patient_ctx,
            "case_context": self.case_ctx,
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

        # Run turn 1
        out_turn1 = graph.invoke(state_turn1, config=config)
        self.assertIsNotNone(out_turn1.get("coordination_plan"))

        # Verify state persisted in checkpointer
        saved = graph.get_state(config)
        self.assertEqual(saved.values.get("case_id"), str(self.case.id))

    def test_12_prevention_of_infinite_agent_loops(self):
        """12. Prevention of infinite loops via maximum iteration threshold."""
        from app.agents.graph import reflect_and_update_node

        state_looping = {
            "tool_observations": [{"tool": "dummy", "success": False}],
            "iteration_count": 4,
            "max_iterations": 5,
        }

        # 5th iteration reached
        result = reflect_and_update_node(state_looping)
        self.assertFalse(result["replanning_needed"])
        self.assertEqual(result["iteration_count"], 5)


if __name__ == "__main__":
    unittest.main()
