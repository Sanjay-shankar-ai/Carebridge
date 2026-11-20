"""B2 - Transport requests (real Postgres, LLM mocked)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.appointment import Appointment
from app.models.care_case import Task
from app.models.notification import Notification
from app.models.transport import TransportRequest
from app.services.appointment_service import AppointmentService
from app.services.patient_behaviour_router import PatientBehaviourRouter as Router
from app.services.response_guard_service import ResponseGuardService
from app.services.transport_service import TransportAuthorizationError, TransportService
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


def _appt_at(db, w, hour, minute=0, days_ahead=2, status="CONFIRMED"):
    dt = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    appt = Appointment(
        id=uuid.uuid4(), case_id=w.case.id, patient_id=w.patient.id, facility="CareBridge Demo Clinic",
        provider_name=w.doctor_owner.name, appointment_type="consultation",
        scheduled_time=dt, status=status, version=1,
        doctor_confirmed=status == "CONFIRMED", patient_confirmed=status == "CONFIRMED",
        doctor_confirmed_version=1 if status == "CONFIRMED" else None,
        patient_confirmed_version=1 if status == "CONFIRMED" else None,
    )
    db.add(appt)
    db.commit()
    return appt


def test_transport_request_confirmed_confirm_and_reschedule_flow(db):
    """Test #2 end-to-end: 10:00 appt -> 09:00 pickup REQUESTED, task+notif, confirm notifies, reschedule 11:00 -> 10:00."""
    w = make_world(db)
    appt = _appt_at(db, w, hour=10, minute=0)

    res = _turn(db, w, "I need transport")
    assert res.intent == "transport_request"
    assert any(o["tool"] == "create_transport_request" and o["success"] for o in res.tool_observations)

    # Reply says requested, NOT confirmed/arranged
    low = res.reply.lower()
    assert "09:00" in res.reply
    assert "requested" in low
    assert "ride is confirmed" not in low and "ride is arranged" not in low and "your pickup is confirmed" not in low
    assert w.coord_owner.name in res.reply

    # Persisted transport_request row linked to appointment version 1
    tr = db.query(TransportRequest).filter(TransportRequest.appointment_id == appt.id).first()
    assert tr is not None
    assert tr.status == "REQUESTED"
    assert tr.appointment_version == 1
    assert tr.pickup_time.astimezone(timezone.utc).strftime("%H:%M") == "09:00"

    # Coordinator task and coordinator notification exist
    task = db.query(Task).filter(Task.case_id == w.case.id, Task.task_type == "transport_request").first()
    assert task is not None and task.assigned_role == "care_coordinator"
    coord_notif = (
        db.query(Notification)
        .filter(Notification.user_id == w.coord_user.id, Notification.event_type == "transport_requested")
        .first()
    )
    assert coord_notif is not None

    # Patient cannot confirm their own transport
    with pytest.raises(TransportAuthorizationError):
        TransportService.confirm_transport_request(db, tr.id, actor_role="patient", actor_id=str(w.patient_user.id))

    # Coordinator confirms -> status CONFIRMED & patient notified
    conf = TransportService.confirm_transport_request(
        db, tr.id, actor_role="care_coordinator", actor_id=str(w.coord_user.id)
    )
    assert conf["success"] is True and conf["status"] == "CONFIRMED"
    db.refresh(tr)
    assert tr.status == "CONFIRMED"
    pat_conf = (
        db.query(Notification)
        .filter(Notification.user_id == w.patient_user.id, Notification.event_type == "transport_confirmed")
        .first()
    )
    assert pat_conf is not None and "09:00" in pat_conf.message

    # Reschedule appointment to 11:00 -> moves pickup to 10:00, links v2, resets to REQUESTED, notifies patient
    new_dt = appt.scheduled_time.astimezone(timezone.utc).replace(hour=11, minute=0)
    AppointmentService.reschedule_appointment(
        db, appt.id, new_scheduled_time=new_dt, actor_role="care_coordinator",
        actor_id=str(w.coord_user.id), reason="Patient schedule change",
    )
    db.commit()
    db.refresh(tr)
    assert tr.appointment_version == 2
    assert tr.pickup_time.astimezone(timezone.utc).strftime("%H:%M") == "10:00"
    assert tr.status == "REQUESTED"
    pat_resched = (
        db.query(Notification)
        .filter(Notification.user_id == w.patient_user.id, Notification.event_type == "transport_rescheduled")
        .first()
    )
    assert pat_resched is not None and "10:00" in pat_resched.message


def test_transport_asks_missing_address_and_no_appointment_case(db):
    # No appointment -> honest reply offering to book first
    w_none = make_world(db, tag="noappt")
    res_none = _turn(db, w_none, "I have no way to reach the hospital")
    assert "book" in res_none.reply.lower()
    assert db.query(TransportRequest).count() == 0

    # Appointment exists but profile address missing -> asks ONE question for address, then creates
    w = make_world(db, tag="noaddr")
    w.patient.patient_context = {}
    db.commit()
    appt = _appt_at(db, w, hour=14, minute=0)

    r1 = _turn(db, w, "I cannot travel alone, need a ride")
    assert "address" in r1.reply.lower()
    assert r1.reply.count("?") == 1
    assert db.query(TransportRequest).filter(TransportRequest.appointment_id == appt.id).first() is None

    r2 = _turn(db, w, "88 Demo Avenue, Caretown")
    assert "13:00" in r2.reply and "requested" in r2.reply.lower()
    tr = db.query(TransportRequest).filter(TransportRequest.appointment_id == appt.id).first()
    assert tr is not None and tr.pickup_address == "88 Demo Avenue, Caretown" and tr.pickup_time.astimezone(timezone.utc).strftime("%H:%M") == "13:00"


def test_transport_multiple_appointments_asks_which_and_cross_patient_blocked(db):
    w = make_world(db, tag="multi")
    a1 = _appt_at(db, w, hour=10, days_ahead=2)
    a2 = _appt_at(db, w, hour=15, days_ahead=4)

    r1 = _turn(db, w, "I need a ride")
    assert "10:00" in r1.reply and "15:00" in r1.reply
    assert r1.reply.count("?") == 1

    r2 = _turn(db, w, "2")
    assert "14:00" in r2.reply and "requested" in r2.reply.lower()
    tr = db.query(TransportRequest).filter(TransportRequest.appointment_id == a2.id).first()
    assert tr is not None

    # Cross-patient transport creation is rejected
    with pytest.raises(TransportAuthorizationError):
        TransportService.create_transport_request(
            db, a1.id, address="Other St", patient_id=w.other_patient.id
        )


def test_transport_tool_failure_keeps_recoverable_task(db, monkeypatch):
    w = make_world(db, tag="fail")
    appt = _appt_at(db, w, hour=10)

    def _boom(*a, **k):
        raise RuntimeError("simulated outbox failure")

    monkeypatch.setattr("app.services.notification_service.NotificationService.stage_notification", _boom)
    res = _turn(db, w, "I need transport")
    assert "could not" in res.reply.lower()
    assert "ride is confirmed" not in res.reply.lower()
    rec_task = db.query(Task).filter(Task.case_id == w.case.id, Task.task_type == "failed_handoff_recovery").first()
    assert rec_task is not None


def test_guard_rewrites_fabricated_ride_confirmed():
    guarded = ResponseGuardService.sanitize_response(
        "Great news! Your ride is confirmed for 09:00.", tool_observations=[], actor_role="patient"
    )
    assert "not confirmed" in guarded.lower()
