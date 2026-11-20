"""B1 - Report summary in plain language (real Postgres, LLM mocked)."""

import re
import pytest

from app.models.care_case import CareCase
from app.services.lifecycle_service import LifecycleService
from app.services.patient_behaviour_router import PatientBehaviourRouter as Router
from app.services.report_explanation_service import ReportExplanationService
from tests.behaviours.conftest import make_world

FORBIDDEN = [r"you have cancer", r"you do not have cancer", r"you don't have cancer", r"don't worry", r"do not worry"]


def _stage(db, case_id, n):
    case = db.query(CareCase).filter(CareCase.id == case_id).first()
    db.refresh(case)
    return next(s for s in LifecycleService.get_lifecycle_stages(case) if s.get("stage_number") == n)


def _turn(db, w, msg):
    return Router.handle_turn(
        db, user_id=w.patient_user.id, role="patient", patient_id=w.patient.id,
        session_id=w.session.id, message=msg, case_id=w.case.id,
    )


@pytest.mark.parametrize("msg", [
    "I want my report summary", "what does my report say", "Explain my report", "my report what saying",
    "can you explain the results", "resumen de mi informe",
])
def test_report_phrasings_call_explain_report(db, world, msg):
    res = _turn(db, world, msg)
    assert res is not None and res.intent == "report_explanation"
    assert any(o["tool"] == "explain_report" and o["success"] for o in res.tool_observations)


def test_summary_has_sections_and_exact_values_and_no_diagnosis(db, world):
    out = ReportExplanationService.explain_report(db, world.patient.id)
    assert out["state"] == "ready"
    d = out["data"]
    for key in ("what_your_report_says", "what_these_words_mean", "what_your_report_recommends",
                "what_is_not_certain", "questions_for_doctor"):
        assert d[key], f"section {key} is empty"
    text = d["full_text"]
    assert "1.2 cm" in text            # exact value from the source report
    assert "BI-RADS" in text and "4" in text
    for pat in FORBIDDEN:
        assert not re.search(pat, text, re.I), pat


def test_stage_4_completes_only_after_delivery_is_persisted(db, world):
    assert _stage(db, world.case.id, 4)["status"] != "completed"
    res = _turn(db, world, "I want my report summary")
    # explanation prepared but NOT delivered: stage still pending
    assert _stage(db, world.case.id, 4)["status"] != "completed"
    # delivery marker refuses while the text is not persisted
    early = ReportExplanationService.mark_delivered(db, world.case.id)
    assert early["success"] is False and early["stage_4_completed"] is False
    assert _stage(db, world.case.id, 4)["status"] != "completed"
    # persist the full text, then the lifecycle completes Stage 4
    Router.finalize_turn(db, res, session_id=world.session.id, patient_id=world.patient.id)
    assert any(o["tool"] == "mark_report_delivered" and o["success"] for o in res.tool_observations), res.tool_observations
    assert _stage(db, world.case.id, 4)["status"] == "completed"


def test_unfinalized_report_says_not_ready_and_leaves_stage_4_pending(db):
    w = make_world(db, finalized=False)
    res = _turn(db, w, "I want my report summary")
    assert res.intent == "report_explanation"
    assert "not ready" in res.reply.lower()
    assert not any(o["success"] for o in res.tool_observations)
    Router.finalize_turn(db, res, session_id=w.session.id, patient_id=w.patient.id)
    assert _stage(db, w.case.id, 4)["status"] != "completed"
    for pat in FORBIDDEN:
        assert not re.search(pat, res.reply, re.I)


def test_unreadable_report_is_honest_and_offers_doctor(db):
    w = make_world(db, report_text="   ")
    # no readable text anywhere -> unreadable path
    case = db.query(CareCase).filter(CareCase.id == w.case.id).first()
    case.screening_result.finding_summary = " "
    db.commit()
    res = _turn(db, w, "explain my report")
    assert "could not read" in res.reply.lower() or "not ready" in res.reply.lower()
    assert "doctor" in res.reply.lower()
    assert _stage(db, w.case.id, 4)["status"] != "completed"
