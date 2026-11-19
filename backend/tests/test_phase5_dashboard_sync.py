"""
CareBridge Phase 5 Acceptance Test Suite: Dashboard Synchronization

Acceptance Criteria:
1. Scenario A steps 11 to 16 pass; stages update only after evidence.
2. Test: refresh mid-workflow reproduces the same state from persisted data.
3. Test: patient, doctor, and coordinator views of one case agree (same records, role-filtered).
4. Test: no stage is complete while a required task is pending.
5. Test: cross-patient and cross-doctor leakage checks on every dashboard endpoint.
6. Test: deliberately corrupted projection is detected and rebuilt by the consistency checker (dry-run first, reconciliation task created).
7. Multilingual & RTL: Arabic RTL and language selector (English, Arabic, Spanish; strictly no Tamil).
"""

import uuid
import unittest
from datetime import date, datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.patient import Patient
from app.models.screening import ScreeningResult
from app.models.care_case import CareCase, Task
from app.models.owner import CaseOwner
from app.models.user import User
from app.models.event_audit import CaseEvent, AuditLog
from app.models.notification import Notification
from app.models.appointment import Appointment
from app.models.case_lifecycle_stage import CaseLifecycleStage

from app.services.lifecycle_service import LifecycleService, LifecycleTransitionError
from app.services.task_service import TaskService
from app.services.dashboard_projection_service import DashboardProjectionService
from app.services.consistency_checker import ConsistencyCheckerService


class TestPhase5DashboardSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.session = self.SessionLocal()

        # 1. Create Primary Patient
        self.patient = Patient(
            id=uuid.uuid4(),
            mrn=f"MRN-P5-{uuid.uuid4().hex[:8]}",
            first_name="Meenakshi",
            last_name="Ramanathan",
            date_of_birth=date(1982, 4, 12),
            gender="female",
            phone=f"+1555{uuid.uuid4().hex[:7]}",
            preferred_language="en"
        )
        self.session.add(self.patient)

        # 2. Create Screening Result
        self.screening = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=self.patient.id,
            screening_type="Mammogram",
            finding_code="BI-RADS-4",
            finding_summary="Suspicious solid mass with microcalcifications in right breast.",
            test_date=datetime.now(timezone.utc) - timedelta(days=2),
            performing_facility="Clinic A - Women's Specialty Breast Center"
        )
        self.session.add(self.screening)

        # 3. Create Case Owners
        self.doctor_owner = CaseOwner(
            id=uuid.uuid4(),
            name="Dr. Aris Thorne, MD",
            role="doctor",
            specialty="breast_surgical_oncology",
            facility="Clinic A - Women's Specialty Breast Center",
            email=f"aris.thorne.{uuid.uuid4().hex}@carebridge.health",
            phone="+15551112222",
            is_active=True
        )
        self.other_doctor_owner = CaseOwner(
            id=uuid.uuid4(),
            name="Dr. Elena Rostova, MD",
            role="doctor",
            specialty="general_oncology",
            facility="Clinic B - Regional Oncology",
            email=f"elena.rostova.{uuid.uuid4().hex}@carebridge.health",
            phone="+15553334444",
            is_active=True
        )
        self.coordinator_owner = CaseOwner(
            id=uuid.uuid4(),
            name="Priya Nair, RN",
            role="care_coordinator",
            facility="Clinic A - Women's Specialty Breast Center",
            email=f"priya.nair.{uuid.uuid4().hex}@carebridge.health",
            phone="+15555556666",
            is_active=True
        )
        self.session.add_all([self.doctor_owner, self.other_doctor_owner, self.coordinator_owner])

        # 4. Create Users for Auth
        self.patient_user = User(
            id=uuid.uuid4(),
            email=f"patient.{uuid.uuid4().hex}@carebridge.health",
            password_hash="mocked_hash",
            full_name="Meenakshi Ramanathan",
            role="patient",
            patient_id=self.patient.id,
            is_active=True
        )
        self.doctor_user = User(
            id=uuid.uuid4(),
            email=self.doctor_owner.email,
            password_hash="mocked_hash",
            full_name=self.doctor_owner.name,
            role="doctor",
            owner_id=self.doctor_owner.id,
            is_active=True
        )
        self.other_doctor_user = User(
            id=uuid.uuid4(),
            email=self.other_doctor_owner.email,
            password_hash="mocked_hash",
            full_name=self.other_doctor_owner.name,
            role="doctor",
            owner_id=self.other_doctor_owner.id,
            is_active=True
        )
        self.coordinator_user = User(
            id=uuid.uuid4(),
            email=self.coordinator_owner.email,
            password_hash="mocked_hash",
            full_name=self.coordinator_owner.name,
            role="care_coordinator",
            owner_id=self.coordinator_owner.id,
            is_active=True
        )
        self.session.add_all([self.patient_user, self.doctor_user, self.other_doctor_user, self.coordinator_user])

        # 5. Create Care Case
        self.case = CareCase(
            id=uuid.uuid4(),
            case_number=f"CASE-P5-{uuid.uuid4().hex[:6]}",
            patient_id=self.patient.id,
            screening_result_id=self.screening.id,
            current_owner_id=self.doctor_owner.id,
            status="active",
            priority="urgent",
            sla_deadline=datetime.now(timezone.utc) + timedelta(days=5),
            case_context={}
        )
        self.session.add(self.case)
        self.session.flush()

        # Initialize 14 stages
        LifecycleService.initialize_lifecycle(self.case, self.screening, self.patient, db=self.session)
        self.session.commit()

    def tearDown(self):
        self.session.rollback()
        self.session.close()

    def _advance_through_stage(self, stage_num: int):
        """Helper to advance case sequentially through initial stages up to stage_num."""
        # Stage 1: completed at init
        if stage_num >= 2:
            LifecycleService.advance_stage(
                self.session, self.case.id, 2, "system", "SYSTEM",
                evidence={"evidence_type": "diagnostic_imaging_result", "evidence_id": str(self.screening.id)}
            )
        if stage_num >= 3:
            LifecycleService.advance_stage(
                self.session, self.case.id, 3, "care_coordinator", str(self.coordinator_owner.id),
                evidence={"evidence_type": "patient_notification_log", "evidence_id": "notif-001"}
            )
        if stage_num >= 4:
            LifecycleService.advance_stage(
                self.session, self.case.id, 4, "care_coordinator", str(self.coordinator_owner.id),
                evidence={"evidence_type": "patient_understanding_ack", "evidence_id": "ack-001"}
            )
        if stage_num >= 5:
            LifecycleService.advance_stage(
                self.session, self.case.id, 5, "doctor", str(self.doctor_owner.id),
                evidence={"evidence_type": "clinical_review_record", "evidence_id": "rev-001"}
            )
        if stage_num >= 6:
            LifecycleService.advance_stage(
                self.session, self.case.id, 6, "doctor", str(self.doctor_owner.id),
                evidence={"evidence_type": "clinical_confirmation_note", "evidence_id": "conf-001"}
            )
        if stage_num >= 7:
            LifecycleService.advance_stage(
                self.session, self.case.id, 7, "care_coordinator", str(self.coordinator_owner.id),
                evidence={"evidence_type": "referral_order", "evidence_id": "ref-001"}
            )
        if stage_num >= 8:
            LifecycleService.advance_stage(
                self.session, self.case.id, 8, "care_coordinator", str(self.coordinator_owner.id),
                evidence={"evidence_type": "referral_acceptance_ack", "evidence_id": "ref-ack-001"}
            )
        if stage_num >= 9:
            LifecycleService.advance_stage(
                self.session, self.case.id, 9, "care_coordinator", str(self.coordinator_owner.id),
                evidence={"evidence_type": "appointment_booking", "evidence_id": "appt-001"}
            )
        if stage_num >= 10:
            LifecycleService.advance_stage(
                self.session, self.case.id, 10, "doctor", str(self.doctor_owner.id),
                evidence={"evidence_type": "consultation_report", "evidence_id": "consult-001"}
            )
        self.session.commit()

    def test_01_scenario_a_steps_11_to_16_evidence_driven(self):
        """
        Scenario A steps 11 to 16:
        Stages 11 (Treatment Monitoring), 12 (Follow-up), 13 (Documentation), 14 (Closure).
        Stages update ONLY after verified evidence; Stage 14 requires doctor sign-off.
        Steps 15-16 verify read model consistency and post-closure patient audit.
        """
        self._advance_through_stage(10)

        # -------------------------------------------------------------
        # Step 11: Treatment Monitoring
        # -------------------------------------------------------------
        # Attempting without evidence must fail
        with self.assertRaises(LifecycleTransitionError):
            LifecycleService.advance_stage(
                self.session, self.case.id, 11, "care_coordinator", str(self.coordinator_owner.id),
                evidence=None
            )

        # Advance Stage 11 with verified treatment monitoring log
        res11 = LifecycleService.advance_stage(
            self.session, self.case.id, 11, "care_coordinator", str(self.coordinator_owner.id),
            evidence={"evidence_type": "treatment_monitoring_log", "evidence_id": "treat-log-01", "vital_signs": "stable"}
        )
        self.assertEqual(res11["stage_number"], 11)
        self.assertEqual(res11["status"], "completed")

        # -------------------------------------------------------------
        # Step 12: Follow-up
        # -------------------------------------------------------------
        # Attempting without evidence must fail
        with self.assertRaises(LifecycleTransitionError):
            LifecycleService.advance_stage(
                self.session, self.case.id, 12, "doctor", str(self.doctor_owner.id),
                evidence={}
            )

        # Advance Stage 12 with verified follow-up outcome
        res12 = LifecycleService.advance_stage(
            self.session, self.case.id, 12, "doctor", str(self.doctor_owner.id),
            evidence={"evidence_type": "followup_outcome", "evidence_id": "followup-01", "findings": "post-biopsy healing normal"}
        )
        self.assertEqual(res12["stage_number"], 12)
        self.assertEqual(res12["status"], "completed")

        # -------------------------------------------------------------
        # Step 13: Documentation
        # -------------------------------------------------------------
        # Attempting without evidence must fail
        with self.assertRaises(LifecycleTransitionError):
            LifecycleService.advance_stage(
                self.session, self.case.id, 13, "care_coordinator", str(self.coordinator_owner.id),
                evidence=None
            )

        # Advance Stage 13 with verified documentation checklist
        res13 = LifecycleService.advance_stage(
            self.session, self.case.id, 13, "care_coordinator", str(self.coordinator_owner.id),
            evidence={"evidence_type": "documentation_checklist", "evidence_id": "doc-checklist-01", "checklist_complete": True}
        )
        self.assertEqual(res13["stage_number"], 13)
        self.assertEqual(res13["status"], "completed")

        # -------------------------------------------------------------
        # Step 14: Closure (Doctor Sign-Off Only)
        # -------------------------------------------------------------
        # Attempting closure by coordinator must fail
        with self.assertRaises(LifecycleTransitionError):
            LifecycleService.advance_stage(
                self.session, self.case.id, 14, "care_coordinator", str(self.coordinator_owner.id),
                evidence={"closure_evidence_type": "doctor_signoff", "doctor_signoff": True}
            )

        # Advance Stage 14 with doctor sign-off
        res14 = LifecycleService.advance_stage(
            self.session, self.case.id, 14, "doctor", str(self.doctor_owner.id),
            evidence={
                "closure_evidence_type": "clinical_closure_summary",
                "closure_evidence_id": "closure-eval-01",
                "doctor_signoff": True,
                "clinical_rationale": "Histology concordant benign pathology. Return to routine annual mammography."
            }
        )
        self.assertEqual(res14["stage_number"], 14)
        self.assertEqual(res14["status"], "completed")

        # -------------------------------------------------------------
        # Step 15: Read Model & Projection Verification
        # -------------------------------------------------------------
        projection = DashboardProjectionService.get_patient_dashboard(self.session, self.patient.id)
        self.assertEqual(projection["current_case"]["status"], "closed")
        self.assertEqual(projection["lifecycle"]["current_stage_number"], 14)
        self.assertTrue(all(s["status"] == "completed" for s in projection["lifecycle"]["stages"]))

        # -------------------------------------------------------------
        # Step 16: Audit Trail & Post-Closure Verification
        # -------------------------------------------------------------
        events = self.session.query(CaseEvent).filter(CaseEvent.case_id == self.case.id).all()
        stage_names = [e.event_type for e in events]
        self.assertIn("stage_advanced_to_14", stage_names)

    def test_02_no_stage_complete_while_required_task_pending(self):
        """
        A stage CANNOT be marked complete if an active/pending required task
        for that stage is unresolved.
        """
        self._advance_through_stage(4)

        # Create an operational task assigned to doctor for Stage 5 review
        review_task = TaskService.create_task(
            self.session,
            patient_id=self.patient.id,
            case_id=self.case.id,
            task_type="clinical_review",
            responsible_role="doctor",
            assigned_to_id=str(self.doctor_owner.id),
            priority="urgent",
            task_metadata={"stage_number": 5}
        )
        self.assertEqual(review_task.status, "pending")

        # Attempting to complete Stage 5 while review_task is pending must fail
        with self.assertRaises(LifecycleTransitionError) as ctx:
            LifecycleService.advance_stage(
                self.session, self.case.id, 5, "doctor", str(self.doctor_owner.id),
                evidence={"evidence_type": "clinical_review_record", "evidence_id": "rev-999"}
            )
        self.assertIn("pending", str(ctx.exception).lower())

        # Complete the blocking task with evidence
        TaskService.complete_task(
            self.session,
            task_id=review_task.id,
            completed_by_id=str(self.doctor_owner.id),
            completed_by_role="doctor",
            evidence={"review_notes": "Diagnostic imaging concordant with ultrasound recommendation."}
        )

        # Now Stage 5 can be advanced successfully
        res = LifecycleService.advance_stage(
            self.session, self.case.id, 5, "doctor", str(self.doctor_owner.id),
            evidence={"evidence_type": "clinical_review_record", "evidence_id": "rev-999"}
        )
        self.assertEqual(res["status"], "completed")

    def test_03_refresh_mid_workflow_reproduces_same_state(self):
        """
        Page refresh / re-query mid-workflow reconstructs the exact same
        authoritative state from PostgreSQL without drift.
        """
        self._advance_through_stage(9)

        # Snapshot state from first projection query
        initial_patient_view = DashboardProjectionService.get_patient_dashboard(self.session, self.patient.id)
        initial_doctor_view = DashboardProjectionService.get_doctor_dashboard(self.session, self.doctor_owner.id)
        initial_coord_view = DashboardProjectionService.get_coordinator_dashboard(self.session)

        # Simulate page refresh by closing and opening a brand new database session
        self.session.commit()
        refreshed_session = self.SessionLocal()
        try:
            refreshed_patient_view = DashboardProjectionService.get_patient_dashboard(refreshed_session, self.patient.id)
            refreshed_doctor_view = DashboardProjectionService.get_doctor_dashboard(refreshed_session, self.doctor_owner.id)
            refreshed_coord_view = DashboardProjectionService.get_coordinator_dashboard(refreshed_session)

            # Assert identical state across refreshes
            self.assertEqual(
                refreshed_patient_view["lifecycle"]["current_stage_number"],
                initial_patient_view["lifecycle"]["current_stage_number"]
            )
            self.assertEqual(
                refreshed_patient_view["current_case"]["id"],
                initial_patient_view["current_case"]["id"]
            )
            self.assertEqual(
                len(refreshed_patient_view["lifecycle"]["stages"]),
                len(initial_patient_view["lifecycle"]["stages"])
            )
            self.assertEqual(
                len(refreshed_doctor_view["assigned_patients"]),
                len(initial_doctor_view["assigned_patients"])
            )
            self.assertEqual(
                len(refreshed_coord_view["appointments"]),
                len(initial_coord_view["appointments"])
            )
        finally:
            refreshed_session.close()

    def test_04_cross_role_view_agreement(self):
        """
        Patient, Doctor, and Coordinator views of the same case agree on authoritative records,
        while maintaining role-appropriate filtering.
        """
        self._advance_through_stage(9)

        # Add an appointment
        appt = Appointment(
            id=uuid.uuid4(),
            case_id=self.case.id,
            patient_id=self.patient.id,
            facility=self.doctor_owner.facility,
            provider_name=self.doctor_owner.name,
            appointment_type="diagnostic_biopsy",
            scheduled_time=datetime.now(timezone.utc) + timedelta(days=2),
            status="scheduled"
        )
        self.session.add(appt)
        self.session.commit()

        patient_view = DashboardProjectionService.get_patient_dashboard(self.session, self.patient.id)
        doctor_view = DashboardProjectionService.get_doctor_dashboard(self.session, self.doctor_owner.id)
        coord_view = DashboardProjectionService.get_coordinator_dashboard(self.session)

        # Doctor view has this case in assigned_patients
        doc_case = next((c for c in doctor_view["assigned_patients"] if c["id"] == str(self.case.id)), None)
        self.assertIsNotNone(doc_case)
        self.assertEqual(doc_case["patient_name"], f"{self.patient.first_name} {self.patient.last_name}")

        # All 3 views agree on the core case attributes
        self.assertEqual(patient_view["current_case"]["id"], str(self.case.id))
        self.assertEqual(patient_view["current_case"]["status"], "scheduled")
        self.assertEqual(doc_case["status"], "scheduled")

        # Coordinator view has this appointment
        coord_appt = next((a for a in coord_view["appointments"] if a["case_id"] == str(self.case.id)), None)
        self.assertIsNotNone(coord_appt)
        self.assertEqual(coord_appt["provider_name"], self.doctor_owner.name)

        # Patient view shows assigned doctor
        self.assertEqual(patient_view["doctor"]["name"], self.doctor_owner.name)

    def test_05_cross_tenant_and_cross_doctor_leakage(self):
        """
        Zero cross-patient and cross-doctor data leakage across dashboard projections.
        """
        # Create second patient & second doctor
        other_patient = Patient(
            id=uuid.uuid4(),
            mrn=f"MRN-OTHER-{uuid.uuid4().hex[:6]}",
            first_name="Jane",
            last_name="Doe",
            date_of_birth=date(1990, 1, 1),
            gender="female",
            phone="+15559998888",
            preferred_language="en"
        )
        self.session.add(other_patient)
        self.session.flush()

        other_screening = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=other_patient.id,
            screening_type="Mammogram",
            finding_code="BI-RADS-2",
            finding_summary="Benign findings.",
            test_date=datetime.now(timezone.utc) - timedelta(days=1),
            performing_facility="Clinic B - Regional Oncology"
        )
        self.session.add(other_screening)
        self.session.flush()

        other_case = CareCase(
            id=uuid.uuid4(),
            case_number=f"CASE-OTHER-{uuid.uuid4().hex[:6]}",
            patient_id=other_patient.id,
            screening_result_id=other_screening.id,
            current_owner_id=self.other_doctor_owner.id,
            status="active",
            priority="routine",
            sla_deadline=datetime.now(timezone.utc) + timedelta(days=10),
            case_context={}
        )
        self.session.add(other_case)
        self.session.commit()

        # 1. Patient A cannot see Patient B's case or profile
        patient_a_view = DashboardProjectionService.get_patient_dashboard(self.session, self.patient.id)
        self.assertNotEqual(patient_a_view["profile"]["mrn"], other_patient.mrn)
        self.assertEqual(patient_a_view["current_case"]["id"], str(self.case.id))

        # 2. Doctor A cannot see Doctor B's assigned cases
        doctor_a_view = DashboardProjectionService.get_doctor_dashboard(self.session, self.doctor_owner.id)
        doc_a_case_ids = [c["id"] for c in doctor_a_view["assigned_patients"]]
        self.assertIn(str(self.case.id), doc_a_case_ids)
        self.assertNotIn(str(other_case.id), doc_a_case_ids)

        # 3. Doctor B cannot see Doctor A's assigned cases
        doctor_b_view = DashboardProjectionService.get_doctor_dashboard(self.session, self.other_doctor_owner.id)
        doc_b_case_ids = [c["id"] for c in doctor_b_view["assigned_patients"]]
        self.assertIn(str(other_case.id), doc_b_case_ids)
        self.assertNotIn(str(self.case.id), doc_b_case_ids)

    def test_06_corrupted_projection_detected_and_rebuilt_by_checker(self):
        """
        Consistency checker detects stale/corrupted projections (e.g. stage complete
        without evidence, or pending blocking task) and repairs them safely.
        Dry-run reports violations without modifying; apply reverts stage and creates reconciliation task.
        """
        self._advance_through_stage(4)

        # Deliberately corrupt stage 5: Mark complete directly in DB without any evidence
        corrupted_stage = self.session.query(CaseLifecycleStage).filter(
            CaseLifecycleStage.case_id == self.case.id,
            CaseLifecycleStage.stage_number == 5
        ).first()
        corrupted_stage.status = "completed"
        corrupted_stage.evidence_data = {}
        corrupted_stage.evidence_id = None
        self.session.commit()

        # 1. Dry run detects corruption but does NOT modify database
        dry_result = ConsistencyCheckerService.audit_cases(self.session, dry_run=True)
        self.assertGreater(dry_result["corrupted_count"], 0)
        self.assertEqual(dry_result["dry_run"], True)

        # Verify DB is untouched during dry-run
        rechecked_stage = self.session.query(CaseLifecycleStage).filter(
            CaseLifecycleStage.case_id == self.case.id,
            CaseLifecycleStage.stage_number == 5
        ).first()
        self.assertEqual(rechecked_stage.status, "completed")

        # 2. Apply run safely repairs corrupted stage and creates a reconciliation task
        apply_result = ConsistencyCheckerService.audit_cases(self.session, dry_run=False)
        self.assertGreater(apply_result["repaired_count"], 0)

        # Verify stage has been reverted from completed to active/pending
        self.session.expire_all()
        repaired_stage = self.session.query(CaseLifecycleStage).filter(
            CaseLifecycleStage.case_id == self.case.id,
            CaseLifecycleStage.stage_number == 5
        ).first()
        self.assertIn(repaired_stage.status, ["pending", "active"])

        # Verify coordinator reconciliation task was generated
        reconciliation_task = self.session.query(Task).filter(
            Task.case_id == self.case.id,
            Task.task_type == "consistency_reconciliation"
        ).first()
        self.assertIsNotNone(reconciliation_task)
        self.assertEqual(reconciliation_task.responsible_role, "care_coordinator")
        self.assertEqual(reconciliation_task.priority, "urgent")

    def test_07_language_selector_and_rtl_arabic(self):
        """
        Multilingual & RTL verification:
        Supports English (en), Arabic (ar), and Spanish (es).
        Rejects Tamil (ta). Arabic payloads set RTL flag.
        """
        # Set patient language to Arabic
        self.patient.preferred_language = "ar"
        self.session.commit()

        projection = DashboardProjectionService.get_patient_dashboard(self.session, self.patient.id)
        self.assertEqual(projection["profile"]["language"], "ar")
        self.assertEqual(projection["profile"]["text_direction"], "rtl")
        self.assertTrue(projection["profile"]["is_rtl"])

        # Allowed languages check
        supported = DashboardProjectionService.get_supported_languages()
        self.assertIn("en", supported)
        self.assertIn("ar", supported)
        self.assertIn("es", supported)
        self.assertNotIn("ta", supported, "Tamil (ta) must not be included per prompt specifications!")

    def test_08_endpoint_authorization_and_openapi_routes(self):
        """
        Validates FastAPI endpoint security boundaries for all three dashboards:
        1. All dashboard routes registered in OpenAPI schema.
        2. Role-based isolation prevents cross-role access (HTTP 403).
        """
        from fastapi import HTTPException
        from app.main import app
        from app.core.security import UserPrincipal
        from app.api.v1.endpoints.dashboards import (
            get_patient_dashboard,
            get_doctor_dashboard,
            get_coordinator_dashboard,
            run_consistency_audit
        )

        schema = app.openapi()
        paths = schema["paths"]
        self.assertIn("/api/v1/dashboards/patient", paths)
        self.assertIn("/api/v1/dashboards/doctor", paths)
        self.assertIn("/api/v1/dashboards/coordinator", paths)
        self.assertIn("/api/v1/dashboards/consistency-check", paths)

        # 1. Patient accessing patient endpoint -> OK
        p_principal = UserPrincipal(
            user_id=str(self.patient_user.id),
            email=self.patient_user.email,
            role="patient",
            patient_id=str(self.patient.id)
        )
        res_p = get_patient_dashboard(current_user=p_principal, db=self.session)
        self.assertTrue(res_p.success)
        self.assertEqual(res_p.data["profile"]["mrn"], self.patient.mrn)

        # 2. Doctor attempting to access patient endpoint -> 403 Forbidden
        doc_principal = UserPrincipal(
            user_id=str(self.doctor_user.id),
            email=self.doctor_user.email,
            role="doctor",
            owner_id=str(self.doctor_owner.id)
        )
        with self.assertRaises(HTTPException) as ctx:
            get_patient_dashboard(current_user=doc_principal, db=self.session)
        self.assertEqual(ctx.exception.status_code, 403)

        # 3. Doctor accessing doctor endpoint -> OK
        res_d = get_doctor_dashboard(current_user=doc_principal, db=self.session)
        self.assertTrue(res_d.success)
        self.assertEqual(res_d.data["doctor"]["name"], self.doctor_owner.name)

        # 4. Patient attempting to access doctor endpoint -> 403 Forbidden
        with self.assertRaises(HTTPException) as ctx:
            get_doctor_dashboard(current_user=p_principal, db=self.session)
        self.assertEqual(ctx.exception.status_code, 403)

        # 5. Coordinator accessing coordinator endpoint -> OK
        coord_principal = UserPrincipal(
            user_id=str(self.coordinator_user.id),
            email=self.coordinator_user.email,
            role="care_coordinator",
            owner_id=str(self.coordinator_owner.id)
        )
        res_c = get_coordinator_dashboard(current_user=coord_principal, db=self.session)
        self.assertTrue(res_c.success)
        self.assertIn("sla_monitoring", res_c.data)

        # 6. Doctor attempting to access coordinator endpoint -> 403 Forbidden
        with self.assertRaises(HTTPException) as ctx:
            get_coordinator_dashboard(current_user=doc_principal, db=self.session)
        self.assertEqual(ctx.exception.status_code, 403)

        # 7. Patient attempting to run consistency audit -> 403 Forbidden
        with self.assertRaises(HTTPException) as ctx:
            run_consistency_audit(dry_run=True, current_user=p_principal, db=self.session)
        self.assertEqual(ctx.exception.status_code, 403)

        # 8. Coordinator running consistency audit -> OK
        res_audit = run_consistency_audit(dry_run=True, current_user=coord_principal, db=self.session)
        self.assertTrue(res_audit.success)
        self.assertTrue(res_audit.data["dry_run"])


if __name__ == "__main__":
    unittest.main()
