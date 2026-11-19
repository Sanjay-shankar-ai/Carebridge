"""
CareBridge Doctor Subgraph Unit & Integration Tests
Tests for permissions, appointment changes, referrals, consultation records,
ownership continuity, clinical closure, and audit trail.
"""

import unittest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
import app.database.session as session_module
from app.database.seed import seed_database
from app.models import (
    Patient, CareCase, CaseOwner, ScreeningResult, Appointment,
    Task, Referral, CaseEvent, AuditLog, ClosureEvidence
)
from app.core.config import settings
from app.workflows.doctor_state import DoctorState
from app.workflows.doctor_nodes import (
    doctor_intake_node,
    doctor_auth_check_node,
    doctor_context_retrieval_node,
    doctor_case_review_node,
    referral_management_node,
    appointment_management_node,
    consultation_management_node,
    clinical_decision_review_node,
    followup_management_node,
    closure_review_node,
    doctor_response_node,
)
from app.workflows.doctor_workflow import (
    create_doctor_workflow,
    run_doctor_workflow,
)


class TestDoctorWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings.LLM_PROVIDER = "mock"
        cls.engine = create_engine("sqlite:///:memory:")
        cls.SessionFactory = sessionmaker(bind=cls.engine)
        session_module.sync_session_factory = cls.SessionFactory

    def setUp(self):
        Base.metadata.create_all(self.engine)
        self.session = self.SessionFactory()
        seed_database(self.session)

        # Seed data entities:
        # CaseOwner 1: Priya Nair, RN (care_coordinator)
        # CaseOwner 2: Dr. Aris Thorne, MD (specialist at Clinic A)
        self.coordinator = self.session.query(CaseOwner).filter(CaseOwner.role == "care_coordinator").first()
        self.doctor = self.session.query(CaseOwner).filter(CaseOwner.role == "specialist").first()
        self.patient = self.session.query(Patient).filter(Patient.mrn == "MRN-2026-0147").first()
        self.case = self.session.query(CareCase).filter(CareCase.patient_id == self.patient.id).first()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)

    # --------------------------------------------------------------------------
    # 1. Intake & Intent Classification
    # --------------------------------------------------------------------------
    def test_01_intake_intent_classification(self):
        intake_tests = [
            ("Please accept referral for this patient", "accept_referral"),
            ("We must reject referral due to capacity", "reject_referral"),
            ("Need to cancel appointment due to emergency surgery", "cancel_appointment"),
            ("Please reschedule appointment for next week", "reschedule_appointment"),
            ("Confirm appointment for Thursday", "confirm_appointment"),
            ("Record consultation findings: patient in stable condition", "record_consultation"),
            ("Clinical decision: recommend core needle biopsy", "clinical_decision"),
            ("Schedule follow-up ultrasound in 6 months", "schedule_followup"),
            ("Pathology is benign, close case", "close_case"),
            ("Please review case status", "review_case"),
        ]

        for msg, expected_intent in intake_tests:
            state: DoctorState = {
                "doctor_id": str(self.doctor.id),
                "doctor_message": msg,
                "doctor_intent": None,
                "intent_confidence": None,
                "case_id": str(self.case.id),
                "patient_id": None,
                "is_authorized": False,
                "auth_failure_reason": None,
                "case_context": None,
                "patient_context": None,
                "screening_context": None,
                "referral_action": None,
                "referral_reason": None,
                "appointment_action": None,
                "cancellation_reason": None,
                "consultation_notes": None,
                "clinical_decision": None,
                "followup_plan": None,
                "closure_decision": None,
                "closure_evidence_summary": None,
                "replacement_requires_dual_acceptance": False,
                "response_message": None,
                "workflow_phase": "start",
                "next_step": None,
                "audit_log": [],
                "errors": [],
            }
            res = doctor_intake_node(state)
            self.assertEqual(res["doctor_intent"], expected_intent, f"Failed for message: '{msg}'")

    # --------------------------------------------------------------------------
    # 2. Permissions & Authorization
    # --------------------------------------------------------------------------
    def test_02_auth_valid_assigned_doctor(self):
        state: DoctorState = {
            "doctor_id": str(self.doctor.id),
            "doctor_message": "review case",
            "case_id": str(self.case.id),
            "is_authorized": False,
            "auth_failure_reason": None,
        }
        res = doctor_auth_check_node(state)
        self.assertTrue(res["is_authorized"])
        self.assertIsNone(res["auth_failure_reason"])

    def test_03_auth_inactive_doctor_blocked(self):
        # Deactivate doctor
        self.doctor.is_active = False
        self.session.commit()

        state: DoctorState = {
            "doctor_id": str(self.doctor.id),
            "doctor_message": "review case",
            "case_id": str(self.case.id),
            "is_authorized": False,
            "auth_failure_reason": None,
        }
        res = doctor_auth_check_node(state)
        self.assertFalse(res["is_authorized"])
        self.assertIn("inactive", res["auth_failure_reason"])

    def test_04_auth_non_doctor_role_blocked(self):
        # Coordinator attempts to access doctor subgraph
        state: DoctorState = {
            "doctor_id": str(self.coordinator.id),
            "doctor_message": "review case",
            "case_id": str(self.case.id),
            "is_authorized": False,
            "auth_failure_reason": None,
        }
        res = doctor_auth_check_node(state)
        self.assertFalse(res["is_authorized"])
        self.assertIn("care_coordinator", res["auth_failure_reason"])

    def test_05_auth_unassigned_doctor_blocked(self):
        # Create an unassigned doctor from another facility
        external_doc = CaseOwner(
            id=uuid.uuid4(),
            name="Dr. External Unassigned, MD",
            role="specialist",
            email="external@unaffiliated.org",
            facility="Unaffiliated General Hospital",
            is_active=True
        )
        self.session.add(external_doc)
        self.session.commit()

        state: DoctorState = {
            "doctor_id": str(external_doc.id),
            "doctor_message": "review case",
            "case_id": str(self.case.id),
            "is_authorized": False,
            "auth_failure_reason": None,
        }
        res = doctor_auth_check_node(state)
        self.assertFalse(res["is_authorized"])
        self.assertIn("not assigned", res["auth_failure_reason"])

    # --------------------------------------------------------------------------
    # 3. Context Retrieval & Case Review
    # --------------------------------------------------------------------------
    def test_06_context_retrieval_and_case_review(self):
        state: DoctorState = {
            "doctor_id": str(self.doctor.id),
            "case_id": str(self.case.id),
            "patient_id": str(self.patient.id),
            "doctor_intent": "review_case",
        }
        ctx_res = doctor_context_retrieval_node(state)
        self.assertEqual(ctx_res["workflow_phase"], "context_retrieved")
        self.assertIsNotNone(ctx_res["case_context"])
        self.assertIsNotNone(ctx_res["screening_context"])
        self.assertEqual(ctx_res["screening_context"]["finding_code"], "BI-RADS-4")

        # Pass retrieved context to review node
        review_state: DoctorState = {
            **state,
            **ctx_res
        }
        rev_res = doctor_case_review_node(review_state)
        self.assertEqual(rev_res["workflow_phase"], "case_reviewed")
        self.assertIn("Meenakshi Ramanathan", rev_res["response_message"])
        self.assertIn("BI-RADS-4", rev_res["response_message"])
        self.assertIn("Priya Nair", rev_res["response_message"])

    # --------------------------------------------------------------------------
    # 4. Referral Management (Accept / Reject / Reroute)
    # --------------------------------------------------------------------------
    def test_07_referral_acceptance(self):
        state: DoctorState = {
            "doctor_id": str(self.doctor.id),
            "case_id": str(self.case.id),
            "doctor_intent": "accept_referral",
            "doctor_message": "Accept referral for diagnostic breast oncology",
            "referral_reason": None,
        }
        res = referral_management_node(state)
        self.assertEqual(res["referral_action"], "accepted")
        self.assertEqual(len(res["audit_log"]), 1)
        self.assertEqual(res["audit_log"][0]["actor_type"], "clinician")

        # Verify DB
        ref = self.session.query(Referral).filter(Referral.case_id == self.case.id).first()
        self.assertEqual(ref.status, "accepted")

    def test_08_referral_rejection_with_reason_and_ownership_continuity(self):
        original_owner_id = self.case.current_owner_id
        self.assertIsNotNone(original_owner_id)

        state: DoctorState = {
            "doctor_id": str(self.doctor.id),
            "case_id": str(self.case.id),
            "doctor_intent": "reject_referral",
            "doctor_message": "Reject referral: facility at full capacity for biopsy",
            "referral_reason": "Capacity constraints at Clinic A",
        }
        res = referral_management_node(state)
        self.assertEqual(res["referral_action"], "rejected")
        self.assertEqual(res["referral_reason"], "Capacity constraints at Clinic A")

        # Check DB
        ref = self.session.query(Referral).filter(Referral.case_id == self.case.id).first()
        self.assertEqual(ref.status, "rejected")
        self.assertEqual(ref.rejection_reason, "Capacity constraints at Clinic A")

        # CRITICAL: Care Coordinator ownership is preserved!
        refreshed_case = self.session.query(CareCase).filter(CareCase.id == self.case.id).first()
        self.assertEqual(refreshed_case.current_owner_id, original_owner_id)

    # --------------------------------------------------------------------------
    # 5. Appointment Management (Cancel Reason Mandatory, Dual Acceptance)
    # --------------------------------------------------------------------------
    def test_09_appointment_cancellation_requires_mandatory_reason(self):
        # Empty cancellation reason
        state: DoctorState = {
            "doctor_id": str(self.doctor.id),
            "case_id": str(self.case.id),
            "doctor_intent": "cancel_appointment",
            "doctor_message": "cancel appointment",
            "cancellation_reason": "",
        }
        res = appointment_management_node(state)
        self.assertEqual(res["workflow_phase"], "cancellation_reason_required")
        self.assertIn("mandatory reason", res["response_message"])

    def test_10_appointment_cancellation_with_reason_and_dual_acceptance(self):
        state: DoctorState = {
            "doctor_id": str(self.doctor.id),
            "case_id": str(self.case.id),
            "doctor_intent": "cancel_appointment",
            "doctor_message": "Cancel appointment because doctor has emergency clinical obligations",
            "cancellation_reason": "Emergency surgery conflict",
        }
        res = appointment_management_node(state)
        self.assertEqual(res["appointment_action"], "cancelled")
        self.assertEqual(res["cancellation_reason"], "Emergency surgery conflict")
        self.assertTrue(res["replacement_requires_dual_acceptance"])
        self.assertEqual(res["audit_log"][0]["actor_type"], "clinician")

        # Check DB appointment
        appt = (
            self.session.query(Appointment)
            .filter(Appointment.case_id == self.case.id, Appointment.status == "cancelled")
            .first()
        )
        self.assertIsNotNone(appt)
        self.assertEqual(appt.cancellation_reason, "Emergency surgery conflict")

        # Coordinator retains ownership
        refreshed_case = self.session.query(CareCase).filter(CareCase.id == self.case.id).first()
        self.assertEqual(refreshed_case.current_owner_id, self.coordinator.id)

    def test_11_appointment_reschedule_dual_acceptance(self):
        state: DoctorState = {
            "doctor_id": str(self.doctor.id),
            "case_id": str(self.case.id),
            "doctor_intent": "reschedule_appointment",
            "doctor_message": "Reschedule appointment to next week",
        }
        res = appointment_management_node(state)
        self.assertEqual(res["appointment_action"], "rescheduled")
        self.assertTrue(res["replacement_requires_dual_acceptance"])

        # Check new replacement appointment created
        new_appt = (
            self.session.query(Appointment)
            .filter(Appointment.case_id == self.case.id, Appointment.rescheduled_from_id.isnot(None))
            .order_by(Appointment.created_at.desc())
            .first()
        )
        self.assertIsNotNone(new_appt)
        self.assertEqual(new_appt.status, "booked")

    # --------------------------------------------------------------------------
    # 6. Consultation Notes Recording
    # --------------------------------------------------------------------------
    def test_12_record_consultation_notes(self):
        notes_text = "Clinical examination completed. 4cm mass palpable in right breast outer quadrant. Core biopsy performed without complications."
        state: DoctorState = {
            "doctor_id": str(self.doctor.id),
            "case_id": str(self.case.id),
            "doctor_intent": "record_consultation",
            "doctor_message": notes_text,
            "consultation_notes": notes_text,
        }
        res = consultation_management_node(state)
        self.assertEqual(res["workflow_phase"], "consultation_recorded")
        self.assertEqual(res["audit_log"][0]["actor_type"], "clinician")

        # Check DB events
        event = (
            self.session.query(CaseEvent)
            .filter(CaseEvent.case_id == self.case.id, CaseEvent.event_type == "doctor_consultation")
            .first()
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.event_data["notes"], notes_text)

        # Check appointment marked attended
        appt = self.session.query(Appointment).filter(Appointment.case_id == self.case.id, Appointment.status == "attended").first()
        self.assertIsNotNone(appt)

    # --------------------------------------------------------------------------
    # 7. Clinical Decision Recording (Physician Authority, NOT AI)
    # --------------------------------------------------------------------------
    def test_13_record_clinical_decision(self):
        decision_data = {
            "diagnosis_impression": "Suspicious mammary lesion BI-RADS 4c",
            "recommended_treatment": "Surgical excision or targeted chemo pending pathology",
            "pathology_requested": True
        }
        state: DoctorState = {
            "doctor_id": str(self.doctor.id),
            "case_id": str(self.case.id),
            "doctor_intent": "clinical_decision",
            "doctor_message": "Clinical decision: Suspicious mammary lesion BI-RADS 4c",
            "clinical_decision": decision_data,
        }
        res = clinical_decision_review_node(state)
        self.assertEqual(res["workflow_phase"], "clinical_decision_recorded")
        self.assertEqual(res["audit_log"][0]["autonomy_level"], 3)
        self.assertEqual(res["audit_log"][0]["actor_type"], "clinician")

        # Check DB
        event = (
            self.session.query(CaseEvent)
            .filter(CaseEvent.case_id == self.case.id, CaseEvent.event_type == "clinical_decision")
            .first()
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.event_data["decision"]["diagnosis_impression"], "Suspicious mammary lesion BI-RADS 4c")

    # --------------------------------------------------------------------------
    # 8. Follow-up Management
    # --------------------------------------------------------------------------
    def test_14_schedule_clinical_followup(self):
        state: DoctorState = {
            "doctor_id": str(self.doctor.id),
            "case_id": str(self.case.id),
            "doctor_intent": "schedule_followup",
            "doctor_message": "Schedule follow-up ultrasound in 14 days",
            "followup_plan": {"description": "Follow-up ultrasound and wound check", "due_days": 14},
        }
        res = followup_management_node(state)
        self.assertEqual(res["workflow_phase"], "followup_scheduled")
        self.assertEqual(res["audit_log"][0]["actor_type"], "clinician")

        # Check DB task created and assigned to coordinator
        task = (
            self.session.query(Task)
            .filter(Task.case_id == self.case.id, Task.task_type == "clinical_followup")
            .first()
        )
        self.assertIsNotNone(task)
        self.assertEqual(task.assigned_to_id, self.coordinator.id)

    # --------------------------------------------------------------------------
    # 9. Closure Review (Level 3 Clinical Verification)
    # --------------------------------------------------------------------------
    def test_15_clinical_closure_verification_approved(self):
        evidence_text = "Pathology report received: Benign fibroadenoma. No atypia or malignancy identified. Routine annual screening recommended."
        state: DoctorState = {
            "doctor_id": str(self.doctor.id),
            "case_id": str(self.case.id),
            "doctor_intent": "close_case",
            "doctor_message": "Pathology benign, approve closure",
            "closure_decision": "approved",
            "closure_evidence_summary": evidence_text,
        }
        res = closure_review_node(state)
        self.assertEqual(res["workflow_phase"], "closure_verified")
        self.assertEqual(res["closure_decision"], "approved")
        self.assertEqual(res["audit_log"][0]["autonomy_level"], 3)
        self.assertEqual(res["audit_log"][0]["actor_type"], "clinician")

        # Verify ClosureEvidence created with doctor sign-off
        evidence = (
            self.session.query(ClosureEvidence)
            .filter(ClosureEvidence.case_id == self.case.id, ClosureEvidence.is_verified.is_(True))
            .first()
        )
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.verifying_clinician_id, self.doctor.id)
        self.assertEqual(evidence.evidence_summary, evidence_text)

    def test_16_clinical_closure_rejected_leaves_case_open(self):
        state: DoctorState = {
            "doctor_id": str(self.doctor.id),
            "case_id": str(self.case.id),
            "doctor_intent": "close_case",
            "doctor_message": "Do not close: margins are unclear, repeat biopsy needed",
            "closure_decision": "rejected",
            "closure_evidence_summary": "Margins unclear, repeat biopsy required before closure.",
        }
        res = closure_review_node(state)
        self.assertEqual(res["workflow_phase"], "closure_rejected")
        self.assertEqual(res["closure_decision"], "rejected")

        # No verified closure evidence should be created
        evidence = (
            self.session.query(ClosureEvidence)
            .filter(ClosureEvidence.case_id == self.case.id, ClosureEvidence.is_verified.is_(True))
            .first()
        )
        self.assertIsNone(evidence)

    # --------------------------------------------------------------------------
    # 10. End-to-End Doctor Workflow Execution via run_doctor_workflow
    # --------------------------------------------------------------------------
    def test_17_full_workflow_case_review(self):
        result = run_doctor_workflow(
            doctor_id=str(self.doctor.id),
            message="Show me the case review and screening results for CASE-2026-0147",
            case_id=str(self.case.id),
        )
        self.assertTrue(result["is_authorized"])
        self.assertIn("Meenakshi Ramanathan", result["response_message"])
        self.assertEqual(result["workflow_phase"], "response_sent")

    def test_18_full_workflow_unauthorized_blocked(self):
        result = run_doctor_workflow(
            doctor_id=str(self.coordinator.id),  # Coordinator, not a doctor
            message="Review case status",
            case_id=str(self.case.id),
        )
        self.assertFalse(result["is_authorized"])
        self.assertIn("Access Denied", result["response_message"])


if __name__ == "__main__":
    unittest.main()
