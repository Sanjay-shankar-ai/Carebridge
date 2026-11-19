"""
CareBridge Analytics & Operational Prioritization API Endpoints (Phase 10)
Exposes data-driven metrics, operational drop-off risk prioritization, and dynamic filters.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_sync_db
from app.services.analytics_service import CareBridgeAnalyticsService
from app.core.security import get_current_user, UserPrincipal
from app.schemas.common import ApiResponseEnvelope

router = APIRouter(prefix="/analytics", tags=["Analytics & Closed-Loop Reporting"])


def parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Helper to parse ISO-8601 date strings safely into UTC datetime objects."""
    if not dt_str or dt_str.lower() in ("all", "undefined", "null"):
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        # Fallback for YYYY-MM-DD
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None


@router.get("/metrics", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Calculate Core Closed-Loop Metrics")
def get_analytics_metrics(
    from_date: Optional[str] = Query(None, description="Start date (ISO-8601)"),
    to_date: Optional[str] = Query(None, description="End date (ISO-8601)"),
    status: Optional[str] = Query(None, description="Case status filter ('all', 'active', 'recovering', 'closed', etc.)"),
    provider_id: Optional[str] = Query(None, description="Provider UUID, provider name, or 'unassigned'"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """
    Computes all 9 core operational and care coordination metrics from real database records.
    Restricted to Care Coordinators, Clinicians, and Administrators.
    1. Time from result to notification
    2. Patient acknowledgement rate
    3. Referral acceptance rate
    4. Appointment attendance rate
    5. Drop-off recovery rate
    6. Median time to care
    7. Verified closure rate
    8. Overdue cases
    9. Unassigned cases
    """
    if current_user.role == "patient":
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Patients do not have access to platform operations analytics."
        )
    start_dt = parse_iso_datetime(from_date)
    end_dt = parse_iso_datetime(to_date)

    metrics = CareBridgeAnalyticsService.calculate_all_metrics(
        db=db,
        from_date=start_dt,
        to_date=end_dt,
        status=status,
        provider_id=provider_id
    )

    return ApiResponseEnvelope.success_response(
        data=metrics,
        message="Closed-loop care metrics calculated successfully from database records."
    )


@router.get("/operational-priorities", response_model=ApiResponseEnvelope[List[Dict[str, Any]]], summary="Operational Drop-Off Risk Prioritization")
def get_operational_priorities(
    from_date: Optional[str] = Query(None, description="Start date (ISO-8601)"),
    to_date: Optional[str] = Query(None, description="End date (ISO-8601)"),
    status: Optional[str] = Query(None, description="Case status filter"),
    provider_id: Optional[str] = Query(None, description="Provider filter"),
    tier: Optional[str] = Query(None, description="Tier filter: 'all', 'urgent_followup', 'elevated_attention', 'on_track'"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """
    Prioritizes active cases based on patient interaction history and case milestone progress.
    Restricted to Care Coordinators, Clinicians, and Administrators.
    Explicitly categorized as Administrative / Coordination Follow-up Prioritization.
    Never represented as clinical risk prediction.
    """
    if current_user.role == "patient":
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Patients do not have access to operational drop-off prioritization."
        )
    start_dt = parse_iso_datetime(from_date)
    end_dt = parse_iso_datetime(to_date)

    priorities = CareBridgeAnalyticsService.get_operational_dropoff_priorities(
        db=db,
        from_date=start_dt,
        to_date=end_dt,
        status=status,
        provider_id=provider_id,
        tier_filter=tier
    )

    return ApiResponseEnvelope.success_response(
        data=priorities,
        message=f"Retrieved {len(priorities)} active case(s) prioritized for operational follow-up."
    )


@router.get("/filters", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Dashboard Filter Options")
def get_filter_options(
    db: Session = Depends(get_sync_db)
):
    """Retrieves dynamic filter options (providers, statuses) available in the database."""
    options = CareBridgeAnalyticsService.get_filter_options(db=db)
    return ApiResponseEnvelope.success_response(
        data=options,
        message="Retrieved filter options"
    )
