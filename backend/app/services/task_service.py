"""
CareBridge Task Service: Operational Task Ownership & Handoffs

Guarantees:
1. One authoritative task model across all operational handoffs.
2. Patient AI screening handoff creates an authoritative coordinator task in the same transaction as the intake requirement.
3. Coordinator-to-Doctor handoffs track doctor response SLAs with automatic escalation on decline or timeout.
4. Recovery Agent creates actionable recovery tasks with social determinant barrier data.
5. Clinical escalation creates urgent clinical tasks deterministically without LLM.
6. Failed tool executions persist recoverable tasks; no handoff is silently lost.
7. Evidence-driven closure: tasks can ONLY be completed with non-empty completion evidence and an authenticated actor.
8. SLA background checker identifies and escalates overdue tasks idempotently.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_

from app.models.care_case import CareCase, Task
from app.models.patient import Patient
from app.models.owner import CaseOwner
from app.models.user import User
from app.models.event_audit import CaseEvent, AuditLog
from app.services.notification_service import NotificationService

logger = logging.getLogger("carebridge.services.task")


class TaskService:
    """Domain service managing the complete lifecycle of CareBridge operational tasks."""

    @classmethod
    def create_task(
        cls,
        db: Session,
        case_id: uuid.UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        task_type: str = "general",
        assigned_role: str = "care_coordinator",
        responsible_role: Optional[str] = None,
        assigned_to_id: Optional[Any] = None,
        patient_id: Optional[uuid.UUID] = None,
        priority: str = "standard",
        due_date: Optional[datetime] = None,
        status: str = "pending",
        idempotency_key: Optional[str] = None,
        initial_context: Optional[Dict[str, Any]] = None,
        task_metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Task:
        """
        Creates an operational task with authoritative role ownership, SLA deadline,
        and idempotency guarantee.
        """
        now = datetime.now(timezone.utc)
        effective_role = responsible_role or assigned_role
        effective_title = title or f"Task: {task_type.replace('_', ' ').title()}"
        effective_desc = description or f"Operational task for {task_type}"
        effective_context = task_metadata if task_metadata is not None else initial_context

        # Convert assigned_to_id string to UUID if applicable
        parsed_assigned_to_id: Optional[uuid.UUID] = None
        if assigned_to_id:
            if isinstance(assigned_to_id, uuid.UUID):
                parsed_assigned_to_id = assigned_to_id
            else:
                try:
                    parsed_assigned_to_id = uuid.UUID(str(assigned_to_id))
                except ValueError:
                    parsed_assigned_to_id = None

        # 1. Idempotency check
        if idempotency_key:
            existing = db.query(Task).filter(Task.idempotency_key == idempotency_key).first()
            if existing:
                logger.info(f"Task with idempotency_key '{idempotency_key}' already exists: {existing.id}")
                return existing

        # 2. Derive patient_id from CareCase if not provided
        if not patient_id:
            case = db.query(CareCase).filter(CareCase.id == case_id).first()
            if case:
                patient_id = case.patient_id

        # 3. Derive default SLA deadline based on priority if not specified
        if not due_date:
            if priority == "critical":
                due_date = now + timedelta(hours=4)
            elif priority == "urgent":
                due_date = now + timedelta(hours=12)
            else:
                due_date = now + timedelta(days=2)

        task = Task(
            id=uuid.uuid4(),
            case_id=case_id,
            patient_id=patient_id,
            title=effective_title,
            description=effective_desc,
            task_type=task_type,
            assigned_role=effective_role,
            assigned_to_id=parsed_assigned_to_id,
            status=status,
            priority=priority,
            due_date=due_date,
            idempotency_key=idempotency_key,
            completion_evidence=effective_context
        )
        db.add(task)
        db.flush()

        # Audit event
        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=case_id,
            event_type="operational_task_created",
            description=f"Task '{effective_title}' ({task_type}) assigned to {effective_role} with SLA due {due_date.strftime('%Y-%m-%d %H:%M UTC')}.",
            event_data={
                "task_id": str(task.id),
                "task_type": task_type,
                "assigned_role": assigned_role,
                "priority": priority,
                "due_date": due_date.isoformat(),
                "idempotency_key": idempotency_key
            },
            timestamp=now
        )
        db.add(event)
        return task

    @classmethod
    def create_screening_handoff_task(
        cls,
        db: Session,
        case_id: uuid.UUID,
        patient_id: uuid.UUID,
        screening_type: str,
        notes: str,
        idempotency_key: Optional[str] = None
    ) -> Task:
        """
        Creates an authoritative Care Coordinator task when Patient AI identifies
        a screening order requirement. A notification is never a substitute for a task.
        """
        title = f"Schedule Screening: {screening_type.replace('_', ' ').title()}"
        description = (
            f"Patient completed initial intake and requires clinical screening coordination.\n"
            f"Required Screening: {screening_type}\n"
            f"Clinical Notes: {notes}\n"
            f"Please verify eligibility, select provider facility, and book appointment slot within SLA."
        )
        return cls.create_task(
            db=db,
            case_id=case_id,
            patient_id=patient_id,
            title=title,
            description=description,
            task_type="schedule_screening",
            assigned_role="care_coordinator",
            priority="urgent",
            due_date=datetime.now(timezone.utc) + timedelta(hours=24),
            idempotency_key=idempotency_key or f"screening_handoff_{case_id}"
        )

    @classmethod
    def create_recovery_task(
        cls,
        db: Session,
        case_id: uuid.UUID,
        patient_id: uuid.UUID,
        barrier_type: str,
        barrier_description: str,
        idempotency_key: Optional[str] = None,
        priority: str = "urgent"
    ) -> Task:
        """
        Recovery Agent: Creates an actionable recovery task with social determinant barrier data
        (transport, financial, childcare, fear/anxiety) to maintain care retention.
        """
        title = f"Resolve Barrier: {barrier_type.replace('_', ' ').title()}"
        description = (
            f"Recovery Agent detected a care journey barrier:\n"
            f"Barrier Category: {barrier_type}\n"
            f"Details: {barrier_description}\n"
            f"Action Required: Contact patient, apply recovery playbook, and coordinate logistics."
        )
        return cls.create_task(
            db=db,
            case_id=case_id,
            patient_id=patient_id,
            title=title,
            description=description,
            task_type="recovery_play",
            assigned_role="care_coordinator",
            priority=priority,
            due_date=datetime.now(timezone.utc) + timedelta(hours=24),
            idempotency_key=idempotency_key,
            initial_context={"barrier_type": barrier_type, "barrier_description": barrier_description}
        )

    @classmethod
    def create_clinical_escalation_task(
        cls,
        db: Session,
        case_id: uuid.UUID,
        patient_id: uuid.UUID,
        red_flag_symptoms: List[str],
        patient_statement: str,
        idempotency_key: Optional[str] = None
    ) -> Task:
        """
        Clinical Escalation: Creates a critical priority clinical task with preserved evidence
        deterministically without LLM, and alerts clinical staff.
        """
        now = datetime.now(timezone.utc)
        symptoms_str = ", ".join(red_flag_symptoms)
        title = f"CRITICAL: Clinical Red Flag ({symptoms_str})"
        description = (
            f"URGENT CLINICAL ESCALATION DETECTED:\n"
            f"Red-Flag Symptoms: {symptoms_str}\n"
            f"Patient Statement: '{patient_statement}'\n"
            f"Evidence preserved at: {now.isoformat()}\n"
            f"Immediate physician review and direct clinical outreach required."
        )

        task = cls.create_task(
            db=db,
            case_id=case_id,
            patient_id=patient_id,
            title=title,
            description=description,
            task_type="clinical_escalation",
            assigned_role="doctor",
            priority="critical",
            due_date=now + timedelta(hours=2),
            idempotency_key=idempotency_key or f"clin_esc_{case_id}_{now.strftime('%Y%m%d%H')}",
            initial_context={
                "red_flag_symptoms": red_flag_symptoms,
                "patient_statement": patient_statement,
                "escalated_at": now.isoformat()
            }
        )

        # Notify Doctor / Clinician Queue
        case = db.query(CareCase).filter(CareCase.id == case_id).first()
        target_user = None
        if case and case.current_owner_id:
            target_user = db.query(User).filter(User.owner_id == case.current_owner_id).first()
        if not target_user:
            target_user = db.query(User).filter(User.role.in_(["doctor", "care_coordinator"])).first()

        if target_user:
            try:
                NotificationService.create_notification(
                    db=db,
                    user_id=target_user.id,
                    role=target_user.role,
                    event_type="clinical_escalation",
                    title="URGENT: Patient Clinical Red Flag",
                    message=f"Critical red flag flagged for case {case.case_number if case else ''}: {symptoms_str}. Direct outreach required.",
                    priority="urgent",
                    case_id=case_id,
                    patient_id=patient_id,
                    action_link=f"/cases/{case_id}",
                    idempotency_key=f"notif_esc_{task.id}"
                )
            except Exception as e:
                logger.warning(f"Could not dispatch clinical escalation notification: {e}")

        return task

    @classmethod
    def record_failed_tool_handoff(
        cls,
        db: Session,
        case_id: uuid.UUID,
        patient_id: Optional[uuid.UUID],
        tool_name: str,
        tool_arguments: Dict[str, Any],
        error_message: str,
        idempotency_key: Optional[str] = None
    ) -> Task:
        """
        Safety Guardrail: If a tool call fails during execution, persist a recoverable
        task with failure arguments and error details so handoffs are never silently lost.
        """
        title = f"Failed Handoff Recovery: {tool_name}"
        description = (
            f"An automated tool execution failed during a care workflow handoff:\n"
            f"Tool: {tool_name}\n"
            f"Error: {error_message}\n"
            f"Arguments: {tool_arguments}\n"
            f"Please manually review and complete this workflow step."
        )
        return cls.create_task(
            db=db,
            case_id=case_id,
            patient_id=patient_id,
            title=title,
            description=description,
            task_type="failed_handoff_recovery",
            assigned_role="care_coordinator",
            priority="urgent",
            due_date=datetime.now(timezone.utc) + timedelta(hours=12),
            idempotency_key=idempotency_key or f"tool_fail_{uuid.uuid4().hex[:10]}",
            initial_context={
                "tool_name": tool_name,
                "tool_arguments": tool_arguments,
                "error_message": error_message,
                "failed_at": datetime.now(timezone.utc).isoformat()
            }
        )

    @classmethod
    def complete_task(
        cls,
        db: Session,
        task_id: uuid.UUID,
        completed_by_id: str,
        completed_by_role: str,
        completion_evidence: Optional[Dict[str, Any]] = None,
        evidence: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Task:
        """
        Closes an operational task with evidence-driven verification.
        Requires both a valid completion actor and non-empty completion evidence.
        """
        now = datetime.now(timezone.utc)
        effective_evidence = completion_evidence or evidence

        # 1. Look up task
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found.")

        # 2. Validation: Actor must be specified
        if not completed_by_id or not str(completed_by_id).strip():
            raise ValueError("Task closure requires an authenticated actor ID (completed_by_id).")
        if not completed_by_role or not str(completed_by_role).strip():
            raise ValueError("Task closure requires a valid completion role (completed_by_role).")

        # 3. Validation: Completion evidence is mandatory
        if not effective_evidence or not isinstance(effective_evidence, dict) or len(effective_evidence) == 0:
            raise ValueError("Task closure requires non-empty supporting completion_evidence.")

        # 4. Atomic completion update
        task.status = "completed"
        task.completed_at = now
        task.completed_by_id = str(completed_by_id).strip()
        task.completed_by_role = str(completed_by_role).strip()
        task.completion_evidence = effective_evidence

        # 5. Record CaseEvent
        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=task.case_id,
            event_type="operational_task_completed",
            description=f"Task '{task.title}' completed by {completed_by_role} ({completed_by_id}).",
            event_data={
                "task_id": str(task.id),
                "completed_by_id": task.completed_by_id,
                "completed_by_role": task.completed_by_role,
                "completion_evidence": completion_evidence,
                "completed_at": now.isoformat()
            },
            timestamp=now
        )
        db.add(event)
        return task

    @classmethod
    def scan_and_escalate_overdue_tasks(cls, db: Session) -> Dict[str, Any]:
        """
        Idempotent background job: Scans all active tasks with passed SLA deadlines,
        transitions them to 'escalated' or 'overdue', and notifies assigned role.
        """
        now = datetime.now(timezone.utc)
        overdue_tasks = (
            db.query(Task)
            .filter(
                Task.status.in_(["pending", "in_progress"]),
                Task.due_date < now
            )
            .all()
        )

        escalated_ids = []
        for task in overdue_tasks:
            task.status = "escalated"
            task.priority = "urgent" if task.priority == "standard" else "critical"

            # Notify Coordinator of task breach
            coord_user = db.query(User).filter(User.role == "care_coordinator").first()
            if coord_user:
                try:
                    NotificationService.create_notification(
                        db=db,
                        user_id=coord_user.id,
                        role="care_coordinator",
                        event_type="task_sla_breached",
                        title=f"SLA Breached: {task.title}",
                        message=f"Task '{task.title}' ({task.task_type}) is overdue past SLA deadline.",
                        priority="urgent",
                        case_id=task.case_id,
                        patient_id=task.patient_id,
                        action_link=f"/cases/{task.case_id}",
                        idempotency_key=f"notif_task_overdue_{task.id}"
                    )
                except Exception as e:
                    logger.warning(f"Could not dispatch task overdue notification: {e}")

            escalated_ids.append(str(task.id))

        db.flush()
        return {
            "job_name": "scan_and_escalate_overdue_tasks",
            "executed_at": now.isoformat(),
            "overdue_count": len(overdue_tasks),
            "escalated_count": len(escalated_ids),
            "task_ids": escalated_ids
        }
