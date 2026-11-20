"""
CareBridge End-to-End Test Suite for New User Onboarding, Dynamic Case Isolation,
Coordinator Allocation, 5 Whys Root Cause, Test Report Upload, AI Doctor Matching,
Report Download, 1-Click Consultation Completion, and LangSmith Observability.
"""

import os
import sys
import uuid
import asyncio
from datetime import datetime, timezone, timedelta

print("1. Starting script...", flush=True)
os.environ["TESTING"] = "1"
os.environ["FORCE_POSTGRES"] = "1"
sys.path.insert(0, os.path.abspath("backend"))

print("2. Importing httpx...", flush=True)
import httpx
print("3. Importing app...", flush=True)
from app.main import app
print("4. Importing models...", flush=True)
from app.database.session import get_sync_db
from app.models.care_case import CareCase, Task
from app.models.appointment import Appointment
from app.models.screening import ScreeningResult
from app.models.communication import Communication, ConversationSession
print("5. Imports done, launching async...", flush=True)


async def run_verification():
    print("6. Creating ASGITransport...", flush=True)
    transport = httpx.ASGITransport(app=app)
    print("7. Entering AsyncClient context...", flush=True)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("8. AsyncClient ready!", flush=True)
        print("\n======================================================================", flush=True)
        print("CareBridge E2E Multi-User Onboarding & Feature Verification")
        print("======================================================================\n")

        # ----------------------------------------------------------------------
        # TEST 1: LangSmith AI Observability Health Check
        # ----------------------------------------------------------------------
        print(">>> 1. Testing LangSmith AI Observability Endpoint...")
        obs_res = await client.get("/api/v1/health/observability")
        assert obs_res.status_code == 200, f"Observability check failed: {obs_res.text}"
        obs_json = obs_res.json()
        obs_data = obs_json.get("data", obs_json)
        assert "status" in obs_data, "Observability missing status field"
        assert obs_data["project"] == "CareBridge"
        assert obs_data["endpoint"] == "https://api.smith.langchain.com"
        print(f"    [PASS] Observability Active: status={obs_data['status']}, project={obs_data['project']}")

        # ----------------------------------------------------------------------
        # TEST 2: Distinct Patient Registration & Case Isolation
        # ----------------------------------------------------------------------
        print("\n>>> 2. Testing Patient Registration & Case Isolation...")
        rand_id_1 = str(uuid.uuid4())[:8]
        rand_id_2 = str(uuid.uuid4())[:8]

        # Register Patient A
        email_a = f"patient_{rand_id_1}@test.com"
        reg_a = await client.post("/api/v1/auth/register/patient", json={
            "email": email_a,
            "password": "Password123!",
            "first_name": "Aarav",
            "last_name": "Patel",
            "phone": f"+1555{rand_id_1[:7]}",
            "date_of_birth": "1988-04-12",
            "preferred_language": "en"
        })
        assert reg_a.status_code == 201, f"Patient A reg failed: {reg_a.text}"
        data_a = reg_a.json()["data"]
        token_a = data_a["token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # Register Patient B
        email_b = f"patient_{rand_id_2}@test.com"
        reg_b = await client.post("/api/v1/auth/register/patient", json={
            "email": email_b,
            "password": "Password123!",
            "first_name": "Divya",
            "last_name": "Sharma",
            "phone": f"+1555{rand_id_2[:7]}",
            "date_of_birth": "1992-09-24",
            "preferred_language": "en"
        })
        assert reg_b.status_code == 201, f"Patient B reg failed: {reg_b.text}"
        data_b = reg_b.json()["data"]
        token_b = data_b["token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Check DB to verify distinct cases
        with get_sync_db() as db:
            case_a = db.query(CareCase).filter(CareCase.patient_id == uuid.UUID(data_a["patient_id"])).first()
            case_b = db.query(CareCase).filter(CareCase.patient_id == uuid.UUID(data_b["patient_id"])).first()

            assert case_a is not None, "CareCase A was not created"
            assert case_b is not None, "CareCase B was not created"
            assert case_a.case_number != case_b.case_number, "Case numbers must be distinct!"
            assert case_a.status == "intake", f"Initial status should be intake, got {case_a.status}"
            assert case_b.status == "intake", f"Initial status should be intake, got {case_b.status}"
            
            # Check Initial Greeting
            comm_a = db.query(Communication).filter(Communication.case_id == case_a.id).first()
            assert comm_a is not None, "Initial greeting not found"
            assert "Aarav" in comm_a.content
            assert "hospital Care Coordinator" in comm_a.content or "care coordination team" in comm_a.content

            print(f"    [PASS] Patient A: case_number={case_a.case_number}, initial_status={case_a.status}")
            print(f"    [PASS] Patient B: case_number={case_b.case_number}, initial_status={case_b.status}")
            print(f"    [PASS] Onboarding Greeting: \"{comm_a.content}\"")
            case_a_id = str(case_a.id)

        # ----------------------------------------------------------------------
        # TEST 3: Patient Explaining Need & AI Alerting Hospital Coordinator
        # ----------------------------------------------------------------------
        print("\n>>> 3. Testing Inbound Patient Need & Hospital Coordinator Alert...")
        chat_res = await client.post("/api/v1/agent/interact", headers=headers_a, json={
            "case_id": case_a_id,
            "message": "Hi, I am registering through the hospital website. I would like to do a health check and screening for oncology concerns."
        })
        assert chat_res.status_code == 200, f"Chat failed: {chat_res.text}"
        chat_data = chat_res.json()
        agent_reply = chat_data["data"]["outbound_message"]
        print(f"    [REPLY] {agent_reply}")
        assert "Care Coordinator" in agent_reply or "Priya Nair" in agent_reply
        assert "schedule" in agent_reply.lower() or "alerted" in agent_reply.lower()
        # Ensure we do NOT ask the user to pick between multiple coordinators
        assert "Which Care Coordinator would you like to guide your care?" not in agent_reply
        print("    [PASS] AI recorded patient theory and alerted hospital Care Coordinator without prompting for selection.")

        # Verify Alert Task created for Coordinator in DB
        with get_sync_db() as db:
            task = db.query(Task).filter(Task.case_id == uuid.UUID(case_a_id)).first()
            assert task is not None, "Coordinator schedule task not found"
            assert task.task_type == "schedule_screening"
            print(f"    [PASS] Coordinator Alert Task Created: {task.title} (Status: {task.status})")

        # ----------------------------------------------------------------------
        # TEST 4: Care Coordinator Updates Screening Schedule
        # ----------------------------------------------------------------------
        print("\n>>> 4. Testing Hospital Coordinator Updating Screening Schedule...")
        # Login as coordinator
        coord_login = await client.post("/api/v1/auth/login", json={
            "email": "coordinator@carebridge.com",
            "password": "CoordinatorPass123!"
        })
        assert coord_login.status_code == 200, f"Coord login failed: {coord_login.text}"
        coord_token = coord_login.json()["data"]["token"]
        coord_headers = {"Authorization": f"Bearer {coord_token}"}

        target_screening_time = datetime.now(timezone.utc) + timedelta(days=3, hours=10)
        sched_res = await client.post(f"/api/v1/cases/{case_a_id}/schedule-screening", headers=coord_headers, json={
            "scheduled_time": target_screening_time.isoformat(),
            "facility": "Metropolitan Hospital Screening Center",
            "notes": "Patient intake reviewed. Diagnostic mammography and ultrasound allocated."
        })
        assert sched_res.status_code == 200, f"Schedule screening failed: {sched_res.text}"
        sched_data = sched_res.json()["data"]
        assert sched_data["status"] == "screening_scheduled"
        print(f"    [PASS] Screening schedule updated: {sched_data['scheduled_time']} at {sched_data['facility']}")
        print(f"    [PASS] Case status advanced to: {sched_data['status']}")

        # ----------------------------------------------------------------------
        # TEST 5: Missed Screening Visit & AI Proactive Recovery Outreach
        # ----------------------------------------------------------------------
        print("\n>>> 5. Testing Missed Screening Detection & AI Recovery Outreach...")
        missed_res = await client.post(f"/api/v1/cases/{case_a_id}/missed-screening", headers=coord_headers, json={
            "missed_reason": "Patient could not attend due to transportation failure"
        })
        assert missed_res.status_code == 200, f"Missed screening failed: {missed_res.text}"
        missed_data = missed_res.json()["data"]
        assert missed_data["status"] == "missed_visit"
        print(f"    [PASS] Missed visit recorded. Case status: {missed_data['status']}")

        # Patient opens chat after missing screening -> AI proactively reaches out
        recovery_chat_res = await client.post("/api/v1/agent/interact", headers=headers_a, json={
            "case_id": case_a_id,
            "message": "Hi, I missed my appointment because my car broke down."
        })
        assert recovery_chat_res.status_code == 200
        recovery_reply = recovery_chat_res.json()["data"]["outbound_message"]
        print(f"    [REPLY] {recovery_reply}")
        assert "missed" in recovery_reply.lower() or "reschedule" in recovery_reply.lower()
        assert "Care Coordinator" in recovery_reply or "Priya Nair" in recovery_reply
        print("    [PASS] AI companion recognized missed screening with empathy and offered rescheduling support.")

        # ----------------------------------------------------------------------
        # TEST 6: Coordinator Manually Enters Screening Completion
        # ----------------------------------------------------------------------
        print("\n>>> 6. Testing Coordinator Manually Recording Screening Completion...")
        complete_res = await client.post(f"/api/v1/cases/{case_a_id}/complete-screening", headers=coord_headers, json={
            "completion_notes": "Patient rescheduled and attended screening. Clinical imaging completed.",
            "completed_at": datetime.now(timezone.utc).isoformat()
        })
        assert complete_res.status_code == 200, f"Complete screening failed: {complete_res.text}"
        complete_data = complete_res.json()["data"]
        assert complete_data["status"] == "screening_completed"
        print(f"    [PASS] Screening manually completed. Case status: {complete_data['status']}")

        # Patient asks about next steps -> AI confirms completion
        comp_chat_res = await client.post("/api/v1/agent/interact", headers=headers_a, json={
            "case_id": case_a_id,
            "message": "What is the status of my screening now?"
        })
        assert comp_chat_res.status_code == 200
        comp_reply = comp_chat_res.json()["data"]["outbound_message"]
        print(f"    [REPLY] {comp_reply}")
        assert "completed" in comp_reply.lower()
        print("    [PASS] AI companion confirmed screening completion and reassured patient.")

        # ----------------------------------------------------------------------
        # TEST 7: 5 Whys Root Cause Exploration
        # ----------------------------------------------------------------------
        print("\n>>> 7. Testing 5 Whys Clinical Root Cause Exploration...")
        whys_res = await client.post("/api/v1/agent/interact", headers=headers_a, json={
            "case_id": case_a_id,
            "message": "Can we explore 5 whys on why I delayed my checkup?"
        })
        assert whys_res.status_code == 200
        whys_reply = whys_res.json()["data"]["outbound_message"]
        print(f"    [REPLY] {whys_reply[:200]}...")
        assert "5 Whys" in whys_reply or "Why" in whys_reply
        assert "Root" in whys_reply and "Cause" in whys_reply
        print("    [PASS] 5 Whys Root Cause framework returned by agent.")

        # ----------------------------------------------------------------------
        # TEST 8: Coordinator Uploads Test Report & AI Matches Doctors
        # ----------------------------------------------------------------------
        print("\n>>> 8. Testing Coordinator Manual Report Upload & AI Doctor Matching...")
        upload_res = await client.post(f"/api/v1/cases/{case_a_id}/test-report", headers=coord_headers, json={
            "disease_condition": "Breast Oncology - Suspicious Mass",
            "finding_summary": "Mammogram indicates a 1.8cm irregular mass in upper outer quadrant. BI-RADS 4 suspicious for malignancy.",
            "urgency_level": "urgent",
            "performing_facility": "Metropolitan Hospital Screening Center",
            "document_name": "aarav_screening_mammogram.pdf",
            "clinical_notes": "Patient completed screening. AI recommendation for surgical breast specialist requested."
        })
        assert upload_res.status_code == 200, f"Upload report failed: {upload_res.text}"
        upload_data = upload_res.json()["data"]
        print(f"    [PASS] Status advanced to: {upload_data['status']}")
        doctors = upload_data.get("ai_suggested_doctors") or upload_data.get("recommended_doctors", [])
        print(f"    [PASS] AI Recommended Doctors: {len(doctors)} matched")
        for doc in doctors:
            print(f"           - {doc['name']} ({doc.get('facility', '')}) - Match: {doc.get('match_score', 0)}%")
        assert len(doctors) > 0
        assert upload_data["status"] == "result_generated"

        # ----------------------------------------------------------------------
        # TEST 9: Patient Report Download
        # ----------------------------------------------------------------------
        print("\n>>> 9. Testing Patient Diagnostic Report Download...")
        dl_res = await client.get(f"/api/v1/cases/{case_a_id}/report-download", headers=headers_a)
        assert dl_res.status_code == 200, f"Download failed: {dl_res.text}"
        dl_data = dl_res.json()["data"]
        report_text = dl_data.get("report_document_text") or dl_data.get("report_content", "")
        assert "CAREBRIDGE" in report_text and "DIAGNOSTIC REPORT" in report_text
        assert dl_data["patient_name"] == "Aarav Patel"
        print(f"    [PASS] Report generated: {dl_data['filename']}")
        print(f"    [PREVIEW]\n{report_text[:250]}...")

        # ----------------------------------------------------------------------
        # TEST 10: 1-Click Consultation Completion by Doctor
        # ----------------------------------------------------------------------
        print("\n>>> 10. Testing Doctor 1-Click Consultation Completion...")
        # Create an active appointment for case A
        with get_sync_db() as db:
            appt = Appointment(
                id=uuid.uuid4(),
                case_id=uuid.UUID(case_a_id),
                patient_id=uuid.UUID(data_a["patient_id"]),
                provider_name="Dr. Aris Thorne",
                facility="Clinic A - Women's Specialty Breast Center",
                scheduled_time=datetime.now(timezone.utc),
                appointment_type="diagnostic_consultation",
                status="booked"
            )
            db.add(appt)
            db.commit()
            appt_id = str(appt.id)

        # Login as doctor
        doc_login = await client.post("/api/v1/auth/login", json={
            "email": "doctor@carebridge.com",
            "password": "DoctorPass123!"
        })
        assert doc_login.status_code == 200
        doc_token = doc_login.json()["data"]["token"]
        doc_headers = {"Authorization": f"Bearer {doc_token}"}

        comp_res = await client.post(f"/api/v1/appointments/{appt_id}/complete", headers=doc_headers, json={
            "consultation_notes": "Patient consultation conducted. Reviewed biopsy plan and clinical pathway.",
            "next_steps": "Schedule core needle biopsy within 7 days."
        })
        assert comp_res.status_code == 200, f"Complete consultation failed: {comp_res.text}"
        comp_data = comp_res.json()["data"]
        appt_stat = comp_data.get("status") or comp_data.get("appointment_status")
        assert appt_stat == "attended"
        assert comp_data["case_status"] == "consulted"
        print(f"    [PASS] Appointment marked: {appt_stat}")
        print(f"    [PASS] Case auto-updated to: {comp_data['case_status']}")

        print("\n======================================================================")
        print("ALL 8 VERIFICATION PHASES PASSED WITH ZERO ERRORS!")
        print("======================================================================\n")


if __name__ == "__main__":
    asyncio.run(run_verification())
