"""
CareBridge Structured Workflow Execution Traces & Coordinator Observability (Phase 8)
Logs granular execution traces per node and generates human-readable action histories
for Care Coordinators and clinical supervisors to audit autonomous workflows.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.workflow_trace import WorkflowExecutionTrace
from app.models.event_audit import CaseEvent
from app.core.correlation import get_correlation_id, get_workflow_id

logger = logging.getLogger("carebridge.workflows.traces")


NODE_COORDINATOR_EXPLANATIONS = {
    "create_case": "AI ingested abnormal screening finding and initialized care case with assigned clinical SLA.",
    "select_approved_pathway": "AI matched screening finding to approved clinical protocol and established diagnostic workup requirements.",
    "draft_patient_communication": "AI drafted personalized, compassionate notification in patient's preferred language.",
    "record_acknowledgement": "AI recorded patient acknowledgement of outreach message and verified patient comprehension.",
    "coordinate_referral": "AI dispatched referral request to specialist facility with 48h acceptance SLA.",
    "coordinate_appointment": "AI coordinated and scheduled diagnostic appointment within SLA deadline window.",
    "monitor_case": "AI evaluated care milestones, inactivity clocks, and SLA compliance.",
    "detect_dropoff": "AI evaluated patient adherence, missed visits, unacknowledged communications, and social barriers.",
    "recovery_agent": "AI formulated and executed proactive recovery play to re-engage patient without dropping coordinator ownership.",
    "escalation": "AI escalated case to urgent supervisory queue due to SLA risk or recovery exhaustion.",
    "verify_closure": "AI evaluated mandatory closed-loop care criteria and prepared case for clinical sign-off.",
    # Supervisor nodes
    "retrieve_context": "AI loaded 8-dimensional patient, case, referral, and SLA context.",
    "interpret_intent": "AI analyzed inbound message intent, emotion, and care barriers.",
    "reason_and_plan": "AI formulated goal-directed coordination plan and selected authorized tools.",
    "safety_gatekeeper": "AI evaluated autonomy boundaries (Level 1/2 Autonomous vs Level 3 Human Authorization).",
    "execute_tools": "AI executed authorized coordination actions against backend database.",
    "reflect_and_update": "AI evaluated action outcomes, checked for errors, and updated case memory.",
    "generate_response": "AI dispatched empathetic patient guidance on designated communication channel."
}


class WorkflowTraceLogger:
    """Logs structured workflow execution traces and renders coordinator-readable action histories."""

    @classmethod
    def summarize_dict(cls, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Creates a compact JSON summary of state dicts to prevent unbounded trace storage.
        Sensitive keys and JWT tokens are redacted before the summary is persisted."""
        if not data:
            return {}

        # Redact sensitive keys / JWT tokens before summarising
        from app.core.redaction import redact_dict as _redact
        data = _redact(data)

        summary = {}
        for k, v in data.items():
            if k in ("patient_context", "case_context", "conversation_context", "context"):
                summary[k] = f"<{len(v) if isinstance(v, dict) else type(v).__name__} keys>"
            elif isinstance(v, (str, int, float, bool)) or v is None:
                summary[k] = v
            elif isinstance(v, list):
                summary[k] = f"<list of {len(v)} items>"
            elif isinstance(v, dict):
                summary[k] = {sub_k: str(sub_v)[:40] for sub_k, sub_v in list(v.items())[:5]}
            else:
                summary[k] = str(v)[:60]
        return summary

    @classmethod
    def log_node_trace(
        cls,
        db: Session,
        case_id: Optional[str],
        thread_id: str,
        run_id: str,
        workflow_name: str,
        node_name: str,
        step_number: int,
        status: str,
        duration_ms: float,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        coordinator_note: Optional[str] = None,
        correlation_id: str = "",
        actor_id: str = "",
        workflow_id: str = "",
        conversation_id: str = "",
        role: str = "",
        patient_id: Optional[Any] = None,
        intent: str = "",
        routing_decision: str = "",
        selected_agent: str = "",
        tool_name: str = "",
        domain_action: str = "",
        db_result: str = "ok",
        event_id: str = "",
        notification_id: str = "",
        lifecycle_transition: str = "",
        retry_count: int = 0,
    ) -> WorkflowExecutionTrace:
        """Persists a structured execution trace in the database."""
        c_uuid = uuid.UUID(str(case_id)) if case_id and len(str(case_id)) == 36 else None
        p_uuid = uuid.UUID(str(patient_id)) if patient_id and len(str(patient_id)) == 36 else None

        # Build coordinator-readable explanation
        note = coordinator_note
        if not note:
            default_expl = NODE_COORDINATOR_EXPLANATIONS.get(node_name)
            if default_expl:
                note = default_expl
            else:
                note = f"Executed step '{node_name}' in workflow '{workflow_name}'."

        # Fall back to contextvars if not explicitly supplied
        effective_corr_id = correlation_id or get_correlation_id()
        effective_wf_id = workflow_id or get_workflow_id()

        trace = WorkflowExecutionTrace(
            id=uuid.uuid4(),
            case_id=c_uuid,
            thread_id=thread_id,
            run_id=run_id,
            workflow_name=workflow_name,
            node_name=node_name,
            step_number=step_number,
            status=status,
            duration_ms=round(duration_ms, 2),
            input_summary=cls.summarize_dict(input_data),
            output_summary=cls.summarize_dict(output_data),
            error_message=error_message,
            coordinator_note=note,
            executed_at=datetime.now(timezone.utc),
            correlation_id=effective_corr_id or None,
            workflow_id=effective_wf_id or None,
            conversation_id=conversation_id or None,
            actor_id=actor_id or None,
            role=role or None,
            patient_id=p_uuid,
            intent=intent or None,
            routing_decision=routing_decision or None,
            selected_agent=selected_agent or None,
            tool_name=tool_name or None,
            domain_action=domain_action or None,
            db_result=db_result or "ok",
            event_id=event_id or None,
            notification_id=notification_id or None,
            lifecycle_transition=lifecycle_transition or None,
            retry_count=retry_count,
        )
        db.add(trace)
        db.commit()
        return trace

    @classmethod
    def get_coordinator_action_history(
        cls,
        db: Session,
        case_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Retrieves a human-readable timeline for the Care Coordinator dashboard.
        Combines workflow traces with CaseEvent records.
        """
        c_uuid = uuid.UUID(case_id) if isinstance(case_id, str) and len(case_id) == 36 else None
        if not c_uuid:
            return []

        traces = (
            db.query(WorkflowExecutionTrace)
            .filter(WorkflowExecutionTrace.case_id == c_uuid)
            .order_by(WorkflowExecutionTrace.executed_at.asc())
            .limit(limit)
            .all()
        )

        history = []
        for t in traces:
            history.append({
                "trace_id": str(t.id),
                "timestamp": t.executed_at.isoformat(),
                "workflow": t.workflow_name,
                "node": t.node_name,
                "status": t.status,
                "step_number": t.step_number,
                "duration_ms": t.duration_ms,
                "coordinator_explanation": t.coordinator_note,
                "has_error": t.status == "failed" or bool(t.error_message),
                "error_details": t.error_message
            })

        return history
