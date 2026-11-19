"""
CareBridge Agent Tool Ecosystem Unit & Integration Tests (Phase 5)
Verifies all 7 modular tool domains:
1. Patient tools (profile, preferences, conversation history)
2. Case tools (create case, details, events, notes, assign ownership)
3. Communication tools (draft message, translate, send permitted, record acknowledgement)
4. Referral tools (create request, check status, retrieve information)
5. Appointment tools (search slots, book within SLA, reschedule with mandatory reason, status)
6. Recovery tools (create followup task, identify stalled cases, propose recovery, escalate)
7. Closure tools (retrieve evidence, 5-point checklist, request clinical verification)
8. Security & Permissions (role validation, consent verification, Level 3 human gate)
9. LangChain @tool wrappers (MODULAR_ECOSYSTEM_TOOLS execution)
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
    Task, Referral, Communication, CaseEvent, AuditLog, ClosureEvidence, Consent
)
from app.core.config import settings

# Schemas
from app.tools.schemas import (
    RetrievePatientProfileInput,
    RetrievePatientPreferencesInput,
    RetrieveConversationHistoryInput,
    CreateCareCaseInput,
    RetrieveCaseDetailsInput,
    RetrieveCaseEventsInput,
    UpdateCaseNotesInput,
    AssignAdministrativeOwnershipInput,
    DraftPatientMessageInput,
    TranslateMessageInput,
    SendPermittedCommunicationInput,
    RecordAcknowledgementInput,
    CreateReferralRequestInput,
    CheckReferralStatusInput,
    RetrieveReferralInformationInput,
    SearchAvailableAppointmentsInput,
    BookAppointmentInput,
    RescheduleAppointmentInput,
    RetrieveAppointmentStatusInput,
    CreateFollowupTaskInput,
    IdentifyStalledCasesInput,
    ProposeRecoveryActionInput,
    EscalateCaseInput,
    RetrieveClosureEvidenceInput,
    RequestClosureVerificationInput,
)

# Domain Implementations
import app.tools.patient_tools as patient_tools
import app.tools.case_tools as case_tools
import app.tools.communication_tools as comm_tools
import app.tools.referral_tools as referral_tools
import app.tools.appointment_tools as appt_tools
import app.tools.recovery_tools as recovery_tools
import app.tools.closure_tools as closure_tools
import app.tools.agent_tools as agent_tools


class TestAgentToolEcosystem(unittest.TestCase):
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

        # Retrieve exemplar seeded records: Meenakshi Ramanathan (P-0147)
        self.patient = self.session.query(Patient).filter(Patient.mrn == "MRN-2026-0147").first()
        self.case = self.session.query(CareCase).filter(CareCase.patient_id == self.patient.id).first()
        self.screening = self.session.query(ScreeningResult).filter(ScreeningResult.patient_id == self.patient.id).first()
        self.coordinator = self.session.query(CaseOwner).filter(CaseOwner.role == "care_coordinator").first()
        self.doctor = self.session.query(CaseOwner).filter(CaseOwner.role == "specialist").first()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)

    # ==========================================================================
    # 1. Patient Domain Tools
    # ==========================================================================
    def test_01_retrieve_patient_profile(self):
        inp = RetrievePatientProfileInput(patient_id=str(self.patient.id))
        res = patient_tools.retrieve_patient_profile(self.session, inp)
        self.assertTrue(res.success)
        self.assertEqual(res.data.mrn, "MRN-2026-0147")
        self.assertEqual(res.data.first_name, "Meenakshi")
        self.assertEqual(res.data.preferred_language, "ta")
        self.assertIn("transportation_caregiver_dependency", res.data.known_barriers)

    def test_02_retrieve_patient_profile_not_found(self):
        inp = RetrievePatientProfileInput(patient_id=str(uuid.uuid4()))
        res = patient_tools.retrieve_patient_profile(self.session, inp)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "PATIENT_NOT_FOUND")

    def test_03_retrieve_patient_preferences(self):
        inp = RetrievePatientPreferencesInput(patient_id=str(self.patient.id))
        res = patient_tools.retrieve_patient_preferences(self.session, inp)
        self.assertTrue(res.success)
        self.assertEqual(res.data.preferred_language, "ta")
        self.assertEqual(res.data.communication_channel, "whatsapp")
        self.assertIn("automated_patient_outreach", res.data.active_consents)

    def test_04_retrieve_conversation_history(self):
        inp = RetrieveConversationHistoryInput(patient_id=str(self.patient.id), case_id=str(self.case.id))
        res = patient_tools.retrieve_conversation_history(self.session, inp)
        self.assertTrue(res.success)
        self.assertGreaterEqual(res.data.total_messages, 1)
        self.assertIsNotNone(res.data.session_summary)

    # ==========================================================================
    # 2. Case Domain Tools
    # ==========================================================================
    def test_05_create_care_case_new_and_idempotent(self):
        # Create a fresh screening result for a new patient
        new_screening = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=self.patient.id,
            screening_type="Mammogram",
            test_date=datetime.now(timezone.utc),
            finding_code="BI-RADS-4",
            finding_summary="Microcalcifications detected in left breast",
            urgency_level="urgent",
            performing_facility="Metropolitan Lab"
        )
        self.session.add(new_screening)
        self.session.commit()

        inp = CreateCareCaseInput(
            patient_id=str(self.patient.id),
            screening_result_id=str(new_screening.id),
            priority="urgent"
        )
        # First creation
        res = case_tools.create_care_case(self.session, inp)
        self.assertTrue(res.success)
        self.assertIn("CASE-", res.data.case_number)
        first_case_id = res.data.case_id

        # Idempotent call with same screening_result_id
        res_idempotent = case_tools.create_care_case(self.session, inp)
        self.assertTrue(res_idempotent.success)
        self.assertEqual(res_idempotent.data.case_id, first_case_id)
        self.assertIn("Idempotent hit", res_idempotent.message)

    def test_06_retrieve_case_details(self):
        inp = RetrieveCaseDetailsInput(case_id=str(self.case.id))
        res = case_tools.retrieve_case_details(self.session, inp)
        self.assertTrue(res.success)
        self.assertEqual(res.data.case_number, "CASE-2026-0147")
        self.assertEqual(res.data.current_owner_name, "Priya Nair, RN")
        self.assertIn("transportation_caregiver", res.data.inferred_barriers)

    def test_07_retrieve_case_events(self):
        inp = RetrieveCaseEventsInput(case_id=str(self.case.id))
        res = case_tools.retrieve_case_events(self.session, inp)
        self.assertTrue(res.success)
        self.assertGreaterEqual(res.data.total_events, 2)

    def test_08_update_case_notes_and_flag_barrier(self):
        inp = UpdateCaseNotesInput(
            case_id=str(self.case.id),
            note="Patient reported anxiety regarding biopsy needle procedure",
            barrier_detected="procedure_anxiety_fear"
        )
        res = case_tools.update_case_notes(self.session, inp)
        self.assertTrue(res.success)
        self.assertIn("procedure_anxiety_fear", res.data.updated_barriers)
        self.assertIsNotNone(res.audit_id)

    def test_09_assign_administrative_ownership(self):
        # Create a second coordinator
        new_coord = CaseOwner(
            id=uuid.uuid4(),
            name="Rahul Verma, RN",
            role="care_coordinator",
            email="rahul.verma@health.org",
            facility="General Hospital",
            is_active=True
        )
        self.session.add(new_coord)
        self.session.commit()

        inp = AssignAdministrativeOwnershipInput(
            case_id=str(self.case.id),
            new_owner_id=str(new_coord.id),
            assigned_by="clinical_director",
            reason="Workload rebalancing"
        )
        res = case_tools.assign_administrative_ownership(self.session, inp)
        self.assertTrue(res.success)
        self.assertEqual(res.data.owner_name, "Rahul Verma, RN")

        # Verify DB case owner updated
        refreshed_case = self.session.query(CareCase).filter(CareCase.id == self.case.id).first()
        self.assertEqual(refreshed_case.current_owner_id, new_coord.id)

    # ==========================================================================
    # 3. Communication Domain Tools
    # ==========================================================================
    def test_10_draft_patient_message_multilingual(self):
        inp_tamil = DraftPatientMessageInput(
            patient_id=str(self.patient.id),
            case_id=str(self.case.id),
            message_purpose="initial_notification",
            language="ta"
        )
        res_ta = comm_tools.draft_patient_message(self.session, inp_tamil)
        self.assertTrue(res_ta.success)
        self.assertEqual(res_ta.data.language, "ta")
        self.assertIn("வணக்கம்", res_ta.data.drafted_content)

        inp_en = DraftPatientMessageInput(
            patient_id=str(self.patient.id),
            case_id=str(self.case.id),
            message_purpose="appointment_reminder",
            language="en"
        )
        res_en = comm_tools.draft_patient_message(self.session, inp_en)
        self.assertTrue(res_en.success)
        self.assertEqual(res_en.data.language, "en")

    def test_11_translate_message(self):
        inp = TranslateMessageInput(
            text="Your appointment is scheduled for tomorrow at 10 AM.",
            target_language="ta"
        )
        res = comm_tools.translate_message(self.session, inp)
        self.assertTrue(res.success)
        self.assertEqual(res.data.target_language, "ta")

    def test_12_send_permitted_communication_consent_enforcement(self):
        # Patient with active consent succeeds
        inp = SendPermittedCommunicationInput(
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            content="Reminder: Your consultation with Dr. Thorne is confirmed."
        )
        res = comm_tools.send_permitted_communication(self.session, inp)
        self.assertTrue(res.success)
        self.assertEqual(res.data.status, "sent")
        self.assertIsNotNone(res.audit_id)

        # Revoke consents and verify permission check blocks sending
        consents = self.session.query(Consent).filter(Consent.patient_id == self.patient.id).all()
        for c in consents:
            c.status = "revoked"
        self.session.commit()

        res_blocked = comm_tools.send_permitted_communication(self.session, inp)
        self.assertFalse(res_blocked.success)
        self.assertEqual(res_blocked.error_code, "CONSENT_MISSING")

    def test_13_record_acknowledgement(self):
        inp = RecordAcknowledgementInput(
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            acknowledged_via="whatsapp",
            patient_response="Yes, I have noted the clinic appointment date."
        )
        res = comm_tools.record_acknowledgement(self.session, inp)
        self.assertTrue(res.success)
        self.assertTrue(res.data.patient_acknowledged)

        # Verify task completed in DB
        refreshed_case = self.session.query(CareCase).filter(CareCase.id == self.case.id).first()
        self.assertTrue(refreshed_case.case_context.get("patient_understanding_confirmed"))

    # ==========================================================================
    # 4. Referral Domain Tools
    # ==========================================================================
    def test_14_create_referral_request(self):
        inp = CreateReferralRequestInput(
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            target_facility="Apollo Specialty Breast Center",
            specialty="Surgical Oncology",
            reason="Tissue biopsy and staging"
        )
        res = referral_tools.create_referral_request(self.session, inp)
        self.assertTrue(res.success)
        self.assertEqual(res.data.status, "sent")
        self.assertIsNotNone(res.audit_id)

    def test_15_check_referral_status(self):
        # Get existing referral from seed data
        ref = self.session.query(Referral).filter(Referral.case_id == self.case.id).first()
        inp = CheckReferralStatusInput(referral_id=str(ref.id))
        res = referral_tools.check_referral_status(self.session, inp)
        self.assertTrue(res.success)
        self.assertEqual(res.data.status, "accepted")

    def test_16_retrieve_referral_information(self):
        inp = RetrieveReferralInformationInput(case_id=str(self.case.id))
        res = referral_tools.retrieve_referral_information(self.session, inp)
        self.assertTrue(res.success)
        self.assertGreaterEqual(res.data.referral_count, 1)

    # ==========================================================================
    # 5. Appointment Domain Tools
    # ==========================================================================
    def test_17_search_available_appointments(self):
        inp = SearchAvailableAppointmentsInput(facility="Clinic A", specialty="Breast Oncology")
        res = appt_tools.search_available_appointments(self.session, inp)
        self.assertTrue(res.success)
        self.assertGreaterEqual(len(res.data.slots), 2)

    def test_18_book_appointment_within_sla(self):
        # Valid appointment time within SLA deadline
        valid_time = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT10:00:00Z")
        inp = BookAppointmentInput(
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            facility="Apollo Diagnostic Center",
            scheduled_time=valid_time,
            appointment_type="diagnostic_evaluation"
        )
        res = appt_tools.book_appointment(self.session, inp)
        self.assertTrue(res.success)
        self.assertEqual(res.data.status, "booked")
        self.assertIsNotNone(res.audit_id)

    def test_19_book_appointment_sla_breach_rejected(self):
        # Time beyond SLA deadline (e.g. 30 days out)
        breached_time = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT10:00:00Z")
        inp = BookAppointmentInput(
            case_id=str(self.case.id),
            patient_id=str(self.patient.id),
            facility="Apollo Diagnostic Center",
            scheduled_time=breached_time,
            appointment_type="diagnostic_evaluation"
        )
        res = appt_tools.book_appointment(self.session, inp)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "SLA_BREACH_REJECTED")

    def test_20_reschedule_appointment_mandatory_reason_and_dual_acceptance(self):
        active_appt = (
            self.session.query(Appointment)
            .filter(Appointment.case_id == self.case.id, Appointment.status == "booked")
            .first()
        )
        new_time = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT14:00:00Z")

        # Empty reason should be rejected
        inp_empty_reason = RescheduleAppointmentInput(
            appointment_id=str(active_appt.id),
            case_id=str(self.case.id),
            new_scheduled_time=new_time,
            reason=""
        )
        res_fail = appt_tools.reschedule_appointment(self.session, inp_empty_reason)
        self.assertFalse(res_fail.success)
        self.assertEqual(res_fail.error_code, "REASON_REQUIRED")

        # Valid reason succeeds
        inp_valid = RescheduleAppointmentInput(
            appointment_id=str(active_appt.id),
            case_id=str(self.case.id),
            new_scheduled_time=new_time,
            reason="Caregiver daughter returned from travel"
        )
        res_ok = appt_tools.reschedule_appointment(self.session, inp_valid)
        self.assertTrue(res_ok.success)
        self.assertTrue(res_ok.data.requires_dual_acceptance)
        self.assertIsNotNone(res_ok.audit_id)

    def test_21_retrieve_appointment_status(self):
        inp = RetrieveAppointmentStatusInput(case_id=str(self.case.id))
        res = appt_tools.retrieve_appointment_status(self.session, inp)
        self.assertTrue(res.success)
        self.assertGreaterEqual(len(res.data.all_appointments), 2)

    # ==========================================================================
    # 6. Recovery Domain Tools
    # ==========================================================================
    def test_22_create_followup_task(self):
        due = (datetime.now(timezone.utc) + timedelta(days=4)).strftime("%Y-%m-%dT12:00:00Z")
        inp = CreateFollowupTaskInput(
            case_id=str(self.case.id),
            title="Follow-up call on pathology report",
            description="Contact laboratory for provisional core needle biopsy results",
            task_type="clinical_followup",
            due_date=due
        )
        res = recovery_tools.create_followup_task(self.session, inp)
        self.assertTrue(res.success)
        self.assertEqual(res.data.status, "pending")

    def test_23_identify_stalled_cases(self):
        # Case P-0147 has recent events, test threshold inspection
        inp = IdentifyStalledCasesInput(case_id=str(self.case.id), days_threshold=1)
        res = recovery_tools.identify_stalled_cases(self.session, inp)
        self.assertTrue(res.success)

    def test_24_propose_recovery_action(self):
        inp = ProposeRecoveryActionInput(
            case_id=str(self.case.id),
            dropoff_reasons=["transportation_caregiver", "unacknowledged_outreach"]
        )
        res = recovery_tools.propose_recovery_action(self.session, inp)
        self.assertTrue(res.success)
        self.assertIsNotNone(res.data.recommended_strategy)
        self.assertIn("Recovery Play", res.data.action_plan)

    def test_25_escalate_case(self):
        inp = EscalateCaseInput(
            case_id=str(self.case.id),
            urgency="critical",
            reason="Patient unreachable after multiple outreach attempts and upcoming SLA deadline."
        )
        res = recovery_tools.escalate_case(self.session, inp)
        self.assertTrue(res.success)
        self.assertEqual(res.data.status, "ESCALATED")
        self.assertEqual(res.data.priority, "critical")
        self.assertIsNotNone(res.audit_id)

    # ==========================================================================
    # 7. Closure Domain Tools
    # ==========================================================================
    def test_26_retrieve_closure_evidence(self):
        inp = RetrieveClosureEvidenceInput(case_id=str(self.case.id))
        res = closure_tools.retrieve_closure_evidence(self.session, inp)
        self.assertTrue(res.success)
        self.assertIn("all_coordination_tasks_completed", res.data.checklist_status)
        self.assertIn("clinical_verification_signed", res.data.checklist_status)

    def test_27_request_closure_verification_level_3_gate(self):
        inp = RequestClosureVerificationInput(
            case_id=str(self.case.id),
            evidence_type="pathology_report",
            evidence_summary="Core needle biopsy confirmed benign fibroadenoma with clear margins.",
            clinician_id=str(self.doctor.id)
        )
        res = closure_tools.request_closure_verification(self.session, inp)
        self.assertTrue(res.success)
        self.assertFalse(res.data.is_verified)  # AI cannot close independently!
        self.assertTrue(res.data.requires_human_approval)
        self.assertEqual(res.autonomy_level, 3)
        self.assertIsNotNone(res.audit_id)

    # ==========================================================================
    # 8. Security & Role Permissions
    # ==========================================================================
    def test_28_invalid_role_permission_rejected(self):
        inp = RetrievePatientProfileInput(
            patient_id=str(self.patient.id),
            actor_role="unauthorized_hacker"
        )
        res = patient_tools.retrieve_patient_profile(self.session, inp)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "INVALID_ROLE")

    # ==========================================================================
    # 9. LangChain @tool Ecosystem Execution
    # ==========================================================================
    def test_29_agent_tools_execution(self):
        # Test calling the LangChain @tool wrapped functions
        profile_res = agent_tools.retrieve_patient_profile.invoke({"patient_id": str(self.patient.id)})
        self.assertTrue(profile_res["success"])
        self.assertEqual(profile_res["data"]["mrn"], "MRN-2026-0147")

        case_res = agent_tools.retrieve_case_details.invoke({"case_id": str(self.case.id)})
        self.assertTrue(case_res["success"])
        self.assertEqual(case_res["data"]["case_number"], "CASE-2026-0147")

        slots_res = agent_tools.search_available_appointments.invoke({"facility": "Clinic A", "specialty": "Oncology"})
        self.assertTrue(slots_res["success"])
        self.assertGreaterEqual(len(slots_res["data"]["slots"]), 1)


if __name__ == "__main__":
    unittest.main()
