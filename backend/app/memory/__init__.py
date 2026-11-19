"""
CareBridge Memory Module Export
Exposes memory contexts and retrieval functions for patient, conversation, and case memory.
"""

from app.memory.schemas import (
    PatientMemoryContext,
    ConversationMemoryContext,
    CaseMemoryContext,
    UnifiedCareContext,
    MessageItem,
    ReferralSummary,
    AppointmentSummary,
    TaskSummary,
)
from app.memory.patient_memory import (
    get_patient_memory,
    get_patient_memory_sync,
    record_patient_barrier,
)
from app.memory.conversation_memory import (
    get_conversation_memory,
    get_conversation_memory_sync,
)
from app.memory.case_memory import (
    get_case_memory,
    get_case_memory_sync,
)
from app.memory.retriever import (
    get_unified_memory,
    get_unified_memory_sync,
)

__all__ = [
    "PatientMemoryContext",
    "ConversationMemoryContext",
    "CaseMemoryContext",
    "UnifiedCareContext",
    "MessageItem",
    "ReferralSummary",
    "AppointmentSummary",
    "TaskSummary",
    "get_patient_memory",
    "get_patient_memory_sync",
    "record_patient_barrier",
    "get_conversation_memory",
    "get_conversation_memory_sync",
    "get_case_memory",
    "get_case_memory_sync",
    "get_unified_memory",
    "get_unified_memory_sync",
]
