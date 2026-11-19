"""
CareBridge Database and Memory Layer Test Suite
Validates the 13 relational entities, foreign key constraints, seed dataset,
and the three memory retrieval layers (Patient, Conversation, Case, Unified).
"""

import unittest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.session import Base
from app.database.seed import seed_database
from app.models import (
    Patient, CareCase, ScreeningResult, CaseOwner, Referral,
    Appointment, Communication, ConversationSession, Task,
    CaseEvent, AuditLog, Consent, ClosureEvidence
)
from app.memory.patient_memory import get_patient_memory_sync, record_patient_barrier
from app.memory.conversation_memory import get_conversation_memory_sync
from app.memory.case_memory import get_case_memory_sync
from app.memory.retriever import get_unified_memory_sync


class TestDatabaseAndMemory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create an in-memory SQLite database for deterministic, high-speed testing
        cls.engine = create_engine(
            "sqlite:///:memory:",
            echo=False,
            future=True
        )
        Base.metadata.create_all(bind=cls.engine)
        cls.SessionFactory = sessionmaker(bind=cls.engine, autocommit=False, autoflush=False)

    def setUp(self):
        self.session = self.SessionFactory()
        # Seed test cohort
        seed_database(self.session)

    def tearDown(self):
        self.session.close()

    def test_relational_models_count(self):
        """Verifies that all 13 models are populated and indexed correctly."""
        self.assertEqual(self.session.query(Patient).count(), 3)
        self.assertEqual(self.session.query(ScreeningResult).count(), 3)
        self.assertEqual(self.session.query(CareCase).count(), 3)
        self.assertEqual(self.session.query(CaseOwner).count(), 2)
        self.assertEqual(self.session.query(Consent).count(), 2)
        self.assertEqual(self.session.query(Referral).count(), 1)
        self.assertEqual(self.session.query(Appointment).count(), 2)
        self.assertEqual(self.session.query(Communication).count(), 3)
        self.assertEqual(self.session.query(ConversationSession).count(), 1)
        self.assertEqual(self.session.query(Task).count(), 1)
        self.assertEqual(self.session.query(CaseEvent).count(), 2)
        self.assertEqual(self.session.query(AuditLog).count(), 2)
        self.assertEqual(self.session.query(ClosureEvidence).count(), 1)

    def test_patient_memory_layer(self):
        """Validates structured patient memory retrieval for Patient P-0147 (Mrs. Meenakshi)."""
        patient = self.session.query(Patient).filter(Patient.mrn == "MRN-2026-0147").first()
        self.assertIsNotNone(patient)

        mem = get_patient_memory_sync(patient.id, self.session)
        self.assertIsNotNone(mem)
        self.assertEqual(mem.full_name, "Meenakshi Ramanathan")
        self.assertEqual(mem.preferred_language, "ta") # Tamil
        self.assertEqual(mem.communication_channel, "whatsapp")
        self.assertIn("transportation_caregiver_dependency", mem.known_barriers)
        self.assertEqual(mem.caregiver_name, "Ananya Ramanathan (Daughter)")
        self.assertIn("automated_patient_outreach", mem.active_consents)

    def test_conversation_memory_layer(self):
        """Validates dialogue history, unanswered queries, and patient commitments for P-0147."""
        patient = self.session.query(Patient).filter(Patient.mrn == "MRN-2026-0147").first()
        case = self.session.query(CareCase).filter(CareCase.case_number == "CASE-2026-0147").first()

        conv = get_conversation_memory_sync(patient.id, case.id, self.session)
        self.assertIsNotNone(conv)
        self.assertGreaterEqual(len(conv.recent_messages), 3)

        # Verify inbound barrier message
        inbound_msg = next((m for m in conv.recent_messages if m.sender == "patient"), None)
        self.assertIsNotNone(inbound_msg)
        self.assertIn("daughter is out of town", inbound_msg.content)

        # Verify active commitments
        self.assertGreaterEqual(len(conv.patient_commitments), 1)
        self.assertIn("daughter Ananya", conv.patient_commitments[0]["commitment"])

    def test_case_memory_layer(self):
        """Validates longitudinal case memory, SLA timers, owner tracking, and recovery records."""
        case = self.session.query(CareCase).filter(CareCase.case_number == "CASE-2026-0147").first()
        self.assertIsNotNone(case)

        case_mem = get_case_memory_sync(case.id, self.session)
        self.assertIsNotNone(case_mem)
        self.assertEqual(case_mem.case_number, "CASE-2026-0147")
        self.assertEqual(case_mem.screening_type, "Mammogram")
        self.assertEqual(case_mem.finding_code, "BI-RADS-4")
        self.assertEqual(case_mem.priority, "urgent")
        self.assertEqual(case_mem.current_owner_name, "Priya Nair, RN")
        self.assertEqual(case_mem.status, "recovering")

        # Verify referral tracking
        self.assertIsNotNone(case_mem.active_referral)
        self.assertEqual(case_mem.active_referral.target_facility, "Clinic A - Women's Specialty Breast Center")
        self.assertEqual(case_mem.active_referral.status, "accepted")

        # Verify appointment history & rescheduled recovery appointment
        self.assertEqual(len(case_mem.appointment_history), 2)
        self.assertIsNotNone(case_mem.upcoming_appointment)
        self.assertEqual(case_mem.upcoming_appointment.status, "booked")

        # Verify recovery strategy in memory
        self.assertEqual(case_mem.recovery_attempts, 1)
        self.assertEqual(case_mem.last_recovery_strategy, "reschedule_with_daughter_availability")
        self.assertIn("transportation_caregiver", case_mem.inferred_barriers)

    def test_unified_memory_retrieval(self):
        """Validates unified composite context passed to the LangGraph brain."""
        case = self.session.query(CareCase).filter(CareCase.case_number == "CASE-2026-0147").first()
        unified = get_unified_memory_sync(case.id, case.patient_id, self.session)

        self.assertIsNotNone(unified)
        self.assertEqual(unified.patient.mrn, "MRN-2026-0147")
        self.assertEqual(unified.case.finding_code, "BI-RADS-4")
        self.assertGreaterEqual(len(unified.conversation.recent_messages), 3)

    def test_evidence_based_closure_governance(self):
        """Validates that closed case P-0149 has verified clinical evidence signed off by a clinician."""
        case_closed = self.session.query(CareCase).filter(CareCase.case_number == "CASE-2026-0149").first()
        self.assertIsNotNone(case_closed)

        case_mem = get_case_memory_sync(case_closed.id, self.session)
        self.assertTrue(case_mem.is_closed)
        self.assertEqual(len(case_mem.closure_evidences), 1)
        
        evidence = case_mem.closure_evidences[0]
        self.assertEqual(evidence["type"], "pathology_report")
        self.assertTrue(evidence["verified"])
        self.assertIn("Benign fibroadenoma", evidence["summary"])

        # Check Level 3 audit trail
        audit = (
            self.session.query(AuditLog)
            .filter(AuditLog.case_id == case_closed.id, AuditLog.action == "VERIFIED_CLINICAL_CLOSURE")
            .first()
        )
        self.assertIsNotNone(audit)
        self.assertEqual(audit.autonomy_level, 3)
        self.assertEqual(audit.actor_type, "clinician")


if __name__ == "__main__":
    unittest.main()
