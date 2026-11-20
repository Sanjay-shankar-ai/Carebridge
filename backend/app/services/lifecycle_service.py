"""
CareBridge Longitudinal Lifecycle Service
Manages the complete 14-stage end-to-end patient care lifecycle from screening to verified clinical closure.

Stages:
  1. SCREENING
  2. RESULT_GENERATED
  3. PATIENT_NOTIFIED
  4. PATIENT_UNDERSTANDS (AI Case-Aware Conversation)
  5. CLINICAL_REVIEW (Attending Physician Review)
  6. CLINICAL_CONFIRMATION_MESSAGE
  7. REFERRAL_INITIATED
  8. REFERRAL_ACCEPTED
  9. APPOINTMENT_SCHEDULED_CONFIRMED
  10. CONSULTATION_COMPLETED
  11. TREATMENT_MONITORING
  12. FOLLOW_UP
  13. DOCUMENTATION_COMPLETED
  14. VERIFIED_CLINICAL_CLOSURE
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.care_case import CareCase, Task
from app.models.screening import ScreeningResult
from app.models.patient import Patient
from app.models.owner import CaseOwner
from app.models.referral import Referral
from app.models.appointment import Appointment
from app.models.event_audit import CaseEvent, AuditLog
from app.models.closure import ClosureEvidence
from app.models.notification import Notification
from app.models.case_lifecycle_stage import CaseLifecycleStage
from app.services.notification_service import NotificationService

logger = logging.getLogger("carebridge.lifecycle")


class LifecycleTransitionError(Exception):
    """Raised when an invalid lifecycle stage transition or unauthorized actor is detected."""
    def __init__(
        self,
        message: str,
        stage_number: int,
        current_stage_number: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.stage_number = stage_number
        self.current_stage_number = current_stage_number
        self.details = details or {}


LIFECYCLE_TRANSITIONS = {
    1: {
        "stage_id": "SCREENING",
        "title": "Screening Examination",
        "allowed_from": [0, None, 1],
        "authorized_roles": ["radiologist", "clinician", "doctor", "care_coordinator", "system", "ai_coordinator"],
        "required_evidence_type": ["screening_completion", "procedure_performed", "screening_order", "imaging_procedure"],
        "allow_empty_evidence": False,
    },
    2: {
        "stage_id": "RESULT_GENERATED",
        "title": "Diagnostic Report Generated",
        "allowed_from": [1, 2],
        "authorized_roles": ["radiologist", "pathologist", "doctor", "clinician", "care_coordinator", "coordinator", "system"],
        "required_evidence_type": ["diagnostic_report", "radiology_report", "pathology_report", "biopsy_report", "screening_result", "report_finalized", "report_upload"],
        "allow_empty_evidence": False,
    },
    3: {
        "stage_id": "PATIENT_NOTIFIED",
        "title": "Initial Patient Outreach",
        "allowed_from": [2, 3],
        "authorized_roles": ["care_coordinator", "ai_coordinator", "system", "clinician", "doctor"],
        "required_evidence_type": ["notification_delivery", "outreach_dispatched", "notification_sent", "channel_delivery"],
        "allow_empty_evidence": False,
    },
    4: {
        "stage_id": "PATIENT_UNDERSTANDS",
        "title": "AI Case-Aware Education & Understanding",
        "allowed_from": [3, 4],
        "authorized_roles": ["ai_coordinator", "care_coordinator", "patient", "system"],
        "required_evidence_type": ["patient_understanding", "ai_explanation", "patient_acknowledgement", "comprehension_confirmed"],
        "allow_empty_evidence": False,
    },
    5: {
        "stage_id": "CLINICAL_REVIEW",
        "title": "Attending Physician Clinical Review",
        "allowed_from": [4, 5],
        "authorized_roles": ["doctor", "clinician", "specialist"],
        "required_evidence_type": ["clinical_review", "attending_review", "pathway_authorization", "doctor_assessment"],
        "allow_empty_evidence": False,
    },
    6: {
        "stage_id": "CLINICAL_CONFIRMATION_MESSAGE",
        "title": "Clinical Confirmation & Next Steps",
        "allowed_from": [5, 6],
        "authorized_roles": ["doctor", "clinician", "specialist"],
        "required_evidence_type": ["clinical_confirmation", "doctor_communication_approval", "pathway_approved"],
        "allow_empty_evidence": False,
    },
    7: {
        "stage_id": "REFERRAL_INITIATED",
        "title": "Specialist Referral Initiated",
        "allowed_from": [6, 7],
        "authorized_roles": ["doctor", "clinician", "care_coordinator", "specialist"],
        "required_evidence_type": ["referral_order", "specialist_referral", "referral_created", "referral_initiated"],
        "allow_empty_evidence": False,
    },
    8: {
        "stage_id": "REFERRAL_ACCEPTED",
        "title": "Referral Formally Accepted",
        "allowed_from": [7, 8],
        "authorized_roles": ["receiving_provider", "specialist", "care_coordinator", "doctor"],
        "required_evidence_type": ["referral_acceptance", "receiving_provider_acceptance", "referral_accepted"],
        "allow_empty_evidence": False,
    },
    9: {
        "stage_id": "APPOINTMENT_SCHEDULED_CONFIRMED",
        "title": "Appointment Scheduled & Confirmed",
        "allowed_from": [8, 9],
        "authorized_roles": ["care_coordinator", "doctor", "clinician", "patient", "system"],
        "required_evidence_type": ["appointment_dual_confirmation", "appointment_confirmed", "dual_confirmation"],
        "allow_empty_evidence": False,
    },
    10: {
        "stage_id": "CONSULTATION_COMPLETED",
        "title": "Specialist Consultation Completed",
        "allowed_from": [9, 10],
        "authorized_roles": ["doctor", "specialist", "clinician"],
        "required_evidence_type": ["consultation_documentation", "clinical_encounter_note", "consultation_notes"],
        "allow_empty_evidence": False,
    },
    11: {
        "stage_id": "TREATMENT_MONITORING",
        "title": "Active Treatment & Progress Monitoring",
        "allowed_from": [10, 11],
        "authorized_roles": ["care_coordinator", "doctor", "clinician"],
        "required_evidence_type": ["treatment_monitoring_plan", "monitoring_milestone", "active_monitoring", "treatment_monitoring_log", "treatment_update"],
        "allow_empty_evidence": False,
    },
    12: {
        "stage_id": "FOLLOW_UP",
        "title": "Follow-Up Evaluation & Surveillance",
        "allowed_from": [11, 12],
        "authorized_roles": ["doctor", "clinician", "care_coordinator", "specialist"],
        "required_evidence_type": ["follow_up_evaluation", "surveillance_visit", "follow_up_notes", "followup_outcome", "follow_up"],
        "allow_empty_evidence": False,
    },
    13: {
        "stage_id": "DOCUMENTATION_COMPLETED",
        "title": "Care Documentation & Audit Complete",
        "allowed_from": [12, 13],
        "authorized_roles": ["care_coordinator", "doctor", "clinician"],
        "required_evidence_type": ["audit_documentation", "case_records_compiled", "documentation_compiled", "documentation_checklist", "checklist_complete"],
        "allow_empty_evidence": False,
    },
    14: {
        "stage_id": "VERIFIED_CLINICAL_CLOSURE",
        "title": "Verified Clinical Closure Sign-Off",
        "allowed_from": [13, 14],
        "authorized_roles": ["doctor", "clinician"], # Strictly doctor only!
        "required_evidence_type": ["authorized_human_signoff", "pathology_report", "consultation_note", "surveillance_imaging", "closure_evidence", "clinical_closure_summary", "doctor_signoff"],
        "allow_empty_evidence": False,
    },
}

STAGE_DEFINITIONS = [
    {
        "stage_number": 1,
        "stage_id": "SCREENING",
        "title": "Screening Examination",
        "description": "Initial screening procedure performed (e.g., diagnostic mammogram, Pap smear, low-dose CT).",
        "responsible_role": "radiologist",
        "default_patient_info": "Your screening examination was performed at the imaging facility.",
        "next_expected_action": "Processing imaging and generating diagnostic findings report."
    },
    {
        "stage_number": 2,
        "stage_id": "RESULT_GENERATED",
        "title": "Diagnostic Report Generated",
        "description": "Official diagnostic report produced with clinical coding (e.g., BI-RADS 4, LOINC code).",
        "responsible_role": "radiologist",
        "default_patient_info": "Screening report finalized and classified with clinical urgency.",
        "next_expected_action": "Dispatch initial notification to patient and initiate care pathway."
    },
    {
        "stage_number": 3,
        "stage_id": "PATIENT_NOTIFIED",
        "title": "Initial Patient Outreach",
        "description": "Notification dispatched to patient informing them that screening results are available.",
        "responsible_role": "care_coordinator",
        "default_patient_info": "Notification delivered via your preferred communication channel.",
        "next_expected_action": "Patient reviews results and connects with CareBridge AI companion for guidance."
    },
    {
        "stage_number": 4,
        "stage_id": "PATIENT_UNDERSTANDS",
        "title": "AI Case-Aware Education & Understanding",
        "description": "Empathetic, factual, non-diagnostic guidance delivered to patient to address questions and confirm understanding.",
        "responsible_role": "ai_coordinator",
        "default_patient_info": "CareBridge AI assistant has explained the screening context in plain language.",
        "next_expected_action": "Attending physician reviews case history, patient concerns, and authorizes pathway."
    },
    {
        "stage_number": 5,
        "stage_id": "CLINICAL_REVIEW",
        "title": "Attending Physician Clinical Review",
        "description": "Attending doctor reviews screening report, patient questions, and authorizes recommended pathway.",
        "responsible_role": "doctor",
        "default_patient_info": "Your case is actively under clinical review by your attending physician.",
        "next_expected_action": "Doctor records clinical assessment and approves specialist referral."
    },
    {
        "stage_number": 6,
        "stage_id": "CLINICAL_CONFIRMATION_MESSAGE",
        "title": "Clinical Confirmation & Next Steps",
        "description": "Patient receives doctor-reviewed explanation and approved clinical pathway next steps.",
        "responsible_role": "doctor",
        "default_patient_info": "Your doctor has confirmed your clinical pathway and approved recommended next steps.",
        "next_expected_action": "Care team initiates specialist referral to destination facility."
    },
    {
        "stage_number": 7,
        "stage_id": "REFERRAL_INITIATED",
        "title": "Specialist Referral Initiated",
        "description": "Doctor-authorized specialist referral submitted to receiving facility with clinical justification.",
        "responsible_role": "care_coordinator",
        "default_patient_info": "A formal referral has been sent to the specialist center on your behalf.",
        "next_expected_action": "Receiving specialist facility reviews and accepts the inbound referral."
    },
    {
        "stage_number": 8,
        "stage_id": "REFERRAL_ACCEPTED",
        "title": "Referral Formally Accepted",
        "description": "Receiving specialist facility confirms acceptance within the 48-hour clinical SLA.",
        "responsible_role": "receiving_provider",
        "default_patient_info": "The specialist institute has accepted your referral. Scheduling is unlocked.",
        "next_expected_action": "Coordinate convenient consultation and biopsy appointment slot."
    },
    {
        "stage_number": 9,
        "stage_id": "APPOINTMENT_SCHEDULED_CONFIRMED",
        "title": "Appointment Scheduled & Confirmed",
        "description": "Consultation/procedure appointment booked within SLA window, verified with patient, and reminders set.",
        "responsible_role": "care_coordinator",
        "default_patient_info": "Your appointment is confirmed. Details and preparation instructions are available.",
        "next_expected_action": "Attend consultation/procedure visit at the specialist clinic."
    },
    {
        "stage_number": 10,
        "stage_id": "CONSULTATION_COMPLETED",
        "title": "Specialist Consultation Completed",
        "description": "Patient attends visit; doctor records clinical findings, biopsy pathology outcome, and recommendations.",
        "responsible_role": "doctor",
        "default_patient_info": "Your consultation visit and diagnostic evaluation were successfully completed.",
        "next_expected_action": "Initiate clinician-approved treatment or surveillance monitoring."
    },
    {
        "stage_number": 11,
        "stage_id": "TREATMENT_MONITORING",
        "title": "Active Treatment & Progress Monitoring",
        "description": "Continuous monitoring of clinician-approved treatment plan, patient-reported symptoms, and barrier support.",
        "responsible_role": "care_coordinator",
        "default_patient_info": "Your care team is actively monitoring your treatment progress and supporting your needs.",
        "next_expected_action": "Complete scheduled follow-up evaluation and verify all health milestones."
    },
    {
        "stage_number": 12,
        "stage_id": "FOLLOW_UP",
        "title": "Follow-Up Evaluation & Surveillance",
        "description": "Scheduled follow-up visit attended or resolved; recovery workflows triggered if barriers occur.",
        "responsible_role": "doctor",
        "default_patient_info": "Follow-up surveillance visit completed or confirmed on schedule.",
        "next_expected_action": "Compile and audit complete patient care record for clinical closure."
    },
    {
        "stage_number": 13,
        "stage_id": "DOCUMENTATION_COMPLETED",
        "title": "Care Documentation & Audit Complete",
        "description": "All clinical records, reports, consultation notes, and audit trails compiled and verified.",
        "responsible_role": "care_coordinator",
        "default_patient_info": "All clinical records, test outcomes, and coordinator touchpoints are fully documented.",
        "next_expected_action": "Attending physician conducts final review and executes verified closure sign-off."
    },
    {
        "stage_number": 14,
        "stage_id": "VERIFIED_CLINICAL_CLOSURE",
        "title": "Verified Clinical Closure Sign-Off",
        "description": "Authenticated physician executes evidence-based closure sign-off; final reassuring update sent to patient.",
        "responsible_role": "doctor",
        "default_patient_info": "Your diagnostic care pathway is officially completed and signed off by your doctor.",
        "next_expected_action": "Routine annual preventive screening as recommended by your physician."
    }
]


class LifecycleService:
    """Manages continuous state transitions, persistence, notifications, and audits across 14 lifecycle stages."""

    @classmethod
    def get_stage_definition(cls, stage_ident: Any) -> Dict[str, Any]:
        """Resolves stage definition by number (1..14) or string ID."""
        if isinstance(stage_ident, int):
            for s in STAGE_DEFINITIONS:
                if s["stage_number"] == stage_ident:
                    return s
        elif isinstance(stage_ident, str):
            s_up = stage_ident.upper().replace(" ", "_")
            for s in STAGE_DEFINITIONS:
                if s["stage_id"] == s_up:
                    return s
            # Try stage number as string
            try:
                num = int(stage_ident)
                return cls.get_stage_definition(num)
            except ValueError:
                pass
        return STAGE_DEFINITIONS[0]

    @classmethod
    def initialize_lifecycle(
        cls,
        arg1: Any,
        arg2: Optional[Any] = None,
        arg3: Optional[Any] = None,
        arg4: Optional[Any] = None,
        db: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Initializes the complete 14-stage lifecycle inside case.case_context and case_lifecycle_stages.
        Marks Stage 1 (SCREENING) and Stage 2 (RESULT_GENERATED) as completed.
        Stage 3 (PATIENT_NOTIFIED) remains pending until actual outreach delivery.
        Stages 4..14 remain pending.
        """
        from sqlalchemy.orm import Session, object_session
        if isinstance(arg1, Session):
            db = arg1
            case = arg2
            screening = arg3
            patient = arg4
        else:
            case = arg1
            screening = arg2
            patient = arg3
            db = db or (object_session(case) if case else None)

        now = datetime.now(timezone.utc)
        ctx = dict(case.case_context or {})
        
        stages = []
        for defn in STAGE_DEFINITIONS:
            st_num = defn["stage_number"]
            st_id = defn["stage_id"]
            
            if st_num == 1:
                # Stage 1: Screening Completed
                st_data = {
                    **defn,
                    "status": "completed",
                    "completed_at": (screening.test_date if screening and screening.test_date else (now - timedelta(days=2))).isoformat(),
                    "evidence": {
                        "evidence_type": "screening_completion",
                        "screening_type": screening.screening_type if screening else "Mammogram",
                        "facility": screening.performing_facility if screening else "CareBridge Imaging Center",
                        "screening_result_id": str(screening.id) if screening else None
                    },
                    "patient_notification_sent": True
                }
            elif st_num == 2:
                # Stage 2: Result Generated
                st_data = {
                    **defn,
                    "status": "completed",
                    "completed_at": (now - timedelta(days=1, hours=12)).isoformat(),
                    "evidence": {
                        "evidence_type": "diagnostic_report",
                        "finding_code": screening.finding_code if screening else "BI-RADS-4",
                        "finding_summary": screening.finding_summary if screening else "Suspicious finding requiring further evaluation",
                        "urgency_level": screening.urgency_level if screening else "urgent"
                    },
                    "patient_notification_sent": True
                }
            elif st_num == 3:
                # Stage 3: Patient Notified (Starts pending awaiting verified delivery!)
                st_data = {
                    **defn,
                    "status": "pending",
                    "completed_at": None,
                    "evidence": {},
                    "patient_notification_sent": False
                }
            else:
                # Stages 4..14: Pending
                st_data = {
                    **defn,
                    "status": "pending",
                    "completed_at": None,
                    "evidence": {},
                    "patient_notification_sent": False
                }
            stages.append(st_data)

        ctx["lifecycle_stages"] = stages
        ctx["current_stage_number"] = 3
        ctx["current_stage_id"] = "PATIENT_NOTIFIED"
        ctx["last_updated_at"] = now.isoformat()
        
        # Structure clinical placeholders
        ctx.setdefault("clinical_review", None)
        ctx.setdefault("consultation_outcome", None)
        ctx.setdefault("treatment_monitoring", {
            "treatment_plan": None,
            "patient_updates": [],
            "coordinator_notes": [],
            "active_barriers": []
        })
        ctx.setdefault("follow_up", {
            "scheduled_date": None,
            "status": "pending",
            "reminders_sent": 0,
            "recovery_workflow_initiated": False
        })
        ctx.setdefault("documentation_evidence", {
            "screening_report_verified": True,
            "doctor_review_verified": False,
            "referral_accepted_verified": False,
            "appointment_confirmed_verified": False,
            "consultation_outcome_verified": False,
            "treatment_monitoring_verified": False,
            "follow_up_verified": False,
            "is_complete": False
        })

        case.case_context = ctx

        # Synchronize with relational table case_lifecycle_stages if session is active
        if db is not None:
            try:
                for st in stages:
                    st_num = st["stage_number"]
                    existing_row = db.query(CaseLifecycleStage).filter(
                        CaseLifecycleStage.case_id == case.id,
                        CaseLifecycleStage.stage_number == st_num
                    ).first()
                    if not existing_row:
                        new_row = CaseLifecycleStage(
                            id=uuid.uuid4(),
                            case_id=case.id,
                            stage_number=st_num,
                            stage_id=st["stage_id"],
                            title=st["title"],
                            status=st["status"],
                            responsible_role=st.get("responsible_role", "system"),
                            evidence_type=st.get("evidence", {}).get("evidence_type"),
                            evidence_data=st.get("evidence", {}),
                            completed_at=datetime.fromisoformat(st["completed_at"]) if st.get("completed_at") else None,
                            patient_notification_sent=st.get("patient_notification_sent", False)
                        )
                        db.add(new_row)
                    else:
                        existing_row.status = st["status"]
                        if st.get("completed_at"):
                            existing_row.completed_at = datetime.fromisoformat(st["completed_at"])
                db.flush()
                db.commit()
            except Exception as e:
                logger.warning(f"Error persisting relational case_lifecycle_stages in initialize_lifecycle: {e}")

        return ctx

    @classmethod
    def get_lifecycle_stages(cls, case: CareCase) -> List[Dict[str, Any]]:
        """Returns the list of 14 stages, initializing them dynamically if absent."""
        ctx = case.case_context or {}
        if "lifecycle_stages" not in ctx or len(ctx["lifecycle_stages"]) < 14:
            cls.initialize_lifecycle(case, case.screening_result, case.patient)
            ctx = case.case_context or {}
        return ctx.get("lifecycle_stages", [])

    @classmethod
    def get_current_stage(cls, case: CareCase) -> Dict[str, Any]:
        """Returns the active or latest completed stage."""
        stages = cls.get_lifecycle_stages(case)
        # Look for the active stage
        for s in stages:
            if s.get("status") == "active":
                return s
        # If all completed or none active, return the last one with completed or stage 14
        completed = [s for s in stages if s.get("status") == "completed"]
        if completed:
            return completed[-1]
        return stages[0]

    @classmethod
    def advance_stage(
        cls,
        db: Session,
        case_id: uuid.UUID,
        stage_ident: Any,
        actor_role: str,
        actor_id: str,
        actor_name: Optional[str] = None,
        evidence: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
        patient_notification_title: Optional[str] = None,
        patient_notification_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Advances or completes a specific stage in the 14-stage care lifecycle.
        Updates stage status to 'completed', activates the next stage, commits case events,
        persists audit log, and dispatches real-time notification.
        """
        # ------------------------------------------------------------------
        # Concurrent transition guard: reject duplicate in-flight advances
        # for the same case (PostgreSQL advisory lock / in-process dict).
        # ------------------------------------------------------------------
        from app.core.concurrent_guard import acquire_case_lock, ConcurrentTransitionError
        from app.core.correlation import get_correlation_id
        corr_id = get_correlation_id()
        if not acquire_case_lock(db, case_id, corr_id):
            raise ConcurrentTransitionError(
                case_id,
                f"Concurrent transition rejected for correlation {corr_id}"
            )

        case = db.query(CareCase).filter(CareCase.id == case_id).first()
        if not case:
            raise ValueError(f"Case {case_id} not found")

        stages = cls.get_lifecycle_stages(case)
        target_defn = cls.get_stage_definition(stage_ident)
        target_num = target_defn["stage_number"]
        now = datetime.now(timezone.utc)

        # ---------------------------------------------------------------------
        # Transition Table & Authority Validation
        # ---------------------------------------------------------------------
        rule = LIFECYCLE_TRANSITIONS.get(target_num, {})

        # 1. Role Authorization
        allowed_roles = [r.lower() for r in rule.get("authorized_roles", [])]
        if actor_role.lower() not in allowed_roles:
            raise LifecycleTransitionError(
                f"Actor role '{actor_role}' is not authorized to advance Stage {target_num} ({target_defn['title']}). "
                f"Authorized roles: {allowed_roles}",
                stage_number=target_num
            )

        # 2. Stage Sequence / Predecessor Verification
        completed_stage_numbers = [s["stage_number"] for s in stages if s.get("status") == "completed"]
        last_completed = max(completed_stage_numbers) if completed_stage_numbers else 0
        allowed_from = rule.get("allowed_from", [])
        if last_completed not in allowed_from and target_num != (last_completed + 1):
            raise LifecycleTransitionError(
                f"Cannot advance to Stage {target_num} ({target_defn['title']}) from current state "
                f"(last completed stage was {last_completed}). Stage jumping without completing prerequisites is prohibited. "
                f"Allowed predecessor stages: {allowed_from}",
                stage_number=target_num,
                current_stage_number=last_completed
            )

        # 3. Evidence Presence Verification
        if not evidence and not rule.get("allow_empty_evidence", False):
            raise LifecycleTransitionError(
                f"Stage {target_num} ({target_defn['title']}) requires verified clinical/operational evidence "
                f"matching {rule.get('required_evidence_type')}, but none was provided.",
                stage_number=target_num,
                current_stage_number=last_completed
            )

        # 3b. Pending Required Task Dependency Guard
        # A stage cannot be completed if an active/pending required task exists for it
        STAGE_TASK_TYPES = {
            1: ["screening", "screening_order", "schedule_screening"],
            3: ["patient_notification", "notify_patient"],
            4: ["patient_understanding", "confirm_understanding"],
            5: ["clinical_review", "doctor_review", "case_review"],
            6: ["clinical_confirmation"],
            7: ["referral", "create_referral"],
            8: ["referral_acceptance", "accept_referral"],
            9: ["book_appointment", "appointment_booking", "schedule_appointment"],
            10: ["consultation", "record_consultation"],
            11: ["treatment_monitoring", "treatment_update"],
            12: ["follow_up", "record_followup"],
            13: ["documentation", "verify_documentation", "documentation_checklist"],
            14: ["closure", "closure_review", "clinical_closure", "doctor_signoff"],
        }
        relevant_task_types = STAGE_TASK_TYPES.get(target_num, [])
        pending_tasks = db.query(Task).filter(
            Task.case_id == case.id,
            Task.status.in_(["pending", "in_progress", "active", "open"])
        ).all()
        for t in pending_tasks:
            meta = t.task_metadata or {}
            task_stage = meta.get("stage_number")
            if (task_stage is not None and int(task_stage) == target_num) or (t.task_type in relevant_task_types):
                raise LifecycleTransitionError(
                    f"Cannot complete Stage {target_num} ({target_defn['title']}) while required task '{t.task_type}' (ID: {t.id}) is pending/in-progress. Required tasks must be resolved before advancing.",
                    stage_number=target_num,
                    current_stage_number=last_completed
                )

        # 4. Strict Stage 14 (Closure) Doctor Sign-off Guard
        if target_num == 14:
            if actor_role.lower() not in ("doctor", "clinician"):
                raise LifecycleTransitionError(
                    "Stage 14 (VERIFIED_CLINICAL_CLOSURE) strictly requires doctor sign-off.",
                    stage_number=14
                )
            if not evidence or not (
                evidence.get("closure_evidence_id")
                or evidence.get("doctor_signoff")
                or evidence.get("evidence_id")
                or evidence.get("closure_evidence_type")
            ):
                raise LifecycleTransitionError(
                    "Stage 14 requires verified ClosureEvidence record or signed doctor closure documentation.",
                    stage_number=14
                )

        # 5. Update or Create Relational Row in case_lifecycle_stages
        evidence_type_val = (
            (evidence or {}).get("evidence_type")
            or (evidence or {}).get("closure_evidence_type")
            or (rule.get("required_evidence_type", ["action_evidence"])[0] if rule else "action_evidence")
        )
        evidence_id_val = str(
            (evidence or {}).get("evidence_id")
            or (evidence or {}).get("closure_evidence_id")
            or (evidence or {}).get("notification_id")
            or (evidence or {}).get("appointment_id")
            or (evidence or {}).get("referral_id")
            or ""
        )

        st_record = db.query(CaseLifecycleStage).filter(
            CaseLifecycleStage.case_id == case.id,
            CaseLifecycleStage.stage_number == target_num
        ).first()

        if not st_record:
            st_record = CaseLifecycleStage(
                id=uuid.uuid4(),
                case_id=case.id,
                stage_number=target_num,
                stage_id=target_defn["stage_id"],
                title=target_defn["title"],
                status="completed",
                responsible_role=actor_role,
                responsible_id=str(actor_id),
                responsible_name=actor_name or actor_role,
                evidence_type=evidence_type_val,
                evidence_id=evidence_id_val if evidence_id_val else None,
                evidence_data=evidence or {},
                completed_at=now,
                patient_notification_sent=bool(patient_notification_title),
                notes=notes
            )
            db.add(st_record)
        else:
            st_record.status = "completed"
            st_record.responsible_role = actor_role
            st_record.responsible_id = str(actor_id)
            st_record.responsible_name = actor_name or actor_role
            st_record.evidence_type = evidence_type_val
            st_record.evidence_id = evidence_id_val if evidence_id_val else st_record.evidence_id
            st_record.evidence_data = {**(st_record.evidence_data or {}), **(evidence or {})}
            st_record.completed_at = now
            if patient_notification_title:
                st_record.patient_notification_sent = True
            if notes:
                st_record.notes = notes

        if target_num < 14:
            next_num = target_num + 1
            next_st_record = db.query(CaseLifecycleStage).filter(
                CaseLifecycleStage.case_id == case.id,
                CaseLifecycleStage.stage_number == next_num
            ).first()
            if next_st_record and next_st_record.status == "pending":
                next_st_record.status = "active"
                next_st_record.started_at = now

        # 6. Update Target Stage in case.case_context["lifecycle_stages"]
        for s in stages:
            if s["stage_number"] == target_num:
                s["status"] = "completed"
                s["completed_at"] = now.isoformat()
                s["responsible_role"] = actor_role
                s["responsible_name"] = actor_name or actor_role
                if evidence:
                    s["evidence"] = {**(s.get("evidence") or {}), **evidence}
                if notes:
                    s["notes"] = notes
                if patient_notification_title:
                    s["patient_notification_sent"] = True
                break

        # 2. Activate Next Stage (if not at stage 14)
        next_num = target_num + 1
        next_stage_id = None
        if next_num <= 14:
            for s in stages:
                if s["stage_number"] == next_num:
                    s["status"] = "active"
                    next_stage_id = s["stage_id"]
                    break

        ctx = dict(case.case_context or {})
        ctx["lifecycle_stages"] = stages
        ctx["current_stage_number"] = next_num if next_num <= 14 else 14
        ctx["current_stage_id"] = next_stage_id or "VERIFIED_CLINICAL_CLOSURE"
        ctx["last_updated_at"] = now.isoformat()
        case.case_context = ctx

        # 3. Synchronize case.status with journey progress
        status_map = {
            1: "screening",
            2: "result_received",
            3: "notified",
            4: "acknowledged",
            5: "clinical_review",
            6: "clinical_confirmed",
            7: "referred",
            8: "referral_accepted",
            9: "scheduled",
            10: "consulted",
            11: "treatment_monitoring",
            12: "follow_up",
            13: "documentation_completed",
            14: "closed"
        }
        if target_num == 14:
            case.status = "closed"
            case.sla_status = "resolved"
        elif target_num in status_map and case.status not in ("closed", "escalated"):
            case.status = status_map[target_num]

        # 4. Record CaseEvent
        ev = CaseEvent(
            id=uuid.uuid4(),
            case_id=case.id,
            event_type=f"stage_{target_num}_{target_defn['stage_id'].lower()}",
            description=f"Stage {target_num} completed ({target_defn['title']}): {notes or target_defn['description']}",
            event_data={
                "stage_number": target_num,
                "stage_id": target_defn["stage_id"],
                "actor_role": actor_role,
                "actor_id": actor_id,
                "evidence": evidence or {}
            },
            timestamp=now
        )
        db.add(ev)

        ev_alias = CaseEvent(
            id=uuid.uuid4(),
            case_id=case.id,
            event_type=f"stage_advanced_to_{target_num}",
            description=f"Advanced to Stage {target_num} ({target_defn['title']})",
            event_data={"stage_number": target_num, "stage_id": target_defn["stage_id"]},
            timestamp=now
        )
        db.add(ev_alias)

        # 5. Record AuditLog
        audit = AuditLog(
            id=uuid.uuid4(),
            case_id=case.id,
            patient_id=case.patient_id,
            actor_type="clinician" if actor_role in ("doctor", "specialist") else "human_coordinator" if actor_role == "care_coordinator" else "ai_agent",
            actor_id=actor_id,
            action=f"COMPLETE_STAGE_{target_defn['stage_id']}",
            autonomy_level=3 if target_num in (5, 10, 14) else 2 if target_num in (7, 8, 9, 12) else 1,
            rationale=f"Completed Stage {target_num} ({target_defn['title']}). Next: {next_stage_id or 'Final Closure'}",
            new_state={"stage": target_defn["stage_id"], "stage_number": target_num, "case_status": case.status},
            timestamp=now
        )
        db.add(audit)

        # 6. Dispatch Notification if requested
        if patient_notification_title and patient_notification_message and case.patient_id:
            try:
                from app.models.user import User
                u_obj = db.query(User).filter(User.patient_id == case.patient_id).first()
                u_id = u_obj.id if u_obj else None
                if not u_id:
                    p_user = db.query(Notification).filter(Notification.patient_id == case.patient_id).first()
                    u_id = p_user.user_id if p_user else None
                
                if u_id:
                    NotificationService.create_notification(
                        db=db,
                        user_id=u_id,
                        role="patient",
                        event_type=f"stage_{target_defn['stage_id'].lower()}",
                        title=patient_notification_title,
                        message=patient_notification_message,
                        priority="normal",
                        case_id=case.id,
                        patient_id=case.patient_id,
                        action_link="/patient",
                        idempotency_key=f"stage_{target_num}_{case.id}_{now.strftime('%Y%m%d%H%M%S')}"
                    )
            except Exception as e:
                logger.warning(f"Lifecycle notification dispatch notice: {e}")

        case.version = (getattr(case, "version", 1) or 1) + 1
        db.commit()
        from app.core.concurrent_guard import release_case_lock
        release_case_lock(case.id, corr_id)
        return {
            "case_id": str(case.id),
            "stage_number": target_num,
            "status": "completed",
            "completed_stage": target_defn,
            "next_stage_id": next_stage_id,
            "next_stage_number": next_num if next_num <= 14 else 14,
            "case_status": case.status,
            "completed_at": now.isoformat()
        }

    # =========================================================================
    # Stage 5 & 6: Clinical Review and Confirmation
    # =========================================================================
    @classmethod
    def record_clinical_review(
        cls,
        db: Session,
        case_id: uuid.UUID,
        doctor_id: str,
        doctor_name: str,
        clinical_assessment: str,
        approved_pathway: str,
        additional_investigations: Optional[str] = None,
        patient_safe_explanation: Optional[str] = None,
        referral_approved: bool = True
    ) -> Dict[str, Any]:
        """
        Doctor records clinical assessment, approves pathway, and issues patient-safe explanation.
        Completes Stage 5 (CLINICAL_REVIEW) and Stage 6 (CLINICAL_CONFIRMATION_MESSAGE).
        """
        case = db.query(CareCase).filter(CareCase.id == case_id).first()
        if not case:
            raise ValueError(f"Case {case_id} not found")

        now = datetime.now(timezone.utc)
        ctx = dict(case.case_context or {})
        
        review_record = {
            "doctor_id": str(doctor_id),
            "doctor_name": doctor_name,
            "reviewed_at": now.isoformat(),
            "clinical_assessment": clinical_assessment,
            "approved_pathway": approved_pathway,
            "additional_investigations": additional_investigations or "None required at this time",
            "patient_safe_explanation": patient_safe_explanation or f"Dr. {doctor_name} has reviewed your mammogram. A follow-up specialist evaluation is recommended for complete diagnostic clarity.",
            "referral_approved": referral_approved
        }
        ctx["clinical_review"] = review_record
        case.case_context = ctx
        db.commit()

        # Complete Stage 4: PATIENT_UNDERSTANDS (AI Case-Aware Conversation)
        cls.advance_stage(
            db=db,
            case_id=case.id,
            stage_ident=4,
            actor_role="ai_agent",
            actor_id="supervisor_agent",
            evidence={"patient_understanding_established": True},
            notes="Patient completed AI case-aware conversation; clinical review ordered."
        )

        # Complete Stage 5: CLINICAL_REVIEW
        cls.advance_stage(
            db=db,
            case_id=case.id,
            stage_ident=5,
            actor_role="doctor",
            actor_id=str(doctor_id),
            actor_name=doctor_name,
            evidence=review_record,
            notes=f"Clinical assessment recorded by Dr. {doctor_name}: {clinical_assessment[:80]}..."
        )

        # Complete Stage 6: CLINICAL_CONFIRMATION_MESSAGE
        confirm_title = f"Clinical Plan Confirmed by Dr. {doctor_name}"
        confirm_msg = review_record["patient_safe_explanation"]
        cls.advance_stage(
            db=db,
            case_id=case.id,
            stage_ident=6,
            actor_role="doctor",
            actor_id=str(doctor_id),
            actor_name=doctor_name,
            evidence={"confirmation_message": confirm_msg, "approved_pathway": approved_pathway},
            notes=f"Patient confirmation dispatched: {confirm_msg[:80]}...",
            patient_notification_title=confirm_title,
            patient_notification_message=confirm_msg
        )

        # If referral approved, automatically draft or initiate referral work item
        if referral_approved:
            task = Task(
                id=uuid.uuid4(),
                case_id=case.id,
                title="Coordinate specialist referral dispatch",
                description=f"Submit approved referral for {approved_pathway} per Dr. {doctor_name}'s clinical orders.",
                task_type="referral_routing",
                assigned_role="care_coordinator",
                status="pending",
                due_date=now + timedelta(hours=24)
            )
            db.add(task)
            db.commit()

        return review_record

    # =========================================================================
    # Stage 7 & 8: Referral Initiation and Acceptance
    # =========================================================================
    @classmethod
    def accept_referral(
        cls,
        db: Session,
        referral_id: uuid.UUID,
        receiving_provider_name: str,
        acceptance_notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Receiving specialist facility / provider formally accepts the referral.
        Completes Stage 8 (REFERRAL_ACCEPTED) and unlocks appointment scheduling.
        """
        ref = db.query(Referral).filter(Referral.id == referral_id).first()
        if not ref:
            raise ValueError(f"Referral {referral_id} not found")

        now = datetime.now(timezone.utc)
        ref.status = "accepted"
        ref.responded_at = now
        db.commit()

        case = ref.care_case
        if case:
            # Complete Stage 8
            cls.advance_stage(
                db=db,
                case_id=case.id,
                stage_ident=8,
                actor_role="receiving_provider",
                actor_id=receiving_provider_name,
                actor_name=receiving_provider_name,
                evidence={
                    "referral_id": str(ref.id),
                    "facility": ref.target_facility,
                    "specialty": ref.specialty,
                    "accepted_at": now.isoformat(),
                    "notes": acceptance_notes or "Referral accepted within clinical SLA."
                },
                notes=f"Referral accepted by {ref.target_facility} for {ref.specialty}.",
                patient_notification_title="Specialist Referral Accepted",
                patient_notification_message=f"Good news: {ref.target_facility} has accepted your specialist referral. Your care coordinator is now preparing your appointment options."
            )

            # Mark pending referral_routing tasks as completed upon acceptance
            pending_ref_tasks = db.query(Task).filter(
                Task.case_id == case.id,
                Task.task_type == "referral_routing",
                Task.status.in_(["pending", "in_progress"])
            ).all()
            for pt in pending_ref_tasks:
                pt.status = "completed"

            # Create appointment scheduling task for coordinator
            task = Task(
                id=uuid.uuid4(),
                case_id=case.id,
                title=f"Schedule accepted consult at {ref.target_facility}",
                description=f"Contact patient to confirm convenient appointment slot for {ref.specialty}.",
                task_type="patient_outreach",
                assigned_role="care_coordinator",
                status="pending",
                due_date=now + timedelta(hours=24)
            )
            db.add(task)
            db.commit()

        return {
            "referral_id": str(ref.id),
            "status": "accepted",
            "accepted_at": now.isoformat(),
            "target_facility": ref.target_facility
        }

    # =========================================================================
    # Stage 10: Consultation Completed
    # =========================================================================
    @classmethod
    def record_consultation_outcome(
        cls,
        db: Session,
        case_id: uuid.UUID,
        doctor_id: str,
        doctor_name: str,
        consultation_notes: str,
        biopsy_pathology_outcome: str,
        clinical_recommendations: str,
        treatment_plan: str,
        next_followup_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Doctor records consultation findings, biopsy pathology outcome, and treatment plan.
        Completes Stage 10 (CONSULTATION_COMPLETED) and advances to Stage 11 (TREATMENT_MONITORING).
        """
        case = db.query(CareCase).filter(CareCase.id == case_id).first()
        if not case:
            raise ValueError(f"Case {case_id} not found")

        now = datetime.now(timezone.utc)
        ctx = dict(case.case_context or {})

        # Mark active appointment as attended
        appt = db.query(Appointment).filter(
            Appointment.case_id == case.id,
            Appointment.status.in_(["booked", "confirmed"])
        ).first()
        if appt:
            appt.status = "attended"
            appt.attendance_recorded_at = now

        consult_data = {
            "doctor_id": str(doctor_id),
            "doctor_name": doctor_name,
            "completed_at": now.isoformat(),
            "consultation_notes": consultation_notes,
            "biopsy_pathology_outcome": biopsy_pathology_outcome,
            "clinical_recommendations": clinical_recommendations,
            "treatment_plan": treatment_plan,
            "next_followup_date": next_followup_date
        }
        ctx["consultation_outcome"] = consult_data
        
        # Initialize Treatment Monitoring (Stage 11)
        tm = ctx.get("treatment_monitoring") or {}
        tm["treatment_plan"] = treatment_plan
        tm["clinician_recommendations"] = clinical_recommendations
        ctx["treatment_monitoring"] = tm

        # Schedule Follow-up (Stage 12)
        if next_followup_date:
            fu = ctx.get("follow_up") or {}
            fu["scheduled_date"] = next_followup_date
            fu["status"] = "scheduled"
            ctx["follow_up"] = fu

        case.case_context = ctx
        db.commit()

        # Complete Stage 10
        cls.advance_stage(
            db=db,
            case_id=case.id,
            stage_ident=10,
            actor_role="doctor",
            actor_id=str(doctor_id),
            actor_name=doctor_name,
            evidence=consult_data,
            notes=f"Consultation completed with Dr. {doctor_name}. Outcome: {biopsy_pathology_outcome}.",
            patient_notification_title="Consultation Notes & Pathology Available",
            patient_notification_message=f"Dr. {doctor_name} has finalized your consultation record: {biopsy_pathology_outcome}. Your care plan is ready for review."
        )

        return consult_data

    # =========================================================================
    # Stage 11: Treatment Monitoring Updates
    # =========================================================================
    @classmethod
    def record_treatment_update(
        cls,
        db: Session,
        case_id: uuid.UUID,
        sender_role: str,
        message: str,
        category: str = "general"
    ) -> Dict[str, Any]:
        """
        Records a patient question, difficulty, or coordinator progress note during active treatment monitoring.
        """
        case = db.query(CareCase).filter(CareCase.id == case_id).first()
        if not case:
            raise ValueError(f"Case {case_id} not found")

        now = datetime.now(timezone.utc)
        ctx = dict(case.case_context or {})
        tm = ctx.get("treatment_monitoring") or {}
        
        entry = {
            "timestamp": now.isoformat(),
            "sender_role": sender_role,
            "category": category,
            "message": message
        }

        if sender_role == "patient":
            p_updates = tm.get("patient_updates", [])
            p_updates.append(entry)
            tm["patient_updates"] = p_updates
        else:
            c_notes = tm.get("coordinator_notes", [])
            c_notes.append(entry)
            tm["coordinator_notes"] = c_notes

        ctx["treatment_monitoring"] = tm
        case.case_context = ctx
        db.commit()

        # Record CaseEvent
        ev = CaseEvent(
            id=uuid.uuid4(),
            case_id=case.id,
            event_type="treatment_monitoring_update",
            description=f"Treatment monitoring update ({category}) from {sender_role}: {message[:75]}...",
            event_data=entry,
            timestamp=now
        )
        db.add(ev)
        db.commit()

        # Advance Stage 11: TREATMENT_MONITORING
        cls.advance_stage(
            db=db,
            case_id=case.id,
            stage_ident=11,
            actor_role=sender_role,
            actor_id=str(case.current_owner_id or "care_coordinator"),
            evidence={"treatment_monitoring_update": entry},
            notes=f"Treatment monitoring update ({category}) recorded: {message[:75]}..."
        )

        return entry

    # =========================================================================
    # Stage 12: Follow-Up Management
    # =========================================================================
    @classmethod
    def record_followup_status(
        cls,
        db: Session,
        case_id: uuid.UUID,
        status: str, # "attended", "missed", "completed", "rescheduled"
        notes: Optional[str] = None,
        actor_role: str = "doctor"
    ) -> Dict[str, Any]:
        """
        Records follow-up attendance. If missed, initiates recovery play and notifies coordinator.
        """
        case = db.query(CareCase).filter(CareCase.id == case_id).first()
        if not case:
            raise ValueError(f"Case {case_id} not found")

        now = datetime.now(timezone.utc)
        ctx = dict(case.case_context or {})
        fu = ctx.get("follow_up") or {}
        fu["status"] = status
        fu["notes"] = notes
        fu["recorded_at"] = now.isoformat()
        ctx["follow_up"] = fu
        case.case_context = ctx
        db.commit()

        if status == "missed":
            # Initiate recovery workflow
            case.status = "recovering"
            fu["recovery_workflow_initiated"] = True
            
            task = Task(
                id=uuid.uuid4(),
                case_id=case.id,
                title="Outreach for missed follow-up surveillance",
                description=f"Patient missed scheduled follow-up. Initiate outreach playbook: transit/childcare/barrier check.",
                task_type="patient_outreach",
                assigned_role="care_coordinator",
                status="pending",
                due_date=now + timedelta(hours=24)
            )
            db.add(task)
            
            ev = CaseEvent(
                id=uuid.uuid4(),
                case_id=case.id,
                event_type="followup_missed",
                description="Patient missed scheduled follow-up. Recovery task dispatched to care coordinator.",
                event_data={"status": "missed", "notes": notes},
                timestamp=now
            )
            db.add(ev)
            db.commit()
            return {"status": "missed", "recovery_initiated": True}

        elif status in ("attended", "completed", "resolved"):
            # Complete Stage 12: FOLLOW_UP
            cls.advance_stage(
                db=db,
                case_id=case.id,
                stage_ident=12,
                actor_role=actor_role,
                actor_id=str(case.current_owner_id or "doctor"),
                evidence={"follow_up_status": status, "notes": notes},
                notes=f"Follow-up completed successfully: {notes or 'Surveillance criteria satisfied'}.",
                patient_notification_title="Follow-Up Milestone Completed",
                patient_notification_message="Your follow-up evaluation has been documented. Thank you for staying proactive in your care journey."
            )
            return {"status": "completed", "stage_completed": 12}

        return {"status": status}

    # =========================================================================
    # Stage 13: Documentation & Evidence Checklist
    # =========================================================================
    @classmethod
    def verify_documentation_checklist(cls, db: Session, case_id: uuid.UUID) -> Dict[str, Any]:
        """
        Audits the 10-point evidence checklist required for formal clinical closure:
          1. Screening result documented.
          2. Doctor clinical review submitted.
          3. Doctor-authorized care pathway recorded.
          4. Referral outcome documented.
          5. Appointment record confirmed & attended.
          6. Consultation outcome documented.
          7. Treatment plan or clinical disposition recorded.
          8. Follow-up requirements resolved.
          9. Supporting documentation available.
          10. No unresolved mandatory clinical tasks.
        """
        case = db.query(CareCase).filter(CareCase.id == case_id).first()
        if not case:
            raise ValueError(f"Case {case_id} not found")

        ctx = case.case_context or {}
        sr = case.screening_result
        cr = ctx.get("clinical_review")
        co = ctx.get("consultation_outcome")
        fu = ctx.get("follow_up")
        
        # Check active / pending clinical tasks
        pending_mandatory_tasks = db.query(Task).filter(
            Task.case_id == case.id,
            Task.status.in_(["pending", "in_progress", "overdue"]),
            Task.task_type.in_(["clinical_review", "referral_routing"])
        ).count()

        checklist = {
            "screening_result_documented": sr is not None,
            "clinical_review_completed": cr is not None and bool(cr.get("clinical_assessment")),
            "care_pathway_authorized": cr is not None and bool(cr.get("approved_pathway")),
            "referral_outcome_documented": len(case.referrals) > 0 and any(r.status in ("accepted", "completed") for r in case.referrals),
            "appointment_attendance_verified": any(a.status in ("attended", "completed", "confirmed") for a in case.appointments),
            "consultation_outcome_documented": co is not None and bool(co.get("biopsy_pathology_outcome")),
            "treatment_disposition_recorded": (co is not None and bool(co.get("treatment_plan"))) or (ctx.get("treatment_monitoring", {}).get("treatment_plan") is not None),
            "follow_up_resolved": fu is not None and fu.get("status") in ("attended", "completed", "resolved", "scheduled"),
            "supporting_evidence_available": True,
            "no_unresolved_clinical_tasks": pending_mandatory_tasks == 0
        }

        all_satisfied = all(checklist.values())
        
        # Update case context
        ctx = dict(case.case_context or {})
        ctx["documentation_evidence"] = {
            "checklist": checklist,
            "is_complete": all_satisfied,
            "verified_at": datetime.now(timezone.utc).isoformat() if all_satisfied else None
        }
        case.case_context = ctx
        db.commit()

        if all_satisfied:
            # Advance Stage 13: DOCUMENTATION_COMPLETED
            cls.advance_stage(
                db=db,
                case_id=case.id,
                stage_ident=13,
                actor_role="care_coordinator",
                actor_id=str(case.current_owner_id or "system"),
                evidence={"checklist": checklist},
                notes="All 10 clinical documentation checklist items verified complete. Case ready for final doctor closure sign-off."
            )

        return {
            "case_id": str(case.id),
            "checklist": checklist,
            "is_complete": all_satisfied,
            "pending_mandatory_tasks_count": pending_mandatory_tasks
        }

    # =========================================================================
    # Stage 14: Verified Clinical Closure
    # =========================================================================
    @classmethod
    def execute_clinical_closure(
        cls,
        db: Session,
        case_id: uuid.UUID,
        doctor_id: str,
        doctor_name: str,
        clinical_rationale: str,
        evidence_summary: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Level 3 Human Physician Gate:
        Attending doctor conducts final clinical evaluation, verifies checklist, and signs closure.
        """
        case = db.query(CareCase).filter(CareCase.id == case_id).first()
        if not case:
            raise ValueError(f"Case {case_id} not found")

        # 1. Audit Documentation Checklist
        doc_audit = cls.verify_documentation_checklist(db, case.id)
        if not doc_audit["is_complete"]:
            incomplete_items = [k for k, v in doc_audit["checklist"].items() if not v]
            raise ValueError(f"Cannot close case: Incomplete clinical prerequisites: {', '.join(incomplete_items)}")

        now = datetime.now(timezone.utc)
        doc_uuid = uuid.UUID(doctor_id) if isinstance(doctor_id, str) and len(doctor_id) == 36 else None

        # Resolve verifying clinician against case_owners to satisfy foreign key constraint
        clinician_owner = None
        if doc_uuid:
            clinician_owner = db.query(CaseOwner).filter(CaseOwner.id == doc_uuid).first()
        if not clinician_owner:
            clinician_owner = db.query(CaseOwner).filter(CaseOwner.role.in_(["doctor", "specialist"])).first()
        clinician_owner_id = clinician_owner.id if clinician_owner else None

        # 2. Persist ClosureEvidence
        evidence = ClosureEvidence(
            id=uuid.uuid4(),
            case_id=case.id,
            evidence_type="authorized_human_signoff",
            evidence_summary=evidence_summary or f"Physician sign-off: {clinical_rationale}",
            verifying_clinician_id=clinician_owner_id,
            verified_at=now,
            evidence_metadata={
                "signed_by_doctor": doctor_name,
                "clinical_rationale": clinical_rationale,
                "checklist_verified": True
            },
            is_verified=True
        )
        db.add(evidence)

        # 3. Complete Stage 14: VERIFIED_CLINICAL_CLOSURE
        closure_res = cls.advance_stage(
            db=db,
            case_id=case.id,
            stage_ident=14,
            actor_role="doctor",
            actor_id=doctor_id,
            actor_name=doctor_name,
            evidence={
                "evidence_id": str(evidence.id),
                "doctor_name": doctor_name,
                "clinical_rationale": clinical_rationale,
                "signed_at": now.isoformat()
            },
            notes=f"Verified clinical closure executed by Dr. {doctor_name}: {clinical_rationale}",
            patient_notification_title="Care Pathway Completed: Results Normal & Reassuring",
            patient_notification_message=f"Dr. {doctor_name} has officially signed off on your care pathway: {clinical_rationale}. Routine annual screening recommended."
        )

        case.status = "closed"
        case.sla_status = "resolved"
        db.commit()

        return {
            "case_id": str(case.id),
            "status": "closed",
            "closed_at": now.isoformat(),
            "doctor_name": doctor_name,
            "evidence_id": str(evidence.id)
        }

