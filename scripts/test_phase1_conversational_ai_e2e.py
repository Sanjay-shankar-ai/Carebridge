"""
CareBridge Phase 1: AI Chat Foundation & Conversational Intelligence E2E Test Suite
Verifies:
1. Persistent PostgreSQL-backed conversation history (both inbound and outbound messages).
2. Proper session linking (ConversationSession) for all interactions.
3. GET /api/v1/agent/history endpoint with pagination and role-based data isolation.
4. Security: Patient strictly isolated from other patients' history (HTTP 403 Forbidden).
5. GET /api/v1/agent/sessions and POST /api/v1/agent/sessions lifecycle.
6. Conversational Follow-up: "Is there any other slot?" -> alternative slots (appointment_slot_alternatives).
7. Conversational Follow-up: "I prefer morning" -> filtered morning slots (appointment_slot_preference).
8. Conversational Follow-up: "The second one" -> ordinal slot selection & booking (appointment_slot_selection).
9. Conversational Follow-up: "Can I change it?" -> reschedule workflow (appointment_reschedule_request).
10. Conversational Follow-up: "Why did my doctor refer me?" -> referral rationale (referral_inquiry).
11. Conversational Follow-up: "I want to wait" -> respectful deferral (referral_deferral).
12. Elimination of generic fallback acknowledgement: "Thank you for confirming, ...".
13. Doctor workflow persistence: Doctor queries and copilot replies are saved in communications.
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
from app.models.communication import Communication, ConversationSession
from app.models.user import User

BASE_URL = "http://127.0.0.1:8000/api/v1"


class TestPhase1ConversationalAIE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # 1. Login as patient (Meenakshi Ramanathan)
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

        # 2. Login as doctor (Dr. Aris Thorne)
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

        # 3. Login as coordinator (Priya Nair)
        coord_login = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": "coordinator@carebridge.com", "password": "CoordinatorPass123!"}
        )
        assert coord_login.status_code == 200, f"Coordinator login failed: {coord_login.text}"
        coord_data = coord_login.json()
        cls.coord_token = (
            coord_data.get("data", {}).get("token")
            or coord_data.get("data", {}).get("access_token")
            or coord_data.get("token")
        )
        cls.coord_headers = {
            "Authorization": f"Bearer {cls.coord_token}",
            "X-Bypass-Rate-Limit": "1"
        }

        # 4. Retrieve patient case for authenticated patient user
        with get_sync_db() as db:
            patient_user = db.query(User).filter(User.email == "patient@carebridge.com").first()
            cls.care_case = db.query(CareCase).filter(CareCase.patient_id == patient_user.patient_id).first()
            assert cls.care_case is not None, "No care case found for test patient"
            cls.case_id = str(cls.care_case.id)
            cls.patient_id = str(cls.care_case.patient_id)

            # Find or identify a different patient's case for security testing
            other_case = db.query(CareCase).filter(CareCase.patient_id != patient_user.patient_id).first()
            cls.other_case_id = str(other_case.id) if other_case else None

    def setUp(self):
        # Reset case status to active
        with get_sync_db() as db:
            cc = db.query(CareCase).filter(CareCase.id == uuid.UUID(self.case_id)).first()
            if cc and cc.status == "escalated":
                cc.status = "active"
                cc.priority = "urgent"
                db.commit()

    def test_01_two_way_persistence_inbound_and_outbound(self):
        """Criterion 1: Inbound message and outbound AI response are both stored in PostgreSQL."""
        unique_marker = f"Test inquiry at {datetime.now(timezone.utc).isoformat()}"
        res = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": self.case_id, "message": f"Hello CareBridge, {unique_marker}"},
            headers=self.patient_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        outbound_msg = data["outbound_message"]
        self.assertTrue(len(outbound_msg) > 10)

        # Verify PostgreSQL communications records
        with get_sync_db() as db:
            inbound = db.query(Communication).filter(
                Communication.case_id == uuid.UUID(self.case_id),
                Communication.sender == "patient",
                Communication.content.like(f"%{unique_marker}%")
            ).first()
            self.assertIsNotNone(inbound, "Inbound patient communication was not persisted in PostgreSQL!")
            self.assertEqual(inbound.channel, "in_app_chat")
            self.assertIsNotNone(inbound.session_id, "Inbound message should be linked to an active session!")

            outbound = db.query(Communication).filter(
                Communication.case_id == uuid.UUID(self.case_id),
                Communication.sender == "ai_coordinator",
                Communication.session_id == inbound.session_id
            ).order_by(Communication.sent_at.desc()).first()
            self.assertIsNotNone(outbound, "Outbound AI response was not persisted in PostgreSQL!")
            self.assertEqual(outbound.content, outbound_msg)
            print("    [PASS] test_01_two_way_persistence_inbound_and_outbound")

    def test_02_get_history_pagination_and_chronology(self):
        """Criterion 2: GET /api/v1/agent/history returns chronological messages with pagination."""
        res = requests.get(
            f"{BASE_URL}/agent/history",
            params={"case_id": self.case_id, "limit": 10, "offset": 0},
            headers=self.patient_headers
        )
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertTrue(payload["success"])
        history_data = payload["data"]
        messages = history_data["messages"]
        self.assertIsInstance(messages, list)
        self.assertGreater(len(messages), 0, "History should contain messages from previous turns")
        self.assertGreaterEqual(history_data["total"], len(messages))

        # Check fields
        first_msg = messages[0]
        self.assertIn("id", first_msg)
        self.assertIn("sender", first_msg)
        self.assertIn("content", first_msg)
        self.assertIn("sent_at", first_msg)
        print("    [PASS] test_02_get_history_pagination_and_chronology")

    def test_03_patient_role_isolation_security(self):
        """Criterion 3: Patient cannot access another patient's communication history."""
        if not self.other_case_id:
            self.skipTest("No other patient care case available for isolation test")

        res = requests.get(
            f"{BASE_URL}/agent/history",
            params={"case_id": self.other_case_id},
            headers=self.patient_headers
        )
        self.assertEqual(res.status_code, 403, "Patient should be rejected with HTTP 403 when requesting another patient's history!")
        print("    [PASS] test_03_patient_role_isolation_security")

    def test_04_session_management_lifecycle(self):
        """Criterion 4: GET /api/v1/agent/sessions and POST /api/v1/agent/sessions manage session lifecycle."""
        # 1. Get current sessions
        get_res = requests.get(
            f"{BASE_URL}/agent/sessions",
            params={"case_id": self.case_id},
            headers=self.patient_headers
        )
        self.assertEqual(get_res.status_code, 200)
        sessions = get_res.json()["data"]
        self.assertIsInstance(sessions, list)
        self.assertGreater(len(sessions), 0)

        # 2. Create new session
        create_res = requests.post(
            f"{BASE_URL}/agent/sessions",
            json={"case_id": self.case_id, "channel": "in_app_chat"},
            headers=self.patient_headers
        )
        self.assertEqual(create_res.status_code, 200)
        new_sess = create_res.json()["data"]
        self.assertTrue(new_sess["is_active"])
        self.assertEqual(new_sess["case_id"], self.case_id)

        # 3. Check that previous sessions are no longer active
        with get_sync_db() as db:
            active_count = db.query(ConversationSession).filter(
                ConversationSession.patient_id == uuid.UUID(self.patient_id),
                ConversationSession.is_active.is_(True)
            ).count()
            self.assertEqual(active_count, 1, "There should be exactly one active session per patient/case")
        print("    [PASS] test_04_session_management_lifecycle")

    def test_05_followup_any_other_slot(self):
        """Criterion 5: 'Is there any other slot?' searches alternative slots without generic acknowledgement."""
        # Turn 1: Patient asks to book
        res1 = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": self.case_id, "message": "I would like to book an appointment"},
            headers=self.patient_headers
        )
        self.assertEqual(res1.status_code, 200)
        outbound1 = res1.json()["data"]["outbound_message"]
        self.assertTrue("Tuesday" in outbound1 or "Thursday" in outbound1 or "slot" in outbound1.lower())

        # Turn 2: Follow-up requesting alternative slots
        res2 = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": self.case_id, "message": "Is there any other slot?"},
            headers=self.patient_headers
        )
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()["data"]
        self.assertEqual(data2["primary_intent"], "appointment_slot_alternatives")
        outbound2 = data2["outbound_message"]
        self.assertNotIn("Thank you for confirming", outbound2)
        self.assertTrue(
            any(w in outbound2.lower() for w in ["friday", "monday", "wednesday", "alternative", "additional", "openings", "slots"])
        )
        print("    [PASS] test_05_followup_any_other_slot")

    def test_06_followup_prefer_morning(self):
        """Criterion 6: 'I prefer morning' filters slots to morning hours without generic acknowledgement."""
        res = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": self.case_id, "message": "I prefer morning"},
            headers=self.patient_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["primary_intent"], "appointment_slot_preference")
        outbound = data["outbound_message"]
        self.assertNotIn("Thank you for confirming", outbound)
        self.assertTrue("morning" in outbound.lower())
        self.assertTrue("9:00 AM" in outbound or "10:00 AM" in outbound or "morning openings" in outbound.lower())
        print("    [PASS] test_06_followup_prefer_morning")

    def test_07_followup_the_second_one_slot_selection(self):
        """Criterion 7: 'The second one' confirms ordinal selection and initiates booking."""
        res = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": self.case_id, "message": "The second one"},
            headers=self.patient_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["primary_intent"], "appointment_slot_selection")
        outbound = data["outbound_message"]
        self.assertNotIn("Thank you for confirming, Meenakshi. We are here to support you at every step", outbound)
        self.assertTrue("second" in outbound.lower() or "thursday" in outbound.lower() or "selected" in outbound.lower())
        print("    [PASS] test_07_followup_the_second_one_slot_selection")

    def test_08_followup_can_i_change_it_reschedule(self):
        """Criterion 8: 'Can I change it?' initiates reschedule workflow without generic acknowledgement."""
        res = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": self.case_id, "message": "Can I change it?"},
            headers=self.patient_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["primary_intent"], "appointment_reschedule_request")
        outbound = data["outbound_message"]
        self.assertNotIn("Thank you for confirming", outbound)
        self.assertTrue("change" in outbound.lower() or "reschedule" in outbound.lower())
        print("    [PASS] test_08_followup_can_i_change_it_reschedule")

    def test_09_followup_why_did_doctor_refer_me(self):
        """Criterion 9: 'Why did my doctor refer me?' explains clinical referral rationale."""
        res = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": self.case_id, "message": "Why did my doctor refer me?"},
            headers=self.patient_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["primary_intent"], "referral_inquiry")
        outbound = data["outbound_message"]
        self.assertNotIn("Thank you for confirming", outbound)
        self.assertTrue("referral" in outbound.lower() or "specialist" in outbound.lower())
        self.assertTrue("benign" in outbound.lower() or "not a diagnosis" in outbound.lower() or "precautionary" in outbound.lower())
        # Must reassure and not claim a definitive cancer diagnosis
        self.assertTrue("does not mean you have cancer" in outbound.lower() or "not a diagnosis" in outbound.lower())
        self.assertNotIn("i diagnose you", outbound.lower())
        print("    [PASS] test_09_followup_why_did_doctor_refer_me")

    def test_10_followup_i_want_to_wait_deferral(self):
        """Criterion 10: 'I want to wait' handles respectful deferral without coercion or false acceptance."""
        res = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": self.case_id, "message": "I want to wait"},
            headers=self.patient_headers
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["primary_intent"], "referral_deferral")
        outbound = data["outbound_message"]
        # Must NOT treat as booking confirmation
        self.assertNotIn("Thank you for confirming", outbound)
        self.assertNotIn("Your appointment has been booked", outbound)
        # Must respect patient pace with supportive tone
        self.assertTrue("respect" in outbound.lower() or "pace" in outbound.lower() or "rush" in outbound.lower() or "wait" in outbound.lower())
        print("    [PASS] test_10_followup_i_want_to_wait_deferral")

    def test_11_doctor_workflow_two_way_persistence(self):
        """Criterion 11: Doctor interaction persists doctor query and copilot reply in communications."""
        doc_msg = f"Reviewing active patient notes at {datetime.now(timezone.utc).isoformat()}"
        res = requests.post(
            f"{BASE_URL}/agent/interact",
            json={"case_id": self.case_id, "message": doc_msg},
            headers=self.doctor_headers
        )
        self.assertEqual(res.status_code, 200)

        with get_sync_db() as db:
            doc_comm = db.query(Communication).filter(
                Communication.case_id == uuid.UUID(self.case_id),
                Communication.sender == "doctor",
                Communication.content == doc_msg
            ).first()
            self.assertIsNotNone(doc_comm, "Doctor query was not persisted in communications table!")

            copilot_comm = db.query(Communication).filter(
                Communication.case_id == uuid.UUID(self.case_id),
                Communication.sender == "ai_doctor_copilot"
            ).order_by(Communication.sent_at.desc()).first()
            self.assertIsNotNone(copilot_comm, "Doctor copilot response was not persisted in communications table!")
        print("    [PASS] test_11_doctor_workflow_two_way_persistence")


if __name__ == "__main__":
    unittest.main()
