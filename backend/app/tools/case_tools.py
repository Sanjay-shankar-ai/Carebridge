"""
CareBridge Modular Case Tools
Implements care case creation, retrieval of details & events, updating notes,
and assigning administrative ownership with continuous ownership history.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models.care_case import CareCase, CaseOwnershipHistory, Task
from app.models.owner import CaseOwner
from app.models.screening import ScreeningResult
from app.models.event_audit import CaseEvent
from app.workflows.rules import calculate_sla_deadline, match_clinical_pathway
from app.tools.base import ToolResult, validate_tool_permission, log_tool_audit, ToolExecutionError
from app.tools.schemas import (
    CreateCareCaseInput, CareCaseOutput,
    RetrieveCaseDetailsInput, CaseDetailsOutput,
    RetrieveCaseEventsInput, CaseEventsOutput, CaseEventItem,
    UpdateCaseNotesInput, UpdateCaseNotesOutput,
    AssignAdministrativeOwnershipInput, AssignOwnershipOutput
)

logger = logging.getLogger("carebridge.tools.case")


def create_care_case(db: Session, input_data: CreateCareCaseInput) -> ToolResult[CareCaseOutput]:
    """Creates a new care case from an abnormal screening result. Idempotent on screening_result_id."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=2)
        p_uuid = uuid.UUID(input_data.patient_id)
        s_uuid = uuid.UUID(input_data.screening_result_id)

        # 1. Idempotency check: Return existing case if already created for this screening result
        existing_case = db.query(CareCase).filter(CareCase.screening_result_id == s_uuid).first()
        if existing_case:
            output = CareCaseOutput(
                case_id=str(existing_case.id),
                case_number=existing_case.case_number,
                patient_id=str(existing_case.patient_id),
                screening_result_id=str(existing_case.screening_result_id),
                current_owner_id=str(existing_case.current_owner_id) if existing_case.current_owner_id else None,
                status=existing_case.status,
                priority=existing_case.priority,
                clinical_pathway=existing_case.clinical_pathway,
                sla_deadline=existing_case.sla_deadline.isoformat() if existing_case.sla_deadline else None,
                sla_status=existing_case.sla_status
            )
            return ToolResult(
                success=True,
                data=output,
                message=f"Idempotent hit: CareCase {existing_case.case_number} already exists.",
                autonomy_level=2
            )

        # 2. Screening result validation
        screening = db.query(ScreeningResult).filter(ScreeningResult.id == s_uuid).first()
        if not screening:
            return ToolResult(
                success=False,
                error_code="SCREENING_NOT_FOUND",
                message=f"ScreeningResult {input_data.screening_result_id} not found."
            )

        now = datetime.now(timezone.utc)
        priority = input_data.priority or screening.urgency_level or "standard"
        deadline = calculate_sla_deadline(priority, now)

        # 3. Pathway selection
        pathway = input_data.clinical_pathway or match_clinical_pathway(
            screening_type=screening.screening_type,
            finding_code=screening.finding_code,
            summary=screening.finding_summary
        )

        # 4. Resolve designated coordinator
        owner_uuid = None
        if input_data.initial_owner_id:
            try:
                owner_uuid = uuid.UUID(input_data.initial_owner_id)
            except ValueError:
                pass
        if not owner_uuid:
            default_coordinator = db.query(CaseOwner).filter(CaseOwner.role == "care_coordinator", CaseOwner.is_active.is_(True)).first()
            if default_coordinator:
                owner_uuid = default_coordinator.id

        # 5. Create CareCase
        case_id = uuid.uuid4()
        case_number = f"CASE-{uuid.uuid4().hex[:8].upper()}"
        new_case = CareCase(
            id=case_id,
            case_number=case_number,
            patient_id=p_uuid,
            screening_result_id=s_uuid,
            current_owner_id=owner_uuid,
            status="result_received",
            priority=priority,
            clinical_pathway=pathway,
            sla_start_time=now,
            sla_deadline=deadline,
            sla_status="normal",
            case_context={"notes": [], "inferred_barriers": [], "recovery_attempts": 0}
        )
        db.add(new_case)
        db.flush()

        # 6. Seed initial ownership history
        if owner_uuid:
            history = CaseOwnershipHistory(
                id=uuid.uuid4(),
                case_id=case_id,
                previous_owner_id=None,
                new_owner_id=owner_uuid,
                transferred_by="create_care_case_tool",
                reason="Initial intake assignment",
                effective_from=now,
                is_active=True
            )
            db.add(history)

        # 7. Audit log
        audit_id = log_tool_audit(
            db=db,
            action="CREATE_CARE_CASE",
            actor_id="carebridge_agent",
            actor_type="ai_agent",
            autonomy_level=2,
            rationale=f"Created case {case_number} under pathway '{pathway}' with deadline {deadline.isoformat()}",
            case_id=case_id,
            patient_id=p_uuid
        )

        output = CareCaseOutput(
            case_id=str(case_id),
            case_number=case_number,
            patient_id=str(p_uuid),
            screening_result_id=str(s_uuid),
            current_owner_id=str(owner_uuid) if owner_uuid else None,
            status=new_case.status,
            priority=priority,
            clinical_pathway=pathway,
            sla_deadline=deadline.isoformat(),
            sla_status="normal"
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Created care case {case_number}",
            autonomy_level=2,
            audit_id=audit_id
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except Exception as e:
        logger.error(f"Error in create_care_case: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def retrieve_case_details(db: Session, input_data: RetrieveCaseDetailsInput) -> ToolResult[CaseDetailsOutput]:
    """Retrieves full case details, accountable owner, SLA deadlines, and barriers."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=1)
        c_uuid = uuid.UUID(input_data.case_id)
        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return ToolResult(success=False, error_code="CASE_NOT_FOUND", message=f"Case {input_data.case_id} not found.")

        ctx = case.case_context or {}
        output = CaseDetailsOutput(
            case_id=str(case.id),
            case_number=case.case_number,
            patient_id=str(case.patient_id),
            current_owner_id=str(case.current_owner_id) if case.current_owner_id else None,
            current_owner_name=case.current_owner.name if case.current_owner else "Unassigned",
            status=case.status,
            priority=case.priority,
            clinical_pathway=case.clinical_pathway,
            sla_deadline=case.sla_deadline.isoformat() if case.sla_deadline else None,
            sla_status=case.sla_status,
            is_closed=case.status in ("closed", "care_completed"),
            inferred_barriers=list(ctx.get("inferred_barriers", [])),
            recovery_attempts=int(ctx.get("recovery_attempts", 0))
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Retrieved case {case.case_number} details",
            autonomy_level=1
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except ValueError as ve:
        return ToolResult(success=False, error_code="INVALID_UUID", message=f"Invalid case_id: {ve}")
    except Exception as e:
        logger.error(f"Error in retrieve_case_details: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def retrieve_case_events(db: Session, input_data: RetrieveCaseEventsInput) -> ToolResult[CaseEventsOutput]:
    """Retrieves chronological timeline events recorded for a case."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=1)
        c_uuid = uuid.UUID(input_data.case_id)
        events = (
            db.query(CaseEvent)
            .filter(CaseEvent.case_id == c_uuid)
            .order_by(CaseEvent.timestamp.desc())
            .limit(input_data.limit)
            .all()
        )
        event_items = [
            CaseEventItem(
                id=str(e.id),
                event_type=e.event_type,
                description=e.description,
                event_data=e.event_data or {},
                timestamp=e.timestamp.isoformat()
            )
            for e in events
        ]
        output = CaseEventsOutput(
            case_id=str(c_uuid),
            events=event_items,
            total_events=len(event_items)
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Retrieved {len(event_items)} events for case {input_data.case_id}",
            autonomy_level=1
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except ValueError as ve:
        return ToolResult(success=False, error_code="INVALID_UUID", message=f"Invalid case_id: {ve}")
    except Exception as e:
        logger.error(f"Error in retrieve_case_events: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def update_case_notes(db: Session, input_data: UpdateCaseNotesInput) -> ToolResult[UpdateCaseNotesOutput]:
    """Appends progress note and flags patient barriers into case memory."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=1)
        c_uuid = uuid.UUID(input_data.case_id)
        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return ToolResult(success=False, error_code="CASE_NOT_FOUND", message=f"Case {input_data.case_id} not found.")

        now = datetime.now(timezone.utc)
        ctx = dict(case.case_context or {})
        notes = list(ctx.get("notes", []))
        timestamp_str = now.strftime("%Y-%m-%d %H:%M UTC")
        notes.append(f"[{timestamp_str}] {input_data.note}")
        ctx["notes"] = notes

        if input_data.barrier_detected:
            barriers = list(ctx.get("inferred_barriers", []))
            if input_data.barrier_detected not in barriers:
                barriers.append(input_data.barrier_detected)
            ctx["inferred_barriers"] = barriers

            event = CaseEvent(
                id=uuid.uuid4(),
                case_id=c_uuid,
                event_type="barrier_identified",
                description=f"Barrier flagged: {input_data.barrier_detected}",
                event_data={"barrier": input_data.barrier_detected, "note": input_data.note},
                timestamp=now
            )
            db.add(event)

        case.case_context = ctx
        db.commit()

        audit_id = log_tool_audit(
            db=db,
            action="UPDATE_CASE_NOTES",
            actor_id=input_data.actor_id or "supervisor_agent",
            actor_type="ai_agent",
            autonomy_level=1,
            rationale=f"Appended progress note. Barrier: {input_data.barrier_detected}",
            case_id=c_uuid,
            patient_id=case.patient_id
        )

        output = UpdateCaseNotesOutput(
            case_id=str(c_uuid),
            note_added=input_data.note,
            barrier_detected=input_data.barrier_detected,
            updated_barriers=ctx.get("inferred_barriers", [])
        )
        return ToolResult(
            success=True,
            data=output,
            message="Case notes updated successfully",
            autonomy_level=1,
            audit_id=audit_id
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except ValueError as ve:
        return ToolResult(success=False, error_code="INVALID_UUID", message=f"Invalid case_id: {ve}")
    except Exception as e:
        logger.error(f"Error in update_case_notes: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def assign_administrative_ownership(db: Session, input_data: AssignAdministrativeOwnershipInput) -> ToolResult[AssignOwnershipOutput]:
    """Assigns an accountable Care Coordinator to a case and logs continuous ownership history."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=2)
        c_uuid = uuid.UUID(input_data.case_id)
        owner_uuid = uuid.UUID(input_data.new_owner_id)

        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return ToolResult(success=False, error_code="CASE_NOT_FOUND", message=f"Case {input_data.case_id} not found.")

        new_owner = db.query(CaseOwner).filter(CaseOwner.id == owner_uuid).first()
        if not new_owner:
            return ToolResult(success=False, error_code="OWNER_NOT_FOUND", message=f"Coordinator {input_data.new_owner_id} not found.")

        prev_owner_id = case.current_owner_id
        now = datetime.now(timezone.utc)

        # Deactivate previous active history records
        active_histories = (
            db.query(CaseOwnershipHistory)
            .filter(CaseOwnershipHistory.case_id == c_uuid, CaseOwnershipHistory.is_active.is_(True))
            .all()
        )
        for h in active_histories:
            h.is_active = False
            h.effective_to = now

        # Add new ownership history
        new_hist = CaseOwnershipHistory(
            id=uuid.uuid4(),
            case_id=c_uuid,
            previous_owner_id=prev_owner_id,
            new_owner_id=owner_uuid,
            transferred_by=input_data.assigned_by,
            reason=input_data.reason,
            effective_from=now,
            is_active=True
        )
        db.add(new_hist)

        case.current_owner_id = owner_uuid
        if case.status == "UNASSIGNED_ESCALATED":
            case.status = "recovering"

        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=c_uuid,
            event_type="case_owner_assigned",
            description=f"Case assigned to {new_owner.name}. Reason: {input_data.reason}",
            event_data={"owner_id": str(owner_uuid), "assigned_by": input_data.assigned_by, "reason": input_data.reason},
            timestamp=now
        )
        db.add(event)
        db.commit()

        audit_id = log_tool_audit(
            db=db,
            action="ASSIGN_CASE_OWNER",
            actor_id=input_data.assigned_by,
            actor_type="human_coordinator" if "coordinator" in input_data.actor_role else "ai_agent",
            autonomy_level=2,
            rationale=f"Assigned owner {new_owner.name}. Reason: {input_data.reason}",
            case_id=c_uuid,
            patient_id=case.patient_id,
            previous_state={"owner_id": str(prev_owner_id) if prev_owner_id else None},
            new_state={"owner_id": str(owner_uuid), "owner_name": new_owner.name}
        )

        output = AssignOwnershipOutput(
            case_id=str(c_uuid),
            new_owner_id=str(owner_uuid),
            owner_name=new_owner.name,
            assigned_by=input_data.assigned_by,
            reason=input_data.reason,
            effective_from=now.isoformat()
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Case ownership assigned to {new_owner.name}",
            autonomy_level=2,
            audit_id=audit_id
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except ValueError as ve:
        return ToolResult(success=False, error_code="INVALID_UUID", message=f"Invalid UUID: {ve}")
    except Exception as e:
        logger.error(f"Error in assign_administrative_ownership: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))
