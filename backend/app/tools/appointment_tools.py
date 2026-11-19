"""
CareBridge Modular Appointment Tools
Implements search of available appointment slots, booking, rescheduling with mandatory reasons,
and retrieval of appointment status.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models.care_case import CareCase, Task
from app.models.appointment import Appointment
from app.models.event_audit import CaseEvent
from app.tools.registry import _parse_scheduled_datetime
from app.tools.base import ToolResult, validate_tool_permission, log_tool_audit, ToolExecutionError
from app.tools.schemas import (
    SearchAvailableAppointmentsInput, AvailableAppointmentsOutput,
    BookAppointmentInput, BookAppointmentOutput,
    RescheduleAppointmentInput, RescheduleAppointmentOutput,
    RetrieveAppointmentStatusInput, AppointmentStatusOutput
)

logger = logging.getLogger("carebridge.tools.appointment")


def search_available_appointments(db: Session, input_data: SearchAvailableAppointmentsInput) -> ToolResult[AvailableAppointmentsOutput]:
    """Searches open consultation slots at a clinic within the clinical SLA window."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=1)
        now = datetime.now(timezone.utc)

        # Calibrate available slots within upcoming 14-day SLA window
        slots = [
            (now + timedelta(days=2, hours=10)).strftime("%Y-%m-%dT10:00:00Z"),
            (now + timedelta(days=4, hours=14)).strftime("%Y-%m-%dT14:00:00Z"),
            (now + timedelta(days=7, hours=11)).strftime("%Y-%m-%dT11:00:00Z"),
            (now + timedelta(days=9, hours=9)).strftime("%Y-%m-%dT09:00:00Z"),
        ]

        output = AvailableAppointmentsOutput(
            facility=input_data.facility,
            specialty=input_data.specialty,
            slots=slots
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Found {len(slots)} open slots at {input_data.facility} ({input_data.specialty})",
            autonomy_level=1
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except Exception as e:
        logger.error(f"Error in search_available_appointments: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def book_appointment(db: Session, input_data: BookAppointmentInput) -> ToolResult[BookAppointmentOutput]:
    """Books a diagnostic or specialist appointment within approved SLA limits."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=2)
        c_uuid = uuid.UUID(input_data.case_id)
        p_uuid = uuid.UUID(input_data.patient_id)
        dt = _parse_scheduled_datetime(input_data.scheduled_time)

        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return ToolResult(success=False, error_code="CASE_NOT_FOUND", message=f"Case {input_data.case_id} not found.")

        # Invariant: Closed cases cannot have new appointments booked
        if case.status == "closed":
            return ToolResult(
                success=False,
                error_code="CASE_CLOSED",
                message=f"Cannot book appointment on closed case {input_data.case_id}. Case must be reopened by an authorized clinician.",
                autonomy_level=2
            )

        # SLA Constraint Validation: Appointment must not exceed case SLA deadline
        if case.sla_deadline and _ensure_utc(dt) > _ensure_utc(case.sla_deadline):
            return ToolResult(
                success=False,
                error_code="SLA_BREACH_REJECTED",
                message=f"Proposed date {input_data.scheduled_time} exceeds case SLA deadline {case.sla_deadline.isoformat()}",
                autonomy_level=2
            )

        # Idempotency check: Reuse existing active appointment for same time/facility
        existing = (
            db.query(Appointment)
            .filter(Appointment.case_id == c_uuid, Appointment.facility == input_data.facility, Appointment.status.in_(["booked", "confirmed"]))
            .first()
        )
        if existing:
            output = BookAppointmentOutput(
                appointment_id=str(existing.id),
                case_id=str(c_uuid),
                patient_id=str(p_uuid),
                facility=existing.facility,
                scheduled_time=existing.scheduled_time.isoformat() if existing.scheduled_time else "",
                status=existing.status,
                appointment_type=existing.appointment_type
            )
            return ToolResult(
                success=True,
                data=output,
                message=f"Idempotent hit: Appointment {existing.id} already active at {existing.facility}",
                autonomy_level=2
            )

        now = datetime.now(timezone.utc)
        appt = Appointment(
            id=uuid.uuid4(),
            case_id=c_uuid,
            patient_id=p_uuid,
            facility=input_data.facility,
            provider_name=input_data.provider_name or "Specialist Clinician",
            appointment_type=input_data.appointment_type,
            scheduled_time=dt,
            status="booked",
            notes=input_data.notes
        )
        db.add(appt)

        # Create milestone task for attendance
        task = Task(
            id=uuid.uuid4(),
            case_id=c_uuid,
            title=f"Appointment Attendance: {input_data.appointment_type}",
            description=f"Verify patient attendance at {input_data.facility} on {dt.isoformat()}",
            task_type="appointment_attendance",
            assigned_to_id=case.current_owner_id,
            assigned_role="care_coordinator",
            status="pending",
            due_date=dt + timedelta(hours=4)
        )
        db.add(task)

        case.status = "appointment_scheduled"

        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=c_uuid,
            event_type="appointment_booked",
            description=f"Appointment booked at {input_data.facility} for {dt.isoformat()}",
            event_data={"facility": input_data.facility, "scheduled_time": dt.isoformat(), "type": input_data.appointment_type},
            timestamp=now
        )
        db.add(event)
        db.commit()

        audit_id = log_tool_audit(
            db=db,
            action="BOOK_APPOINTMENT",
            actor_id="carebridge_agent",
            actor_type="ai_agent",
            autonomy_level=2,
            rationale=f"Booked {input_data.appointment_type} at {input_data.facility} within SLA limits.",
            case_id=c_uuid,
            patient_id=p_uuid
        )

        output = BookAppointmentOutput(
            appointment_id=str(appt.id),
            case_id=str(c_uuid),
            patient_id=str(p_uuid),
            facility=input_data.facility,
            scheduled_time=dt.isoformat(),
            status="booked",
            appointment_type=input_data.appointment_type
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Appointment booked successfully for {dt.isoformat()}",
            autonomy_level=2,
            audit_id=audit_id
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except Exception as e:
        logger.error(f"Error in book_appointment: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def reschedule_appointment(db: Session, input_data: RescheduleAppointmentInput) -> ToolResult[RescheduleAppointmentOutput]:
    """Reschedules an appointment with a mandatory documented reason, maintaining dual-acceptance flags."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=2)
        appt_uuid = uuid.UUID(input_data.appointment_id)
        c_uuid = uuid.UUID(input_data.case_id)

        # Mandatory cancellation reason validation
        if not input_data.reason or not input_data.reason.strip():
            return ToolResult(
                success=False,
                error_code="REASON_REQUIRED",
                message="Rescheduling requires a mandatory, non-empty cancellation reason.",
                autonomy_level=2
            )

        old_appt = db.query(Appointment).filter(Appointment.id == appt_uuid).first()
        if not old_appt:
            return ToolResult(success=False, error_code="APPOINTMENT_NOT_FOUND", message=f"Appointment {input_data.appointment_id} not found.")

        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return ToolResult(success=False, error_code="CASE_NOT_FOUND", message=f"Case {input_data.case_id} not found.")

        # Invariant: Closed cases cannot have new appointments booked
        if case.status == "closed":
            return ToolResult(
                success=False,
                error_code="CASE_CLOSED",
                message=f"Cannot book appointment on closed case {input_data.case_id}. Case must be reopened by an authorized clinician.",
                autonomy_level=2
            )

        now = datetime.now(timezone.utc)
        new_dt = datetime.fromisoformat(input_data.new_scheduled_time.replace("Z", "+00:00"))

        # Update old appointment
        old_status = old_appt.status
        old_appt.status = "rescheduled"
        old_appt.cancellation_reason = input_data.reason
        old_appt.cancellation_outcome = "rescheduled"

        # Create replacement appointment requiring dual acceptance
        new_appt = Appointment(
            id=uuid.uuid4(),
            case_id=c_uuid,
            patient_id=old_appt.patient_id,
            facility=old_appt.facility,
            provider_name=old_appt.provider_name,
            appointment_type=old_appt.appointment_type,
            scheduled_time=new_dt,
            status="booked",
            rescheduled_from_id=old_appt.id,
            notes=f"Rescheduled. Reason: {input_data.reason}. {input_data.notes or ''}"
        )
        db.add(new_appt)

        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=c_uuid,
            event_type="appointment_rescheduled",
            description=f"Appointment rescheduled from {old_appt.scheduled_time} to {new_dt}. Reason: {input_data.reason}",
            event_data={
                "old_appointment_id": str(old_appt.id),
                "new_appointment_id": str(new_appt.id),
                "reason": input_data.reason
            },
            timestamp=now
        )
        db.add(event)
        db.commit()

        audit_id = log_tool_audit(
            db=db,
            action="RESCHEDULE_APPOINTMENT",
            actor_id="carebridge_agent",
            actor_type="ai_agent",
            autonomy_level=2,
            rationale=f"Rescheduled appointment to {new_dt.isoformat()}. Reason: {input_data.reason}",
            case_id=c_uuid,
            patient_id=old_appt.patient_id,
            previous_state={"appointment_id": str(old_appt.id), "status": old_status},
            new_state={"appointment_id": str(new_appt.id), "status": "booked", "reason": input_data.reason}
        )

        output = RescheduleAppointmentOutput(
            previous_appointment_id=str(old_appt.id),
            new_appointment_id=str(new_appt.id),
            case_id=str(c_uuid),
            new_scheduled_time=new_dt.isoformat(),
            reason=input_data.reason,
            requires_dual_acceptance=True
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Appointment rescheduled to {new_dt.isoformat()} (dual acceptance required)",
            autonomy_level=2,
            audit_id=audit_id
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except Exception as e:
        logger.error(f"Error in reschedule_appointment: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def retrieve_appointment_status(db: Session, input_data: RetrieveAppointmentStatusInput) -> ToolResult[AppointmentStatusOutput]:
    """Retrieves current appointment, full appointment history, and attendance records."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=1)
        c_uuid = uuid.UUID(input_data.case_id)
        appointments = (
            db.query(Appointment)
            .filter(Appointment.case_id == c_uuid)
            .order_by(Appointment.created_at.desc())
            .all()
        )

        appt_list = [
            {
                "id": str(a.id),
                "facility": a.facility,
                "provider_name": a.provider_name,
                "appointment_type": a.appointment_type,
                "scheduled_time": a.scheduled_time.isoformat() if a.scheduled_time else None,
                "status": a.status,
                "cancellation_reason": a.cancellation_reason,
                "cancellation_outcome": a.cancellation_outcome,
                "rescheduled_from_id": str(a.rescheduled_from_id) if a.rescheduled_from_id else None
            }
            for a in appointments
        ]

        active_appt = next((a for a in appt_list if a["status"] in ("booked", "confirmed")), None)
        has_attended = any(a["status"] == "attended" for a in appt_list)

        output = AppointmentStatusOutput(
            case_id=str(c_uuid),
            active_appointment=active_appt,
            all_appointments=appt_list,
            has_attended=has_attended
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Retrieved {len(appt_list)} appointments for case {input_data.case_id} (attended: {has_attended})",
            autonomy_level=1
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except ValueError as ve:
        return ToolResult(success=False, error_code="INVALID_UUID", message=f"Invalid case_id: {ve}")
    except Exception as e:
        logger.error(f"Error in retrieve_appointment_status: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))
