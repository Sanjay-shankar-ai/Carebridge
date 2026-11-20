"""B3 - Cancellation with a WHY question (real Postgres, LLM mocked)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.appointment import Appointment
from app.models.care_case import CareCase, Task
from app.models.notification import Notification
from app.models.transport import TransportRequest
from app.services.appointment_service import AppointmentService
from app.services.lifecycle_service import LifecycleService
from app.services.patient_behaviour_router import PatientBehaviourRouter as Router
from app.services.response_guard_service import ResponseGuardService
from tests.behaviours.conftest import make_world


def _turn(db, w, msg, lang="en"):
    res = Router.handle_turn(
        db, user_id=w.patient_user.id, role="patient", patient_id=w.patient.id,
        session_id=w.session.id, message=msg, case_id=w.case.id, language=lang,
    )
    assert res is not None
    res.reply = ResponseGuardService.sanitize_response(
        res.reply, tool_observations=res.tool_observations, actor_role="patient"
    )
    Router.finalize_turn(db, res, session_id=w.session.id, patient_id=w.patient.id, language=lang)
    return res


def _appt_at(db, w, hour=10, days_ahead=2, status="CONFIRMED"):
    dt = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    appt = Appointment(
        id=uuid.uuid4(), case_id=w.case.id, patient_id=w.patient.id, facility="CareBridge Demo Clinic",
        provider_name=w.doctor_owner.name, appointment_type="consultation",
        scheduled_time=dt, status=status, version=1,
        doctor_confirmed=True, patient_confirmed=True, doctor_confirmed_version=1, patient_confirmed_version=1,
    )
    db.add(appt)
    db.commit()
    return appt


def test_cancel_asks_why_does_not_cancel_yet_and_transport_reason_offers_ride(db):
    w = make_world(db, tag="c_tr")
    appt = _appt_at(db, w, hour=10)

    r1 = _turn(db, w, "Cancel my appointment")
    assert "making it hard to come" in r1.reply.lower()
    assert r1.reply.count("?") == 1
    db.refresh(appt)
    assert appt.status == "CONFIRMED"  # NOT cancelled yet!

    r2 = _turn(db, w, "I have no transport to reach the clinic")
    assert "ride" in r2.reply.lower() or "transport" in r2.reply.lower()
    db.refresh(appt)
    assert appt.status == "CONFIRMED"

    # Accepting the ride routes into B2 and creates a REQUESTED transport request
    r3 = _turn(db, w, "Yes, please request a ride")
    assert "09:00" in r3.reply and "requested" in r3.reply.lower()
    tr = db.query(TransportRequest).filter(TransportRequest.appointment_id == appt.id).first()
    assert tr is not None and tr.status == "REQUESTED"
    db.refresh(appt)
    assert appt.status == "CONFIRMED"


def test_cancel_work_evenings_offers_real_evening_slots_only_and_moves_to_v2(db):
    w = make_world(db, tag="c_wrk")
    appt = _appt_at(db, w, hour=10, days_ahead=2)

    r1 = _turn(db, w, "I need to cancel my appointment")
    assert "making it hard to come" in r1.reply.lower()

    r2 = _turn(db, w, "Work shift conflicts, only evenings work")
    assert any(o["tool"] == "get_available_slots" for o in r2.tool_observations)
    # Doctor schedule_slots in conftest has 10:00, 14:00, and 18:00 — ONLY 18:00 (evening) should be offered!
    assert "18:00" in r2.reply
    assert "10:00" not in r2.reply and "14:00" not in r2.reply

    # Choose slot 1 -> moves appointment to version 2, resets confirmations, notifies doctor
    r3 = _turn(db, w, "1")
    assert any(o["tool"] == "reschedule_appointment" and o["success"] for o in r3.tool_observations)
    db.refresh(appt)
    assert appt.version == 2
    assert appt.doctor_confirmed is False
    assert appt.scheduled_time.astimezone(timezone.utc).hour == 18
    doc_notif = (
        db.query(Notification)
        .filter(Notification.user_id == w.doctor_user.id, Notification.event_type == "appointment_rescheduled")
        .first()
    )
    assert doc_notif is not None


def test_cancel_work_no_matching_slots_creates_coordinator_task_and_never_invents_time(db):
    w = make_world(db, tag="c_noslot")
    # Remove evening slots from doctor's schedule so only morning/afternoon exist
    now = datetime.now(timezone.utc)
    w.doctor_owner.working_hours = {
        "schedule_slots": [
            (now + timedelta(days=d)).replace(hour=10, minute=0, second=0, microsecond=0).isoformat()
            for d in range(2, 6)
        ]
    }
    db.commit()
    _appt_at(db, w, hour=10, days_ahead=2)

    _turn(db, w, "I can't come")
    r2 = _turn(db, w, "My work schedule — I can only do evenings")
    assert "no open slots" in r2.reply.lower()
    assert "18:00" not in r2.reply and "19:00" not in r2.reply and "17:00" not in r2.reply
    coord_task = (
        db.query(Task)
        .filter(Task.case_id == w.case.id, Task.task_type == "reschedule_assistance")
        .first()
    )
    assert coord_task is not None and coord_task.assigned_role == "care_coordinator"


def test_cancel_cost_requests_financial_counselling_and_confirmed_cancel_full_effects(db):
    w = make_world(db, tag="c_full")
    appt = _appt_at(db, w, hour=10)

    stages_before = {
        s["stage_number"]: s["status"] for s in LifecycleService.get_lifecycle_stages(w.case)
    }

    _turn(db, w, "Cancel my appointment")
    r2 = _turn(db, w, "I am worried about the cost and cannot afford it")
    assert "requested" in r2.reply.lower() and "financial counselling" in r2.reply.lower()
    fin_task = db.query(Task).filter(Task.case_id == w.case.id, Task.task_type == "financial_counselling").first()
    assert fin_task is not None
    db.refresh(appt)
    assert appt.status == "CONFIRMED"

    # Explicit confirmation -> CANCELLED, doctor & coordinator notified, recovery task opened, no stage completed, case stays open
    r3 = _turn(db, w, "yes, cancel")
    assert any(o["tool"] == "cancel_appointment" and o["success"] for o in r3.tool_observations)
    db.refresh(appt)
    assert appt.status == "CANCELLED"
    assert "cost" in (appt.cancellation_reason or "").lower()

    doc_notif = (
        db.query(Notification)
        .filter(Notification.user_id == w.doctor_user.id, Notification.event_type == "appointment_cancelled")
        .first()
    )
    coord_notif = (
        db.query(Notification)
        .filter(Notification.user_id == w.coord_user.id, Notification.event_type == "appointment_cancelled")
        .first()
    )
    assert doc_notif is not None
    assert coord_notif is not None

    rec_task = db.query(Task).filter(Task.case_id == w.case.id, Task.task_type == "recovery_play").first()
    assert rec_task is not None and rec_task.assigned_role == "care_coordinator"

    case = db.query(CareCase).filter(CareCase.id == w.case.id).first()
    assert case.status != "closed"
    stages_after = {
        s["stage_number"]: s["status"] for s in LifecycleService.get_lifecycle_stages(case)
    }
    assert stages_after == stages_before


def test_cancel_cross_patient_rejected_and_guard_rewrites_fabricated_cancel(db):
    w = make_world(db, tag="c_sec")
    appt = _appt_at(db, w, hour=10)
    with pytest.raises(PermissionError):
        AppointmentService.cancel_appointment(
            db, appt.id, reason="unauthorized", patient_id=w.other_patient.id
        )
    db.refresh(appt)
    assert appt.status == "CONFIRMED"

    guarded = ResponseGuardService.sanitize_response(
        "Done! Your appointment has been cancelled.", tool_observations=[], actor_role="patient"
    )
    assert "not been cancelled" in guarded.lower()
