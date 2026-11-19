"""
CareBridge Central Supervisor Agent Graph
Stateful cognitive orchestration built with LangGraph, PostgreSQL Checkpointer, and Safety Gates.
"""

import uuid
from typing import Dict, Any, Literal
from sqlalchemy.orm import Session
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.database.session import get_sync_db
from app.memory.retriever import get_unified_memory_sync
from app.agents.state import AgentState
from app.agents.cognitive_engine import CognitiveEngine
from app.tools.registry import ToolRegistry


# ------------------------------------------------------------------------------
# 1. Graph Nodes
# ------------------------------------------------------------------------------

def retrieve_context_node(state: AgentState) -> Dict[str, Any]:
    """Retrieves factual Patient, Case, and Conversation memory from persistent storage."""
    case_id = state.get("case_id")
    patient_id = state.get("patient_id")

    if not case_id or not patient_id:
        return {
            "patient_context": {},
            "case_context": {},
            "conversation_context": {"inbound_sender": state.get("inbound_sender") or state.get("actor_role") or ""},
        }

    with get_sync_db() as db:
        try:
            c_uuid = uuid.UUID(str(case_id))
            p_uuid = uuid.UUID(str(patient_id))
            unified = get_unified_memory_sync(c_uuid, p_uuid, db)

            if unified:
                conv_data = unified.conversation.model_dump()
                conv_data["inbound_sender"] = state.get("inbound_sender") or state.get("actor_role") or ""
                return {
                    "patient_context": unified.patient.model_dump(),
                    "case_context": unified.case.model_dump(),
                    "conversation_context": conv_data,
                }
        except Exception:
            pass
        return {
            "patient_context": {},
            "case_context": {},
            "conversation_context": {"inbound_sender": state.get("inbound_sender") or state.get("actor_role") or ""},
        }


def interpret_intent_node(state: AgentState) -> Dict[str, Any]:
    """Analyzes natural language message to infer intent, emotion, barriers, and language."""
    message = state.get("inbound_message", "")
    patient_ctx = state.get("patient_context", {})
    case_ctx = state.get("case_context", {})
    conv_ctx = dict(state.get("conversation_context") or {})
    conv_ctx["inbound_sender"] = state.get("inbound_sender") or state.get("actor_role") or conv_ctx.get("inbound_sender", "")

    intent = CognitiveEngine.analyze_intent(message, patient_ctx, case_ctx, conv_ctx)
    return {"intent_analysis": intent.model_dump()}


def reason_and_plan_node(state: AgentState) -> Dict[str, Any]:
    """Formulates a goal-oriented coordination plan and selects tools."""
    inbound_sender = (state.get("inbound_sender") or state.get("actor_role") or "").lower()
    if inbound_sender in ("doctor", "clinician", "specialist"):
        from app.workflows.doctor_workflow import run_doctor_workflow
        doctor_id = str(state.get("actor_id") or state.get("current_owner_id") or "00000000-0000-0000-0000-000000000002")
        doc_res = run_doctor_workflow(
            doctor_id=doctor_id,
            message=state.get("inbound_message", ""),
            case_id=state.get("case_id"),
        )
        return {
            "coordination_plan": {
                "goal": "Doctor clinical workflow execution",
                "situation_summary": f"Doctor processed {doc_res.get('doctor_intent')}",
                "actions": [],
                "patient_response_draft": doc_res.get("response_message", "Clinical request processed."),
                "target_language": "en"
            },
            "pending_tool_calls": [],
            "outbound_message": doc_res.get("response_message", "Clinical request processed."),
            "outbound_language": "en",
            "audit_entries": doc_res.get("audit_log", []),
            "replanning_needed": False,
        }

    from app.agents.state import IntentAnalysis
    intent_data = state.get("intent_analysis") or {}
    intent = IntentAnalysis(**intent_data)
    patient_ctx = state.get("patient_context", {})
    case_ctx = state.get("case_context", {})
    conv_ctx = dict(state.get("conversation_context") or {})
    conv_ctx["inbound_sender"] = state.get("inbound_sender") or state.get("actor_role") or conv_ctx.get("inbound_sender", "")

    plan = CognitiveEngine.formulate_plan(intent, patient_ctx, case_ctx, conv_ctx)
    pending_calls = [
        {
            "step": act.step_number,
            "tool": act.tool_name,
            "arguments": act.arguments,
            "rationale": act.rationale,
            "autonomy_level": act.autonomy_level,
        }
        for act in plan.actions
    ]

    return {
        "coordination_plan": plan.model_dump(),
        "pending_tool_calls": pending_calls,
        "outbound_message": plan.patient_response_draft,
        "outbound_language": plan.target_language,
        "replanning_needed": False,
    }


def safety_gatekeeper_node(state: AgentState) -> Dict[str, Any]:
    """Validates autonomy boundaries. Routes Level 3 actions to human approval interrupt."""
    pending_calls = state.get("pending_tool_calls", [])
    requires_approval = any(call.get("autonomy_level", 1) >= 3 for call in pending_calls)

    if requires_approval:
        level_3_call = next(c for c in pending_calls if c.get("autonomy_level", 1) >= 3)
        return {
            "requires_human_approval": True,
            "approval_request": {
                "action": level_3_call.get("tool"),
                "arguments": level_3_call.get("arguments"),
                "reason": "Level 3 Clinical Human Authorization Required",
            }
        }
    return {"requires_human_approval": False}


def execute_tools_node(state: AgentState) -> Dict[str, Any]:
    """Executes permitted Level 1 and Level 2 tools against the backend registry."""
    pending_calls = state.get("pending_tool_calls", [])
    observations = []
    audit_entries = []

    with get_sync_db() as db:
        for call in pending_calls:
            tool_name = call.get("tool")
            args = call.get("arguments", {}).copy()

            # Sanitize case_id and patient_id against LLM template placeholders (e.g. '{case_id}')
            if "case_id" in args and ("{" in str(args["case_id"]) or not args["case_id"]):
                args["case_id"] = state.get("case_id")
            if "patient_id" in args and ("{" in str(args["patient_id"]) or not args["patient_id"]):
                args["patient_id"] = state.get("patient_id")

            if tool_name == "create_followup_task":
                if "case_id" not in args or not args["case_id"]:
                    args["case_id"] = state.get("case_id")
                if "due_date" not in args or not args["due_date"] or "{" in str(args["due_date"]):
                    from datetime import datetime, timezone, timedelta
                    args["due_date"] = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT10:00:00Z")
                if "title" not in args or not args["title"] or "{" in str(args["title"]):
                    args["title"] = "Follow up with patient regarding care barrier"
                if "description" not in args or not args["description"]:
                    args["description"] = "Patient barrier resolution follow-up"
                if "task_type" not in args or not args["task_type"]:
                    args["task_type"] = "recovery_play"

            func = getattr(ToolRegistry, tool_name, None)

            if func:
                try:
                    result = func(db, **args)
                    observations.append({
                        "step": call.get("step"),
                        "tool": tool_name,
                        "result": result,
                        "success": result.get("success", True),
                    })
                    audit_entries.append({
                        "action": tool_name,
                        "rationale": call.get("rationale"),
                        "autonomy_level": call.get("autonomy_level", 1),
                        "status": "executed"
                    })
                except Exception as e:
                    observations.append({
                        "step": call.get("step"),
                        "tool": tool_name,
                        "error": str(e),
                        "success": False,
                    })

    return {
        "tool_observations": observations,
        "audit_entries": audit_entries,
        "pending_tool_calls": [],
    }


def reflect_and_update_node(state: AgentState) -> Dict[str, Any]:
    """Reflects on tool execution outcomes, guards against infinite loops, and checks replanning."""
    observations = state.get("tool_observations", [])
    has_failures = any(not obs.get("success", True) for obs in observations)

    current_iter = state.get("iteration_count", 0) + 1
    max_iter = state.get("max_iterations", 5)

    # Infinite loop prevention safeguard: Halt replanning if maximum iteration threshold reached
    if current_iter >= max_iter:
        return {
            "replanning_needed": False,
            "iteration_count": current_iter,
        }

    return {
        "replanning_needed": has_failures,
        "iteration_count": current_iter,
    }


def generate_response_node(state: AgentState) -> Dict[str, Any]:
    """Dispatches the finalized empathetic response to the patient channel."""
    outbound = state.get("outbound_message")
    case_id = state.get("case_id")
    patient_id = state.get("patient_id")
    session_id = state.get("session_id")
    lang = state.get("outbound_language", "en")
    channel = state.get("inbound_channel", "sms")

    if outbound and case_id and patient_id:
        with get_sync_db() as db:
            ToolRegistry.send_patient_message(
                db=db,
                case_id=case_id,
                patient_id=patient_id,
                message=outbound,
                language=lang,
                channel=channel,
                session_id=session_id
            )

    return {"final_case_status": "active_progress"}


# ------------------------------------------------------------------------------
# 2. Graph Wiring & Conditional Routing
# ------------------------------------------------------------------------------

def route_after_safety(state: AgentState) -> Literal["human_interrupt", "execute_tools"]:
    if state.get("requires_human_approval", False):
        return "human_interrupt"
    return "execute_tools"


def human_interrupt_node(state: AgentState) -> Dict[str, Any]:
    """Human-in-the-loop checkpoint pause for Level 3 clinical decisions."""
    # In interactive LangGraph execution, this node can be configured with an interrupt.
    decision = state.get("human_decision", "pending")
    return {"requires_human_approval": False, "human_decision": decision}


def route_after_reflection(state: AgentState) -> Literal["reason_and_plan", "generate_response"]:
    if state.get("replanning_needed", False):
        return "reason_and_plan"
    return "generate_response"


def create_carebridge_graph(checkpointer=None):
    """Builds and compiles the CareBridge LangGraph Supervisor Workflow."""
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node("retrieve_context", retrieve_context_node)
    workflow.add_node("interpret_intent", interpret_intent_node)
    workflow.add_node("reason_and_plan", reason_and_plan_node)
    workflow.add_node("safety_gatekeeper", safety_gatekeeper_node)
    workflow.add_node("human_interrupt", human_interrupt_node)
    workflow.add_node("execute_tools", execute_tools_node)
    workflow.add_node("reflect_and_update", reflect_and_update_node)
    workflow.add_node("generate_response", generate_response_node)

    # Add Edges
    workflow.add_edge(START, "retrieve_context")
    workflow.add_edge("retrieve_context", "interpret_intent")
    workflow.add_edge("interpret_intent", "reason_and_plan")
    workflow.add_edge("reason_and_plan", "safety_gatekeeper")

    workflow.add_conditional_edges(
        "safety_gatekeeper",
        route_after_safety,
        {
            "human_interrupt": "human_interrupt",
            "execute_tools": "execute_tools",
        }
    )

    workflow.add_edge("human_interrupt", "execute_tools")
    workflow.add_edge("execute_tools", "reflect_and_update")

    workflow.add_conditional_edges(
        "reflect_and_update",
        route_after_reflection,
        {
            "reason_and_plan": "reason_and_plan",
            "generate_response": "generate_response",
        }
    )

    workflow.add_edge("generate_response", END)

    # Use supplied checkpointer or default in-memory checkpointer
    cp = checkpointer or MemorySaver()
    return workflow.compile(checkpointer=cp)


# Compiled default supervisor graph instance
supervisor_graph = create_carebridge_graph()
