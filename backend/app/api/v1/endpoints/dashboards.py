"""
CareBridge Dashboard Synchronized Projections Endpoints
Exposes role-authorized, synchronized domain read models for:
- /api/v1/dashboards/patient
- /api/v1/dashboards/doctor
- /api/v1/dashboards/coordinator
- /api/v1/dashboards/consistency-check
"""

import uuid
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_sync_db
from app.core.security import get_current_user, UserPrincipal
from app.schemas.common import ApiResponseEnvelope
from app.services.dashboard_projection_service import DashboardProjectionService
from app.services.consistency_checker import ConsistencyCheckerService


router = APIRouter(prefix="/dashboards", tags=["Dashboards"])


@router.get("/patient", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Get Patient Dashboard Projection")
def get_patient_dashboard(
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """
    Authoritative domain projection for the PATIENT role.
    Strictly isolated: Patients can only view their own clinical and journey state.
    """
    if current_user.role != "patient":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Patient dashboard is only accessible to authenticated patients."
        )

    if not current_user.patient_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account is not linked to an active patient record."
        )

    try:
        p_uuid = uuid.UUID(str(current_user.patient_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid patient UUID")

    try:
        data = DashboardProjectionService.get_patient_dashboard(db, p_uuid)
        return ApiResponseEnvelope.success_response(
            data=data,
            message="Retrieved authoritative patient dashboard state"
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/doctor", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Get Doctor Dashboard Projection")
def get_doctor_dashboard(
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """
    Authoritative domain projection for the DOCTOR role.
    Strictly isolated: Doctors only view cases assigned to them or specialty pool requests.
    """
    if current_user.role not in ("doctor", "clinician"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Doctor dashboard is only accessible to authorized physicians."
        )

    if not current_user.owner_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Physician account is not linked to an active case owner record."
        )

    try:
        o_uuid = uuid.UUID(str(current_user.owner_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid doctor owner UUID")

    try:
        data = DashboardProjectionService.get_doctor_dashboard(db, o_uuid)
        return ApiResponseEnvelope.success_response(
            data=data,
            message="Retrieved authoritative doctor dashboard state"
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/coordinator", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Get Coordinator Dashboard Projection")
def get_coordinator_dashboard(
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """
    Authoritative domain projection for the CARE_COORDINATOR role.
    Access to care journey operations, screening orders, allocation queue, recovery plays, SLAs.
    """
    if current_user.role != "care_coordinator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Coordinator hub is only accessible to authorized care coordinators."
        )

    data = DashboardProjectionService.get_coordinator_dashboard(db)
    return ApiResponseEnvelope.success_response(
        data=data,
        message="Retrieved authoritative care coordinator dashboard state"
    )


@router.get("/consistency-check", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Audit & Rebuild Dashboard Projections")
def run_consistency_audit(
    dry_run: bool = Query(True, description="When true, reports anomalies without modifying state."),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """
    Clinical consistency checker for care lifecycle projections and required tasks.
    Detects stale or corrupted projections and repairs them safely.
    """
    if current_user.role not in ("care_coordinator", "doctor", "clinician"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only authorized clinical personnel can trigger projection audits."
        )

    result = ConsistencyCheckerService.audit_cases(db, dry_run=dry_run)
    return ApiResponseEnvelope.success_response(
        data=result,
        message=f"Consistency audit completed in {'dry-run' if dry_run else 'apply'} mode"
    )
