"""
CareBridge Autonomous AI Workflows
LangGraph-orchestrated closed-loop care coordination engine.
Includes Care Coordination Workflow and Doctor Subgraph.
"""

from app.workflows.state import CareBridgeState, ClosureChecklist
from app.workflows.rules import (
    calculate_sla_deadline,
    evaluate_sla_status,
    match_clinical_pathway,
    evaluate_dropoff_rules,
    determine_recovery_strategy,
    evaluate_closure_checklist,
)
from app.workflows.checkpointer import (
    get_workflow_checkpointer,
    get_thread_config,
    get_in_memory_checkpointer,
)
from app.workflows.care_workflow import (
    create_carebridge_workflow,
    run_carebridge_workflow,
    resume_carebridge_workflow,
)
from app.workflows.orchestrator import LongRunningWorkflowOrchestrator
from app.workflows.doctor_state import DoctorState, DOCTOR_INTENTS
from app.workflows.doctor_workflow import (
    create_doctor_workflow,
    run_doctor_workflow,
)
from app.workflows.doctor_nodes import (
    doctor_intake_node,
    doctor_auth_check_node,
    doctor_context_retrieval_node,
    doctor_case_review_node,
    referral_management_node,
    appointment_management_node,
    consultation_management_node,
    clinical_decision_review_node,
    followup_management_node,
    closure_review_node,
    doctor_response_node,
)

__all__ = [
    # Care Workflow
    "CareBridgeState",
    "ClosureChecklist",
    "calculate_sla_deadline",
    "evaluate_sla_status",
    "match_clinical_pathway",
    "evaluate_dropoff_rules",
    "determine_recovery_strategy",
    "evaluate_closure_checklist",
    "get_workflow_checkpointer",
    "get_thread_config",
    "get_in_memory_checkpointer",
    "create_carebridge_workflow",
    "run_carebridge_workflow",
    "resume_carebridge_workflow",
    "LongRunningWorkflowOrchestrator",
    # Doctor Subgraph
    "DoctorState",
    "DOCTOR_INTENTS",
    "create_doctor_workflow",
    "run_doctor_workflow",
    "doctor_intake_node",
    "doctor_auth_check_node",
    "doctor_context_retrieval_node",
    "doctor_case_review_node",
    "referral_management_node",
    "appointment_management_node",
    "consultation_management_node",
    "clinical_decision_review_node",
    "followup_management_node",
    "closure_review_node",
    "doctor_response_node",
]
