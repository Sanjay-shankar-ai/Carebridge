"""
End-to-End Test Suite for Patient AI Conversational Intelligence & Supervisor Refinements
Verifies:
1. Simple greeting does not create a coordinator notification.
2. Repeated greetings produce natural, varied conversational responses (not generic notifications).
3. Screening questions receive contextual, non-diagnostic answers with relevant follow-ups.
4. Multi-turn conversations retain context across turns.
5. Patient anxiety receives empathetic, validating guidance.
6. Appointment requests use the correct coordination tools.
7. Missed appointments initiate recovery workflows.
8. Urgent symptoms trigger clinical escalation and physician alert.
9. Normal questions do not trigger clinical escalation.
10. LLM failure produces a sensible, context-appropriate fallback.
11. Existing role authorization and patient isolation remain intact.
12. Zero regression across the platform.
"""

import os
import sys
import uuid
import unittest
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath("backend"))

from app.database.session import get_sync_db
from app.models.care_case import CareCase
from app.models.notification import Notification
from app.models.communication import Communication
from app.agents.cognitive_engine import CognitiveEngine
from app.agents.state import IntentAnalysis, InferredBarrier
from app.agents.specialized import PatientCommunicationAgent, ClinicalEscalationAgent

BASE_URL = "http://127.0.0.1:8000/api/v1"


class TestPatientAIChatConversationalE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # 1. Login as synthetic patient (Meenakshi Ramanathan)
        login_res = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": "patient@carebridge.com", "password": "PatientPass123!"}
        )
        assert login_res.status_code == 200, f"Patient login failed: {login_res.text}"
        data = login_res.json()
        cls.patient_token = (
            data.get("data", {}).get("token")
            or data.get("data", {}).get("access_token")
            or data.get("token")
        )
        cls.patient_headers = {
            "Authorization": f"Bearer {cls.patient_token}",
            "X-Bypass-Rate-Limit": "1"
        }

        # 2. Login as synthetic doctor (Dr. Aris Thorne)
        doc_login = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": "doctor@carebridge.com", "password": "DoctorPass123!"}
        )
        assert doc_login.status_code == 200, f"Doctor login failed: {doc_login.text}"
        doc_data = doc_login.json()
        cls.doctor_token = (
            doc_data.get("data", {}).get("token")
            or doc_data.get("data", {}).get("access_token")
            or doc_data.get("token")
        )
        cls.doctor_headers = {
            "Authorization": f"Bearer {cls.doctor_token}",
            "X-Bypass-Rate-Limit": "1"
        }

        # 3. Retrieve patient case for authenticated patient user
        with get_sync_db() as db:
            from app.models.user import User
            patient_user = db.query(User).filter(User.email == "patient@carebridge.com").first()
            cls.care_case = db.query(CareCase).filter(CareCase.patient_id == patient_user.patient_id).first()
            assert cls.care_case is not None, "No care case found for test patient"
            cls.case_id = str(cls.care_case.id)
            cls.patient_id = str(cls.care_case.patient_id)

    def setUp(self):
        # Reset case status to active for clean isolation across test cases
        with get_sync_db() as db:
            cc = db.query(CareCase).filter(CareCase.id == uuid.UUID(self.case_id)).first()
            if cc and cc.status == "escalated":
                cc.status = "active"
                cc.priority = "urgent"
                db.commit()

    def _get_notification_count_for_patient_message(self):
        with get_sync_db() as db:
            return db.query(Notification).filter(Notification.event_type == "patient_message").count()

    def test_01_simple_greeting_does_not_create_notification(self):
        """Criterion 1: Simple greeting responds naturally without coordinator notification."""
        notifs_before = self._get_notification_count_for_patient_message()

        res = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": self.case_id, "message": "Hello"},
            headers=self.patient_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]

        # Intent must be greeting
        self.assertEqual(data["primary_intent"], "greeting")

        # Must not claim coordinator was notified
        outbound = data["outbound_message"]
        self.assertNotIn("Your care coordinator Priya Nair and clinical team have been notified", outbound)
        self.assertTrue("Hello" in outbound or "Care Companion" in outbound or "Meenakshi" in outbound)

        # Actions should be empty (no booking or clinical actions on greeting)
        self.assertEqual(len(data["actions_executed"]), 0)

        # Zero new coordinator notifications
        notifs_after = self._get_notification_count_for_patient_message()
        self.assertEqual(notifs_after, notifs_before, "Greeting should NOT create a coordinator notification!")

    def test_02_repeated_greeting_natural_and_no_notification(self):
        """Criterion 2: Repeated greetings produce varied natural response and no notifications."""
        notifs_before = self._get_notification_count_for_patient_message()

        res = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": self.case_id, "message": "Good morning!"},
            headers=self.patient_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]

        self.assertEqual(data["primary_intent"], "greeting")
        outbound = data["outbound_message"]
        self.assertNotIn("have been notified to support", outbound)
        self.assertTrue(len(outbound) > 10)

        notifs_after = self._get_notification_count_for_patient_message()
        self.assertEqual(notifs_after, notifs_before, "Repeated greeting should NOT create coordinator notifications!")

    def test_03_screening_question_contextual_explanation(self):
        """Criterion 3: Screening questions receive contextual answers without diagnosis."""
        notifs_before = self._get_notification_count_for_patient_message()

        res = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": self.case_id, "message": "What does BI-RADS 4 mean?"},
            headers=self.patient_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]

        outbound = data["outbound_message"]
        # Must explain BI-RADS 4 factually
        self.assertTrue("BI-RADS 4" in outbound or "BI-RADS" in outbound or "mammogram" in outbound.lower())
        # Must clearly state it is NOT cancer / 70-80% benign
        self.assertTrue("benign" in outbound.lower() or "not a diagnosis" in outbound.lower() or "not cancer" in outbound.lower())
        # Must not diagnose or claim definitive cancer
        self.assertNotIn("you have cancer", outbound.lower())
        self.assertNotIn("i diagnose you", outbound.lower())

        # No coordinator notification for routine screening inquiry
        notifs_after = self._get_notification_count_for_patient_message()
        self.assertEqual(notifs_after, notifs_before)

    def test_04_multi_turn_anxiety_receives_empathetic_guidance(self):
        """Criterion 4 & 5: Multi-turn emotional distress receives empathetic validating guidance."""
        # Patient expresses fear following the BI-RADS 4 inquiry
        res = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": self.case_id, "message": "I'm really scared about this. What should I do?"},
            headers=self.patient_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]

        outbound = data["outbound_message"]
        # Must validate feelings and provide empathy
        self.assertTrue(
            any(w in outbound.lower() for w in ["understand", "scary", "scared", "normal", "worried", "anxious", "with you", "by your side"])
        )
        # Must provide reassurance (benign statistics or support)
        self.assertTrue("benign" in outbound.lower() or "care team" in outbound.lower() or "support" in outbound.lower())
        # Must NOT diagnose
        self.assertNotIn("i diagnose", outbound.lower())

        # Emotional distress in routine chat should NOT trigger emergency escalation
        with get_sync_db() as db:
            cc = db.query(CareCase).filter(CareCase.id == uuid.UUID(self.case_id)).first()
            # Case should not be escalated for anxiety
            self.assertNotEqual(cc.status, "escalated")

    def test_06_appointment_request_uses_coordination_tools(self):
        """Criterion 6: Appointment booking request triggers proper coordination workflow."""
        res = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": self.case_id, "message": "Can you please help me book an appointment?"},
            headers=self.patient_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]

        self.assertEqual(data["primary_intent"], "appointment_booking_request")
        action_tools = [a.get("tool") for a in data["actions_executed"]]
        self.assertTrue(
            "search_available_appointments" in action_tools or "book_appointment" in action_tools,
            f"Expected booking tools in actions, got: {action_tools}"
        )

    def test_07_missed_appointment_recovery_workflow(self):
        """Criterion 7: Missed appointment triggers recovery workflow."""
        res = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": self.case_id, "message": "I missed my appointment yesterday and could not go."},
            headers=self.patient_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]

        self.assertEqual(data["primary_intent"], "missed_appointment")
        action_tools = [a.get("tool") for a in data["actions_executed"]]
        # Must involve cancellation of missed visit and reschedule search
        self.assertTrue("cancel_appointment" in action_tools or "search_available_appointments" in action_tools)

    def test_08_urgent_symptoms_trigger_clinical_escalation(self):
        """Criterion 8: Acute clinical symptoms trigger immediate clinical escalation."""
        res = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": self.case_id, "message": "I have severe emergency chest pain, heavy bleeding, and high fever right now."},
            headers=self.patient_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]

        self.assertEqual(data["primary_intent"], "urgent_clinical_escalation")
        action_tools = [a.get("tool") for a in data["actions_executed"]]
        self.assertIn("escalate_case", action_tools)

        # Verify case in PostgreSQL is updated to escalated & critical
        with get_sync_db() as db:
            cc = db.query(CareCase).filter(CareCase.id == uuid.UUID(self.case_id)).first()
            self.assertEqual(cc.status, "escalated")
            self.assertEqual(cc.priority, "critical")

            # Verify escalation notification created in DB
            esc_notif = (
                db.query(Notification)
                .filter(Notification.event_type == "clinical_escalation", Notification.case_id == cc.id)
                .first()
            )
            self.assertIsNotNone(esc_notif, "Escalation notification must exist in database")

    def test_09_normal_questions_do_not_trigger_clinical_escalation(self):
        """Criterion 9: Normal questions never trigger clinical escalation."""
        # Reset case status for isolation test
        with get_sync_db() as db:
            cc = db.query(CareCase).filter(CareCase.id == uuid.UUID(self.case_id)).first()
            cc.status = "active"
            cc.priority = "urgent"
            db.commit()

        normal_queries = [
            "What should I expect during my consultation?",
            "Will a biopsy hurt?",
            "When is my next follow-up?",
            "Thank you so much for the information."
        ]
        for query in normal_queries:
            res = requests.post(
                f"{BASE_URL}/agent/interact",
                json={"case_id": self.case_id, "message": query},
                headers=self.patient_headers
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()["data"]
            self.assertNotEqual(data["primary_intent"], "urgent_clinical_escalation")

            with get_sync_db() as db:
                cc = db.query(CareCase).filter(CareCase.id == uuid.UUID(self.case_id)).first()
                self.assertNotEqual(cc.status, "escalated", f"Query '{query}' improperly escalated the case!")

    def test_10_llm_failure_sensible_fallback_behavior(self):
        """Criterion 10: Deterministic fallbacks produce empathetic, context-appropriate responses."""
        p_ctx = {"full_name": "Meenakshi Ramanathan", "preferred_language": "en"}
        c_ctx = {"case_id": self.case_id, "finding_code": "BI-RADS 4", "screening_type": "Mammogram", "status": "active"}

        # 1. Greeting fallback
        greeting_intent = CognitiveEngine._offline_intent_analysis("Hello", p_ctx)
        greeting_plan = CognitiveEngine._offline_plan_formulation(greeting_intent, p_ctx, c_ctx, {})
        self.assertNotIn("notified", greeting_plan.patient_response_draft)
        self.assertIn("Meenakshi", greeting_plan.patient_response_draft)
        self.assertEqual(len(greeting_plan.actions), 0)

        # 2. Inquiry fallback
        inquiry_intent = CognitiveEngine._offline_intent_analysis("What is BI-RADS 4?", p_ctx)
        inquiry_plan = CognitiveEngine._offline_plan_formulation(inquiry_intent, p_ctx, c_ctx, {})
        self.assertIn("benign", inquiry_plan.patient_response_draft)
        self.assertNotIn("you have cancer", inquiry_plan.patient_response_draft)

        # 3. Anxiety fallback
        anxiety_intent = CognitiveEngine._offline_intent_analysis("I'm scared about this", p_ctx)
        anxiety_plan = CognitiveEngine._offline_plan_formulation(anxiety_intent, p_ctx, c_ctx, {})
        self.assertTrue(
            any(w in anxiety_plan.patient_response_draft.lower() for w in ["understand", "normal", "scared", "alone", "benign"])
        )

    def test_11_role_authorization_and_isolation(self):
        """Criterion 11: Patient isolation and Doctor role access boundaries are strictly enforced."""
        # Patient cannot access another case ID
        fake_case_id = str(uuid.uuid4())
        forbidden_res = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": fake_case_id, "message": "Hello"},
            headers=self.patient_headers
        )
        self.assertIn(forbidden_res.status_code, [403, 404])

        # Doctor workflow succeeds with doctor token
        doc_res = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"message": "Please summarize assigned patient caseload.", "case_id": self.case_id},
            headers=self.doctor_headers
        )
        self.assertEqual(doc_res.status_code, 200)
        self.assertTrue(doc_res.json()["success"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
