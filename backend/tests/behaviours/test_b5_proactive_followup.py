"""B5 - Proactive follow-up background job (real Postgres, LLM mocked)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.appointment import Appointment
from app.models.care_case import CareCase, Task
from app.models.communication import Communication
from app.models.notification import Notification
from app.models.workflow_trace import WorkflowExecutionTrace
from app.services.appointment_service import AppointmentService
from app.services.lifecycle_service import LifecycleService
from app.services.patient_behaviour_router import PatientBehaviourRouter as Router
from app.services.proactive_followup_service import ProactiveFollowupService
from tests.behaviours.conftest import make_world

# Use UTC+0 (tz_offset_minutes=0) so daytime 12:00 UTC is cleanly outside quiet hours (21:00-08:00)
DAYTIME_NOW = datetime(2026, 11, 25, 12, 0, 0, tzinfo=timezone.utc)
QUIET_NIGHT_NOW = datetime(2026, 11, 25, 22, 30, 0, tzinfo=timezone.utc)
QUIET_EARLY_NOW = datetime(2026, 11, 25, 6, 15, 0, tzinfo=timezone.utc)


def _make_appt(db, w, scheduled_time, status="CONFIRMED"):
    appt = Appointment(
        id=uuid.uuid4(), case_id=w.case.id, patient_id=w.patient.id, facility="CareBridge Demo Clinic",
        provider_name=w.doctor_owner.name, appointment_type="consultation",
        scheduled_time=scheduled_time, status=status, version=1,
        doctor_confirmed=True, patient_confirmed=True, doctor_confirmed_version=1, patient_confirmed_version=1,
    )
    db.add(appt)
    db.commit()
    return appt


def test_upcoming_24h_and_2h_idempotent_no_duplicates(db):
    w = make_world(db, tag="fu_up")
    appt_time = DAYTIME_NOW + timedelta(hours=20)
    appt = _make_appt(db, w, scheduled_time=appt_time)

    # First run (20h before) -> sends upcoming_24h once
    r1 = ProactiveFollowupService.evaluate_all(db, now=DAYTIME_NOW, tz_offset_minutes=0)
    assert r1["upcoming_24h_sent"] == 1 and r1["upcoming_2h_sent"] == 0

    # Immediate re-run -> idempotent, zero duplicates
    r1_dup = ProactiveFollowupService.evaluate_all(db, now=DAYTIME_NOW + timedelta(minutes=15), tz_offset_minutes=0)
    assert r1_dup["upcoming_24h_sent"] == 0 and r1_dup["upcoming_2h_sent"] == 0

    # Advance to 90 minutes before appointment -> sends upcoming_2h once (choose daytime hour!)
    # Shift appt_time & now_2h cleanly inside daytime
    appt_2h = _make_appt(db, w, scheduled_time=DAYTIME_NOW + timedelta(minutes=90))
    r2 = ProactiveFollowupService.evaluate_all(db, now=DAYTIME_NOW, tz_offset_minutes=0)
    assert r2["upcoming_2h_sent"] == 1 and r2["upcoming_24h_sent"] == 0

    # Re-run 2h window -> zero duplicates
    r2_dup = ProactiveFollowupService.evaluate_all(db, now=DAYTIME_NOW + timedelta(minutes=15), tz_offset_minutes=0)
    assert r2_dup["upcoming_2h_sent"] == 0

    # Exactly 2 outbox notifications & 2 AI chat messages & 2 traces
    notifs = (
        db.query(Notification)
        .filter(Notification.user_id == w.patient_user.id, Notification.event_type == "proactive_followup_upcoming")
        .all()
    )
    assert len(notifs) == 2
    assert {n.idempotency_key for n in notifs} == {
        f"{appt.id}:upcoming_24h:v1",
        f"{appt_2h.id}:upcoming_2h:v1",
    }
    comms = (
        db.query(Communication)
        .filter(Communication.patient_id == w.patient.id, Communication.sender == "ai_coordinator")
        .all()
    )
    assert len(comms) == 2
    assert all("ride" in c.content.lower() and w.doctor_owner.name in c.content for c in comms)

    traces = db.query(WorkflowExecutionTrace).filter(WorkflowExecutionTrace.workflow_name == "proactive_followup").all()
    assert len(traces) >= 2


def test_missed_appointment_checkin_once_recovery_task_and_no_auto_no_show(db):
    w = make_world(db, tag="fu_miss")
    stages_before = {s["stage_number"]: s["status"] for s in LifecycleService.get_lifecycle_stages(w.case)}
    appt = _make_appt(db, w, scheduled_time=DAYTIME_NOW - timedelta(minutes=45))

    r1 = ProactiveFollowupService.evaluate_all(db, now=DAYTIME_NOW, tz_offset_minutes=0)
    assert r1["missed_sent"] == 1 and r1["recovery_tasks_created"] == 1

    # Re-run -> idempotent (no duplicate check-in or recovery task)
    r2 = ProactiveFollowupService.evaluate_all(db, now=DAYTIME_NOW + timedelta(minutes=15), tz_offset_minutes=0)
    assert r2["missed_sent"] == 0 and r2["recovery_tasks_created"] == 0

    # Status was NOT auto-marked NO_SHOW; passed time NEVER completes a stage
    db.refresh(appt)
    assert appt.status == "CONFIRMED"
    case = db.query(CareCase).filter(CareCase.id == w.case.id).first()
    stages_after = {s["stage_number"]: s["status"] for s in LifecycleService.get_lifecycle_stages(case)}
    assert stages_after == stages_before

    # Recovery task exists for coordinator; AI check-in says "We missed you today"
    tasks = db.query(Task).filter(Task.case_id == w.case.id, Task.task_type == "recovery_play").all()
    assert len(tasks) == 1 and tasks[0].assigned_role == "care_coordinator"
    comm = db.query(Communication).filter(Communication.patient_id == w.patient.id).first()
    assert comm is not None and "we missed you today" in comm.content.lower()

    # Patient/AI cannot mark NO_SHOW; authorized doctor/coordinator can
    with pytest.raises(PermissionError):
        AppointmentService.mark_no_show(db, appt.id, actor_role="ai_coordinator", actor_id="ai")
    marked = AppointmentService.mark_no_show(db, appt.id, actor_role="care_coordinator", actor_id=str(w.coord_user.id))
    assert marked.status == "NO_SHOW"


def test_overdue_followup_sends_checkin_once_and_opens_recovery_task(db):
    w = make_world(db, tag="fu_over")
    ctx = dict(w.case.case_context or {})
    ctx["follow_up"] = {
        "scheduled_date": (DAYTIME_NOW - timedelta(days=2)).isoformat(),
        "status": "pending",
    }
    w.case.case_context = ctx
    db.commit()

    r1 = ProactiveFollowupService.evaluate_all(db, now=DAYTIME_NOW, tz_offset_minutes=0)
    assert r1["overdue_followup_sent"] == 1 and r1["recovery_tasks_created"] == 1
    r2 = ProactiveFollowupService.evaluate_all(db, now=DAYTIME_NOW + timedelta(minutes=15), tz_offset_minutes=0)
    assert r2["overdue_followup_sent"] == 0


def test_quiet_hours_respected(db):
    w = make_world(db, tag="fu_quiet")
    _make_appt(db, w, scheduled_time=QUIET_NIGHT_NOW + timedelta(hours=12))

    # 22:30 local -> quiet hours -> skipped, 0 messages
    r_night = ProactiveFollowupService.evaluate_all(db, now=QUIET_NIGHT_NOW, tz_offset_minutes=0)
    assert r_night["skipped_quiet_hours"] is True and r_night["upcoming_24h_sent"] == 0

    # 06:15 local -> quiet hours -> skipped, 0 messages
    r_early = ProactiveFollowupService.evaluate_all(db, now=QUIET_EARLY_NOW, tz_offset_minutes=0)
    assert r_early["skipped_quiet_hours"] is True and r_early["upcoming_24h_sent"] == 0

    assert db.query(Notification).filter(Notification.user_id == w.patient_user.id).count() == 0
    assert db.query(Communication).filter(Communication.patient_id == w.patient.id).count() == 0


def test_patient_reply_to_upcoming_reminder_routed_to_b2(db):
    w = make_world(db, tag="fu_reply")
    future_appt = _make_appt(db, w, scheduled_time=datetime.now(timezone.utc) + timedelta(hours=18))
    res = Router.handle_turn(
        db, user_id=w.patient_user.id, role="patient", patient_id=w.patient.id,
        session_id=w.session.id, message="Yes, I need help with a ride", case_id=w.case.id,
    )
    assert res is not None and res.intent == "transport_request"
    assert any(o["tool"] == "create_transport_request" and o["success"] for o in res.tool_observations)
    assert db.query(Task).filter(Task.case_id == w.case.id, Task.task_type == "transport_request").count() == 1
