"""
LangChain @tool definitions for the CareBridge AI Agent Tool Ecosystem.
Wraps modular domain tools with typed schemas, docstrings, permission checks,
and audit logging for native LLM binding.
"""

from typing import Optional, List, Dict, Any
from langchain_core.tools import tool
from app.database.session import get_sync_db
from app.tools.registry import ToolRegistry

from app.tools.schemas import (
    RetrievePatientProfileInput,
    RetrievePatientPreferencesInput,
    RetrieveConversationHistoryInput,
    CreateCareCaseInput,
    RetrieveCaseDetailsInput,
    RetrieveCaseEventsInput,
    UpdateCaseNotesInput,
    AssignAdministrativeOwnershipInput,
    DraftPatientMessageInput,
    TranslateMessageInput,
    SendPermittedCommunicationInput,
    RecordAcknowledgementInput,
    CreateReferralRequestInput,
    CheckReferralStatusInput,
    RetrieveReferralInformationInput,
    SearchAvailableAppointmentsInput,
    BookAppointmentInput,
    RescheduleAppointmentInput,
    RetrieveAppointmentStatusInput,
    CreateFollowupTaskInput,
    IdentifyStalledCasesInput,
    ProposeRecoveryActionInput,
    EscalateCaseInput,
    RetrieveClosureEvidenceInput,
    RequestClosureVerificationInput,
)

import app.tools.patient_tools as patient_module
import app.tools.case_tools as case_module
import app.tools.communication_tools as comm_module
import app.tools.referral_tools as referral_module
import app.tools.appointment_tools as appt_module
import app.tools.recovery_tools as recovery_module
import app.tools.closure_tools as closure_module


# ==============================================================================
# 1. Patient Domain Tools
# ==============================================================================
@tool
def retrieve_patient_profile(patient_id: str, actor_role: Optional[str] = "ai_coordinator") -> Dict[str, Any]:
    """Retrieve full demographic, clinical context, and known barriers for a patient."""
    with get_sync_db() as db:
        res = patient_module.retrieve_patient_profile(
            db, RetrievePatientProfileInput(patient_id=patient_id, actor_role=actor_role)
        )
        return res.model_dump()


@tool
def retrieve_patient_preferences(patient_id: str, actor_role: Optional[str] = "ai_coordinator") -> Dict[str, Any]:
    """Retrieve communication preferences, language, accessibility requirements, and consents."""
    with get_sync_db() as db:
        res = patient_module.retrieve_patient_preferences(
            db, RetrievePatientPreferencesInput(patient_id=patient_id, actor_role=actor_role)
        )
        return res.model_dump()


@tool
def retrieve_conversation_history(
    patient_id: str, case_id: Optional[str] = None, limit: int = 20, actor_role: Optional[str] = "ai_coordinator"
) -> Dict[str, Any]:
    """Retrieve previous communications, messages, and conversation summaries for a patient."""
    with get_sync_db() as db:
        res = patient_module.retrieve_conversation_history(
            db, RetrieveConversationHistoryInput(patient_id=patient_id, case_id=case_id, limit=limit, actor_role=actor_role)
        )
        return res.model_dump()


# ==============================================================================
# 2. Case Domain Tools
# ==============================================================================
@tool
def create_care_case(
    patient_id: str,
    screening_result_id: str,
    clinical_pathway: Optional[str] = None,
    priority: str = "standard",
    initial_owner_id: Optional[str] = None,
    actor_role: Optional[str] = "care_coordinator"
) -> Dict[str, Any]:
    """Create a new care case from an abnormal screening result. Idempotent on screening_result_id."""
    with get_sync_db() as db:
        res = case_module.create_care_case(
            db, CreateCareCaseInput(
                patient_id=patient_id,
                screening_result_id=screening_result_id,
                clinical_pathway=clinical_pathway,
                priority=priority,
                initial_owner_id=initial_owner_id,
                actor_role=actor_role
            )
        )
        return res.model_dump()


@tool
def retrieve_case_details(case_id: str, actor_role: Optional[str] = "ai_coordinator") -> Dict[str, Any]:
    """Retrieve full case details, accountable coordinator, priority, pathway, and SLA deadlines."""
    with get_sync_db() as db:
        res = case_module.retrieve_case_details(
            db, RetrieveCaseDetailsInput(case_id=case_id, actor_role=actor_role)
        )
        return res.model_dump()


@tool
def retrieve_case_events(case_id: str, limit: int = 50, actor_role: Optional[str] = "ai_coordinator") -> Dict[str, Any]:
    """Retrieve chronological timeline events recorded for a care case."""
    with get_sync_db() as db:
        res = case_module.retrieve_case_events(
            db, RetrieveCaseEventsInput(case_id=case_id, limit=limit, actor_role=actor_role)
        )
        return res.model_dump()


@tool
def update_case_notes(
    case_id: str, note: str, barrier_detected: Optional[str] = None, actor_role: Optional[str] = "ai_coordinator"
) -> Dict[str, Any]:
    """Append a clinical or administrative progress note and record any discovered patient barrier."""
    with get_sync_db() as db:
        res = case_module.update_case_notes(
            db, UpdateCaseNotesInput(case_id=case_id, note=note, barrier_detected=barrier_detected, actor_role=actor_role)
        )
        return res.model_dump()


@tool
def assign_administrative_ownership(
    case_id: str, new_owner_id: str, assigned_by: str, reason: str, actor_role: Optional[str] = "care_coordinator"
) -> Dict[str, Any]:
    """Assign an accountable Care Coordinator to a case and log continuous ownership history."""
    with get_sync_db() as db:
        res = case_module.assign_administrative_ownership(
            db, AssignAdministrativeOwnershipInput(
                case_id=case_id, new_owner_id=new_owner_id, assigned_by=assigned_by, reason=reason, actor_role=actor_role
            )
        )
        return res.model_dump()


# ==============================================================================
# 3. Communication Domain Tools
# ==============================================================================
@tool
def draft_patient_message(
    patient_id: str,
    case_id: str,
    message_purpose: str,
    clinical_context: Optional[str] = None,
    language: Optional[str] = None,
    actor_role: Optional[str] = "ai_coordinator"
) -> Dict[str, Any]:
    """Draft an empathetic, non-alarmist message adapted to the patient's language and literacy."""
    with get_sync_db() as db:
        res = comm_module.draft_patient_message(
            db, DraftPatientMessageInput(
                patient_id=patient_id, case_id=case_id, message_purpose=message_purpose,
                clinical_context=clinical_context, language=language, actor_role=actor_role
            )
        )
        return res.model_dump()


@tool
def translate_message(
    text: str, target_language: str, source_language: Optional[str] = "auto", actor_role: Optional[str] = "ai_coordinator"
) -> Dict[str, Any]:
    """Translate a message between English and regional languages (e.g. Tamil) maintaining clinical clarity."""
    with get_sync_db() as db:
        res = comm_module.translate_message(
            db, TranslateMessageInput(text=text, target_language=target_language, source_language=source_language, actor_role=actor_role)
        )
        return res.model_dump()


@tool
def send_permitted_communication(
    case_id: str,
    patient_id: str,
    content: str,
    channel: Optional[str] = None,
    language: Optional[str] = "en",
    actor_role: Optional[str] = "ai_coordinator"
) -> Dict[str, Any]:
    """Dispatch an outreach communication to the patient after validating active consent."""
    with get_sync_db() as db:
        res = comm_module.send_permitted_communication(
            db, SendPermittedCommunicationInput(
                case_id=case_id, patient_id=patient_id, content=content, channel=channel, language=language, actor_role=actor_role
            )
        )
        return res.model_dump()


@tool
def record_acknowledgement(
    case_id: str,
    patient_id: str,
    acknowledged_via: str = "sms",
    patient_response: Optional[str] = None,
    actor_role: Optional[str] = "ai_coordinator"
) -> Dict[str, Any]:
    """Record patient receipt and comprehension of screening notification, completing outreach tasks."""
    with get_sync_db() as db:
        res = comm_module.record_acknowledgement(
            db, RecordAcknowledgementInput(
                case_id=case_id, patient_id=patient_id, acknowledged_via=acknowledged_via,
                patient_response=patient_response, actor_role=actor_role
            )
        )
        return res.model_dump()


# ==============================================================================
# 4. Referral Domain Tools
# ==============================================================================
@tool
def create_referral_request(
    case_id: str,
    patient_id: str,
    target_facility: str,
    specialty: str,
    reason: str,
    actor_role: Optional[str] = "care_coordinator"
) -> Dict[str, Any]:
    """Create and dispatch an inter-facility referral request with a 48h SLA deadline."""
    with get_sync_db() as db:
        res = referral_module.create_referral_request(
            db, CreateReferralRequestInput(
                case_id=case_id, patient_id=patient_id, target_facility=target_facility,
                specialty=specialty, reason=reason, actor_role=actor_role
            )
        )
        return res.model_dump()


@tool
def check_referral_status(referral_id: str, actor_role: Optional[str] = "ai_coordinator") -> Dict[str, Any]:
    """Check referral acceptance status, target specialty clinic, and SLA deadline."""
    with get_sync_db() as db:
        res = referral_module.check_referral_status(
            db, CheckReferralStatusInput(referral_id=referral_id, actor_role=actor_role)
        )
        return res.model_dump()


@tool
def retrieve_referral_information(case_id: str, actor_role: Optional[str] = "ai_coordinator") -> Dict[str, Any]:
    """Retrieve all active and historical referrals associated with a care case."""
    with get_sync_db() as db:
        res = referral_module.retrieve_referral_information(
            db, RetrieveReferralInformationInput(case_id=case_id, actor_role=actor_role)
        )
        return res.model_dump()


# ==============================================================================
# 5. Appointment Domain Tools
# ==============================================================================
@tool
def search_available_appointments(
    facility: str, specialty: str, timeframe: Optional[str] = "next_14_days", actor_role: Optional[str] = "ai_coordinator"
) -> Dict[str, Any]:
    """Search for available consultation slots at a clinic within the clinical SLA window."""
    with get_sync_db() as db:
        res = appt_module.search_available_appointments(
            db, SearchAvailableAppointmentsInput(facility=facility, specialty=specialty, timeframe=timeframe, actor_role=actor_role)
        )
        return res.model_dump()


@tool
def book_appointment(
    case_id: str,
    patient_id: str,
    facility: str,
    scheduled_time: str,
    appointment_type: str,
    provider_name: Optional[str] = "Specialist Clinician",
    notes: Optional[str] = None,
    actor_role: Optional[str] = "ai_coordinator"
) -> Dict[str, Any]:
    """Book a confirmed clinic appointment within the approved SLA window."""
    with get_sync_db() as db:
        res = appt_module.book_appointment(
            db, BookAppointmentInput(
                case_id=case_id, patient_id=patient_id, facility=facility, scheduled_time=scheduled_time,
                appointment_type=appointment_type, provider_name=provider_name, notes=notes, actor_role=actor_role
            )
        )
        return res.model_dump()


@tool
def reschedule_appointment(
    appointment_id: str,
    case_id: str,
    new_scheduled_time: str,
    reason: str,
    notes: Optional[str] = None,
    actor_role: Optional[str] = "care_coordinator"
) -> Dict[str, Any]:
    """Reschedule an appointment with a mandatory documented reason, maintaining dual-acceptance flags."""
    with get_sync_db() as db:
        res = appt_module.reschedule_appointment(
            db, RescheduleAppointmentInput(
                appointment_id=appointment_id, case_id=case_id, new_scheduled_time=new_scheduled_time,
                reason=reason, notes=notes, actor_role=actor_role
            )
        )
        return res.model_dump()


@tool
def retrieve_appointment_status(case_id: str, actor_role: Optional[str] = "ai_coordinator") -> Dict[str, Any]:
    """Retrieve active appointment, full appointment history, and attendance records for a case."""
    with get_sync_db() as db:
        res = appt_module.retrieve_appointment_status(
            db, RetrieveAppointmentStatusInput(case_id=case_id, actor_role=actor_role)
        )
        return res.model_dump()


# ==============================================================================
# 6. Recovery Domain Tools
# ==============================================================================
@tool
def create_followup_task(
    case_id: str,
    title: str,
    description: str,
    task_type: str,
    due_date: str,
    assigned_role: Optional[str] = "care_coordinator",
    assigned_to_id: Optional[str] = None,
    actor_role: Optional[str] = "care_coordinator"
) -> Dict[str, Any]:
    """Create an actionable follow-up task along the care coordination journey."""
    with get_sync_db() as db:
        res = recovery_module.create_followup_task(
            db, CreateFollowupTaskInput(
                case_id=case_id, title=title, description=description, task_type=task_type,
                due_date=due_date, assigned_role=assigned_role, assigned_to_id=assigned_to_id, actor_role=actor_role
            )
        )
        return res.model_dump()


@tool
def identify_stalled_cases(
    case_id: Optional[str] = None, days_threshold: int = 5, actor_role: Optional[str] = "ai_coordinator"
) -> Dict[str, Any]:
    """Identify care cases exceeding the inactivity threshold without recorded progress."""
    with get_sync_db() as db:
        res = recovery_module.identify_stalled_cases(
            db, IdentifyStalledCasesInput(case_id=case_id, days_threshold=days_threshold, actor_role=actor_role)
        )
        return res.model_dump()


@tool
def propose_recovery_action(
    case_id: str, dropoff_reasons: Optional[List[str]] = None, actor_role: Optional[str] = "ai_coordinator"
) -> Dict[str, Any]:
    """Analyze detected dropoff barriers and formulate an actionable recovery strategy."""
    with get_sync_db() as db:
        res = recovery_module.propose_recovery_action(
            db, ProposeRecoveryActionInput(case_id=case_id, dropoff_reasons=dropoff_reasons, actor_role=actor_role)
        )
        return res.model_dump()


@tool
def escalate_case(
    case_id: str, urgency: str = "urgent", reason: str = "", actor_role: Optional[str] = "ai_coordinator"
) -> Dict[str, Any]:
    """Escalate an at-risk, stalled, or unowned case to the human coordinator/supervisor emergency queue."""
    with get_sync_db() as db:
        res = recovery_module.escalate_case(
            db, EscalateCaseInput(case_id=case_id, urgency=urgency, reason=reason, actor_role=actor_role)
        )
        return res.model_dump()


# ==============================================================================
# 7. Closure Domain Tools
# ==============================================================================
@tool
def retrieve_closure_evidence(case_id: str, actor_role: Optional[str] = "ai_coordinator") -> Dict[str, Any]:
    """Retrieve all clinical closure evidence, pathology reports, and the 5-point closure checklist."""
    with get_sync_db() as db:
        res = closure_module.retrieve_closure_evidence(
            db, RetrieveClosureEvidenceInput(case_id=case_id, actor_role=actor_role)
        )
        return res.model_dump()


@tool
def request_closure_verification(
    case_id: str,
    evidence_type: str,
    evidence_summary: str,
    clinician_id: str,
    actor_role: Optional[str] = "ai_coordinator"
) -> Dict[str, Any]:
    """Submit clinical findings for human clinician review and sign-off (Level 3 Gate). AI cannot close independently!"""
    with get_sync_db() as db:
        res = closure_module.request_closure_verification(
            db, RequestClosureVerificationInput(
                case_id=case_id, evidence_type=evidence_type, evidence_summary=evidence_summary,
                clinician_id=clinician_id, actor_role=actor_role
            )
        )
        return res.model_dump()


# ==============================================================================
# Backward-Compatible Legacy Wrappers
# ==============================================================================
@tool
def get_patient_context(patient_id: str) -> Dict[str, Any]:
    """Retrieve patient demographic context, preferred language, and known barriers."""
    with get_sync_db() as db:
        return ToolRegistry.get_patient_context(db, patient_id)


@tool
def get_case_status(case_id: str) -> Dict[str, Any]:
    """Retrieve active care case status, current owner, priority, and SLA deadlines."""
    with get_sync_db() as db:
        return ToolRegistry.get_case_status(db, case_id)


@tool
def get_screening_result(case_id: str) -> Dict[str, Any]:
    """Retrieve the screening finding details, BI-RADS code, and urgency level."""
    with get_sync_db() as db:
        return ToolRegistry.get_screening_result(db, case_id)


@tool
def get_referral_status(case_id: str) -> Dict[str, Any]:
    """Check referral status, target specialty clinic, and acceptance deadline."""
    with get_sync_db() as db:
        return ToolRegistry.get_referral_status(db, case_id)


@tool
def search_appointments(facility: str, specialty: str, timeframe: str = "next_14_days") -> Dict[str, Any]:
    """Search for available consultation slots at a clinic within the clinical SLA window."""
    with get_sync_db() as db:
        return ToolRegistry.search_appointments(db, facility, specialty, timeframe)


@tool
def cancel_appointment(
    appointment_id: str, case_id: str, reason: str, outcome: str = "reschedule_pending", detailed_notes: Optional[str] = None
) -> Dict[str, Any]:
    """Cancel an appointment with a mandatory documented reason and outcome path."""
    with get_sync_db() as db:
        return ToolRegistry.cancel_appointment(db, appointment_id, case_id, reason, outcome, detailed_notes)


@tool
def record_case_event(
    case_id: str, event_type: str, description: str, event_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Record a milestone or event in the immutable case timeline."""
    with get_sync_db() as db:
        return ToolRegistry.record_case_event(db, case_id, event_type, description, event_data)


@tool
def get_case_owner(case_id: str) -> Dict[str, Any]:
    """Retrieve the designated accountable Care Coordinator who owns this case."""
    with get_sync_db() as db:
        return ToolRegistry.get_case_owner(db, case_id)


@tool
def assign_case_owner(case_id: str, new_owner_id: str, assigned_by: str, reason: str) -> Dict[str, Any]:
    """Assign an accountable Care Coordinator to a case and log continuous ownership history."""
    with get_sync_db() as db:
        return ToolRegistry.assign_case_owner(db, case_id, new_owner_id, assigned_by, reason)


@tool
def transfer_case_ownership(case_id: str, from_owner_id: str, to_owner_id: str, transferred_by: str, reason: str) -> Dict[str, Any]:
    """Transfer accountability from one coordinator to another with audit history."""
    with get_sync_db() as db:
        return ToolRegistry.transfer_case_ownership(db, case_id, from_owner_id, to_owner_id, transferred_by, reason)


@tool
def get_pending_case_tasks(case_id: str) -> Dict[str, Any]:
    """Retrieve outstanding tasks, incomplete milestones, and overdue coordinator work items."""
    with get_sync_db() as db:
        return ToolRegistry.get_pending_case_tasks(db, case_id)


@tool
def detect_stalled_case(case_id: str, days_threshold: int = 5) -> Dict[str, Any]:
    """Check if a case has stalled with no recorded touchpoints or progress."""
    with get_sync_db() as db:
        return ToolRegistry.detect_stalled_case(db, case_id, days_threshold)


@tool
def notify_case_owner(case_id: str, priority: str, message: str) -> Dict[str, Any]:
    """Dispatch an actionable alert notification to the accountable Care Coordinator."""
    with get_sync_db() as db:
        return ToolRegistry.notify_case_owner(db, case_id, priority, message)


@tool
def escalate_unowned_case(case_id: str, reason: str) -> Dict[str, Any]:
    """Place an unowned case into UNASSIGNED_ESCALATED state for urgent administrative intervention."""
    with get_sync_db() as db:
        return ToolRegistry.escalate_unowned_case(db, case_id, reason)


@tool
def get_case_closure_requirements(case_id: str) -> Dict[str, Any]:
    """Evaluate whether all coordination tasks, evidence, and clinical sign-offs are satisfied for closure."""
    with get_sync_db() as db:
        return ToolRegistry.get_case_closure_requirements(db, case_id)


# ==============================================================================
# Complete Modular AI Tool Ecosystem
# ==============================================================================
MODULAR_ECOSYSTEM_TOOLS = [
    # Patient
    retrieve_patient_profile,
    retrieve_patient_preferences,
    retrieve_conversation_history,
    # Case
    create_care_case,
    retrieve_case_details,
    retrieve_case_events,
    update_case_notes,
    assign_administrative_ownership,
    # Communication
    draft_patient_message,
    translate_message,
    send_permitted_communication,
    record_acknowledgement,
    # Referral
    create_referral_request,
    check_referral_status,
    retrieve_referral_information,
    # Appointment
    search_available_appointments,
    book_appointment,
    reschedule_appointment,
    retrieve_appointment_status,
    # Recovery
    create_followup_task,
    identify_stalled_cases,
    propose_recovery_action,
    escalate_case,
    # Closure
    retrieve_closure_evidence,
    request_closure_verification,
]

# Supervisor Tools: includes modular ecosystem tools + legacy tools
SUPERVISOR_TOOLS = MODULAR_ECOSYSTEM_TOOLS + [
    get_patient_context,
    get_case_status,
    get_screening_result,
    get_referral_status,
    search_appointments,
    cancel_appointment,
    record_case_event,
    get_case_owner,
    assign_case_owner,
    transfer_case_ownership,
    get_pending_case_tasks,
    detect_stalled_case,
    notify_case_owner,
    escalate_unowned_case,
    get_case_closure_requirements,
]
