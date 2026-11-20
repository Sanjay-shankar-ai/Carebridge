"""
CareBridge Background Surveillance & Recovery Scheduler Jobs (Phase 8)
Periodic jobs that monitor inactive cases, SLA clocks, unacknowledged communications,
and overdue milestones. Automatically resumes workflows without keeping HTTP connections open.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database.session import get_sync_db
from app.models.care_case import CareCase, Task
from app.models.communication import Communication
from app.models.event_audit import CaseEvent
from app.workflows.rules import _ensure_utc, evaluate_sla_status
from app.agents.recovery.agent import run_care_recovery_agent
from app.tools.registry import ToolRegistry
from app.workflows.persistence.traces import WorkflowTraceLogger

logger = logging.getLogger("carebridge.scheduler.jobs")


class SchedulerJobs:
    """Collection of periodic background surveillance and workflow resumption jobs."""

    @classmethod
    def scan_stalled_cases(cls, db: Session, days_threshold: float = 5.0) -> Dict[str, Any]:
        """
        Job 1: Scans for active cases with no recorded activity for >= days_threshold days.
        Automatically resumes the case by triggering the Care Recovery Agent.
        """
        now = datetime.now(timezone.utc)
        active_cases = (
            db.query(CareCase)
            .filter(CareCase.status.notin_(["closed", "care_completed", "escalated"]))
            .all()
        )

        stalled_cases = []
        recovered_cases = []

        for case in active_cases:
            latest_event = (
                db.query(CaseEvent)
                .filter(CaseEvent.case_id == case.id)
                .order_by(CaseEvent.timestamp.desc())
                .first()
            )
            last_activity = latest_event.timestamp if latest_event else case.updated_at
            days_inactive = (now - _ensure_utc(last_activity)).total_seconds() / 86400.0

            if days_inactive >= days_threshold:
                stalled_cases.append({
                    "case_id": str(case.id),
                    "case_number": case.case_number,
                    "days_inactive": round(days_inactive, 1)
                })

                # Automatically trigger Care Recovery Agent
                try:
                    rec_res = run_care_recovery_agent(case_id=str(case.id))
                    recovered_cases.append({
                        "case_id": str(case.id),
                        "playbook": rec_res.get("selected_playbook"),
                        "outcome": rec_res.get("outcome_status")
                    })
                except Exception as e:
                    logger.error(f"Error running recovery for stalled case {case.id}: {e}", exc_info=True)

        logger.info(
            f"[SchedulerJob] Stalled cases scan complete: Found {len(stalled_cases)} stalled, "
            f"recovered {len(recovered_cases)}."
        )

        return {
            "job_name": "scan_stalled_cases",
            "executed_at": now.isoformat(),
            "stalled_count": len(stalled_cases),
            "recovered_count": len(recovered_cases),
            "stalled_cases": stalled_cases,
            "recovered_cases": recovered_cases
        }

    @classmethod
    def scan_sla_deadlines(cls, db: Session) -> Dict[str, Any]:
        """
        Job 2: Scans for cases nearing SLA deadlines (< 72h) or already breached.
        Dispatches urgent coordinator alerts or executes emergency escalation.
        """
        now = datetime.now(timezone.utc)
        active_cases = (
            db.query(CareCase)
            .filter(CareCase.status.notin_(["closed", "care_completed"]))
            .all()
        )

        warning_cases = []
        breached_cases = []

        for case in active_cases:
            sla_deadline = _ensure_utc(case.sla_deadline)
            current_status = evaluate_sla_status(sla_deadline, now)
            case.sla_status = current_status

            if current_status == "breached":
                breached_cases.append(str(case.id))
                # Escalate breached case
                ToolRegistry.escalate_case(
                    db=db,
                    case_id=str(case.id),
                    urgency="critical",
                    reason=f"SLA deadline breached! Overdue since {case.sla_deadline.isoformat()}."
                )
                try:
                    from app.services.notification_service import NotificationService
                    diff_hours = int((sla_deadline - now).total_seconds() / 3600)
                    p_name = f"{case.patient.first_name} {case.patient.last_name}" if case.patient else "Patient"
                    NotificationService.notify_sla_warning(
                        db=db,
                        case_id=case.id,
                        case_number=case.case_number,
                        patient_name=p_name,
                        hours_remaining=diff_hours
                    )
                except Exception:
                    pass
            elif current_status == "warning":
                warning_cases.append(str(case.id))
                # Notify coordinator of impending deadline
                ToolRegistry.notify_case_owner(
                    db=db,
                    case_id=str(case.id),
                    priority="urgent",
                    message="SLA deadline warning: Less than 72 hours remaining for diagnostic resolution."
                )
                try:
                    from app.services.notification_service import NotificationService
                    diff_hours = int((sla_deadline - now).total_seconds() / 3600)
                    p_name = f"{case.patient.first_name} {case.patient.last_name}" if case.patient else "Patient"
                    NotificationService.notify_sla_warning(
                        db=db,
                        case_id=case.id,
                        case_number=case.case_number,
                        patient_name=p_name,
                        hours_remaining=diff_hours
                    )
                except Exception:
                    pass

        db.commit()

        return {
            "job_name": "scan_sla_deadlines",
            "executed_at": now.isoformat(),
            "warning_count": len(warning_cases),
            "breached_count": len(breached_cases),
            "warning_cases": warning_cases,
            "breached_cases": breached_cases
        }

    @classmethod
    def scan_unacknowledged_outreach(cls, db: Session, hours_threshold: float = 24.0) -> Dict[str, Any]:
        """
        Job 3: Identifies outreach communications sent >= hours_threshold hours ago
        without patient acknowledgement, and triggers re-engagement playbooks.
        """
        now = datetime.now(timezone.utc)
        active_cases = (
            db.query(CareCase)
            .filter(CareCase.status.notin_(["closed", "care_completed", "escalated"]))
            .all()
        )

        unacknowledged_cases = []
        for case in active_cases:
            latest_outreach = (
                db.query(Communication)
                .filter(Communication.case_id == case.id, Communication.sender.in_(["ai_coordinator", "human_coordinator"]))
                .order_by(Communication.created_at.desc())
                .first()
            )
            latest_inbound = (
                db.query(Communication)
                .filter(Communication.case_id == case.id, Communication.sender == "patient")
                .order_by(Communication.created_at.desc())
                .first()
            )

            is_unacknowledged = False
            if latest_outreach:
                if not latest_inbound:
                    is_unacknowledged = True
                elif _ensure_utc(latest_outreach.sent_at) > _ensure_utc(latest_inbound.sent_at):
                    is_unacknowledged = True

            if is_unacknowledged and latest_outreach:
                outreach_time = _ensure_utc(latest_outreach.sent_at)
                hours_unack = (now - outreach_time).total_seconds() / 3600.0

                if hours_unack >= hours_threshold:
                    unacknowledged_cases.append({
                        "case_id": str(case.id),
                        "hours_unacknowledged": round(hours_unack, 1)
                    })
                    # Re-evaluate with recovery agent
                    try:
                        run_care_recovery_agent(case_id=str(case.id))
                    except Exception as e:
                        logger.error(f"Error running recovery for unacknowledged case {case.id}: {e}", exc_info=True)

        return {
            "job_name": "scan_unacknowledged_outreach",
            "executed_at": now.isoformat(),
            "unacknowledged_count": len(unacknowledged_cases),
            "cases": unacknowledged_cases
        }

    @classmethod
    def scan_overdue_tasks(cls, db: Session) -> Dict[str, Any]:
        """
        Job 4: Identifies pending coordination tasks past due date and alerts coordinators.
        """
        now = datetime.now(timezone.utc)
        overdue_tasks = (
            db.query(Task)
            .filter(Task.status == "pending", Task.due_date < now)
            .all()
        )

        task_ids = []
        for t in overdue_tasks:
            t.status = "overdue"
            task_ids.append(str(t.id))
            if t.assigned_to_id:
                ToolRegistry.notify_case_owner(
                    db=db,
                    case_id=str(t.case_id),
                    priority="urgent",
                    message=f"Overdue coordination task: '{t.title}' was due on {t.due_date.isoformat()}."
                )

        db.commit()

        return {
            "job_name": "scan_overdue_tasks",
            "executed_at": now.isoformat(),
            "overdue_task_count": len(task_ids),
            "task_ids": task_ids
        }

    @classmethod
    def scan_appointment_reminders(cls, db: Session, hours_ahead: int = 48) -> Dict[str, Any]:
        """
        Job 5: Scans booked appointments within upcoming hours_ahead window
        and dispatches persistent reminders for patients with idempotency protection.
        """
        from app.services.notification_service import NotificationService
        return NotificationService.scan_and_send_appointment_reminders(db, hours_ahead=hours_ahead)

    @classmethod
    def scan_expired_doctor_assignments(cls, db: Session) -> Dict[str, Any]:
        """
        Job 6: Scans doctor assignments past their response deadline,
        atomically expires them, prevents late acceptance, and escalates to the Care Coordinator.
        """
        from app.services.doctor_allocation_service import DoctorAllocationService
        return DoctorAllocationService.scan_and_expire_assignments(db)

    @classmethod
    def run_proactive_followups(
        cls, db: Session, now: Any = None, tz_offset_minutes: Any = None
    ) -> Dict[str, Any]:
        """
        Job 7 (B5): Every 15 minutes evaluates UPCOMING (24h & 2h), MISSED (+30m),
        and OVERDUE FOLLOW-UP triggers with idempotency, outbox delivery, quiet hours, and tracing.
        """
        from app.services.proactive_followup_service import ProactiveFollowupService
        return ProactiveFollowupService.evaluate_all(db, now=now, tz_offset_minutes=tz_offset_minutes)
