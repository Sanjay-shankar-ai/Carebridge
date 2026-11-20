#!/usr/bin/env python3
"""
CareBridge — Idempotent Demo User Reset Script
(Re)creates or updates demo user accounts using the application's native hash function.
Reads passwords strictly from environment variables or gitignored local files (.env.demo / .env).
Passwords and password hashes are never hardcoded or printed.
"""

import os
import sys
from pathlib import Path

# Add backend directory to path
repo_root = Path(__file__).resolve().parent.parent
backend_dir = repo_root / "backend"
sys.path.insert(0, str(backend_dir))

def load_local_env_file(file_path: Path):
    """Load key-value pairs from a file into os.environ if not already set."""
    if not file_path.exists():
        return
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k and k not in os.environ:
                os.environ[k] = v

# Load from gitignored local files if env vars not in ambient environment
load_local_env_file(repo_root / ".env.demo")
load_local_env_file(repo_root / ".env")
load_local_env_file(backend_dir / ".env")

doctor_pw = os.getenv("DEMO_DOCTOR_PASSWORD")
coordinator_pw = os.getenv("DEMO_COORDINATOR_PASSWORD")
patient_pw = os.getenv("DEMO_PATIENT_PASSWORD")

if not doctor_pw or not coordinator_pw or not patient_pw:
    print(
        "ERROR: Demo passwords not configured. "
        "Please set DEMO_DOCTOR_PASSWORD, DEMO_COORDINATOR_PASSWORD, and DEMO_PATIENT_PASSWORD "
        "in your environment or in a gitignored .env.demo file.",
        file=sys.stderr
    )
    sys.exit(1)

from app.core.security import hash_password
from app.database.session import get_sync_db
from app.models.user import User
from app.models.owner import CaseOwner
from app.models.patient import Patient
from sqlalchemy import select
import uuid

def reset_demo_users():
    """Idempotently create or update demo user accounts."""
    with get_sync_db() as db:
        # Find owners and patients to link
        doctor_owner = db.execute(
            select(CaseOwner).where(CaseOwner.email == "aris.thorne@specialtyclinic.org")
        ).scalar_one_or_none()

        coord_owner = db.execute(
            select(CaseOwner).where(CaseOwner.email == "priya.nair@metrogovhealth.org")
        ).scalar_one_or_none()

        patient_record = db.execute(
            select(Patient).where(Patient.email == "meenakshi.r52@example.com")
        ).scalar_one_or_none()

        demo_specs = [
            # Doctor accounts
            {
                "email": "doctor@carebridge.com",
                "role": "doctor",
                "full_name": "Dr. Aris Thorne, MD",
                "password": doctor_pw,
                "owner_id": doctor_owner.id if doctor_owner else None,
                "patient_id": None,
            },
            {
                "email": "aris.thorne@specialtyclinic.org",
                "role": "doctor",
                "full_name": "Dr. Aris Thorne, MD",
                "password": doctor_pw,
                "owner_id": doctor_owner.id if doctor_owner else None,
                "patient_id": None,
            },
            # Coordinator accounts
            {
                "email": "coordinator@carebridge.com",
                "role": "care_coordinator",
                "full_name": "Priya Nair, RN",
                "password": coordinator_pw,
                "owner_id": coord_owner.id if coord_owner else None,
                "patient_id": None,
            },
            {
                "email": "priya.nair@metrogovhealth.org",
                "role": "care_coordinator",
                "full_name": "Priya Nair, RN",
                "password": coordinator_pw,
                "owner_id": coord_owner.id if coord_owner else None,
                "patient_id": None,
            },
            # Patient accounts
            {
                "email": "patient@carebridge.com",
                "role": "patient",
                "full_name": "Meenakshi Ramanathan",
                "password": patient_pw,
                "owner_id": None,
                "patient_id": patient_record.id if patient_record else None,
            },
            {
                "email": "meenakshi.r52@example.com",
                "role": "patient",
                "full_name": "Meenakshi Ramanathan",
                "password": patient_pw,
                "owner_id": None,
                "patient_id": patient_record.id if patient_record else None,
            },
        ]

        summary = []
        for spec in demo_specs:
            email_normalized = spec["email"].strip().lower()
            existing_user = db.execute(
                select(User).where(User.email == email_normalized)
            ).scalar_one_or_none()

            # Hash using app's exact cryptographic scheme
            hashed = hash_password(spec["password"])

            if existing_user:
                existing_user.password_hash = hashed
                existing_user.role = spec["role"]
                existing_user.full_name = spec["full_name"]
                existing_user.is_active = True
                existing_user.is_verified = True
                if spec["owner_id"]:
                    existing_user.owner_id = spec["owner_id"]
                if spec["patient_id"]:
                    existing_user.patient_id = spec["patient_id"]
                summary.append(f"Updated: {email_normalized} (Role: {spec['role']})")
            else:
                new_user = User(
                    id=uuid.uuid4(),
                    email=email_normalized,
                    password_hash=hashed,
                    role=spec["role"],
                    full_name=spec["full_name"],
                    is_active=True,
                    is_verified=True,
                    owner_id=spec["owner_id"],
                    patient_id=spec["patient_id"],
                )
                db.add(new_user)
                summary.append(f"Created: {email_normalized} (Role: {spec['role']})")

        db.commit()
        print("Demo user reset completed successfully (idempotent):")
        for line in summary:
            print(f" - {line}")

if __name__ == "__main__":
    reset_demo_users()
