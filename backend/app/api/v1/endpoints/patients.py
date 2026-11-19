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

router = APIRouter(prefix="/patients", tags=["Patients"])


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
