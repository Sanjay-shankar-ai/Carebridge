"""B6 - Conversation quality, reviewed knowledge retrieval, response guard, and RBAC/isolation (real Postgres, LLM mocked)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.agents.prompts import CONVERSATION_PROMPT, render_conversation_prompt
from app.models.appointment import Appointment
from app.services.appointment_service import AppointmentService
from app.services.knowledge_retrieval_service import KnowledgeRetrievalService
from app.services.lifecycle_service import LifecycleService, LifecycleTransitionError
from app.services.notification_service import NotificationService, RecipientAuthorizationError
from app.services.patient_behaviour_router import PatientBehaviourRouter as Router
from app.services.response_guard_service import ResponseGuardService
from app.services.transport_service import TransportAuthorizationError, TransportService
from tests.behaviours.conftest import make_world


def test_conversation_prompt_contains_core_rules():
    for placeholder in (
        "{{first_name_or_blank}}", "{{language}}", "{{date}}", "{{care_journey}}",
        "{{report_status}}", "{{doctor_name}}", "{{coordinator_name}}",
        "{{appointment}}", "{{transport_status}}",
    ):
        assert placeholder in CONVERSATION_PROMPT
    low = CONVERSATION_PROMPT.lower()
    assert "tool result confirms it" in low
    assert "ask one question" in low
    assert "never invent slots, rides, dates, doctors, family members or findings" in low
    assert "do not repeat your previous opening sentence" in low
    assert "never say \"don't worry\"" in low

    rendered = render_conversation_prompt(
        first_name_or_blank="Meera",
        language="en",
        date="2026-11-20",
        care_journey="Stage 4 - Understanding Results",
        report_status="FINALIZED",
        doctor_name="Dr. Test Menon, MD",
        coordinator_name="Priya Test, RN",
        appointment="2026-11-22 10:00 UTC (CONFIRMED)",
        transport_status="REQUESTED (09:00)",
    )
    assert "{{" not in rendered
    assert "Meera" in rendered and "Dr. Test Menon, MD" in rendered and "REQUESTED (09:00)" in rendered


def test_knowledge_retrieval_strictly_enforces_reviewed_role_and_language():
    # English patient query -> returns ONLY reviewed=True, role=patient, language=en
    en_docs = KnowledgeRetrievalService.retrieve("mammogram BI-RADS report", role="patient", language="en")
    assert len(en_docs) >= 1
    assert all(d["reviewed"] is True and d["role"] == "patient" and d["language"] == "en" for d in en_docs)
    # Unreviewed draft file must NEVER be returned
    assert all("UNREVIEWED_SECRET_DRAFT_MARKER" not in d["body"] for d in en_docs)
    assert all(d["id"] != "draft_unreviewed_notes_en" for d in en_docs)

    # Spanish patient query -> only Spanish reviewed patient docs
    es_docs = KnowledgeRetrievalService.retrieve("mamografía BI-RADS informe", role="patient", language="es")
    assert len(es_docs) >= 1
    assert all(d["reviewed"] is True and d["role"] == "patient" and d["language"] == "es" for d in es_docs)

    # Arabic patient query -> only Arabic reviewed patient docs
    ar_docs = KnowledgeRetrievalService.retrieve("تقرير الماموجرام BI-RADS", role="patient", language="ar")
    assert len(ar_docs) >= 1
    assert all(d["reviewed"] is True and d["role"] == "patient" and d["language"] == "ar" for d in ar_docs)

    # Coordinator role -> only coordinator docs, never patient docs
    coord_docs = KnowledgeRetrievalService.retrieve("transport closure handoff", role="care_coordinator", language="en")
    assert len(coord_docs) >= 1
    assert all(d["reviewed"] is True and d["role"] == "care_coordinator" and d["language"] == "en" for d in coord_docs)

    # Role with no matching language docs -> empty list (no leak across languages/roles)
    empty_docs = KnowledgeRetrievalService.retrieve("closure handoff", role="care_coordinator", language="ar")
    assert empty_docs == []


def test_cancellation_knowledge_file_audience_and_inline_comment_reviewed_gate(tmp_path):
    # Installed convo-cancellation-reasons-v1.md has reviewed: false with inline comment -> must be ignored!
    all_docs = {d["id"]: d for d in KnowledgeRetrievalService.load_all()}
    assert "convo-cancellation-reasons-v1" in all_docs
    meta = all_docs["convo-cancellation-reasons-v1"]
    assert meta["role"] == "patient" and meta["audience"] == "patient"
    assert meta["language"] == "en" and meta["type"] == "conversation"
    assert meta["reviewed"] is False

    hits = KnowledgeRetrievalService.retrieve(
        "cancel transport work schedule fear cost caregiver", role="patient", language="en", limit=10
    )
    assert all(d["id"] != "convo-cancellation-reasons-v1" for d in hits)

    # Once reviewed: true (even with an inline YAML comment), audience: patient is retrieved ONLY for patient+en
    reviewed_copy = tmp_path / "convo-cancellation-reasons-v1.md"
    raw = (
        KnowledgeRetrievalService.load_all()[0]["path"]
    )
    from pathlib import Path
    src_text = (Path(raw).parent / "convo-cancellation-reasons-v1.md").read_text(encoding="utf-8")
    reviewed_copy.write_text(src_text.replace("reviewed: false", "reviewed: true"), encoding="utf-8")

    ok = KnowledgeRetrievalService.retrieve(
        "transport work schedule fear cost", role="patient", language="en", knowledge_dir=tmp_path
    )
    assert len(ok) == 1 and ok[0]["id"] == "convo-cancellation-reasons-v1" and ok[0]["reviewed"] is True
    assert KnowledgeRetrievalService.retrieve("transport cost", role="doctor", language="en", knowledge_dir=tmp_path) == []
    assert KnowledgeRetrievalService.retrieve("transport cost", role="patient", language="es", knowledge_dir=tmp_path) == []


def test_consecutive_replies_never_start_with_same_sentence(db):
    w = make_world(db, tag="dedup")

    r1 = Router.handle_turn(
        db, user_id=w.patient_user.id, role="patient", patient_id=w.patient.id,
        session_id=w.session.id, message="I am scared about my report", case_id=w.case.id,
    )
    Router.finalize_turn(db, r1, session_id=w.session.id, patient_id=w.patient.id)

    r2 = Router.handle_turn(
        db, user_id=w.patient_user.id, role="patient", patient_id=w.patient.id,
        session_id=w.session.id, message="is it cancer? I am scared", case_id=w.case.id,
    )
    Router.finalize_turn(db, r2, session_id=w.session.id, patient_id=w.patient.id)

    s1 = ResponseGuardService._first_sentence(r1.reply).lower()
    s2 = ResponseGuardService._first_sentence(r2.reply).lower()
    assert s1 and s2 and s1 != s2


def test_response_guard_rewrites_fabricated_ride_confirmed_and_appointment_cancelled():
    # Fabricated ride confirmed without tool
    g_ride = ResponseGuardService.sanitize_response(
        "Your ride is confirmed and the driver will arrive at 09:00.",
        tool_observations=[],
        actor_role="patient",
    )
    assert "not confirmed" in g_ride.lower()

    # Fabricated appointment cancelled without tool
    g_cancel = ResponseGuardService.sanitize_response(
        "Your appointment has been cancelled as requested.",
        tool_observations=[],
        actor_role="patient",
    )
    assert "not been cancelled" in g_cancel.lower()

    # Grounded cancellation WITH successful cancel_appointment tool is preserved
    ok_cancel = ResponseGuardService.sanitize_response(
        "Your appointment has been cancelled.",
        tool_observations=[{"tool": "cancel_appointment", "success": True}],
        actor_role="patient",
    )
    assert "has been cancelled" in ok_cancel.lower()

    # Fabricated case closure without doctor sign-off tool is rewritten
    g_close = ResponseGuardService.sanitize_response(
        "Your case is now closed.",
        tool_observations=[],
        actor_role="care_coordinator",
    )
    assert "not yet closed" in g_close.lower()


def test_cross_patient_access_rejected_and_only_doctor_can_close_case(db):
    w = make_world(db, tag="sec7")
    appt = Appointment(
        id=uuid.uuid4(), case_id=w.case.id, patient_id=w.patient.id, facility="CareBridge Demo Clinic",
        provider_name=w.doctor_owner.name, appointment_type="consultation",
        scheduled_time=datetime.now(timezone.utc) + timedelta(days=2), status="CONFIRMED", version=1,
    )
    db.add(appt)
    db.commit()

    # 1. Cross-patient transport rejected
    with pytest.raises(TransportAuthorizationError):
        TransportService.create_transport_request(db, appt.id, address="99 Bad St", patient_id=w.other_patient.id)

    # 2. Cross-patient cancellation rejected
    with pytest.raises(PermissionError):
        AppointmentService.cancel_appointment(db, appt.id, reason="nope", patient_id=w.other_patient.id)

    # 3. Cross-patient notification rejected
    with pytest.raises(RecipientAuthorizationError):
        NotificationService.stage_notification(
            db=db, user_id=w.other_user.id, role="patient", event_type="test_cross",
            title="Leak", message="Should fail", case_id=w.case.id, patient_id=w.patient.id,
        )

    # 4. Care coordinator CANNOT close a case (Stage 14)
    with pytest.raises(LifecycleTransitionError):
        LifecycleService.advance_stage(
            db=db, case_id=w.case.id, stage_ident=14,
            actor_role="care_coordinator", actor_id=str(w.coord_user.id),
            evidence={"evidence_type": "authorized_human_signoff", "summary": "attempt"},
        )

    # 5. AI CANNOT close a case (Stage 14)
    with pytest.raises(LifecycleTransitionError):
        LifecycleService.advance_stage(
            db=db, case_id=w.case.id, stage_ident=14,
            actor_role="ai_coordinator", actor_id="carebridge-ai",
            evidence={"evidence_type": "authorized_human_signoff", "summary": "attempt"},
        )
