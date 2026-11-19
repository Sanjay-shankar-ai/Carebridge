"""
Patient Memory Layer
Retrieves and updates patient preferences, language, accessibility, and social context.
"""

import uuid
from typing import Optional, Dict, Any, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from app.models.patient import Patient, Consent
from app.memory.schemas import PatientMemoryContext


def _build_patient_memory(patient: Patient) -> PatientMemoryContext:
    ctx = patient.patient_context or {}
    active_consents = [c.scope for c in patient.consents if c.status == "active"]
    
    return PatientMemoryContext(
        patient_id=patient.id,
        mrn=patient.mrn,
        full_name=f"{patient.first_name} {patient.last_name}",
        phone=patient.phone,
        preferred_language=patient.preferred_language,
        communication_channel=patient.communication_channel,
        accessibility_requirements=patient.accessibility_requirements or {},
        known_barriers=ctx.get("known_barriers", []),
        caregiver_name=ctx.get("caregiver_name"),
        caregiver_phone=ctx.get("caregiver_phone"),
        active_consents=active_consents,
    )


async def get_patient_memory(
    patient_id: uuid.UUID,
    db: AsyncSession
) -> Optional[PatientMemoryContext]:
    """Asynchronously retrieves structured patient memory from the database."""
    stmt = (
        select(Patient)
        .where(Patient.id == patient_id)
    )
    result = await db.execute(stmt)
    patient = result.scalar_one_or_none()
    if not patient:
        return None
    
    # Load consents
    consents_stmt = select(Consent).where(Consent.patient_id == patient_id)
    consents_res = await db.execute(consents_stmt)
    patient.consents = list(consents_res.scalars().all())
    
    return _build_patient_memory(patient)


def get_patient_memory_sync(
    patient_id: uuid.UUID,
    db: Session
) -> Optional[PatientMemoryContext]:
    """Synchronously retrieves structured patient memory (used in testing and sync tasks)."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        return None
    return _build_patient_memory(patient)


async def record_patient_barrier(
    patient_id: uuid.UUID,
    barrier: str,
    db: AsyncSession
) -> bool:
    """Appends an inferred barrier to patient memory."""
    patient = await db.get(Patient, patient_id)
    if not patient:
        return False
    
    ctx = dict(patient.patient_context or {})
    barriers = list(ctx.get("known_barriers", []))
    if barrier not in barriers:
        barriers.append(barrier)
        ctx["known_barriers"] = barriers
        patient.patient_context = ctx
        await db.commit()
    return True
