"""
CareBridge Deterministic Clinical & Operational Rules
Hard boundaries, SLA calculations, pathway mapping, and closure criteria.
All rules are deterministic Python functions — AI does NOT alter clinical safety boundaries.
"""

from datetime import datetime, timezone, timedelta
from typing import Tuple, List, Optional, Dict, Any
from app.workflows.state import ClosureChecklist


def _ensure_utc(dt: Optional[datetime]) -> datetime:
    """Ensures a datetime object is UTC-aware across SQLite and PostgreSQL."""
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def calculate_sla_deadline(urgency: str, start_time: Optional[datetime] = None) -> datetime:
    """
    Calculates deterministic SLA deadline based on clinical urgency:
    - critical: 48 hours
    - urgent: 7 days
    - standard: 14 days
    """
    base_time = _ensure_utc(start_time)
    urgency_lower = (urgency or "standard").lower()

    if urgency_lower == "critical":
        return base_time + timedelta(hours=48)
    elif urgency_lower == "urgent":
        return base_time + timedelta(days=7)
    else:
        return base_time + timedelta(days=14)


def evaluate_sla_status(deadline: datetime, now: Optional[datetime] = None) -> str:
    """
    Evaluates SLA progress deterministically:
    - 'breached' if now > deadline
    - 'warning' if within 3 days (or 12h for critical) of deadline
    - 'normal' otherwise
    """
    current_time = _ensure_utc(now)
    utc_deadline = _ensure_utc(deadline)

    if current_time >= utc_deadline:
        return "breached"
    elif (utc_deadline - current_time) <= timedelta(days=3):
        return "warning"
    return "normal"


def match_clinical_pathway(screening_type: str, finding_code: str, summary: str = "") -> str:
    """
    Deterministically matches screening modalities to authorized clinical pathways.
    AI must never invent clinical pathways.
    """
    st_lower = (screening_type or "").lower()
    fc_upper = (finding_code or "").upper().replace(" ", "").replace("_", "-")
    summary_lower = (summary or "").lower()

    # Mammography pathways
    if "mammo" in st_lower or "breast" in st_lower:
        if "BI-RADS-5" in fc_upper or "BIRADS-5" in fc_upper or "5" in fc_upper:
            return "mammogram_abnormal_bi_rads_5_urgent"
        elif "BI-RADS-4" in fc_upper or "BIRADS-4" in fc_upper or "4" in fc_upper:
            return "mammogram_abnormal_bi_rads_4"
        return "mammogram_general_diagnostic_workup"

    # Cervical pathways
    if "cervic" in st_lower or "pap" in st_lower or "hpv" in st_lower:
        if "HPV-16" in fc_upper or "HPV-18" in fc_upper or "CIN-3" in fc_upper or "HSIL" in fc_upper:
            return "cervical_high_risk_colposcopy_urgent"
        return "cervical_abnormal_colposcopy"

    # Colorectal pathways
    if "color" in st_lower or "fit" in st_lower or "colon" in st_lower:
        if "HIGH" in fc_upper or "POSITIVE" in fc_upper:
            return "colorectal_fit_positive_colonoscopy"
        return "colorectal_diagnostic_colonoscopy"

    # Default general screening diagnostic workup
    return "general_diagnostic_workup"


def evaluate_dropoff_rules(
    patient_acknowledged: bool,
    outreach_sent_at: Optional[datetime],
    appointment_status: Optional[str],
    scheduled_appointment_time: Optional[datetime],
    sla_status: str,
    days_inactive: float,
    inferred_barriers: Optional[List[Dict[str, Any]]] = None,
    now: Optional[datetime] = None
) -> Tuple[bool, List[str]]:
    """
    Deterministic rule engine for flagging patient drop-off risks.
    """
    current_time = _ensure_utc(now)
    reasons: List[str] = []

    # Rule 1: Patient has not acknowledged after outreach (>24h for urgent/critical, >48h standard)
    if not patient_acknowledged and outreach_sent_at:
        outreach_utc = _ensure_utc(outreach_sent_at)
        hours_unacknowledged = (current_time - outreach_utc).total_seconds() / 3600.0
        if hours_unacknowledged >= 24.0:
            reasons.append(f"unacknowledged_after_{int(hours_unacknowledged)}_hours")

    # Rule 2: Missed appointment / No-show
    if appointment_status == "no_show":
        reasons.append("appointment_no_show")
    elif appointment_status == "booked" and scheduled_appointment_time:
        app_utc = _ensure_utc(scheduled_appointment_time)
        if current_time > app_utc + timedelta(hours=6):
            reasons.append("appointment_passed_without_recorded_attendance")

    # Rule 3: Cancelled without immediate rescheduling
    if appointment_status == "cancelled":
        reasons.append("appointment_cancelled_unresolved")

    # Rule 4: Prolonged case inactivity (>= 5 days)
    if days_inactive >= 5.0:
        reasons.append(f"case_inactive_{int(days_inactive)}_days")

    # Rule 5: SLA Breach or Warning
    if sla_status in ("breached", "warning"):
        reasons.append(f"sla_status_{sla_status}")

    # Rule 6: Specific unaddressed barriers extracted from conversation
    if inferred_barriers:
        for b in inferred_barriers:
            if isinstance(b, dict):
                b_type = b.get("barrier_type", "")
            elif isinstance(b, str):
                b_type = b
            else:
                b_type = str(b)
            if b_type:
                reasons.append(f"patient_barrier_{b_type}")

    has_dropoff = len(reasons) > 0
    return has_dropoff, reasons


def determine_recovery_strategy(
    dropoff_reasons: List[str],
    recovery_attempts: int,
    patient_language: str = "en"
) -> str:
    """
    Selects tailored recovery strategy based on deterministic triage.
    """
    reasons_str = " ".join(dropoff_reasons).lower()

    if "transport" in reasons_str:
        return "transportation_assistance_navigation"
    elif "fear" in reasons_str or "anxiety" in reasons_str:
        return "clinical_nurse_empathy_consultation"
    elif "financial" in reasons_str or "cost" in reasons_str:
        return "financial_aid_counseling"
    elif "no_show" in reasons_str or "appointment" in reasons_str:
        return "direct_rescheduling_multi_slot_offer"
    elif "unacknowledged" in reasons_str:
        if recovery_attempts == 0:
            return "gentle_sms_reminder"
        elif recovery_attempts == 1:
            return "phone_call_outreach"
        else:
            return "community_health_worker_dispatch"
    elif "inactive" in reasons_str:
        return "coordinator_direct_outreach"

    return "multichannel_patient_re_engagement"


def evaluate_closure_checklist(
    has_attended_appointment: bool,
    has_closure_evidence: bool,
    is_clinician_signed_off: bool,
    has_pending_tasks: bool,
    has_unresolved_barriers: bool,
    has_coordinator_concurrence: bool
) -> ClosureChecklist:
    """
    Evaluates mandatory 5-point closed-loop care verification checklist.
    AI must never independently approve closure.
    """
    return ClosureChecklist(
        diagnostic_resolution_completed=has_attended_appointment and has_closure_evidence,
        all_tasks_completed=not has_pending_tasks,
        clinical_signoff_verified=is_clinician_signed_off,
        barriers_resolved=not has_unresolved_barriers,
        coordinator_concurrence=has_coordinator_concurrence
    )
