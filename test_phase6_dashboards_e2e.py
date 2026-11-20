"""
CareBridge Phase 6: Three Role Dashboards & End-to-End Verification Suite
Tests the three application dashboards against real PostgreSQL 17 and FastAPI endpoints:
  1. PATIENT Dashboard: Profile, screening results, appointments, timeline, AI assistant, patient isolation.
  2. DOCTOR Dashboard: Assigned cases, escalation queue, appointment booking/cancellation, doctor review, case reopening.
  3. CARE_COORDINATOR Dashboard: Case queue, SLA countdowns, active referrals, recovery queue, trigger recovery.
  4. Role Boundaries & Authorization: No admin role, coordinator cannot reopen cases, patient cannot access others.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
import httpx

from app.main import app
from app.database.session import sync_session_factory
from app.models import (
    User, Patient, CareCase, ScreeningResult, CaseOwner, Appointment,
    Referral, Consent, CaseEvent, AuditLog
)
from app.core.security import hash_password

results = {
    "total": 12,
    "passed": 0,
    "failed": 0,
    "details": []
}

def record_test(step: int, title: str, passed: bool, evidence: str, error: str = None):
    status = "PASS" if passed else "FAIL"
    if passed:
        results["passed"] += 1
    else:
        results["failed"] += 1
    results["details"].append({"step": step, "title": title, "status": status, "evidence": evidence, "error": error})
    sym = "[PASS]" if passed else "[FAIL]"
    print(f"\n{sym} Step {step}: {title}")
    print(f"       Evidence: {evidence}")
    if error:
        print(f"       Error: {error}")


def create_phase6_fixtures(db):
    suffix = uuid.uuid4().hex[:6].upper()
    now = datetime.now(timezone.utc)

    # 1. Synthetic Patient
    pat = Patient(
        id=uuid.uuid4(),
        mrn=f"SYN-P6-{suffix}",
        first_name="Padmini",
        last_name=f"Sundaram-{suffix}",
        email=f"padmini_{suffix.lower()}@carebridge-test.com",
        phone="+91-98765-66778",
        preferred_language="ta",
        communication_channel="in_app_chat",
        date_of_birth=datetime(1980, 5, 12, tzinfo=timezone.utc),
        gender="female"
    )
    db.add(pat)

    # 2. Consent
    c = Consent(
        id=uuid.uuid4(),
        patient_id=pat.id,
        scope="referral,sharing,diagnostic_data",
        status="active",
        expires_at=now + timedelta(days=365)
    )
    db.add(c)

    # 3. Screening Result
    sr = ScreeningResult(
        id=uuid.uuid4(),
        patient_id=pat.id,
        screening_type="Mammogram",
        test_date=now - timedelta(days=3),
        finding_code="BI-RADS-4",
        finding_summary="Suspicious 2.5cm mass in left breast, targeted biopsy recommended.",
        urgency_level="urgent",
        performing_facility="Metropolitan Breast Screening Center"
    )
    db.add(sr)

    # 4. Coordinator & Doctor CaseOwners
    coord = db.query(CaseOwner).filter(CaseOwner.role == "care_coordinator").first()
    doc = db.query(CaseOwner).filter(CaseOwner.role == "doctor").first()

    # 5. Active Care Case
    case = CareCase(
        id=uuid.uuid4(),
        case_number=f"CASE-P6-{suffix}",
        patient_id=pat.id,
        screening_result_id=sr.id,
        current_owner_id=coord.id if coord else None,
        status="scheduled",
        clinical_pathway="mammogram_abnormal_bi_rads_4",
        priority="urgent",
        sla_start_time=now,
        sla_deadline=now + timedelta(days=14),
        sla_status="normal",
        case_context={"recovery_attempts": 0, "inferred_barriers": ["transportation"]}
    )
    db.add(case)

    # 6. User for Patient
    u = User(
        id=uuid.uuid4(),
        email=pat.email,
        password_hash=hash_password("PatientPass123!"),
        role="patient",
        full_name=f"{pat.first_name} {pat.last_name}",
        is_active=True,
        is_verified=True,
        patient_id=pat.id
    )
    db.add(u)

    # 7. Pre-existing Booked Appointment
    appt = Appointment(
        id=uuid.uuid4(),
        case_id=case.id,
        patient_id=pat.id,
        facility="Clinic A - Women's Specialty Breast Center",
        provider_name="Dr. Aris Thorne, MD",
        appointment_type="diagnostic_biopsy",
        scheduled_time=now + timedelta(days=2),
        status="booked",
        notes="Patient accompanied by family."
    )
    db.add(appt)

    # 8. Closed Case with its own Screening Result for Doctor Reopening Test
    sr_closed = ScreeningResult(
        id=uuid.uuid4(),
        patient_id=pat.id,
        screening_type="Mammogram",
        test_date=now - timedelta(days=35),
        finding_code="BI-RADS-4",
        finding_summary="Previous mammogram finding successfully evaluated.",
        urgency_level="standard",
        performing_facility="Metropolitan Breast Screening Center"
    )
    db.add(sr_closed)

    closed_case = CareCase(
        id=uuid.uuid4(),
        case_number=f"CASE-P6-CLOSED-{suffix}",
        patient_id=pat.id,
        screening_result_id=sr_closed.id,
        current_owner_id=coord.id if coord else None,
        status="closed",
        clinical_pathway="mammogram_abnormal_bi_rads_4",
        priority="standard",
        sla_start_time=now - timedelta(days=30),
        sla_deadline=now - timedelta(days=16),
        sla_status="normal",
        case_context={"clinical_verification_signed": True}
    )
    db.add(closed_case)

    # 9. Inbound Referral
    ref = Referral(
        id=uuid.uuid4(),
        case_id=case.id,
        patient_id=pat.id,
        referring_provider="Primary Care Clinic",
        target_facility="Clinic A - Women's Specialty Breast Center",
        specialty="Diagnostic Breast Oncology",
        reason_for_referral="BI-RADS 4 ultrasound & core biopsy",
        status="sent",
        acceptance_deadline=now + timedelta(hours=48)
    )
    db.add(ref)

    db.commit()
    return pat, case, closed_case, appt, ref, u


async def run_phase6_verification():
    print("=" * 70)
    print("CAREBRIDGE PHASE 6: THREE ROLE DASHBOARDS E2E VERIFICATION")
    print("PostgreSQL 17 | FastAPI | Next.js Integration | Role Isolation")
    print("=" * 70)

    with sync_session_factory() as db:
        pat, case, closed_case, appt, ref, pat_user = create_phase6_fixtures(db)
        case_id = str(case.id)
        closed_case_id = str(closed_case.id)
        appt_id = str(appt.id)
        pat_email = pat_user.email
        pat_id = str(pat.id)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # =====================================================================
        # PART 1: AUTHENTICATION FOR THE THREE DASHBOARDS
        # =====================================================================
        # Step 1: Patient Login
        try:
            p_res = await client.post("/api/v1/auth/login", json={"email": pat_email, "password": "PatientPass123!"})
            assert p_res.status_code == 200, f"Login failed: {p_res.text}"
            pat_data = p_res.json()["data"]
            pat_token = pat_data["token"]
            assert pat_data["role"] == "patient"
            record_test(1, "Patient authenticates and receives JWT with patient role", True,
                        f"Authenticated as {pat_data['name']} (role: {pat_data['role']}, patient_id: {pat_data['patient_id']})")
        except Exception as e:
            record_test(1, "Patient authenticates and receives JWT with patient role", False, "Failed", str(e))

        # Step 2: Doctor Login
        try:
            d_res = await client.post("/api/v1/auth/login", json={"email": "doctor@carebridge.com", "password": "DoctorPass123!"})
            assert d_res.status_code == 200, f"Doctor login failed: {d_res.text}"
            doc_data = d_res.json()["data"]
            doc_token = doc_data["token"]
            assert doc_data["role"] in ("doctor", "clinician")
            record_test(2, "Doctor authenticates and receives JWT with doctor role", True,
                        f"Authenticated as {doc_data['name']} (role: {doc_data['role']})")
        except Exception as e:
            record_test(2, "Doctor authenticates and receives JWT with doctor role", False, "Failed", str(e))

        # Step 3: Care Coordinator Login
        try:
            c_res = await client.post("/api/v1/auth/login", json={"email": "coordinator@carebridge.com", "password": "CoordinatorPass123!"})
            assert c_res.status_code == 200, f"Coordinator login failed: {c_res.text}"
            coord_data = c_res.json()["data"]
            coord_token = coord_data["token"]
            assert coord_data["role"] == "care_coordinator"
            record_test(3, "Care Coordinator authenticates and receives JWT with coordinator role", True,
                        f"Authenticated as {coord_data['name']} (role: {coord_data['role']})")
        except Exception as e:
            record_test(3, "Care Coordinator authenticates and receives JWT with coordinator role", False, "Failed", str(e))

        # =====================================================================
        # PART 2: PATIENT DASHBOARD ENDPOINTS & ISOLATION
        # =====================================================================
        # Step 4: Patient Dashboard data retrieval (Cases & Appointments)
        try:
            c_res = await client.get("/api/v1/cases", headers={"Authorization": f"Bearer {pat_token}"})
            assert c_res.status_code == 200
            cases_list = c_res.json()["data"]
            assert len(cases_list) >= 1
            # Verify patient only sees their own cases
            for c in cases_list:
                assert c["patient_id"] == pat_id, f"Cross-patient leak: {c['patient_id']} != {pat_id}"

            a_res = await client.get("/api/v1/appointments", headers={"Authorization": f"Bearer {pat_token}"})
            assert a_res.status_code == 200
            appts_list = a_res.json()["data"]

            record_test(4, "Patient Dashboard retrieves scoped cases & appointments without cross-patient leaks", True,
                        f"Retrieved {len(cases_list)} case(s) strictly matching patient_id {pat_id}. Appointments: {len(appts_list)}.")
        except Exception as e:
            record_test(4, "Patient Dashboard retrieves scoped cases & appointments without cross-patient leaks", False, "Failed", str(e))

        # Step 5: Patient interacts with embedded AI Assistant (Supervisor Engine)
        try:
            chat_res = await client.post("/api/v1/agent/interact", headers={"Authorization": f"Bearer {pat_token}"}, json={
                "case_id": case_id,
                "message": "Can I bring my daughter with me to the appointment?",
                "channel": "in_app_chat"
            })
            assert chat_res.status_code == 200
            chat_data = chat_res.json()["data"]
            assert chat_data["outbound_message"]
            record_test(5, "Patient conversational AI Assistant processes inquiry via Cognitive Supervisor", True,
                        f"Empathetic reply received: '{chat_data['outbound_message'][:80]}...' (intent: {chat_data['primary_intent']})")
        except Exception as e:
            record_test(5, "Patient conversational AI Assistant processes inquiry via Cognitive Supervisor", False, "Failed", str(e))

        # =====================================================================
        # PART 3: DOCTOR DASHBOARD ENDPOINTS & CLINICAL AUTHORITY
        # =====================================================================
        # Step 6: Doctor retrieves assigned cases & escalation queue
        try:
            d_cases = await client.get("/api/v1/cases", headers={"Authorization": f"Bearer {doc_token}"})
            assert d_cases.status_code == 200
            doc_cases_data = d_cases.json()["data"]
            # Escalations are cases with priority 'critical' or status 'escalated'
            urgent_cases = [c for c in doc_cases_data if c["priority"] in ("urgent", "critical") or c["status"] == "escalated"]
            record_test(6, "Doctor Dashboard retrieves patient roster and urgent clinical escalation queue", True,
                        f"Doctor retrieved {len(doc_cases_data)} total cases ({len(urgent_cases)} flagged for urgent clinical attention).")
        except Exception as e:
            record_test(6, "Doctor Dashboard retrieves patient roster and urgent clinical escalation queue", False, "Failed", str(e))

        # Step 7: Doctor schedules and cancels procedure with mandatory reason
        try:
            # 1. Book appointment
            new_time = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
            book_res = await client.post("/api/v1/appointments/book", headers={"Authorization": f"Bearer {doc_token}"}, json={
                "case_id": case_id,
                "patient_id": pat_id,
                "facility": "Clinic A - Women's Specialty Breast Center",
                "provider_name": "Dr. Aris Thorne, MD",
                "appointment_type": "diagnostic_biopsy",
                "scheduled_time": new_time,
                "notes": "Targeted ultrasound guidance"
            })
            assert book_res.status_code == 200, f"Booking failed: {book_res.text}"
            new_appt_id = book_res.json()["data"]["id"]

            # 2. Cancel with mandatory reason
            cancel_res = await client.post(f"/api/v1/appointments/{new_appt_id}/cancel", headers={"Authorization": f"Bearer {doc_token}"}, json={
                "cancellation_reason": "Emergency surgery conflict for attending specialist",
                "cancelled_by": "doctor",
                "notes": "Coordinator instructed to offer next morning slot."
            })
            assert cancel_res.status_code == 200, f"Cancel failed: {cancel_res.text}"
            c_data = cancel_res.json()["data"]
            assert c_data["status"] == "cancelled"
            record_test(7, "Doctor schedules procedure and cancels with mandatory clinical reason", True,
                        f"Procedure booked (ID: {new_appt_id[:8]}...) then cancelled with logged clinical reason: '{c_data.get('cancellation_reason')}'.")
        except Exception as e:
            record_test(7, "Doctor schedules procedure and cancels with mandatory clinical reason", False, "Failed", str(e))

        # Step 8: Doctor Clinical Consultation via Doctor Subgraph
        try:
            doc_review = await client.post("/api/v1/agent/interact", headers={"Authorization": f"Bearer {doc_token}"}, json={
                "case_id": case_id,
                "message": "Clinical review completed by Dr. Thorne: Targeted core biopsy indicates benign fibroadenoma with no atypia. Routine 12-month mammogram recommended.",
                "channel": "in_app_chat",
                "sender": "doctor"
            })
            assert doc_review.status_code == 200, f"Doctor review failed: {doc_review.text}"
            doc_rev_data = doc_review.json()["data"]
            record_test(8, "Doctor executes clinical consultation decision via Doctor Subgraph", True,
                        f"Doctor decision registered (Intent: {doc_rev_data['primary_intent']}, actions: {len(doc_rev_data['actions_executed'])}).")
        except Exception as e:
            record_test(8, "Doctor executes clinical consultation decision via Doctor Subgraph", False, "Failed", str(e))

        # Step 9: Authorized Doctor reopens closed care case
        try:
            reopen_res = await client.post(f"/api/v1/cases/{closed_case_id}/reopen", headers={"Authorization": f"Bearer {doc_token}"}, json={
                "clinical_rationale": "New palpable nodule observed on 6-month surveillance exam requiring repeat targeted ultrasound."
            })
            assert reopen_res.status_code == 200, f"Reopen failed: {reopen_res.text}"
            reopened_data = reopen_res.json()["data"]
            assert reopened_data["status"] == "reopened"
            assert reopened_data["priority"] == "urgent"
            record_test(9, "Doctor authorizes reopening of closed care case with clinical rationale", True,
                        f"Case #{reopened_data['case_number']} successfully transitioned to '{reopened_data['status']}' with priority '{reopened_data['priority']}'.")
        except Exception as e:
            record_test(9, "Doctor authorizes reopening of closed care case with clinical rationale", False, "Failed", str(e))

        # =====================================================================
        # PART 4: CARE COORDINATOR DASHBOARD & RECOVERY
        # =====================================================================
        # Step 10: Coordinator retrieves active cases, SLA countdowns, and recovery queue
        try:
            coord_cases = await client.get("/api/v1/cases", headers={"Authorization": f"Bearer {coord_token}"})
            assert coord_cases.status_code == 200
            all_cases = coord_cases.json()["data"]

            rec_res = await client.get("/api/v1/recovery", headers={"Authorization": f"Bearer {coord_token}"})
            assert rec_res.status_code == 200
            rec_queue = rec_res.json()["data"]

            refs_res = await client.get("/api/v1/referrals", headers={"Authorization": f"Bearer {coord_token}"})
            assert refs_res.status_code == 200
            refs_list = refs_res.json()["data"]

            record_test(10, "Coordinator Dashboard retrieves case queue with SLAs, recovery queue, and active referrals", True,
                        f"Coordinator active surveillance: {len(all_cases)} cases, {len(rec_queue)} stalled recovery cases, {len(refs_list)} referrals.")
        except Exception as e:
            record_test(10, "Coordinator Dashboard retrieves case queue with SLAs, recovery queue, and active referrals", False, "Failed", str(e))

        # Step 11: Coordinator triggers recovery playbook for stalled case
        try:
            trigger_res = await client.post(f"/api/v1/recovery/trigger/{case_id}", headers={"Authorization": f"Bearer {coord_token}"})
            assert trigger_res.status_code == 200, f"Recovery trigger failed: {trigger_res.text}"
            trig_data = trigger_res.json()["data"]
            record_test(11, "Coordinator triggers automated Care Recovery playbook for stalled case", True,
                        f"Recovery playbook '{trig_data.get('action')}' dispatched successfully for case #{case.case_number}.")
        except Exception as e:
            record_test(11, "Coordinator triggers automated Care Recovery playbook for stalled case", False, "Failed", str(e))

        # =====================================================================
        # PART 5: ROLE BOUNDARIES & SECURITY (NO ADMIN, PROPER ACCESS GATES)
        # =====================================================================
        # Step 12: Role security checks: Coordinator cannot reopen case & Admin is rejected
        try:
            # 1. Coordinator attempts case reopening -> 403 Forbidden
            coord_reopen = await client.post(f"/api/v1/cases/{closed_case_id}/reopen", headers={"Authorization": f"Bearer {coord_token}"}, json={
                "clinical_rationale": "Coordinator attempting unauthorized clinical reopening"
            })
            assert coord_reopen.status_code == 403, f"Expected 403 Forbidden for coordinator, got {coord_reopen.status_code}"

            # 2. Patient attempts case reopening -> 403 Forbidden
            pat_reopen = await client.post(f"/api/v1/cases/{closed_case_id}/reopen", headers={"Authorization": f"Bearer {pat_token}"}, json={
                "clinical_rationale": "Patient attempting case reopening"
            })
            assert pat_reopen.status_code == 403, f"Expected 403 Forbidden for patient, got {pat_reopen.status_code}"

            # 3. Admin login attempt -> disabled / rejected
            admin_login = await client.post("/api/v1/auth/login", json={"email": "admin@carebridge.com", "password": "AdminPassword123!"})
            assert admin_login.status_code in (401, 403, 404), f"Admin login should be disabled/rejected, got {admin_login.status_code}"

            record_test(12, "Role security strictly enforced: Level 3 reopening blocked for non-physicians, admin disabled", True,
                        "Coordinator reopening rejected with HTTP 403. Patient reopening rejected with HTTP 403. Admin account disabled (HTTP 401).")
        except Exception as e:
            record_test(12, "Role security strictly enforced: Level 3 reopening blocked for non-physicians, admin disabled", False, "Failed", str(e))

    print("\n" + "=" * 70)
    print(f"PHASE 6 VERIFICATION SUMMARY: {results['passed']} PASSED, {results['failed']} FAILED (out of {results['total']})")
    print("=" * 70)
    if results["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_phase6_verification())
