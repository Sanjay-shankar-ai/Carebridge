"""
CareBridge Autonomous Care Coordination Service (Phase 6)
Connects the AI cognitive brain with the modular tool ecosystem to provide
adaptive, context-aware care coordination across the complete screening-to-care loop:
Screening Result → Outreach → Acknowledgement → Referral → Appointment → Recovery → Verified Closure
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.database.session import get_sync_db
from app.models.care_case import CareCase
from app.models.patient import Patient
from app.models.event_audit import CaseEvent
from app.tools.registry import ToolRegistry

logger = logging.getLogger("carebridge.services.coordination")


class CareCoordinationService:
    """Orchestrates adaptive autonomous care coordination across all lifecycle events."""

    @classmethod
    def process_patient_message(
        cls,
        case_id: str,
        patient_id: str,
        message: str,
        channel: str = "sms",
        checkpointer = None
    ) -> Dict[str, Any]:
        """
        Processes an incoming patient communication through the cognitive Supervisor Agent.
        Dynamically adapts next actions based on context (questions, barriers, refusals, emergencies).
        """
        logger.info(f"Processing patient message for case {case_id} via {channel}")
        from app.agents.graph import create_carebridge_graph
        graph = create_carebridge_graph(checkpointer=checkpointer)

        thread_id = f"care-thread-{case_id}"
        config = {"configurable": {"thread_id": thread_id}}

        initial_state = {
            "case_id": case_id,
            "patient_id": patient_id,
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
            "final_case_status": "in_progress",
        }

        result = graph.invoke(initial_state, config=config)
        return result

    @classmethod
    def handle_screening_intake(
        cls,
        screening_result_id: str,
        patient_id: str,
        priority: str = "urgent"
    ) -> Dict[str, Any]:
        """Initiates an adaptive care journey upon ingestion of an abnormal screening finding."""
        with get_sync_db() as db:
            return ToolRegistry.create_care_case(
                db=db,
                patient_id=patient_id,
                screening_result_id=screening_result_id,
                priority=priority
            )

    @classmethod
    def handle_delayed_referral(
        cls,
        case_id: str,
        referral_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Investigates delayed referral handoffs and alerts coordinator for active clinic liaison."""
        with get_sync_db() as db:
            ref_status = ToolRegistry.retrieve_referral_information(db=db, case_id=case_id)
            ToolRegistry.notify_case_owner(
                db=db,
                case_id=case_id,
                priority="urgent",
                message="Specialist referral delayed beyond 48h SLA window. Active clinic follow-up required."
            )
            return {
                "case_id": case_id,
                "action": "delayed_referral_alert_dispatched",
                "referral_info": ref_status
            }

    @classmethod
    def handle_missed_appointment(
        cls,
        case_id: str,
        appointment_id: str,
        barrier_reason: str = "appointment_no_show"
    ) -> Dict[str, Any]:
        """Proactively recovers a missed appointment without dropping Care Coordinator ownership."""
        with get_sync_db() as db:
            # 1. Update notes documenting no-show and barrier
            ToolRegistry.update_case_notes(
                db=db,
                case_id=case_id,
                note=f"Patient missed scheduled appointment (id={appointment_id}). Barrier: {barrier_reason}",
                barrier_detected=barrier_reason
            )
            # 2. Formulate recovery play
            recovery = ToolRegistry.propose_recovery_action(
                db=db,
                case_id=case_id,
                dropoff_reasons=[barrier_reason]
            )
            # 3. Create recovery task
            task = ToolRegistry.create_followup_task(
                db=db,
                case_id=case_id,
                title="Care Recovery: Re-engage patient after missed appointment",
                description=f"Engage patient with strategy '{recovery.get('data', {}).get('recommended_strategy')}'.",
                task_type="recovery_play",
                due_date=datetime.now(timezone.utc).strftime("%Y-%m-%dT10:00:00Z"),
                assigned_role="care_coordinator"
            )
            return {
                "case_id": case_id,
                "action": "recovery_play_initiated",
                "recovery_plan": recovery,
                "task": task
            }

    @classmethod
    def recover_stalled_case(
        cls,
        case_id: str,
        actor_role: str = "care_coordinator"
    ) -> Dict[str, Any]:
        """
        Invokes the Phase 7 Care Recovery Agent to evaluate why the care journey is
        stalled, distinguish facts from assumptions, execute appropriate re-engagement,
        and update the accountable Care Coordinator.
        """
        from app.agents.recovery import run_care_recovery_agent
        return run_care_recovery_agent(case_id=case_id, actor_role=actor_role)

    @classmethod
    def handle_closure_verification_request(
        cls,
        case_id: str,
        evidence_type: str,
        evidence_summary: str,
        clinician_id: str
    ) -> Dict[str, Any]:
        """Evaluates 5-point checklist and submits evidence for clinician verification (Level 3 Gate)."""
        with get_sync_db() as db:
            checklist = ToolRegistry.get_case_closure_requirements(db=db, case_id=case_id)
            verification = ToolRegistry.request_closure_verification(
                db=db,
                case_id=case_id,
                evidence_type=evidence_type,
                evidence_summary=evidence_summary,
                clinician_id=clinician_id
            )
            return {
                "case_id": case_id,
                "closure_checklist": checklist,
                "verification_request": verification
            }

    @classmethod
    def handle_emergency_escalation(
        cls,
        case_id: str,
        urgency: str,
        reason: str
    ) -> Dict[str, Any]:
        """Escalates acute emergencies or patient care refusals to qualified clinical supervision."""
        with get_sync_db() as db:
            return ToolRegistry.escalate_case(
                db=db,
                case_id=case_id,
                urgency=urgency,
                reason=reason
            )
