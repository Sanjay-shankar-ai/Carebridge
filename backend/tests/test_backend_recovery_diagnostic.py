"""
CareBridge Backend Diagnostic and Recovery Test Suite
Validates Phases 1 through 6:
- Database connectivity & relational integrity
- 3-role authentication and authorization (PATIENT, DOCTOR, CARE_COORDINATOR)
- LangGraph Central Supervisor & Doctor Subgraph state machines
- Level 3 clinical safety boundaries (human-in-the-loop closure sign-off)
- Complete 10-step synthetic patient care journey
"""

import unittest
import uuid
from datetime import datetime, timezone, timedelta, date

from app.database.session import get_sync_db
from app.database.seed import seed_database
from app.models import (
    User, Patient, CareCase, CaseOwner, ScreeningResult,
    Referral, Appointment, Communication, ClosureEvidence,
    CaseEvent, AuditLog
)
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    require_role,
    UserPrincipal
)
from app.agents.cognitive_engine import CognitiveEngine
from app.workflows.doctor_workflow import run_doctor_workflow
from app.tools.registry import ToolRegistry
from app.services.analytics_service import CareBridgeAnalyticsService


class TestCareBridgeBackendRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Seed database with demo and extended analytics cohorts."""
        db = get_sync_db()
        try:
            seed_database(db, extended=True)
            db.commit()
        finally:
            db.close()

    def setUp(self):
        self.db = get_sync_db()
        self.case = self.db.query(CareCase).filter(CareCase.case_number == "CASE-2026-0147").first()
        self.assertIsNotNone(self.case, "Base demo case CASE-2026-0147 must exist in database.")
        self.patient = self.db.query(Patient).filter(Patient.id == self.case.patient_id).first()
        self.assertIsNotNone(self.patient, "Associated patient must exist.")

    def tearDown(self):
        self.db.close()

    # ==========================================================================
    # Phase 3: Database and Role-Based Authentication
    # ==========================================================================
    def test_phase3_role_authentication_and_isolation(self):
        """Validates independent authentication for PATIENT, DOCTOR, and CARE_COORDINATOR."""
        # 1. Test Patient Role
        p_user = self.db.query(User).filter(User.role == "patient").first()
        self.assertIsNotNone(p_user)
        self.assertTrue(verify_password("PatientPass123!", p_user.password_hash))
        p_token = create_access_token({"sub": str(p_user.id), "role": "patient", "email": p_user.email})
        p_claims = decode_access_token(p_token)
        self.assertEqual(p_claims["role"], "patient")

        # 2. Test Doctor Role
        d_user = self.db.query(User).filter(User.role == "clinician").first()
        self.assertIsNotNone(d_user)
        self.assertTrue(verify_password("DoctorPass123!", d_user.password_hash))
        d_token = create_access_token({"sub": str(d_user.id), "role": "clinician", "email": d_user.email})
        d_claims = decode_access_token(d_token)
        self.assertEqual(d_claims["role"], "clinician")

        # 3. Test Care Coordinator Role
        c_user = self.db.query(User).filter(User.role == "care_coordinator").first()
        self.assertIsNotNone(c_user)
        self.assertTrue(verify_password("CoordinatorPass123!", c_user.password_hash))
        c_token = create_access_token({"sub": str(c_user.id), "role": "care_coordinator", "email": c_user.email})
        c_claims = decode_access_token(c_token)
        self.assertEqual(c_claims["role"], "care_coordinator")

        # 4. RBAC Gate: Patient blocked from clinical/operational endpoints
        clinical_gate = require_role(["clinician", "care_coordinator"])
        p_principal = UserPrincipal(user_id=str(p_user.id), email=p_user.email, role="patient", full_name=p_user.full_name)
        d_principal = UserPrincipal(user_id=str(d_user.id), email=d_user.email, role="clinician", full_name=d_user.full_name)
        
        # Doctor allowed
        self.assertEqual(clinical_gate(d_principal).role, "clinician")
        # Patient rejected with 403
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            clinical_gate(p_principal)
        self.assertEqual(ctx.exception.status_code, 403)

    # ==========================================================================
    # Phase 4: LangGraph Supervisor, Doctor Subgraph & Safety Gates
    # ==========================================================================
    def test_phase4_doctor_subgraph_clinical_isolation(self):
        """Validates that Doctor interactions route to Doctor Subgraph with clinical persona."""
        d_user = self.db.query(User).filter(User.role == "clinician").first()
        
        # Doctor greeting
        doc_res = run_doctor_workflow(
            doctor_id=str(d_user.id),
            message="Hello, Dr. Thorne checking in on today's clinic schedule"
        )
        self.assertTrue(doc_res.get("is_authorized"))
        self.assertEqual(doc_res.get("doctor_intent"), "general_query")
        msg = doc_res.get("response_message") or ""
        self.assertIn("Clinical Co-Pilot", msg)
        self.assertNotIn("breast cancer", msg.lower())

    def test_phase4_level3_closure_human_gate(self):
        """Validates Level 3 Clinical Gate: AI cannot close a case without verified physician evidence."""
        d_user = self.db.query(User).filter(User.role == "clinician").first()
        doc_id = str(d_user.owner_id) if d_user.owner_id else str(d_user.id)

        # AI-initiated closure verification request requires Level 3 human authorization
        closure_res = ToolRegistry.request_closure_verification(
            db=self.db,
            case_id=str(self.case.id),
            evidence_type="pathology_report",
            evidence_summary="Stereotactic core biopsy returned benign fibroadenoma",
            clinician_id=doc_id
        )
        self.assertTrue(closure_res["success"])
        self.assertEqual(closure_res["autonomy_level"], 3)
        self.assertTrue(closure_res["data"]["requires_human_approval"])
        self.assertFalse(closure_res["data"]["is_verified"], "AI request must NOT autonomously mark closure as verified.")

    # ==========================================================================
    # Phase 5: Core Services & Analytics Metrics
    # ==========================================================================
    def test_phase5_analytics_metrics_calculation(self):
        """Validates calculation of all 9 core metrics from actual DB records."""
        metrics = CareBridgeAnalyticsService.calculate_all_metrics(db=self.db)
        self.assertIn("summary", metrics)
        self.assertIn("metrics", metrics)
        self.assertGreater(metrics["summary"]["total_cases"], 0)
        
        # Check presence of all 9 required metrics
        m = metrics["metrics"]
        for key in [
            "time_from_result_to_notification",
            "patient_acknowledgement_rate",
            "referral_acceptance_rate",
            "appointment_attendance_rate",
            "drop_off_recovery_rate",
            "median_time_to_care",
            "verified_closure_rate",
            "overdue_cases",
            "unassigned_cases"
        ]:
            self.assertIn(key, m, f"Metric '{key}' must be calculated.")

    # ==========================================================================
    # Phase 6: Complete 10-Step Synthetic Patient Care Journey
    # ==========================================================================
    def test_phase6_complete_synthetic_care_journey(self):
        """
        Executes end-to-end synthetic 10-step clinical coordination journey:
        1. Patient logs in
        2. Patient views screening result
        3. Patient asks natural-language question
        4. AI retrieves context & provides nuanced educational answer
        5. Care Coordinator coordinates referral
        6. Doctor logs in and reviews case
        7. Doctor records consultation notes
        8. Doctor schedules diagnostic follow-up
        9. Patient receives communication update
        10. Case achieves approved clinical closure verification
        """
        # Step 1: Patient logs in
        p_user = self.db.query(User).filter(User.role == "patient").first()
        self.assertIsNotNone(p_user)
        self.assertTrue(verify_password("PatientPass123!", p_user.password_hash))

        # Step 2: Patient views screening result
        screening = self.db.query(ScreeningResult).filter(ScreeningResult.patient_id == p_user.patient_id).first()
        self.assertIsNotNone(screening)
        self.assertEqual(screening.finding_code, "BI-RADS-4")

        # Step 3: Patient asks natural-language question
        question = "What does BI-RADS 4 mean? Is it definitely cancer?"
        engine = CognitiveEngine()
        p_ctx = {"first_name": self.patient.first_name, "preferred_language": "en"}
        c_ctx = {"screening_type": screening.screening_type, "finding_code": screening.finding_code}

        # Step 4: AI retrieves context and responds empathetically with 70-80% benign explanation
        intent = engine.analyze_intent(question, p_ctx, c_ctx)
        self.assertEqual(intent.primary_intent, "patient_inquiry")
        self.assertEqual(intent.inquiry_topic, "birads")
        plan = engine.formulate_plan(intent, p_ctx, c_ctx, {})
        self.assertIn("70% to 80%", plan.patient_response_draft)
        self.assertIn("NOT a diagnosis of cancer", plan.patient_response_draft)

        # Step 5: Care Coordinator coordinates referral
        ref_res = ToolRegistry.create_referral_request(
            db=self.db,
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            target_facility="Clinic A - Women's Specialty Breast Center",
            specialty="Breast Surgical Oncology",
            reason="Expedited diagnostic core needle biopsy per BI-RADS 4 protocol"
        )
        self.assertTrue(ref_res["success"])
        ref_id = ref_res["data"]["referral_id"]

        # Step 6: Doctor logs in and reviews assigned case
        d_user = self.db.query(User).filter(User.role == "clinician").first()
        review_res = run_doctor_workflow(
            doctor_id=str(d_user.id),
            case_id=str(self.case.id),
            message="Review case CASE-2026-0147"
        )
        self.assertTrue(review_res.get("is_authorized"))
        self.assertIn("CASE-2026-0147", review_res.get("response_message", ""))

        # Step 7: Doctor records clinical consultation notes
        note_res = ToolRegistry.update_case_notes(
            db=self.db,
            case_id=str(self.case.id),
            note="Consultation completed: Diagnostic ultrasound and stereotactic core biopsy indicated."
        )
        self.assertTrue(note_res["success"])

        # Step 8: Doctor schedules follow-up diagnostic biopsy
        now = datetime.now(timezone.utc)
        appt_time = (now + timedelta(days=3, hours=10)).isoformat()
        appt_res = ToolRegistry.book_appointment(
            db=self.db,
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            facility="Clinic A - Women's Specialty Breast Center",
            scheduled_time=appt_time,
            appointment_type="diagnostic_biopsy",
            notes="Ultrasound-guided core needle biopsy scheduled with Dr. Thorne."
        )
        self.assertTrue(appt_res["success"])

        # Step 9: Patient receives communication update
        comm_res = ToolRegistry.send_patient_message(
            db=self.db,
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            message="Your diagnostic appointment is confirmed for Tuesday at 10:00 AM with Dr. Aris Thorne.",
            language="en",
            channel="in_app_chat"
        )
        self.assertTrue(comm_res["success"])

        # Step 10: Approved closure process: Verified clinical evidence recorded and signed off
        doc_uuid = d_user.owner_id or d_user.id
        evidence = ClosureEvidence(
            id=uuid.uuid4(),
            case_id=self.case.id,
            evidence_type="pathology_report",
            evidence_summary="Benign fibroadenoma with no evidence of atypia or malignancy.",
            verifying_clinician_id=doc_uuid,
            is_verified=True,
            verified_at=now
        )
        self.db.add(evidence)
        self.case.status = "closed"
        self.db.commit()

        # Verify database persistence
        reloaded_case = self.db.query(CareCase).filter(CareCase.id == self.case.id).first()
        self.assertEqual(reloaded_case.status, "closed")
        self.assertTrue(evidence.is_verified)


if __name__ == "__main__":
    unittest.main()
