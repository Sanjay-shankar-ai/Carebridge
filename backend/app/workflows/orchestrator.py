"""
CareBridge Long-Running Workflow Orchestrator (Phase 8)
Orchestrates persistent, event-driven care workflows across days and weeks without
holding HTTP connections open. Integrates PostgreSQL checkpointing, case-isolated threads,
inbound/outbound de-duplication, retry resilience, and structured trace telemetry.
"""

import uuid
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from app.database.session import get_sync_db
from app.models.care_case import CareCase
from app.models.patient import Patient
from app.models.communication import Communication
from app.models.appointment import Appointment
from app.models.referral import Referral
from app.models.event_audit import CaseEvent
from app.workflows.care_workflow import create_carebridge_workflow
from app.workflows.persistence.checkpointer import (
    get_workflow_checkpointer,
    get_thread_config,
    get_latest_checkpoint_state
)
from app.workflows.persistence.idempotency import (
    IdempotencyManager,
    DuplicateMessageFilter
)
from app.workflows.persistence.retry import (
    RetryPolicy,
    RetryConfig,
    WorkflowRetryExhaustedError
)
from app.workflows.persistence.traces import (
    WorkflowTraceLogger,
    NODE_COORDINATOR_EXPLANATIONS
)

logger = logging.getLogger("carebridge.workflows.orchestrator")


class LongRunningWorkflowOrchestrator:
    """Manages long-running, asynchronous, event-driven agent workflows."""

    @classmethod
    def initiate_case_workflow(
        cls,
        case_id: str,
        patient_id: str,
        screening_result_id: str,
        priority: str = "urgent",
        checkpointer = None
    ) -> Dict[str, Any]:
        """
        Initiates the care workflow upon abnormal screening result ingestion.
        Executes initial intake, pathway matching, and initial patient outreach,
        then suspends cleanly at 'acknowledgement_pending' without holding the HTTP request.
        """
        logger.info(f"[Orchestrator] Initiating long-running workflow for case {case_id}")
        start_time = time.time()
        run_id = str(uuid.uuid4())
        thread_config = get_thread_config(case_id, run_id=run_id)

        cp = checkpointer or get_workflow_checkpointer()
        workflow = create_carebridge_workflow(checkpointer=cp)

        initial_state = {
            "case_id": case_id,
            "patient_id": patient_id,
            "screening_result_id": screening_result_id,
            "priority": priority,
            "workflow_phase": "intake_initiated",
            "next_step": "create_case",
            "patient_acknowledged": False,
            "dropoff_risk": False,
            "errors": [],
            "audit_log": []
        }

        # Idempotency key for initial case creation
        idempotency_key = f"initiate_case:{case_id}"

        def _run_initiation():
            return workflow.invoke(initial_state, config=thread_config)

        res = IdempotencyManager.execute_idempotent(idempotency_key, _run_initiation)

        duration_ms = (time.time() - start_time) * 1000.0

        # Log structured execution trace
        with get_sync_db() as db:
            WorkflowTraceLogger.log_node_trace(
                db=db,
                case_id=case_id,
                thread_id=thread_config["configurable"]["thread_id"],
                run_id=run_id,
                workflow_name="closed_loop_care_workflow",
                node_name="initiate_case_workflow",
                step_number=1,
                status="success",
                duration_ms=duration_ms,
                input_data={"case_id": case_id, "priority": priority},
                output_data={"workflow_phase": res.get("workflow_phase"), "next_step": res.get("next_step")},
                coordinator_note="Workflow initiated. Initial outreach drafted and dispatched. Suspended waiting for patient acknowledgement."
            )

        return {
            "case_id": case_id,
            "run_id": run_id,
            "status": "suspended_waiting_for_patient",
            "workflow_phase": res.get("workflow_phase"),
            "next_step": res.get("next_step"),
            "thread_id": thread_config["configurable"]["thread_id"]
        }

    @classmethod
    def resume_on_patient_response(
        cls,
        case_id: str,
        message: str,
        sender: str = "patient",
        channel: str = "sms",
        checkpointer = None
    ) -> Dict[str, Any]:
        """
        Event-driven resumption when an inbound patient message arrives.
        Checks duplicate message filter, resumes the case thread from checkpoint,
        records acknowledgement, runs cognitive reasoning, and updates state.
        """
        logger.info(f"[Orchestrator] Resuming workflow for case {case_id} on patient message")
        start_time = time.time()
        run_id = str(uuid.uuid4())

        # 1. Duplicate Message Detection (drop webhook retries within 120s)
        if DuplicateMessageFilter.is_duplicate_inbound(case_id, sender, message):
            logger.warning(f"[Orchestrator] Suppressing duplicate message for case {case_id}")
            return {
                "case_id": case_id,
                "status": "duplicate_suppressed",
                "message": "Duplicate inbound message dropped"
            }

        thread_config = get_thread_config(case_id, run_id=run_id)
        cp = checkpointer or get_workflow_checkpointer()

        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if not case:
                raise ValueError(f"Case {case_id} not found")

            # 2. Persist Inbound Communication in DB (Source of Truth)
            comm = Communication(
                id=uuid.uuid4(),
                case_id=c_uuid,
                patient_id=case.patient_id,
                sender=sender,
                channel=channel,
                language=case.patient.preferred_language if case.patient else "en",
                content=message,
                acknowledged=True,
                sent_at=datetime.now(timezone.utc)
            )
            db.add(comm)

            # Record timeline event
            event = CaseEvent(
                id=uuid.uuid4(),
                case_id=c_uuid,
                event_type="patient_response_received",
                description=f"Inbound patient message received via {channel}: '{message[:60]}'",
                event_data={"channel": channel, "sender": sender, "message": message},
                timestamp=datetime.now(timezone.utc)
            )
            db.add(event)
            db.commit()

            patient_id_str = str(case.patient_id)

        # 3. Resume the Supervisor Graph using the case thread ID
        from app.agents.graph import create_carebridge_graph
        supervisor = create_carebridge_graph(checkpointer=cp)
        resume_state = {
            "case_id": case_id,
            "patient_id": patient_id_str,
            "inbound_message": message,
            "inbound_channel": channel,
            "patient_context": {},
            "case_context": {},
            "conversation_context": {},
            "intent_analysis": {},
            "coordination_plan": {},
            "pending_tool_calls": [],
            "tool_observations": [],
            "outbound_message": "",
            "outbound_language": "en",
            "replanning_needed": False,
            "iteration_count": 0,
            "max_iterations": 5,
            "requires_human_approval": False,
            "approval_request": {},
            "human_decision": None,
            "audit_entries": [],
            "final_case_status": "in_progress"
        }

        # Execute with retry policy for transient LLM/DB errors
        def _invoke_supervisor():
            return supervisor.invoke(resume_state, config=thread_config)

        res = RetryPolicy.execute_with_retry(
            _invoke_supervisor,
            operation_name=f"supervisor_resume_{case_id}"
        )

        duration_ms = (time.time() - start_time) * 1000.0

        # 4. Log Structured Execution Trace
        with get_sync_db() as db:
            intent = res.get("intent_analysis", {})
            outbound = res.get("outbound_message")

            coord_note = (
                f"Patient responded via {channel}. Primary intent: '{intent.get('primary_intent', 'unknown')}'. "
                f"AI analyzed response and generated guidance in '{res.get('outbound_language', 'en')}'."
            )

            WorkflowTraceLogger.log_node_trace(
                db=db,
                case_id=case_id,
                thread_id=thread_config["configurable"]["thread_id"],
                run_id=run_id,
                workflow_name="carebridge_supervisor",
                node_name="resume_on_patient_response",
                step_number=2,
                status="success",
                duration_ms=duration_ms,
                input_data={"message": message, "channel": channel},
                output_data={"intent": intent, "outbound": outbound},
                coordinator_note=coord_note
            )

        return {
            "case_id": case_id,
            "run_id": run_id,
            "status": "resumed_and_processed",
            "primary_intent": intent.get("primary_intent"),
            "outbound_message": outbound,
            "requires_human_approval": res.get("requires_human_approval", False),
            "thread_id": thread_config["configurable"]["thread_id"]
        }

    @classmethod
    def resume_on_clinic_event(
        cls,
        case_id: str,
        event_type: str,
        event_payload: Dict[str, Any],
        checkpointer = None
    ) -> Dict[str, Any]:
        """
        Event-driven continuation when a clinical or facility event occurs:
        - appointment_attended
        - appointment_no_show
        - appointment_cancelled
        - referral_accepted
        - referral_rejected
        - clinical_signoff
        """
        logger.info(f"[Orchestrator] Resuming workflow for case {case_id} on clinic event: {event_type}")
        start_time = time.time()
        run_id = str(uuid.uuid4())
        thread_config = get_thread_config(case_id, run_id=run_id)

        outcome_status = "event_processed"
        result_details = {}

        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if not case:
                raise ValueError(f"Case {case_id} not found")

            # Route by event type
            if event_type == "appointment_attended":
                appt_id = event_payload.get("appointment_id")
                if appt_id:
                    appt = db.query(Appointment).filter(Appointment.id == uuid.UUID(appt_id)).first()
                    if appt:
                        appt.status = "attended"
                        appt.attendance_recorded_at = datetime.now(timezone.utc)
                case.status = "diagnostic_completed"
                outcome_status = "ready_for_clinical_closure_review"

            elif event_type == "appointment_no_show":
                appt_id = event_payload.get("appointment_id")
                if appt_id:
                    appt = db.query(Appointment).filter(Appointment.id == uuid.UUID(appt_id)).first()
                    if appt:
                        appt.status = "no_show"
                # Automatically trigger Care Recovery Agent
                from app.agents.recovery.agent import run_care_recovery_agent
                recovery_res = run_care_recovery_agent(case_id=case_id)
                outcome_status = f"recovery_triggered_{recovery_res.get('selected_playbook')}"
                result_details = recovery_res

            elif event_type == "appointment_cancelled":
                appt_id = event_payload.get("appointment_id")
                reason = event_payload.get("reason", "patient_requested")
                if appt_id:
                    appt = db.query(Appointment).filter(Appointment.id == uuid.UUID(appt_id)).first()
                    if appt:
                        appt.status = "cancelled"
                        appt.cancellation_reason = reason
                        appt.cancellation_outcome = "reschedule_pending"
                case.status = "recovering"
                outcome_status = "reschedule_coordination_initiated"

            elif event_type == "referral_accepted":
                ref_id = event_payload.get("referral_id")
                if ref_id:
                    ref = db.query(Referral).filter(Referral.id == uuid.UUID(ref_id)).first()
                    if ref:
                        ref.status = "accepted"
                        ref.responded_at = datetime.now(timezone.utc)
                case.status = "referral_accepted"
                outcome_status = "proceed_to_appointment_booking"

            elif event_type == "referral_rejected":
                ref_id = event_payload.get("referral_id")
                rejection_reason = event_payload.get("reason", "clinic_capacity_exceeded")
                if ref_id:
                    ref = db.query(Referral).filter(Referral.id == uuid.UUID(ref_id)).first()
                    if ref:
                        ref.status = "rejected"
                        ref.rejection_reason = rejection_reason
                case.status = "referral_rerouting_needed"
                outcome_status = "coordinator_liaison_required"

            # Record timeline event in DB
            event = CaseEvent(
                id=uuid.uuid4(),
                case_id=c_uuid,
                event_type=f"clinic_{event_type}",
                description=f"Clinic external event '{event_type}' processed for case {case.case_number}",
                event_data=event_payload,
                timestamp=datetime.now(timezone.utc)
            )
            db.add(event)
            db.commit()

        duration_ms = (time.time() - start_time) * 1000.0

        # Log trace
        with get_sync_db() as db:
            WorkflowTraceLogger.log_node_trace(
                db=db,
                case_id=case_id,
                thread_id=thread_config["configurable"]["thread_id"],
                run_id=run_id,
                workflow_name="event_driven_clinic_continuation",
                node_name=f"on_{event_type}",
                step_number=3,
                status="success",
                duration_ms=duration_ms,
                input_data=event_payload,
                output_data={"outcome": outcome_status},
                coordinator_note=f"External clinic event '{event_type}' processed. Outcome: {outcome_status}."
            )

        return {
            "case_id": case_id,
            "run_id": run_id,
            "event_type": event_type,
            "status": outcome_status,
            "details": result_details
        }

    @classmethod
    def retry_failed_workflow(
        cls,
        case_id: str,
        checkpointer = None
    ) -> Dict[str, Any]:
        """
        Failure recovery: Resumes a halted or failed workflow from the last verified checkpoint.
        Uses exponential backoff retry policy.
        """
        logger.info(f"[Orchestrator] Attempting failure recovery for case {case_id}")
        start_time = time.time()
        run_id = str(uuid.uuid4())
        thread_config = get_thread_config(case_id, run_id=run_id)
        cp = checkpointer or get_workflow_checkpointer()

        latest_state = get_latest_checkpoint_state(cp, thread_config["configurable"]["thread_id"])
        if not latest_state:
            # Fall back to initializing recovery agent
            from app.agents.recovery.agent import run_care_recovery_agent
            rec_res = run_care_recovery_agent(case_id=case_id)
            return {
                "case_id": case_id,
                "status": "recovered_via_recovery_agent",
                "details": rec_res
            }

        # Clear any errors in state to allow continuation
        clean_state = dict(latest_state)
        clean_state["errors"] = []
        clean_state["workflow_phase"] = "recovery_resumed"

        workflow = create_carebridge_workflow(checkpointer=cp)

        def _retry_exec():
            return workflow.invoke(clean_state, config=thread_config)

        res = RetryPolicy.execute_with_retry(
            _retry_exec,
            operation_name=f"retry_failed_workflow_{case_id}"
        )

        duration_ms = (time.time() - start_time) * 1000.0

        with get_sync_db() as db:
            WorkflowTraceLogger.log_node_trace(
                db=db,
                case_id=case_id,
                thread_id=thread_config["configurable"]["thread_id"],
                run_id=run_id,
                workflow_name="workflow_failure_recovery",
                node_name="retry_failed_workflow",
                step_number=99,
                status="success",
                duration_ms=duration_ms,
                output_data={"workflow_phase": res.get("workflow_phase")},
                coordinator_note="Workflow recovered from previous failure checkpoint and resumed execution."
            )

        return {
            "case_id": case_id,
            "run_id": run_id,
            "status": "workflow_recovered",
            "workflow_phase": res.get("workflow_phase")
        }

    @classmethod
    def get_coordinator_action_history(
        cls,
        case_id: str
    ) -> Dict[str, Any]:
        """
        Retrieves the complete coordinator-readable action history for a case.
        """
        with get_sync_db() as db:
            history = WorkflowTraceLogger.get_coordinator_action_history(db, case_id)
            return {
                "case_id": case_id,
                "total_actions": len(history),
                "timeline": history
            }
