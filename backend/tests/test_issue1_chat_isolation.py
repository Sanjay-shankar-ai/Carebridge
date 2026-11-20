"""
Automated Test Suite for Issue 1: Conversation Isolation, Session Ownership & Clean Chat State
Verifies that:
1. User A chats and creates a persistent conversation session owned by (user_id, role).
2. User B cannot fetch User A's conversation session by ID (strictly 403 Forbidden).
3. Non-existent session IDs return 404 Not Found.
4. /agent/sessions lists only the authenticated user's own conversations.
5. User B cannot rename or delete User A's conversation (403 Forbidden).
6. User A can rename and delete their own conversation.
7. Coordinator starts fresh with zero patient context when no patient is specified.
"""

import pytest
import os
import sys
import uuid
from pathlib import Path

# Add repo root and backend to sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
backend_dir = repo_root / "backend"
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import requests
from app.core.security import decode_access_token

BASE_URL = "http://127.0.0.1:8000/api/v1"

@pytest.fixture(scope="module", autouse=True)
def setup_users():
    import importlib.util
    script_path = repo_root / "scripts" / "reset_demo_users.py"
    spec = importlib.util.spec_from_file_location("reset_demo_users", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.reset_demo_users()


def get_token(email: str, password: str) -> str:
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": email, "password": password},
        headers={"X-Bypass-Rate-Limit": "test"},
        timeout=5.0
    )
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return resp.json()["data"]["token"]


def test_user_a_creates_chat_and_receives_session():
    """User A (Doctor) sends a message and gets a lazily created session ID."""
    doc_token = get_token("doctor@carebridge.com", os.environ.get("DEMO_DOCTOR_PASSWORD", "DoctorPass123!"))
    headers = {"Authorization": f"Bearer {doc_token}", "X-Bypass-Rate-Limit": "test"}

    resp = requests.post(
        f"{BASE_URL}/agent/interact",
        json={"message": "Which reports need my review today?", "channel": "in_app_chat"},
        headers=headers,
        timeout=10.0
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    session_id = body["data"].get("session_id")
    assert session_id is not None, "session_id was not returned"

    # Verify session appears in Doctor's sessions list
    sess_resp = requests.get(f"{BASE_URL}/agent/sessions", headers=headers, timeout=5.0)
    assert sess_resp.status_code == 200
    doctor_sessions = sess_resp.json()["data"]
    session_ids = [s["id"] for s in doctor_sessions]
    assert session_id in session_ids


def test_user_b_cannot_access_user_a_session():
    """User B (Coordinator) cannot fetch User A's (Doctor) conversation by ID (403 Forbidden)."""
    doc_token = get_token("doctor@carebridge.com", os.environ.get("DEMO_DOCTOR_PASSWORD", "DoctorPass123!"))
    coord_token = get_token("coordinator@carebridge.com", os.environ.get("DEMO_COORDINATOR_PASSWORD", "CoordinatorPass123!"))

    # Doctor creates a conversation
    doc_resp = requests.post(
        f"{BASE_URL}/agent/interact",
        json={"message": "Private clinical assessment for doctor session", "channel": "in_app_chat"},
        headers={"Authorization": f"Bearer {doc_token}", "X-Bypass-Rate-Limit": "test"},
        timeout=10.0
    )
    doc_session_id = doc_resp.json()["data"]["session_id"]

    # Coordinator attempts to fetch Doctor's session history by ID
    coord_resp = requests.get(
        f"{BASE_URL}/agent/history?session_id={doc_session_id}",
        headers={"Authorization": f"Bearer {coord_token}", "X-Bypass-Rate-Limit": "test"},
        timeout=5.0
    )
    assert coord_resp.status_code == 403, f"Expected 403 Forbidden, got {coord_resp.status_code}"
    assert "Forbidden" in coord_resp.json().get("detail", "")


def test_nonexistent_session_returns_404():
    """Requesting history for an invalid/nonexistent session returns 404."""
    doc_token = get_token("doctor@carebridge.com", os.environ.get("DEMO_DOCTOR_PASSWORD", "DoctorPass123!"))
    fake_id = str(uuid.uuid4())

    resp = requests.get(
        f"{BASE_URL}/agent/history?session_id={fake_id}",
        headers={"Authorization": f"Bearer {doc_token}", "X-Bypass-Rate-Limit": "test"},
        timeout=5.0
    )
    assert resp.status_code == 404


def test_sessions_list_isolation():
    """User B's session list does NOT contain User A's sessions."""
    doc_token = get_token("doctor@carebridge.com", os.environ.get("DEMO_DOCTOR_PASSWORD", "DoctorPass123!"))
    coord_token = get_token("coordinator@carebridge.com", os.environ.get("DEMO_COORDINATOR_PASSWORD", "CoordinatorPass123!"))

    # Create session as Doctor
    doc_sess_resp = requests.post(
        f"{BASE_URL}/agent/sessions",
        json={"title": "Doctor Confidential Thread"},
        headers={"Authorization": f"Bearer {doc_token}", "X-Bypass-Rate-Limit": "test"},
        timeout=5.0
    )
    doc_sess_id = doc_sess_resp.json()["data"]["id"]

    # Coordinator lists sessions
    coord_list_resp = requests.get(
        f"{BASE_URL}/agent/sessions",
        headers={"Authorization": f"Bearer {coord_token}", "X-Bypass-Rate-Limit": "test"},
        timeout=5.0
    )
    coord_sess_ids = [s["id"] for s in coord_list_resp.json()["data"]]
    assert doc_sess_id not in coord_sess_ids, "Cross-user conversation leaked in session list!"


def test_rename_and_delete_session_permissions():
    """User A can rename and delete own session; User B is blocked (403)."""
    doc_token = get_token("doctor@carebridge.com", os.environ.get("DEMO_DOCTOR_PASSWORD", "DoctorPass123!"))
    coord_token = get_token("coordinator@carebridge.com", os.environ.get("DEMO_COORDINATOR_PASSWORD", "CoordinatorPass123!"))

    # Doctor creates a session
    create_resp = requests.post(
        f"{BASE_URL}/agent/sessions",
        json={"title": "Initial Title"},
        headers={"Authorization": f"Bearer {doc_token}", "X-Bypass-Rate-Limit": "test"},
        timeout=5.0
    )
    sess_id = create_resp.json()["data"]["id"]

    # Coordinator tries to rename -> 403
    bad_rename = requests.patch(
        f"{BASE_URL}/agent/sessions/{sess_id}",
        json={"title": "Hacked Title"},
        headers={"Authorization": f"Bearer {coord_token}", "X-Bypass-Rate-Limit": "test"},
        timeout=5.0
    )
    assert bad_rename.status_code == 403

    # Coordinator tries to delete -> 403
    bad_delete = requests.delete(
        f"{BASE_URL}/agent/sessions/{sess_id}",
        headers={"Authorization": f"Bearer {coord_token}", "X-Bypass-Rate-Limit": "test"},
        timeout=5.0
    )
    assert bad_delete.status_code == 403

    # Doctor renames own session -> 200
    good_rename = requests.patch(
        f"{BASE_URL}/agent/sessions/{sess_id}",
        json={"title": "Updated Clinical Title"},
        headers={"Authorization": f"Bearer {doc_token}", "X-Bypass-Rate-Limit": "test"},
        timeout=5.0
    )
    assert good_rename.status_code == 200
    assert good_rename.json()["data"]["title"] == "Updated Clinical Title"

    # Doctor deletes own session -> 200
    good_delete = requests.delete(
        f"{BASE_URL}/agent/sessions/{sess_id}",
        headers={"Authorization": f"Bearer {doc_token}", "X-Bypass-Rate-Limit": "test"},
        timeout=5.0
    )
    assert good_delete.status_code == 200

    # Verify session is now gone (404)
    verify_fetch = requests.get(
        f"{BASE_URL}/agent/history?session_id={sess_id}",
        headers={"Authorization": f"Bearer {doc_token}", "X-Bypass-Rate-Limit": "test"},
        timeout=5.0
    )
    assert verify_fetch.status_code == 404


def test_coordinator_starts_with_no_patient_context():
    """Coordinator asking an operational question has zero patient context attached."""
    coord_token = get_token("coordinator@carebridge.com", os.environ.get("DEMO_COORDINATOR_PASSWORD", "CoordinatorPass123!"))
    headers = {"Authorization": f"Bearer {coord_token}", "X-Bypass-Rate-Limit": "test"}

    resp = requests.post(
        f"{BASE_URL}/agent/interact",
        json={"message": "Any new patients in the intake queue?", "channel": "in_app_chat"},
        headers=headers,
        timeout=10.0
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    # Verify no random patient was leaked or assumed
    assert data["case_id"] == ""
    assert data["patient_id"] == ""
    assert data["session_id"] != ""
