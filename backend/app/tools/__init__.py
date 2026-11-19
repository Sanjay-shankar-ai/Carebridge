"""
CareBridge Tool Layer Exports
Exports modular domain tools, Pydantic input/output schemas, and execution wrappers.
"""

# Base & Envelopes
from app.tools.base import (
    ToolResult,
    ToolExecutionError,
    validate_tool_permission,
    log_tool_audit,
)

# Schemas
from app.tools.schemas import (
    # Patient
    RetrievePatientProfileInput, PatientProfileOutput,
    RetrievePatientPreferencesInput, PatientPreferencesOutput,
    RetrieveConversationHistoryInput, ConversationHistoryOutput, MessageItem,
    # Case
    CreateCareCaseInput, CareCaseOutput,
    RetrieveCaseDetailsInput, CaseDetailsOutput,
    RetrieveCaseEventsInput, CaseEventsOutput, CaseEventItem,
    UpdateCaseNotesInput, UpdateCaseNotesOutput,
    AssignAdministrativeOwnershipInput, AssignOwnershipOutput,
    # Communication
    DraftPatientMessageInput, DraftPatientMessageOutput,
    TranslateMessageInput, TranslateMessageOutput,
    SendPermittedCommunicationInput, SendPermittedCommunicationOutput,
    RecordAcknowledgementInput, RecordAcknowledgementOutput,
    # Referral
    CreateReferralRequestInput, ReferralRequestOutput,
    CheckReferralStatusInput, ReferralStatusOutput,
    RetrieveReferralInformationInput, ReferralInformationOutput,
    # Appointment
    SearchAvailableAppointmentsInput, AvailableAppointmentsOutput,
    BookAppointmentInput, BookAppointmentOutput,
    RescheduleAppointmentInput, RescheduleAppointmentOutput,
    RetrieveAppointmentStatusInput, AppointmentStatusOutput,
    # Recovery
    CreateFollowupTaskInput, FollowupTaskOutput,
    IdentifyStalledCasesInput, StalledCasesOutput, StalledCaseItem,
    ProposeRecoveryActionInput, RecoveryActionOutput,
    EscalateCaseInput, EscalateCaseOutput,
    # Closure
    RetrieveClosureEvidenceInput, ClosureEvidenceOutput, ClosureEvidenceItem,
    RequestClosureVerificationInput, RequestClosureVerificationOutput,
)

# Domain Implementations
from app.tools.patient_tools import (
    retrieve_patient_profile,
    retrieve_patient_preferences,
    retrieve_conversation_history,
)
from app.tools.case_tools import (
    create_care_case,
    retrieve_case_details,
    retrieve_case_events,
    update_case_notes,
    assign_administrative_ownership,
)
from app.tools.communication_tools import (
    draft_patient_message,
    translate_message,
    send_permitted_communication,
    record_acknowledgement,
)
from app.tools.referral_tools import (
    create_referral_request,
    check_referral_status,
    retrieve_referral_information,
)
from app.tools.appointment_tools import (
    search_available_appointments,
    book_appointment,
    reschedule_appointment,
    retrieve_appointment_status,
)
from app.tools.recovery_tools import (
    create_followup_task,
    identify_stalled_cases,
    propose_recovery_action,
    escalate_case,
)
from app.tools.closure_tools import (
    retrieve_closure_evidence,
    request_closure_verification,
)

# LangChain @tool Ecosystem
from app.tools.agent_tools import (
    MODULAR_ECOSYSTEM_TOOLS,
    SUPERVISOR_TOOLS,
)

# Legacy Registry (backward compatibility)
from app.tools.registry import ToolRegistry, ToolExecutionResult

__all__ = [
    # Base
    "ToolResult",
    "ToolExecutionError",
    "validate_tool_permission",
    "log_tool_audit",
    # Patient Schemas & Tools
    "RetrievePatientProfileInput", "PatientProfileOutput",
    "RetrievePatientPreferencesInput", "PatientPreferencesOutput",
    "RetrieveConversationHistoryInput", "ConversationHistoryOutput", "MessageItem",
    "retrieve_patient_profile", "retrieve_patient_preferences", "retrieve_conversation_history",
    # Case Schemas & Tools
    "CreateCareCaseInput", "CareCaseOutput",
    "RetrieveCaseDetailsInput", "CaseDetailsOutput",
    "RetrieveCaseEventsInput", "CaseEventsOutput", "CaseEventItem",
    "UpdateCaseNotesInput", "UpdateCaseNotesOutput",
    "AssignAdministrativeOwnershipInput", "AssignOwnershipOutput",
    "create_care_case", "retrieve_case_details", "retrieve_case_events",
    "update_case_notes", "assign_administrative_ownership",
    # Communication Schemas & Tools
    "DraftPatientMessageInput", "DraftPatientMessageOutput",
    "TranslateMessageInput", "TranslateMessageOutput",
    "SendPermittedCommunicationInput", "SendPermittedCommunicationOutput",
    "RecordAcknowledgementInput", "RecordAcknowledgementOutput",
    "draft_patient_message", "translate_message",
    "send_permitted_communication", "record_acknowledgement",
    # Referral Schemas & Tools
    "CreateReferralRequestInput", "ReferralRequestOutput",
    "CheckReferralStatusInput", "ReferralStatusOutput",
    "RetrieveReferralInformationInput", "ReferralInformationOutput",
    "create_referral_request", "check_referral_status", "retrieve_referral_information",
    # Appointment Schemas & Tools
    "SearchAvailableAppointmentsInput", "AvailableAppointmentsOutput",
    "BookAppointmentInput", "BookAppointmentOutput",
    "RescheduleAppointmentInput", "RescheduleAppointmentOutput",
    "RetrieveAppointmentStatusInput", "AppointmentStatusOutput",
    "search_available_appointments", "book_appointment",
    "reschedule_appointment", "retrieve_appointment_status",
    # Recovery Schemas & Tools
    "CreateFollowupTaskInput", "FollowupTaskOutput",
    "IdentifyStalledCasesInput", "StalledCasesOutput", "StalledCaseItem",
    "ProposeRecoveryActionInput", "RecoveryActionOutput",
    "EscalateCaseInput", "EscalateCaseOutput",
    "create_followup_task", "identify_stalled_cases",
    "propose_recovery_action", "escalate_case",
    # Closure Schemas & Tools
    "RetrieveClosureEvidenceInput", "ClosureEvidenceOutput", "ClosureEvidenceItem",
    "RequestClosureVerificationInput", "RequestClosureVerificationOutput",
    "retrieve_closure_evidence", "request_closure_verification",
    # Agent Tool Lists
    "MODULAR_ECOSYSTEM_TOOLS",
    "SUPERVISOR_TOOLS",
    # Legacy
    "ToolRegistry",
    "ToolExecutionResult",
]
