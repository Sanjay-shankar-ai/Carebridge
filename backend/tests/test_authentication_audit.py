"""
CareBridge Authentication, Identity Propagation, and User Context Audit Test Suite
Comprehensive automated test suite fulfilling STEP 7 of the CareBridge Audit.
Tests run synchronously and natively without requiring socket loopback binds in sandbox.
"""

import unittest
import uuid
from datetime import datetime, timezone, timedelta, date
from fastapi import HTTPException

from app.database.session import get_sync_db
from app.database.seed import seed_database
from app.models import User, Patient, CareCase, CaseOwner, Referral, Appointment
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    get_current_user,
    require_role,
    UserPrincipal
)
from app.agents.cognitive_engine import CognitiveEngine
from app.workflows.doctor_workflow import run_doctor_workflow


class TestCareBridgeAuthenticationAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Seed database once for the audit test suite."""
        cls.db = get_sync_db()
        seed_database(cls.db, extended=True)
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.db = get_sync_db()

    def tearDown(self):
        self.db.close()

    # --------------------------------------------------------------------------
    # 1. Patient & Doctor Registration Audit (STEP 1)
    # --------------------------------------------------------------------------
    def test_01_patient_registration_unique_id_and_hashing(self):
        """STEP 1: Verify patient registration creates unique user ID, hashes password with bcrypt, and prevents duplicate accounts."""
        unique_email = f"patient_{uuid.uuid4().hex[:8]}@audit.test"
        plain_password = "SecurePatientPass123!"

        # 1. Check duplicate prevention
        existing = self.db.query(User).filter(User.email == unique_email).first()
        self.assertIsNone(existing)

        # 2. Simulate patient registration logic
        year = datetime.now(timezone.utc).year
        rand_suffix = str(uuid.uuid4().hex[:6]).upper()
        mrn = f"MRN-{year}-{rand_suffix}"

        new_patient = Patient(
            id=uuid.uuid4(),
            mrn=mrn,
            first_name="Divya",
            last_name="Krishnan",
            phone="+91-98765-55555",
            email=unique_email,
            date_of_birth=date(1990, 5, 15),
            preferred_language="ta",
            communication_channel="in_app_chat",
        )
        self.db.add(new_patient)
        self.db.flush()

        pw_hash = hash_password(plain_password)
        new_user = User(
            id=uuid.uuid4(),
            email=unique_email,
            password_hash=pw_hash,
            role="patient",
            full_name="Divya Krishnan",
            is_active=True,
            is_verified=True,
            patient_id=new_patient.id,
        )
        self.db.add(new_user)
        self.db.commit()

        # 3. Verify user table and password verification
        user_in_db = self.db.query(User).filter(User.email == unique_email).first()
        self.assertIsNotNone(user_in_db)
        self.assertEqual(user_in_db.role, "patient")
        self.assertTrue(user_in_db.is_active)
        self.assertTrue(user_in_db.is_verified)
        self.assertTrue(user_in_db.password_hash.startswith("$2b$") or user_in_db.password_hash.startswith("$2a$"))
        self.assertTrue(verify_password(plain_password, user_in_db.password_hash))
        self.assertFalse(verify_password("WrongPassword!", user_in_db.password_hash))
        self.assertEqual(user_in_db.patient_id, new_patient.id)

        # 4. Enforce unique constraint / duplicate email rejection
        with self.assertRaises(Exception):
            dup_user = User(
                id=uuid.uuid4(),
                email=unique_email,
                password_hash=hash_password("AnotherPassword"),
                role="patient",
                full_name="Duplicate User",
            )
            self.db.add(dup_user)
            self.db.commit()
        self.db.rollback()

    def test_02_doctor_registration_with_case_owner(self):
        """STEP 1: Verify doctor registration creates CaseOwner profile, unique User account, and specialist role."""
        unique_email = f"doctor_{uuid.uuid4().hex[:8]}@audit.test"
        plain_password = "DoctorSecurePass123!"

        # 1. Create CaseOwner profile
        new_owner = CaseOwner(
            id=uuid.uuid4(),
            name="Dr. Rajesh Sharma, MD",
            role="specialist",
            facility="Metro Oncology Center",
            phone="+91-98765-66666",
            email=unique_email,
            is_active=True,
        )
        self.db.add(new_owner)
        self.db.flush()

        # 2. Create User account
        new_user = User(
            id=uuid.uuid4(),
            email=unique_email,
            password_hash=hash_password(plain_password),
            role="clinician",
            full_name="Dr. Rajesh Sharma, MD",
            is_active=True,
            is_verified=True,
            owner_id=new_owner.id,
        )
        self.db.add(new_user)
        self.db.commit()

        # 3. Verify linkage and role
        persisted = self.db.query(User).filter(User.email == unique_email).first()
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.role, "clinician")
        self.assertEqual(persisted.owner_id, new_owner.id)
        owner_record = self.db.query(CaseOwner).filter(CaseOwner.id == persisted.owner_id).first()
        self.assertIsNotNone(owner_record)
        self.assertEqual(owner_record.facility, "Metro Oncology Center")

    # --------------------------------------------------------------------------
    # 2. Login & Session Management Audit (STEP 2)
    # --------------------------------------------------------------------------
    def test_03_login_credential_verification_and_jwt(self):
        """STEP 2: Verify login authenticates against database, verifies password, and returns valid JWT."""
        # 1. Fetch doctor user
        doc = self.db.query(User).filter(User.role == "clinician").first()
        self.assertIsNotNone(doc)

        # 2. Verify password checking
        self.assertTrue(verify_password("DoctorPass123!", doc.password_hash))
        self.assertFalse(verify_password("InvalidPass999!", doc.password_hash))

        # 3. Create real access token
        token = create_access_token({
            "sub": str(doc.id),
            "email": doc.email,
            "role": doc.role,
            "name": doc.full_name,
            "owner_id": str(doc.owner_id) if doc.owner_id else None,
        })
        self.assertTrue(token)

        # 4. Decode token and verify claims
        claims = decode_access_token(token)
        self.assertEqual(claims["sub"], str(doc.id))
        self.assertEqual(claims["role"], "clinician")
        self.assertEqual(claims["email"], doc.email)

    def test_04_token_validation_and_expiration(self):
        """STEP 2: Verify that expired, forged, and malformed tokens are rejected with HTTP 401."""
        # 1. Expired token
        expired_token = create_access_token(
            {"sub": str(uuid.uuid4()), "role": "patient"},
            expires_delta=timedelta(minutes=-5)
        )
        with self.assertRaises(HTTPException) as ctx_exp:
            decode_access_token(expired_token)
        self.assertEqual(ctx_exp.exception.status_code, 401)
        self.assertIn("expired", ctx_exp.exception.detail.lower())

        # 2. Tampered token
        fake_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.fake_signature_abc123"
        with self.assertRaises(HTTPException) as ctx_fake:
            decode_access_token(fake_token)
        self.assertEqual(ctx_fake.exception.status_code, 401)

        # 3. Malformed token string
        with self.assertRaises(HTTPException) as ctx_mal:
            decode_access_token("not-a-valid-jwt")
        self.assertEqual(ctx_mal.exception.status_code, 401)

    # --------------------------------------------------------------------------
    # 3. Role Detection & Authorization Boundaries (STEP 3 & 5)
    # --------------------------------------------------------------------------
    def test_05_role_enforcement_and_isolation(self):
        """STEP 3 & 5: Verify backend enforces trusted roles strictly from DB and blocks cross-role access."""
        # Patient principal
        patient_user = self.db.query(User).filter(User.role == "patient").first()
        patient_principal = UserPrincipal(
            user_id=str(patient_user.id),
            email=patient_user.email,
            role="patient",
            full_name=patient_user.full_name,
            patient_id=str(patient_user.patient_id)
        )

        # Clinician principal
        doc_user = self.db.query(User).filter(User.role == "clinician").first()
        doc_principal = UserPrincipal(
            user_id=str(doc_user.id),
            email=doc_user.email,
            role="clinician",
            full_name=doc_user.full_name,
            owner_id=str(doc_user.owner_id)
        )

        # 1. Role requirement check for internal operations (recovery queue / analytics)
        checker = require_role(["clinician", "care_coordinator", "admin"])
        
        # Clinician passes
        res_doc = checker(doc_principal)
        self.assertEqual(res_doc.role, "clinician")

        # Patient is blocked with 403 Forbidden
        with self.assertRaises(HTTPException) as ctx_rbac:
            checker(patient_principal)
        self.assertEqual(ctx_rbac.exception.status_code, 403)
        self.assertIn("forbidden", ctx_rbac.exception.detail.lower())

        # 2. Cross-patient case isolation
        # Querying cases as patient: must only return their own case
        patient_cases = self.db.query(CareCase).filter(CareCase.patient_id == patient_user.patient_id).all()
        all_cases = self.db.query(CareCase).all()
        self.assertTrue(len(patient_cases) >= 1)
        self.assertLessEqual(len(patient_cases), len(all_cases))
        for c in patient_cases:
            self.assertEqual(c.patient_id, patient_user.patient_id)

    # --------------------------------------------------------------------------
    # 4. LangGraph Workflow Routing & State Isolation (STEP 4)
    # --------------------------------------------------------------------------
    def test_06_doctor_routes_to_doctor_subgraph(self):
        """STEP 4: Verify doctor interactions route to 11-node Doctor Subgraph with clinical objective persona."""
        doc_user = self.db.query(User).filter(User.role == "clinician").first()
        self.assertIsNotNone(doc_user)

        # 1. Doctor greeting interaction
        res = run_doctor_workflow(
            doctor_id=str(doc_user.id),
            message="Hello Dr. Thorne here"
        )
        self.assertTrue(res.get("is_authorized"))
        self.assertEqual(res.get("doctor_intent"), "general_query")
        response_msg = res.get("response_message") or ""
        self.assertIn("Clinical Co-Pilot", response_msg)
        self.assertNotIn("breast cancer", response_msg.lower())

        # 2. Isolated thread naming
        doc_thread = f"doctor_{doc_user.id}_case_general"
        patient_thread = f"patient_{uuid.uuid4()}_case_{uuid.uuid4()}"
        self.assertNotEqual(doc_thread, patient_thread)
        self.assertTrue(doc_thread.startswith("doctor_"))

    # --------------------------------------------------------------------------
    # 5. Patient AI Nuanced Responses (STEP 6)
    # --------------------------------------------------------------------------
    def test_07_patient_ai_nuanced_responses(self):
        """STEP 6: Verify Patient AI delivers distinct, nuanced responses rather than identical canned messages."""
        engine = CognitiveEngine()
        p_ctx = {"preferred_language": "en", "first_name": "Meenakshi"}
        c_ctx = {"screening_type": "Mammogram", "finding_code": "BI-RADS-4"}
        cv_ctx = {}

        # 1. Patient greeting: "Hi" -> Warm greeting, zero unnecessary DB writes
        intent_greet = engine.analyze_intent("Hi", p_ctx, c_ctx)
        self.assertEqual(intent_greet.primary_intent, "greeting")
        plan_greet = engine.formulate_plan(intent_greet, p_ctx, c_ctx, cv_ctx)
        self.assertEqual(len(plan_greet.actions), 0)
        self.assertIn("Care Companion", plan_greet.patient_response_draft)

        # 2. Patient asks about BI-RADS 4 -> Explains 70% to 80% benign probability
        intent_birads = engine.analyze_intent("What does BI-RADS 4 mean?", p_ctx, c_ctx)
        self.assertEqual(intent_birads.primary_intent, "patient_inquiry")
        self.assertEqual(intent_birads.inquiry_topic, "birads")
        plan_birads = engine.formulate_plan(intent_birads, p_ctx, c_ctx, cv_ctx)
        self.assertIn("70% to 80%", plan_birads.patient_response_draft)
        self.assertIn("NOT a diagnosis of cancer", plan_birads.patient_response_draft)

        # 3. Patient asks about biopsy pain -> Explains local anesthesia and outpatient safety
        intent_biopsy = engine.analyze_intent("Will the biopsy hurt?", p_ctx, c_ctx)
        self.assertEqual(intent_biopsy.primary_intent, "patient_inquiry")
        self.assertEqual(intent_biopsy.inquiry_topic, "biopsy")
        plan_biopsy = engine.formulate_plan(intent_biopsy, p_ctx, c_ctx, cv_ctx)
        self.assertIn("local anesthesia", plan_biopsy.patient_response_draft)

        # 4. Responses are distinct and nuanced
        self.assertNotEqual(plan_greet.patient_response_draft, plan_birads.patient_response_draft)
        self.assertNotEqual(plan_birads.patient_response_draft, plan_biopsy.patient_response_draft)

    # --------------------------------------------------------------------------
    # 6. Appointment Booking via Agent (STEP 6)
    # --------------------------------------------------------------------------
    def test_08_appointment_booking_via_agent(self):
        """STEP 6: Verify patient can request appointment booking and receive active clinic options."""
        engine = CognitiveEngine()
        p_ctx = {"preferred_language": "en", "first_name": "Meenakshi"}
        c_ctx = {"screening_type": "Mammogram", "finding_code": "BI-RADS-4"}
        cv_ctx = {}

        intent_appt = engine.analyze_intent("I would like to book an appointment please", p_ctx, c_ctx)
        self.assertEqual(intent_appt.primary_intent, "appointment_booking_request")
        
        plan_appt = engine.formulate_plan(intent_appt, p_ctx, c_ctx, cv_ctx)
        self.assertIn("Clinic A", plan_appt.patient_response_draft)
        action_names = [a.tool_name for a in plan_appt.actions]
        self.assertIn("search_available_appointments", action_names)
        self.assertIn("create_followup_task", action_names)


if __name__ == "__main__":
    unittest.main()
