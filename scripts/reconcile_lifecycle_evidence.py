#!/usr/bin/env python3
"""
CareBridge Lifecycle Evidence Reconciliation Script (Phase 1)
Audits the database for any lifecycle stages marked 'completed' without verifiable backing evidence.

Rules:
- Dry-run by default: NEVER automatically modifies stage statuses or erases records.
- Cross-references relational tables (ScreeningResult, Notification, Referral, Appointment, ClosureEvidence, CaseEvent).
- Generates actionable reconciliation tasks for Care Coordinators to manually review and verify ungrounded completions.
"""

import os
import sys
import uuid
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

# Ensure backend is in python path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session

from app.models.care_case import CareCase, Task
from app.models.case_lifecycle_stage import CaseLifecycleStage
from app.models.screening import ScreeningResult
from app.models.notification import Notification
from app.models.referral import Referral
from app.models.appointment import Appointment
from app.models.closure import ClosureEvidence
from app.models.event_audit import CaseEvent, AuditLog
from app.services.lifecycle_service import STAGE_DEFINITIONS, LifecycleService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("carebridge.reconciliation")


def audit_case_evidence(db: Session, case: CareCase) -> List[Dict[str, Any]]:
    """
    Audits a single case across all 14 stages.
    Returns list of discrepancies where a stage is marked 'completed' without backing evidence.
    """
    discrepancies = []

    # Get relational stages or fallback to case_context
    db_stages = db.query(CaseLifecycleStage).filter(CaseLifecycleStage.case_id == case.id).order_by(CaseLifecycleStage.stage_number).all()
    stages_dict = {s.stage_number: s for s in db_stages}

    ctx_stages = (case.case_context or {}).get("lifecycle_stages", [])
    ctx_dict = {s["stage_number"]: s for s in ctx_stages if isinstance(s, dict) and "stage_number" in s}

    for defn in STAGE_DEFINITIONS:
        st_num = defn["stage_number"]
        st_title = defn["title"]

        db_stage = stages_dict.get(st_num)
        ctx_stage = ctx_dict.get(st_num)

        is_completed = (
            (db_stage and db_stage.status == "completed")
            or (ctx_stage and ctx_stage.get("status") == "completed")
        )

        if not is_completed:
            continue

        # Check evidence for this completed stage
        has_evidence = False
        missing_reason = "No backing evidence found"

        if st_num == 1:
            # Stage 1: Screening Examination
            screening = db.query(ScreeningResult).filter(ScreeningResult.patient_id == case.patient_id).first()
            if screening or (db_stage and db_stage.evidence_data):
                has_evidence = True
            else:
                missing_reason = "No screening procedure or ScreeningResult record linked to patient"

        elif st_num == 2:
            # Stage 2: Diagnostic Report Generated
            screening = db.query(ScreeningResult).filter(ScreeningResult.id == case.screening_result_id).first()
            if screening and screening.finding_code:
                has_evidence = True
            else:
                missing_reason = "Screening result missing verified clinical coding or report data"

        elif st_num == 3:
            # Stage 3: Initial Patient Outreach (Notification)
            notif = db.query(Notification).filter(Notification.patient_id == case.patient_id).first()
            if notif or (db_stage and db_stage.evidence_data.get("notification_id")):
                has_evidence = True
            else:
                missing_reason = "No notification delivery record exists for patient outreach"

        elif st_num == 4:
            # Stage 4: Patient Understanding
            ctx = case.case_context or {}
            if ctx.get("patient_understanding_confirmed") or (db_stage and db_stage.evidence_data.get("patient_understanding_confirmed")):
                has_evidence = True
            else:
                missing_reason = "No documented AI explanation or patient comprehension acknowledgement"

        elif st_num == 5:
            # Stage 5: Clinical Review
            review_ev = db.query(CaseEvent).filter(
                CaseEvent.case_id == case.id,
                CaseEvent.event_type.in_(["stage_5_clinical_review", "clinical_review_completed"])
            ).first()
            if review_ev or (db_stage and db_stage.evidence_data.get("clinical_assessment")):
                has_evidence = True
            else:
                missing_reason = "No documented physician clinical review notes in case events"

        elif st_num == 6:
            # Stage 6: Clinical Confirmation Message
            confirm_ev = db.query(CaseEvent).filter(
                CaseEvent.case_id == case.id,
                CaseEvent.event_type.in_(["stage_6_clinical_confirmation_message", "clinical_confirmation_sent"])
            ).first()
            if confirm_ev or (db_stage and db_stage.evidence_data.get("message_approved")):
                has_evidence = True
            else:
                missing_reason = "No doctor authorization event found for patient confirmation message"

        elif st_num == 7:
            # Stage 7: Referral Initiated
            ref = db.query(Referral).filter(Referral.case_id == case.id).first()
            if ref:
                has_evidence = True
            else:
                missing_reason = "No Referral record exists for this case"

        elif st_num == 8:
            # Stage 8: Referral Formally Accepted
            ref_acc = db.query(Referral).filter(Referral.case_id == case.id, Referral.status == "accepted").first()
            if ref_acc:
                has_evidence = True
            else:
                missing_reason = "No accepted referral found (referral status is not 'accepted')"

        elif st_num == 9:
            # Stage 9: Appointment Scheduled & Confirmed
            appt = db.query(Appointment).filter(
                Appointment.case_id == case.id,
                Appointment.status.in_(["CONFIRMED", "confirmed"])
            ).first()
            if appt:
                has_evidence = True
            else:
                missing_reason = "No dual-confirmed appointment record found"

        elif st_num == 10:
            # Stage 10: Consultation Completed
            appt_comp = db.query(Appointment).filter(
                Appointment.case_id == case.id,
                Appointment.status.in_(["COMPLETED", "attended"])
            ).first()
            if appt_comp and appt_comp.attendance_recorded_at:
                has_evidence = True
            else:
                missing_reason = "No completed appointment with verified attendance timestamp found"

        elif st_num == 11:
            # Stage 11: Treatment Monitoring
            ctx = case.case_context or {}
            if ctx.get("treatment_monitoring", {}).get("treatment_plan") or (db_stage and db_stage.evidence_data.get("monitoring_plan")):
                has_evidence = True
            else:
                missing_reason = "No active treatment plan or monitoring milestones documented"

        elif st_num == 12:
            # Stage 12: Follow-up Evaluation
            fu_ev = db.query(CaseEvent).filter(
                CaseEvent.case_id == case.id,
                CaseEvent.event_type.in_(["stage_12_follow_up", "follow_up_completed"])
            ).first()
            if fu_ev or (db_stage and db_stage.evidence_data.get("follow_up_outcome")):
                has_evidence = True
            else:
                missing_reason = "No documented follow-up evaluation outcome or surveillance record"

        elif st_num == 13:
            # Stage 13: Documentation Completed
            ctx = case.case_context or {}
            if ctx.get("documentation_evidence", {}).get("is_complete") or (db_stage and db_stage.evidence_data.get("audit_complete")):
                has_evidence = True
            else:
                missing_reason = "No completed documentation audit trail recorded"

        elif st_num == 14:
            # Stage 14: Verified Clinical Closure
            closure = db.query(ClosureEvidence).filter(
                ClosureEvidence.case_id == case.id,
                ClosureEvidence.is_verified.is_(True)
            ).first()
            if closure:
                has_evidence = True
            else:
                missing_reason = "No doctor-signed, verified ClosureEvidence record found in database"

        if not has_evidence:
            discrepancies.append({
                "case_id": str(case.id),
                "case_number": case.case_number,
                "stage_number": st_num,
                "stage_id": defn["stage_id"],
                "stage_title": st_title,
                "responsible_role": defn["responsible_role"],
                "missing_reason": missing_reason
            })

    return discrepancies


def run_reconciliation(
    db_url: Optional[str] = None,
    dry_run: bool = True,
    create_tasks: bool = False
) -> Dict[str, Any]:
    """Runs full reconciliation scan across all active and closed care cases."""
    if not db_url:
        db_file = Path("backend/carebridge.db").resolve()
        db_url = f"sqlite:///{db_file.as_posix()}"

    # Normalize url for sync engine
    sync_url = db_url.replace("+asyncpg", "").replace("+aiosqlite", "")
    engine = create_engine(sync_url)
    SessionClass = sessionmaker(bind=engine)
    session = SessionClass()

    logger.info(f"Connecting to database: {sync_url} (dry_run={dry_run})")

    cases = session.query(CareCase).all()
    logger.info(f"Auditing {len(cases)} care cases for lifecycle evidence integrity...")

    all_discrepancies = []
    tasks_created = 0

    now = datetime.now(timezone.utc)

    for case in cases:
        disc = audit_case_evidence(session, case)
        if disc:
            all_discrepancies.extend(disc)
            if create_tasks and not dry_run:
                for d in disc:
                    reconcile_task = Task(
                        id=uuid.uuid4(),
                        case_id=case.id,
                        title=f"Reconcile Stage {d['stage_number']} Evidence: {d['stage_title']}",
                        description=(
                            f"Automated Reconciliation Flag: Stage {d['stage_number']} ({d['stage_id']}) "
                            f"is marked completed without verified backing evidence. Reason: {d['missing_reason']}. "
                            f"Care coordinator review required to attach authentic clinical documentation."
                        ),
                        task_type="reconciliation_review",
                        assigned_to_id=case.current_owner_id,
                        assigned_role="care_coordinator",
                        priority="urgent",
                        status="pending",
                        due_date=now
                    )
                    session.add(reconcile_task)
                    tasks_created += 1

    if create_tasks and not dry_run:
        session.commit()

    session.close()

    return {
        "total_cases_audited": len(cases),
        "total_discrepancies_found": len(all_discrepancies),
        "dry_run": dry_run,
        "tasks_created": tasks_created,
        "discrepancies": all_discrepancies
    }


def main():
    parser = argparse.ArgumentParser(description="CareBridge Lifecycle Evidence Reconciliation Audit")
    parser.add_argument("--db", type=str, default=None, help="Database connection URL")
    parser.add_argument("--apply-tasks", action="store_true", help="Generate actionable reconciliation tasks (persisted only if not dry-run)")
    parser.add_argument("--no-dry-run", action="store_true", help="Execute write actions (create tasks)")
    args = parser.parse_args()

    dry_run = not args.no_dry_run
    res = run_reconciliation(db_url=args.db, dry_run=dry_run, create_tasks=args.apply_tasks)

    print("\n" + "=" * 80)
    print("CAREBRIDGE LIFECYCLE EVIDENCE RECONCILIATION REPORT")
    print(f"Mode: {'DRY RUN (Read-Only)' if res['dry_run'] else 'LIVE WRITE'}")
    print(f"Total Cases Audited: {res['total_cases_audited']}")
    print(f"Total Discrepancies Found: {res['total_discrepancies_found']}")
    print(f"Reconciliation Tasks Created: {res['tasks_created']}")
    print("=" * 80)

    if res["discrepancies"]:
        print(f"\n{'Case #':<18} | {'Stage':<6} | {'Stage Title':<32} | {'Missing Evidence Reason'}")
        print("-" * 80)
        for d in res["discrepancies"]:
            print(f"{d['case_number']:<18} | {d['stage_number']:<6} | {d['stage_title'][:32]:<32} | {d['missing_reason']}")
    else:
        print("\nAll completed stages have verified backing database evidence!")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
