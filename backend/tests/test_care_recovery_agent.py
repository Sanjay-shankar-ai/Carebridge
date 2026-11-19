"""
CareBridge Phase 7 Unit and Integration Test Suite: Care Recovery Agent
Tests comprehensive multi-source context retrieval, fact vs assumption separation,
patient clarification inquiries, context-aware playbooks, dynamic multilingual messaging,
multi-attempt adaptation, and Care Coordinator ownership continuity.
"""

import uuid
import unittest
from datetime import datetime, timezone, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.session import Base
from app.database.seed import seed_database
from app.models.care_case import CareCase, Task
from app.models.patient import Patient
from app.models.owner import CaseOwner
from app.models.communication import Communication, ConversationSession
from app.models.referral import Referral
from app.models.appointment import Appointment
from app.models.event_audit import CaseEvent, AuditLog

from app.agents.recovery.context_retriever import MultiSourceContextRetriever
from app.agents.recovery.evaluator import FactAssumptionEvaluator
from app.agents.recovery.playbooks import RecoveryPlaybookEngine
from app.agents.recovery.agent import CareRecoveryAgent, create_recovery_graph, run_care_recovery_agent
from app.services.care_coordination_service import CareCoordinationService


class TestCareRecoveryAgent(unittest.TestCase):
    """Exhaustive test suite for the Phase 7 Care Recovery Agent."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False, future=True)
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionFactory = sessionmaker(bind=cls.engine, autocommit=False, autoflush=False)

        import app.database.session as session_module
        session_module.sync_session_factory = cls.SessionFactory

        from app.core.config import settings
        settings.LLM_PROVIDER = "mock"

    def setUp(self):
        Base.metadata.create_all(self.engine)
        self.db = self.SessionFactory()
        seed_database(self.db)

        # Retrieve exemplar records from seed
        self.patient = self.db.query(Patient).filter(Patient.mrn == "MRN-2026-0147").first()
        self.case = self.db.query(CareCase).filter(CareCase.patient_id == self.patient.id).first()
        self.coordinator = self.case.current_owner

        # Reset case context for clean test state
        ctx = dict(self.case.case_context or {})
        ctx["recovery_attempts"] = 0
        ctx["inferred_barriers"] = []
        self.case.case_context = ctx
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    # ==========================================================================
    # Test 1: Multi-Source Context Retrieval across all 8 dimensions
    # ==========================================================================
    def test_01_multi_source_context_retrieval(self):
        """Verifies that all 8 operational context dimensions are retrieved and structured."""
        now = datetime.now(timezone.utc)
        comm = Communication(
            id=uuid.uuid4(),
            case_id=self.case.id,
            patient_id=self.patient.id,
            sender="ai_coordinator",
            channel="sms",
            language="en",
            content="Hello Meenakshi, we need to schedule your follow-up.",
            sent_at=now - timedelta(hours=36)
        )
        appt = Appointment(
            id=uuid.uuid4(),
            case_id=self.case.id,
            patient_id=self.patient.id,
            facility="Mercy Imaging Center",
            provider_name="Dr. Sundaram",
            appointment_type="diagnostic_mammogram",
            scheduled_time=now - timedelta(days=1),
            status="no_show"
        )
        task = Task(
            id=uuid.uuid4(),
            case_id=self.case.id,
            title="Coordinate appointment",
            description="Coordinate diagnostic appointment with facility",
            task_type="appointment_coordination",
            assigned_role="care_coordinator",
            assigned_to_id=self.coordinator.id,
            status="pending",
            due_date=now - timedelta(hours=2) # Overdue
        )
        self.db.add_all([comm, appt, task])
        self.db.commit()

        ctx = MultiSourceContextRetriever.retrieve_full_context(self.db, str(self.case.id))

        # Check all 8 dimensions
        self.assertIn("case_history", ctx)
        self.assertIn("patient_conversations", ctx)
        self.assertIn("previous_communication_attempts", ctx)
        self.assertIn("referral_status", ctx)
        self.assertIn("appointment_history", ctx)
        self.assertIn("patient_preferences", ctx)
        self.assertIn("outstanding_tasks", ctx)
        self.assertIn("sla_context", ctx)

        # Dimension content checks
        self.assertEqual(ctx["case_history"]["current_owner_name"], self.coordinator.name)
        self.assertGreaterEqual(ctx["appointment_history"]["no_show_count"], 1)
        self.assertGreaterEqual(ctx["outstanding_tasks"]["overdue_count"], 1)
        self.assertEqual(ctx["patient_preferences"]["preferred_language"], self.patient.preferred_language)
        self.assertGreaterEqual(ctx["previous_communication_attempts"]["outreach_count"], 1)

    # ==========================================================================
    # Test 2: Stalled Journey Detection across signals
    # ==========================================================================
    def test_02_stalled_journey_detection(self):
        """Verifies detection of stalled journeys (no-show, unacknowledged outreach, overdue tasks)."""
        now = datetime.now(timezone.utc)
        appt = Appointment(
            id=uuid.uuid4(),
            case_id=self.case.id,
            patient_id=self.patient.id,
            facility="Mercy Imaging",
            provider_name="Dr. Sundaram",
            appointment_type="diagnostic_mammogram",
            scheduled_time=now - timedelta(days=1),
            status="no_show"
        )
        comm = Communication(
            id=uuid.uuid4(),
            case_id=self.case.id,
            patient_id=self.patient.id,
            sender="ai_coordinator",
            channel="sms",
            content="Please confirm your appointment",
            sent_at=now - timedelta(hours=30)
        )
        self.db.add_all([appt, comm])
        self.db.commit()

        ctx = MultiSourceContextRetriever.retrieve_full_context(self.db, str(self.case.id))
        is_stalled, signals = FactAssumptionEvaluator.detect_stalled_journey(ctx)

        self.assertTrue(is_stalled)
        signal_types = [s["type"] for s in signals]
        self.assertIn("appointment_no_show", signal_types)

    # ==========================================================================
    # Test 3: Distinguishing Known Facts from Assumptions (Unknown Cause)
    # ==========================================================================
    def test_03_facts_vs_assumptions_unexplained_noshow(self):
        """
        When patient no-shows with NO explanation message, the agent MUST flag
        that the cause is an assumption, and trigger clarification rather than guessing.
        """
        # Clear any prior messages so the no-show is completely unexplained
        self.db.query(Communication).filter(Communication.case_id == self.case.id).delete()
        self.db.commit()

        now = datetime.now(timezone.utc)
        appt = Appointment(
            id=uuid.uuid4(),
            case_id=self.case.id,
            patient_id=self.patient.id,
            facility="Mercy Imaging",
            provider_name="Dr. Sundaram",
            appointment_type="diagnostic_mammogram",
            scheduled_time=now - timedelta(days=1),
            status="no_show"
        )
        self.db.add(appt)
        self.db.commit()

        ctx = MultiSourceContextRetriever.retrieve_full_context(self.db, str(self.case.id))
        is_stalled, signals = FactAssumptionEvaluator.detect_stalled_journey(ctx)
        eval_res = FactAssumptionEvaluator.evaluate_facts_vs_assumptions(ctx, signals)

        # Verified facts include the appointment record
        fact_categories = [f["category"] for f in eval_res["known_facts"]]
        self.assertIn("appointment", fact_categories)

        # Assumptions include unverified hypotheses about the no-show reason
        self.assertGreater(len(eval_res["assumptions"]), 0)
        self.assertEqual(eval_res["assumptions"][0]["event"], "appointment_no_show")

        # MUST require clarification from patient
        self.assertTrue(eval_res["needs_clarification"])
        self.assertIn("Must inquire empathetically before assuming cause", eval_res["clarification_reason"])

    # ==========================================================================
    # Test 4: Known Fact when Patient Explicitly Communicates Barrier
    # ==========================================================================
    def test_04_facts_vs_assumptions_explicit_barrier(self):
        """
        When patient explicitly texted 'I don't have a car to drive there',
        the barrier is a KNOWN FACT and clarification is NOT needed.
        """
        now = datetime.now(timezone.utc)
        comm = Communication(
            id=uuid.uuid4(),
            case_id=self.case.id,
            patient_id=self.patient.id,
            sender="patient",
            channel="sms",
            language="en",
            content="I can't make it because my car broke down and I have no ride to the clinic.",
            sent_at=now - timedelta(hours=4)
        )
        appt = Appointment(
            id=uuid.uuid4(),
            case_id=self.case.id,
            patient_id=self.patient.id,
            facility="Mercy Imaging",
            provider_name="Dr. Sundaram",
            appointment_type="diagnostic_mammogram",
            scheduled_time=now - timedelta(days=1),
            status="no_show"
        )
        self.db.add_all([comm, appt])
        self.db.commit()

        ctx = MultiSourceContextRetriever.retrieve_full_context(self.db, str(self.case.id))
        is_stalled, signals = FactAssumptionEvaluator.detect_stalled_journey(ctx)
        eval_res = FactAssumptionEvaluator.evaluate_facts_vs_assumptions(ctx, signals)

        # Barrier identified as a verified Known Fact
        self.assertIn("transportation", eval_res["detected_barriers"])
        fact_quotes = [f.get("quote") for f in eval_res["known_facts"] if "quote" in f]
        self.assertTrue(any("car broke down" in q for q in fact_quotes if q))

        # Because the cause is KNOWN, clarification about the cause is NOT needed
        self.assertFalse(eval_res["needs_clarification"])

    # ==========================================================================
    # Test 5: Context-Aware Playbook Selection (Barrier Specific)
    # ==========================================================================
    def test_05_playbook_selection_matrix(self):
        """Verifies correct playbook selection for different barrier conditions."""
        # 1. Transportation
        pb_trans = RecoveryPlaybookEngine.select_playbook(
            stalled_signals=[], known_facts=[], assumptions=[],
            detected_barriers=["transportation"],
            needs_clarification=False, recovery_attempts=0, sla_breached=False, is_referral_stalled=False
        )
        self.assertEqual(pb_trans, "transportation_support")

        # 2. Caregiver / Family
        pb_care = RecoveryPlaybookEngine.select_playbook(
            stalled_signals=[], known_facts=[], assumptions=[],
            detected_barriers=["caregiver_family"],
            needs_clarification=False, recovery_attempts=0, sla_breached=False, is_referral_stalled=False
        )
        self.assertEqual(pb_care, "caregiver_coordination")

        # 3. Fear & Anxiety
        pb_fear = RecoveryPlaybookEngine.select_playbook(
            stalled_signals=[], known_facts=[], assumptions=[],
            detected_barriers=["fear_anxiety"],
            needs_clarification=False, recovery_attempts=0, sla_breached=False, is_referral_stalled=False
        )
        self.assertEqual(pb_fear, "fear_anxiety_support")

        # 4. Clarification Inquiry (when cause is unknown)
        pb_clar = RecoveryPlaybookEngine.select_playbook(
            stalled_signals=[], known_facts=[], assumptions=[],
            detected_barriers=[],
            needs_clarification=True, recovery_attempts=0, sla_breached=False, is_referral_stalled=False
        )
        self.assertEqual(pb_clar, "clarification_inquiry")

        # 5. SLA Breached / Recovery Exhausted -> Emergency Escalation
        pb_esc = RecoveryPlaybookEngine.select_playbook(
            stalled_signals=[], known_facts=[], assumptions=[],
            detected_barriers=["transportation"],
            needs_clarification=False, recovery_attempts=3, sla_breached=False, is_referral_stalled=False
        )
        self.assertEqual(pb_esc, "emergency_escalation")

    # ==========================================================================
    # Test 6: Non-Fixed Dynamic Multilingual Messaging
    # ==========================================================================
    def test_06_dynamic_multilingual_messaging(self):
        """Verifies non-fixed messaging across languages and attempt levels."""
        # English Clarification Message
        en_msg = RecoveryPlaybookEngine.generate_patient_message(
            playbook="clarification_inquiry",
            patient_name="Meenakshi",
            language="en",
            attempt=0
        )
        self.assertIn("Meenakshi", en_msg)
        self.assertIn("CareBridge", en_msg)

        # Spanish Transportation Message
        es_msg = RecoveryPlaybookEngine.generate_patient_message(
            playbook="transportation_support",
            patient_name="Elena",
            language="es",
            attempt=0
        )
        self.assertIn("Elena", es_msg)
        self.assertIn("transporte", es_msg.lower())

        # Tamil Clarification Message
        ta_msg = RecoveryPlaybookEngine.generate_patient_message(
            playbook="clarification_inquiry",
            patient_name="மீனாட்சி",
            language="ta",
            attempt=0
        )
        self.assertIn("மீனாட்சி", ta_msg)
        self.assertIn("CareBridge", ta_msg)

        # Progression across attempts for unacknowledged outreach
        att1_msg = RecoveryPlaybookEngine.generate_patient_message(
            playbook="unacknowledged_reengagement",
            patient_name="Meenakshi",
            language="en",
            attempt=0
        )
        att3_msg = RecoveryPlaybookEngine.generate_patient_message(
            playbook="unacknowledged_reengagement",
            patient_name="Meenakshi",
            language="en",
            attempt=2
        )
        self.assertNotEqual(att1_msg, att3_msg)
        self.assertIn("URGENT", att3_msg.upper())

    # ==========================================================================
    # Test 7: Multi-Attempt Progression & Adaptation
    # ==========================================================================
    def test_07_multi_attempt_progression(self):
        """Verifies stateful attempt tracking, playbook adaptation, and escalation at max attempts."""
        # Clear prior messages so no-show is unexplained and requires initial clarification
        self.db.query(Communication).filter(Communication.case_id == self.case.id).delete()
        self.db.commit()

        now = datetime.now(timezone.utc)
        appt = Appointment(
            id=uuid.uuid4(),
            case_id=self.case.id,
            patient_id=self.patient.id,
            facility="Mercy Imaging",
            provider_name="Dr. Sundaram",
            appointment_type="diagnostic_mammogram",
            scheduled_time=now - timedelta(days=1),
            status="no_show"
        )
        self.db.add(appt)
        self.db.commit()

        # Run Attempt 1
        res1 = run_care_recovery_agent(str(self.case.id))
        self.assertEqual(res1["recovery_attempts"], 1)
        self.assertEqual(res1["selected_playbook"], "clarification_inquiry")
        self.assertEqual(res1["outcome_status"], "clarification_pending")

        # Simulate Attempt 2
        res2 = run_care_recovery_agent(str(self.case.id))
        self.assertEqual(res2["recovery_attempts"], 2)

        # Simulate Attempt 3
        res3 = run_care_recovery_agent(str(self.case.id))
        self.assertEqual(res3["recovery_attempts"], 3)

        # Run Attempt 4 (Attempts >= 3 triggers emergency escalation)
        res4 = run_care_recovery_agent(str(self.case.id))
        self.assertEqual(res4["selected_playbook"], "emergency_escalation")
        self.assertEqual(res4["outcome_status"], "escalated")

    # ==========================================================================
    # Test 8: Care Coordinator Ownership Continuity
    # ==========================================================================
    def test_08_coordinator_ownership_continuity(self):
        """Verifies coordinator retains ownership and receives notifications during recovery."""
        now = datetime.now(timezone.utc)
        appt = Appointment(
            id=uuid.uuid4(),
            case_id=self.case.id,
            patient_id=self.patient.id,
            facility="Mercy Imaging",
            provider_name="Dr. Sundaram",
            appointment_type="diagnostic_mammogram",
            scheduled_time=now - timedelta(days=1),
            status="no_show"
        )
        self.db.add(appt)
        self.db.commit()

        res = run_care_recovery_agent(str(self.case.id))

        self.assertTrue(res["coordinator_notified"])
        self.assertEqual(res["accountable_owner_id"], str(self.coordinator.id))

        # Check DB to verify coordinator is still current_owner_id
        self.db.expire_all()
        case_db = self.db.query(CareCase).filter(CareCase.id == self.case.id).first()
        self.assertEqual(case_db.current_owner_id, self.coordinator.id)

        # Verify notification task was created and assigned to coordinator
        tasks = self.db.query(Task).filter(
            Task.case_id == self.case.id,
            Task.assigned_to_id == self.coordinator.id
        ).all()
        self.assertGreater(len(tasks), 0)

    # ==========================================================================
    # Test 9: End-to-End Service Integration with CareCoordinationService
    # ==========================================================================
    def test_09_care_coordination_service_recover_stalled_case(self):
        """Verifies CareCoordinationService.recover_stalled_case coordinates the recovery agent."""
        now = datetime.now(timezone.utc)
        # Setup stalled case by adding a missed appointment
        appt = Appointment(
            id=uuid.uuid4(),
            case_id=self.case.id,
            patient_id=self.patient.id,
            facility="Mercy Imaging",
            provider_name="Dr. Sundaram",
            appointment_type="diagnostic_mammogram",
            scheduled_time=now - timedelta(days=2),
            status="no_show"
        )
        self.db.add(appt)
        self.db.commit()

        result = CareCoordinationService.recover_stalled_case(case_id=str(self.case.id))

        self.assertTrue(result["is_stalled"])
        self.assertIn("selected_playbook", result)
        self.assertTrue(result["coordinator_notified"])
        self.assertGreater(len(result["tool_actions_executed"]), 0)


if __name__ == "__main__":
    unittest.main()
