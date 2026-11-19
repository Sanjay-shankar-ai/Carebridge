"""
CareBridge Relational Models Export
Consolidates core relational entities for SQLAlchemy and Alembic migrations.
"""

from app.models.user import User
from app.models.patient import Patient, Consent
from app.models.screening import ScreeningResult
from app.models.owner import CaseOwner
from app.models.care_case import CareCase, Task, CaseOwnershipHistory
from app.models.referral import Referral
from app.models.appointment import Appointment
from app.models.communication import Communication, ConversationSession
from app.models.event_audit import CaseEvent, AuditLog
from app.models.closure import ClosureEvidence
from app.models.workflow_trace import WorkflowExecutionTrace
from app.models.notification import Notification
from app.models.doctor_assignment import DoctorAssignment
from app.models.case_lifecycle_stage import CaseLifecycleStage

__all__ = [
    "User",
    "Patient",
    "Consent",
    "ScreeningResult",
    "CaseOwner",
    "CareCase",
    "Task",
    "CaseOwnershipHistory",
    "Referral",
    "Appointment",
    "Communication",
    "ConversationSession",
    "CaseEvent",
    "AuditLog",
    "ClosureEvidence",
    "WorkflowExecutionTrace",
    "Notification",
    "DoctorAssignment",
    "CaseLifecycleStage",
]
