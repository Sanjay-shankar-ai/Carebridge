"""
CareBridge Recovery API (Phase 9)
Provides real backend endpoints for the Care Recovery Queue:
stalled cases, active recovery playbooks, missed appointments, and recovery triggers.
"""

import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.session import get_async_db
from app.models.care_case import CareCase
from app.models.patient import Patient
from app.models.appointment import Appointment
from app.models.event_audit import CaseEvent
from app.agents.recovery.agent import run_care_recovery_agent
from app.core.security import get_current_user, UserPrincipal
from app.schemas.common import ApiResponseEnvelope

router = APIRouter(prefix="/recovery", tags=["Care Recovery"])


@router.get("", response_model=ApiResponseEnvelope[List[Dict[str, Any]]], summary="List Recovery Operations")
async def list_recovery_cases(
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Retrieves all cases currently in the Recovery Queue.
    Restricted to Care Coordinators, Clinicians, and Administrators.
    """
    if current_user.role == "patient":
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Patients do not have access to internal recovery operations."
        )
    stmt = (
        select(CareCase)
        .options(
            selectinload(CareCase.screening_result),
            selectinload(CareCase.current_owner),
            selectinload(CareCase.patient),
            selectinload(CareCase.appointments)
        )
        .where(
            CareCase.status.in_([
                "recovering", "missed_visit", "escalated",
                "UNASSIGNED_ESCALATED", "recovery_exhausted"
            ])
            | (CareCase.sla_status.in_(["warning", "breached"]))
        )
        .order_by(CareCase.updated_at.desc())
    )

    result = await db.execute(stmt)
    cases = result.scalars().all()

    data = []
    now = datetime.now(timezone.utc)
    for c in cases:
        ctx = c.case_context or {}
        attempts = ctx.get("recovery_attempts", 0)
        barriers = ctx.get("inferred_barriers", [])
        last_playbook = ctx.get("last_recovery_playbook") or ctx.get("last_recovery_strategy")

        # Check for missed appointments
        no_show_appts = [a for a in c.appointments if a.status == "no_show"]

        patient_name = f"{c.patient.first_name} {c.patient.last_name}" if c.patient else "Unknown"
        owner_name = c.current_owner.name if c.current_owner else "Unassigned"

        data.append({
            "case_id": str(c.id),
            "case_number": c.case_number,
            "patient_id": str(c.patient_id),
            "patient_name": patient_name,
            "patient_phone": c.patient.phone if c.patient else None,
            "patient_language": c.patient.preferred_language if c.patient else "en",
            "status": c.status,
            "priority": c.priority,
            "current_owner": owner_name,
            "sla_deadline": c.sla_deadline.isoformat(),
            "sla_status": c.sla_status,
            "recovery_attempts": attempts,
            "active_playbook": last_playbook or ("clarification_inquiry" if no_show_appts else "re_engagement"),
            "barriers_detected": barriers,
            "has_no_show": len(no_show_appts) > 0,
            "no_show_count": len(no_show_appts),
            "last_recovery_timestamp": ctx.get("last_recovery_timestamp") or c.updated_at.isoformat()
        })

    return ApiResponseEnvelope.success_response(
        data=data,
        message=f"Retrieved {len(data)} case(s) in recovery queue"
    )


@router.post("/trigger/{case_id}", summary="Trigger Recovery Agent on Case")
async def trigger_recovery_play(
    case_id: uuid.UUID,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Manually or autonomously dispatches the Care Recovery Agent on a stalled case."""
    if current_user.role == "patient":
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Patients cannot dispatch recovery playbooks."
        )
    case_stmt = select(CareCase).where(CareCase.id == case_id)
    res = await db.execute(case_stmt)
    care_case = res.scalar_one_or_none()
    if not care_case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    result = run_care_recovery_agent(case_id=str(case_id))

    return ApiResponseEnvelope.success_response(
        data=result,
        message=f"Recovery Agent executed playbook '{result.get('selected_playbook')}'"
    )
