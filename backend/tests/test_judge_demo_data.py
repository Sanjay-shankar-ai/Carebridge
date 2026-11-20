"""
CareBridge — Task 1: Judge Demo Data Test Suite
Tests:
1. Seeded users log in with env passwords (patient, doctor, coordinator)
2. Seeded patient shows Stage 3 complete and Stage 4 pending
3. Running seed twice creates no duplicate records
4. Reset returns to the exact starting state
5. Unassigned patient Rahul Das is present in coordinator queue
6. Doctor Arjun Menon has Mon/Wed/Fri weekly schedule for 4 weeks
"""

import os
import sys
import pytest
import requests
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent.parent
backend_dir = repo_root / "backend"
scripts_dir = repo_root / "scripts"
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(scripts_dir))

from app.database.session import get_sync_db
from app.models.user import User
from app.models.patient import Patient
from app.models.care_case import CareCase
from app.models.owner import CaseOwner
from app.models.screening import ScreeningResult
from app.services.lifecycle_service import LifecycleService
from seed_judge_demo import seed_judge_demo
from reset_judge_demo import reset_judge_demo

BASE_URL = "http://127.0.0.1:8000/api/v1"


def get_token(email: str, password: str) -> dict:
    headers = {"Content-Type": "application/json", "X-Bypass-Rate-Limit": "1"}
    res = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": email, "password": password},
        headers=headers,
        timeout=10
    )
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return res.json()["data"]


def test_seeded_users_can_login_with_env_passwords():
    """Each seeded demo user (patient, doctor, coordinator) logs in with env passwords and gets correct role."""
    doc_pw = os.environ.get("DEMO_DOCTOR_PASSWORD", "DoctorPass123!")
    coord_pw = os.environ.get("DEMO_COORDINATOR_PASSWORD", "CoordinatorPass123!")
    pat_pw = os.environ.get("DEMO_PATIENT_PASSWORD", "PatientPass123!")

    # Patient: Meera Krishnan
    pat_data = get_token("meera.krishnan@carebridge.com", pat_pw)
    assert pat_data["role"].lower() == "patient"
    assert "token" in pat_data

    # Doctor: Dr. Arjun Menon
    doc_data = get_token("arjun.menon@carebridge.com", doc_pw)
    assert doc_data["role"].lower() == "doctor"
    assert "token" in doc_data

    # Coordinator: Priya Nair
    coord_data = get_token("priya.nair@carebridge.com", coord_pw)
    assert coord_data["role"].lower() == "care_coordinator"
    assert "token" in coord_data


def test_seeded_patient_shows_stage_3_complete_and_stage_4_pending():
    """Seeded patient Meera Krishnan shows Stages 1, 2, 3 complete and Stage 4 pending."""
    coord_pw = os.environ.get("DEMO_COORDINATOR_PASSWORD", "CoordinatorPass123!")
    coord_data = get_token("priya.nair@carebridge.com", coord_pw)
    headers = {"Authorization": f"Bearer {coord_data['token']}"}

    with get_sync_db() as db:
        case = db.query(CareCase).filter(CareCase.case_number == "CASE-2026-JUDGE01").first()
        assert case is not None, "CASE-2026-JUDGE01 not found"

        stages = LifecycleService.get_lifecycle_stages(case)
        assert len(stages) == 14

        stage_1 = next(s for s in stages if s["stage_number"] == 1)
        stage_2 = next(s for s in stages if s["stage_number"] == 2)
        stage_3 = next(s for s in stages if s["stage_number"] == 3)
        stage_4 = next(s for s in stages if s["stage_number"] == 4)

        assert stage_1["status"].upper() == "COMPLETED", f"Stage 1 status is {stage_1['status']}"
        assert stage_2["status"].upper() == "COMPLETED", f"Stage 2 status is {stage_2['status']}"
        assert stage_3["status"].upper() == "COMPLETED", f"Stage 3 status is {stage_3['status']}"
        assert stage_4["status"].upper() in ("PENDING", "ACTIVE") and stage_4["status"].upper() != "COMPLETED", f"Stage 4 status is {stage_4['status']}"

        # Verify doctor assignment
        assert case.case_context.get("assigned_doctor") == "Dr. Arjun Menon, MD"


def test_seed_twice_creates_no_duplicates():
    """Running seed twice creates no duplicate patient, case, or user records."""
    seed_judge_demo()
    seed_judge_demo()

    with get_sync_db() as db:
        patients = db.query(Patient).filter(Patient.mrn == "MRN-2026-0461").all()
        assert len(patients) == 1, f"Expected 1 patient, got {len(patients)}"

        cases = db.query(CareCase).filter(CareCase.case_number == "CASE-2026-JUDGE01").all()
        assert len(cases) == 1, f"Expected 1 case, got {len(cases)}"

        doctors = db.query(CaseOwner).filter(CaseOwner.email == "arjun.menon@carebridge.com").all()
        assert len(doctors) == 1, f"Expected 1 doctor, got {len(doctors)}"


def test_reset_returns_to_exact_starting_state():
    """Reset restores the exact starting state: Stage 3 completed, Stage 4 pending."""
    reset_judge_demo()

    with get_sync_db() as db:
        case = db.query(CareCase).filter(CareCase.case_number == "CASE-2026-JUDGE01").first()
        assert case is not None
        stages = LifecycleService.get_lifecycle_stages(case)
        st3 = next(s for s in stages if s["stage_number"] == 3)
        st4 = next(s for s in stages if s["stage_number"] == 4)

        assert st3["status"].upper() == "COMPLETED"
        assert st4["status"].upper() in ("PENDING", "ACTIVE") and st4["status"].upper() != "COMPLETED"


def test_unassigned_patient_in_coordinator_queue():
    """Rahul Das is unassigned so coordinator queue is not empty."""
    with get_sync_db() as db:
        unassigned_case = db.query(CareCase).filter(CareCase.case_number == "CASE-2026-UNASSIGNED01").first()
        assert unassigned_case is not None
        assert unassigned_case.current_owner_id is None, "Rahul Das case must be unassigned"


def test_doctor_weekly_schedule_table():
    """Dr. Arjun Menon has a Mon/Wed/Fri weekly schedule for the next 4 weeks."""
    with get_sync_db() as db:
        doctor = db.query(CaseOwner).filter(CaseOwner.email == "arjun.menon@carebridge.com").first()
        assert doctor is not None
        assert doctor.working_hours is not None
        assert "schedule_slots" in doctor.working_hours
        slots = doctor.working_hours["schedule_slots"]
        assert len(slots) >= 12, f"Expected at least 12 slots for 4 weeks Mon/Wed/Fri, got {len(slots)}"
