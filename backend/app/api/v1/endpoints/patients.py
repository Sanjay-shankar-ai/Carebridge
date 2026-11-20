import uuid
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.session import get_async_db
from app.models.patient import Patient
from app.memory.patient_memory import get_patient_memory
from app.schemas.common import ApiResponseEnvelope
from app.core.security import get_current_user, filter_minimum_necessary_phi, UserPrincipal

import uuid
import math
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.database.session import get_async_db
from app.models.patient import Patient
from app.models.care_case import CareCase, Task
from app.services.lifecycle_service import LifecycleService
from app.memory.patient_memory import get_patient_memory
from app.schemas.common import ApiResponseEnvelope
from app.core.security import get_current_user, filter_minimum_necessary_phi, UserPrincipal

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.get("/coordinator", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Coordinator Patients Management List (14 Stages)")
async def list_coordinator_patients(
    q: Optional[str] = Query(None, description="Search by name, MRN, phone, case number"),
    stage: Optional[int] = Query(None, description="Filter by stage number (1-14)"),
    needs_my_action: Optional[bool] = Query(None, description="Filter by tasks requiring care coordinator action"),
    overdue_sla: Optional[bool] = Query(None, description="Filter by SLA warning or breach"),
    unassigned: Optional[bool] = Query(None, description="Filter by unassigned doctor/owner"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=50, description="Items per page"),
    sort_by: str = Query("last_updated", description="Sort field: 'last_updated', 'name', 'stage', 'sla'"),
    sort_order: str = Query("desc", description="Sort direction: 'asc', 'desc'"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Role-authorized endpoint for Care Coordinators and Physicians to monitor
    every patient's longitudinal journey across all 14 stages.
    """
    user_role = current_user.role.lower()
    if user_role not in ("care_coordinator", "coordinator", "doctor", "clinician", "specialist", "system"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Patients management area is restricted to authorized Care Coordinators and Physicians."
        )

    stmt = (
        select(Patient)
        .options(
            selectinload(Patient.care_cases).selectinload(CareCase.current_owner),
            selectinload(Patient.care_cases).selectinload(CareCase.screening_result),
            selectinload(Patient.care_cases).selectinload(CareCase.appointments),
            selectinload(Patient.care_cases).selectinload(CareCase.referrals),
        )
    )
    res = await db.execute(stmt)
    patients = res.scalars().all()

    items: List[Dict[str, Any]] = []

    for p in patients:
        active_case: Optional[CareCase] = None
        if p.care_cases:
            # Sort cases by updated_at desc to find active case
            sorted_cases = sorted(
                p.care_cases,
                key=lambda c: c.updated_at or c.created_at,
                reverse=True
            )
            active_case = sorted_cases[0]

        if active_case:
            curr_stage = LifecycleService.get_current_stage(active_case)
            curr_stage_num = curr_stage.get("stage_number", 1)
            stage_title = curr_stage.get("title", f"Stage {curr_stage_num}")
            resp_role = curr_stage.get("responsible_role", "care_coordinator")
            allowed_act = curr_stage.get("allowed_action", "Review Requirements")
            
            assigned_doc = "Unassigned"
            if active_case.current_owner and active_case.current_owner.role in ("doctor", "clinician", "specialist"):
                assigned_doc = active_case.current_owner.name

            sla_status = active_case.sla_status or "normal"
            sla_deadline = active_case.sla_deadline.isoformat() if active_case.sla_deadline else None
            needs_action = (resp_role == "care_coordinator" and active_case.status not in ("closed", "care_completed"))
            case_id = str(active_case.id)
            case_number = active_case.case_number
            case_status = active_case.status
            last_updated = (active_case.updated_at or active_case.created_at).isoformat()
        else:
            curr_stage_num = 1
            stage_title = "Stage 1: Screening Order"
            resp_role = "care_coordinator"
            allowed_act = "Create Screening Order"
            assigned_doc = "Unassigned"
            sla_status = "normal"
            sla_deadline = None
            needs_action = True
            case_id = ""
            case_number = "N/A"
            case_status = "intake"
            last_updated = p.created_at.isoformat()

        items.append({
            "patient_id": str(p.id),
            "name": f"{p.first_name} {p.last_name}",
            "mrn": p.mrn,
            "phone": p.phone,
            "case_id": case_id,
            "case_number": case_number,
            "current_stage_number": curr_stage_num,
            "current_stage_title": stage_title,
            "status": case_status,
            "pending_action": allowed_act,
            "responsible_role": resp_role,
            "assigned_doctor": assigned_doc,
            "sla_status": sla_status,
            "sla_deadline": sla_deadline,
            "needs_coordinator_action": needs_action,
            "last_updated": last_updated
        })

    # Search filter
    if q and q.strip():
        term = q.lower().strip()
        items = [
            it for it in items
            if term in it["name"].lower()
            or term in it["mrn"].lower()
            or term in it["case_number"].lower()
            or term in (it["phone"] or "").lower()
        ]

    # Stage filter
    if stage is not None:
        items = [it for it in items if it["current_stage_number"] == stage]

    # Needs my action filter
    if needs_my_action:
        items = [it for it in items if it["needs_coordinator_action"] is True]

    # Overdue SLA filter
    if overdue_sla:
        items = [
            it for it in items
            if it["sla_status"] in ("warning", "breached")
            or it["status"] in ("missed_visit", "recovering", "recovery_active")
        ]

    # Unassigned doctor filter
    if unassigned:
        items = [it for it in items if it["assigned_doctor"] == "Unassigned"]

    # Sorting
    reverse = (sort_order.lower() == "desc")
    if sort_by == "name":
        items.sort(key=lambda x: x["name"].lower(), reverse=reverse)
    elif sort_by == "stage":
        items.sort(key=lambda x: x["current_stage_number"], reverse=reverse)
    elif sort_by == "sla":
        sla_weight = {"breached": 3, "warning": 2, "normal": 1}
        items.sort(key=lambda x: sla_weight.get(x["sla_status"], 0), reverse=reverse)
    else:
        items.sort(key=lambda x: x["last_updated"], reverse=reverse)

    # Pagination
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    paged_items = items[start:end]
    total_pages = max(1, math.ceil(total / page_size))

    return ApiResponseEnvelope(
        success=True,
        message=f"Retrieved {len(paged_items)} coordinator patient cases (Total: {total})",
        data={
            "items": paged_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        }
    )


@router.get("/coordinator/tasks", response_model=ApiResponseEnvelope[List[Dict[str, Any]]], summary="Coordinator My Tasks Tab")
async def list_coordinator_tasks(
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Returns only tasks assigned to the Care Coordinator role across active patient cases.
    Each item contains one-click navigational pointers to patient and stage.
    """
    user_role = current_user.role.lower()
    if user_role not in ("care_coordinator", "coordinator", "doctor", "clinician", "system"):
        raise HTTPException(status_code=403, detail="Forbidden")

    tasks_stmt = (
        select(Task)
        .options(selectinload(Task.care_case).selectinload(CareCase.patient))
        .where(
            Task.assigned_role.in_(["care_coordinator", "coordinator"]),
            Task.status.in_(["pending", "in_progress", "overdue"])
        )
        .order_by(Task.created_at.desc())
        .limit(50)
    )
    t_res = await db.execute(tasks_stmt)
    tasks = t_res.scalars().all()

    data = []
    for t in tasks:
        p_name = "Patient"
        p_id = ""
        stage_num = 1
        stage_title = "Screening"
        sla = "normal"
        if t.care_case:
            stage_info = LifecycleService.get_current_stage(t.care_case)
            stage_num = stage_info.get("stage_number", 1)
            stage_title = stage_info.get("title", f"Stage {stage_num}")
            sla = t.care_case.sla_status or "normal"
            if t.care_case.patient:
                p_name = f"{t.care_case.patient.first_name} {t.care_case.patient.last_name}"
                p_id = str(t.care_case.patient.id)

        data.append({
            "task_id": str(t.id),
            "case_id": str(t.case_id),
            "patient_id": p_id,
            "patient_name": p_name,
            "stage_number": stage_num,
            "stage_title": stage_title,
            "task_title": t.title,
            "description": t.description,
            "priority": t.priority,
            "status": t.status,
            "sla_status": sla,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "created_at": t.created_at.isoformat()
        })

    return ApiResponseEnvelope(
        success=True,
        message=f"Retrieved {len(data)} pending coordinator tasks",
        data=data
    )


@router.get("", response_model=ApiResponseEnvelope[List[Dict[str, Any]]], summary="List Patients")
async def list_patients(
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Retrieves patient demographic records and communication preferences, enforcing minimum necessary PHI."""
    stmt = select(Patient)
    result = await db.execute(stmt)
    patients = result.scalars().all()

    data = [
        filter_minimum_necessary_phi({
            "id": str(p.id),
            "mrn": p.mrn,
            "name": f"{p.first_name} {p.last_name}",
            "phone": p.phone,
            "email": p.email,
            "preferred_language": p.preferred_language,
            "communication_channel": p.communication_channel,
            "accessibility_requirements": p.accessibility_requirements,
            "known_barriers": (p.patient_context or {}).get("known_barriers", []),
            "created_at": p.created_at.isoformat(),
        }, current_user.role)
        for p in patients
    ]

    return ApiResponseEnvelope(
        success=True,
        message=f"Retrieved {len(data)} patients",
        data=data
    )


@router.get("/{patient_id}/memory", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Get Patient Memory")
async def get_patient_memory_endpoint(
    patient_id: uuid.UUID,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Retrieves factual patient memory: language, accessibility, social determinants."""
    mem = await get_patient_memory(patient_id, db)
    if not mem:
        raise HTTPException(status_code=404, detail="Patient not found")

    return ApiResponseEnvelope(
        success=True,
        data=mem.model_dump()
    )
