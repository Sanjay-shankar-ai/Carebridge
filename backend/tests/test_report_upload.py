"""
CareBridge Task 3 Test Suite: Coordinator Report Upload with Browse & Validation
Tests:
- Valid PDF passes upload (extracts text, generates preview, state: READY_TO_FINALIZE)
- Upload alone NEVER completes Stage 2
- Finalize report completes Stage 2 through LifecycleService
- Duplicate finalize is idempotent
- Wrong file type rejected by content magic bytes (400)
- Oversize file (> 10 MB) rejected (413/400)
- Corrupt/unreadable PDF leaves Stage 2 pending with FAILED state
- Cross-role upload (patient or doctor) rejected with 403 Forbidden
"""

import os
import uuid
import pytest
import io
import fitz
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from app.database.session import get_sync_db
from app.models.care_case import CareCase
from app.models.case_lifecycle_stage import CaseLifecycleStage
from app.models.patient import Patient, Consent
from app.models.screening import ScreeningResult
from app.models.owner import CaseOwner
from app.services.lifecycle_service import LifecycleService
from app.core.security import create_access_token


@pytest.fixture
def test_case_setup():
    """Seeds an active patient case at Stage 1 completed, Stage 2 pending."""
    with get_sync_db() as db:
        pat_id = uuid.uuid4()
        case_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        sr_id = uuid.uuid4()

        # Care coordinator owner
        owner = db.query(CaseOwner).filter(CaseOwner.role == "care_coordinator").first()
        if not owner:
            owner = CaseOwner(
                id=owner_id,
                name="Priya Nair, RN",
                role="care_coordinator",
                email=f"priya_{uuid.uuid4().hex[:6]}@carebridge.demo",
                facility="CareBridge Breast Health Center",
                is_active=True
            )
            db.add(owner)
            db.flush()

        from datetime import date, datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        patient = Patient(
            id=pat_id,
            first_name="Test",
            last_name=f"Patient_{uuid.uuid4().hex[:4]}",
            mrn=f"MRN-TEST-{uuid.uuid4().hex[:6].upper()}",
            phone=f"+1555{uuid.uuid4().hex[:7]}",
            date_of_birth=date(1980, 5, 12),
            preferred_language="en"
        )
        db.add(patient)
        db.flush()

        sr = ScreeningResult(
            id=sr_id,
            patient_id=pat_id,
            screening_type="Mammogram",
            test_date=now,
            finding_code="PENDING",
            finding_summary="Screening order placed, awaiting radiology report.",
            urgency_level="standard",
            performing_facility="CareBridge Imaging Center",
            raw_report_data={}
        )
        db.add(sr)
        db.flush()

        care_case = CareCase(
            id=case_id,
            case_number=f"CASE-TEST-{uuid.uuid4().hex[:6].upper()}",
            patient_id=pat_id,
            screening_result_id=sr_id,
            current_owner_id=owner.id,
            status="screening_scheduled",
            priority="standard",
            sla_start_time=now,
            sla_deadline=now + timedelta(days=14),
            case_context={"screening_order_id": "ORD-TEST-001"}
        )
        db.add(care_case)
        db.flush()

        # Initialize lifecycle: Stage 1 active/completed, Stage 2 pending
        LifecycleService.initialize_lifecycle(care_case, sr, patient, db=db)

        # Explicitly ensure Stage 2 is pending (not completed) in both JSON and relational table
        stages = LifecycleService.get_lifecycle_stages(care_case)
        for s in stages:
            if s.get("stage_number") == 1:
                s["status"] = "completed"
            elif s.get("stage_number") >= 2:
                s["status"] = "pending"
                s["completed_at"] = None
        care_case.case_context = dict(care_case.case_context)
        care_case.case_context["lifecycle_stages"] = stages
        care_case.case_context["current_stage_number"] = 2
        care_case.case_context["current_stage_id"] = "RESULT_GENERATED"

        # Synchronize relational rows
        for st_row in db.query(CaseLifecycleStage).filter(CaseLifecycleStage.case_id == care_case.id).all():
            if st_row.stage_number == 1:
                st_row.status = "completed"
            elif st_row.stage_number >= 2:
                st_row.status = "pending"
                st_row.completed_at = None
        db.commit()

        yield {
            "case_id": str(case_id),
            "patient_id": str(pat_id),
            "coordinator_id": str(owner.id),
        }


def make_pdf_bytes(text_lines: list) -> bytes:
    """Helper to generate an authentic PDF byte array using ReportLab."""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFont("Helvetica", 11)
    y = 750
    for line in text_lines:
        p.drawString(50, y, line)
        y -= 20
    p.showPage()
    p.save()
    return buffer.getvalue()


def get_auth_token(email: str, default_pass: str, env_var: str) -> str:
    import requests
    pwd = os.environ.get(env_var, default_pass)
    res = requests.post(
        "http://127.0.0.1:8000/api/v1/auth/login",
        json={"email": email, "password": pwd},
        headers={"Content-Type": "application/json", "X-Bypass-Rate-Limit": "1"},
        timeout=10
    )
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return res.json()["data"]["token"]


@pytest.fixture
def coordinator_headers():
    token = get_auth_token("priya.nair@carebridge.com", "CoordinatorPass123!", "DEMO_COORDINATOR_PASSWORD")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def doctor_headers():
    token = get_auth_token("arjun.menon@carebridge.com", "DoctorPass123!", "DEMO_DOCTOR_PASSWORD")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def patient_headers():
    token = get_auth_token("meera.krishnan@carebridge.com", "PatientPass123!", "DEMO_PATIENT_PASSWORD")
    return {"Authorization": f"Bearer {token}"}


def test_valid_pdf_upload_passes(test_case_setup, coordinator_headers):
    """Valid text PDF uploads, validates, extracts text, and sets READY_TO_FINALIZE."""
    import requests
    case_id = test_case_setup["case_id"]

    pdf_bytes = make_pdf_bytes([
        "DIAGNOSTIC MAMMOGRAM REPORT",
        "FINDINGS: Focal asymmetry with grouped pleomorphic microcalcifications in upper outer quadrant.",
        "IMPRESSION: Suspicious abnormality requiring tissue diagnosis.",
        "BI-RADS CATEGORY 4: Suspicious abnormality.",
        "RECOMMENDATION: Core needle biopsy recommended under stereotactic guidance."
    ])

    files = {"file": ("report_meera.pdf", pdf_bytes, "application/pdf")}
    data = {"screening_order_id": "ORD-SCR-001", "screening_type": "Mammogram"}

    res = requests.post(
        f"http://127.0.0.1:8000/api/v1/cases/{case_id}/upload-report-file",
        files=files,
        data=data,
        headers=coordinator_headers
    )

    assert res.status_code == 200, f"Upload failed: {res.text}"
    body = res.json()
    assert body["success"] is True
    data_res = body["data"]
    assert data_res["state"] == "READY_TO_FINALIZE"
    assert "BI-RADS 4" in (data_res["finding_code"] or "")
    assert data_res["preview"] is not None
    assert data_res["stage_2_completed"] is False


def test_upload_alone_never_completes_stage_2(test_case_setup, coordinator_headers):
    """Asserts that uploading a report leaves Stage 2 pending until explicit coordinator finalization."""
    import requests
    case_id = test_case_setup["case_id"]

    pdf_bytes = make_pdf_bytes([
        "DIAGNOSTIC REPORT",
        "BI-RADS 4: Suspicious findings.",
        "FINDINGS: Focal density."
    ])
    files = {"file": ("report_test.pdf", pdf_bytes, "application/pdf")}
    res = requests.post(
        f"http://127.0.0.1:8000/api/v1/cases/{case_id}/upload-report-file",
        files=files,
        headers=coordinator_headers
    )
    assert res.status_code == 200

    # Verify database / lifecycle: Stage 2 MUST NOT be completed
    with get_sync_db() as db:
        c_uuid = uuid.UUID(case_id)
        cc = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        stages = LifecycleService.get_lifecycle_stages(cc)
        stage_2 = next((s for s in stages if s.get("stage_number") == 2), None)
        assert stage_2 is not None
        assert stage_2["status"] != "completed", f"Stage 2 must remain pending after upload alone, found: {stage_2['status']}"


def test_finalize_report_completes_stage_2(test_case_setup, coordinator_headers):
    """Coordinator clicks 'Finalize report', which executes LifecycleService and completes Stage 2."""
    import requests
    case_id = test_case_setup["case_id"]

    # 1. Upload valid file first
    pdf_bytes = make_pdf_bytes([
        "MAMMOGRAM REPORT",
        "BI-RADS CATEGORY 4",
        "FINDINGS: Upper outer quadrant mass.",
        "RECOMMENDATION: Core needle biopsy."
    ])
    files = {"file": ("report.pdf", pdf_bytes, "application/pdf")}
    requests.post(
        f"http://127.0.0.1:8000/api/v1/cases/{case_id}/upload-report-file",
        files=files,
        headers=coordinator_headers
    )

    # 2. Finalize report
    finalize_payload = {
        "finding_code": "BI-RADS 4",
        "finding_summary": "Upper outer quadrant mass requiring biopsy",
        "clinical_recommendation": "Core needle biopsy",
        "requires_doctor_review": False
    }
    fin_res = requests.post(
        f"http://127.0.0.1:8000/api/v1/cases/{case_id}/finalize-report",
        json=finalize_payload,
        headers=coordinator_headers
    )
    assert fin_res.status_code == 200, f"Finalize failed: {fin_res.text}"
    fin_data = fin_res.json()["data"]
    assert fin_data["status"] == "FINALIZED"
    assert fin_data["stage_2_completed"] is True

    # Verify Stage 2 completed in database
    with get_sync_db() as db:
        c_uuid = uuid.UUID(case_id)
        cc = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        stages = LifecycleService.get_lifecycle_stages(cc)
        stage_2 = next((s for s in stages if s.get("stage_number") == 2), None)
        assert stage_2["status"] == "completed"


def test_duplicate_finalize_is_idempotent(test_case_setup, coordinator_headers):
    """Submitting finalize multiple times is completely idempotent."""
    import requests
    case_id = test_case_setup["case_id"]

    # First finalize
    payload = {"finding_code": "BI-RADS 4", "requires_doctor_review": False}
    res1 = requests.post(
        f"http://127.0.0.1:8000/api/v1/cases/{case_id}/finalize-report",
        json=payload,
        headers=coordinator_headers
    )
    assert res1.status_code == 200
    assert res1.json()["data"]["stage_2_completed"] is True

    # Duplicate finalize
    res2 = requests.post(
        f"http://127.0.0.1:8000/api/v1/cases/{case_id}/finalize-report",
        json=payload,
        headers=coordinator_headers
    )
    assert res2.status_code == 200
    assert res2.json()["data"]["stage_2_completed"] is True
    assert "already finalized" in res2.json()["message"]


def test_wrong_file_type_rejected_by_content(test_case_setup, coordinator_headers):
    """File disguised as .pdf but containing plain text or binary must be rejected by magic bytes."""
    import requests
    case_id = test_case_setup["case_id"]

    fake_pdf = b"Hello, this is just plain text masquerading as a PDF."
    files = {"file": ("malicious.pdf", fake_pdf, "application/pdf")}

    res = requests.post(
        f"http://127.0.0.1:8000/api/v1/cases/{case_id}/upload-report-file",
        files=files,
        headers=coordinator_headers
    )
    assert res.status_code == 400
    assert "only authentic PDF, JPG, and PNG" in res.json().get("detail", "")


def test_oversize_rejected(test_case_setup, coordinator_headers):
    """File exceeding 10 MB limit must be rejected with 413 or 400."""
    import requests
    case_id = test_case_setup["case_id"]

    # 10.5 MB fake PDF
    oversized = b"%PDF-1.4\n" + b"A" * (11 * 1024 * 1024)
    files = {"file": ("huge_scan.pdf", oversized, "application/pdf")}

    res = requests.post(
        f"http://127.0.0.1:8000/api/v1/cases/{case_id}/upload-report-file",
        files=files,
        headers=coordinator_headers
    )
    assert res.status_code in (400, 413)
    body = res.json()
    detail = body.get("detail") or body.get("message") or body.get("error") or ""
    assert "exceeds" in detail.lower() or "limit" in detail.lower() or "large" in detail.lower()


def test_corrupt_pdf_leaves_stage_2_pending(test_case_setup, coordinator_headers):
    """Corrupted PDF returns state FAILED and keeps Stage 2 pending."""
    import requests
    case_id = test_case_setup["case_id"]

    corrupt_pdf = b"%PDF-corrupt-data-not-a-valid-structure-%%EOF"
    files = {"file": ("corrupted.pdf", corrupt_pdf, "application/pdf")}

    res = requests.post(
        f"http://127.0.0.1:8000/api/v1/cases/{case_id}/upload-report-file",
        files=files,
        headers=coordinator_headers
    )
    assert res.status_code == 200  # Returns 200 with success=False payload
    body = res.json()
    assert body["success"] is False
    assert body["data"]["state"] == "FAILED"
    assert "Could not read this file" in body["data"]["reason"]
    assert body["data"]["stage_2_completed"] is False

    # Stage 2 MUST remain pending in database
    with get_sync_db() as db:
        c_uuid = uuid.UUID(case_id)
        cc = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        stages = LifecycleService.get_lifecycle_stages(cc)
        stage_2 = next((s for s in stages if s.get("stage_number") == 2), None)
        assert stage_2["status"] != "completed"


def test_cross_role_upload_rejected(test_case_setup, doctor_headers, patient_headers):
    """Only Care Coordinators are authorized to upload reports; Doctors and Patients are blocked with 403."""
    import requests
    case_id = test_case_setup["case_id"]
    pdf_bytes = make_pdf_bytes(["Test report"])
    files = {"file": ("report.pdf", pdf_bytes, "application/pdf")}

    # Doctor attempt
    res_doc = requests.post(
        f"http://127.0.0.1:8000/api/v1/cases/{case_id}/upload-report-file",
        files={"file": ("report.pdf", pdf_bytes, "application/pdf")},
        headers=doctor_headers
    )
    assert res_doc.status_code == 403

    # Patient attempt
    res_pat = requests.post(
        f"http://127.0.0.1:8000/api/v1/cases/{case_id}/upload-report-file",
        files={"file": ("report.pdf", pdf_bytes, "application/pdf")},
        headers=patient_headers
    )
    assert res_pat.status_code == 403
