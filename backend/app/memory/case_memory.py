"""
Case Memory Layer
Longitudinal state tracker for the care case: findings, SLAs, referrals, appointments, and closure status.
"""

import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload, Session
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.care_case import CareCase, Task
from app.models.screening import ScreeningResult
from app.models.owner import CaseOwner
from app.models.referral import Referral
from app.models.appointment import Appointment
from app.models.closure import ClosureEvidence
from app.memory.schemas import (
    CaseMemoryContext,
    ReferralSummary,
    AppointmentSummary,
    TaskSummary,
)


def _build_case_memory(care_case: CareCase) -> CaseMemoryContext:
    screening = care_case.screening_result
    ctx = care_case.case_context or {}
    
    # Map referrals
    referral_summaries = [
        ReferralSummary(
            id=r.id,
            target_facility=r.target_facility,
            specialty=r.specialty,
            status=r.status,
            acceptance_deadline=r.acceptance_deadline,
            rejection_reason=r.rejection_reason
        )
        for r in (care_case.referrals or [])
    ]
    active_ref = next((r for r in referral_summaries if r.status in ["sent", "accepted"]), None)

    # Map appointments
    appt_summaries = [
        AppointmentSummary(
            id=a.id,
            facility=a.facility,
            provider_name=a.provider_name,
            appointment_type=a.appointment_type,
            scheduled_time=a.scheduled_time,
            status=a.status,
            notes=a.notes
        )
        for a in (care_case.appointments or [])
    ]
    upcoming_appt = next((a for a in appt_summaries if a.status in ["booked", "confirmed"]), None)

    # Map tasks
    task_summaries = [
        TaskSummary(
            id=t.id,
            title=t.title,
            assigned_role=t.assigned_role,
            status=t.status,
            due_date=t.due_date
        )
        for t in (care_case.tasks or [])
        if t.status in ["pending", "in_progress", "overdue"]
    ]

    # Map closure evidences
    closure_list = [
        {
            "id": str(e.id),
            "type": e.evidence_type,
            "summary": e.evidence_summary,
            "verified": e.is_verified,
            "verified_at": e.verified_at.isoformat() if e.verified_at else None
        }
        for e in (care_case.closure_evidences or [])
    ]
    is_closed = care_case.status == "closed" or any(e["verified"] for e in closure_list)

    return CaseMemoryContext(
        case_id=care_case.id,
        patient_id=care_case.patient_id,
        case_number=care_case.case_number,
        status=care_case.status,
        priority=care_case.priority,
        clinical_pathway=care_case.clinical_pathway,
        current_owner_name=care_case.current_owner.name if care_case.current_owner else None,
        current_owner_role=care_case.current_owner.role if care_case.current_owner else None,
        screening_type=screening.screening_type if screening else "Unknown",
        finding_code=screening.finding_code if screening else "Unknown",
        finding_summary=screening.finding_summary if screening else "No summary",
        urgency_level=screening.urgency_level if screening else "standard",
        sla_start_time=care_case.sla_start_time,
        sla_deadline=care_case.sla_deadline,
        sla_status=care_case.sla_status,
        inferred_barriers=ctx.get("inferred_barriers", []),
        recovery_attempts=ctx.get("recovery_attempts", 0),
        last_recovery_strategy=ctx.get("last_recovery_strategy"),
        patient_understanding_confirmed=ctx.get("patient_understanding_confirmed", False),
        active_referral=active_ref,
        all_referrals=referral_summaries,
        upcoming_appointment=upcoming_appt,
        appointment_history=appt_summaries,
        pending_tasks=task_summaries,
        is_closed=is_closed,
        closure_evidences=closure_list,
        lifecycle_stages=ctx.get("lifecycle_stages", []),
        current_stage_number=ctx.get("current_stage_number", 1),
        current_stage_id=ctx.get("current_stage_id", "SCREENING"),
        clinical_review=ctx.get("clinical_review"),
        consultation_outcome=ctx.get("consultation_outcome"),
        treatment_monitoring=ctx.get("treatment_monitoring"),
        follow_up=ctx.get("follow_up"),
        documentation_evidence=ctx.get("documentation_evidence")
    )


async def get_case_memory(
    case_id: uuid.UUID,
    db: AsyncSession
) -> Optional[CaseMemoryContext]:
    """Asynchronously loads the complete relational case memory."""
    stmt = (
        select(CareCase)
        .where(CareCase.id == case_id)
        .options(
            selectinload(CareCase.screening_result),
            selectinload(CareCase.current_owner),
            selectinload(CareCase.referrals),
            selectinload(CareCase.appointments),
            selectinload(CareCase.tasks),
            selectinload(CareCase.closure_evidences),
        )
    )
    res = await db.execute(stmt)
    care_case = res.scalar_one_or_none()
    if not care_case:
        return None
    return _build_case_memory(care_case)


def get_case_memory_sync(
    case_id: uuid.UUID,
    db: Session
) -> Optional[CaseMemoryContext]:
    """Synchronous retrieval of complete case memory."""
    care_case = db.query(CareCase).filter(CareCase.id == case_id).first()
    if not care_case:
        return None
    return _build_case_memory(care_case)
