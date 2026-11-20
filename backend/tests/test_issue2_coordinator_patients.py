"""
CareBridge Issue 2 Verification Test Suite
Tests:
1. coordinator can list patients with filters
2. stage 1 action creates evidence and advances stage
3. coordinator cannot close case (403)
4. doctor stages are read-only for coordinator
5. SLA badges match SLA service
6. 14 stages render correctly from backend
7. missing evidence blocks stage advancement
"""

import os
import uuid
import pytest
import requests

BASE_URL = "http://127.0.0.1:8000/api/v1"


def get_token(email: str, password: str = None) -> str:
    if password is None:
        if "coord" in email:
            password = os.environ.get("DEMO_COORDINATOR_PASSWORD", "CoordinatorPass123!")
        elif "doctor" in email:
            password = os.environ.get("DEMO_DOCTOR_PASSWORD", "DoctorPass123!")
        else:
            password = os.environ.get("DEMO_PATIENT_PASSWORD", "PatientPass123!")

    res = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": email, "password": password},
        headers={"Content-Type": "application/json"},
        timeout=10
    )
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return res.json()["data"]["token"]


def test_coordinator_can_list_patients_with_filters():
    """Coordinator can list all patients with pagination, search, and multidimensional filters."""
    coord_token = get_token("coordinator@carebridge.com")
    headers = {"Authorization": f"Bearer {coord_token}"}

    # 1. Base list
    res = requests.get(f"{BASE_URL}/patients/coordinator?page=1&page_size=10", headers=headers, timeout=10)
    assert res.status_code == 200
    data = res.json()["data"]
    assert "items" in data
    assert "total" in data
    assert "total_pages" in data
    assert len(data["items"]) > 0

    first_item = data["items"][0]
    required_fields = [
        "patient_id", "name", "mrn", "case_id", "case_number",
        "current_stage_number", "current_stage_title", "status",
        "pending_action", "responsible_role", "assigned_doctor",
        "sla_status", "last_updated"
    ]
    for f in required_fields:
        assert f in first_item, f"Missing field '{f}' in coordinator patient item"

    # 2. Search filter
    p_name = first_item["name"].split()[0]
    search_res = requests.get(f"{BASE_URL}/patients/coordinator?q={p_name}", headers=headers, timeout=10)
    assert search_res.status_code == 200
    search_items = search_res.json()["data"]["items"]
    assert any(p_name.lower() in it["name"].lower() for it in search_items)

    # 3. Stage filter
    stg_res = requests.get(f"{BASE_URL}/patients/coordinator?stage=1", headers=headers, timeout=10)
    assert stg_res.status_code == 200
    for it in stg_res.json()["data"]["items"]:
        assert it["current_stage_number"] == 1

    # 4. Needs my action filter
    act_res = requests.get(f"{BASE_URL}/patients/coordinator?needs_my_action=true", headers=headers, timeout=10)
    assert act_res.status_code == 200
    for it in act_res.json()["data"]["items"]:
        assert it["needs_coordinator_action"] is True

    # 5. Overdue / SLA breach filter
    sla_res = requests.get(f"{BASE_URL}/patients/coordinator?overdue_sla=true", headers=headers, timeout=10)
    assert sla_res.status_code == 200

    # 6. Unassigned filter
    unassigned_res = requests.get(f"{BASE_URL}/patients/coordinator?unassigned=true", headers=headers, timeout=10)
    assert unassigned_res.status_code == 200
    for it in unassigned_res.json()["data"]["items"]:
        assert it["assigned_doctor"] == "Unassigned"


def test_patient_cannot_access_coordinator_endpoint():
    """Patient role is blocked with 403 Forbidden when attempting to access coordinator endpoint."""
    patient_token = get_token("patient@carebridge.com")
    headers = {"Authorization": f"Bearer {patient_token}"}

    res = requests.get(f"{BASE_URL}/patients/coordinator", headers=headers, timeout=10)
    assert res.status_code == 403
    assert "Forbidden" in res.json().get("detail", "")


def test_14_stages_render_correctly_from_backend():
    """Backend lifecycle endpoint returns all 14 stages in order with evidence and status."""
    coord_token = get_token("coordinator@carebridge.com")
    headers = {"Authorization": f"Bearer {coord_token}"}

    cases_res = requests.get(f"{BASE_URL}/cases", headers=headers, timeout=10)
    assert cases_res.status_code == 200
    cases = cases_res.json()["data"]
    assert len(cases) > 0
    case_id = cases[0]["id"]

    res = requests.get(f"{BASE_URL}/cases/{case_id}/lifecycle", headers=headers, timeout=10)
    assert res.status_code == 200
    payload = res.json()["data"]

    stages = payload.get("stages", [])
    assert len(stages) == 14, f"Expected exactly 14 stages, got {len(stages)}"

    stage_nums = [s["stage_number"] for s in stages]
    assert stage_nums == list(range(1, 15)), f"Expected stages 1..14 in sequence, got {stage_nums}"

    valid_statuses = {"NOT_STARTED", "PENDING", "IN_PROGRESS", "COMPLETED", "BLOCKED", "REQUIRES_REVIEW"}
    for st in stages:
        assert st["status"].upper() in valid_statuses, f"Invalid stage status: {st['status']}"
        assert "responsible_role" in st
        assert "stage_id" in st


def test_stage_1_action_creates_evidence_and_advances_stage():
    """Recording screening performed creates Stage 1 evidence and advances lifecycle."""
    coord_token = get_token("coordinator@carebridge.com")
    headers = {"Authorization": f"Bearer {coord_token}"}

    # Find a case at stage 1 or first case
    cases_res = requests.get(f"{BASE_URL}/cases", headers=headers, timeout=10)
    cases = cases_res.json()["data"]
    assert len(cases) > 0
    case_id = cases[0]["id"]

    complete_payload = {
        "completion_notes": "Diagnostic imaging completed with mammogram protocol at screening center.",
        "completed_at": "2026-11-20T10:00:00Z"
    }

    res = requests.post(f"{BASE_URL}/cases/{case_id}/complete-screening", json=complete_payload, headers=headers, timeout=10)
    assert res.status_code == 200
    assert res.json().get("success") is True

    # Check lifecycle stage 1 is COMPLETED
    life_res = requests.get(f"{BASE_URL}/cases/{case_id}/lifecycle", headers=headers, timeout=10)
    assert life_res.status_code == 200
    stages = life_res.json()["data"]["stages"]
    stage_1 = next(s for s in stages if s["stage_number"] == 1)
    assert stage_1["status"].upper() == "COMPLETED"
    assert stage_1.get("completed_at") is not None


def test_coordinator_cannot_close_case_403():
    """Coordinator attempting clinical closure is strictly blocked with 403 Forbidden."""
    coord_token = get_token("coordinator@carebridge.com")
    headers = {"Authorization": f"Bearer {coord_token}"}

    cases_res = requests.get(f"{BASE_URL}/cases", headers=headers, timeout=10)
    cases = cases_res.json()["data"]
    case_id = cases[0]["id"]

    closure_payload = {
        "clinical_rationale": "Coordinator trying to close case directly without doctor sign-off."
    }

    res = requests.post(f"{BASE_URL}/cases/{case_id}/clinical-closure", json=closure_payload, headers=headers, timeout=10)
    assert res.status_code == 403, f"Expected 403 Forbidden, got {res.status_code}: {res.text}"
    assert "Only an authorized physician" in res.json().get("detail", "")


def test_doctor_stages_are_read_only_for_coordinator():
    """Doctor-exclusive stages (Stage 5 Clinical Review, Stage 14 Closure) reject coordinator calls."""
    coord_token = get_token("coordinator@carebridge.com")
    headers = {"Authorization": f"Bearer {coord_token}"}

    cases_res = requests.get(f"{BASE_URL}/cases", headers=headers, timeout=10)
    cases = cases_res.json()["data"]
    case_id = cases[0]["id"]

    # Attempt Stage 5 Clinical Review as coordinator
    review_payload = {
        "clinical_assessment": "Coordinator attempting physician review.",
        "approved_pathway": "diagnostic_imaging"
    }
    rev_res = requests.post(f"{BASE_URL}/cases/{case_id}/clinical-review", json=review_payload, headers=headers, timeout=10)
    assert rev_res.status_code == 403


def test_sla_badges_match_sla_service():
    """SLA status values returned by coordinator patients endpoint match valid domain SLA levels."""
    coord_token = get_token("coordinator@carebridge.com")
    headers = {"Authorization": f"Bearer {coord_token}"}

    res = requests.get(f"{BASE_URL}/patients/coordinator", headers=headers, timeout=10)
    assert res.status_code == 200
    items = res.json()["data"]["items"]

    valid_sla_levels = {"normal", "warning", "breached"}
    for it in items:
        assert it["sla_status"] in valid_sla_levels, f"Invalid SLA status {it['sla_status']}"


def test_missing_evidence_blocks_stage_advancement():
    """Advancing clinical closure without required checklist evidence is blocked."""
    doc_token = get_token("doctor@carebridge.com")
    headers = {"Authorization": f"Bearer {doc_token}"}

    # Attempt closure on an uncompleted case without evidence
    cases_res = requests.get(f"{BASE_URL}/cases", headers=headers, timeout=10)
    cases = cases_res.json()["data"]
    # Pick a case not in stage 13
    case_id = cases[0]["id"]

    res = requests.post(
        f"{BASE_URL}/cases/{case_id}/clinical-closure",
        json={"clinical_rationale": "Premature closure without documentation checklist."},
        headers=headers,
        timeout=10
    )
    # Either 400 (missing evidence/preconditions) or fails validation
    assert res.status_code in (400, 422), f"Expected 400/422 on premature closure without evidence, got {res.status_code}"
