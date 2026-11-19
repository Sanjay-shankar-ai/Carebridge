"""
CareBridge Agent Tool Ecosystem - Base Infrastructure
Provides typed execution envelopes, permission validation, audit logging,
and safe execution wrappers for all modular tools.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import TypeVar, Generic, Optional, Dict, Any, List
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.models.event_audit import AuditLog

logger = logging.getLogger("carebridge.tools")

T = TypeVar("T")


class ToolResult(BaseModel, Generic[T]):
    """Standardized strongly-typed response envelope for all CareBridge tools."""
    success: bool = Field(description="Indicates whether tool execution succeeded")
    data: Optional[T] = Field(default=None, description="Typed output payload on success")
    message: str = Field(description="Human-readable result or status summary")
    error_code: Optional[str] = Field(default=None, description="Error identifier on failure")
    autonomy_level: int = Field(default=1, description="Autonomy classification: 1=Autonomous, 2=Constrained, 3=Human Gate")
    audit_id: Optional[str] = Field(default=None, description="UUID of associated audit log entry if recorded")


class ToolExecutionError(Exception):
    """Domain exception raised during tool permission or operational failures."""
    def __init__(self, message: str, error_code: str = "EXECUTION_ERROR", autonomy_level: int = 1):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.autonomy_level = autonomy_level


# Allowed role hierarchies and privileges (Strictly PATIENT, DOCTOR, CARE_COORDINATOR)
VALID_ROLES = {
    "ai_coordinator",
    "care_coordinator",
    "clinician",
    "doctor",
    "primary_physician",
    "specialist",
    "nurse_navigator",
    "system",
}

LEVEL_PERMISSIONS = {
    1: {"ai_coordinator", "care_coordinator", "clinician", "doctor", "primary_physician", "specialist", "nurse_navigator", "system"},
    2: {"ai_coordinator", "care_coordinator", "clinician", "doctor", "primary_physician", "specialist", "nurse_navigator", "system"},
    3: {"clinician", "doctor", "primary_physician", "specialist"},  # Clinical human-in-the-loop gate (physicians only)
}


def validate_tool_permission(
    actor_role: Optional[str],
    autonomy_level: int = 1,
    allowed_roles: Optional[List[str]] = None
) -> None:
    """
    Validates that the caller's role possesses permissions to execute the tool
    under the specified autonomy level.
    """
    role = (actor_role or "ai_coordinator").lower().strip()
    if role not in VALID_ROLES:
        raise ToolExecutionError(
            f"Unauthorized: Role '{actor_role}' is not a recognized CareBridge actor.",
            error_code="INVALID_ROLE",
            autonomy_level=autonomy_level
        )

    permitted = allowed_roles if allowed_roles else LEVEL_PERMISSIONS.get(autonomy_level, set())
    if role not in permitted:
        raise ToolExecutionError(
            f"Permission Denied: Role '{role}' lacks Level {autonomy_level} execution rights for this tool.",
            error_code="PERMISSION_DENIED",
            autonomy_level=autonomy_level
        )


def log_tool_audit(
    db: Session,
    action: str,
    actor_id: str,
    actor_type: str,
    autonomy_level: int,
    rationale: str,
    case_id: Optional[uuid.UUID] = None,
    patient_id: Optional[uuid.UUID] = None,
    previous_state: Optional[Dict[str, Any]] = None,
    new_state: Optional[Dict[str, Any]] = None,
    commit: bool = True
) -> Optional[str]:
    """Records an immutable audit entry in the PostgreSQL/SQLite database."""
    try:
        audit = AuditLog(
            id=uuid.uuid4(),
            case_id=case_id,
            patient_id=patient_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            autonomy_level=autonomy_level,
            previous_state=previous_state,
            new_state=new_state,
            rationale=rationale,
            timestamp=datetime.now(timezone.utc)
        )
        db.add(audit)
        if commit:
            db.commit()
        else:
            db.flush()
        return str(audit.id)
    except Exception as e:
        logger.error(f"Failed to record audit log for action {action}: {e}", exc_info=True)
        return None
