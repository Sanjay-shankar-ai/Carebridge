"""
CareBridge Background Scheduler Manager (Phase 8)
Controls periodic execution of background surveillance and recovery jobs.
Provides both automated timer loops and programmatic on-demand job execution.
"""

import time
import threading
import logging
from typing import Dict, Any, Optional

from app.database.session import get_sync_db
from app.scheduler.jobs import SchedulerJobs

logger = logging.getLogger("carebridge.scheduler.manager")


class BackgroundSchedulerManager:
    """Manages background surveillance threads and on-demand scheduler job executions."""

    _is_running = False
    _thread: Optional[threading.Thread] = None
    _interval_seconds = 900  # Default 15 minutes (proactive follow-up cadence)
    _stop_event = threading.Event()

    @classmethod
    def run_job(cls, job_name: str, db=None) -> Dict[str, Any]:
        """Runs a specific surveillance job on demand."""
        logger.info(f"[SchedulerManager] Executing job: {job_name}")

        def _dispatch(session):
            if job_name == "scan_stalled_cases":
                return SchedulerJobs.scan_stalled_cases(session)
            elif job_name == "scan_sla_deadlines":
                return SchedulerJobs.scan_sla_deadlines(session)
            elif job_name == "scan_unacknowledged_outreach":
                return SchedulerJobs.scan_unacknowledged_outreach(session)
            elif job_name == "scan_overdue_tasks":
                return SchedulerJobs.scan_overdue_tasks(session)
            elif job_name == "scan_appointment_reminders":
                return SchedulerJobs.scan_appointment_reminders(session)
            elif job_name == "scan_expired_doctor_assignments":
                return SchedulerJobs.scan_expired_doctor_assignments(session)
            elif job_name == "run_proactive_followups":
                return SchedulerJobs.run_proactive_followups(session)
            else:
                raise ValueError(f"Unknown scheduler job: {job_name}")

        if db:
            return _dispatch(db)

        with get_sync_db() as session:
            return _dispatch(session)

    @classmethod
    def run_all_surveillance_jobs(cls, db=None) -> Dict[str, Any]:
        """Executes all surveillance jobs in sequence."""
        results = {}
        for job in [
            "scan_stalled_cases",
            "scan_sla_deadlines",
            "scan_unacknowledged_outreach",
            "scan_overdue_tasks",
            "scan_appointment_reminders",
            "scan_expired_doctor_assignments",
            "run_proactive_followups",
        ]:
            results[job] = cls.run_job(job, db=db)
        return results

    @classmethod
    def start(cls, interval_seconds: int = 900):
        """Starts the background scheduler thread."""
        if cls._is_running:
            logger.warning("[SchedulerManager] Scheduler thread is already running.")
            return

        cls._interval_seconds = interval_seconds
        cls._stop_event.clear()
        cls._is_running = True

        def _loop():
            logger.info(f"[SchedulerManager] Background loop started (Interval: {cls._interval_seconds}s)")
            # Allow server warmup before initiating first surveillance cycle
            if cls._stop_event.wait(30):
                return
            while not cls._stop_event.is_set():
                try:
                    cls.run_all_surveillance_jobs()
                except Exception as e:
                    logger.error(f"[SchedulerManager] Error in background surveillance run: {e}", exc_info=True)
                cls._stop_event.wait(cls._interval_seconds)

        cls._thread = threading.Thread(target=_loop, daemon=True, name="CareBridgeSchedulerThread")
        cls._thread.start()

    @classmethod
    def stop(cls):
        """Stops the background scheduler thread."""
        if not cls._is_running:
            return
        cls._stop_event.set()
        cls._is_running = False
        if cls._thread and cls._thread.is_alive():
            cls._thread.join(timeout=2.0)
        logger.info("[SchedulerManager] Background scheduler stopped.")

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Returns the operational status of the scheduler."""
        return {
            "is_running": cls._is_running,
            "interval_seconds": cls._interval_seconds,
            "thread_alive": cls._thread.is_alive() if cls._thread else False,
            "registered_jobs": [
                "scan_stalled_cases",
                "scan_sla_deadlines",
                "scan_unacknowledged_outreach",
                "scan_overdue_tasks",
                "scan_appointment_reminders",
                "scan_expired_doctor_assignments",
                "run_proactive_followups"
            ]
        }
