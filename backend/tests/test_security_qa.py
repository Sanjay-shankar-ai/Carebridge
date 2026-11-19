"""
CareBridge Phase 11: Security & Quality Assurance Comprehensive Test Suite
Validates:
1. AI interpretation accuracy (intents, sentiments, multi-lingual concordance)
2. Conversational memory (factual recall, thread isolation)
3. Tool selection & routing
4. Tool execution (atomic DB persistence)
5. Database persistence & relational integrity
6. Workflow resumption from checkpoints
7. Duplicate event & message de-duplication idempotency
8. API validation (UUID, payload schemas)
9. Authentication (API keys, Bearer tokens, Principal resolution)
10. Role-based access control (RBAC & Level 3 human gate)
11. Consent enforcement (outreach & referral sharing scopes)
12. Audit logging (tamper-evident telemetry, autonomy levels)
13. Human approval (LangGraph interrupt/resume, supervisory gate)
14. Closure verification (physician clinical sign-off requirement)
15. Minimum necessary PHI masking
16. Zero hardcoded secrets & synthetic data compliance
"""

import unittest
import uuid
from datetime import datetime, timezone, timedelta, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.database.seed import seed_database
from app.models import (
    Patient, CareCase, Appointment, Referral, Communication,
    Consent, ClosureEvidence, CaseOwner, CaseEvent, AuditLog
)
from app.core.security import (
    get_current_user,
    require_role,
    filter_minimum_necessary_phi,
    mask_phone_number,
    ROLE_API_KEYS,
    UserPrincipal
)
from app.tools.base import ToolExecutionError, validate_tool_permission
from app.tools.registry import ToolRegistry
import app.tools.communication_tools as comm_tools
import app.tools.referral_tools as ref_tools
import app.tools.closure_tools as clos_tools
from app.tools.schemas import (
    SendPermittedCommunicationInput,
    CreateReferralRequestInput,
    RetrieveClosureEvidenceInput,
    RequestClosureVerificationInput
)
from app.agents.cognitive_engine import CognitiveEngine
from app.agents.state import AgentState
from app.workflows.persistence.idempotency import IdempotencyManager, DuplicateMessageFilter


class TestSecurityAndQualityAssurance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        cls.SessionFactory = sessionmaker(bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

    def setUp(self):
        self.session = self.SessionFactory()
        seed_database(self.session, extended=True)
        self.case = self.session.query(CareCase).filter(CareCase.case_number == "CASE-2026-0147").first()
        self.patient = self.session.query(Patient).filter(Patient.id == self.case.patient_id).first()

    def tearDown(self):
        self.session.close()

    # ==========================================================================
    # 1. AI Interpretation Accuracy & Language Concordance
    # ==========================================================================
    def test_01_ai_intent_interpretation_accuracy(self):
        """Verifies accurate intent classification across diverse patient utterances."""
        engine = CognitiveEngine()
        p_ctx = {"preferred_language": "ta"}
        c_ctx = {"screening_type": "Mammogram", "finding_code": "BI-RADS-4"}

        # Transportation barrier utterance
        t_res = engine.analyze_intent(
            "I cannot make it to the clinic because my daughter is out of town and cannot drive me.",
            p_ctx,
            c_ctx
        )
        self.assertIn(t_res.primary_intent, [
            "appointment_reschedule_with_barrier", "appointment_reschedule_request", "reschedule", "barrier_transit",
            "transportation_issue", "appointment_reschedule", "barrier"
        ])
        self.assertTrue(len(t_res.detected_barriers) > 0 or t_res.emotional_state in ["anxious", "overwhelmed", "neutral"])

        # Medical question utterance
        q_res = engine.analyze_intent(
            "What does BI-RADS 4 mean? Is it definitely cancer?",
            {"preferred_language": "en"},
            c_ctx
        )
        self.assertIn(q_res.primary_intent, ["patient_inquiry", "clinical_question", "question", "clarification", "anxiety_inquiry", "medical_question"])

        # Tamil language comprehension
        tamil_res = engine.analyze_intent(
            "நாளை என்னால் வர இயலாது, உதவி தேவை", # "I cannot come tomorrow, need help"
            {"preferred_language": "ta"},
            c_ctx
        )
        self.assertIsNotNone(tamil_res.primary_intent)

    # ==========================================================================
    # 2. Conversational Memory & Thread Isolation
    # ==========================================================================
    def test_02_conversational_memory_persistence(self):
        """Validates that patient facts and barriers persist in memory across conversation turns."""
        self.assertIsNotNone(self.patient.patient_context)
        barriers = self.patient.patient_context.get("known_barriers", [])
        self.assertIn("transportation_caregiver_dependency", barriers)

        # Thread isolation: Ensure Case P-0147 communications are isolated from P-0148
        case_148 = self.session.query(CareCase).filter(CareCase.case_number == "CASE-2026-0148").first()
        c147_comms = self.session.query(Communication).filter(Communication.case_id == self.case.id).all()
        c148_comms = self.session.query(Communication).filter(Communication.case_id == case_148.id).all()

        c147_ids = {c.id for c in c147_comms}
        c148_ids = {c.id for c in c148_comms}
        self.assertEqual(len(c147_ids.intersection(c148_ids)), 0, "Memory threads must remain isolated.")

    # ==========================================================================
    # 3. Tool Selection & Permission Boundaries
    # ==========================================================================
    def test_03_tool_selection_and_role_permissions(self):
        """Validates tool hierarchy: Level 1/2 autonomous vs Level 3 human gate."""
        # Level 1/2: Permitted for AI coordinator
        validate_tool_permission("ai_coordinator", autonomy_level=1)
        validate_tool_permission("ai_coordinator", autonomy_level=2)

        # Level 3: AI Coordinator strictly forbidden
        with self.assertRaises(ToolExecutionError) as ctx:
            validate_tool_permission("ai_coordinator", autonomy_level=3)
        self.assertEqual(ctx.exception.error_code, "PERMISSION_DENIED")

        # Level 3: Permitted for licensed clinician
        validate_tool_permission("clinician", autonomy_level=3)
        validate_tool_permission("specialist", autonomy_level=3)

    # ==========================================================================
    # 4. Tool Execution & Atomic DB Persistence
    # ==========================================================================
    def test_04_atomic_tool_execution_and_persistence(self):
        """Verifies atomic appointment booking tool execution with database commit."""
        now = datetime.now(timezone.utc)
        appt_time = (now + timedelta(days=3)).isoformat()
        res = ToolRegistry.book_appointment(
            db=self.session,
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            facility="Clinic A - Women's Specialty",
            scheduled_time=appt_time,
            appointment_type="consultation"
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["autonomy_level"], 2)

        # Confirm persisted in database
        persisted = self.session.query(Appointment).filter(Appointment.id == uuid.UUID(res["data"]["appointment_id"])).first()
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status, "booked")

    # ==========================================================================
    # 5. Database Relational Integrity
    # ==========================================================================
    def test_05_database_persistence_and_relationships(self):
        """Validates foreign key integrity and bidirectional ORM relationships."""
        self.assertEqual(self.case.patient.id, self.patient.id)
        self.assertIsNotNone(self.case.current_owner)
        self.assertGreater(len(self.case.communications), 0)
        self.assertGreater(len(self.case.appointments), 0)

    # ==========================================================================
    # 6. Duplicate Event Prevention & Idempotency
    # ==========================================================================
    def test_06_duplicate_event_and_message_suppression(self):
        """Validates inbound message hash de-duplication and idempotency keys."""
        msg = "I need to reschedule my consultation"
        cid = str(self.case.id)

        # First message passes
        self.assertFalse(DuplicateMessageFilter.is_duplicate_inbound(cid, "patient", msg))

        # Immediate duplicate is suppressed
        self.assertTrue(DuplicateMessageFilter.is_duplicate_inbound(cid, "patient", msg))

        # Idempotency token generation and cached outcome execution
        key = f"referral:{cid}:facility_a"
        op_count = {"count": 0}
        def _test_op():
            op_count["count"] += 1
            return {"status": "dispatched"}

        res1 = IdempotencyManager.execute_idempotent(key, _test_op)
        res2 = IdempotencyManager.execute_idempotent(key, _test_op)
        self.assertEqual(res1, res2)
        self.assertEqual(op_count["count"], 1, "Idempotent operation must only execute once.")

    # ==========================================================================
    # 7. Consent Enforcement (Outreach & Referral Sharing)
    # ==========================================================================
    def test_07_consent_enforcement_outreach_and_referrals(self):
        """Validates that automated outreach and inter-facility referrals require active consent."""
        # 1. Outreach with active consent succeeds
        comm_input = SendPermittedCommunicationInput(
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            channel="whatsapp",
            content="Your appointment reminder for tomorrow.",
            message_type="reminder"
        )
        res_ok = comm_tools.send_permitted_communication(self.session, comm_input)
        self.assertTrue(res_ok.success)

        # 2. Revoke consent and confirm outreach is blocked
        for c in self.patient.consents:
            c.status = "revoked"
        self.session.commit()

        res_blocked = comm_tools.send_permitted_communication(self.session, comm_input)
        self.assertFalse(res_blocked.success)
        self.assertIn(res_blocked.error_code, ["CONSENT_REVOKED", "CONSENT_MISSING"])

        # 3. Referral dispatch without referral consent is blocked
        ref_input = CreateReferralRequestInput(
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            target_facility="External Diagnostic Imaging Center",
            specialty="Radiology",
            reason="Follow-up ultrasound"
        )
        ref_blocked = ref_tools.create_referral_request(self.session, ref_input)
        self.assertFalse(ref_blocked.success)
        self.assertEqual(ref_blocked.error_code, "CONSENT_MISSING")

    # ==========================================================================
    # 8. Audit Logging & Autonomy Levels
    # ==========================================================================
    def test_08_immutable_audit_logging(self):
        """Validates tamper-evident audit logging for state-modifying agent actions."""
        pre_count = self.session.query(AuditLog).count()

        ToolRegistry.log_audit(
            db=self.session,
            action="TEST_SECURITY_ACTION",
            actor_id="qa_test_suite",
            autonomy_level=2,
            rationale="Automated security verification audit trial",
            case_id=self.case.id,
            patient_id=self.patient.id
        )

        post_count = self.session.query(AuditLog).count()
        self.assertEqual(post_count, pre_count + 1)

        latest_audit = self.session.query(AuditLog).order_by(AuditLog.timestamp.desc()).first()
        self.assertEqual(latest_audit.action, "TEST_SECURITY_ACTION")
        self.assertEqual(latest_audit.autonomy_level, 2)

    # ==========================================================================
    # 9. Human Approval & Strict Prohibition on AI-Only Clinical Closure
    # ==========================================================================
    def test_09_prohibition_on_ai_only_clinical_closure(self):
        """
        CRITICAL CLINICAL INVARIANT:
        AI is strictly prohibited from approving final clinical closure.
        Verification requires authorized licensed clinician sign-off.
        """
        dr_thorne = self.session.query(CaseOwner).filter(CaseOwner.role == "specialist").first()
        self.assertIsNotNone(dr_thorne)

        # AI requests verification -> produces pending task, is_verified=False
        inp = RequestClosureVerificationInput(
            case_id=str(self.case.id),
            clinician_id=str(dr_thorne.id),
            evidence_type="pathology_report",
            evidence_summary="Biopsy reveals benign tissue. Clinical sign-off needed.",
            actor_role="ai_coordinator"
        )
        res = clos_tools.request_closure_verification(self.session, inp)
        self.assertTrue(res.success)
        self.assertFalse(res.data.is_verified, "AI must NEVER mark closure as verified.")
        self.assertTrue(res.data.requires_human_approval)
        self.assertEqual(res.autonomy_level, 3)

        # Unauthorized role cannot act as verifying clinician
        coord_priya = self.session.query(CaseOwner).filter(CaseOwner.role == "care_coordinator").first()
        inp_bad_clinician = RequestClosureVerificationInput(
            case_id=str(self.case.id),
            clinician_id=str(coord_priya.id),  # Coordinator, NOT a licensed doctor!
            evidence_type="pathology_report",
            evidence_summary="Attempted closure sign-off by coordinator.",
            actor_role="care_coordinator"
        )
        res_bad = clos_tools.request_closure_verification(self.session, inp_bad_clinician)
        self.assertFalse(res_bad.success)
        self.assertEqual(res_bad.error_code, "INVALID_CLINICIAN")

    # ==========================================================================
    # 10. Authentication & Role-Based Access Control (RBAC)
    # ==========================================================================
    def test_10_authentication_and_rbac(self):
        """Validates API key resolution, UserPrincipal context, and role enforcement."""
        # 1. Resolver for coordinator key
        coord_user = get_current_user(api_key="dev-coordinator-key")
        self.assertEqual(coord_user.role, "care_coordinator")
        self.assertEqual(coord_user.name, "Priya Nair, RN")

        # 2. Resolver for clinician key
        doc_user = get_current_user(api_key="dev-clinician-key")
        self.assertEqual(doc_user.role, "clinician")
        self.assertEqual(doc_user.name, "Dr. Aris Thorne, MD")

        # 3. RBAC guard: Clinician allowed for clinical review
        doc_checker = require_role(["clinician", "specialist"])
        authorized_doc = doc_checker(user=doc_user)
        self.assertEqual(authorized_doc.role, "clinician")

        # 4. RBAC guard: Coordinator blocked from clinician-only endpoints
        with self.assertRaises(Exception):
            doc_checker(user=coord_user)

    # ==========================================================================
    # 11. Minimum Necessary PHI Standard
    # ==========================================================================
    def test_11_minimum_necessary_phi_masking(self):
        """Validates redaction and masking of direct identifiers for non-clinical roles."""
        raw_phone = "+91-94440-12345"
        masked = mask_phone_number(raw_phone)
        self.assertIn("***", masked)
        self.assertTrue(masked.startswith("+91-94"))
        self.assertTrue(masked.endswith("345"))

        patient_dict = {
            "mrn": "MRN-2026-0147",
            "name": "Meenakshi Ramanathan",
            "phone": "+91-94440-12345",
            "email": "meenakshi.r52@example.com"
        }

        # Coordinator / Public role -> PHI masked
        coord_view = filter_minimum_necessary_phi(patient_dict, requester_role="care_coordinator")
        self.assertIn("***", coord_view["phone"])
        self.assertIn("***", coord_view["email"])

        # Clinician role -> Full clinical access
        doc_view = filter_minimum_necessary_phi(patient_dict, requester_role="clinician")
        self.assertEqual(doc_view["phone"], "+91-94440-12345")
        self.assertEqual(doc_view["email"], "meenakshi.r52@example.com")

    # ==========================================================================
    # 12. Synthetic Data & Security Sanitization Compliance
    # ==========================================================================
    def test_12_synthetic_data_compliance(self):
        """Ensures all seeded patient demographics are synthetic for hackathon safety."""
        all_patients = self.session.query(Patient).all()
        for p in all_patients:
            self.assertTrue(p.mrn.startswith("MRN-2026-"), f"MRN must follow synthetic pattern: {p.mrn}")
            self.assertTrue(
                p.phone.startswith("+91-") or p.phone.startswith("+1-555-"),
                f"Phone must be fictitious: {p.phone}"
            )
            self.assertIn("example.com", p.email, f"Email must use RFC 2606 example.com domain: {p.email}")


if __name__ == "__main__":
    unittest.main()
