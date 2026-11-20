"""
Shared fixtures for AI behaviour tests (B1-B6).

Uses a dedicated REAL PostgreSQL database (`carebridge_test`) created on demand beside the app database.
All data is synthetic. The LLM is mocked off so only deterministic, tool-grounded behaviour is tested.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.database.session import Base
import app.models  # noqa: F401  (register all tables)

TEST_DB_NAME = "carebridge_test"


def _sync_url(dbname: str):
    url = make_url(settings.DATABASE_URL)
    return url.set(drivername="postgresql+psycopg", database=dbname)


@pytest.fixture(scope="session")
def pg_engine():
    admin = create_engine(_sync_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname=:n"), {"n": TEST_DB_NAME}).first()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin.dispose()
    engine = create_engine(_sync_url(TEST_DB_NAME))
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(pg_engine):
    """Fresh Session on a truncated test database for every test."""
    with pg_engine.begin() as conn:
        names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    Session = sessionmaker(bind=pg_engine, expire_on_commit=False)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture(autouse=True)
def mock_llm_off(monkeypatch):
    """Mock the LLM: no provider is ever called in these tests."""
    try:
        from app.services.llm_service import LLMService
        monkeypatch.setattr(LLMService, "get_llm", classmethod(lambda cls, *a, **k: None), raising=False)
    except Exception:
        pass
    yield


REPORT_TEXT = (
    "SYNTHETIC DEMO REPORT - NOT A REAL PATIENT\n"
    "Patient: Test Patient (synthetic)   Age: 46   Study: Bilateral screening mammogram (digital)\n"
    "TECHNIQUE: Standard CC and MLO views of both breasts.\n"
    "BREAST COMPOSITION: Heterogeneously dense (category C).\n"
    "FINDINGS: Right breast, upper outer quadrant: irregular hyperdense mass measuring approximately 1.2 cm "
    "with spiculated margins. Left breast: no suspicious mass.\n"
    "IMPRESSION: Suspicious right breast mass. BI-RADS Category 4.\n"
    "RECOMMENDATION: Ultrasound-guided core needle biopsy and clinical correlation.\n"
)


class World:
    """Synthetic cohort handles."""
    pass


def _advance(db, case, stage, evidence_type, role="system"):
    from app.services.lifecycle_service import LifecycleService
    LifecycleService.advance_stage(
        db=db, case_id=case.id, stage_ident=stage, actor_role=role, actor_id="test-setup",
        evidence={"evidence_type": evidence_type, "synthetic": True, "delivered": True},
        notes="synthetic test setup",
    )


def make_world(db, *, finalized=True, report_text=REPORT_TEXT, appt_in_hours=None, appt_status="CONFIRMED",
               tag=None):
    """Create doctor, coordinator, patient (+users), case with stages 1-3 done (if finalized)."""
    from app.models.owner import CaseOwner
    from app.models.user import User
    from app.models.patient import Patient
    from app.models.screening import ScreeningResult
    from app.models.care_case import CareCase
    from app.models.appointment import Appointment

    tag = tag or uuid.uuid4().hex[:6]
    now = datetime.now(timezone.utc)
    w = World()

    w.doctor_owner = CaseOwner(
        id=uuid.uuid4(), name="Dr. Test Menon, MD", role="primary_physician", email=f"doc_{tag}@test.example",
        facility="CareBridge Demo Clinic", specialty="Breast Oncology",
        working_hours={"schedule_slots": [
            (now + timedelta(days=d)).replace(hour=h, minute=0, second=0, microsecond=0).isoformat()
            for d in range(2, 9) for h in (10, 14, 18)
        ]},
    )
    w.coord_owner = CaseOwner(
        id=uuid.uuid4(), name="Priya Test, RN", role="care_coordinator", email=f"coord_{tag}@test.example",
        facility="CareBridge Demo Clinic",
    )
    db.add_all([w.doctor_owner, w.coord_owner])
    db.flush()

    w.patient = Patient(
        id=uuid.uuid4(), mrn=f"MRN-{tag}", first_name="Meera", last_name="Tester", phone="+910000000000",
        date_of_birth=datetime(1980, 1, 1).date(), preferred_language="en",
        patient_context={"address": "12 Synthetic Street, Testville"},
    )
    other = Patient(
        id=uuid.uuid4(), mrn=f"MRN-O-{tag}", first_name="Other", last_name="Person", phone="+910000000001",
        date_of_birth=datetime(1975, 5, 5).date(), preferred_language="en",
    )
    db.add_all([w.patient, other])
    db.flush()
    w.other_patient = other

    def _user(email, role, name, patient=None, owner=None):
        u = User(id=uuid.uuid4(), email=email, password_hash="x", role=role, full_name=name,
                 patient_id=patient.id if patient else None, owner_id=owner.id if owner else None)
        db.add(u)
        return u

    w.patient_user = _user(f"pat_{tag}@test.example", "patient", "Meera Tester", patient=w.patient)
    w.other_user = _user(f"oth_{tag}@test.example", "patient", "Other Person", patient=other)
    w.doctor_user = _user(f"docu_{tag}@test.example", "doctor", w.doctor_owner.name, owner=w.doctor_owner)
    w.coord_user = _user(f"coordu_{tag}@test.example", "care_coordinator", w.coord_owner.name, owner=w.coord_owner)
    db.flush()

    sr = ScreeningResult(
        id=uuid.uuid4(), patient_id=w.patient.id, screening_type="Mammogram", test_date=now - timedelta(days=3),
        finding_code="BI-RADS-4", finding_summary="Suspicious right breast mass. BI-RADS Category 4.",
        urgency_level="urgent", performing_facility="CareBridge Demo Clinic",
        raw_report_data={"report_text": report_text},
    )
    db.add(sr)
    db.flush()
    w.case = CareCase(
        id=uuid.uuid4(), case_number=f"CASE-T-{tag}", patient_id=w.patient.id, screening_result_id=sr.id,
        current_owner_id=w.coord_owner.id, status="notified", priority="urgent",
        sla_deadline=now + timedelta(days=14),
    )
    db.add(w.case)
    db.flush()
    if finalized:
        # Lifecycle initialisation completes Stages 1-2 (screening + report); outreach completes Stage 3.
        from app.services.lifecycle_service import LifecycleService
        LifecycleService.get_lifecycle_stages(w.case)
        db.commit()
        _advance(db, w.case, 3, "notification_delivery")
    else:
        from app.services.lifecycle_service import LifecycleService
        stages = [dict(s) for s in LifecycleService.get_lifecycle_stages(w.case)]
        for s in stages:
            if s["stage_number"] in (2, 3):
                s["status"] = "pending"
                s["completed_at"] = None
        ctx = dict(w.case.case_context or {})
        ctx["lifecycle_stages"] = stages
        w.case.case_context = ctx
    db.commit()

    w.appointment = None
    if appt_in_hours is not None:
        w.appointment = Appointment(
            id=uuid.uuid4(), case_id=w.case.id, patient_id=w.patient.id, facility="CareBridge Demo Clinic",
            provider_name=w.doctor_owner.name, appointment_type="consultation",
            scheduled_time=now + timedelta(hours=appt_in_hours), status=appt_status, version=1,
            doctor_confirmed=appt_status == "CONFIRMED", patient_confirmed=appt_status == "CONFIRMED",
            doctor_confirmed_version=1 if appt_status == "CONFIRMED" else None,
            patient_confirmed_version=1 if appt_status == "CONFIRMED" else None,
        )
        db.add(w.appointment)
        db.commit()

    from app.models.communication import ConversationSession
    w.session = ConversationSession(
        id=uuid.uuid4(), user_id=w.patient_user.id, role="patient", patient_id=w.patient.id, case_id=w.case.id,
        title="test", channel="in_app_chat",
    )
    db.add(w.session)
    db.commit()
    return w


@pytest.fixture()
def world(db):
    return make_world(db)
