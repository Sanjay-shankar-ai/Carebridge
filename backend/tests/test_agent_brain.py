"""
CareBridge Agent Brain Test Suite
Evaluates natural language understanding, barrier inference, dynamic planning,
multilingual adaptation, and safety gatekeeping across diverse patient messages.
"""

import unittest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.session import Base
from app.database.seed import seed_database
from app.models import Patient, CareCase
from app.agents.cognitive_engine import CognitiveEngine
from app.agents.graph import create_carebridge_graph
from langgraph.checkpoint.memory import MemorySaver


class TestAgentBrain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False, future=True)
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionFactory = sessionmaker(bind=cls.engine, autocommit=False, autoflush=False)
        
        # Override the global sync_session_factory for graph node execution during testing
        import app.database.session
        app.database.session.sync_session_factory = cls.SessionFactory

        # Set offline test flag for high-speed deterministic test suite execution
        from app.core.config import settings
        settings.OPENAI_API_KEY = "dummy-offline-test"

    def setUp(self):
        self.session = self.SessionFactory()
        seed_database(self.session)

        # Get test case and patient
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
            "finding_summary": "4.2cm irregular mass requiring biopsy",
            "sla_deadline": self.case.sla_deadline.isoformat(),
            "sla_status": self.case.sla_status,
        }

    def tearDown(self):
        self.session.close()

    def test_transportation_barrier_inference(self):
        """Scenario 1: Natural language barrier detection without exact keywords."""
        msg = "I can't come tomorrow. My daughter is out of town and I have nobody to take me."
        intent = CognitiveEngine.analyze_intent(msg, self.patient_ctx, self.case_ctx)

        self.assertEqual(intent.primary_intent, "appointment_reschedule_with_barrier")
        self.assertTrue(any(b.barrier_type == "transportation_caregiver" for b in intent.detected_barriers))
        self.assertEqual(intent.emotional_state, "anxious")

        # Test plan generation
        plan = CognitiveEngine.formulate_plan(intent, self.patient_ctx, self.case_ctx, {})
        self.assertTrue(len(plan.actions) >= 2)
        tool_names = [a.tool_name for a in plan.actions]
        self.assertIn("update_case_notes", tool_names)
        self.assertIn("search_available_appointments", tool_names)
        self.assertIn("daughter", plan.patient_response_draft.lower())

    def test_tamil_multilingual_comprehension(self):
        """Scenario 2: Tamil natural language message with anxiety."""
        msg = "வணக்கம், எனக்கு ரிசல்ட் பற்றி ரொம்ப பயமாக இருக்கிறது. அடுத்து என்ன செய்வது?"
        intent = CognitiveEngine.analyze_intent(msg, self.patient_ctx, self.case_ctx)

        self.assertEqual(intent.detected_language, "ta")
        self.assertTrue(any(b.barrier_type == "fear_anxiety" for b in intent.detected_barriers))

        plan = CognitiveEngine.formulate_plan(intent, self.patient_ctx, self.case_ctx, {})
        self.assertEqual(plan.target_language, "ta")
        # Response should contain respectful Tamil guidance
        self.assertTrue(any("\u0b80" <= char <= "\u0bff" for char in plan.patient_response_draft))

    def test_acute_clinical_urgency_escalation(self):
        """Scenario 3: Severe symptoms trigger clinical escalation."""
        msg = "I have severe emergency chest pain and dizziness since morning."
        intent = CognitiveEngine.analyze_intent(msg, self.patient_ctx, self.case_ctx)

        self.assertEqual(intent.primary_intent, "urgent_clinical_escalation")
        self.assertTrue(intent.requires_human_escalation)

        plan = CognitiveEngine.formulate_plan(intent, self.patient_ctx, self.case_ctx, {})
        tool_names = [a.tool_name for a in plan.actions]
        self.assertIn("escalate_case", tool_names)

    def test_routine_acknowledgement(self):
        """Scenario 4: Simple patient acknowledgement."""
        msg = "Yes I received the message, thank you so much."
        intent = CognitiveEngine.analyze_intent(msg, self.patient_ctx, self.case_ctx)

        self.assertEqual(intent.primary_intent, "acknowledgement")
        self.assertEqual(len(intent.detected_barriers), 0)

        plan = CognitiveEngine.formulate_plan(intent, self.patient_ctx, self.case_ctx, {})
        self.assertIn("Thank you", plan.patient_response_draft)

    def test_appointment_cancellation_with_reason_and_outcome(self):
        """Scenario 5: Explicit appointment cancellation with documented reason and outcome."""
        msg = "Please cancel my appointment, I don't want to come."
        intent = CognitiveEngine.analyze_intent(msg, self.patient_ctx, self.case_ctx)

        self.assertEqual(intent.primary_intent, "appointment_cancellation_and_refusal")
        self.assertTrue(intent.requires_human_escalation)

        plan = CognitiveEngine.formulate_plan(intent, self.patient_ctx, self.case_ctx, {})
        tool_names = [a.tool_name for a in plan.actions]
        self.assertIn("cancel_appointment", tool_names)
        self.assertIn("escalate_case", tool_names)

        # Test direct ToolRegistry execution of cancel_appointment
        from app.models import Appointment
        active_appt = self.session.query(Appointment).filter(Appointment.case_id == self.case.id).first()
        self.assertIsNotNone(active_appt)

        from app.tools.registry import ToolRegistry
        res = ToolRegistry.cancel_appointment(
            db=self.session,
            appointment_id=str(active_appt.id),
            case_id=str(self.case.id),
            reason="patient_declined_care",
            outcome="care_declined",
            detailed_notes="Patient requested cancellation of consultation."
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["status"], "cancelled")
        self.assertEqual(res["data"]["cancellation_reason"], "patient_declined_care")
        self.assertEqual(res["data"]["cancellation_outcome"], "care_declined")

        # Verify database record updated
        updated_appt = self.session.query(Appointment).filter(Appointment.id == active_appt.id).first()
        self.assertEqual(updated_appt.status, "cancelled")
        self.assertEqual(updated_appt.cancellation_reason, "patient_declined_care")
        self.assertEqual(updated_appt.cancellation_outcome, "care_declined")

    def test_langgraph_end_to_end_execution(self):
        """Scenario 5: Complete LangGraph workflow execution with state persistence."""
        graph = create_carebridge_graph(checkpointer=MemorySaver())

        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        initial_state = {
            "case_id": str(self.case.id),
            "patient_id": str(self.patient.id),
            "inbound_message": "I can't come tomorrow. My daughter is out of town and I have nobody to take me.",
            "inbound_channel": "whatsapp",
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
            "outbound_language": "ta",
            "final_case_status": None,
            "audit_entries": [],
        }

        # Invoke the LangGraph workflow
        final_state = graph.invoke(initial_state, config=config)

        self.assertIsNotNone(final_state.get("intent_analysis"))
        self.assertIsNotNone(final_state.get("coordination_plan"))
        self.assertGreater(len(final_state.get("tool_observations", [])), 0)
        self.assertIsNotNone(final_state.get("outbound_message"))

        # Verify state persistence in checkpointer
        checkpoint_state = graph.get_state(config)
        self.assertIsNotNone(checkpoint_state)
        self.assertEqual(checkpoint_state.values.get("case_id"), str(self.case.id))


if __name__ == "__main__":
    unittest.main()
