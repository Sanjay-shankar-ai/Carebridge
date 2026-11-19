"""
CareBridge Referrals API (Phase 9)
Provides real backend endpoints for listing referrals, tracking specialist handoffs,
and monitoring 48h acceptance deadlines.
"""

import uuid
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.session import get_async_db, get_sync_db
from app.models.referral import Referral
from app.models.care_case import CareCase
from app.models.patient import Patient
from app.services.lifecycle_service import LifecycleService
from app.core.security import get_current_user, UserPrincipal
from app.schemas.common import ApiResponseEnvelope

router = APIRouter(prefix="/referrals", tags=["Referrals"])


@router.get("", response_model=ApiResponseEnvelope[List[Dict[str, Any]]], summary="List Referrals")
async def list_referrals(
    case_id: Optional[uuid.UUID] = Query(None, description="Filter by case ID"),
    status: Optional[str] = Query(None, description="Filter by status (sent, accepted, rejected, completed)"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Retrieves specialist referrals with target facilities and acceptance deadlines."""
    stmt = (
        select(Referral)
        .options(
            selectinload(Referral.care_case).selectinload(CareCase.patient)
        )
        .order_by(Referral.created_at.desc())
    )

    if current_user.role == "patient":
        if not current_user.patient_id:
            return ApiResponseEnvelope.success_response(data=[], message="No referrals found.")
        try:
            p_uuid = uuid.UUID(current_user.patient_id)
            stmt = stmt.where(Referral.patient_id == p_uuid)
        except ValueError:
            return ApiResponseEnvelope.success_response(data=[], message="Invalid patient ID.")

    if case_id:
        stmt = stmt.where(Referral.case_id == case_id)
    if status:
        stmt = stmt.where(Referral.status == status)

    result = await db.execute(stmt)
    refs = result.scalars().all()

    data = []
    for r in refs:
        patient_name = "Unknown"
        case_number = "Unknown"
        if r.care_case:
            case_number = r.care_case.case_number
            if r.care_case.patient:
                patient_name = f"{r.care_case.patient.first_name} {r.care_case.patient.last_name}"

        data.append({
            "id": str(r.id),
            "case_id": str(r.case_id),
            "case_number": case_number,
            "patient_id": str(r.patient_id),
            "patient_name": patient_name,
            "referring_provider": r.referring_provider,
            "target_facility": r.target_facility,
            "specialty": r.specialty,
            "reason_for_referral": r.reason_for_referral,
            "status": r.status,
            "rejection_reason": r.rejection_reason,
            "acceptance_deadline": r.acceptance_deadline.isoformat() if r.acceptance_deadline else None,
            "responded_at": r.responded_at.isoformat() if r.responded_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None
        })

    return ApiResponseEnvelope.success_response(
        data=data,
        message=f"Retrieved {len(data)} referral(s)"
    )


class AcceptReferralRequest(BaseModel):
    receiving_provider_name: str = Field(default="CareBridge Breast Health Clinic", description="Receiving provider or facility name")
    acceptance_notes: Optional[str] = Field(default="Referral accepted for specialist consultation and workup.", description="Acceptance notes")


@router.post("/{referral_id}/accept", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Accept Specialist Referral (Stage 8)")
async def accept_referral_endpoint(
    referral_id: uuid.UUID,
    req: AcceptReferralRequest,
    current_user: UserPrincipal = Depends(get_current_user),
):
    """
    Receiving specialist facility / provider formally accepts the referral.
    Completes Stage 8 (REFERRAL_ACCEPTED) and generates an appointment scheduling task for the coordinator.
    """
    if current_user.role == "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Patients cannot accept medical referrals on behalf of clinics."
        )

    with get_sync_db() as sync_db:
        try:
            res = LifecycleService.accept_referral(
                db=sync_db,
                referral_id=referral_id,
                receiving_provider_name=req.receiving_provider_name,
                acceptance_notes=req.acceptance_notes
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    return ApiResponseEnvelope.success_response(
        data=res,
        message=f"Referral successfully accepted by {req.receiving_provider_name}."
    )
