"""
CareBridge Agent State Schema
Defines the state structure for LangGraph workflow execution.
"""

from typing import List, Dict, Any, Optional, TypedDict, Annotated
import operator
from pydantic import BaseModel, Field


class InferredBarrier(BaseModel):
    barrier_type: str = Field(description="e.g. 'transportation', 'childcare', 'fear_anxiety', 'financial', 'schedule_conflict'")
    severity: str = Field(description="'low', 'medium', 'high'")
    details: str = Field(description="Explanation extracted from patient message")


class IntentAnalysis(BaseModel):
    primary_intent: str = Field(description="'urgent_clinical_escalation', 'appointment_reschedule_request', 'clinical_question', 'acknowledgement', 'refusal'")
    emotional_state: str = Field(description="'anxious', 'cooperative', 'overwhelmed', 'frustrated', 'neutral'")
    detected_language: str = Field(description="'en', 'ta', 'mixed'")
    detected_barriers: List[InferredBarrier] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    inquiry_topic: Optional[str] = Field(default=None, description="Topic of inquiry, e.g. 'birads', 'biopsy', 'pain', 'scheduling'")
    raw_query: Optional[str] = Field(default=None, description="Raw user query text")
    requires_clarification: bool = False
    requires_human_escalation: bool = False


class ProposedAction(BaseModel):
    step_number: int
    tool_name: str
    arguments: Dict[str, Any]
    rationale: str
    autonomy_level: int = 1 # 1 = Autonomous, 2 = Constrained, 3 = Human Authorized


class CoordinationPlan(BaseModel):
    goal: str
    situation_summary: str
    actions: List[ProposedAction] = Field(default_factory=list)
    patient_response_draft: str = Field(description="Empathetic message formulated for patient")
    target_language: str = "en"


class AgentState(TypedDict, total=False):
    """LangGraph state representation passed through the cognitive loop."""
    # Identification
    case_id: str
    patient_id: str
    session_id: Optional[str]

    # Inbound trigger
    inbound_message: str
    inbound_channel: str
    inbound_sender: str

    # Retrieved Memory Contexts
    patient_context: Dict[str, Any]
    case_context: Dict[str, Any]
    conversation_context: Dict[str, Any]

    # Cognitive Reasoning
    intent_analysis: Optional[Dict[str, Any]]
    coordination_plan: Optional[Dict[str, Any]]

    # Tool Execution Loop
    pending_tool_calls: List[Dict[str, Any]]
    tool_observations: List[Dict[str, Any]]
    replanning_needed: bool

    # Human-in-the-Loop Interrupt
    requires_human_approval: bool
    approval_request: Optional[Dict[str, Any]]
    human_decision: Optional[str]

    # Loop & Safeguards
    iteration_count: int
    max_iterations: int

    # Final outputs
    outbound_message: Optional[str]
    outbound_language: str
    final_case_status: Optional[str]
    audit_entries: List[Dict[str, Any]]
