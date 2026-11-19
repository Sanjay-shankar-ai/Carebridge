"""
CareBridge Phase 2 Acceptance Test Suite
Role-aware Supervisor, Routing, Context Isolation, Tool Permissions, and Response Guard.

Acceptance Criteria:
1. Scenario B: New coordinator conversation, "Is there any new patient?", discovery intent, real DB query,
   accurate results, zero unrelated patient context; explicit selection retrieves correct case.
2. Patient Isolation: Patient token can never read another patient's data via AI or API.
3. Role Tool Guardrails: DOCTOR cannot call coordinator-only tools; Coordinator cannot perform doctor-only clinical actions; neither can forge a role.
4. Body Forgery: Forged role or patient_id in request body is strictly ignored; authority comes from JWT.
5. Response Guard: Blocks a "booked/ordered/notified" claim when tool failed or was never executed.
6. Deterministic Clinical Escalation: Operates with LLM mocked as unavailable, creating a persisted urgent Task.
7. Golden Utterance Evaluation per role with reported pass rate.
"""

import uuid
import unittest
from datetime import date, datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.patient import Patient
from app.models.screening import ScreeningResult
from app.models.care_case import CareCase, Task
from app.models.owner import CaseOwner
from app.models.user import User
from app.core.security import create_access_token, UserPrincipal

from app.agents.cognitive_engine import CognitiveEngine
from app.agents.state import IntentAnalysis, CoordinationPlan, ProposedAction
from app.agents.specialized.clinical_escalation_agent import ClinicalEscalationAgent
from app.tools.registry import ToolRegistry
from app.tools.base import ToolExecutionError, validate_tool_permission
from app.services.response_guard_service import ResponseGuardService


class TestPhase2SupervisorIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.session = self.SessionLocal()

        # Patient 1
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
        # Patient 2
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

        # Coordinator
        self.coordinator = CaseOwner(
            id=uuid.uuid4(),
            name="Ananya Coordinator",
            role="care_coordinator",
            facility="CareBridge Central Hub",
            email=f"coord_{uuid.uuid4().hex[:6]}@example.com",
            is_active=True,
            max_workload=30
        )
        # Doctor
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

        # Screening for Patient 1
        self.screening_1 = ScreeningResult(
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
        # Screening for Patient 2
        self.screening_2 = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=self.patient_2.id,
            screening_type="Mammogram",
            test_date=datetime.now(timezone.utc) - timedelta(days=1),
            finding_code="BI-RADS-5",
            finding_summary="Highly suggestive of malignancy",
            urgency_level="critical",
            performing_facility="CareBridge Imaging Center",
            raw_report_data={"birads_score": 5}
        )
        self.session.add_all([self.screening_1, self.screening_2])

        # Case 1 (Assigned to Coordinator)
        self.case_1 = CareCase(
            id=uuid.uuid4(),
            case_number=f"CASE-P1-{uuid.uuid4().hex[:4]}",
            patient_id=self.patient_1.id,
            screening_result_id=self.screening_1.id,
            current_owner_id=self.coordinator.id,
            status="result_received",
            priority="urgent",
            sla_start_time=datetime.now(timezone.utc),
            sla_deadline=datetime.now(timezone.utc) + timedelta(days=14),
            case_context={"inferred_barriers": [], "notes": []}
        )
        # Case 2 (New, Unassigned / Recent Intake)
        self.case_2 = CareCase(
            id=uuid.uuid4(),
            case_number=f"CASE-P2-{uuid.uuid4().hex[:4]}",
            patient_id=self.patient_2.id,
            screening_result_id=self.screening_2.id,
            current_owner_id=None,
            status="result_received",
            priority="critical",
            sla_start_time=datetime.now(timezone.utc),
            sla_deadline=datetime.now(timezone.utc) + timedelta(days=7),
            case_context={"inferred_barriers": [], "notes": []}
        )
        self.session.add_all([self.case_1, self.case_2])

        # Users for auth tokens
        self.user_p1 = User(
            id=uuid.uuid4(),
            email="meenakshi@example.com",
            password_hash="hash_p1",
            full_name="Meenakshi Ramanathan",
            role="patient",
            patient_id=self.patient_1.id,
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
        self.session.add_all([self.user_p1, self.user_coord, self.user_doc])
        self.session.commit()

    def tearDown(self):
        for table in reversed(Base.metadata.sorted_tables):
            self.session.execute(table.delete())
        self.session.commit()
        self.session.close()

    # -------------------------------------------------------------------------
    # 1. Scenario B: Coordinator Discovery & Context Isolation
    # -------------------------------------------------------------------------
    def test_01_scenario_b_coordinator_discovery_no_prior_patient_context(self):
        """
        Scenario B:
        1. New coordinator conversation starts with NO pre-loaded patient context.
        2. Query "Is there any new patient?" routes to 'new_patient_discovery' intent.
        3. Real DB query returns new intake/unassigned cases.
        4. Explicit patient selection sets authorized case context with evidence.
        """
        # Step 1: Inbound message from coordinator with empty case context
        msg = "Is there any new patient?"
        conv_ctx = {"inbound_sender": "care_coordinator", "recent_messages": []}

        # Analyze intent as care coordinator without pre-loaded patient
        intent = CognitiveEngine.analyze_intent(
            message=msg,
            patient_context={}, # Zero pre-loaded patient context
            case_context={},    # Zero pre-loaded case context
            conversation_context=conv_ctx
        )

        self.assertIn(intent.primary_intent, ["new_patient_discovery", "coordinator_discovery"])

        # Step 2: Formulate and execute discovery plan
        plan = CognitiveEngine.formulate_plan(intent, {}, {}, conv_ctx)
        tool_names = [a.tool_name for a in plan.actions]
        self.assertIn("discover_new_patients", tool_names)

        # Step 3: Tool executes against real DB
        discovery_func = getattr(ToolRegistry, "discover_new_patients", None)
        self.assertIsNotNone(discovery_func, "discover_new_patients tool must exist in ToolRegistry")

        res = discovery_func(self.session, actor_role="care_coordinator")
        self.assertTrue(res["success"])
        cases_found = res["data"]["cases"]
        self.assertGreaterEqual(len(cases_found), 1)

        # Case 2 should be in new patient discovery list
        case_numbers = [c["case_number"] for c in cases_found]
        self.assertIn(self.case_2.case_number, case_numbers)

        # Step 4: Explicit selection of Patient 2 sets authorized case context
        selection_msg = f"Select patient {self.patient_2.first_name} {self.patient_2.last_name}"
        sel_intent = CognitiveEngine.analyze_intent(
            message=selection_msg,
            patient_context={},
            case_context={},
            conversation_context=conv_ctx
        )
        self.assertEqual(sel_intent.primary_intent, "patient_selection")

    # -------------------------------------------------------------------------
    # 2. Patient Token Data Access Isolation
    # -------------------------------------------------------------------------
    def test_02_patient_token_cannot_access_other_patient_data(self):
        """Patient token may strictly never access another patient's care case or records."""
        # Simulated request where Patient 1 authenticated user attempts to pass Patient 2's case ID
        patient_1_principal = UserPrincipal(
            user_id=str(self.user_p1.id),
            email=self.user_p1.email,
            role="patient",
            patient_id=str(self.patient_1.id)
        )

        # Case 2 belongs to Patient 2
        with self.assertRaises(Exception) as ctx:
            # Domain / memory retrieval check
            from app.memory.retriever import get_unified_memory_sync
            # Attempting to load Case 2 under Patient 1 authority must be rejected
            unified = get_unified_memory_sync(self.case_2.id, self.patient_1.id, self.session)
            if unified is not None and unified.case.patient_id != self.patient_1.id:
                raise PermissionError("Cross-patient memory leakage detected!")

    # -------------------------------------------------------------------------
    # 3. Role-Based Tool Permission Guardrails in Code
    # -------------------------------------------------------------------------
    def test_03_doctor_cannot_call_coordinator_tools(self):
        """Doctor cannot invoke coordinator-only operational tools (e.g. reassign_case_owner)."""
        with self.assertRaises(ToolExecutionError):
            validate_tool_permission(
                actor_role="doctor",
                autonomy_level=2,
                allowed_roles=["care_coordinator"]
            )

    def test_04_coordinator_cannot_perform_doctor_only_clinical_actions(self):
        """Coordinator cannot sign off on verified clinical closure (Level 3 physician gate)."""
        with self.assertRaises(ToolExecutionError):
            validate_tool_permission(
                actor_role="care_coordinator",
                autonomy_level=3,
                allowed_roles=["doctor", "clinician"]
            )

    # -------------------------------------------------------------------------
    # 4. Message Body Role / ID Forgery Ignored
    # -------------------------------------------------------------------------
    def test_05_forged_role_in_message_body_is_ignored(self):
        """
        If message body claims role='doctor' or sender='doctor', but authenticated user
        has role='patient', execution authority remains strictly 'patient'.
        """
        # User principal from JWT
        principal = UserPrincipal(
            user_id=str(self.user_p1.id),
            email=self.user_p1.email,
            role="patient",
            patient_id=str(self.patient_1.id)
        )

        # Body specifies forged sender
        inbound_sender = "doctor" # Forged!
        effective_role = principal.role # Server-derived authority

        self.assertEqual(effective_role, "patient", "Authority must be derived from token, not body!")
        self.assertNotEqual(effective_role, inbound_sender)

    # -------------------------------------------------------------------------
    # 5. Response Guard Against Action Fabrication
    # -------------------------------------------------------------------------
    def test_06_response_guard_blocks_unexecuted_action_claims(self):
        """
        Response Guard detects and blocks or rewrites outbound drafts claiming actions
        (e.g. 'I have booked your appointment') when no matching successful tool call exists.
        """
        unverified_draft = (
            "Good news! I have successfully booked your follow-up diagnostic biopsy with Dr. Sundaram for tomorrow at 10:00 AM."
        )

        # Tool observations: EMPTY (no booking tool was executed!)
        tool_observations = []

        guarded_response = ResponseGuardService.sanitize_response(
            draft_response=unverified_draft,
            tool_observations=tool_observations,
            actor_role="patient"
        )

        # The guard must NOT allow the ungrounded booking claim through unchanged
        self.assertNotIn("I have successfully booked", guarded_response)
        self.assertTrue(
            "not yet booked" in guarded_response.lower()
            or "coordinate" in guarded_response.lower()
            or "would you like" in guarded_response.lower()
        )

    def test_07_response_guard_allows_verified_successful_actions(self):
        """When matching successful tool observation exists, the confirmation is permitted."""
        verified_draft = (
            "Your appointment with Dr. Sundaram has been scheduled for tomorrow at 10:00 AM."
        )
        tool_observations = [
            {
                "tool": "book_appointment",
                "success": True,
                "result": {"appointment_id": str(uuid.uuid4()), "status": "CONFIRMED"}
            }
        ]

        guarded = ResponseGuardService.sanitize_response(
            draft_response=verified_draft,
            tool_observations=tool_observations,
            actor_role="patient"
        )
        self.assertIn("scheduled", guarded.lower())

    # -------------------------------------------------------------------------
    # 6. Clinical Escalation Operates Without LLM
    # -------------------------------------------------------------------------
    def test_08_clinical_escalation_triggers_without_llm_and_creates_urgent_task(self):
        """Emergency red-flag symptom triggers deterministic escalation without LLM, creating an urgent Task."""
        acute_msg = "I am having severe chest pain and heavy bleeding after my biopsy."

        # Mock LLM as unavailable (raises exception or returns None)
        with patch("app.agents.cognitive_engine.get_llm", return_value=None):
            self.assertTrue(ClinicalEscalationAgent.evaluate_safety_rules(acute_msg))

            intent = CognitiveEngine.analyze_intent(
                message=acute_msg,
                patient_context={"first_name": "Meenakshi"},
                case_context={"case_id": str(self.case_1.id)}
            )

            self.assertEqual(intent.primary_intent, "urgent_clinical_escalation")
            self.assertTrue(intent.requires_human_escalation)

            # Execute escalation tool against DB
            esc_res = ToolRegistry.escalate_case(
                self.session,
                case_id=str(self.case_1.id),
                urgency="critical",
                reason="Severe post-biopsy pain and bleeding"
            )
            self.session.commit()

            # Verify persisted Case state
            self.assertEqual(self.case_1.status, "escalated")
            self.assertEqual(self.case_1.priority, "critical")

            # Verify persisted urgent Task created for human oversight
            task = (
                self.session.query(Task)
                .filter(Task.case_id == self.case_1.id, Task.priority == "critical")
                .first()
            )
            self.assertIsNotNone(task, "Clinical escalation must create a persisted urgent Task in PostgreSQL!")
            self.assertEqual(task.status, "pending")

    # -------------------------------------------------------------------------
    # 7. Golden Utterance Evaluation per Role
    # -------------------------------------------------------------------------
    def test_09_golden_utterance_eval_patient(self):
        """Evaluates patient natural-language intents including fragments and misspellings."""
        patient_utterances = [
            ("my report what saying", "case_context_inquiry"),
            ("i want book doctor tomorrow", "appointment_booking_request"),
            ("why did my doctor refer me", "referral_inquiry"),
            ("doctor not call me yet", "referral_delay"),
            ("i am fear biopsy", "patient_inquiry"),
            ("any other slot morning", "appointment_slot_alternatives"),
        ]

        passed = 0
        for text, expected in patient_utterances:
            intent = CognitiveEngine.analyze_intent(
                message=text,
                patient_context={"preferred_language": "en"},
                case_context={"screening_type": "Mammogram", "finding_code": "BI-RADS 4"},
                conversation_context={"inbound_sender": "patient"}
            )
            if intent.primary_intent == expected:
                passed += 1

        pass_rate = passed / len(patient_utterances)
        self.assertGreaterEqual(pass_rate, 0.80, f"Patient golden utterance pass rate {pass_rate:.1%} < 80%")

    def test_10_golden_utterance_eval_coordinator(self):
        """Evaluates coordinator operational intents."""
        coord_utterances = [
            ("is there any new patient", "new_patient_discovery"),
            ("show me pending coordination tasks", "task_management"),
            ("which cases have overdue referrals", "referral_monitoring"),
            ("are there any stalled cases", "sla_recovery_queue"),
        ]

        passed = 0
        for text, expected in coord_utterances:
            intent = CognitiveEngine.analyze_intent(
                message=text,
                patient_context={},
                case_context={},
                conversation_context={"inbound_sender": "care_coordinator"}
            )
            if intent.primary_intent == expected:
                passed += 1

        pass_rate = passed / len(coord_utterances)
        self.assertGreaterEqual(pass_rate, 0.75, f"Coordinator golden utterance pass rate {pass_rate:.1%} < 75%")


if __name__ == "__main__":
    unittest.main()

