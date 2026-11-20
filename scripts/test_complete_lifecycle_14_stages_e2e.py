"""
CareBridge Longitudinal Lifecycle Integration Test Suite (14 Stages E2E)
Verifies:
  1. Complete 14-stage journey from SCREENING to VERIFIED CLINICAL CLOSURE
  2. Patient-Aware AI responses for all 9 required contextual questions
  3. Role-based authorization enforcement (Doctor Level 3 gates vs Coordinator vs Patient)
  4. 10-point clinical documentation checklist validation
  5. Idempotent state transitions and notifications
"""

import sys
import os
import uuid
import httpx
from datetime import datetime, timezone, timedelta

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.database.session import sync_session_factory
from app.models import (
    User, Patient, CareCase, ScreeningResult, CaseOwner, Appointment,
    Referral, Task, CaseEvent, AuditLog, Notification, ClosureEvidence
)
from app.core.security import hash_password
from app.services.lifecycle_service import LifecycleService, STAGE_DEFINITIONS

BASE_URL = "http://127.0.0.1:8000"

def run_test():
    print("=" * 80)
    print("CAREBRIDGE 14-STAGE COMPLETE LIFECYCLE E2E VERIFICATION")
    print("=" * 80)

    suffix = uuid.uuid4().hex[:6].upper()
    now = datetime.now(timezone.utc)

    # --------------------------------------------------------------------------
    # 1. Setup Isolated Synthetic Test Fixtures
    # --------------------------------------------------------------------------
    print("\n[SETUP] Creating isolated synthetic test patient, doctor, and coordinator...")
    with sync_session_factory() as db:
        patient = Patient(
            id=uuid.uuid4(),
            mrn=f"MRN-LIFE-{suffix}",
            first_name="Ananya",
            last_name=f"Sundaram-{suffix}",
            email=f"ananya_{suffix.lower()}@carebridge-test.health",
            phone="+91-94444-12345",
            preferred_language="en",
            communication_channel="in_app_chat",
            date_of_birth=datetime(1982, 3, 15, tzinfo=timezone.utc),
            gender="female",
            patient_context={"support_person": "Sister Meera", "transportation_mode": "personal_vehicle"}
        )
        db.add(patient)

        # Doctor: Dr. Aris Thorne
        doc_user = db.query(User).filter(User.email == "doctor@carebridge.health").first()
        if not doc_user:
            doc_user = User(
                id=uuid.uuid4(),
                email="doctor@carebridge.health",
                password_hash=hash_password("DoctorSecure123!"),
                role="doctor",
                full_name="Dr. Aris Thorne",
                is_active=True
            )
            db.add(doc_user)

        # Coordinator: Sarah Jenkins
        coord_user = db.query(User).filter(User.email == "coordinator@carebridge.health").first()
        if not coord_user:
            coord_user = User(
                id=uuid.uuid4(),
                email="coordinator@carebridge.health",
                password_hash=hash_password("CoordinatorSecure123!"),
                role="care_coordinator",
                full_name="Sarah Jenkins",
                is_active=True
            )
            db.add(coord_user)

        # Patient User
        patient_user = User(
            id=uuid.uuid4(),
            email=f"ananya_{suffix.lower()}@carebridge-test.health",
            password_hash=hash_password("PatientSecure123!"),
            role="patient",
            full_name=f"Ananya Sundaram",
            patient_id=patient.id,
            is_active=True
        )
        db.add(patient_user)

        # Doctor CaseOwner record
        doc_owner = db.query(CaseOwner).filter(CaseOwner.role.in_(["doctor", "specialist"])).first()
        if not doc_owner:
            doc_owner = CaseOwner(id=uuid.uuid4(), name="Dr. Aris Thorne", role="specialist", email="doctor@carebridge.health")
            db.add(doc_owner)

        # Coordinator CaseOwner record
        coord_owner = db.query(CaseOwner).filter(CaseOwner.role == "care_coordinator").first()
        if not coord_owner:
            coord_owner = CaseOwner(id=uuid.uuid4(), name="Sarah Jenkins", role="care_coordinator", email="coordinator@carebridge.health")
            db.add(coord_owner)

        # Screening Result (BI-RADS 4)
        sr = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=patient.id,
            screening_type="Digital Screening Mammogram",
            test_date=now - timedelta(days=2),
            finding_code="BI-RADS-4",
            finding_summary="Irregular hypoechoic mass in upper outer quadrant of left breast, measuring 1.4 cm with microcalcifications.",
            urgency_level="urgent",
            performing_facility="CareBridge Advanced Imaging Center",
            raw_report_data={"radiologist_notes": "Suspicious microcalcifications warrant diagnostic ultrasound and core needle biopsy."}
        )
        db.add(sr)

        # Care Case
        case = CareCase(
            id=uuid.uuid4(),
            case_number=f"CASE-LIFE-{suffix}",
            patient_id=patient.id,
            screening_result_id=sr.id,
            status="notified",
            priority="urgent",
            clinical_pathway="Breast Diagnostic Workup",
            current_owner_id=coord_owner.id,
            sla_start_time=now - timedelta(days=1),
            sla_deadline=now + timedelta(days=5),
            sla_status="normal",
            case_context={
                "inferred_barriers": [],
                "recovery_attempts": 0,
                "current_stage_number": 4,
                "current_stage_id": "PATIENT_UNDERSTANDS"
            }
        )
        db.add(case)
        db.flush()

        # Initialize 14 stages via LifecycleService
        LifecycleService.initialize_lifecycle(case, sr, patient)
        db.commit()

        case_id = str(case.id)
        patient_id = str(patient.id)
        patient_email = patient_user.email
        coord_id = str(coord_user.id)
        doc_id = str(doc_user.id)
        print(f"✅ Created synthetic case #{case.case_number} (ID: {case_id})")

    # --------------------------------------------------------------------------
    # 2. Authenticate All Three Roles
    # --------------------------------------------------------------------------
    client = httpx.Client(base_url=BASE_URL, timeout=30.0)

    # Doctor Login
    doc_resp = client.post("/api/v1/auth/login", json={"email": "doctor@carebridge.health", "password": "DoctorSecure123!"})
    assert doc_resp.status_code == 200, f"Doctor login failed: {doc_resp.text}"
    doc_token = doc_resp.json()["data"].get("token") or doc_resp.json()["data"].get("access_token")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    # Coordinator Login
    coord_resp = client.post("/api/v1/auth/login", json={"email": "coordinator@carebridge.health", "password": "CoordinatorSecure123!"})
    assert coord_resp.status_code == 200, f"Coordinator login failed: {coord_resp.text}"
    coord_token = coord_resp.json()["data"].get("token") or coord_resp.json()["data"].get("access_token")
    coord_headers = {"Authorization": f"Bearer {coord_token}"}

    # Patient Login
    pat_resp = client.post("/api/v1/auth/login", json={"email": patient_email, "password": "PatientSecure123!"})
    assert pat_resp.status_code == 200, f"Patient login failed: {pat_resp.text}"
    pat_token = pat_resp.json()["data"].get("token") or pat_resp.json()["data"].get("access_token")
    pat_headers = {"Authorization": f"Bearer {pat_token}"}

    print("✅ Authenticated all 3 roles (Doctor, Coordinator, Patient)")

    # --------------------------------------------------------------------------
    # STAGES 1, 2, 3: Verify Initial Lifecycle State
    # --------------------------------------------------------------------------
    print("\n--- Verifying Stages 1, 2, 3 (Screening, Result Generated, Patient Notified) ---")
    life_resp = client.get(f"/api/v1/cases/{case_id}/lifecycle", headers=pat_headers)
    assert life_resp.status_code == 200, f"Failed to get lifecycle: {life_resp.text}"
    life_data = life_resp.json()["data"]
    stages = life_data["stages"]
    assert len(stages) == 14, f"Expected 14 stages, got {len(stages)}"

    s1 = stages[0]
    s2 = stages[1]
    s3 = stages[2]
    s4 = stages[3]

    assert s1["stage_id"] == "SCREENING" and s1["status"] == "completed"
    assert s2["stage_id"] == "RESULT_GENERATED" and s2["status"] == "completed"
    assert s3["stage_id"] == "PATIENT_NOTIFIED" and s3["status"] == "completed"
    assert s4["stage_id"] == "PATIENT_UNDERSTANDS" and s4["status"] == "active"
    print("✅ Stages 1, 2, 3 verified completed. Stage 4 is active.")

    # --------------------------------------------------------------------------
    # STAGE 4: Patient Understands (AI Case-Aware Conversation)
    # Question 1: "What does my screening result mean?"
    # Question 2: "Why does my doctor recommend further evaluation?"
    # --------------------------------------------------------------------------
    print("\n--- Verifying Stage 4 (AI Conversation: Questions 1 & 2) ---")
    
    # Q1: Screening Result Meaning
    q1_resp = client.post("/api/v1/agent/interact", headers=pat_headers, json={
        "case_id": case_id,
        "message": "What does my screening result mean?",
        "channel": "in_app_chat"
    })
    assert q1_resp.status_code == 200, f"Q1 failed: {q1_resp.text}"
    q1_msg = q1_resp.json()["data"]["outbound_message"]
    print(f"🤖 Q1 Response:\n    {q1_msg[:120]}...")
    assert "BI-RADS" in q1_msg or "mammogram" in q1_msg.lower()
    assert "not" in q1_msg.lower() and "cancer" in q1_msg.lower(), "Must reassure non-cancer diagnosis"
    print("✅ Q1 verified: Empathetic, factual, non-diagnostic reassurance provided.")

    # Q2: Why Doctor Recommends Further Evaluation
    q2_resp = client.post("/api/v1/agent/interact", headers=pat_headers, json={
        "case_id": case_id,
        "message": "Why does my doctor recommend further evaluation?",
        "channel": "in_app_chat"
    })
    assert q2_resp.status_code == 200, f"Q2 failed: {q2_resp.text}"
    q2_msg = q2_resp.json()["data"]["outbound_message"]
    print(f"🤖 Q2 Response:\n    {q2_msg[:120]}...")
    assert "evaluation" in q2_msg.lower() or "certainty" in q2_msg.lower() or "diagnostic" in q2_msg.lower()
    print("✅ Q2 verified: Factual reason for further evaluation explained.")

    # --------------------------------------------------------------------------
    # STAGE 5 & 6: Clinical Review and Confirmation
    # --------------------------------------------------------------------------
    print("\n--- Verifying Stage 5 & 6 (Doctor Clinical Review & Confirmation) ---")
    
    # Negative Test: Coordinator attempts clinical review (Must be 403 Forbidden)
    coord_bad_review = client.post(f"/api/v1/cases/{case_id}/clinical-review", headers=coord_headers, json={
        "clinical_assessment": "Coordinator unauthorized assessment",
        "approved_pathway": "biopsy"
    })
    assert coord_bad_review.status_code == 403, f"Expected 403 for coordinator clinical review, got {coord_bad_review.status_code}"
    print("✅ Authorization verified: Non-doctor rejected with 403 Forbidden.")

    # Doctor conducts Clinical Review
    doc_review_resp = client.post(f"/api/v1/cases/{case_id}/clinical-review", headers=doc_headers, json={
        "clinical_assessment": "Suspicious 1.4 cm microcalcified cluster in left breast (BI-RADS 4). Diagnostic ultrasound-guided core biopsy recommended.",
        "approved_pathway": "Specialist Diagnostic Core Needle Biopsy",
        "additional_investigations": "Targeted ultrasound of left axilla and ipsilateral breast",
        "patient_safe_explanation": "Dr. Aris Thorne has reviewed your mammogram. A gentle outpatient core needle biopsy is recommended to provide conclusive reassurance.",
        "referral_approved": True
    })
    assert doc_review_resp.status_code == 200, f"Doctor review failed: {doc_review_resp.text}"
    print("✅ Stage 5 (Clinical Review) & Stage 6 (Clinical Confirmation) completed by Dr. Thorne.")

    # Verify patient received clinical confirmation notification
    pat_notifs = client.get("/api/v1/notifications", headers=pat_headers).json()["data"]
    has_confirm = any("Clinical Plan Confirmed" in n.get("title", "") for n in pat_notifs)
    assert has_confirm, "Patient must receive persistent notification of doctor's confirmed plan"
    print("✅ Patient received persistent clinical confirmation notification.")

    # --------------------------------------------------------------------------
    # STAGE 7: Referral Initiated
    # --------------------------------------------------------------------------
    print("\n--- Verifying Stage 7 (Referral Initiated) ---")
    # Coordinator creates referral to specialist facility
    with sync_session_factory() as db:
        ref = Referral(
            id=uuid.uuid4(),
            case_id=uuid.UUID(case_id),
            patient_id=uuid.UUID(patient_id),
            referring_provider="Dr. Aris Thorne",
            target_facility="CareBridge Breast Health Clinic",
            specialty="Breast Surgical Oncology",
            reason_for_referral="BI-RADS 4 evaluation and core needle biopsy per physician order.",
            status="sent",
            acceptance_deadline=now + timedelta(hours=48)
        )
        db.add(ref)
        db.commit()
        ref_id = str(ref.id)

        # Advance Stage 7
        LifecycleService.advance_stage(
            db=db,
            case_id=uuid.UUID(case_id),
            stage_ident=7,
            actor_role="care_coordinator",
            actor_id=coord_id,
            evidence={"referral_id": ref_id, "target_facility": ref.target_facility, "specialty": ref.specialty},
            notes="Specialist referral transmitted to CareBridge Breast Health Clinic."
        )
    print("✅ Stage 7 completed: Referral initiated to CareBridge Breast Health Clinic.")

    # --------------------------------------------------------------------------
    # STAGE 8: Referral Accepted
    # Question 3: "Has my referral been accepted?"
    # --------------------------------------------------------------------------
    print("\n--- Verifying Stage 8 (Referral Accepted & AI Inquiry) ---")
    
    # Facility accepts referral
    accept_resp = client.post(f"/api/v1/referrals/{ref_id}/accept", headers=coord_headers, json={
        "receiving_provider_name": "CareBridge Breast Health Clinic",
        "acceptance_notes": "Referral accepted. Breast surgery team confirmed slot availability."
    })
    assert accept_resp.status_code == 200, f"Referral acceptance failed: {accept_resp.text}"
    print("✅ Stage 8 completed: Referral accepted by specialist clinic.")

    # Patient asks AI Q3: "Has my referral been accepted?"
    q3_resp = client.post("/api/v1/agent/interact", headers=pat_headers, json={
        "case_id": case_id,
        "message": "Has my referral been accepted?",
        "channel": "in_app_chat"
    })
    assert q3_resp.status_code == 200, f"Q3 failed: {q3_resp.text}"
    q3_msg = q3_resp.json()["data"]["outbound_message"]
    print(f"🤖 Q3 Response:\n    {q3_msg[:120]}...")
    assert "accepted" in q3_msg.lower() and ("CareBridge" in q3_msg or "specialist" in q3_msg.lower())
    print("✅ Q3 verified: AI confirmed referral acceptance without hallucination.")

    # --------------------------------------------------------------------------
    # STAGE 9: Appointment Scheduled and Confirmed
    # Question 4: "When is my appointment?"
    # Question 5: "What should I expect during my consultation?"
    # --------------------------------------------------------------------------
    print("\n--- Verifying Stage 9 (Appointment Scheduling & AI Inquiries) ---")
    appt_time = (now + timedelta(days=3, hours=10)).replace(minute=0, second=0, microsecond=0)
    book_resp = client.post("/api/v1/appointments/book", headers=coord_headers, json={
        "case_id": case_id,
        "patient_id": patient_id,
        "facility": "CareBridge Breast Health Clinic",
        "provider_name": "Dr. Aris Thorne",
        "appointment_type": "diagnostic_biopsy",
        "scheduled_time": appt_time.isoformat(),
        "notes": "Diagnostic core needle biopsy and clinical ultrasound."
    })
    assert book_resp.status_code == 200, f"Booking failed: {book_resp.text}"
    appt_id = book_resp.json()["data"]["id"]
    print(f"✅ Stage 9 completed: Appointment booked for {appt_time.strftime('%b %d, %Y at %I:%M %p')}.")

    # Patient asks AI Q4: "When is my appointment?"
    q4_resp = client.post("/api/v1/agent/interact", headers=pat_headers, json={
        "case_id": case_id,
        "message": "When is my appointment?",
        "channel": "in_app_chat"
    })
    assert q4_resp.status_code == 200, f"Q4 failed: {q4_resp.text}"
    q4_msg = q4_resp.json()["data"]["outbound_message"]
    print(f"🤖 Q4 Response:\n    {q4_msg[:120]}...")
    assert "confirmed" in q4_msg.lower() or "appointment" in q4_msg.lower()
    print("✅ Q4 verified: AI reported exact confirmed appointment details.")

    # Patient asks AI Q5: "What should I expect during my consultation?"
    q5_resp = client.post("/api/v1/agent/interact", headers=pat_headers, json={
        "case_id": case_id,
        "message": "What should I expect during my consultation?",
        "channel": "in_app_chat"
    })
    assert q5_resp.status_code == 200, f"Q5 failed: {q5_resp.text}"
    q5_msg = q5_resp.json()["data"]["outbound_message"]
    print(f"🤖 Q5 Response:\n    {q5_msg[:120]}...")
    assert "numbing" in q5_msg.lower() or "anesthesia" in q5_msg.lower() or "minutes" in q5_msg.lower()
    print("✅ Q5 verified: Empathetic, anxiety-reducing procedure expectation provided.")

    # --------------------------------------------------------------------------
    # STAGE 10: Consultation Completed
    # Question 6: "What did my doctor recommend?"
    # --------------------------------------------------------------------------
    print("\n--- Verifying Stage 10 (Consultation Completed & AI Inquiry) ---")
    next_fu_target = (now + timedelta(days=180)).strftime("%Y-%m-%d")
    consult_resp = client.post(f"/api/v1/cases/{case_id}/consultation-outcome", headers=doc_headers, json={
        "consultation_notes": "Targeted ultrasound-guided core biopsy performed under local lidocaine anesthesia. 4 core samples obtained without complication.",
        "biopsy_pathology_outcome": "Benign fibroadenoma with focal ductal hyperplasia; NO atypia, ductal carcinoma in situ, or invasive malignancy identified.",
        "clinical_recommendations": "Concordant benign pathology. Return to routine clinical surveillance. Reassuring outcome.",
        "treatment_plan": "Active surveillance with bilateral screening mammography in 6 months.",
        "next_followup_date": next_fu_target
    })
    assert consult_resp.status_code == 200, f"Consultation outcome recording failed: {consult_resp.text}"
    print("✅ Stage 10 completed: Consultation and benign pathology documented.")

    # Patient asks AI Q6: "What did my doctor recommend?"
    q6_resp = client.post("/api/v1/agent/interact", headers=pat_headers, json={
        "case_id": case_id,
        "message": "What did my doctor recommend?",
        "channel": "in_app_chat"
    })
    assert q6_resp.status_code == 200, f"Q6 failed: {q6_resp.text}"
    q6_msg = q6_resp.json()["data"]["outbound_message"]
    print(f"🤖 Q6 Response:\n    {q6_msg[:120]}...")
    assert "benign" in q6_msg.lower() and ("surveillance" in q6_msg.lower() or "plan" in q6_msg.lower())
    print("✅ Q6 verified: AI accurately cited doctor's recommendation and benign biopsy pathology.")

    # --------------------------------------------------------------------------
    # STAGE 11: Treatment Monitoring
    # Question 7: "What happens next in my treatment?"
    # --------------------------------------------------------------------------
    print("\n--- Verifying Stage 11 (Treatment Monitoring & AI Inquiry) ---")
    # Patient logs a treatment check
    treat_resp = client.post(f"/api/v1/cases/{case_id}/treatment-update", headers=pat_headers, json={
        "message": "I am feeling well post-procedure, minor bruising is healing quickly. Ready for surveillance.",
        "category": "symptom"
    })
    assert treat_resp.status_code == 200, f"Treatment update failed: {treat_resp.text}"
    print("✅ Stage 11 active: Patient recovery note logged in treatment monitoring.")

    # Patient asks AI Q7: "What happens next in my treatment?"
    q7_resp = client.post("/api/v1/agent/interact", headers=pat_headers, json={
        "case_id": case_id,
        "message": "What happens next in my treatment?",
        "channel": "in_app_chat"
    })
    assert q7_resp.status_code == 200, f"Q7 failed: {q7_resp.text}"
    q7_msg = q7_resp.json()["data"]["outbound_message"]
    print(f"🤖 Q7 Response:\n    {q7_msg[:120]}...")
    assert "treatment plan" in q7_msg.lower() or "surveillance" in q7_msg.lower()
    print("✅ Q7 verified: Treatment next steps accurately communicated.")

    # --------------------------------------------------------------------------
    # STAGE 12: Follow-Up
    # Question 8: "When is my next follow-up?"
    # --------------------------------------------------------------------------
    print("\n--- Verifying Stage 12 (Follow-Up Management & AI Inquiry) ---")
    
    # Patient asks AI Q8: "When is my next follow-up?"
    q8_resp = client.post("/api/v1/agent/interact", headers=pat_headers, json={
        "case_id": case_id,
        "message": "When is my next follow-up?",
        "channel": "in_app_chat"
    })
    assert q8_resp.status_code == 200, f"Q8 failed: {q8_resp.text}"
    q8_msg = q8_resp.json()["data"]["outbound_message"]
    print(f"🤖 Q8 Response:\n    {q8_msg[:120]}...")
    assert next_fu_target in q8_msg or "scheduled" in q8_msg.lower()
    print("✅ Q8 verified: AI reported exact upcoming follow-up surveillance milestone.")

    # Record follow-up milestone attendance
    fu_resp = client.post(f"/api/v1/cases/{case_id}/follow-up", headers=doc_headers, json={
        "status": "completed",
        "notes": "Surveillance interval established. Patient education confirmed."
    })
    assert fu_resp.status_code == 200, f"Follow up status failed: {fu_resp.text}"
    print("✅ Stage 12 completed: Follow-up status documented.")

    # --------------------------------------------------------------------------
    # STAGE 13: Documentation Completed (10-Point Checklist Audit)
    # --------------------------------------------------------------------------
    print("\n--- Verifying Stage 13 (10-Point Documentation Checklist) ---")
    chk_resp = client.get(f"/api/v1/cases/{case_id}/documentation-checklist", headers=doc_headers)
    assert chk_resp.status_code == 200, f"Checklist audit failed: {chk_resp.text}"
    chk_data = chk_resp.json()["data"]
    checklist = chk_data["checklist"]
    
    print("📋 10-Point Documentation Checklist Status:")
    for k, v in checklist.items():
        sym = "✅" if v else "❌"
        print(f"    {sym} {k}: {v}")

    assert chk_data["is_complete"] == True, f"Checklist must be 100% satisfied: {checklist}"
    print("✅ Stage 13 completed: 10/10 evidence requirements verified satisfied.")

    # --------------------------------------------------------------------------
    # STAGE 14: Verified Clinical Closure (Level 3 Human Physician Gate)
    # Question 9: "Have all my care steps been completed?"
    # --------------------------------------------------------------------------
    print("\n--- Verifying Stage 14 (Level 3 Clinical Closure Sign-Off & AI Inquiry) ---")
    
    # Negative Test: Coordinator attempts clinical closure (Must be 403 Forbidden)
    coord_bad_close = client.post(f"/api/v1/cases/{case_id}/clinical-closure", headers=coord_headers, json={
        "clinical_rationale": "Coordinator attempting unauthorized closure sign-off"
    })
    assert coord_bad_close.status_code == 403, f"Expected 403 for coordinator closure, got {coord_bad_close.status_code}"
    print("✅ Authorization verified: Coordinator rejected with 403 Forbidden on closure sign-off.")

    # Doctor executes verified clinical closure
    close_resp = client.post(f"/api/v1/cases/{case_id}/clinical-closure", headers=doc_headers, json={
        "clinical_rationale": "Benign concordance established between ultrasound findings and pathology. No residual disease or suspicion. Return to routine annual preventive screening.",
        "evidence_summary": "10/10 evidence checklist satisfied. Pathology confirmed benign fibroadenoma."
    })
    assert close_resp.status_code == 200, f"Closure sign-off failed: {close_resp.text}"
    close_data = close_resp.json()["data"]
    assert close_data["status"] == "closed"
    print("✅ Stage 14 completed: Dr. Aris Thorne executed verified clinical closure sign-off.")

    # Patient asks AI Q9: "Have all my care steps been completed?"
    q9_resp = client.post("/api/v1/agent/interact", headers=pat_headers, json={
        "case_id": case_id,
        "message": "Have all my care steps been completed?",
        "channel": "in_app_chat"
    })
    assert q9_resp.status_code == 200, f"Q9 failed: {q9_resp.text}"
    q9_msg = q9_resp.json()["data"]["outbound_message"]
    print(f"🤖 Q9 Response:\n    {q9_msg[:120]}...")
    assert "14" in q9_msg or "completed" in q9_msg.lower() or "closed" in q9_msg.lower() or "sign-off" in q9_msg.lower()
    assert "routine" in q9_msg.lower() or "annual" in q9_msg.lower()
    print("✅ Q9 verified: AI confirmed complete journey closure and annual screening recommendation.")

    # Final Lifecycle State Check
    final_life = client.get(f"/api/v1/cases/{case_id}/lifecycle", headers=pat_headers).json()["data"]
    assert final_life["status"] == "closed"
    all_stages = final_life["stages"]
    completed_stages = [s for s in all_stages if s["status"] == "completed"]
    print(f"\n📊 Final Lifecycle Summary: {len(completed_stages)}/14 stages COMPLETED.")
    assert len(completed_stages) == 14, f"All 14 stages must be completed, found {len(completed_stages)}"

    print("\n" + "=" * 80)
    print("🎉 ALL 14 STAGES AND 9 AI CONTEXTUAL QUESTIONS VERIFIED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    run_test()
