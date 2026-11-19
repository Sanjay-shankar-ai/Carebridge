"""
CareBridge Modular Referral Tools
Implements creation of referral requests, checking referral status, and retrieving referral information.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models.care_case import CareCase, Task
from app.models.patient import Patient, Consent
from app.models.referral import Referral
from app.models.event_audit import CaseEvent
from app.workflows.rules import _ensure_utc
from app.tools.base import ToolResult, validate_tool_permission, log_tool_audit, ToolExecutionError
from app.tools.schemas import (
    CreateReferralRequestInput, ReferralRequestOutput,
    CheckReferralStatusInput, ReferralStatusOutput,
    RetrieveReferralInformationInput, ReferralInformationOutput
)

logger = logging.getLogger("carebridge.tools.referral")


def create_referral_request(db: Session, input_data: CreateReferralRequestInput) -> ToolResult[ReferralRequestOutput]:
    """Creates and dispatches an inter-facility referral request with 48h SLA deadline."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=2)
        c_uuid = uuid.UUID(input_data.case_id)
        p_uuid = uuid.UUID(input_data.patient_id)

        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return ToolResult(success=False, error_code="CASE_NOT_FOUND", message=f"Case {input_data.case_id} not found.")

        # Consent enforcement: verify patient has active consent for referral data sharing
        patient = db.query(Patient).filter(Patient.id == p_uuid).first()
        if patient and patient.consents:
            has_referral_consent = any(
                c.status == "active" and ("referral" in c.scope or "sharing" in c.scope)
                for c in patient.consents
            )
            if not has_referral_consent:
                return ToolResult(
                    success=False,
                    error_code="CONSENT_MISSING",
                    message="Patient has not granted active consent for cross-facility referral sharing.",
                    autonomy_level=2
                )

        # Idempotency check: Reuse existing active referral for same target facility if exists
        existing = (
            db.query(Referral)
            .filter(Referral.case_id == c_uuid, Referral.target_facility == input_data.target_facility, Referral.status.in_(["sent", "accepted"]))
            .first()
        )
        if existing:
            output = ReferralRequestOutput(
                referral_id=str(existing.id),
                case_id=str(c_uuid),
                patient_id=str(p_uuid),
                target_facility=existing.target_facility,
                specialty=existing.specialty,
                status=existing.status,
                acceptance_deadline=existing.acceptance_deadline.isoformat() if existing.acceptance_deadline else ""
            )
            return ToolResult(
                success=True,
                data=output,
                message=f"Idempotent hit: Active referral already exists for {input_data.target_facility}",
                autonomy_level=2
            )

        now = datetime.now(timezone.utc)
        deadline = now + timedelta(hours=48)

        referral = Referral(
            id=uuid.uuid4(),
            case_id=c_uuid,
            patient_id=p_uuid,
            referring_provider="CareBridge AI Screening Network",
            target_facility=input_data.target_facility,
            specialty=input_data.specialty,
            reason_for_referral=input_data.reason,
            status="sent",
            acceptance_deadline=deadline
        )
        db.add(referral)

        # Create referral tracking task
        task = Task(
            id=uuid.uuid4(),
            case_id=c_uuid,
            title=f"Track referral acceptance: {input_data.target_facility}",
            description=f"Monitor acceptance of referral for {input_data.specialty} within 48h SLA.",
            task_type="referral_routing",
            assigned_to_id=case.current_owner_id,
            assigned_role="care_coordinator",
            status="pending",
            due_date=deadline
        )
        db.add(task)

        case.status = "referral_coordinated"

        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=c_uuid,
            event_type="referral_created",
            description=f"Referral dispatched to {input_data.target_facility} ({input_data.specialty})",
            event_data={"facility": input_data.target_facility, "specialty": input_data.specialty},
            timestamp=now
        )
        db.add(event)
        db.commit()

        audit_id = log_tool_audit(
            db=db,
            action="CREATE_REFERRAL",
            actor_id="carebridge_agent",
            actor_type="ai_agent",
            autonomy_level=2,
            rationale=f"Dispatched referral to {input_data.target_facility} with 48h SLA deadline.",
            case_id=c_uuid,
            patient_id=p_uuid
        )

        output = ReferralRequestOutput(
            referral_id=str(referral.id),
            case_id=str(c_uuid),
            patient_id=str(p_uuid),
            target_facility=input_data.target_facility,
            specialty=input_data.specialty,
            status="sent",
            acceptance_deadline=deadline.isoformat()
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Referral dispatched to {input_data.target_facility}",
            autonomy_level=2,
            audit_id=audit_id
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except Exception as e:
        logger.error(f"Error in create_referral_request: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def check_referral_status(db: Session, input_data: CheckReferralStatusInput) -> ToolResult[ReferralStatusOutput]:
    """Checks the status, recipient facility, and SLA deadline of a referral."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=1)
        r_uuid = uuid.UUID(input_data.referral_id)
        referral = db.query(Referral).filter(Referral.id == r_uuid).first()
        if not referral:
            return ToolResult(success=False, error_code="REFERRAL_NOT_FOUND", message=f"Referral {input_data.referral_id} not found.")

        now = datetime.now(timezone.utc)
        is_overdue = False
        if referral.acceptance_deadline and referral.status == "sent":
            is_overdue = _ensure_utc(referral.acceptance_deadline) < now

        output = ReferralStatusOutput(
            referral_id=str(referral.id),
            case_id=str(referral.case_id),
            status=referral.status,
            target_facility=referral.target_facility,
            specialty=referral.specialty,
            acceptance_deadline=referral.acceptance_deadline.isoformat() if referral.acceptance_deadline else None,
            responded_at=referral.responded_at.isoformat() if referral.responded_at else None,
            is_overdue=is_overdue
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Referral status: {referral.status} (overdue: {is_overdue})",
            autonomy_level=1
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except ValueError as ve:
        return ToolResult(success=False, error_code="INVALID_UUID", message=f"Invalid referral_id: {ve}")
    except Exception as e:
        logger.error(f"Error in check_referral_status: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def retrieve_referral_information(db: Session, input_data: RetrieveReferralInformationInput) -> ToolResult[ReferralInformationOutput]:
    """Retrieves all active and historical referrals associated with a care case."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=1)
        c_uuid = uuid.UUID(input_data.case_id)
        referrals = db.query(Referral).filter(Referral.case_id == c_uuid).order_by(Referral.created_at.desc()).all()

        ref_list = [
            {
                "id": str(r.id),
                "target_facility": r.target_facility,
                "specialty": r.specialty,
                "status": r.status,
                "reason_for_referral": r.reason_for_referral,
                "rejection_reason": r.rejection_reason,
                "acceptance_deadline": r.acceptance_deadline.isoformat() if r.acceptance_deadline else None,
                "responded_at": r.responded_at.isoformat() if r.responded_at else None
            }
            for r in referrals
        ]

        active_ref = next((r for r in ref_list if r["status"] in ("sent", "accepted")), None)

        output = ReferralInformationOutput(
            case_id=str(c_uuid),
            active_referral=active_ref,
            all_referrals=ref_list,
            referral_count=len(ref_list)
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Retrieved {len(ref_list)} referrals for case {input_data.case_id}",
            autonomy_level=1
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except ValueError as ve:
        return ToolResult(success=False, error_code="INVALID_UUID", message=f"Invalid case_id: {ve}")
    except Exception as e:
        logger.error(f"Error in retrieve_referral_information: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))
