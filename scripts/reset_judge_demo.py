#!/usr/bin/env python3
"""
CareBridge — Judge Demo State Reset Script
Restores the exact starting demo state:
- Cleans up any conversations, appointments, or higher-stage transitions created during a judge demo
- Resets Meera Krishnan's case (CASE-2026-JUDGE01) to:
  * Stage 1: COMPLETED
  * Stage 2: COMPLETED
  * Stage 3: COMPLETED
  * Stage 4: PENDING
  * Assigned to Dr. Arjun Menon, MD
- Re-seeds/verifies the demo cohort via seed_judge_demo()
"""

import os
import sys
from pathlib import Path

scripts_dir = Path(__file__).resolve().parent
repo_root = scripts_dir.parent
backend_dir = repo_root / "backend"
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(scripts_dir))

from sqlalchemy import select, and_, delete
from app.database.session import get_sync_db
from app.models.care_case import CareCase, Task
from app.models.appointment import Appointment
from app.models.communication import ConversationSession, Communication
from app.models.patient import Patient
from app.models.event_audit import CaseEvent
from app.models.closure import ClosureEvidence
from app.models.case_lifecycle_stage import CaseLifecycleStage
from seed_judge_demo import seed_judge_demo


def reset_judge_demo():
    print("Resetting CareBridge Judge Demo to exact starting state...")
    with get_sync_db() as db:
        case = db.execute(
            select(CareCase).where(CareCase.case_number == "CASE-2026-JUDGE01")
        ).scalar_one_or_none()

        patient = db.execute(
            select(Patient).where(Patient.mrn == "MRN-2026-0461")
        ).scalar_one_or_none()

        if case:
            # 1. Delete appointments on demo case
            db.execute(delete(Appointment).where(Appointment.case_id == case.id))

            # 2. Delete tasks created after initial setup
            db.execute(
                delete(Task).where(
                    and_(Task.case_id == case.id, Task.task_type.notin_(["initial_screening"]))
                )
            )

            # 3. Delete closure evidence
            db.execute(delete(ClosureEvidence).where(ClosureEvidence.case_id == case.id))

            # 4. Reset CaseLifecycleStage rows for stages >= 4
            stages_to_reset = db.execute(
                select(CaseLifecycleStage).where(
                    and_(CaseLifecycleStage.case_id == case.id, CaseLifecycleStage.stage_number >= 4)
                )
            ).scalars().all()
            for st in stages_to_reset:
                st.status = "pending"
                st.completed_at = None
                st.evidence_data = {}
                st.evidence_type = None
                st.evidence_id = None
                st.notes = None

            # 5. Delete post-stage-3 case events
            db.execute(
                delete(CaseEvent).where(
                    and_(
                        CaseEvent.case_id == case.id,
                        CaseEvent.event_type.in_([
                            "stage_4_patient_understands", "stage_5_clinical_review",
                            "stage_6_clinical_confirmation_message", "stage_7_referral_initiated",
                            "stage_8_referral_accepted", "stage_9_appointment_scheduled_confirmed",
                            "stage_10_consultation_completed", "stage_11_treatment_monitoring",
                            "stage_12_follow_up", "stage_13_documentation_completed",
                            "stage_14_verified_clinical_closure", "clinical_review_completed",
                            "appointment_booked", "clinical_closure_signed"
                        ])
                    )
                )
            )

        if patient:
            # 6. Delete communications and conversation sessions for demo patient
            sessions = db.execute(
                select(ConversationSession).where(ConversationSession.patient_id == patient.id)
            ).scalars().all()
            for s in sessions:
                db.execute(delete(Communication).where(Communication.session_id == s.id))
                db.delete(s)

        db.commit()

    # Re-run idempotent seed to restore exact records, stages, and notifications
    seed_judge_demo()
    print("CareBridge Judge Demo state successfully restored to initial baseline.")


if __name__ == "__main__":
    reset_judge_demo()
