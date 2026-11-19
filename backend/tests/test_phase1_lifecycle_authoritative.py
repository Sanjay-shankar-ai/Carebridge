"""
CareBridge Phase 1 Test Suite: Authoritative Database State & Unified Lifecycle Workflow
Verifies acceptance criteria for:
1. Strict 14-stage explicit transition table and role-based / evidence-based guards
2. Authoritative relational lifecycle stages table (case_lifecycle_stages)
3. Appointment 10-state machine with versioned dual-confirmation & double-booking prevention
4. Doctor allocation with clinical/specialty eligibility before workload ranking
5. Referral service with doctor clinical rationale distinct from AI educational text and patient decision tracking
6. Scenario D: Full sequential 14-stage journey with real evidence records
"""

import uuid
import unittest
from datetime import date, datetime, timezone, timedelta
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.patient import Patient
from app.models.screening import ScreeningResult
from app.models.care_case import CareCase, Task
from app.models.owner import CaseOwner
from app.models.appointment import Appointment
from app.models.referral import Referral
from app.models.closure import ClosureEvidence
from app.models.doctor_assignment import DoctorAssignment
from app.models.notification import Notification

from app.services.lifecycle_service import (
    LifecycleService,
    LifecycleTransitionError,
    LIFECYCLE_TRANSITIONS,
)
from app.services.appointment_service import (
    AppointmentService,
    AppointmentConflictError,
    AppointmentClosedCaseError,
    AppointmentConfirmationError,
)
from app.services.referral_service import ReferralService
from app.services.doctor_allocation_service import DoctorAllocationService


class TestPhase1LifecycleAuthoritative(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.session = self.SessionLocal()
        # Create base test records
        self.patient = Patient(
            id=uuid.uuid4(),
            mrn=f"MRN-PH1-{uuid.uuid4().hex[:6]}",
            first_name="Priya",
            last_name="Nair",
            date_of_birth=date(1984, 5, 12),
            gender="female",
            preferred_language="en",
            communication_channel="in_app_chat",
            phone="+91-9876543210",
            email="priya.nair@example.com"
        )
        self.session.add(self.patient)

        # Attending Doctor
        self.doctor_owner = CaseOwner(
            id=uuid.uuid4(),
            name="Dr. Sundaram",
            role="doctor",
            specialty="Diagnostic Radiology",
            facility="CareBridge Specialty Hub",
            email=f"sundaram_{uuid.uuid4().hex[:6]}@example.com",
            is_active=True,
            max_workload=10
        )
        self.session.add(self.doctor_owner)

        # Care Coordinator
        self.coordinator_owner = CaseOwner(
            id=uuid.uuid4(),
            name="Ananya Coordinator",
            role="care_coordinator",
            facility="CareBridge Central",
            email=f"ananya_{uuid.uuid4().hex[:6]}@example.com",
            is_active=True,
            max_workload=25
        )
        self.session.add(self.coordinator_owner)

        # Screening Result
        self.screening = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=self.patient.id,
            screening_type="Mammogram",
            test_date=datetime.now(timezone.utc) - timedelta(days=2),
            finding_code="BI-RADS-4",
            finding_summary="Suspicious microcalcifications in left upper quadrant.",
            urgency_level="urgent",
            performing_facility="CareBridge Imaging Center",
            raw_report_data={"birads_score": 4, "density": "heterogeneously dense", "status": "finalized"}
        )
        self.session.add(self.screening)

        # Care Case
        self.case = CareCase(
            id=uuid.uuid4(),
            case_number=f"CASE-PH1-{uuid.uuid4().hex[:6]}",
            patient_id=self.patient.id,
            screening_result_id=self.screening.id,
            current_owner_id=self.coordinator_owner.id,
            status="screening_completed",
            clinical_pathway="breast_cancer_diagnostic",
            priority="urgent",
            sla_start_time=datetime.now(timezone.utc),
            sla_deadline=datetime.now(timezone.utc) + timedelta(days=14),
            sla_status="normal",
            case_context={
                "inferred_barriers": [],
                "recovery_attempts": 0,
                "notes": []
            }
        )
        self.session.add(self.case)
        self.session.commit()

    def tearDown(self):
        for table in reversed(Base.metadata.sorted_tables):
            self.session.execute(table.delete())
        self.session.commit()
        self.session.close()

    # -------------------------------------------------------------------------
    # 1. Lifecycle Initialization & Stage 3 Non-Completion
    # -------------------------------------------------------------------------
    def test_01_initialize_lifecycle_leaves_stage_3_pending(self):
        """Stage 3 (PATIENT_NOTIFIED) must NOT be marked complete at case creation."""
        ctx = LifecycleService.initialize_lifecycle(self.session, self.case, self.screening, self.patient)
        stages = ctx.get("lifecycle_stages", [])
        
        st1 = next((s for s in stages if s["stage_number"] == 1), None)
        st2 = next((s for s in stages if s["stage_number"] == 2), None)
        st3 = next((s for s in stages if s["stage_number"] == 3), None)

        self.assertIsNotNone(st1)
        self.assertIsNotNone(st2)
        self.assertIsNotNone(st3)
        self.assertEqual(st1["status"], "completed")
        self.assertEqual(st2["status"], "completed")
        # Stage 3 MUST NOT be completed until actual notification is dispatched
        self.assertNotEqual(st3["status"], "completed", "Stage 3 cannot be pre-marked completed without notification evidence!")
        self.assertIn(st3["status"], ["pending", "active"])

    # -------------------------------------------------------------------------
    # 2. Strict Explicit Transition Table & Guardrails
    # -------------------------------------------------------------------------
    def test_02_invalid_stage_jump_is_rejected(self):
        """Jumping from Stage 2 directly to Stage 5 without intermediate stages must be rejected."""
        LifecycleService.initialize_lifecycle(self.session, self.case, self.screening, self.patient)
        self.session.commit()

        with self.assertRaises(LifecycleTransitionError):
            LifecycleService.advance_stage(
                self.session,
                case_id=self.case.id,
                stage_ident=5, # Attempting to jump directly to Stage 5
                actor_role="doctor",
                actor_id=str(self.doctor_owner.id),
                evidence={"review": "Doctor quick review"}
            )

    def test_03_unauthorized_role_for_stage_14_rejected(self):
        """Non-doctor (coordinator or patient) cannot sign off on Stage 14 (Closure)."""
        # Set case stages up to 13 completed
        LifecycleService.initialize_lifecycle(self.session, self.case, self.screening, self.patient)
        # Force stages 1-13 as completed for test setup
        for s in self.case.case_context.get("lifecycle_stages", []):
            if s["stage_number"] < 14:
                s["status"] = "completed"
        self.case.case_context["current_stage_number"] = 14
        self.session.commit()

        # Coordinator attempts closure
        with self.assertRaises(LifecycleTransitionError):
            LifecycleService.advance_stage(
                self.session,
                case_id=self.case.id,
                stage_ident=14,
                actor_role="care_coordinator",
                actor_id=str(self.coordinator_owner.id),
                evidence={"closure_evidence_type": "authorized_human_signoff"}
            )

    def test_04_stage_14_closure_requires_closure_evidence(self):
        """Stage 14 requires verified closure evidence and fails without it."""
        for s in self.case.case_context.get("lifecycle_stages", []):
            if s["stage_number"] < 14:
                s["status"] = "completed"
        self.case.case_context["current_stage_number"] = 14
        self.session.commit()

        # Doctor attempts closure without evidence
        with self.assertRaises(LifecycleTransitionError):
            LifecycleService.advance_stage(
                self.session,
                case_id=self.case.id,
                stage_ident=14,
                actor_role="doctor",
                actor_id=str(self.doctor_owner.id),
                evidence=None # Missing required evidence
            )

    # -------------------------------------------------------------------------
    # 3. Appointment State Machine & Dual Confirmation
    # -------------------------------------------------------------------------
    def test_05_appointment_requires_dual_confirmation_same_version(self):
        """CONFIRMED status requires both doctor and patient confirming the SAME version."""
        appt = AppointmentService.create_appointment_proposal(
            self.session,
            case_id=self.case.id,
            patient_id=self.patient.id,
            facility="CareBridge Specialty Hub",
            provider_name="Dr. Sundaram",
            appointment_type="consultation",
            scheduled_time=datetime.now(timezone.utc) + timedelta(days=3),
            proposed_by_role="care_coordinator",
            proposed_by_id=str(self.coordinator_owner.id)
        )
        self.session.commit()

        self.assertEqual(appt.status, "PROPOSED")
        self.assertEqual(appt.version, 1)

        # Doctor confirms version 1
        appt = AppointmentService.confirm_appointment(
            self.session,
            appointment_id=appt.id,
            actor_role="doctor",
            actor_id=str(self.doctor_owner.id),
            version=1
        )
        self.session.commit()
        self.assertEqual(appt.status, "PENDING_PATIENT_CONFIRMATION")

        # Patient confirms version 1 -> Status reaches CONFIRMED
        appt = AppointmentService.confirm_appointment(
            self.session,
            appointment_id=appt.id,
            actor_role="patient",
            actor_id=str(self.patient.id),
            version=1
        )
        self.session.commit()
        self.assertEqual(appt.status, "CONFIRMED")

    def test_06_appointment_version_mismatch_prevents_confirmation(self):
        """If appointment is rescheduled to version 2, patient confirming version 1 must be rejected."""
        appt = AppointmentService.create_appointment_proposal(
            self.session,
            case_id=self.case.id,
            patient_id=self.patient.id,
            facility="CareBridge Specialty Hub",
            provider_name="Dr. Sundaram",
            appointment_type="consultation",
            scheduled_time=datetime.now(timezone.utc) + timedelta(days=3),
            proposed_by_role="care_coordinator",
            proposed_by_id=str(self.coordinator_owner.id)
        )
        self.session.commit()

        # Doctor confirms v1
        AppointmentService.confirm_appointment(
            self.session,
            appointment_id=appt.id,
            actor_role="doctor",
            actor_id=str(self.doctor_owner.id),
            version=1
        )
        self.session.commit()

        # Doctor reschedules -> increments to version 2
        appt = AppointmentService.reschedule_appointment(
            self.session,
            appointment_id=appt.id,
            new_scheduled_time=datetime.now(timezone.utc) + timedelta(days=5),
            actor_role="doctor",
            actor_id=str(self.doctor_owner.id)
        )
        self.session.commit()
        self.assertEqual(appt.version, 2)
        self.assertFalse(appt.patient_confirmed)

        # Patient attempts to confirm stale version 1 -> Must raise AppointmentConfirmationError
        with self.assertRaises(AppointmentConfirmationError):
            AppointmentService.confirm_appointment(
                self.session,
                appointment_id=appt.id,
                actor_role="patient",
                actor_id=str(self.patient.id),
                version=1 # Stale version!
            )

    def test_07_appointment_double_booking_prevention(self):
        """Cannot book overlapping appointments for the same provider or patient."""
        slot_time = datetime.now(timezone.utc) + timedelta(days=4)
        appt1 = AppointmentService.create_appointment_proposal(
            self.session,
            case_id=self.case.id,
            patient_id=self.patient.id,
            facility="CareBridge Specialty Hub",
            provider_name="Dr. Sundaram",
            appointment_type="consultation",
            scheduled_time=slot_time,
            proposed_by_role="care_coordinator",
            proposed_by_id=str(self.coordinator_owner.id)
        )
        self.session.commit()

        # Attempting duplicate proposal for same doctor at same time
        with self.assertRaises(AppointmentConflictError):
            AppointmentService.create_appointment_proposal(
                self.session,
                case_id=self.case.id,
                patient_id=self.patient.id,
                facility="CareBridge Specialty Hub",
                provider_name="Dr. Sundaram",
                appointment_type="biopsy",
                scheduled_time=slot_time,
                proposed_by_role="care_coordinator",
                proposed_by_id=str(self.coordinator_owner.id)
            )

    def test_08_appointment_cannot_be_created_on_closed_case(self):
        """Cannot create appointment on a closed case without reopen workflow."""
        self.case.status = "closed"
        self.session.commit()

        with self.assertRaises(AppointmentClosedCaseError):
            AppointmentService.create_appointment_proposal(
                self.session,
                case_id=self.case.id,
                patient_id=self.patient.id,
                facility="CareBridge Specialty Hub",
                provider_name="Dr. Sundaram",
                appointment_type="consultation",
                scheduled_time=datetime.now(timezone.utc) + timedelta(days=2),
                proposed_by_role="care_coordinator",
                proposed_by_id=str(self.coordinator_owner.id)
            )

    # -------------------------------------------------------------------------
    # 4. Doctor Allocation: Specialty Eligibility BEFORE Workload Ranking
    # -------------------------------------------------------------------------
    def test_09_specialty_eligibility_before_workload(self):
        """Doctor allocation must strictly match required specialty before checking workload capacity."""
        # Doctor A: Orthopedics (wrong specialty!)
        doc_ortho = CaseOwner(
            id=uuid.uuid4(),
            name="Dr. Ortho",
            role="doctor",
            specialty="Orthopedics",
            facility="CareBridge Clinic",
            email=f"ortho_{uuid.uuid4().hex[:6]}@example.com",
            is_active=True,
            max_workload=20
        )
        # Doctor B: Diagnostic Radiology (matches specialty!)
        doc_radio = CaseOwner(
            id=uuid.uuid4(),
            name="Dr. Radiologist",
            role="doctor",
            specialty="Diagnostic Radiology",
            facility="CareBridge Specialty Hub",
            email=f"radio_{uuid.uuid4().hex[:6]}@example.com",
            is_active=True,
            max_workload=10
        )
        self.session.add_all([doc_ortho, doc_radio])
        self.session.commit()

        match = DoctorAllocationService.allocate_doctor_for_case(
            self.session,
            case_id=self.case.id,
            required_specialty="Diagnostic Radiology",
            assigned_by_role="care_coordinator",
            assigned_by_id=str(self.coordinator_owner.id)
        )
        self.session.commit()

        self.assertIsNotNone(match)
        self.assertNotEqual(match.doctor_id, doc_ortho.id, "Ineligible specialty doctor must never be selected!")
        self.assertIn(match.doctor_id, [doc_radio.id, self.doctor_owner.id], "Must allocate a matching specialty doctor!")

    # -------------------------------------------------------------------------
    # 5. Referral Service: Doctor Rationale Separation & Patient Decision Tracking
    # -------------------------------------------------------------------------
    def test_10_referral_rationale_separation_and_decision_tracking(self):
        """Referral separates doctor clinical rationale from AI educational summary, and records patient decision."""
        ref = ReferralService.create_referral(
            self.session,
            case_id=self.case.id,
            patient_id=self.patient.id,
            referring_provider="Dr. Sundaram",
            target_facility="Regional Oncology Center",
            specialty="Surgical Oncology",
            reason_for_referral="BI-RADS 4 suspicious mass requiring tissue sampling",
            clinical_rationale="Core needle biopsy indicated to evaluate microcalcifications per ACR guidelines",
            ai_educational_summary="Your doctor recommends a visit to an oncology specialist for a detailed tissue check."
        )
        self.session.commit()

        self.assertEqual(ref.clinical_rationale, "Core needle biopsy indicated to evaluate microcalcifications per ACR guidelines")
        self.assertEqual(ref.ai_educational_summary, "Your doctor recommends a visit to an oncology specialist for a detailed tissue check.")

        # Record patient decision
        updated_ref = ReferralService.record_patient_decision(
            self.session,
            referral_id=ref.id,
            patient_id=self.patient.id,
            decision="wait",
            notes="Patient requesting clarification regarding financial coverage."
        )
        self.session.commit()

        self.assertEqual(updated_ref.patient_decision, "wait")
        self.assertIsNotNone(updated_ref.patient_decision_at)

    # -------------------------------------------------------------------------
    # 6. Scenario D: Full Sequential 14-Stage Verified Care Journey
    # -------------------------------------------------------------------------
    def test_11_scenario_d_sequential_14_stages_with_real_evidence(self):
        """Scenario D: Complete 14-stage journey executed with real evidence for every single stage."""
        # Stage 1 & 2 initialized
        LifecycleService.initialize_lifecycle(self.session, self.case, self.screening, self.patient)
        self.session.commit()

        # Stage 3: PATIENT_NOTIFIED with notification delivery evidence
        notif = Notification(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            patient_id=self.patient.id,
            role="patient",
            event_type="screening_result",
            title="Screening Results Available",
            message="Your mammogram screening results are ready.",
            priority="normal",
            is_read=True
        )
        self.session.add(notif)
        self.session.commit()

        LifecycleService.advance_stage(
            self.session,
            case_id=self.case.id,
            stage_ident=3,
            actor_role="care_coordinator",
            actor_id=str(self.coordinator_owner.id),
            evidence={"notification_id": str(notif.id), "delivery_status": "delivered", "channel": "in_app_chat"}
        )
        self.session.commit()

        # Stage 4: PATIENT_UNDERSTANDS with case-aware explanation evidence
        LifecycleService.advance_stage(
            self.session,
            case_id=self.case.id,
            stage_ident=4,
            actor_role="ai_coordinator",
            actor_id="carebridge_ai_companion",
            evidence={
                "explanation_summary": "Explained BI-RADS 4 finding in plain language",
                "patient_understanding_confirmed": True
            }
        )
        self.session.commit()

        # Stage 5: CLINICAL_REVIEW with doctor review notes
        LifecycleService.advance_stage(
            self.session,
            case_id=self.case.id,
            stage_ident=5,
            actor_role="doctor",
            actor_id=str(self.doctor_owner.id),
            evidence={
                "clinical_assessment": "Reviewed mammography report; agree with BI-RADS 4 assessment",
                "recommended_pathway": "diagnostic_biopsy"
            }
        )
        self.session.commit()

        # Stage 6: CLINICAL_CONFIRMATION_MESSAGE
        LifecycleService.advance_stage(
            self.session,
            case_id=self.case.id,
            stage_ident=6,
            actor_role="doctor",
            actor_id=str(self.doctor_owner.id),
            evidence={
                "message_approved": True,
                "approved_next_steps": "Initiate specialist referral for biopsy"
            }
        )
        self.session.commit()

        # Stage 7: REFERRAL_INITIATED
        ref = ReferralService.create_referral(
            self.session,
            case_id=self.case.id,
            patient_id=self.patient.id,
            referring_provider="Dr. Sundaram",
            target_facility="CareBridge Specialist Center",
            specialty="Surgical Oncology",
            reason_for_referral="BI-RADS 4 assessment",
            clinical_rationale="Biopsy needed",
            ai_educational_summary="Referral for biopsy"
        )
        self.session.commit()

        LifecycleService.advance_stage(
            self.session,
            case_id=self.case.id,
            stage_ident=7,
            actor_role="doctor",
            actor_id=str(self.doctor_owner.id),
            evidence={"referral_id": str(ref.id), "specialty": "Surgical Oncology"}
        )
        self.session.commit()

        # Stage 8: REFERRAL_ACCEPTED
        ref.status = "accepted"
        ref.responded_at = datetime.now(timezone.utc)
        self.session.commit()

        LifecycleService.advance_stage(
            self.session,
            case_id=self.case.id,
            stage_ident=8,
            actor_role="receiving_provider",
            actor_id="prov_spec_01",
            evidence={"referral_id": str(ref.id), "acceptance_status": "accepted"}
        )
        self.session.commit()

        # Stage 9: APPOINTMENT_SCHEDULED_CONFIRMED with dual confirmation
        appt = AppointmentService.create_appointment_proposal(
            self.session,
            case_id=self.case.id,
            patient_id=self.patient.id,
            facility="CareBridge Specialist Center",
            provider_name="Dr. Specialist",
            appointment_type="consultation",
            scheduled_time=datetime.now(timezone.utc) + timedelta(days=2),
            proposed_by_role="care_coordinator",
            proposed_by_id=str(self.coordinator_owner.id)
        )
        self.session.commit()

        AppointmentService.confirm_appointment(
            self.session, appointment_id=appt.id, actor_role="doctor", actor_id=str(self.doctor_owner.id), version=1
        )
        AppointmentService.confirm_appointment(
            self.session, appointment_id=appt.id, actor_role="patient", actor_id=str(self.patient.id), version=1
        )
        self.session.commit()

        LifecycleService.advance_stage(
            self.session,
            case_id=self.case.id,
            stage_ident=9,
            actor_role="care_coordinator",
            actor_id=str(self.coordinator_owner.id),
            evidence={"appointment_id": str(appt.id), "status": "CONFIRMED", "version": 1}
        )
        self.session.commit()

        # Stage 10: CONSULTATION_COMPLETED with consultation documentation
        LifecycleService.advance_stage(
            self.session,
            case_id=self.case.id,
            stage_ident=10,
            actor_role="doctor",
            actor_id=str(self.doctor_owner.id),
            evidence={
                "consultation_notes": "Patient attended consultation. Physical exam and ultrasound-guided core biopsy performed.",
                "procedure_performed": "Core Needle Biopsy"
            }
        )
        self.session.commit()

        # Stage 11: TREATMENT_MONITORING
        LifecycleService.advance_stage(
            self.session,
            case_id=self.case.id,
            stage_ident=11,
            actor_role="care_coordinator",
            actor_id=str(self.coordinator_owner.id),
            evidence={
                "monitoring_plan": "Post-biopsy symptom tracking and pathology turnaround monitoring",
                "milestones_defined": ["pathology_received", "symptom_free"]
            }
        )
        self.session.commit()

        # Stage 12: FOLLOW_UP
        LifecycleService.advance_stage(
            self.session,
            case_id=self.case.id,
            stage_ident=12,
            actor_role="doctor",
            actor_id=str(self.doctor_owner.id),
            evidence={
                "follow_up_outcome": "Pathology shows benign fibroadenoma. No malignancy detected.",
                "surveillance_schedule": "Routine annual mammography recommended"
            }
        )
        self.session.commit()

        # Stage 13: DOCUMENTATION_COMPLETED
        LifecycleService.advance_stage(
            self.session,
            case_id=self.case.id,
            stage_ident=13,
            actor_role="care_coordinator",
            actor_id=str(self.coordinator_owner.id),
            evidence={
                "records_compiled": ["imaging_report", "biopsy_pathology", "consultation_notes", "follow_up_notes"],
                "audit_complete": True
            }
        )
        self.session.commit()

        # Stage 14: VERIFIED_CLINICAL_CLOSURE with doctor verified sign-off
        closure = ClosureEvidence(
            id=uuid.uuid4(),
            case_id=self.case.id,
            evidence_type="authorized_human_signoff",
            evidence_summary="Biopsy benign, clinical resolution verified by attending physician",
            verifying_clinician_id=self.doctor_owner.id,
            verified_at=datetime.now(timezone.utc),
            is_verified=True,
            evidence_metadata={"benign_finding": True, "closure_type": "resolved"}
        )
        self.session.add(closure)
        self.session.commit()

        LifecycleService.advance_stage(
            self.session,
            case_id=self.case.id,
            stage_ident=14,
            actor_role="doctor",
            actor_id=str(self.doctor_owner.id),
            evidence={
                "closure_evidence_id": str(closure.id),
                "closure_evidence_type": "authorized_human_signoff",
                "doctor_signoff": True
            }
        )
        self.session.commit()

        # Verification of final state
        self.assertEqual(self.case.status, "closed")
        stages = LifecycleService.get_lifecycle_stages(self.case)
        for s in stages:
            self.assertEqual(s["status"], "completed", f"Stage {s['stage_number']} ({s['stage_id']}) was not completed!")
            self.assertTrue(bool(s.get("evidence")), f"Stage {s['stage_number']} missing evidence!")


if __name__ == "__main__":
    unittest.main()
