"""
Unit and Integration Tests for Issue 4: Authentication, Normalization, and Non-Leaking Errors
"""

import pytest
import os
import sys
import asyncio
from pathlib import Path

# Add repo root and backend to sys.path
repo_root = Path(__file__).resolve().parent.parent.parent
backend_dir = repo_root / "backend"
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import httpx
import requests
from app.main import app
from app.core.security import decode_access_token

os.environ.setdefault("DEMO_DOCTOR_PASSWORD", "DoctorPass123!")
os.environ.setdefault("DEMO_COORDINATOR_PASSWORD", "CoordinatorPass123!")
os.environ.setdefault("DEMO_PATIENT_PASSWORD", "PatientPass123!")

def post_login(email: str, password: str):
    """Posts to /api/v1/auth/login via live server if available, else ASGITransport."""
    try:
        r = requests.post(
            "http://127.0.0.1:8000/api/v1/auth/login",
            json={"email": email, "password": password},
            headers={"X-Bypass-Rate-Limit": "test"},
            timeout=2.0
        )
        return r.status_code, (r.json() if "application/json" in r.headers.get("content-type", "") else {"text": r.text})
    except Exception:
        # Fall back to ASGITransport
        async def _call():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=10.0) as client:
                res = await client.post(
                    "/api/v1/auth/login",
                    json={"email": email, "password": password},
                    headers={"X-Bypass-Rate-Limit": "test"}
                )
                return res.status_code, res.json()
        return asyncio.run(_call())

@pytest.fixture(scope="module", autouse=True)
def setup_demo_users():
    import importlib.util
    script_path = repo_root / "scripts" / "reset_demo_users.py"
    spec = importlib.util.spec_from_file_location("reset_demo_users", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.reset_demo_users()


def test_doctor_login_success():
    """Doctor can log in and receives JWT with 'doctor' role."""
    status, body = post_login("doctor@carebridge.com", os.environ["DEMO_DOCTOR_PASSWORD"])
    assert status == 200, body
    data = body["data"]
    assert data["role"] == "doctor"
    assert "token" in data
    claims = decode_access_token(data["token"])
    assert claims["role"] == "doctor"
    assert claims["email"] == "doctor@carebridge.com"


def test_coordinator_login_success():
    """Coordinator can log in and receives JWT with 'care_coordinator' role."""
    status, body = post_login("coordinator@carebridge.com", os.environ["DEMO_COORDINATOR_PASSWORD"])
    assert status == 200, body
    data = body["data"]
    assert data["role"] == "care_coordinator"
    claims = decode_access_token(data["token"])
    assert claims["role"] == "care_coordinator"


def test_patient_login_success():
    """Patient can log in and receives JWT with 'patient' role."""
    status, body = post_login("patient@carebridge.com", os.environ["DEMO_PATIENT_PASSWORD"])
    assert status == 200, body
    data = body["data"]
    assert data["role"] == "patient"
    claims = decode_access_token(data["token"])
    assert claims["role"] == "patient"


def test_email_case_and_whitespace_normalization():
    """Case variations and leading/trailing whitespace behave identically."""
    variants = [
        "Doctor@CareBridge.com",
        "  doctor@carebridge.com  ",
        "DOCTOR@CAREBRIDGE.COM",
        " Coordinator@CareBridge.com ",
        "Patient@CareBridge.com ",
    ]
    for variant in variants:
        pwd = (
            os.environ["DEMO_DOCTOR_PASSWORD"] if "doctor" in variant.lower()
            else os.environ["DEMO_COORDINATOR_PASSWORD"] if "coord" in variant.lower()
            else os.environ["DEMO_PATIENT_PASSWORD"]
        )
        status, body = post_login(variant, pwd)
        assert status == 200, f"Failed for variant '{variant}': {body}"


def test_non_leaking_wrong_password():
    """Wrong password returns generic 401 message without leaking field specificity."""
    status, body = post_login("doctor@carebridge.com", "WrongPassword123!")
    assert status == 401
    assert body.get("detail") == "Invalid credentials."


def test_non_leaking_nonexistent_email():
    """Nonexistent email returns identical generic 401 message to prevent user enumeration."""
    status, body = post_login("nobody_exists_12345@nowhere.org", "SomePassword123!")
    assert status == 401
    assert body.get("detail") == "Invalid credentials."


def test_deactivated_account_rejected():
    """Deactivated accounts receive 403 Forbidden with clear message."""
    status, body = post_login("admin@carebridge.com", "AnyPassword123!")
    assert status == 403
    assert "deactivated" in body.get("detail", "").lower()
