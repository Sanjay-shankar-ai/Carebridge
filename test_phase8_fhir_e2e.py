"""
CareBridge Phase 8: HL7 FHIR Interoperability End-to-End Verification Suite
PostgreSQL 17 | FastAPI | HL7 FHIR R4 (v4.0.1) | Role Security & Privacy
Verifies:
  1. CapabilityStatement metadata endpoint (/api/v1/fhir/metadata).
  2. Patient resource retrieval & FHIR R4 schema compliance.
  3. DiagnosticReport resource retrieval & LOINC / BI-RADS mappings.
  4. ServiceRequest resource retrieval & referral tracking.
  5. Task resource retrieval & care coordination lifecycle.
  6. Appointment resource retrieval & participant structure.
  7. Communication resource retrieval & multilingual payload.
  8. Consent resource retrieval & privacy scope / provision.
  9. AuditEvent resource retrieval & provenance metadata.
  10. Cross-resource reference integrity (subject.reference -> Patient/{id}).
  11. Patient privacy & strict isolation (403 Forbidden on foreign records).
  12. Role-based ingestion authorization (Patient blocked with 403, Coordinator allowed with 201).
  13. Invalid UUID rejection (400 Bad Request).
  14. Schema validation ($validate) with OperationOutcome (200 for valid, 422 for invalid).
  15. AuditEvent persistence in PostgreSQL for all FHIR reads.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

import uuid
import asyncio
from datetime import datetime, timezone, timedelta
import httpx

from app.database.session import sync_session_factory
from app.models import (
    User, Patient, CareCase, ScreeningResult, CaseOwner, Appointment,
    Referral, Consent, CaseEvent, AuditLog, Communication, Task
)
from app.services.fhir_service import FHIRService
from app.core.security import hash_password

results = {
    "total": 15,
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


def create_phase8_fixtures(db):
    """Creates isolated synthetic test fixtures for Phase 8 FHIR verification."""
    suffix = uuid.uuid4().hex[:6].upper()
    now = datetime.now(timezone.utc)

    # 1. Patients
    pat_a = Patient(
        id=uuid.uuid4(),
        mrn=f"MRN-FHIR-A-{suffix}",
        first_name="Ananya",
        last_name=f"Venkatesh-{suffix}",
        email=f"ananya_{suffix.lower()}@carebridge-test.com",
        phone="+91-98401-22334",
        preferred_language="ta",
        communication_channel="in_app_chat",
        date_of_birth=datetime(1982, 8, 14, tzinfo=timezone.utc),
        gender="female"
    )
    db.add(pat_a)

    pat_b = Patient(
        id=uuid.uuid4(),
        mrn=f"MRN-FHIR-B-{suffix}",
        first_name="Radha",
        last_name=f"Krishnan-{suffix}",
        email=f"radha_{suffix.lower()}@carebridge-test.com",
        phone="+91-98765-44556",
        preferred_language="en",
        communication_channel="sms",
        date_of_birth=datetime(1975, 3, 20, tzinfo=timezone.utc),
        gender="female"
    )
    db.add(pat_b)

    # 2. Screening Result
    sr_a = ScreeningResult(
        id=uuid.uuid4(),
        patient_id=pat_a.id,
        screening_type="Diagnostic Mammogram",
        test_date=now - timedelta(days=3),
        finding_code="BI-RADS-4",
        finding_summary="Suspicious architectural distortion in upper outer quadrant.",
        urgency_level="urgent",
        performing_facility="Metropolitan Breast Screening Center"
    )
    db.add(sr_a)

    # 3. Case Owner (Doctor & Coordinator)
    coord = db.query(CaseOwner).filter(CaseOwner.role == "care_coordinator").first()
    doc = db.query(CaseOwner).filter(CaseOwner.role == "doctor").first()

    # 4. Care Case
    case_a = CareCase(
        id=uuid.uuid4(),
        case_number=f"CASE-FHIR-{suffix}",
        patient_id=pat_a.id,
        screening_result_id=sr_a.id,
        current_owner_id=coord.id if coord else None,
        status="referred",
        clinical_pathway="mammogram_abnormal_bi_rads_4",
        priority="urgent",
        sla_start_time=now - timedelta(days=2),
        sla_deadline=now + timedelta(days=5),
        sla_status="normal"
    )
    db.add(case_a)

    # 5. Referral (ServiceRequest)
    ref_a = Referral(
        id=uuid.uuid4(),
        case_id=case_a.id,
        patient_id=pat_a.id,
        referring_provider="Dr. Sundaramoorthy, MD",
        target_facility="Apollo Specialty Oncology Breast Care Center",
        specialty="Surgical Oncology",
        reason_for_referral="Tissue core biopsy evaluation of BI-RADS-4 lesion",
        status="sent",
        acceptance_deadline=now + timedelta(hours=48)
    )
    db.add(ref_a)

    # 6. Task
    task_a = Task(
        id=uuid.uuid4(),
        case_id=case_a.id,
        title="Coordinate specialized ultrasound guided core biopsy",
        description="Contact patient to verify transportation and confirm diagnostic procedure slot",
        task_type="patient_outreach",
        assigned_to_id=coord.id if coord else None,
        assigned_role="care_coordinator",
        status="pending",
        due_date=now + timedelta(hours=24)
    )
    db.add(task_a)

    # 7. Appointment
    appt_a = Appointment(
        id=uuid.uuid4(),
        case_id=case_a.id,
        patient_id=pat_a.id,
        facility="Apollo Specialty Oncology Breast Care Center",
        provider_name="Dr. Aris Thorne, MD",
        appointment_type="core_biopsy",
        scheduled_time=now + timedelta(days=2),
        status="booked",
        notes="Pre-procedure diagnostic evaluation"
    )
    db.add(appt_a)

    # 8. Communication
    comm_a = Communication(
        id=uuid.uuid4(),
        case_id=case_a.id,
        patient_id=pat_a.id,
        sender="ai_coordinator",
        channel="in_app_chat",
        language="en",
        content="Hello Ananya, your diagnostic biopsy appointment is confirmed with Dr. Thorne.",
        translated_content="வணக்கம் அனன்யா, உங்கள் பயாப்ஸி சந்திப்பு உறுதி செய்யப்பட்டுள்ளது.",
        acknowledged=True,
        sent_at=now - timedelta(hours=1)
    )
    db.add(comm_a)

    # 9. Consent
    consent_a = Consent(
        id=uuid.uuid4(),
        patient_id=pat_a.id,
        scope="care_coordination_outreach",
        status="active",
        granted_at=now - timedelta(days=5)
    )
    db.add(consent_a)

    # 10. AuditLog
    audit_a = AuditLog(
        id=uuid.uuid4(),
        case_id=case_a.id,
        patient_id=pat_a.id,
        actor_type="clinician",
        actor_id="doctor_thorne",
        action="VERIFY_DIAGNOSTIC_REPORT",
        autonomy_level=3,
        rationale="Physician confirmed BI-RADS 4 finding and initiated specialty referral.",
        timestamp=now - timedelta(hours=2)
    )
    db.add(audit_a)

    # 11. User accounts
    user_a = User(
        id=uuid.uuid4(),
        email=pat_a.email,
        password_hash=hash_password("PatientPass123!"),
        role="patient",
        full_name=f"{pat_a.first_name} {pat_a.last_name}",
        is_active=True,
        is_verified=True,
        patient_id=pat_a.id
    )
    db.add(user_a)

    user_b = User(
        id=uuid.uuid4(),
        email=pat_b.email,
        password_hash=hash_password("PatientPass123!"),
        role="patient",
        full_name=f"{pat_b.first_name} {pat_b.last_name}",
        is_active=True,
        is_verified=True,
        patient_id=pat_b.id
    )
    db.add(user_b)

    db.commit()

    return {
        "pat_a_id": str(pat_a.id),
        "pat_b_id": str(pat_b.id),
        "email_a": user_a.email,
        "email_b": user_b.email,
        "sr_a_id": str(sr_a.id),
        "ref_a_id": str(ref_a.id),
        "task_a_id": str(task_a.id),
        "appt_a_id": str(appt_a.id),
        "comm_a_id": str(comm_a.id),
        "consent_a_id": str(consent_a.id),
        "audit_a_id": str(audit_a.id),
        "case_a_id": str(case_a.id),
        "mrn_a": pat_a.mrn
    }


async def run_phase8_verification():
    print("=" * 70)
    print("CAREBRIDGE PHASE 8: HL7 FHIR R4 INTEROPERABILITY VERIFICATION")
    print("PostgreSQL 17 | FastAPI | HL7 FHIR Release 4 (v4.0.1)")
    print("=" * 70)

    with sync_session_factory() as db:
        fix = create_phase8_fixtures(db)

    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=30.0) as client:
        # Authenticate Doctor, Coordinator, Patient A, Patient B
        doc_login = await client.post("/api/v1/auth/login", json={"email": "doctor@carebridge.com", "password": "DoctorPass123!"})
        token_doc = doc_login.json()["data"]["token"]

        coord_login = await client.post("/api/v1/auth/login", json={"email": "coordinator@carebridge.com", "password": "CoordinatorPass123!"})
        token_coord = coord_login.json()["data"]["token"]

        pat_a_login = await client.post("/api/v1/auth/login", json={"email": fix["email_a"], "password": "PatientPass123!"})
        token_pat_a = pat_a_login.json()["data"]["token"]

        pat_b_login = await client.post("/api/v1/auth/login", json={"email": fix["email_b"], "password": "PatientPass123!"})
        token_pat_b = pat_b_login.json()["data"]["token"]

        headers_doc = {"Authorization": f"Bearer {token_doc}"}
        headers_coord = {"Authorization": f"Bearer {token_coord}"}
        headers_pat_a = {"Authorization": f"Bearer {token_pat_a}"}
        headers_pat_b = {"Authorization": f"Bearer {token_pat_b}"}

        # =====================================================================
        # 1. CapabilityStatement Metadata
        # =====================================================================
        try:
            cs_res = await client.get("/api/v1/fhir/metadata")
            assert cs_res.status_code == 200, f"Expected 200, got {cs_res.status_code}"
            assert "application/fhir+json" in cs_res.headers.get("content-type", "")
            cs = cs_res.json()
            assert cs["resourceType"] == "CapabilityStatement"
            assert cs["fhirVersion"] == "4.0.1"
            assert cs["status"] == "active"
            res_types = [r["type"] for r in cs["rest"][0]["resource"]]
            expected_resources = ["Patient", "DiagnosticReport", "ServiceRequest", "Task", "Appointment", "Communication", "Consent", "AuditEvent"]
            for er in expected_resources:
                assert er in res_types, f"Resource {er} missing from CapabilityStatement"

            record_test(1, "CapabilityStatement describes HL7 FHIR R4 server capabilities", True,
                        f"CapabilityStatement (fhirVersion: {cs['fhirVersion']}) verified with all 8 clinical resources.")
        except Exception as e:
            record_test(1, "CapabilityStatement describes HL7 FHIR R4 server capabilities", False, "Failed", str(e))

        # =====================================================================
        # 2. Patient Resource Retrieval & Mappings
        # =====================================================================
        try:
            p_res = await client.get(f"/api/v1/fhir/Patient/{fix['pat_a_id']}", headers=headers_doc)
            assert p_res.status_code == 200
            pat = p_res.json()
            assert pat["resourceType"] == "Patient"
            assert pat["id"] == fix["pat_a_id"]
            assert pat["identifier"][0]["value"] == fix["mrn_a"]
            assert pat["name"][0]["family"] == f"Venkatesh-{fix['mrn_a'].split('-')[-1]}"
            assert pat["communication"][0]["language"]["coding"][0]["code"] == "ta"

            record_test(2, "Patient retrieved with demographics, official MRN identifier & language", True,
                        f"Patient #{pat['id']} verified: Name='{pat['name'][0]['text']}', MRN='{pat['identifier'][0]['value']}'.")
        except Exception as e:
            record_test(2, "Patient retrieved with demographics, official MRN identifier & language", False, "Failed", str(e))

        # =====================================================================
        # 3. DiagnosticReport Resource Retrieval & LOINC / Findings Mappings
        # =====================================================================
        try:
            dr_res = await client.get(f"/api/v1/fhir/DiagnosticReport/{fix['sr_a_id']}", headers=headers_doc)
            assert dr_res.status_code == 200
            dr = dr_res.json()
            assert dr["resourceType"] == "DiagnosticReport"
            assert dr["id"] == fix["sr_a_id"]
            assert dr["status"] == "final"
            assert dr["subject"]["reference"] == f"Patient/{fix['pat_a_id']}"
            assert dr["code"]["coding"][0]["code"] == "24606-6" # LOINC for mammogram
            assert dr["conclusionCode"][0]["coding"][0]["code"] == "BI-RADS-4"

            record_test(3, "DiagnosticReport maps screening type, LOINC coding, BI-RADS code & subject", True,
                        f"DiagnosticReport #{dr['id']} verified with LOINC 24606-6 and conclusionCode BI-RADS-4.")
        except Exception as e:
            record_test(3, "DiagnosticReport maps screening type, LOINC coding, BI-RADS code & subject", False, "Failed", str(e))

        # =====================================================================
        # 4. ServiceRequest Resource Retrieval & Referral Mappings
        # =====================================================================
        try:
            sr_res = await client.get(f"/api/v1/fhir/ServiceRequest/{fix['ref_a_id']}", headers=headers_doc)
            assert sr_res.status_code == 200
            sr = sr_res.json()
            assert sr["resourceType"] == "ServiceRequest"
            assert sr["id"] == fix["ref_a_id"]
            assert sr["intent"] == "order"
            assert sr["subject"]["reference"] == f"Patient/{fix['pat_a_id']}"
            assert "Surgical Oncology" in sr["code"]["text"]
            assert "Apollo Specialty" in sr["performer"][0]["display"]

            record_test(4, "ServiceRequest maps specialist referral, intent, performer facility & reason", True,
                        f"ServiceRequest #{sr['id']} verified: Specialty='{sr['code']['text']}', Performer='{sr['performer'][0]['display']}'.")
        except Exception as e:
            record_test(4, "ServiceRequest maps specialist referral, intent, performer facility & reason", False, "Failed", str(e))

        # =====================================================================
        # 5. Task Resource Retrieval & Care Coordination Mappings
        # =====================================================================
        try:
            t_res = await client.get(f"/api/v1/fhir/Task/{fix['task_a_id']}", headers=headers_coord)
            assert t_res.status_code == 200
            task = t_res.json()
            assert task["resourceType"] == "Task"
            assert task["id"] == fix["task_a_id"]
            assert task["status"] in ("requested", "in-progress", "pending")
            assert task["for"]["reference"] == f"Patient/{fix['pat_a_id']}"
            assert task["owner"]["display"] == "care_coordinator"

            record_test(5, "Task maps care coordination work item, status, priority & owner", True,
                        f"Task #{task['id']} verified: Description='{task['description'][:50]}...', Owner='{task['owner']['display']}'.")
        except Exception as e:
            record_test(5, "Task maps care coordination work item, status, priority & owner", False, "Failed", str(e))

        # =====================================================================
        # 6. Appointment Resource Retrieval & Participant Structure
        # =====================================================================
        try:
            appt_res = await client.get(f"/api/v1/fhir/Appointment/{fix['appt_a_id']}", headers=headers_doc)
            assert appt_res.status_code == 200
            appt = appt_res.json()
            assert appt["resourceType"] == "Appointment"
            assert appt["id"] == fix["appt_a_id"]
            assert appt["status"] == "booked"
            assert appt["start"] is not None
            assert len(appt["participant"]) >= 2
            pat_actor = next((p for p in appt["participant"] if p.get("actor", {}).get("type") == "Patient"), None)
            assert pat_actor is not None
            assert pat_actor["actor"]["reference"] == f"Patient/{fix['pat_a_id']}"

            record_test(6, "Appointment maps procedure visit, time window, status & participants", True,
                        f"Appointment #{appt['id']} verified with Patient participant reference and start timestamp.")
        except Exception as e:
            record_test(6, "Appointment maps procedure visit, time window, status & participants", False, "Failed", str(e))

        # =====================================================================
        # 7. Communication Resource Retrieval & Multilingual Payload
        # =====================================================================
        try:
            comm_res = await client.get(f"/api/v1/fhir/Communication/{fix['comm_a_id']}", headers=headers_doc)
            assert comm_res.status_code == 200
            comm = comm_res.json()
            assert comm["resourceType"] == "Communication"
            assert comm["id"] == fix["comm_a_id"]
            assert comm["status"] == "completed"
            assert comm["subject"]["reference"] == f"Patient/{fix['pat_a_id']}"
            assert len(comm["payload"]) >= 1
            assert "appointment is confirmed" in comm["payload"][0]["contentString"]

            record_test(7, "Communication maps patient touchpoint, channel & translated payloads", True,
                        f"Communication #{comm['id']} verified with {len(comm['payload'])} payload entries.")
        except Exception as e:
            record_test(7, "Communication maps patient touchpoint, channel & translated payloads", False, "Failed", str(e))

        # =====================================================================
        # 8. Consent Resource Retrieval & Privacy Scope
        # =====================================================================
        try:
            c_res = await client.get(f"/api/v1/fhir/Consent/{fix['consent_a_id']}", headers=headers_doc)
            assert c_res.status_code == 200
            consent = c_res.json()
            assert consent["resourceType"] == "Consent"
            assert consent["id"] == fix["consent_a_id"]
            assert consent["status"] == "active"
            assert consent["patient"]["reference"] == f"Patient/{fix['pat_a_id']}"
            assert consent["provision"]["type"] == "permit"

            record_test(8, "Consent maps patient privacy scope, permit provision & validity dates", True,
                        f"Consent #{consent['id']} verified: Status='{consent['status']}', Provision='{consent['provision']['type']}'.")
        except Exception as e:
            record_test(8, "Consent maps patient privacy scope, permit provision & validity dates", False, "Failed", str(e))

        # =====================================================================
        # 9. AuditEvent Resource Retrieval & Security Provenance
        # =====================================================================
        try:
            a_res = await client.get(f"/api/v1/fhir/AuditEvent/{fix['audit_a_id']}", headers=headers_doc)
            assert a_res.status_code == 200
            audit = a_res.json()
            assert audit["resourceType"] == "AuditEvent"
            assert audit["id"] == fix["audit_a_id"]
            assert audit["type"]["code"] == "rest"
            assert audit["outcome"] == "0"
            assert audit["agent"][0]["who"]["identifier"]["value"] == "doctor_thorne"

            record_test(9, "AuditEvent maps action, actor agent, entity reference & outcome", True,
                        f"AuditEvent #{audit['id']} verified: Action='{audit['subtype'][0]['code']}', Actor='{audit['agent'][0]['who']['display']}'.")
        except Exception as e:
            record_test(9, "AuditEvent maps action, actor agent, entity reference & outcome", False, "Failed", str(e))

        # =====================================================================
        # 10. Cross-Resource Reference Integrity
        # =====================================================================
        try:
            # Check DiagnosticReport -> Patient reference resolves to existing patient
            dr_check = await client.get(f"/api/v1/fhir/DiagnosticReport/{fix['sr_a_id']}", headers=headers_doc)
            target_ref = dr_check.json()["subject"]["reference"]
            assert target_ref.startswith("Patient/")
            target_pat_id = target_ref.split("/")[1]

            pat_resolve = await client.get(f"/api/v1/fhir/Patient/{target_pat_id}", headers=headers_doc)
            assert pat_resolve.status_code == 200
            assert pat_resolve.json()["id"] == fix["pat_a_id"]

            record_test(10, "Cross-resource references strictly resolve across clinical relational entities", True,
                        f"DiagnosticReport subject reference '{target_ref}' successfully resolved to Patient #{target_pat_id}.")
        except Exception as e:
            record_test(10, "Cross-resource references strictly resolve across clinical relational entities", False, "Failed", str(e))

        # =====================================================================
        # 11. Patient Privacy & Strict Isolation
        # =====================================================================
        try:
            # Patient A queries their own resources -> 200 OK
            p_a_res = await client.get(f"/api/v1/fhir/Patient/{fix['pat_a_id']}", headers=headers_pat_a)
            assert p_a_res.status_code == 200

            # Patient A searches Patients -> returns ONLY Patient A
            p_search = await client.get("/api/v1/fhir/Patient", headers=headers_pat_a)
            assert p_search.status_code == 200
            assert p_search.json()["total"] == 1
            assert p_search.json()["entry"][0]["resource"]["id"] == fix["pat_a_id"]

            # Patient A attempts to read Patient B's record -> 403 Forbidden
            p_b_unauth = await client.get(f"/api/v1/fhir/Patient/{fix['pat_b_id']}", headers=headers_pat_a)
            assert p_b_unauth.status_code == 403, f"Expected 403, got {p_b_unauth.status_code}"

            # Patient B attempts to read Patient A's DiagnosticReport -> 403 Forbidden
            dr_unauth = await client.get(f"/api/v1/fhir/DiagnosticReport/{fix['sr_a_id']}", headers=headers_pat_b)
            assert dr_unauth.status_code == 403, f"Expected 403, got {dr_unauth.status_code}"

            record_test(11, "Patient privacy strictly isolated: cross-patient resource reads blocked (403 Forbidden)", True,
                        f"Patient A restricted to self (total: 1). Unauthorized Patient B accesses rejected with HTTP 403 Forbidden.")
        except Exception as e:
            record_test(11, "Patient privacy strictly isolated: cross-patient resource reads blocked (403 Forbidden)", False, "Failed", str(e))

        # =====================================================================
        # 12. Role-Based Ingestion Authorization
        # =====================================================================
        try:
            valid_payload = {
                "resourceType": "Patient",
                "id": str(uuid.uuid4()),
                "active": True,
                "name": [{"use": "official", "family": "Kumar", "given": ["Suresh"]}]
            }

            # Patient attempts inbound submission -> 403 Forbidden
            pat_sub = await client.post("/api/v1/fhir/Patient", json=valid_payload, headers=headers_pat_a)
            assert pat_sub.status_code == 403, f"Expected 403, got {pat_sub.status_code}"

            # Coordinator attempts inbound submission -> 201 Created
            coord_sub = await client.post("/api/v1/fhir/Patient", json=valid_payload, headers=headers_coord)
            assert coord_sub.status_code == 201, f"Expected 201, got {coord_sub.status_code}"
            assert coord_sub.json()["issue"][0]["severity"] == "information"

            record_test(12, "Role-based ingestion authorization enforced: patient submission blocked, coordinator permitted", True,
                        f"Patient ingestion rejected with HTTP 403. Coordinator ingestion approved with HTTP 201 Created.")
        except Exception as e:
            record_test(12, "Role-based ingestion authorization enforced: patient submission blocked, coordinator permitted", False, "Failed", str(e))

        # =====================================================================
        # 13. Invalid UUID Rejection
        # =====================================================================
        try:
            bad_uuid_res = await client.get("/api/v1/fhir/Patient/invalid-id-xyz-99", headers=headers_doc)
            assert bad_uuid_res.status_code == 400, f"Expected 400, got {bad_uuid_res.status_code}"

            record_test(13, "Malformed non-UUID identifiers strictly rejected with HTTP 400 Bad Request", True,
                        f"Request with invalid ID returned HTTP 400: '{bad_uuid_res.json().get('detail')}'.")
        except Exception as e:
            record_test(13, "Malformed non-UUID identifiers strictly rejected with HTTP 400 Bad Request", False, "Failed", str(e))

        # =====================================================================
        # 14. Schema Validation ($validate) with OperationOutcome
        # =====================================================================
        try:
            # Valid Patient validation
            valid_p = {
                "resourceType": "Patient",
                "id": str(uuid.uuid4()),
                "active": True,
                "name": [{"use": "official", "family": "Nair", "given": ["Geetha"]}]
            }
            v_res = await client.post("/api/v1/fhir/Patient/validate", json=valid_p)
            assert v_res.status_code == 200
            assert v_res.json()["resourceType"] == "OperationOutcome"
            assert v_res.json()["issue"][0]["severity"] == "information"

            # Invalid Patient validation (mismatched resourceType)
            invalid_p = {
                "resourceType": "Observation",
                "valueString": "Invalid"
            }
            inv_res = await client.post("/api/v1/fhir/Patient/validate", json=invalid_p)
            assert inv_res.status_code == 422
            assert inv_res.json()["resourceType"] == "OperationOutcome"
            assert inv_res.json()["issue"][0]["severity"] == "error"

            record_test(14, "FHIR validation endpoint ($validate) validates payloads and returns OperationOutcome", True,
                        "Valid payload returned OperationOutcome/information (200). Invalid payload returned OperationOutcome/error (422).")
        except Exception as e:
            record_test(14, "FHIR validation endpoint ($validate) validates payloads and returns OperationOutcome", False, "Failed", str(e))

        # =====================================================================
        # 15. AuditEvent Persistence for FHIR Reads
        # =====================================================================
        try:
            # Perform a FHIR read
            await client.get(f"/api/v1/fhir/DiagnosticReport/{fix['sr_a_id']}", headers=headers_doc)

            # Verify in PostgreSQL
            with sync_session_factory() as db:
                audit_records = (
                    db.query(AuditLog)
                    .filter(AuditLog.action == "FHIR_READ_DIAGNOSTICREPORT")
                    .order_by(AuditLog.timestamp.desc())
                    .first()
                )
                assert audit_records is not None, "Expected FHIR_READ_DIAGNOSTICREPORT audit log"
                assert "DiagnosticReport" in audit_records.rationale

            record_test(15, "FHIR resource access automatically persists HIPAA-compliant AuditLog in PostgreSQL", True,
                        f"AuditLog #{audit_records.id} recorded action='{audit_records.action}' at {audit_records.timestamp}.")
        except Exception as e:
            record_test(15, "FHIR resource access automatically persists HIPAA-compliant AuditLog in PostgreSQL", False, "Failed", str(e))

    print("\n" + "=" * 70)
    print(f"PHASE 8 TEST SUMMARY: {results['passed']} PASSED, {results['failed']} FAILED (out of {results['total']})")
    print("=" * 70)
    if results["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_phase8_verification())
