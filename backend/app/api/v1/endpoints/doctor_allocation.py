"""
CareBridge Doctor Allocation & Assignment Endpoints
Provides endpoints for:
- Doctor reviewing and responding to assignment requests (Accept / Decline)
- Coordinator reviewing ranked candidates and executing reassignments
- Background timeout & escalation execution
"""

import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.database.session import get_sync_db
from app.core.security import get_current_user, UserPrincipal
from app.models.doctor_assignment import DoctorAssignment
from app.models.owner import CaseOwner
from app.models.care_case import CareCase
from app.services.doctor_allocation_service import DoctorAllocationService
from app.schemas.common import ApiResponseEnvelope

router = APIRouter(prefix="", tags=["Doctor Allocation & Assignments"])


class DeclineRequest(BaseModel):
    decline_reason: Optional[str] = Field(None, description="Clinical or scheduling reason for declining assignment")


class ReassignRequest(BaseModel):
    new_doctor_id: uuid.UUID = Field(..., description="ID of the alternative specialist doctor")
    reassignment_reason: str = Field(..., description="Coordinator's documented rationale for reassignment")


class AssignmentResponseDTO(BaseModel):
    id: str
    case_id: str
    doctor_id: str
    doctor_name: Optional[str] = None
    status: str
    specialty_matched: str
    urgency_level: str
    allocation_score: float
    allocation_factors: Dict[str, Any]
    assigned_by_role: str
    deadline: str
    responded_at: Optional[str] = None
    decline_reason: Optional[str] = None
    reassignment_reason: Optional[str] = None
    case_number: Optional[str] = None
    patient_name: Optional[str] = None


@router.get("/doctor/assignments", response_model=ApiResponseEnvelope[List[AssignmentResponseDTO]], summary="Doctor Lists Assignment Requests")
def get_doctor_assignments(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status, e.g. PENDING_DOCTOR_RESPONSE"),
    current_user: UserPrincipal = Depends(get_current_user),
):
    """Retrieves assignment requests for the authenticated doctor."""
    with get_sync_db() as db:
        query = db.query(DoctorAssignment)
        if current_user.role != "care_coordinator":
            # Must filter to this doctor's owner_id
            if not current_user.owner_id:
                raise HTTPException(status_code=403, detail="User account is not linked to a clinical doctor profile.")
            query = query.filter(DoctorAssignment.doctor_id == current_user.owner_id)

        if status_filter:
            query = query.filter(DoctorAssignment.status == status_filter.upper())

        assignments = query.order_by(DoctorAssignment.created_at.desc()).all()
        results = []
        for a in assignments:
            doc = db.query(CaseOwner).filter(CaseOwner.id == a.doctor_id).first()
            case = db.query(CareCase).filter(CareCase.id == a.case_id).first()
            results.append(AssignmentResponseDTO(
                id=str(a.id),
                case_id=str(a.case_id),
                doctor_id=str(a.doctor_id),
                doctor_name=doc.name if doc else "Doctor",
                status=a.status,
                specialty_matched=a.specialty_matched,
                urgency_level=a.urgency_level,
                allocation_score=a.allocation_score,
                allocation_factors=a.allocation_factors or {},
                assigned_by_role=a.assigned_by_role,
                deadline=a.deadline.isoformat(),
                responded_at=a.responded_at.isoformat() if a.responded_at else None,
                decline_reason=a.decline_reason,
                reassignment_reason=a.reassignment_reason,
                case_number=case.case_number if case else None,
                patient_name=f"{case.patient.first_name} {case.patient.last_name}" if case and case.patient else None,
            ))
        return ApiResponseEnvelope.success_response(results)


@router.post("/doctor/assignments/{assignment_id}/accept", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Doctor Accepts Assignment Request")
def accept_assignment(
    assignment_id: uuid.UUID,
    current_user: UserPrincipal = Depends(get_current_user),
):
    """
    Doctor formally accepts the case assignment request.
    Verifies authentication, deadline expiration, and concurrency guards.
    """
    with get_sync_db() as db:
        try:
            assignment = DoctorAllocationService.doctor_accept_assignment(
                db=db,
                assignment_id=assignment_id,
                doctor_user_id=current_user.user_id
            )
            return ApiResponseEnvelope.success_response({
                "assignment_id": str(assignment.id),
                "case_id": str(assignment.case_id),
                "status": assignment.status,
                "responded_at": assignment.responded_at.isoformat() if assignment.responded_at else None,
                "message": "Doctor assignment successfully accepted. Patient notified and appointment scheduling unlocked."
            })
        except PermissionError as pe:
            raise HTTPException(status_code=403, detail=str(pe))
        except ValueError as ve:
            # Concurrency conflict or expired
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ve))


@router.post("/doctor/assignments/{assignment_id}/decline", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Doctor Declines Assignment Request")
def decline_assignment(
    assignment_id: uuid.UUID,
    req: DeclineRequest,
    current_user: UserPrincipal = Depends(get_current_user),
):
    """
    Doctor declines assignment request with optional reason.
    Transitions status to DECLINED and escalates to the Care Coordinator.
    """
    with get_sync_db() as db:
        try:
            assignment = DoctorAllocationService.doctor_decline_assignment(
                db=db,
                assignment_id=assignment_id,
                doctor_user_id=current_user.user_id,
                decline_reason=req.decline_reason
            )
            return ApiResponseEnvelope.success_response({
                "assignment_id": str(assignment.id),
                "case_id": str(assignment.case_id),
                "status": assignment.status,
                "decline_reason": assignment.decline_reason,
                "message": "Assignment declined. Case escalated to Care Coordinator for specialist reassignment."
            })
        except PermissionError as pe:
            raise HTTPException(status_code=403, detail=str(pe))
        except ValueError as ve:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ve))


@router.post("/coordinator/assignments/{assignment_id}/reassign", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Coordinator Reassigns Alternative Doctor")
def reassign_doctor(
    assignment_id: uuid.UUID,
    req: ReassignRequest,
    current_user: UserPrincipal = Depends(get_current_user),
):
    """
    Care Coordinator reassigns case to an alternative eligible doctor.
    Requires coordinator authorization and documented reason.
    """
    if current_user.role not in ("care_coordinator", "doctor"):
        raise HTTPException(status_code=403, detail="Only Care Coordinators are authorized to reassign specialist doctors.")

    with get_sync_db() as db:
        try:
            new_assign = DoctorAllocationService.reassign_doctor(
                db=db,
                previous_assignment_id=assignment_id,
                new_doctor_id=req.new_doctor_id,
                coordinator_user_id=current_user.user_id,
                reassignment_reason=req.reassignment_reason
            )
            return ApiResponseEnvelope.success_response({
                "previous_assignment_id": str(assignment_id),
                "new_assignment_id": str(new_assign.id),
                "new_doctor_id": str(new_assign.doctor_id),
                "status": new_assign.status,
                "reassignment_reason": new_assign.reassignment_reason,
                "deadline": new_assign.deadline.isoformat(),
                "message": "Case successfully reassigned. New specialist doctor notified for acceptance."
            })
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))


@router.get("/cases/{case_id}/doctor-candidates", response_model=ApiResponseEnvelope[List[Dict[str, Any]]], summary="Coordinator Evaluates Ranked Doctor Candidates")
def get_doctor_candidates_for_case(
    case_id: uuid.UUID,
    specialty_override: Optional[str] = Query(None, description="Optional override for specialty"),
    current_user: UserPrincipal = Depends(get_current_user),
):
    """Returns explainable, workload-aware ranked doctor candidates for a case."""
    if current_user.role not in ("care_coordinator", "doctor"):
        raise HTTPException(status_code=403, detail="Only clinical staff and coordinators can view doctor allocation candidates.")

    with get_sync_db() as db:
        case = db.query(CareCase).filter(CareCase.id == case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail="Care case not found")

        target_specialty = specialty_override
        if not target_specialty:
            ctx = case.case_context or {}
            target_specialty = ctx.get("target_specialty") or "General Oncology"

        candidates = DoctorAllocationService.rank_eligible_doctors(
            db=db,
            specialty=target_specialty,
            urgency_level=case.priority or "standard",
            case_id=case.id
        )
        return ApiResponseEnvelope.success_response(candidates)
