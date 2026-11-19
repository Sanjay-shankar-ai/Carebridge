"""
CareBridge Modular Recovery Tools
Implements follow-up task creation, stalled case identification,
proposing recovery strategies, and emergency case escalation.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.care_case import CareCase, Task
from app.models.event_audit import CaseEvent
from app.models.patient import Patient
from app.workflows.rules import determine_recovery_strategy, _ensure_utc
from app.tools.base import ToolResult, validate_tool_permission, log_tool_audit, ToolExecutionError
from app.tools.schemas import (
    CreateFollowupTaskInput, FollowupTaskOutput,
    IdentifyStalledCasesInput, StalledCasesOutput, StalledCaseItem,
    ProposeRecoveryActionInput, RecoveryActionOutput,
    EscalateCaseInput, EscalateCaseOutput
)

logger = logging.getLogger("carebridge.tools.recovery")


def create_followup_task(db: Session, input_data: CreateFollowupTaskInput) -> ToolResult[FollowupTaskOutput]:
    """Creates an actionable coordination or surveillance task along the care journey."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=2)
        c_uuid = uuid.UUID(input_data.case_id)
        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return ToolResult(success=False, error_code="CASE_NOT_FOUND", message=f"Case {input_data.case_id} not found.")

        dt = datetime.fromisoformat(input_data.due_date.replace("Z", "+00:00"))
        owner_id = uuid.UUID(input_data.assigned_to_id) if input_data.assigned_to_id else case.current_owner_id

        task = Task(
            id=uuid.uuid4(),
            case_id=c_uuid,
            patient_id=case.patient_id,
            title=input_data.title,
            description=input_data.description,
            task_type=input_data.task_type,
            assigned_role=input_data.assigned_role or "care_coordinator",
            assigned_to_id=owner_id,
            status="pending",
            due_date=dt
        )
        db.add(task)
        db.commit()

        output = FollowupTaskOutput(
            task_id=str(task.id),
            case_id=str(c_uuid),
            title=task.title,
            status="pending",
            due_date=dt.isoformat(),
            assigned_role=task.assigned_role
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Follow-up task '{task.title}' created successfully",
            autonomy_level=2
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except Exception as e:
        logger.error(f"Error in create_followup_task: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def identify_stalled_cases(db: Session, input_data: IdentifyStalledCasesInput) -> ToolResult[StalledCasesOutput]:
    """Identifies care cases exceeding the inactivity threshold without recorded progress."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=1)
        now = datetime.now(timezone.utc)
        threshold = input_data.days_threshold

        query = db.query(CareCase).filter(CareCase.status.notin_(["closed", "care_completed"]))
        if input_data.case_id:
            c_uuid = uuid.UUID(input_data.case_id)
            query = query.filter(CareCase.id == c_uuid)

        active_cases = query.all()
        stalled_items: List[StalledCaseItem] = []

        for case in active_cases:
            latest_event = (
                db.query(CaseEvent)
                .filter(CaseEvent.case_id == case.id)
                .order_by(CaseEvent.timestamp.desc())
                .first()
            )
            last_activity = latest_event.timestamp if latest_event else case.updated_at
            days_inactive = (now - _ensure_utc(last_activity)).total_seconds() / 86400.0

            if days_inactive >= threshold:
                owner_name = case.current_owner.name if case.current_owner else "Unassigned"
                rec = (
                    f"Notify coordinator {owner_name} to engage patient or trigger recovery play."
                    if case.current_owner else "Immediate administrative assignment required."
                )
                stalled_items.append(
                    StalledCaseItem(
                        case_id=str(case.id),
                        case_number=case.case_number,
                        days_inactive=round(days_inactive, 1),
                        last_activity_at=last_activity.isoformat(),
                        accountable_owner=owner_name,
                        recommendation=rec
                    )
                )

        output = StalledCasesOutput(
            stalled=len(stalled_items) > 0,
            stalled_case_count=len(stalled_items),
            cases=stalled_items
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Identified {len(stalled_items)} stalled case(s) (threshold: {threshold} days)",
            autonomy_level=1
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except Exception as e:
        logger.error(f"Error in identify_stalled_cases: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def propose_recovery_action(db: Session, input_data: ProposeRecoveryActionInput) -> ToolResult[RecoveryActionOutput]:
    """Analyzes dropoff barriers and formulates a structured proactive recovery strategy."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=1)
        c_uuid = uuid.UUID(input_data.case_id)
        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return ToolResult(success=False, error_code="CASE_NOT_FOUND", message=f"Case {input_data.case_id} not found.")

        ctx = dict(case.case_context or {})
        attempts = int(ctx.get("recovery_attempts", 0))
        reasons = input_data.dropoff_reasons or list(ctx.get("inferred_barriers", []))
        if not reasons:
            reasons = ["unacknowledged_outreach"]

        patient = db.query(Patient).filter(Patient.id == case.patient_id).first()
        lang = patient.preferred_language if patient else "en"

        strategy = determine_recovery_strategy(reasons, attempts, lang)
        escalate_rec = attempts >= 2 or case.sla_status == "breached"

        action_plan = (
            f"Recovery Play #{attempts + 1}: Strategy '{strategy}' selected for barriers: {', '.join(reasons)}. "
            f"Deliver proactive outreach in language '{lang}' with coordinator oversight."
        )

        output = RecoveryActionOutput(
            case_id=str(c_uuid),
            recommended_strategy=strategy,
            action_plan=action_plan,
            recovery_attempts=attempts,
            escalation_recommended=escalate_rec
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Recommended recovery strategy: '{strategy}'",
            autonomy_level=1
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except Exception as e:
        logger.error(f"Error in propose_recovery_action: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def escalate_case(db: Session, input_data: EscalateCaseInput) -> ToolResult[EscalateCaseOutput]:
    """Escalates an at-risk, stalled, or unowned case to the human coordinator/supervisor queue."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=2)
        c_uuid = uuid.UUID(input_data.case_id)
        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return ToolResult(success=False, error_code="CASE_NOT_FOUND", message=f"Case {input_data.case_id} not found.")

        now = datetime.now(timezone.utc)
        is_unowned = case.current_owner_id is None
        new_status = "UNASSIGNED_ESCALATED" if is_unowned else "ESCALATED"

        case.status = new_status
        case.priority = "critical"

        # Create urgent escalation task
        task = Task(
            id=uuid.uuid4(),
            case_id=c_uuid,
            title=f"URGENT ESCALATION: {input_data.reason[:60]}",
            description=input_data.reason,
            task_type="clinical_review",
            assigned_to_id=case.current_owner_id,
            assigned_role="care_coordinator",
            status="pending",
            due_date=now + timedelta(hours=12)
        )
        db.add(task)

        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=c_uuid,
            event_type="case_escalated",
            description=f"Case escalated to {new_status}. Urgency: {input_data.urgency}. Reason: {input_data.reason}",
            event_data={"status": new_status, "urgency": input_data.urgency, "reason": input_data.reason},
            timestamp=now
        )
        db.add(event)
        db.commit()

        audit_id = log_tool_audit(
            db=db,
            action="ESCALATE_CASE",
            actor_id="carebridge_agent",
            actor_type="ai_agent",
            autonomy_level=2,
            rationale=f"Escalated case {case.case_number} to {new_status}: {input_data.reason}",
            case_id=c_uuid,
            patient_id=case.patient_id
        )

        output = EscalateCaseOutput(
            case_id=str(c_uuid),
            status=new_status,
            priority="critical",
            escalation_reason=input_data.reason,
            escalated_at=now.isoformat()
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Case escalated to {new_status} (priority: critical)",
            autonomy_level=2,
            audit_id=audit_id
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except Exception as e:
        logger.error(f"Error in escalate_case: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))
