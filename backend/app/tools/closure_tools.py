"""
CareBridge Modular Closure Tools
Implements closure evidence retrieval, 5-point checklist evaluation,
and submission of clinical verification requests (Level 3 Human-in-the-Loop Gate).
AI must NEVER independently approve clinical closure.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models.care_case import CareCase, Task
from app.models.closure import ClosureEvidence
from app.models.owner import CaseOwner
from app.models.event_audit import CaseEvent
from app.tools.base import ToolResult, validate_tool_permission, log_tool_audit, ToolExecutionError
from app.tools.schemas import (
    RetrieveClosureEvidenceInput, ClosureEvidenceOutput, ClosureEvidenceItem,
    RequestClosureVerificationInput, RequestClosureVerificationOutput
)

logger = logging.getLogger("carebridge.tools.closure")


def retrieve_closure_evidence(db: Session, input_data: RetrieveClosureEvidenceInput) -> ToolResult[ClosureEvidenceOutput]:
    """Retrieves all clinical closure evidence, pathology reports, and the 5-point closure checklist."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=1)
        c_uuid = uuid.UUID(input_data.case_id)
        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return ToolResult(success=False, error_code="CASE_NOT_FOUND", message=f"Case {input_data.case_id} not found.")

        evidences = (
            db.query(ClosureEvidence)
            .filter(ClosureEvidence.case_id == c_uuid)
            .order_by(ClosureEvidence.created_at.desc())
            .all()
        )

        evidence_items = [
            ClosureEvidenceItem(
                id=str(e.id),
                evidence_type=e.evidence_type,
                evidence_summary=e.evidence_summary,
                verifying_clinician_id=str(e.verifying_clinician_id) if e.verifying_clinician_id else None,
                is_verified=e.is_verified,
                verified_at=e.verified_at.isoformat() if e.verified_at else None
            )
            for e in evidences
        ]

        # 5-point checklist evaluation
        pending_tasks = db.query(Task).filter(Task.case_id == c_uuid, Task.status.in_(["pending", "in_progress"])).count()
        has_evidence = len(evidences) > 0
        has_verified_signoff = any(e.is_verified for e in evidences)
        barriers = (case.case_context or {}).get("inferred_barriers", [])
        has_owner = case.current_owner_id is not None

        checklist = {
            "all_coordination_tasks_completed": pending_tasks == 0,
            "closure_evidence_recorded": has_evidence,
            "clinical_verification_signed": has_verified_signoff,
            "exceptions_resolved": len(barriers) == 0 or case.status != "recovering",
            "accountable_owner_present": has_owner,
        }

        output = ClosureEvidenceOutput(
            case_id=str(c_uuid),
            evidences=evidence_items,
            has_verified_signoff=has_verified_signoff,
            checklist_status=checklist
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Retrieved {len(evidence_items)} closure evidence record(s). Verified sign-off: {has_verified_signoff}",
            autonomy_level=1
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except ValueError as ve:
        return ToolResult(success=False, error_code="INVALID_UUID", message=f"Invalid case_id: {ve}")
    except Exception as e:
        logger.error(f"Error in retrieve_closure_evidence: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def request_closure_verification(db: Session, input_data: RequestClosureVerificationInput) -> ToolResult[RequestClosureVerificationOutput]:
    """
    Submits clinical findings for human clinician review and sign-off (Level 3 Gate).
    CRITICAL INVARIANT: AI must NEVER independently approve clinical closure.
    """
    try:
        # Level 3 operation: requires physician or coordinator request
        validate_tool_permission(input_data.actor_role, autonomy_level=2)
        c_uuid = uuid.UUID(input_data.case_id)
        doc_uuid = uuid.UUID(input_data.clinician_id)

        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return ToolResult(success=False, error_code="CASE_NOT_FOUND", message=f"Case {input_data.case_id} not found.")

        clinician = db.query(CaseOwner).filter(CaseOwner.id == doc_uuid).first()
        if not clinician or clinician.role not in ("specialist", "primary_physician"):
            return ToolResult(
                success=False,
                error_code="INVALID_CLINICIAN",
                message=f"User {input_data.clinician_id} is not an authorized physician for closure sign-off."
            )

        now = datetime.now(timezone.utc)
        evidence = ClosureEvidence(
            id=uuid.uuid4(),
            case_id=c_uuid,
            evidence_type=input_data.evidence_type,
            evidence_summary=input_data.evidence_summary,
            verifying_clinician_id=doc_uuid,
            is_verified=False  # Mandatory Level 3 Human Gate!
        )
        db.add(evidence)

        # Create urgent clinical sign-off task for the physician
        task = Task(
            id=uuid.uuid4(),
            case_id=c_uuid,
            title="Clinical Closure Verification Sign-off",
            description=f"Review clinical evidence ({input_data.evidence_type}) and sign off on case closure: {input_data.evidence_summary[:100]}",
            task_type="clinical_review",
            assigned_to_id=doc_uuid,
            assigned_role="clinician",
            status="pending",
            due_date=now + timedelta(days=2)
        )
        db.add(task)

        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=c_uuid,
            event_type="closure_verification_requested",
            description=f"Closure verification requested from Dr. {clinician.name}",
            event_data={"evidence_id": str(evidence.id), "clinician_id": str(doc_uuid), "type": input_data.evidence_type},
            timestamp=now
        )
        db.add(event)
        db.commit()

        audit_id = log_tool_audit(
            db=db,
            action="PROPOSE_CLOSURE_VERIFICATION",
            actor_id="carebridge_agent",
            actor_type="ai_agent",
            autonomy_level=3,
            rationale=f"Proposed clinical closure. Clinical sign-off assigned to Dr. {clinician.name}",
            case_id=c_uuid
        )

        output = RequestClosureVerificationOutput(
            evidence_id=str(evidence.id),
            case_id=str(c_uuid),
            clinician_id=str(doc_uuid),
            is_verified=False,
            requires_human_approval=True,
            message=f"Closure evidence recorded. Pending formal clinical sign-off by Dr. {clinician.name}."
        )
        return ToolResult(
            success=True,
            data=output,
            message="Closure verification submitted for clinical authorization",
            autonomy_level=3,
            audit_id=audit_id
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except Exception as e:
        logger.error(f"Error in request_closure_verification: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))
