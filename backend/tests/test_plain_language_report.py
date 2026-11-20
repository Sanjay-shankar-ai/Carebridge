"""
CareBridge Task 4 Test Suite: Plain-Language Medical Report Explanation
Tests:
1. Synthetic report produces all 6 required counselling sections.
2. Numbers, dimensions, and categories match the source report exactly (4.2 cm, BI-RADS 4, Category C).
3. Unknown/unreviewed clinical terms not in the patient glossary are flagged and offered to doctor.
4. Failed generation (unreadable/empty report) leaves Stage 4 pending without corrupting state.
5. Replay is idempotent: calling explain_report again does not double-complete or crash.
6. API endpoint POST /api/v1/cases/{case_id}/explain-report works end-to-end for authenticated patient.
7. API SSE streaming endpoint GET /api/v1/cases/{case_id}/explain-report/stream delivers streaming sections.
"""

import os
import sys
import uuid
import pytest
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta, date

repo_root = Path(__file__).resolve().parent.parent.parent
backend_dir = repo_root / "backend"
sys.path.insert(0, str(backend_dir))

from app.database.session import get_sync_db
from app.models.care_case import CareCase
from app.models.case_lifecycle_stage import CaseLifecycleStage
from app.models.patient import Patient, Consent
from app.models.screening import ScreeningResult
from app.models.owner import CaseOwner
from app.services.lifecycle_service import LifecycleService
from app.services.report_explanation_service import ReportExplanationService, REVIEWED_GLOSSARY


SYNTHETIC_MAMMOGRAM_TEXT = """METROPOLITAN COMPREHENSIVE BREAST CENTER
1200 Healthcare Parkway, Medical District • Tel: (555) 019-2834 • Accredited Breast Imaging Center
Patient Name: Meera Krishnan
MRN: MRN-2026-0461
Date of Birth: 1980-05-14 (Age: 46)
Exam Date: November 17, 2026
Referring Clinician: Dr. Arjun Menon, MD
Accession: ACC-2026-8812

STUDY TYPE
Diagnostic Bilateral Digital Mammography with 3D Tomosynthesis (DBT) and Supplementary Right Breast Target Ultrasound.

CLINICAL INDICATION
Routine screening follow-up; patient reports 3-week history of mild localized fullness in right upper quadrant. No nipple discharge. Family history significant for maternal postmenopausal breast cancer.

BREAST DENSITY
Category C: Heterogeneously dense breast tissue, which may obscure small masses.

FINDINGS
Right Breast: There is an irregular, hypoechoic solid mass measuring 4.2 cm in greatest dimension with ill-defined, partially spiculated margins located in the upper outer quadrant at the 10:00 position, approximately 4 cm from the nipple. Associated fine, pleomorphic clustered microcalcifications are identified within and immediately adjacent to the mass. Targeted color Doppler ultrasound confirms internal vascularity.

Left Breast: Normal parenchymal pattern without focal architectural distortion, suspicious mass, or suspicious microcalcifications.

Axilla: Bilateral axillary lymph nodes show preserved fatty hila and normal cortical thickness with no radiologic evidence of adenopathy.

IMPRESSION & ASSESSMENT
4.2 cm dominant solid mass in right breast upper outer quadrant with clustered pleomorphic microcalcifications.
BI-RADS CATEGORY 4: Suspicious Abnormality

RECOMMENDATIONS
1. Ultrasound-guided core needle tissue biopsy of the right breast 10:00 position mass is recommended for definitive histological characterization.
2. Consultation with a breast surgical oncologist (Dr. Arjun Menon) within 14 days.
3. Post-biopsy clip placement and verification mammogram.

Interpreting Radiologist: Sunita Rao, MD (Board Certified Diagnostic Radiologist) • Finalized: 2026-11-18T10:30:00Z
"""


@pytest.fixture
def test_case_stage3_done():
    """Seeds a test case at Stage 3 completed, Stage 4 pending with the synthetic report text."""
    with get_sync_db() as db:
        now = datetime.now(timezone.utc)
        case_id = uuid.uuid4()
        pat_id = uuid.uuid4()
        sr_id = uuid.uuid4()

        owner = db.query(CaseOwner).filter(CaseOwner.email == "arjun.menon@carebridge.com").first()
        if not owner:
            owner = db.query(CaseOwner).first()
        if not owner:
            owner = CaseOwner(
                id=uuid.uuid4(),
                name="Dr. Arjun Menon",
                role="doctor",
                email=f"arjun_{uuid.uuid4().hex[:6]}@carebridge.com",
                facility="Metropolitan Breast Center",
                is_active=True
            )
            db.add(owner)
            db.flush()

        patient = Patient(
            id=pat_id,
            first_name="Meera",
            last_name="Krishnan",
            mrn=f"MRN-T4-{uuid.uuid4().hex[:6].upper()}",
            phone="+15550198888",
            date_of_birth=date(1980, 5, 14),
            preferred_language="en"
        )
        db.add(patient)
        db.flush()

        sr = ScreeningResult(
            id=sr_id,
            patient_id=pat_id,
            screening_type="Mammogram",
            test_date=now - timedelta(days=2),
            finding_code="BI-RADS-4",
            finding_summary="4.2 cm mass in right breast upper outer quadrant with microcalcifications.",
            urgency_level="urgent",
            performing_facility="Metropolitan Breast Center",
            raw_report_data={
                "report_text": SYNTHETIC_MAMMOGRAM_TEXT,
                "extracted_text": SYNTHETIC_MAMMOGRAM_TEXT,
                "filename": "meera_krishnan_mammogram_report.pdf"
            }
        )
        db.add(sr)
        db.flush()

        care_case = CareCase(
            id=case_id,
            case_number=f"CASE-T4-{uuid.uuid4().hex[:6].upper()}",
            patient_id=pat_id,
            screening_result_id=sr_id,
            current_owner_id=owner.id,
            status="notified",
            priority="urgent",
            sla_start_time=now,
            sla_deadline=now + timedelta(days=14),
            case_context={
                "staged_report": {
                    "extracted_text": SYNTHETIC_MAMMOGRAM_TEXT,
                    "safe_filename": "meera_krishnan_mammogram_report.pdf",
                    "file_type": "pdf"
                }
            }
        )
        db.add(care_case)
        db.flush()

        # Initialize lifecycle: Stages 1, 2, 3 completed; Stage 4 pending
        LifecycleService.initialize_lifecycle(care_case, sr, patient, db=db)

        # Advance to Stage 3 completed
        stages = LifecycleService.get_lifecycle_stages(care_case)
        for s in stages:
            if s.get("stage_number") in (1, 2, 3):
                s["status"] = "completed"
                s["completed_at"] = (now - timedelta(hours=12)).isoformat()
            elif s.get("stage_number") >= 4:
                s["status"] = "pending"
                s["completed_at"] = None

        care_case.case_context = dict(care_case.case_context)
        care_case.case_context["lifecycle_stages"] = stages
        care_case.case_context["current_stage_number"] = 4
        care_case.case_context["current_stage_id"] = "PATIENT_UNDERSTANDS"

        # Sync relational rows
        for st_row in db.query(CaseLifecycleStage).filter(CaseLifecycleStage.case_id == care_case.id).all():
            if st_row.stage_number in (1, 2, 3):
                st_row.status = "completed"
                st_row.completed_at = now - timedelta(hours=12)
            elif st_row.stage_number >= 4:
                st_row.status = "pending"
                st_row.completed_at = None
        db.commit()

        yield {
            "case_id": case_id,
            "patient_id": pat_id,
            "sr_id": sr_id,
            "doctor_id": owner.id
        }


def test_synthetic_report_produces_correct_sections(test_case_stage3_done):
    """The synthetic report produces all 6 required counselling sections adhering to grade 6-8."""
    case_id = test_case_stage3_done["case_id"]

    with get_sync_db() as db:
        res = ReportExplanationService.generate_explanation(
            db=db,
            case_id=case_id,
            language="en"
        )
        assert res["success"] is True
        assert res["stage_4_completed"] is True
        data = res["data"]

        # 1. Section: What your report says
        assert "what_your_report_says" in data
        assert len(data["what_your_report_says"]) > 50

        # 2. Section: What these words mean
        assert "what_these_words_mean" in data
        assert "BI-RADS Category 4" in data["what_these_words_mean"]
        assert "Microcalcifications" in data["what_these_words_mean"]
        assert "Heterogeneously Dense" in data["what_these_words_mean"]

        # 3. Section: What your report recommends
        assert "what_your_report_recommends" in data
        assert "core needle" in data["what_your_report_recommends"].lower()
        assert "biopsy" in data["what_your_report_recommends"].lower()

        # 4. Section: What is not certain
        assert "what_is_not_certain" in data
        assert "cannot" in data["what_is_not_certain"].lower()
        assert "benign or cancerous" in data["what_is_not_certain"].lower()

        # 5. Section: Questions you may want to ask your doctor
        assert "questions_for_doctor" in data
        assert "1." in data["questions_for_doctor"]
        assert "2." in data["questions_for_doctor"]
        assert "3." in data["questions_for_doctor"]

        # 6. Section: Warm closing line
        assert "warm_closing" in data
        assert "not" in data["warm_closing"].lower() and "alone" in data["warm_closing"].lower()

        # Verify Stage 4 is completed in the database
        cc = db.query(CareCase).filter(CareCase.id == case_id).first()
        stages = LifecycleService.get_lifecycle_stages(cc)
        stage_4 = next((s for s in stages if s.get("stage_number") == 4), None)
        assert stage_4 is not None
        assert stage_4["status"] == "completed"


def test_numbers_and_categories_match_source_exactly(test_case_stage3_done):
    """Numbers, dimensions, and categories match source text exactly without inference."""
    case_id = test_case_stage3_done["case_id"]

    with get_sync_db() as db:
        res = ReportExplanationService.generate_explanation(db=db, case_id=case_id)
        assert res["success"] is True
        summary = res["data"]["structured_summary"]

        # Match exact measurements and categories
        assert "4.2 cm" in summary["findings"]
        assert "4.2 cm" in summary["impression"]
        assert "10:00 position" in summary["findings"]
        assert "upper outer quadrant" in summary["findings"]
        assert "Category C" in summary["breast_density"]
        assert "Heterogeneously dense" in summary["breast_density"]
        assert "BI-RADS CATEGORY 4" in summary["bi_rads_category"] or "BI-RADS 4" in summary["bi_rads_category"]
        assert "November 17, 2026" in summary["date"]
        assert "core needle tissue biopsy" in summary["recommendation"].lower()


def test_unknown_clinical_term_flagged(test_case_stage3_done):
    """Unknown clinical terms not in the reviewed glossary are flagged for doctor consultation."""
    case_id = test_case_stage3_done["case_id"]

    with get_sync_db() as db:
        res = ReportExplanationService.generate_explanation(db=db, case_id=case_id)
        assert res["success"] is True
        data = res["data"]

        # The synthetic report mentions 'spiculated margins' and 'pleomorphic' which are unreviewed terms
        unknown = data["unknown_terms"]
        assert len(unknown) > 0
        assert any(t in unknown for t in ["spiculated margins", "pleomorphic"])

        # The section explicitly notes them and defers to Dr. Arjun Menon without guessing
        assert "not in our reviewed patient glossary" in data["what_these_words_mean"]
        assert "Dr. Arjun Menon" in data["what_these_words_mean"]


def test_failed_generation_leaves_stage_4_pending():
    """Unreadable or empty report leaves Stage 4 pending and returns an error."""
    with get_sync_db() as db:
        now = datetime.now(timezone.utc)
        case_id = uuid.uuid4()
        pat_id = uuid.uuid4()
        sr_id = uuid.uuid4()

        patient = Patient(
            id=pat_id,
            first_name="TestEmpty",
            last_name="Patient",
            mrn=f"MRN-EMPTY-{uuid.uuid4().hex[:6].upper()}",
            phone="+15550190000",
            date_of_birth=date(1985, 1, 1),
            preferred_language="en"
        )
        db.add(patient)
        db.flush()

        sr = ScreeningResult(
            id=sr_id,
            patient_id=pat_id,
            screening_type="Mammogram",
            test_date=now - timedelta(days=2),
            finding_code="PENDING",
            finding_summary="",
            urgency_level="standard",
            performing_facility="Metropolitan Breast Center",
            raw_report_data={}
        )
        db.add(sr)
        db.flush()

        care_case = CareCase(
            id=case_id,
            case_number=f"CASE-EMPTY-{uuid.uuid4().hex[:6].upper()}",
            patient_id=pat_id,
            screening_result_id=sr_id,
            status="notified",
            priority="standard",
            sla_start_time=now,
            sla_deadline=now + timedelta(days=14),
            case_context={"staged_report": {"extracted_text": ""}}
        )
        db.add(care_case)
        db.commit()

        LifecycleService.initialize_lifecycle(care_case, sr, patient, db=db)

        # Attempt explanation on empty report
        res = ReportExplanationService.generate_explanation(db=db, case_id=case_id)
        assert res["success"] is False
        assert res["stage_4_completed"] is False
        assert "Could not read" in res["error"]

        # Verify Stage 4 remains pending in database
        cc = db.query(CareCase).filter(CareCase.id == case_id).first()
        stages = LifecycleService.get_lifecycle_stages(cc)
        stage_4 = next((s for s in stages if s.get("stage_number") == 4), None)
        assert stage_4 is not None
        assert stage_4["status"] == "pending"


def test_replay_does_not_double_complete(test_case_stage3_done):
    """Replaying explain_report on an already-completed Stage 4 is idempotent."""
    case_id = test_case_stage3_done["case_id"]

    with get_sync_db() as db:
        # First execution advances Stage 4
        res1 = ReportExplanationService.generate_explanation(db=db, case_id=case_id)
        assert res1["success"] is True
        assert res1["stage_4_completed"] is True

        # Second execution (replay) succeeds idempotently without double-completion error
        res2 = ReportExplanationService.generate_explanation(db=db, case_id=case_id)
        assert res2["success"] is True
        assert res2["stage_4_completed"] is True

        cc = db.query(CareCase).filter(CareCase.id == case_id).first()
        stages = LifecycleService.get_lifecycle_stages(cc)
        stage_4 = next((s for s in stages if s.get("stage_number") == 4), None)
        assert stage_4["status"] == "completed"


def test_explain_report_api_endpoint(test_case_stage3_done):
    """API endpoint POST /api/v1/cases/{case_id}/explain-report returns 200 with 6 sections."""
    case_id = str(test_case_stage3_done["case_id"])
    pwd = os.environ.get("DEMO_PATIENT_PASSWORD", "PatientPass123!")

    # Login as Meera Krishnan
    login_res = requests.post(
        "http://127.0.0.1:8000/api/v1/auth/login",
        json={"email": "meera.krishnan@carebridge.com", "password": pwd},
        headers={"Content-Type": "application/json", "X-Bypass-Rate-Limit": "1"},
        timeout=10
    )
    assert login_res.status_code == 200
    token = login_res.json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    res = requests.post(
        f"http://127.0.0.1:8000/api/v1/cases/{case_id}/explain-report",
        json={"language": "en"},
        headers=headers,
        timeout=10
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert "what_your_report_says" in body["data"]
    assert "what_these_words_mean" in body["data"]
    assert "what_your_report_recommends" in body["data"]
    assert "what_is_not_certain" in body["data"]
    assert "questions_for_doctor" in body["data"]
    assert "warm_closing" in body["data"]


def test_explain_report_stream_endpoint(test_case_stage3_done):
    """API endpoint GET /api/v1/cases/{case_id}/explain-report/stream delivers SSE sections."""
    case_id = str(test_case_stage3_done["case_id"])
    pwd = os.environ.get("DEMO_PATIENT_PASSWORD", "PatientPass123!")

    login_res = requests.post(
        "http://127.0.0.1:8000/api/v1/auth/login",
        json={"email": "meera.krishnan@carebridge.com", "password": pwd},
        headers={"Content-Type": "application/json", "X-Bypass-Rate-Limit": "1"},
        timeout=10
    )
    assert login_res.status_code == 200
    token = login_res.json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}

    res = requests.get(
        f"http://127.0.0.1:8000/api/v1/cases/{case_id}/explain-report/stream?lang=en",
        headers=headers,
        stream=True,
        timeout=10
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers.get("content-type", "")

    chunks = []
    for line in res.iter_lines():
        if line:
            decoded = line.decode("utf-8")
            chunks.append(decoded)

    full_stream = "\n".join(chunks)
    assert "event: section" in full_stream
    assert "event: done" in full_stream
    assert "What your report says" in full_stream
    assert "stage_4_completed" in full_stream
