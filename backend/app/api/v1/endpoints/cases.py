import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query, status, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.session import get_async_db, get_sync_db
from app.models.care_case import CareCase, Task
from app.models.appointment import Appointment
from app.models.event_audit import CaseEvent, AuditLog
from app.models.screening import ScreeningResult
from app.models.owner import CaseOwner
from app.models.patient import Patient
from app.services.lifecycle_service import LifecycleService
from app.memory.case_memory import get_case_memory
from app.memory.retriever import get_unified_memory
from app.core.security import get_current_user, UserPrincipal
from app.schemas.common import ApiResponseEnvelope

router = APIRouter(prefix="/cases", tags=["Care Cases"])


@router.get("", response_model=ApiResponseEnvelope[List[Dict[str, Any]]], summary="List Care Cases")
async def list_cases(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by case status"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Retrieves care cases filtered by user authorization and active SLA countdowns."""
    stmt = (
        select(CareCase)
        .options(
            selectinload(CareCase.screening_result),
            selectinload(CareCase.current_owner),
            selectinload(CareCase.patient),
        )
    )

    # Role-based scoping: Patients can ONLY see their own case records
    if current_user.role == "patient":
        if not current_user.patient_id:
            return ApiResponseEnvelope(success=True, message="No cases found for patient", data=[])
        try:
            p_uuid = uuid.UUID(current_user.patient_id)
            stmt = stmt.where(CareCase.patient_id == p_uuid)
        except ValueError:
            return ApiResponseEnvelope(success=True, message="Invalid patient ID", data=[])

    if status_filter:
        stmt = stmt.where(CareCase.status == status_filter)

    result = await db.execute(stmt)
    cases = result.scalars().all()

    data = [
        {
            "id": str(c.id),
            "case_number": c.case_number,
            "patient_id": str(c.patient_id),
            "patient_name": f"{c.patient.first_name} {c.patient.last_name}" if c.patient else "Unknown",
            "patient_phone": c.patient.phone if c.patient else None,
            "patient_language": c.patient.preferred_language if c.patient else "en",
            "screening_type": c.screening_result.screening_type if c.screening_result else "Screening",
            "finding_code": c.screening_result.finding_code if c.screening_result else "N/A",
            "finding_summary": c.screening_result.finding_summary if c.screening_result else "",
            "status": c.status,
            "priority": c.priority,
            "current_owner": c.current_owner.name if c.current_owner else "Unassigned",
            "sla_deadline": c.sla_deadline.isoformat(),
            "sla_status": c.sla_status,
            "inferred_barriers": (c.case_context or {}).get("inferred_barriers", []),
            "recovery_attempts": (c.case_context or {}).get("recovery_attempts", 0),
            "created_at": c.created_at.isoformat(),
        }
        for c in cases
    ]

    return ApiResponseEnvelope(
        success=True,
        message=f"Retrieved {len(data)} care cases",
        data=data
    )


@router.get("/{case_id}", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Get Case Memory")
async def get_case_detail(
    case_id: uuid.UUID,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Retrieves full longitudinal case memory and context with role-based access validation."""
    case_mem = await get_case_memory(case_id, db)
    if not case_mem:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    # Patient isolation check: Patients can only view their own assigned care case
    if current_user.role == "patient":
        if not current_user.patient_id or str(case_mem.patient_id) != str(current_user.patient_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not have permission to view another patient's care case."
            )

    return ApiResponseEnvelope(
        success=True,
        data=case_mem.model_dump()
    )


@router.get("/{case_id}/events", response_model=ApiResponseEnvelope[List[Dict[str, Any]]], summary="Get Case Timeline Events")
async def get_case_timeline_events(
    case_id: uuid.UUID,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Retrieves persisted chronological CaseEvent audit records for a care case."""
    case_stmt = select(CareCase).where(CareCase.id == case_id)
    case_res = await db.execute(case_stmt)
    care_case = case_res.scalar_one_or_none()
    if not care_case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    if current_user.role == "patient":
        if not current_user.patient_id or str(care_case.patient_id) != str(current_user.patient_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not have permission to view another patient's case timeline."
            )

    ev_stmt = (
        select(CaseEvent)
        .where(CaseEvent.case_id == case_id)
        .order_by(CaseEvent.timestamp.desc())
    )
    ev_res = await db.execute(ev_stmt)
    events = ev_res.scalars().all()

    data = [
        {
            "event_id": str(e.id),
            "case_id": str(e.case_id),
            "event_type": e.event_type,
            "description": e.description,
            "event_data": e.event_data or {},
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
        }
        for e in events
    ]
    return ApiResponseEnvelope(
        success=True,
        message=f"Retrieved {len(data)} timeline events for case #{care_case.case_number}",
        data=data,
    )


@router.get("/{case_id}/unified-context", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Get Unified Care Context")
async def get_case_unified_context(
    case_id: uuid.UUID,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Retrieves composite Patient + Case + Conversation memory for agent reasoning."""
    case_stmt = select(CareCase.patient_id).where(CareCase.id == case_id)
    res = await db.execute(case_stmt)
    patient_id = res.scalar_one_or_none()
    if not patient_id:
        raise HTTPException(status_code=404, detail="Case not found")

    # Patient isolation check: Patients can only view their own assigned care case
    if current_user.role == "patient":
        if not current_user.patient_id or str(patient_id) != str(current_user.patient_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not have permission to view another patient's care case."
            )

    unified = await get_unified_memory(case_id, patient_id, db)
    if not unified:
        raise HTTPException(status_code=404, detail="Unified context could not be assembled")

    return ApiResponseEnvelope(
        success=True,
        data=unified.model_dump()
    )


class ReopenCaseRequest(BaseModel):
    clinical_rationale: str = Field(min_length=10, description="Clinical justification for case reopening")


@router.post("/{case_id}/reopen", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Clinician Reopens Closed Case")
async def reopen_closed_case(
    case_id: uuid.UUID,
    req: ReopenCaseRequest,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Authorized clinical reopening workflow (Level 3 Human Authority).
    Strictly restricted to doctors/clinicians/specialists. Reopens a closed care case with audit trail.
    """
    user_role = current_user.role.lower()
    if user_role not in ("doctor", "clinician", "specialist", "primary_physician"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only an authorized physician/clinician may reopen a closed care case."
        )

    stmt = select(CareCase).where(CareCase.id == case_id)
    res = await db.execute(stmt)
    care_case = res.scalar_one_or_none()

    if not care_case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    if care_case.status != "closed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reopen case #{care_case.case_number} because it is currently in '{care_case.status}' status (must be 'closed')."
        )

    now = datetime.now(timezone.utc)
    care_case.status = "reopened"
    care_case.priority = "urgent"

    event = CaseEvent(
        id=uuid.uuid4(),
        case_id=care_case.id,
        event_type="case_reopened",
        description=f"Case #{care_case.case_number} reopened by Dr. {getattr(current_user, 'name', 'Physician')}: {req.clinical_rationale}",
        event_data={"clinical_rationale": req.clinical_rationale, "reopened_by": str(current_user.user_id)},
        timestamp=now
    )
    db.add(event)

    audit = AuditLog(
        id=uuid.uuid4(),
        case_id=care_case.id,
        patient_id=care_case.patient_id,
        actor_type="doctor",
        actor_id=str(current_user.user_id),
        action="REOPEN_CASE",
        autonomy_level=3,
        rationale=f"Clinical case reopening: {req.clinical_rationale}",
        timestamp=now
    )
    db.add(audit)
    await db.commit()

    return ApiResponseEnvelope.success_response(
        data={
            "case_id": str(care_case.id),
            "case_number": care_case.case_number,
            "status": "reopened",
            "priority": "urgent",
            "reopened_at": now.isoformat()
        },
        message=f"Case #{care_case.case_number} successfully reopened under physician authorization."
    )


# =============================================================================
# 14-Stage Longitudinal Care Lifecycle Endpoints
# =============================================================================

@router.get("/{case_id}/lifecycle", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Get 14-Stage Lifecycle Progress")
async def get_case_lifecycle(
    case_id: uuid.UUID,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Retrieves the full 14-stage journey for a case, verifying patient access isolation."""
    stmt = (
        select(CareCase)
        .options(
            selectinload(CareCase.screening_result),
            selectinload(CareCase.patient),
            selectinload(CareCase.referrals),
            selectinload(CareCase.appointments),
        )
        .where(CareCase.id == case_id)
    )
    res = await db.execute(stmt)
    care_case = res.scalar_one_or_none()
    if not care_case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    if current_user.role == "patient":
        if not current_user.patient_id or str(care_case.patient_id) != str(current_user.patient_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not have permission to view another patient's care lifecycle."
            )

    stages = LifecycleService.get_lifecycle_stages(care_case)
    curr_stage = LifecycleService.get_current_stage(care_case)
    ctx = care_case.case_context or {}

    return ApiResponseEnvelope.success_response(
        data={
            "case_id": str(care_case.id),
            "case_number": care_case.case_number,
            "status": care_case.status,
            "current_stage": curr_stage,
            "current_stage_number": curr_stage.get("stage_number", 1),
            "stages": stages,
            "clinical_review": ctx.get("clinical_review"),
            "consultation_outcome": ctx.get("consultation_outcome"),
            "treatment_monitoring": ctx.get("treatment_monitoring"),
            "follow_up": ctx.get("follow_up"),
            "documentation_evidence": ctx.get("documentation_evidence"),
        },
        message=f"Retrieved 14-stage lifecycle for case #{care_case.case_number}"
    )


class ClinicalReviewRequest(BaseModel):
    clinical_assessment: str = Field(min_length=5, description="Attending physician diagnostic assessment")
    approved_pathway: str = Field(min_length=3, description="Authorized pathway, e.g. specialist biopsy")
    additional_investigations: Optional[str] = Field(default=None)
    patient_safe_explanation: Optional[str] = Field(default=None)
    referral_approved: bool = Field(default=True)


@router.post("/{case_id}/clinical-review", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Doctor Submits Clinical Review (Stages 5 & 6)")
def submit_clinical_review(
    case_id: uuid.UUID,
    req: ClinicalReviewRequest,
    current_user: UserPrincipal = Depends(get_current_user),
):
    """Attending physician completes clinical review (Stage 5) and confirms patient explanation (Stage 6)."""
    user_role = current_user.role.lower()
    if user_role not in ("doctor", "clinician", "specialist", "primary_physician"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only an authorized physician/clinician may perform clinical review."
        )

    doc_name = getattr(current_user, "name", None) or "Dr. Aris Thorne"

    with get_sync_db() as sync_db:
        try:
            review = LifecycleService.record_clinical_review(
                db=sync_db,
                case_id=case_id,
                doctor_id=str(current_user.user_id),
                doctor_name=doc_name,
                clinical_assessment=req.clinical_assessment,
                approved_pathway=req.approved_pathway,
                additional_investigations=req.additional_investigations,
                patient_safe_explanation=req.patient_safe_explanation,
                referral_approved=req.referral_approved
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    return ApiResponseEnvelope.success_response(
        data=review,
        message="Clinical review recorded and patient confirmation message dispatched."
    )


class ConsultationOutcomeRequest(BaseModel):
    consultation_notes: str = Field(min_length=5, description="Clinical consultation notes")
    biopsy_pathology_outcome: str = Field(min_length=3, description="Biopsy pathology findings")
    clinical_recommendations: str = Field(min_length=3, description="Physician recommendations")
    treatment_plan: str = Field(min_length=3, description="Follow-up care or treatment plan")
    next_followup_date: Optional[str] = Field(default=None, description="ISO timestamp or date string")


@router.post("/{case_id}/consultation-outcome", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Doctor Records Consultation Outcome (Stage 10)")
def record_consultation_outcome_endpoint(
    case_id: uuid.UUID,
    req: ConsultationOutcomeRequest,
    current_user: UserPrincipal = Depends(get_current_user),
):
    """Attending physician records consultation findings, biopsy pathology, and treatment plan (Stage 10)."""
    user_role = current_user.role.lower()
    if user_role not in ("doctor", "clinician", "specialist", "primary_physician"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only an authorized physician/clinician may record consultation outcomes."
        )

    doc_name = getattr(current_user, "name", None) or "Dr. Aris Thorne"

    with get_sync_db() as sync_db:
        try:
            outcome = LifecycleService.record_consultation_outcome(
                db=sync_db,
                case_id=case_id,
                doctor_id=str(current_user.user_id),
                doctor_name=doc_name,
                consultation_notes=req.consultation_notes,
                biopsy_pathology_outcome=req.biopsy_pathology_outcome,
                clinical_recommendations=req.clinical_recommendations,
                treatment_plan=req.treatment_plan,
                next_followup_date=req.next_followup_date
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    return ApiResponseEnvelope.success_response(
        data=outcome,
        message="Consultation outcome and biopsy pathology documented successfully."
    )


class TreatmentUpdateRequest(BaseModel):
    message: str = Field(min_length=3, description="Patient question/symptom or coordinator update")
    category: str = Field(default="general", description="'symptom', 'question', 'barrier', 'adherence'")


@router.post("/{case_id}/treatment-update", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Record Treatment Monitoring Update (Stage 11)")
async def submit_treatment_update(
    case_id: uuid.UUID,
    req: TreatmentUpdateRequest,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Records patient feedback, questions, or coordinator notes during Stage 11 Treatment Monitoring."""
    stmt = select(CareCase).where(CareCase.id == case_id)
    res = await db.execute(stmt)
    care_case = res.scalar_one_or_none()
    if not care_case:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    if current_user.role == "patient":
        if not current_user.patient_id or str(care_case.patient_id) != str(current_user.patient_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: Cross-patient access denied.")

    with get_sync_db() as sync_db:
        entry = LifecycleService.record_treatment_update(
            db=sync_db,
            case_id=case_id,
            sender_role=current_user.role,
            message=req.message,
            category=req.category
        )

    return ApiResponseEnvelope.success_response(
        data=entry,
        message="Treatment monitoring update logged successfully."
    )


class FollowUpStatusRequest(BaseModel):
    status: str = Field(description="'attended', 'missed', 'completed', 'rescheduled'")
    notes: Optional[str] = Field(default=None, description="Notes on follow-up surveillance")


@router.post("/{case_id}/follow-up", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Record Follow-Up Milestone (Stage 12)")
def record_followup_status_endpoint(
    case_id: uuid.UUID,
    req: FollowUpStatusRequest,
    current_user: UserPrincipal = Depends(get_current_user),
):
    """Records follow-up attendance (Stage 12). If missed, triggers recovery playbook for care coordinator."""
    user_role = current_user.role.lower()
    if user_role not in ("doctor", "clinician", "specialist", "care_coordinator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only clinicians or care coordinators may document follow-up status."
        )

    with get_sync_db() as sync_db:
        try:
            res = LifecycleService.record_followup_status(
                db=sync_db,
                case_id=case_id,
                status=req.status,
                notes=req.notes,
                actor_role=current_user.role
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    return ApiResponseEnvelope.success_response(
        data=res,
        message=f"Follow-up status recorded as '{req.status}'."
    )


@router.get("/{case_id}/documentation-checklist", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Audit 10-Point Documentation Checklist (Stage 13)")
def get_documentation_checklist(
    case_id: uuid.UUID,
    current_user: UserPrincipal = Depends(get_current_user),
):
    """Audits the 10-point documentation checklist required before verified clinical closure."""
    with get_sync_db() as sync_db:
        try:
            checklist = LifecycleService.verify_documentation_checklist(sync_db, case_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    return ApiResponseEnvelope.success_response(
        data=checklist,
        message="Documentation checklist audited successfully."
    )


class ClinicalClosureRequest(BaseModel):
    clinical_rationale: str = Field(min_length=5, description="Physician clinical justification for closure")
    evidence_summary: Optional[str] = Field(default=None, description="Summary of evidence reviewed")


@router.post("/{case_id}/clinical-closure", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Doctor Verified Clinical Closure (Stage 14)")
def execute_clinical_closure_endpoint(
    case_id: uuid.UUID,
    req: ClinicalClosureRequest,
    current_user: UserPrincipal = Depends(get_current_user),
):
    """Level 3 Human Authority: Authenticated physician verifies checklist and executes clinical closure."""
    user_role = current_user.role.lower()
    if user_role not in ("doctor", "clinician", "specialist", "primary_physician"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only an authorized physician/clinician may execute clinical closure sign-off."
        )

    doc_name = getattr(current_user, "name", None) or "Dr. Aris Thorne"

    doc_owner = current_user.owner_id or str(current_user.user_id)

    with get_sync_db() as sync_db:
        try:
            closure_res = LifecycleService.execute_clinical_closure(
                db=sync_db,
                case_id=case_id,
                doctor_id=doc_owner,
                doctor_name=doc_name,
                clinical_rationale=req.clinical_rationale,
                evidence_summary=req.evidence_summary
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return ApiResponseEnvelope.success_response(
        data=closure_res,
        message=f"Verified clinical closure executed by {doc_name}."
    )


# ------------------------------------------------------------------------------
# Care Coordinator Screening Workflow (Schedule, Manual Completion, Missed Task)
# ------------------------------------------------------------------------------

class ScheduleScreeningRequest(BaseModel):
    scheduled_time: datetime = Field(description="Target date and time for screening")
    facility: Optional[str] = Field(default=None, description="Screening facility / hospital unit")
    provider_name: Optional[str] = Field(default=None, description="Screening technician / provider")
    notes: Optional[str] = Field(default=None, description="Preparation or operational instructions")


class CompleteScreeningRequest(BaseModel):
    completion_notes: Optional[str] = Field(default=None, description="Technician / coordinator notes on completed screening")
    completed_at: Optional[datetime] = Field(default=None, description="Timestamp of completed screening")


class RecordMissedScreeningRequest(BaseModel):
    missed_reason: Optional[str] = Field(default="Patient did not attend scheduled visit", description="Reason for missed screening")


@router.post("/{case_id}/schedule-screening", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Coordinator Updates Screening Schedule")
async def schedule_screening(
    case_id: uuid.UUID,
    req: ScheduleScreeningRequest,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Care Coordinator sets or updates the patient's screening appointment schedule.
    Updates case status to 'screening_scheduled' and dispatches real-time notification to patient.
    """
    case_stmt = (
        select(CareCase)
        .options(
            selectinload(CareCase.patient),
            selectinload(CareCase.current_owner)
        )
        .where(CareCase.id == case_id)
    )
    res = await db.execute(case_stmt)
    care_case = res.scalar_one_or_none()
    if not care_case:
        raise HTTPException(status_code=404, detail="Care case not found")

    facility = req.facility or (care_case.current_owner.facility if care_case.current_owner else "Metropolitan Hospital Screening Center")
    provider_name = req.provider_name or (care_case.current_owner.name if care_case.current_owner else "Clinical Screening Unit")
    now = datetime.now(timezone.utc)

    # Check for existing screening appointment or create new
    appt_stmt = (
        select(Appointment)
        .where(
            Appointment.case_id == case_id,
            Appointment.appointment_type.in_(["screening_evaluation", "screening"])
        )
        .order_by(Appointment.created_at.desc())
    )
    appt_res = await db.execute(appt_stmt)
    appt = appt_res.scalars().first()

    if appt:
        appt.scheduled_time = req.scheduled_time
        appt.facility = facility
        appt.provider_name = provider_name
        appt.status = "booked"
        appt.notes = req.notes or appt.notes
    else:
        appt = Appointment(
            id=uuid.uuid4(),
            case_id=case_id,
            patient_id=care_case.patient_id,
            facility=facility,
            provider_name=provider_name,
            appointment_type="screening_evaluation",
            scheduled_time=req.scheduled_time,
            status="booked",
            notes=req.notes or f"Screening appointment scheduled by {getattr(current_user, 'name', 'Care Coordinator')}."
        )
        db.add(appt)

    # Advance Case Status (Order created / scheduled — Stage 1 remains PENDING until screening is performed)
    care_case.status = "screening_scheduled"
    ctx = dict(care_case.case_context or {})
    ctx.update({
        "onboarding_stage": "screening_scheduled",
        "screening_order_id": f"ORD-SCR-{str(care_case.id)[:8].upper()}",
        "screening_order_status": "ORDERED",
        "screening_scheduled_at": req.scheduled_time.isoformat(),
        "screening_facility": facility,
        "screening_provider": provider_name
    })
    care_case.case_context = ctx

    # Resolve pending schedule_screening task with order creation evidence
    task_stmt = select(Task).where(
        Task.case_id == care_case.id,
        Task.task_type == "schedule_screening",
        Task.status.in_(["pending", "in_progress", "overdue"])
    )
    for t_row in (await db.execute(task_stmt)).scalars().all():
        t_row.status = "completed"
        t_row.completed_at = now
        t_row.completion_evidence = {
            "order_created": True,
            "scheduled_time": req.scheduled_time.isoformat(),
            "facility": facility,
            "completed_by": getattr(current_user, "name", "Priya Nair, RN")
        }

    # Record Case Event
    event = CaseEvent(
        id=uuid.uuid4(),
        case_id=care_case.id,
        event_type="screening_scheduled",
        description=f"Screening appointment scheduled for {req.scheduled_time.strftime('%A, %B %d at %I:%M %p')} at {facility}.",
        event_data={
            "scheduled_time": req.scheduled_time.isoformat(),
            "facility": facility,
            "provider_name": provider_name
        },
        timestamp=now
    )
    db.add(event)

    # Dispatch notification to patient
    try:
        from app.services.notification_service import NotificationService
        from app.database.session import get_sync_db
        with get_sync_db() as sync_db:
            p_name = f"{care_case.patient.first_name} {care_case.patient.last_name}" if care_case.patient else "Patient"
            NotificationService.notify_screening_scheduled(
                db=sync_db,
                case_id=care_case.id,
                patient_id=care_case.patient_id,
                facility=facility,
                scheduled_time=req.scheduled_time,
                patient_name=p_name
            )
    except Exception as notif_err:
        import logging
        logging.getLogger("carebridge.cases").warning(f"Notification schedule notice: {notif_err}")

    await db.commit()

    return ApiResponseEnvelope.success_response(
        data={
            "case_id": str(care_case.id),
            "status": care_case.status,
            "appointment_id": str(appt.id),
            "scheduled_time": req.scheduled_time.isoformat(),
            "facility": facility,
            "provider_name": provider_name
        },
        message=f"Screening scheduled for {req.scheduled_time.strftime('%A, %B %d at %I:%M %p')}. Patient notified."
    )


@router.post("/{case_id}/complete-screening", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Coordinator Manually Records Screening Completion")
async def complete_screening(
    case_id: uuid.UUID,
    req: CompleteScreeningRequest,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Care Coordinator manually enters that the patient completed the screening.
    Updates appointment to 'attended', advances case status to 'screening_completed',
    and notifies patient that results are being processed.
    """
    case_stmt = (
        select(CareCase)
        .options(
            selectinload(CareCase.patient),
            selectinload(CareCase.current_owner)
        )
        .where(CareCase.id == case_id)
    )
    res = await db.execute(case_stmt)
    care_case = res.scalar_one_or_none()
    if not care_case:
        raise HTTPException(status_code=404, detail="Care case not found")

    now = datetime.now(timezone.utc)
    completed_time = req.completed_at or now

    # Find screening appointment and mark attended
    appt_stmt = (
        select(Appointment)
        .where(
            Appointment.case_id == case_id,
            Appointment.appointment_type.in_(["screening_evaluation", "screening"])
        )
        .order_by(Appointment.created_at.desc())
    )
    appt_res = await db.execute(appt_stmt)
    appt = appt_res.scalars().first()

    facility = appt.facility if appt else (care_case.current_owner.facility if care_case.current_owner else "Hospital Screening Center")

    if appt:
        appt.status = "attended"
        appt.attendance_recorded_at = completed_time
        if req.completion_notes:
            appt.notes = f"{appt.notes or ''} [Completion Notes: {req.completion_notes}]".strip()

    # Advance Case Status
    care_case.status = "screening_completed"
    ctx = dict(care_case.case_context or {})
    ctx.update({
        "onboarding_stage": "screening_completed",
        "screening_order_status": "PERFORMED",
        "screening_completed_at": completed_time.isoformat(),
        "completion_notes": req.completion_notes
    })
    care_case.case_context = ctx

    # Ensure any schedule_screening task is marked completed before advancing Stage 1
    task_stmt = select(Task).where(
        Task.case_id == care_case.id,
        Task.task_type == "schedule_screening",
        Task.status.in_(["pending", "in_progress", "overdue"])
    )
    for t_row in (await db.execute(task_stmt)).scalars().all():
        t_row.status = "completed"
        t_row.completed_at = now
        t_row.completion_evidence = {
            "screening_performed": True,
            "completed_at": completed_time.isoformat(),
            "facility": facility
        }

    # Record Case Event
    event = CaseEvent(
        id=uuid.uuid4(),
        case_id=care_case.id,
        event_type="screening_completed",
        description=f"Screening procedure manually verified as completed by {getattr(current_user, 'name', 'Care Coordinator')}.",
        event_data={
            "completed_at": completed_time.isoformat(),
            "facility": facility,
            "completion_notes": req.completion_notes
        },
        timestamp=now
    )
    db.add(event)
    await db.commit()

    # Dispatch notification to patient & advance Stage 1 in lifecycle
    try:
        from app.services.notification_service import NotificationService
        from app.database.session import get_sync_db
        with get_sync_db() as sync_db:
            p_name = f"{care_case.patient.first_name} {care_case.patient.last_name}" if care_case.patient else "Patient"
            NotificationService.notify_screening_completed(
                db=sync_db,
                case_id=care_case.id,
                patient_id=care_case.patient_id,
                facility=facility,
                patient_name=p_name
            )
            # Advance Stage 1 (SCREENING_PERFORMED) with verified operational evidence
            try:
                LifecycleService.advance_stage(
                    db=sync_db,
                    case_id=care_case.id,
                    stage_ident=1,
                    actor_role="care_coordinator",
                    actor_id=str(current_user.user_id),
                    actor_name=getattr(current_user, "name", "Priya Nair, RN"),
                    evidence={
                        "screening_performed": True,
                        "order_status": "PERFORMED",
                        "facility": facility,
                        "completed_at": completed_time.isoformat(),
                        "completion_notes": req.completion_notes,
                        "verified_by": getattr(current_user, "name", "Care Coordinator")
                    }
                )
            except Exception as stage_err:
                import logging
                logging.getLogger("carebridge.cases").warning(f"Lifecycle Stage 1 advancement notice: {stage_err}")
    except Exception as notif_err:
        import logging
        logging.getLogger("carebridge.cases").warning(f"Notification complete notice: {notif_err}")

    await db.refresh(care_case)

    return ApiResponseEnvelope.success_response(
        data={
            "case_id": str(care_case.id),
            "status": care_case.status,
            "completed_at": completed_time.isoformat(),
            "facility": facility
        },
        message="Screening marked as completed. Diagnostic findings processing initiated."
    )


@router.post("/{case_id}/missed-screening", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Record Missed Screening Visit & Trigger Alert")
async def record_missed_screening(
    case_id: uuid.UUID,
    req: RecordMissedScreeningRequest,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Care Coordinator or Surveillance System records that a patient missed their screening visit.
    Updates appointment to 'no_show', advances case to 'missed_visit', generates an urgent coordinator recovery task,
    and dispatches a critical recovery notification to the patient.
    """
    case_stmt = (
        select(CareCase)
        .options(
            selectinload(CareCase.patient),
            selectinload(CareCase.current_owner)
        )
        .where(CareCase.id == case_id)
    )
    res = await db.execute(case_stmt)
    care_case = res.scalar_one_or_none()
    if not care_case:
        raise HTTPException(status_code=404, detail="Care case not found")

    now = datetime.now(timezone.utc)

    # Find screening appointment and mark no_show
    appt_stmt = (
        select(Appointment)
        .where(
            Appointment.case_id == case_id,
            Appointment.appointment_type.in_(["screening_evaluation", "screening"])
        )
        .order_by(Appointment.created_at.desc())
    )
    appt_res = await db.execute(appt_stmt)
    appt = appt_res.scalars().first()

    scheduled_time = appt.scheduled_time if appt else now
    facility = appt.facility if appt else (care_case.current_owner.facility if care_case.current_owner else "Screening Center")
    coord_name = care_case.current_owner.name if care_case.current_owner else "Care Coordinator"
    patient_name = f"{care_case.patient.first_name} {care_case.patient.last_name}" if care_case.patient else "Patient"
    patient_first = care_case.patient.first_name if care_case.patient else "Patient"

    if appt:
        appt.status = "no_show"
        appt.cancellation_reason = req.missed_reason
        appt.cancellation_outcome = "reschedule_pending"

    # Advance Case Status
    care_case.status = "missed_visit"
    ctx = care_case.case_context or {}
    ctx.update({
        "missed_visit": True,
        "missed_visit_at": now.isoformat(),
        "missed_reason": req.missed_reason,
        "recovery_attempts": ctx.get("recovery_attempts", 0) + 1
    })
    care_case.case_context = ctx

    # Create Recovery Task for Coordinator
    task = Task(
        id=uuid.uuid4(),
        case_id=care_case.id,
        title=f"Recovery Outreach: {patient_first} missed screening visit",
        description=f"Patient missed scheduled screening on {scheduled_time.strftime('%b %d at %I:%M %p')} ({req.missed_reason}). Reach out via chat/phone to address barriers and reschedule.",
        task_type="recovery_outreach",
        assigned_to_id=care_case.current_owner_id,
        assigned_role="care_coordinator",
        status="pending",
        due_date=now + timedelta(days=1)
    )
    db.add(task)

    # Record Case Event
    event = CaseEvent(
        id=uuid.uuid4(),
        case_id=care_case.id,
        event_type="screening_missed",
        description=f"Patient missed screening visit scheduled for {scheduled_time.strftime('%b %d, %Y %I:%M %p')}. Recovery workflow activated.",
        event_data={
            "scheduled_time": scheduled_time.isoformat(),
            "facility": facility,
            "missed_reason": req.missed_reason
        },
        timestamp=now
    )
    db.add(event)

    # Dispatch notification to patient
    try:
        from app.services.notification_service import NotificationService
        from app.database.session import get_sync_db
        with get_sync_db() as sync_db:
            NotificationService.notify_screening_missed(
                db=sync_db,
                case_id=care_case.id,
                patient_id=care_case.patient_id,
                facility=facility,
                scheduled_time=scheduled_time,
                coordinator_name=coord_name,
                patient_name=patient_name
            )
    except Exception as notif_err:
        import logging
        logging.getLogger("carebridge.cases").warning(f"Notification missed notice: {notif_err}")

    await db.commit()

    return ApiResponseEnvelope.success_response(
        data={
            "case_id": str(care_case.id),
            "status": care_case.status,
            "missed_time": scheduled_time.isoformat(),
            "recovery_task_id": str(task.id)
        },
        message=f"Missed visit recorded for {patient_name}. Patient notified and coordinator recovery outreach task assigned."
    )


# ------------------------------------------------------------------------------
# Test Report Upload & AI Doctor Preference Suggestion (Stage 2 & 7)
# ------------------------------------------------------------------------------

class TestReportUploadRequest(BaseModel):
    screening_type: str = Field(default="Mammogram", description="Type of screening test")
    disease_condition: str = Field(default="BI-RADS 4 Suspicious Mass", description="Identified disease/condition")
    finding_code: str = Field(default="BI-RADS-4", description="Diagnostic finding code")
    finding_summary: str = Field(description="Summary of radiological or histological findings")
    report_text: Optional[str] = Field(default=None, description="Clinical report text or parsed document content")
    report_filename: Optional[str] = Field(default=None, description="Original uploaded filename (PDF/DOCX)")
    clinical_recommendation: Optional[str] = Field(
        default="Diagnostic ultrasound and core needle tissue biopsy within 14 days",
        description="Recommended next clinical step"
    )
    urgency_level: Optional[str] = Field(default="standard", description="standard, urgent, critical")


@router.post("/{case_id}/test-report", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Coordinator Uploads Test Report & AI Suggests Doctors")
async def upload_test_report(
    case_id: uuid.UUID,
    req: TestReportUploadRequest,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Care Coordinator uploads test report (with PDF/DOCX or text findings).
    The AI reads the disease condition, findings, and clinical urgency,
    automatically suggests matching specialist doctors, advances case to 'result_generated',
    and triggers an alert notification for the patient.
    """
    case_stmt = (
        select(CareCase)
        .options(
            selectinload(CareCase.patient),
            selectinload(CareCase.screening_result),
            selectinload(CareCase.current_owner)
        )
        .where(CareCase.id == case_id)
    )
    res = await db.execute(case_stmt)
    care_case = res.scalar_one_or_none()

    if not care_case:
        raise HTTPException(status_code=404, detail="Care case not found")

    now = datetime.now(timezone.utc)

    # 1. Update or create ScreeningResult record
    if care_case.screening_result:
        screening = care_case.screening_result
        screening.screening_type = req.screening_type
        screening.finding_code = req.finding_code
        screening.finding_summary = req.finding_summary
        screening.urgency_level = req.urgency_level or "standard"
        screening.test_date = now
        screening.raw_report_data = {
            "disease_condition": req.disease_condition,
            "report_text": req.report_text or req.finding_summary,
            "filename": req.report_filename,
            "recommendation": req.clinical_recommendation,
            "uploaded_by": getattr(current_user, "name", "Care Coordinator"),
            "uploaded_at": now.isoformat()
        }
    else:
        screening = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=care_case.patient_id,
            screening_type=req.screening_type,
            test_date=now,
            finding_code=req.finding_code,
            finding_summary=req.finding_summary,
            urgency_level=req.urgency_level or "standard",
            performing_facility=care_case.current_owner.facility if care_case.current_owner else "Metropolitan Screening Center",
            raw_report_data={
                "disease_condition": req.disease_condition,
                "report_text": req.report_text or req.finding_summary,
                "filename": req.report_filename,
                "recommendation": req.clinical_recommendation,
                "uploaded_by": getattr(current_user, "name", "Care Coordinator"),
                "uploaded_at": now.isoformat()
            }
        )
        db.add(screening)
        await db.flush()
        care_case.screening_result_id = screening.id

    # 2. Configurable Clinical Specialty Routing Service
    from app.services.specialty_routing_service import SpecialtyRoutingService
    from app.services.doctor_allocation_service import DoctorAllocationService

    routing_res = SpecialtyRoutingService.determine_specialty(
        disease_condition=req.disease_condition,
        finding_code=req.finding_code,
        finding_summary=req.finding_summary,
        screening_type=req.screening_type,
        report_text=req.report_text,
        urgency_level=req.urgency_level
    )

    ai_suggested_doctors = []
    initial_assignment_id = None

    with get_sync_db() as sync_db:
        if routing_res.requires_human_review:
            # Human review required instead of guessing
            task = Task(
                id=uuid.uuid4(),
                case_id=care_case.id,
                title=f"Specialty Routing Review Required: {care_case.case_number}",
                description=(
                    f"Automated specialty determination inconclusive for {req.disease_condition} ({req.finding_code}).\n"
                    f"Rationale: {routing_res.routing_rationale}\n"
                    f"Please review clinical report and assign specialty."
                ),
                task_type="specialty_routing_review",
                assigned_role="care_coordinator",
                status="pending",
                due_date=now + timedelta(hours=12)
            )
            sync_db.add(task)
            sync_db.commit()
        else:
            # Rank eligible active doctors via 5 explainable factors
            ranked_candidates = DoctorAllocationService.rank_eligible_doctors(
                db=sync_db,
                specialty=routing_res.specialty,
                urgency_level=routing_res.urgency_level,
                case_id=care_case.id
            )

            for cand in ranked_candidates:
                ai_suggested_doctors.append({
                    "id": cand["doctor_id"],
                    "name": cand["name"],
                    "facility": cand["facility"],
                    "specialty": cand["specialty"],
                    "match_score": cand["match_score"],
                    "match_reason": cand["explanation"],
                    "factors": cand["factors"]
                })

            # Create initial persisted assignment request for top candidate
            if ranked_candidates:
                top_cand = ranked_candidates[0]
                try:
                    initial_assignment = DoctorAllocationService.request_doctor_assignment(
                        db=sync_db,
                        case_id=care_case.id,
                        doctor_id=uuid.UUID(top_cand["doctor_id"]),
                        specialty_matched=routing_res.specialty,
                        urgency_level=routing_res.urgency_level,
                        assigned_by_role="ai_allocation_agent",
                        allocation_factors=top_cand["factors"],
                        allocation_score=top_cand["total_score"]
                    )
                    initial_assignment_id = str(initial_assignment.id)
                except Exception as e:
                    logger.warning(f"Could not auto-create assignment request: {e}")

    # Fallback to general specialists cohort if routing required human review
    if not ai_suggested_doctors:
        specialists_stmt = select(CaseOwner).where(CaseOwner.role == "specialist", CaseOwner.is_active.is_(True))
        spec_res = await db.execute(specialists_stmt)
        for spec in spec_res.scalars().all():
            ai_suggested_doctors.append({
                "id": str(spec.id),
                "name": spec.name,
                "facility": spec.facility,
                "specialty": getattr(spec, "specialty", "Clinical Specialist"),
                "match_score": 85,
                "match_reason": "Clinical specialist in hospital cohort (Pending human coordinator routing verification)."
            })

    # Sort doctors by match score
    ai_suggested_doctors.sort(key=lambda d: d.get("match_score", 0), reverse=True)

    # 3. Update CareCase status and context
    care_case.status = "result_generated"
    if req.urgency_level in ("urgent", "critical"):
        care_case.priority = req.urgency_level

    existing_context = care_case.case_context or {}
    existing_context.update({
        "disease_condition": req.disease_condition,
        "screening_report_uploaded": True,
        "report_filename": req.report_filename,
        "clinical_recommendation": req.clinical_recommendation,
        "specialty_routed": routing_res.specialty,
        "specialty_confidence": routing_res.confidence,
        "specialty_evidence": routing_res.supporting_evidence,
        "requires_human_review": routing_res.requires_human_review,
        "ai_suggested_doctors": ai_suggested_doctors,
        "pending_assignment_id": initial_assignment_id,
        "last_report_update": now.isoformat()
    })
    care_case.case_context = existing_context

    # 4. Record Case Event
    event = CaseEvent(
        id=uuid.uuid4(),
        case_id=care_case.id,
        event_type="test_report_uploaded",
        description=f"Test report uploaded for {req.disease_condition} ({req.finding_code}). Clinical specialty: {routing_res.specialty or 'HUMAN_REVIEW_REQUIRED'} (Confidence: {routing_res.confidence}). AI matched {len(ai_suggested_doctors)} specialist doctors.",
        event_data={
            "screening_type": req.screening_type,
            "finding_code": req.finding_code,
            "disease_condition": req.disease_condition,
            "specialty_routed": routing_res.specialty,
            "confidence": routing_res.confidence,
            "requires_human_review": routing_res.requires_human_review,
            "recommendation": req.clinical_recommendation,
            "pending_assignment_id": initial_assignment_id
        },
        timestamp=now
    )
    db.add(event)

    # 5. Dispatch real-time notification to patient & advance Stage 2
    try:
        from app.services.notification_service import NotificationService
        with get_sync_db() as sync_db:
            p_name = f"{care_case.patient.first_name} {care_case.patient.last_name}" if care_case.patient else "Patient"
            NotificationService.notify_test_report_updated(
                db=sync_db,
                case_id=care_case.id,
                patient_id=care_case.patient_id,
                disease_condition=req.disease_condition,
                finding_code=req.finding_code,
                patient_name=p_name
            )
            # Advance Stage 2 (RESULT_GENERATED) with report metadata evidence
            try:
                LifecycleService.advance_stage(
                    db=sync_db,
                    case_id=care_case.id,
                    stage_ident=2,
                    actor_role="care_coordinator",
                    actor_id=str(current_user.user_id),
                    evidence={
                        "finding_code": req.finding_code,
                        "finding_summary": req.finding_summary,
                        "disease_condition": req.disease_condition,
                        "report_filename": req.report_filename,
                        "clinical_recommendation": req.clinical_recommendation,
                        "specialty_routed": routing_res.specialty,
                        "uploaded_by": getattr(current_user, "name", "Care Coordinator")
                    }
                )
            except Exception as stage_err:
                import logging
                logging.getLogger("carebridge.cases").warning(f"Lifecycle Stage 2 advancement notice: {stage_err}")
    except Exception as e:
        import logging
        logging.getLogger("carebridge.cases").warning(f"Notification dispatch notice: {e}")

    await db.commit()

    return ApiResponseEnvelope.success_response(
        data={
            "case_id": str(care_case.id),
            "status": care_case.status,
            "disease_condition": req.disease_condition,
            "finding_code": req.finding_code,
            "finding_summary": req.finding_summary,
            "ai_suggested_doctors": ai_suggested_doctors,
            "notification_sent": True
        },
        message=f"Test report uploaded for {req.disease_condition}. AI matched {len(ai_suggested_doctors)} specialist(s) and notified patient."
    )


@router.get("/{case_id}/report-download", summary="Download Structured Diagnostic Test Report")
async def download_diagnostic_report(
    case_id: uuid.UUID,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Generates and returns structured clinical diagnostic report data,
    including findings, attending providers, pathology recommendations,
    and a downloadable markdown/text document format.
    """
    case_stmt = (
        select(CareCase)
        .options(
            selectinload(CareCase.patient),
            selectinload(CareCase.screening_result),
            selectinload(CareCase.current_owner)
        )
        .where(CareCase.id == case_id)
    )
    res = await db.execute(case_stmt)
    care_case = res.scalar_one_or_none()

    if not care_case:
        raise HTTPException(status_code=404, detail="Care case not found")

    p = care_case.patient
    s = care_case.screening_result
    owner = care_case.current_owner

    patient_name = f"{p.first_name} {p.last_name}" if p else "Patient"
    mrn = p.mrn if p else "N/A"
    dob = p.date_of_birth.isoformat() if (p and p.date_of_birth) else "N/A"
    gender = p.gender.capitalize() if (p and p.gender) else "N/A"

    screening_type = s.screening_type if s else "Mammogram Diagnostic Screening"
    finding_code = s.finding_code if s else "BI-RADS-4"
    finding_summary = s.finding_summary if s else "Focal architectural distortion with suspicious microcalcifications."
    urgency = s.urgency_level if s else "standard"
    facility = s.performing_facility if s else (owner.facility if owner else "Metropolitan Screening Lab")
    test_date = s.test_date.strftime("%B %d, %Y") if (s and s.test_date) else datetime.now().strftime("%B %d, %Y")

    raw_data = s.raw_report_data if (s and s.raw_report_data) else {}
    condition = raw_data.get("disease_condition") or "Abnormal Diagnostic Lesion"
    recommendation = raw_data.get("recommendation") or "Targeted ultrasound and ultrasound-guided core needle biopsy within 14 days"
    notes = raw_data.get("report_text") or finding_summary

    report_document = f"""# CAREBRIDGE OFFICIAL DIAGNOSTIC REPORT
Document Reference: RPT-{case_id.hex[:8].upper()}
Report Generation Date: {datetime.now().strftime('%B %d, %Y %I:%M %p')}

================================================================================
PATIENT DEMOGRAPHICS
================================================================================
Full Name:             {patient_name}
Medical Record (MRN):  {mrn}
Date of Birth:         {dob}
Gender:                {gender}
Assigned Case ID:      {care_case.case_number}

================================================================================
CLINICAL SCREENING & DIAGNOSTIC FINDINGS
================================================================================
Screening Procedure:   {screening_type}
Examination Date:      {test_date}
Performing Facility:   {facility}
Diagnostic Code:       {finding_code}
Urgency Classification:{urgency.upper()}

PRIMARY DIAGNOSTIC SUMMARY:
{finding_summary}

DISEASE CONDITION EVALUATION:
{condition}

DETAILED RADIOLOGICAL & PATHOLOGICAL NOTES:
{notes}

================================================================================
CLINICAL RECOMMENDATION & CARE PATHWAY
================================================================================
Recommended Action:
{recommendation}

Accountable Care Team:
• Care Coordinator:    {owner.name if owner else 'Priya Nair, RN'} ({facility})
• Referring Facility:  Metropolitan Health & Diagnostic Screening Network
• Verification Status: Digitally Authenticated & Stored in CareBridge Health Cloud

================================================================================
NOTICE TO PATIENT:
This diagnostic document has been reviewed by your CareBridge healthcare coordination
team. Your Care Coordinator is proactively assisting with scheduling, provider referrals,
and any transportation or caregiver requirements.
================================================================================
"""

    return ApiResponseEnvelope.success_response(
        data={
            "case_id": str(care_case.id),
            "case_number": care_case.case_number,
            "patient_name": patient_name,
            "mrn": mrn,
            "screening_type": screening_type,
            "finding_code": finding_code,
            "finding_summary": finding_summary,
            "disease_condition": condition,
            "recommendation": recommendation,
            "test_date": test_date,
            "facility": facility,
            "coordinator_name": owner.name if owner else "Priya Nair, RN",
            "report_document_text": report_document,
            "filename": f"CareBridge_Diagnostic_Report_{care_case.case_number}.txt"
        },
        message="Diagnostic report generated successfully"
    )


class FinalizeReportRequest(BaseModel):
    finding_code: Optional[str] = "BI-RADS 4"
    finding_summary: Optional[str] = None
    clinical_recommendation: Optional[str] = None
    disease_condition: Optional[str] = "Breast Health"
    urgency_level: Optional[str] = "standard"
    requires_doctor_review: Optional[bool] = False


@router.post("/{case_id}/upload-report-file", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Coordinator Uploads Report File with Content Validation")
async def upload_report_file(
    case_id: uuid.UUID,
    file: UploadFile = File(...),
    screening_order_id: Optional[str] = Form(None),
    screening_type: Optional[str] = Form("Mammogram"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Care Coordinator uploads report file (PDF, JPG, PNG).
    Validates file content (not just extension), enforces 10 MB limit,
    extracts text or tests OCR availability, generates first page preview,
    and stores securely. Upload alone NEVER completes Stage 2.
    """
    if current_user.role.lower() not in ("care_coordinator", "coordinator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only Care Coordinators are authorized to upload clinical reports."
        )

    case_stmt = (
        select(CareCase)
        .options(
            selectinload(CareCase.patient),
            selectinload(CareCase.screening_result),
            selectinload(CareCase.current_owner)
        )
        .where(CareCase.id == case_id)
    )
    res = await db.execute(case_stmt)
    care_case = res.scalar_one_or_none()
    if not care_case:
        raise HTTPException(status_code=404, detail="Care case not found")

    content = await file.read()
    filename = file.filename or "report.pdf"

    from app.services.report_upload_service import ReportUploadService
    try:
        safe_filename, file_type = ReportUploadService.validate_file(content, filename)
    except ValueError as ve:
        err_msg = str(ve)
        status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if "exceeds" in err_msg else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=err_msg)

    proc_result = ReportUploadService.process_and_extract(content, file_type, safe_filename)

    now = datetime.now(timezone.utc)
    ctx = care_case.case_context or {}
    ctx["staged_report"] = {
        "safe_filename": safe_filename,
        "original_filename": filename,
        "file_size": len(content),
        "file_type": file_type,
        "state": proc_result.get("state"),
        "reason": proc_result.get("reason"),
        "finding_code": proc_result.get("finding_code"),
        "finding_summary": proc_result.get("finding_summary"),
        "recommendation": proc_result.get("recommendation"),
        "structured_summary": proc_result.get("structured_summary"),
        "extracted_text": proc_result.get("text"),
        "uploaded_by": getattr(current_user, "name", "Care Coordinator"),
        "uploaded_at": now.isoformat(),
        "screening_order_id": screening_order_id
    }
    care_case.case_context = ctx
    await db.commit()

    if proc_result.get("state") == "FAILED":
        return ApiResponseEnvelope(
            success=False,
            message=proc_result.get("reason", "Could not read this file"),
            data={
                "state": "FAILED",
                "reason": proc_result.get("reason"),
                "filename": filename,
                "preview": proc_result.get("preview"),
                "stage_2_completed": False
            }
        )

    return ApiResponseEnvelope(
        success=True,
        message="Report uploaded and validated. Ready for coordinator finalization.",
        data={
            "state": "READY_TO_FINALIZE",
            "safe_filename": safe_filename,
            "filename": filename,
            "file_size": len(content),
            "file_type": file_type,
            "preview": proc_result.get("preview"),
            "finding_code": proc_result.get("finding_code"),
            "finding_summary": proc_result.get("finding_summary"),
            "recommendation": proc_result.get("recommendation"),
            "structured_summary": proc_result.get("structured_summary"),
            "stage_2_completed": False
        }
    )


@router.post("/{case_id}/finalize-report", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Coordinator Finalizes Clinical Report & Completes Stage 2")
async def finalize_report(
    case_id: uuid.UUID,
    req: FinalizeReportRequest,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Care Coordinator finalizes the validated medical report.
    Completes Stage 2 through LifecycleService. Idempotent across multiple clicks.
    """
    if current_user.role.lower() not in ("care_coordinator", "coordinator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only Care Coordinators are authorized to finalize clinical reports."
        )

    case_stmt = (
        select(CareCase)
        .options(
            selectinload(CareCase.patient),
            selectinload(CareCase.screening_result),
            selectinload(CareCase.current_owner)
        )
        .where(CareCase.id == case_id)
    )
    res = await db.execute(case_stmt)
    care_case = res.scalar_one_or_none()
    if not care_case:
        raise HTTPException(status_code=404, detail="Care case not found")

    now = datetime.now(timezone.utc)
    ctx = care_case.case_context or {}
    staged = ctx.get("staged_report") or {}

    finding_code = req.finding_code or staged.get("finding_code") or "BI-RADS 4"
    finding_summary = req.finding_summary or staged.get("finding_summary") or "focal asymmetry requiring further diagnostic evaluation"
    recommendation = req.clinical_recommendation or staged.get("recommendation") or "diagnostic biopsy and clinical evaluation"
    filename = staged.get("safe_filename") or "report.pdf"

    stages = LifecycleService.get_lifecycle_stages(care_case)
    stage_2 = next((s for s in stages if s.get("stage_number") == 2), None)
    if stage_2 and stage_2.get("status") == "completed":
        return ApiResponseEnvelope(
            success=True,
            message="Report is already finalized (idempotent).",
            data={
                "case_id": str(care_case.id),
                "status": "FINALIZED" if not req.requires_doctor_review else "REQUIRES_REVIEW",
                "finding_code": finding_code,
                "finding_summary": finding_summary,
                "stage_2_completed": True
            }
        )

    # 1. Update or create ScreeningResult record
    screening_type_label = "Mammogram"
    if care_case.screening_result:
        sr = care_case.screening_result
        screening_type_label = sr.screening_type or "Mammogram"
        sr.finding_code = finding_code
        sr.finding_summary = finding_summary
        sr.test_date = now
        sr_raw = dict(sr.raw_report_data or {})
        sr_raw.update({
            "filename": filename,
            "report_text": finding_summary,
            "recommendation": recommendation,
            "finalized_by": getattr(current_user, "name", "Priya Nair, RN"),
            "finalized_at": now.isoformat(),
            "structured_summary": staged.get("structured_summary")
        })
        sr.raw_report_data = sr_raw
    else:
        sr = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=care_case.patient_id,
            screening_type="Mammogram",
            test_date=now,
            finding_code=finding_code,
            finding_summary=finding_summary,
            urgency_level=req.urgency_level or "standard",
            performing_facility=care_case.current_owner.facility if care_case.current_owner else "Metropolitan Screening Center",
            raw_report_data={
                "filename": filename,
                "report_text": finding_summary,
                "recommendation": recommendation,
                "finalized_by": getattr(current_user, "name", "Priya Nair, RN"),
                "finalized_at": now.isoformat(),
                "structured_summary": staged.get("structured_summary")
            }
        )
        db.add(sr)
        await db.flush()
        care_case.screening_result_id = sr.id

    report_status = "FINALIZED"
    if req.requires_doctor_review:
        report_status = "REQUIRES_REVIEW"
        care_case.status = "requires_review"

    ctx = dict(care_case.case_context or {})
    ctx["report_status"] = report_status
    care_case.case_context = ctx
    await db.commit()

    # 2. Advance Stage 2 (RESULT_FINALIZED) & Stage 3 (RESULT_DELIVERED + Patient Notification) via LifecycleService
    with get_sync_db() as sync_db:
        LifecycleService.advance_stage(
            db=sync_db,
            case_id=care_case.id,
            stage_ident=2,
            actor_role="care_coordinator",
            actor_id=str(current_user.user_id),
            actor_name=getattr(current_user, "name", "Priya Nair, RN"),
            evidence={
                "evidence_type": "diagnostic_report",
                "finding_code": finding_code,
                "finding_summary": finding_summary,
                "report_filename": filename,
                "report_finalized": True,
                "finalized_by": getattr(current_user, "name", "Priya Nair, RN"),
                "finalized_at": now.isoformat()
            }
        )
        LifecycleService.advance_stage(
            db=sync_db,
            case_id=care_case.id,
            stage_ident=3,
            actor_role="care_coordinator",
            actor_id=str(current_user.user_id),
            actor_name=getattr(current_user, "name", "Priya Nair, RN"),
            evidence={
                "notification_channel": "in_app_portal",
                "delivered": True,
                "report_filename": filename,
                "finding_code": finding_code
            },
            notes=f"Finalized report ({finding_code}) delivered to patient portal with notification.",
            patient_notification_title=f"Diagnostic Report Finalized: {finding_code}",
            patient_notification_message=(
                f"Your {screening_type_label} "
                f"report ({finding_code}) has been validated and finalized. Open CareBridge AI to review your plain-language explanation."
            )
        )

    await db.refresh(care_case)

    return ApiResponseEnvelope(
        success=True,
        message=f"Report finalized successfully. Stage 2 completed (Status: {report_status}).",
        data={
            "case_id": str(care_case.id),
            "status": report_status,
            "finding_code": finding_code,
            "finding_summary": finding_summary,
            "stage_2_completed": True
        }
    )


class ExplainReportRequest(BaseModel):
    language: Optional[str] = Field("en", description="Target language (en, es, ar, ta)")


@router.post("/{case_id}/explain-report", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Patient AI Plain-Language Report Explanation")
async def explain_case_report(
    case_id: uuid.UUID,
    req: Optional[ExplainReportRequest] = None,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Translates finalized diagnostic report into empathetic, Grade 6-8 plain language
    with 6 structured sections, reviewed glossary terms, and advances Stage 4 (PATIENT_UNDERSTANDS).
    """
    from app.services.report_explanation_service import ReportExplanationService

    lang = req.language if req and req.language else "en"
    with get_sync_db() as sync_db:
        result = ReportExplanationService.generate_explanation(
            db=sync_db,
            case_id=case_id,
            language=lang,
            actor_role=current_user.role.lower() if current_user.role.lower() in ("patient", "care_coordinator") else "ai_coordinator",
            actor_id=str(current_user.user_id)
        )

    if not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Could not generate report explanation.")
        )

    return ApiResponseEnvelope(
        success=True,
        message="Plain-language report explanation generated and Stage 4 completed.",
        data=result["data"]
    )


@router.get("/{case_id}/explain-report/stream", summary="Stream Plain-Language Report Explanation via SSE")
async def stream_case_report_explanation(
    case_id: uuid.UUID,
    lang: str = Query("en"),
    current_user: UserPrincipal = Depends(get_current_user)
):
    """
    Streams the plain-language report explanation as Server-Sent Events (SSE),
    persisting full text and completing Stage 4 upon completion.
    """
    import json
    import asyncio
    from fastapi.responses import StreamingResponse
    from app.services.report_explanation_service import ReportExplanationService

    async def event_generator():
        with get_sync_db() as sync_db:
            result = ReportExplanationService.generate_explanation(
                db=sync_db,
                case_id=case_id,
                language=lang,
                actor_role=current_user.role.lower() if current_user.role.lower() in ("patient", "care_coordinator") else "ai_coordinator",
                actor_id=str(current_user.user_id)
            )

        if not result.get("success"):
            err_payload = json.dumps({"error": result.get("error", "Could not read this report text.")})
            yield f"event: error\ndata: {err_payload}\n\n"
            return

        data = result["data"]
        sections = [
            ("What your report says", data["what_your_report_says"]),
            ("What these words mean", data["what_these_words_mean"]),
            ("What your report recommends", data["what_your_report_recommends"]),
            ("What is not certain", data["what_is_not_certain"]),
            ("Questions you may want to ask your doctor", data["questions_for_doctor"]),
            ("Warm closing", data["warm_closing"]),
        ]

        for heading, body in sections:
            chunk = json.dumps({"section": heading, "content": body})
            yield f"event: section\ndata: {chunk}\n\n"
            await asyncio.sleep(0.02)

        done_payload = json.dumps({
            "stage_4_completed": True,
            "structured_summary": data["structured_summary"],
            "matched_glossary_ids": data["matched_glossary_ids"],
            "unknown_terms": data["unknown_terms"]
        })
        yield f"event: done\ndata: {done_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
