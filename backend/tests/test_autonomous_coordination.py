"""
CareBridge Phase 6: Autonomous Care Coordination Integration Tests
Verifies adaptive care coordination across the complete case journey:
1. Patient inquiries (answers medical questions before proceeding)
2. Inability to attend (identifies caregiver transport barrier and reschedules)
3. Referral delay (investigates status and coordinates liaison)
4. Missed appointment (proactively recovers without dropping ownership)
5. Patient needs assistance (connects with financial/childcare support)
6. Urgent symptoms (emergency escalation protocol to clinical staff)
7. Care refusal (cancels with documented reason and escalates)
8. Evidence-based closure (evaluates 5-point checklist, Level 3 clinical verification)
9. Ownership continuity (coordinator accountability preserved across disruptions)
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
from app.services.care_coordination_service import CareCoordinationService
from app.agents.cognitive_engine import CognitiveEngine
from app.agents.graph import create_carebridge_graph


class TestAutonomousCareCoordination(unittest.TestCase):
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

        # Retrieve exemplar records: Meenakshi Ramanathan (P-0147)
        self.patient = self.session.query(Patient).filter(Patient.mrn == "MRN-2026-0147").first()
        self.case = self.session.query(CareCase).filter(CareCase.patient_id == self.patient.id).first()
        self.coordinator = self.session.query(CaseOwner).filter(CaseOwner.role == "care_coordinator").first()
        self.doctor = self.session.query(CaseOwner).filter(CaseOwner.role == "specialist").first()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)

    # --------------------------------------------------------------------------
    # Scenario 1: Patient Inquiries (Answers medical questions before proceeding)
    # --------------------------------------------------------------------------
    def test_01_patient_inquiry_answers_questions_first(self):
        message = "What does BI-RADS 4 mean? Does this test result mean I have cancer?"
        result = CareCoordinationService.process_patient_message(
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            message=message
        )

        plan = result.get("coordination_plan", {})
        intent = result.get("intent_analysis", {})
        self.assertEqual(intent.get("primary_intent"), "patient_inquiry")

        # Must not rush to cancel or close
        action_names = [a.get("tool") for a in result.get("pending_tool_calls", [])] + [
            obs.get("tool") for obs in result.get("tool_observations", [])
        ]
        self.assertIn("get_screening_result", action_names)
        self.assertIn("update_case_notes", action_names)

        # Empathetic educational explanation provided
        outbound = result.get("outbound_message", "")
        self.assertTrue(any(word in outbound.lower() for word in ["common", "routine", "cancer", "reassur", "peace of mind", "வழக்கமான"]))

    # --------------------------------------------------------------------------
    # Scenario 2: Patient Cannot Attend (Caregiver Transport Barrier)
    # --------------------------------------------------------------------------
    def test_02_cannot_attend_caregiver_barrier_reschedule(self):
        initial_owner = self.case.current_owner_id
        message = "I cannot come tomorrow because my daughter is out of town and I have nobody to take me."
        result = CareCoordinationService.process_patient_message(
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            message=message
        )

        intent = result.get("intent_analysis", {})
        self.assertEqual(intent.get("primary_intent"), "appointment_reschedule_with_barrier")
        barriers = [b.get("barrier_type") for b in intent.get("detected_barriers", [])]
        self.assertIn("transportation_caregiver", barriers)

        # Plan executes slot search and recovery task
        observed_tools = [obs.get("tool") for obs in result.get("tool_observations", [])]
        self.assertIn("update_case_notes", observed_tools)
        self.assertIn("search_available_appointments", observed_tools)
        self.assertIn("create_followup_task", observed_tools)

        # Care Coordinator accountability is strictly preserved!
        refreshed_case = self.session.query(CareCase).filter(CareCase.id == self.case.id).first()
        self.assertEqual(refreshed_case.current_owner_id, initial_owner)

    # --------------------------------------------------------------------------
    # Scenario 3: Delayed Referral Investigation
    # --------------------------------------------------------------------------
    def test_03_delayed_referral_investigation(self):
        res = CareCoordinationService.handle_delayed_referral(case_id=str(self.case.id))
        self.assertEqual(res["action"], "delayed_referral_alert_dispatched")

        # Verify task was created for coordinator
        alert_task = (
            self.session.query(Task)
            .filter(Task.case_id == self.case.id, Task.task_type == "coordinator_alert")
            .order_by(Task.created_at.desc())
            .first()
        )
        self.assertIsNotNone(alert_task)
        self.assertIn("referral", alert_task.description.lower())

    # --------------------------------------------------------------------------
    # Scenario 4: Missed Appointment / No-show Recovery
    # --------------------------------------------------------------------------
    def test_04_missed_appointment_recovery(self):
        appt = self.session.query(Appointment).filter(Appointment.case_id == self.case.id).first()
        res = CareCoordinationService.handle_missed_appointment(
            case_id=str(self.case.id),
            appointment_id=str(appt.id),
            barrier_reason="patient_transport_missed"
        )
        self.assertEqual(res["action"], "recovery_play_initiated")

        # Verify case notes and recovery task logged
        self.session.expire_all()
        refreshed_case = self.session.query(CareCase).filter(CareCase.id == self.case.id).first()
        self.assertIn("patient_transport_missed", refreshed_case.case_context.get("inferred_barriers", []))

    # --------------------------------------------------------------------------
    # Scenario 5: Patient Needs Assistance (Financial / Childcare)
    # --------------------------------------------------------------------------
    def test_05_assistance_request_social_barrier(self):
        message = "I need financial assistance because this clinic is too expensive and I cannot afford the fees."
        result = CareCoordinationService.process_patient_message(
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            message=message
        )

        intent = result.get("intent_analysis", {})
        barriers = [b.get("barrier_type") for b in intent.get("detected_barriers", [])]
        self.assertIn("financial", barriers)

        # Task created for coordinator to connect patient with financial assistance
        support_task = (
            self.session.query(Task)
            .filter(Task.case_id == self.case.id, Task.title.like("%support program%"))
            .first()
        )
        self.assertIsNotNone(support_task)

    # --------------------------------------------------------------------------
    # Scenario 6: Urgent Clinical Symptoms (Emergency Escalation)
    # --------------------------------------------------------------------------
    def test_06_urgent_symptoms_emergency_escalation(self):
        message = "Emergency! I am having severe chest pain and heavy bleeding after my exam."
        result = CareCoordinationService.process_patient_message(
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            message=message
        )

        intent = result.get("intent_analysis", {})
        self.assertEqual(intent.get("primary_intent"), "urgent_clinical_escalation")
        self.assertTrue(intent.get("requires_human_escalation"))

        # Escalates case to critical
        self.session.expire_all()
        refreshed_case = self.session.query(CareCase).filter(CareCase.id == self.case.id).first()
        self.assertEqual(refreshed_case.status.upper(), "ESCALATED")
        self.assertEqual(refreshed_case.priority, "critical")

    # --------------------------------------------------------------------------
    # Scenario 7: Care Refusal / Cancellation with Reason
    # --------------------------------------------------------------------------
    def test_07_care_refusal_with_escalation(self):
        message = "Cancel my appointment. I refuse to come for any biopsy, leave me alone."
        result = CareCoordinationService.process_patient_message(
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            message=message
        )

        intent = result.get("intent_analysis", {})
        self.assertEqual(intent.get("primary_intent"), "appointment_cancellation_and_refusal")

        observed_tools = [obs.get("tool") for obs in result.get("tool_observations", [])]
        self.assertIn("cancel_appointment", observed_tools)
        self.assertIn("escalate_case", observed_tools)

        # Cancelled appointment has documented reason
        cancelled_appt = (
            self.session.query(Appointment)
            .filter(Appointment.case_id == self.case.id, Appointment.status == "cancelled")
            .first()
        )
        self.assertIsNotNone(cancelled_appt)
        self.assertEqual(cancelled_appt.cancellation_reason, "patient_declined_care")

    # --------------------------------------------------------------------------
    # Scenario 8: Evidence-Based Closure Verification (Level 3 Gate)
    # --------------------------------------------------------------------------
    def test_08_evidence_based_closure_verification_gate(self):
        res = CareCoordinationService.handle_closure_verification_request(
            case_id=str(self.case.id),
            evidence_type="pathology_report",
            evidence_summary="Core needle biopsy returned benign fibroadenoma. No malignancy.",
            clinician_id=str(self.doctor.id)
        )
        self.assertIn("closure_checklist", res)
        self.assertIn("verification_request", res)

        # AI did NOT close independently; is_verified is False awaiting clinician sign-off
        verif_data = res["verification_request"].get("data", {})
        self.assertFalse(verif_data.get("is_verified"))
        self.assertTrue(verif_data.get("requires_human_approval") or verif_data.get("requires_approval"))

    # --------------------------------------------------------------------------
    # Scenario 9: Multilingual Tamil Interaction
    # --------------------------------------------------------------------------
    def test_09_multilingual_tamil_interaction(self):
        tamil_message = "வணக்கம், எனது மேமோகிராம் முடிவு என்ன? எனக்கு பயமாக உள்ளது."
        result = CareCoordinationService.process_patient_message(
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            message=tamil_message
        )

        intent = result.get("intent_analysis", {})
        self.assertEqual(intent.get("detected_language"), "ta")
        barriers = [b.get("barrier_type") for b in intent.get("detected_barriers", [])]
        self.assertIn("fear_anxiety", barriers)

        outbound = result.get("outbound_message", "")
        self.assertIn("வணக்கம்", outbound)


if __name__ == "__main__":
    unittest.main()
