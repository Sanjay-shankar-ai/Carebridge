"""
CareBridge Dashboard Read Model Consistency Checker
Detects stale/corrupted projections and repairs them safely.
Features:
- Dry-run first mode (--dry-run).
- Reverts unverified stage completions to active/pending.
- Creates coordinator reconciliation task when clinical evidence is missing or conflicting.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.care_case import CareCase, Task
from app.models.case_lifecycle_stage import CaseLifecycleStage
from app.services.task_service import TaskService
from app.services.lifecycle_service import LifecycleService, LIFECYCLE_TRANSITIONS


class ConsistencyCheckerService:
    """Audits and synchronizes database lifecycle states, tasks, and dashboard projections."""

    @classmethod
    def audit_cases(cls, db: Session, dry_run: bool = True) -> Dict[str, Any]:
        """
        Scans all care cases for corrupted lifecycle projections, missing evidence,
        or invalid stage completions.
        If dry_run=True, reports anomalies without modifying the database.
        If dry_run=False, reverts unverified stages and generates reconciliation tasks.
        """
        cases = db.query(CareCase).all()
        anomalies: List[Dict[str, Any]] = []
        corrupted_count = 0
        repaired_count = 0

        for case in cases:
            case_stages = (
                db.query(CaseLifecycleStage)
                .filter(CaseLifecycleStage.case_id == case.id)
                .order_by(CaseLifecycleStage.stage_number)
                .all()
            )

            # Check each stage for valid evidence and task dependencies
            for st in case_stages:
                if st.status != "completed":
                    continue

                rule = LIFECYCLE_TRANSITIONS.get(st.stage_number, {})
                allow_empty = rule.get("allow_empty_evidence", False)

                # 1. Missing evidence check
                has_evidence = bool(
                    st.evidence_id
                    or (st.evidence_data and len(st.evidence_data) > 0)
                    or (st.evidence_type and st.evidence_type != "none")
                )

                is_corrupted = False
                corruption_reason = ""

                if not has_evidence and not allow_empty and st.stage_number > 1:
                    is_corrupted = True
                    corruption_reason = f"Stage {st.stage_number} marked completed without required evidence."

                # 2. Strict Stage 14 doctor signoff check
                if st.stage_number == 14 and st.status == "completed":
                    ed = st.evidence_data or {}
                    if not (ed.get("doctor_signoff") or ed.get("closure_evidence_id") or ed.get("evidence_id")):
                        is_corrupted = True
                        corruption_reason = "Stage 14 marked completed without verified physician closure sign-off."

                # 3. Pending blocking task check
                pending_blocking_task = (
                    db.query(Task)
                    .filter(
                        Task.case_id == case.id,
                        Task.status.in_(["pending", "in_progress", "active"])
                    )
                    .all()
                )
                for pt in pending_blocking_task:
                    meta = pt.task_metadata or {}
                    if meta.get("stage_number") == st.stage_number:
                        is_corrupted = True
                        corruption_reason = f"Stage {st.stage_number} marked completed while required task '{pt.task_type}' (ID: {pt.id}) is still pending."
                        break

                if is_corrupted:
                    corrupted_count += 1
                    anomaly_item = {
                        "case_id": str(case.id),
                        "case_number": case.case_number,
                        "stage_number": st.stage_number,
                        "title": st.title,
                        "reason": corruption_reason,
                    }
                    anomalies.append(anomaly_item)

                    if not dry_run:
                        # Safely repair stage: revert from completed to active/pending
                        st.status = "active"
                        st.completed_at = None

                        # Synchronize JSON case_context
                        ctx = dict(case.case_context or {})
                        ctx_stages = ctx.get("lifecycle_stages", [])
                        for cs in ctx_stages:
                            if cs.get("stage_number") == st.stage_number:
                                cs["status"] = "active"
                                cs["completed_at"] = None
                                break
                        ctx["current_stage_number"] = st.stage_number
                        case.case_context = ctx

                        if case.status == "closed":
                            case.status = "active"
                            case.sla_status = "in_progress"

                        # Create reconciliation task for Care Coordinator
                        TaskService.create_task(
                            db,
                            patient_id=case.patient_id,
                            case_id=case.id,
                            task_type="consistency_reconciliation",
                            responsible_role="care_coordinator",
                            priority="urgent",
                            task_metadata={
                                "reason": corruption_reason,
                                "stage_number": st.stage_number,
                                "detected_at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                        repaired_count += 1

        if not dry_run:
            db.commit()

        return {
            "dry_run": dry_run,
            "total_cases_scanned": len(cases),
            "corrupted_count": corrupted_count,
            "repaired_count": repaired_count,
            "anomalies": anomalies,
        }
