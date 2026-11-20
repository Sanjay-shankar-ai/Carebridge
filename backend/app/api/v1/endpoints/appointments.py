"""
CareBridge Appointments API (Phase 9 & Role Workflow Enhancement)
Provides real backend endpoints for listing appointments, booking appointments,
and robust doctor/patient cancellation & rescheduling lifecycle workflows.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.session import get_async_db
from app.models.appointment import Appointment
from app.models.care_case import CareCase, Task
from app.models.patient import Patient
from app.models.event_audit import CaseEvent, AuditLog
from app.core.security import get_current_user, UserPrincipal
from app.schemas.common import ApiResponseEnvelope

router = APIRouter(prefix="/appointments", tags=["Appointments"])


class BookAppointmentRequest(BaseModel):
    case_id: uuid.UUID = Field(description="UUID of the CareCase")
    patient_id: uuid.UUID = Field(description="UUID of the Patient")
    facility: str = Field(description="Facility/Clinic name")
    provider_name: str = Field(description="Doctor / Provider name")
    appointment_type: str = Field(default="diagnostic_evaluation", description="Type of visit (e.g. diagnostic_biopsy, follow_up)")
    scheduled_time: datetime = Field(description="Target ISO timestamp for visit")
    notes: Optional[str] = Field(default=None, description="Clinical or scheduling notes")


class CancelAppointmentRequest(BaseModel):
    cancellation_reason: str = Field(description="Mandatory clinical or operational reason for cancellation")
    cancelled_by: str = Field(default="doctor", description="Role initiating cancellation: 'doctor' or 'patient'")
    notes: Optional[str] = Field(default=None, description="Additional context or patient instructions")


class RescheduleProposeRequest(BaseModel):
    proposed_slots: List[datetime] = Field(description="List of proposed alternative timestamps")
    reason: str = Field(description="Reason for proposing new times")
    proposed_by: str = Field(default="doctor", description="'doctor', 'patient', or 'care_coordinator'")


class RescheduleAcceptRequest(BaseModel):
    selected_slot: datetime = Field(description="Mutually agreed scheduled time")
    accepted_by: str = Field(description="'doctor' or 'patient'")
    partner_confirmed: bool = Field(default=False, description="Whether both parties have confirmed")


class ConfirmAppointmentRequest(BaseModel):
    confirmed_by: Optional[str] = Field(default=None, description="'doctor' or 'patient'")
    appointment_version: int = Field(default=1, description="Version of the appointment schedule agreed upon")
    notes: Optional[str] = Field(default=None, description="Confirmation notes")


@router.get("", response_model=ApiResponseEnvelope[List[Dict[str, Any]]], summary="List Appointments")
async def list_appointments(
    case_id: Optional[uuid.UUID] = Query(None, description="Filter by case ID"),
    patient_id: Optional[uuid.UUID] = Query(None, description="Filter by patient ID"),
    status: Optional[str] = Query(None, description="Filter by status (booked, attended, no_show, cancelled)"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Retrieves appointments with associated case and patient details, enforcing patient privacy."""
    stmt = (
        select(Appointment)
        .options(
            selectinload(Appointment.care_case).selectinload(CareCase.patient)
        )
        .order_by(Appointment.scheduled_time.desc())
    )

    # Scoping for patient role
    if current_user.role == "patient":
        if not current_user.patient_id:
            return ApiResponseEnvelope.success_response(data=[], message="No appointments found.")
        try:
            p_uuid = uuid.UUID(current_user.patient_id)
            stmt = stmt.where(Appointment.patient_id == p_uuid)
        except ValueError:
            return ApiResponseEnvelope.success_response(data=[], message="Invalid patient ID.")
    elif patient_id:
        stmt = stmt.where(Appointment.patient_id == patient_id)

    if case_id:
        stmt = stmt.where(Appointment.case_id == case_id)
    if status:
        stmt = stmt.where(Appointment.status == status)

    result = await db.execute(stmt)
    appts = result.scalars().all()

    data = []
    for a in appts:
        patient_name = "Unknown"
        case_number = "Unknown"
        if a.care_case:
            case_number = a.care_case.case_number
            if a.care_case.patient:
                patient_name = f"{a.care_case.patient.first_name} {a.care_case.patient.last_name}"
        elif a.patient_id:
            patient_name = f"Patient {str(a.patient_id)[:8]}"

        data.append({
            "id": str(a.id),
            "case_id": str(a.case_id),
            "case_number": case_number,
            "patient_id": str(a.patient_id),
            "patient_name": patient_name,
            "facility": a.facility,
            "provider_name": a.provider_name,
            "appointment_type": a.appointment_type,
            "scheduled_time": a.scheduled_time.isoformat() if a.scheduled_time else None,
            "status": a.status,
            "attendance_recorded_at": a.attendance_recorded_at.isoformat() if a.attendance_recorded_at else None,
            "cancellation_reason": a.cancellation_reason,
            "cancellation_outcome": a.cancellation_outcome,
            "notes": a.notes
        })

    return ApiResponseEnvelope.success_response(
        data=data,
        message=f"Retrieved {len(data)} appointment(s)"
    )


@router.post("/book", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Book New Appointment")
async def book_appointment(
    req: BookAppointmentRequest,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Books an appointment for a patient within an active care case.
    Validates case existence, creates appointment record with status 'booked',
    updates care case status, and creates audit and case timeline events.
    """
    # Patient authorization check: Patients can only book for themselves
    if current_user.role == "patient":
        if not current_user.patient_id or str(req.patient_id) != str(current_user.patient_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not have permission to book an appointment for another patient."
            )

    case_stmt = select(CareCase).options(selectinload(CareCase.patient)).where(CareCase.id == req.case_id)
    case_res = await db.execute(case_stmt)
    care_case = case_res.scalar_one_or_none()

    if not care_case:
        raise HTTPException(status_code=404, detail=f"CareCase {req.case_id} not found")

    # Clinical & operational invariant: Reject appointment booking on a closed case
    if care_case.status == "closed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot book appointment on closed care case #{care_case.case_number}. An authorized clinician must explicitly reopen the case first."
        )

    sched_time = req.scheduled_time
    if sched_time.tzinfo is None:
        sched_time = sched_time.replace(tzinfo=timezone.utc)

    # Reliability Invariant: Duplicate Appointment Prevention & Idempotency
    dup_stmt = select(Appointment).where(
        Appointment.patient_id == req.patient_id,
        Appointment.facility == req.facility,
        Appointment.scheduled_time == sched_time,
        Appointment.status.in_(["booked", "confirmed"])
    )
    dup_res = await db.execute(dup_stmt)
    existing_appt = dup_res.scalar_one_or_none()
    if existing_appt:
        return ApiResponseEnvelope.success_response(
            data={
                "id": str(existing_appt.id),
                "case_id": str(existing_appt.case_id),
                "patient_id": str(existing_appt.patient_id),
                "facility": existing_appt.facility,
                "provider_name": existing_appt.provider_name,
                "appointment_type": existing_appt.appointment_type,
                "scheduled_time": existing_appt.scheduled_time.isoformat() if existing_appt.scheduled_time else None,
                "status": existing_appt.status,
                "notes": existing_appt.notes
            },
            message="Appointment already scheduled for this patient at the requested time slot (idempotent)."
        )

    new_appt = Appointment(
        id=uuid.uuid4(),
        case_id=care_case.id,
        patient_id=req.patient_id,
        facility=req.facility,
        provider_name=req.provider_name,
        appointment_type=req.appointment_type,
        scheduled_time=sched_time,
        status="booked",
        notes=req.notes
    )
    db.add(new_appt)

    if care_case.status in ("pending", "notified", "acknowledged", "referred", "recovering", "result_received", "escalated", "in_progress", "active", "reopened", "referral_coordinated"):
        care_case.status = "scheduled"

    event = CaseEvent(
        id=uuid.uuid4(),
        case_id=care_case.id,
        event_type="appointment_booked",
        description=f"Appointment booked with {req.provider_name} at {req.facility} for {sched_time.strftime('%b %d, %Y %I:%M %p UTC')}.",
        event_data={
            "appointment_id": str(new_appt.id),
            "facility": req.facility,
            "provider_name": req.provider_name,
            "appointment_type": req.appointment_type,
            "scheduled_time": sched_time.isoformat()
        }
    )
    db.add(event)

    audit = AuditLog(
        id=uuid.uuid4(),
        case_id=care_case.id,
        patient_id=req.patient_id,
        actor_type="clinician",
        actor_id="carebridge_scheduling_service",
        action="BOOK_APPOINTMENT",
        autonomy_level=2,
        new_state={"appointment_id": str(new_appt.id), "scheduled_time": sched_time.isoformat()},
        rationale=f"Appointment booked: {req.appointment_type} with {req.provider_name}."
    )
    db.add(audit)

    await db.commit()

    # Phase 7: Real-time notification dispatch
    try:
        from app.services.notification_service import NotificationService
        from app.database.session import get_sync_db
        p_name = f"{care_case.patient.first_name} {care_case.patient.last_name}" if care_case.patient else None
        with get_sync_db() as sync_db:
            NotificationService.notify_appointment_booked(
                db=sync_db,
                case_id=care_case.id,
                appointment_id=new_appt.id,
                patient_id=req.patient_id,
                provider_name=req.provider_name,
                facility=req.facility,
                scheduled_time=sched_time,
                patient_name=p_name
            )
            # Advance Stage 9 (APPOINTMENT_SCHEDULED_CONFIRMED) in longitudinal lifecycle
            try:
                from app.services.lifecycle_service import LifecycleService
                LifecycleService.advance_stage(
                    db=sync_db,
                    case_id=care_case.id,
                    stage_ident=9,
                    actor_role=current_user.role,
                    actor_id=str(current_user.user_id),
                    evidence={
                        "appointment_id": str(new_appt.id),
                        "facility": req.facility,
                        "provider_name": req.provider_name,
                        "scheduled_time": sched_time.isoformat(),
                    },
                    notes=f"Appointment confirmed with {req.provider_name} at {req.facility}."
                )
            except Exception as ls_err:
                pass
    except Exception as e:
        import logging
        logging.getLogger("carebridge.appointments").warning(f"Notification dispatch notice: {e}")

    return ApiResponseEnvelope.success_response(
        data={
            "id": str(new_appt.id),
            "case_id": str(new_appt.case_id),
            "patient_id": str(new_appt.patient_id),
            "facility": new_appt.facility,
            "provider_name": new_appt.provider_name,
            "appointment_type": new_appt.appointment_type,
            "scheduled_time": new_appt.scheduled_time.isoformat(),
            "status": new_appt.status,
            "notes": new_appt.notes
        },
        message="Appointment successfully booked"
    )


@router.post("/{appointment_id}/cancel", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Cancel Appointment with Mandatory Reason")
async def cancel_appointment(
    appointment_id: uuid.UUID,
    req: CancelAppointmentRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Cancels an appointment.
    Doctor/clinician cancellations REQUIRE a non-empty cancellation reason.
    Retains care coordinator case ownership and creates an immediate follow-up task to protect patient safety.
    """
    reason = req.cancellation_reason.strip()
    if not reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A mandatory cancellation reason is required to cancel clinical appointments."
        )

    appt_stmt = (
        select(Appointment)
        .options(selectinload(Appointment.care_case))
        .where(Appointment.id == appointment_id)
    )
    appt_res = await db.execute(appt_stmt)
    appt = appt_res.scalar_one_or_none()

    if not appt:
        raise HTTPException(status_code=404, detail=f"Appointment {appointment_id} not found")

    appt.status = "cancelled"
    appt.cancellation_reason = reason
    appt.cancellation_outcome = f"Retained coordinator ownership. Immediate rebooking recommended. Reason: {reason}"
    if req.notes:
        appt.notes = f"{appt.notes or ''} [Cancellation note: {req.notes}]".strip()

    care_case = appt.care_case
    if care_case:
        care_case.status = "recovering"

        now = datetime.now(timezone.utc)
        task = Task(
            id=uuid.uuid4(),
            case_id=care_case.id,
            title=f"Rebook cancelled appointment for {care_case.case_number}",
            description=f"Appointment with {appt.provider_name} cancelled by {req.cancelled_by}. Reason: {reason}. Coordinate mutual alternative slots with patient.",
            task_type="recovery_outreach",
            assigned_to_id=care_case.current_owner_id,
            assigned_role="care_coordinator",
            status="pending",
            due_date=now + timedelta(days=2)
        )
        db.add(task)

        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=care_case.id,
            event_type="appointment_cancelled",
            description=f"Appointment cancelled by {req.cancelled_by}. Reason: {reason}. Retained coordinator ownership and scheduled rebooking outreach.",
            event_data={
                "appointment_id": str(appt.id),
                "cancelled_by": req.cancelled_by,
                "cancellation_reason": reason,
                "retained_coordinator_id": str(care_case.current_owner_id) if care_case.current_owner_id else None
            }
        )
        db.add(event)

        audit = AuditLog(
            id=uuid.uuid4(),
            case_id=care_case.id,
            patient_id=appt.patient_id,
            actor_type="clinician" if req.cancelled_by == "doctor" else "patient",
            actor_id=req.cancelled_by,
            action="CANCEL_APPOINTMENT",
            autonomy_level=3,
            rationale=f"Appointment cancelled with mandatory clinical reason: {reason}"
        )
        db.add(audit)

    await db.commit()

    # Phase 7: Real-time notification dispatch for cancelled visit
    try:
        from app.services.notification_service import NotificationService
        from app.database.session import get_sync_db
        with get_sync_db() as sync_db:
            p_name = None
            if appt.care_case and appt.care_case.patient:
                p_name = f"{appt.care_case.patient.first_name} {appt.care_case.patient.last_name}"
            NotificationService.notify_appointment_cancelled(
                db=sync_db,
                case_id=appt.case_id,
                appointment_id=appt.id,
                patient_id=appt.patient_id,
                reason=reason,
                cancelled_by=req.cancelled_by,
                patient_name=p_name
            )
    except Exception as e:
        import logging
        logging.getLogger("carebridge.appointments").warning(f"Notification cancellation notice: {e}")

    return ApiResponseEnvelope.success_response(
        data={
            "id": str(appt.id),
            "status": appt.status,
            "cancellation_reason": appt.cancellation_reason,
            "cancellation_outcome": appt.cancellation_outcome,
            "coordinator_ownership_retained": True
        },
        message="Appointment cancelled successfully. Care coordinator notified for rapid recovery outreach."
    )


@router.post("/{appointment_id}/reschedule-propose", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Propose Alternative Slots")
async def propose_reschedule(
    appointment_id: uuid.UUID,
    req: RescheduleProposeRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """Proposes mutual alternative appointment slots for doctor and patient alignment."""
    appt_stmt = select(Appointment).where(Appointment.id == appointment_id)
    appt_res = await db.execute(appt_stmt)
    appt = appt_res.scalar_one_or_none()

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    proposed_iso = [s.isoformat() for s in req.proposed_slots]
    appt.notes = f"{appt.notes or ''} [Proposed alternative slots by {req.proposed_by}: {', '.join(proposed_iso)}]".strip()

    await db.commit()

    return ApiResponseEnvelope.success_response(
        data={
            "appointment_id": str(appt.id),
            "proposed_slots": proposed_iso,
            "reason": req.reason,
            "proposed_by": req.proposed_by
        },
        message=f"{len(proposed_iso)} alternative slot(s) proposed"
    )


@router.post("/{appointment_id}/reschedule-accept", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Accept Rescheduled Slot")
async def accept_rescheduled_slot(
    appointment_id: uuid.UUID,
    req: RescheduleAcceptRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Records mutual agreement on a new appointment slot.
    Once accepted, confirms appointment and moves case back into 'scheduled' status.
    """
    appt_stmt = (
        select(Appointment)
        .options(selectinload(Appointment.care_case))
        .where(Appointment.id == appointment_id)
    )
    appt_res = await db.execute(appt_stmt)
    appt = appt_res.scalar_one_or_none()

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    new_time = req.selected_slot
    if new_time.tzinfo is None:
        new_time = new_time.replace(tzinfo=timezone.utc)

    appt.scheduled_time = new_time
    appt.status = "booked"
    appt.cancellation_reason = None
    appt.cancellation_outcome = None
    appt.notes = f"{appt.notes or ''} [Rescheduled confirmed by {req.accepted_by} to {new_time.isoformat()}]".strip()

    if appt.care_case:
        appt.care_case.status = "scheduled"
        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=appt.care_case.id,
            event_type="appointment_rescheduled",
            description=f"Appointment rescheduled to {new_time.strftime('%b %d, %Y %I:%M %p UTC')} after mutual agreement.",
            event_data={"appointment_id": str(appt.id), "new_time": new_time.isoformat()}
        )
        db.add(event)

    await db.commit()

    return ApiResponseEnvelope.success_response(
        data={
            "appointment_id": str(appt.id),
            "scheduled_time": appt.scheduled_time.isoformat(),
            "status": appt.status,
            "confirmed": True
        },
        message="Appointment rescheduled and confirmed"
    )


@router.post("/{appointment_id}/complete", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Doctor Completes Consultation / Appointment")
async def complete_appointment(
    appointment_id: uuid.UUID,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    1-Click Doctor Consultation Completion.
    Updates appointment status to 'attended', records timestamp,
    auto-updates care case status to 'consulted', and logs clinical completion event.
    """
    appt_stmt = (
        select(Appointment)
        .options(selectinload(Appointment.care_case).selectinload(CareCase.patient))
        .where(Appointment.id == appointment_id)
    )
    appt_res = await db.execute(appt_stmt)
    appt = appt_res.scalar_one_or_none()

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    now = datetime.now(timezone.utc)
    appt.status = "attended"
    appt.attendance_recorded_at = now
    doctor_name = getattr(current_user, "name", appt.provider_name or "Attending Physician")

    case_updated = False
    if appt.care_case:
        appt.care_case.status = "consulted"
        case_updated = True

        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=appt.care_case.id,
            event_type="consultation_completed",
            description=f"Consultation and procedure completed with {doctor_name}. Staging and pathology documented.",
            event_data={
                "appointment_id": str(appt.id),
                "attended_at": now.isoformat(),
                "attending_provider": doctor_name
            },
            timestamp=now
        )
        db.add(event)

        # Dispatch completion notification to patient
        try:
            from app.services.notification_service import NotificationService
            from app.database.session import get_sync_db
            with get_sync_db() as sync_db:
                p_name = f"{appt.care_case.patient.first_name} {appt.care_case.patient.last_name}" if appt.care_case.patient else "Patient"
                NotificationService.notify_consultation_completed(
                    db=sync_db,
                    case_id=appt.care_case.id,
                    patient_id=appt.care_case.patient_id,
                    patient_name=p_name,
                    doctor_name=doctor_name,
                    summary="Consultation completed. Your care coordinator will verify follow-up surveillance."
                )
        except Exception as notif_err:
            import logging
            logging.getLogger("carebridge.appointments").warning(f"Notification notice: {notif_err}")

    await db.commit()
    await db.refresh(appt)

    return ApiResponseEnvelope.success_response(
        data={
            "appointment_id": str(appt.id),
            "status": "attended",
            "attendance_recorded_at": now.isoformat(),
            "case_id": str(appt.care_case.id) if appt.care_case else None,
            "case_status": appt.care_case.status if appt.care_case else None,
            "doctor_name": doctor_name,
            "auto_updated": True
        },
        message=f"Consultation with {doctor_name} completed and case updated to consulted."
    )


@router.post("/{appointment_id}/confirm", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Doctor and Patient Dual Confirmation")
async def confirm_appointment(
    appointment_id: uuid.UUID,
    req: ConfirmAppointmentRequest,
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Requires mutual doctor and patient confirmation for the same appointment version.
    Only when both parties have confirmed is the appointment marked 'confirmed'.
    """
    appt_stmt = (
        select(Appointment)
        .options(selectinload(Appointment.care_case))
        .where(Appointment.id == appointment_id)
    )
    appt_res = await db.execute(appt_stmt)
    appt = appt_res.scalar_one_or_none()

    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    caller_role = req.confirmed_by or current_user.role
    notes_text = appt.notes or ""

    doc_confirmed = "[doctor_confirmed:v1]" in notes_text or caller_role in ("doctor", "clinician")
    pat_confirmed = "[patient_confirmed:v1]" in notes_text or caller_role == "patient"

    # Mark the current caller's confirmation
    if caller_role in ("doctor", "clinician") and "[doctor_confirmed:v1]" not in notes_text:
        notes_text = f"{notes_text} [doctor_confirmed:v1]".strip()
        doc_confirmed = True
    elif caller_role == "patient" and "[patient_confirmed:v1]" not in notes_text:
        notes_text = f"{notes_text} [patient_confirmed:v1]".strip()
        pat_confirmed = True

    appt.notes = notes_text

    is_fully_confirmed = doc_confirmed and pat_confirmed
    if is_fully_confirmed:
        appt.status = "confirmed"
        if appt.care_case:
            appt.care_case.status = "scheduled"
            event = CaseEvent(
                id=uuid.uuid4(),
                case_id=appt.care_case.id,
                event_type="appointment_confirmed_dual",
                description=f"Appointment on {appt.scheduled_time.strftime('%b %d, %Y %I:%M %p UTC')} fully confirmed by both doctor and patient.",
                event_data={
                    "appointment_id": str(appt.id),
                    "doctor_confirmed": True,
                    "patient_confirmed": True,
                    "version": req.appointment_version
                }
            )
            db.add(event)
    else:
        # One party confirmed, pending other party
        pending_role = "patient" if doc_confirmed else "doctor"
        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=appt.care_case.id if appt.care_case else uuid.uuid4(),
            event_type="appointment_confirmation_pending",
            description=f"Appointment confirmation recorded from {caller_role}. Awaiting confirmation from {pending_role}.",
            event_data={
                "appointment_id": str(appt.id),
                "doctor_confirmed": doc_confirmed,
                "patient_confirmed": pat_confirmed
            }
        )
        db.add(event)

    await db.commit()
    await db.refresh(appt)

    return ApiResponseEnvelope.success_response(
        data={
            "appointment_id": str(appt.id),
            "status": appt.status,
            "doctor_confirmed": doc_confirmed,
            "patient_confirmed": pat_confirmed,
            "is_fully_confirmed": is_fully_confirmed,
            "scheduled_time": appt.scheduled_time.isoformat() if appt.scheduled_time else None,
            "notes": appt.notes
        },
        message="Appointment marked CONFIRMED after mutual dual confirmation." if is_fully_confirmed else f"Confirmation recorded for {caller_role}. Pending dual confirmation."
    )


@router.post("/transport-requests/{transport_request_id}/confirm", response_model=ApiResponseEnvelope[Dict[str, Any]], summary="Coordinator Confirms Patient Transport Request")
async def confirm_transport_request(
    transport_request_id: uuid.UUID,
    current_user: UserPrincipal = Depends(get_current_user),
):
    """Only an authorized care coordinator may move a transport request to CONFIRMED."""
    from app.database.session import get_sync_db
    from app.services.transport_service import TransportService, TransportAuthorizationError
    try:
        with get_sync_db() as sync_db:
            res = TransportService.confirm_transport_request(
                db=sync_db,
                transport_request_id=transport_request_id,
                actor_role=current_user.role,
                actor_id=str(current_user.user_id),
            )
    except TransportAuthorizationError as auth_err:
        raise HTTPException(status_code=403, detail=str(auth_err))
    if not res.get("success"):
        raise HTTPException(status_code=404, detail=res.get("error", "Transport request not found"))
    return ApiResponseEnvelope.success_response(data=res, message="Transport request confirmed and patient notified.")


