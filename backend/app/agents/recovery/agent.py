"""
CareBridge Care Recovery Agent (Phase 7)
LangGraph-orchestrated intelligent recovery agent.
Detects stalled journeys, retrieves 8-source context, separates facts from assumptions,
inquires for clarification when cause is unknown, selects tailored playbooks,
executes permitted administrative actions, observes outcomes, and adapts strategy
while maintaining strict Care Coordinator ownership continuity.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from langgraph.graph import StateGraph, START, END

from app.database.session import get_sync_db
from app.models.care_case import CareCase
from app.models.event_audit import CaseEvent, AuditLog
from app.tools.registry import ToolRegistry
from app.agents.recovery.state import RecoveryState
from app.agents.recovery.context_retriever import MultiSourceContextRetriever
from app.agents.recovery.evaluator import FactAssumptionEvaluator
from app.agents.recovery.playbooks import RecoveryPlaybookEngine

logger = logging.getLogger("carebridge.agents.recovery")


class CareRecoveryAgent:
    """Intelligent Care Recovery Agent orchestrating multi-step adaptive re-engagement."""

    # ==========================================================================
    # Graph Nodes
    # ==========================================================================

    @classmethod
    def retrieve_context_node(cls, state: RecoveryState) -> Dict[str, Any]:
        """Node 1: Retrieves 8-dimensional operational context."""
        case_id = state["case_id"]
        logger.info(f"[CareRecoveryAgent] Node 1: Retrieving context for case {case_id}")

        with get_sync_db() as db:
            context = MultiSourceContextRetriever.retrieve_full_context(db, case_id)

            case_hist = context.get("case_history", {})
            patient_pref = context.get("patient_preferences", {})

            # Retrieve existing recovery attempt count from case_context
            case_ctx = case_hist.get("case_context", {})
            current_attempts = case_ctx.get("recovery_attempts", 0)

            return {
                "patient_id": patient_pref.get("patient_id"),
                "context": context,
                "accountable_owner_id": case_hist.get("current_owner_id"),
                "accountable_owner_name": case_hist.get("current_owner_name"),
                "recovery_attempts": current_attempts,
                "actor_role": state.get("actor_role") or "ai_recovery_agent",
                "audit_entries": [],
                "errors": []
            }

    @classmethod
    def detect_stalled_node(cls, state: RecoveryState) -> Dict[str, Any]:
        """Node 2: Detects stalled signals across 7 deterministic dimensions."""
        logger.info("[CareRecoveryAgent] Node 2: Detecting stalled signals")
        context = state.get("context", {})
        is_stalled, signals = FactAssumptionEvaluator.detect_stalled_journey(context)

        return {
            "is_stalled": is_stalled,
            "stalled_signals": signals
        }

    @classmethod
    def eval_facts_vs_assumptions_node(cls, state: RecoveryState) -> Dict[str, Any]:
        """Node 3: Distinguishes known facts from assumptions and identifies need for clarification."""
        logger.info("[CareRecoveryAgent] Node 3: Evaluating facts vs assumptions")
        context = state.get("context", {})
        stalled_signals = state.get("stalled_signals", [])

        eval_result = FactAssumptionEvaluator.evaluate_facts_vs_assumptions(context, stalled_signals)

        return {
            "known_facts": eval_result["known_facts"],
            "assumptions": eval_result["assumptions"],
            "detected_barriers": eval_result["detected_barriers"],
            "needs_clarification": eval_result["needs_clarification"]
        }

    @classmethod
    def determine_recovery_plan_node(cls, state: RecoveryState) -> Dict[str, Any]:
        """Node 4: Selects tailored playbook and structures action plan."""
        logger.info("[CareRecoveryAgent] Node 4: Determining recovery plan")
        context = state.get("context", {})
        sla_ctx = context.get("sla_context", {})
        ref_status = context.get("referral_status", {})
        patient_pref = context.get("patient_preferences", {})

        stalled_signals = state.get("stalled_signals", [])
        known_facts = state.get("known_facts", [])
        assumptions = state.get("assumptions", [])
        detected_barriers = state.get("detected_barriers", [])
        needs_clarification = state.get("needs_clarification", False)
        attempts = state.get("recovery_attempts", 0)

        playbook = RecoveryPlaybookEngine.select_playbook(
            stalled_signals=stalled_signals,
            known_facts=known_facts,
            assumptions=assumptions,
            detected_barriers=detected_barriers,
            needs_clarification=needs_clarification,
            recovery_attempts=attempts,
            sla_breached=sla_ctx.get("is_breached", False),
            is_referral_stalled=ref_status.get("is_stalled", False)
        )

        patient_name = patient_pref.get("full_name", "Patient")
        lang = patient_pref.get("preferred_language", "en")

        action_plan = RecoveryPlaybookEngine.build_action_plan(
            playbook=playbook,
            case_id=state["case_id"],
            patient_id=state.get("patient_id") or patient_pref.get("patient_id"),
            owner_id=state.get("accountable_owner_id"),
            patient_name=patient_name,
            language=lang,
            attempt=attempts,
            barriers=detected_barriers
        )

        clarification_prompt = None
        if needs_clarification or playbook == "clarification_inquiry":
            clarification_prompt = RecoveryPlaybookEngine.generate_patient_message(
                playbook="clarification_inquiry",
                patient_name=patient_name,
                language=lang,
                attempt=attempts
            )

        return {
            "selected_playbook": playbook,
            "action_plan": action_plan,
            "clarification_prompt": clarification_prompt
        }

    @classmethod
    def execute_actions_node(cls, state: RecoveryState) -> Dict[str, Any]:
        """Node 5: Executes permitted administrative actions and verifies Level 3 safety gates."""
        logger.info("[CareRecoveryAgent] Node 5: Executing recovery action plan")
        case_id = state["case_id"]
        action_plan = state.get("action_plan", [])
        executed_actions = []
        audit_entries = list(state.get("audit_entries", []))

        with get_sync_db() as db:
            for item in action_plan:
                tool_name = item.get("tool")
                params = item.get("parameters", {})

                # Safety Check: Level 3 Sensitive Action Gate
                if item.get("requires_approval", False) or item.get("autonomy_level", 1) >= 3:
                    return {
                        "requires_human_authorization": True,
                        "human_approval_request": {
                            "action": item.get("action"),
                            "tool": tool_name,
                            "parameters": params,
                            "reason": "Level 3 clinical or sensitive decision requires human authorization."
                        },
                        "outcome_status": "human_authorization_required"
                    }

                # Autonomous Execution of Level 1 and Level 2 Tools
                res = None
                if tool_name == "send_permitted_communication":
                    res = ToolRegistry.send_patient_message(
                        db=db,
                        case_id=params["case_id"],
                        patient_id=params["patient_id"],
                        message=params["message"],
                        language=params.get("language", "en"),
                        channel=params.get("channel", "sms")
                    )
                elif tool_name == "update_permitted_case_notes":
                    res = ToolRegistry.update_case_notes(
                        db=db,
                        case_id=params["case_id"],
                        note=params["note"]
                    )
                elif tool_name == "create_followup_task":
                    res = ToolRegistry.create_followup_task(
                        db=db,
                        case_id=params["case_id"],
                        title=params["title"],
                        description=params["description"],
                        task_type=params.get("task_type", "recovery_play"),
                        due_date=params["due_date"],
                        assigned_role=params.get("assigned_role", "care_coordinator")
                    )
                elif tool_name == "notify_case_owner":
                    res = ToolRegistry.notify_case_owner(
                        db=db,
                        case_id=params["case_id"],
                        priority=params["priority"],
                        message=params["message"]
                    )
                elif tool_name == "escalate_case":
                    res = ToolRegistry.escalate_case(
                        db=db,
                        case_id=params["case_id"],
                        urgency=params["urgency"],
                        reason=params["reason"]
                    )

                if res:
                    executed_actions.append({
                        "tool": tool_name,
                        "result": res,
                        "executed_at": datetime.now(timezone.utc).isoformat()
                    })

            # Record recovery event in case timeline
            c_uuid = uuid.UUID(case_id)
            playbook = state.get("selected_playbook", "recovery")
            attempts = state.get("recovery_attempts", 0)

            event = CaseEvent(
                id=uuid.uuid4(),
                case_id=c_uuid,
                event_type="care_recovery_cycle_executed",
                description=f"Care Recovery Agent executed playbook '{playbook}' (Attempt #{attempts + 1}).",
                event_data={
                    "playbook": playbook,
                    "attempt": attempts + 1,
                    "barriers": state.get("detected_barriers", []),
                    "needs_clarification": state.get("needs_clarification", False)
                },
                timestamp=datetime.now(timezone.utc)
            )
            db.add(event)

            # Audit entry
            audit = AuditLog(
                id=uuid.uuid4(),
                case_id=c_uuid,
                actor_type="ai_agent",
                actor_id="care_recovery_agent",
                action="EXECUTE_RECOVERY_PLAYBOOK",
                autonomy_level=2,
                rationale=f"Executed recovery strategy '{playbook}' for case {case_id} (Attempt #{attempts + 1})",
                timestamp=datetime.now(timezone.utc)
            )
            db.add(audit)
            db.commit()

            audit_entries.append({
                "audit_id": str(audit.id),
                "action": "EXECUTE_RECOVERY_PLAYBOOK",
                "playbook": playbook
            })

        return {
            "tool_actions_executed": executed_actions,
            "audit_entries": audit_entries,
            "clarification_sent": state.get("needs_clarification", False)
        }

    @classmethod
    def observe_and_adapt_node(cls, state: RecoveryState) -> Dict[str, Any]:
        """Node 6: Observes execution outcomes and adapts recovery strategy."""
        logger.info("[CareRecoveryAgent] Node 6: Observing outcomes and adapting")
        case_id = state["case_id"]
        attempts = state.get("recovery_attempts", 0) + 1
        playbook = state.get("selected_playbook", "")
        needs_clarification = state.get("needs_clarification", False)

        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if case:
                ctx = dict(case.case_context or {})
                ctx["recovery_attempts"] = attempts
                ctx["last_recovery_playbook"] = playbook
                ctx["last_recovery_timestamp"] = datetime.now(timezone.utc).isoformat()
                case.case_context = ctx
                db.commit()

        # Determine outcome status
        if playbook == "emergency_escalation":
            outcome = "escalated"
        elif needs_clarification:
            outcome = "clarification_pending"
        elif attempts >= 3:
            outcome = "recovery_exhausted"
        else:
            outcome = "recovery_in_progress"

        observation = {
            "playbook_executed": playbook,
            "new_attempt_count": attempts,
            "outcome_status": outcome,
            "next_reassessment_hours": 24 if outcome == "clarification_pending" else 12
        }

        return {
            "recovery_attempts": attempts,
            "observation": observation,
            "outcome_status": outcome
        }

    @classmethod
    def notify_coordinator_node(cls, state: RecoveryState) -> Dict[str, Any]:
        """Node 7: Keeps the designated Care Coordinator informed and preserves ownership continuity."""
        logger.info("[CareRecoveryAgent] Node 7: Updating coordinator and maintaining ownership continuity")
        case_id = state["case_id"]
        owner_id = state.get("accountable_owner_id")
        playbook = state.get("selected_playbook")
        outcome = state.get("outcome_status")

        with get_sync_db() as db:
            c_uuid = uuid.UUID(case_id)
            case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
            if case and case.current_owner:
                ToolRegistry.notify_case_owner(
                    db=db,
                    case_id=case_id,
                    priority="urgent" if outcome in ("escalated", "recovery_exhausted") else "normal",
                    message=f"Care Recovery Agent update: Playbook '{playbook}' executed. Status: {outcome}. Ownership retained by {case.current_owner.name}."
                )

        return {
            "coordinator_notified": True
        }


# ==============================================================================
# LangGraph Builder & Entry Point
# ==============================================================================

def create_recovery_graph(checkpointer=None):
    """Compiles the LangGraph StateGraph for Care Recovery reasoning."""
    builder = StateGraph(RecoveryState)

    builder.add_node("retrieve_context", CareRecoveryAgent.retrieve_context_node)
    builder.add_node("detect_stalled", CareRecoveryAgent.detect_stalled_node)
    builder.add_node("eval_facts_vs_assumptions", CareRecoveryAgent.eval_facts_vs_assumptions_node)
    builder.add_node("determine_recovery_plan", CareRecoveryAgent.determine_recovery_plan_node)
    builder.add_node("execute_actions", CareRecoveryAgent.execute_actions_node)
    builder.add_node("observe_and_adapt", CareRecoveryAgent.observe_and_adapt_node)
    builder.add_node("notify_coordinator", CareRecoveryAgent.notify_coordinator_node)

    # Edges
    builder.add_edge(START, "retrieve_context")
    builder.add_edge("retrieve_context", "detect_stalled")

    def route_stalled(state: RecoveryState):
        if not state.get("is_stalled", False):
            return END
        return "eval_facts_vs_assumptions"

    builder.add_conditional_edges("detect_stalled", route_stalled, {
        END: END,
        "eval_facts_vs_assumptions": "eval_facts_vs_assumptions"
    })

    builder.add_edge("eval_facts_vs_assumptions", "determine_recovery_plan")
    builder.add_edge("determine_recovery_plan", "execute_actions")
    builder.add_edge("execute_actions", "observe_and_adapt")
    builder.add_edge("observe_and_adapt", "notify_coordinator")
    builder.add_edge("notify_coordinator", END)

    return builder.compile(checkpointer=checkpointer)


def run_care_recovery_agent(
    case_id: str,
    actor_role: str = "ai_recovery_agent",
    checkpointer=None
) -> Dict[str, Any]:
    """
    Executes the autonomous Care Recovery Agent for a given care case.
    """
    graph = create_recovery_graph(checkpointer=checkpointer)
    initial_state: RecoveryState = {
        "case_id": case_id,
        "actor_role": actor_role,
        "stalled_signals": [],
        "is_stalled": False,
        "context": {},
        "known_facts": [],
        "assumptions": [],
        "needs_clarification": False,
        "clarification_prompt": None,
        "clarification_sent": False,
        "detected_barriers": [],
        "recovery_attempts": 0,
        "selected_playbook": "",
        "action_plan": [],
        "tool_actions_executed": [],
        "requires_human_authorization": False,
        "human_approval_request": None,
        "observation": {},
        "outcome_status": "initialized",
        "coordinator_notified": False,
        "accountable_owner_id": None,
        "accountable_owner_name": None,
        "audit_entries": [],
        "errors": []
    }

    config = {"configurable": {"thread_id": f"recovery-{case_id}"}}
    result = graph.invoke(initial_state, config=config)
    return result
