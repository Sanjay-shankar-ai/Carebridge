"""
CareBridge Agent Tool Schemas
Strongly-typed Pydantic input and output models for all modular CareBridge tools.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator


# ==============================================================================
# 1. Patient Tool Schemas
# ==============================================================================
class RetrievePatientProfileInput(BaseModel):
    patient_id: str = Field(description="UUID of the patient")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role executing the request")


class PatientProfileOutput(BaseModel):
    patient_id: str
    mrn: str
    first_name: str
    last_name: str
    date_of_birth: Optional[str] = None
    gender: str
    phone: Optional[str] = None
    email: Optional[str] = None
    preferred_language: str
    communication_channel: str
    accessibility_requirements: Dict[str, Any] = Field(default_factory=dict)
    known_barriers: List[str] = Field(default_factory=list)


class RetrievePatientPreferencesInput(BaseModel):
    patient_id: str = Field(description="UUID of the patient")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role executing the request")


class PatientPreferencesOutput(BaseModel):
    patient_id: str
    preferred_language: str
    communication_channel: str
    accessibility_requirements: Dict[str, Any] = Field(default_factory=dict)
    caregiver_name: Optional[str] = None
    caregiver_phone: Optional[str] = None
    active_consents: List[str] = Field(default_factory=list)


class RetrieveConversationHistoryInput(BaseModel):
    patient_id: str = Field(description="UUID of the patient")
    case_id: Optional[str] = Field(default=None, description="Optional case UUID filter")
    limit: int = Field(default=20, description="Max messages to return")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role executing the request")


class MessageItem(BaseModel):
    id: str
    sender: str
    channel: str
    content: str
    translated_content: Optional[str] = None
    language: str
    sent_at: Optional[str] = None
    acknowledged: bool


class ConversationHistoryOutput(BaseModel):
    patient_id: str
    messages: List[MessageItem]
    total_messages: int
    session_summary: Optional[str] = None
    unanswered_questions: List[str] = Field(default_factory=list)


# ==============================================================================
# 2. Case Tool Schemas
# ==============================================================================
class CreateCareCaseInput(BaseModel):
    patient_id: str = Field(description="UUID of the patient")
    screening_result_id: str = Field(description="UUID of the abnormal screening finding")
    clinical_pathway: Optional[str] = Field(default=None, description="Clinical pathway name")
    priority: str = Field(default="standard", description="'standard', 'urgent', 'critical'")
    initial_owner_id: Optional[str] = Field(default=None, description="Designated Care Coordinator UUID")
    actor_role: Optional[str] = Field(default="care_coordinator", description="Role creating the case")


class CareCaseOutput(BaseModel):
    case_id: str
    case_number: str
    patient_id: str
    screening_result_id: str
    current_owner_id: Optional[str] = None
    status: str
    priority: str
    clinical_pathway: Optional[str] = None
    sla_deadline: Optional[str] = None
    sla_status: str


class RetrieveCaseDetailsInput(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role executing the request")


class CaseDetailsOutput(BaseModel):
    case_id: str
    case_number: str
    patient_id: str
    current_owner_id: Optional[str] = None
    current_owner_name: Optional[str] = None
    status: str
    priority: str
    clinical_pathway: Optional[str] = None
    sla_deadline: Optional[str] = None
    sla_status: str
    is_closed: bool
    inferred_barriers: List[str] = Field(default_factory=list)
    recovery_attempts: int = 0


class RetrieveCaseEventsInput(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    limit: int = Field(default=50, description="Max events to return")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role executing the request")


class CaseEventItem(BaseModel):
    id: str
    event_type: str
    description: str
    event_data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str


class CaseEventsOutput(BaseModel):
    case_id: str
    events: List[CaseEventItem]
    total_events: int


class UpdateCaseNotesInput(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    note: str = Field(description="Progress note to append")
    barrier_detected: Optional[str] = Field(default=None, description="Optional barrier identified")
    actor_id: Optional[str] = Field(default="supervisor_agent", description="Actor identifier")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role updating notes")


class UpdateCaseNotesOutput(BaseModel):
    case_id: str
    note_added: str
    barrier_detected: Optional[str] = None
    updated_barriers: List[str] = Field(default_factory=list)


class AssignAdministrativeOwnershipInput(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    new_owner_id: str = Field(description="UUID of the Care Coordinator being assigned")
    assigned_by: str = Field(description="Name or ID of assigner")
    reason: str = Field(description="Operational rationale for assignment")
    actor_role: Optional[str] = Field(default="care_coordinator", description="Role performing assignment")


class AssignOwnershipOutput(BaseModel):
    case_id: str
    new_owner_id: str
    owner_name: str
    assigned_by: str
    reason: str
    effective_from: str


# ==============================================================================
# 3. Communication Tool Schemas
# ==============================================================================
class DraftPatientMessageInput(BaseModel):
    patient_id: str = Field(description="UUID of the patient")
    case_id: str = Field(description="UUID of the care case")
    message_purpose: str = Field(description="e.g. 'initial_notification', 'appointment_reminder', 'barrier_recovery'")
    clinical_context: Optional[str] = Field(default=None, description="Clinical summary for message calibration")
    language: Optional[str] = Field(default=None, description="Target language ('en', 'ta')")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role drafting message")


class DraftPatientMessageOutput(BaseModel):
    drafted_content: str
    language: str
    channel: str
    patient_name: str


class TranslateMessageInput(BaseModel):
    text: str = Field(description="Original message text to translate")
    target_language: str = Field(description="Target language code ('en', 'ta')")
    source_language: Optional[str] = Field(default="auto", description="Source language code")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role executing translation")


class TranslateMessageOutput(BaseModel):
    original_text: str
    translated_text: str
    source_language: str
    target_language: str


class SendPermittedCommunicationInput(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    patient_id: str = Field(description="UUID of the patient")
    content: str = Field(description="Message body to dispatch")
    channel: Optional[str] = Field(default=None, description="Channel ('sms', 'whatsapp', 'in_app_chat')")
    language: Optional[str] = Field(default="en", description="Message language")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role sending communication")


class SendPermittedCommunicationOutput(BaseModel):
    communication_id: str
    case_id: str
    patient_id: str
    channel: str
    language: str
    status: str
    sent_at: str


class RecordAcknowledgementInput(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    patient_id: str = Field(description="UUID of the patient")
    acknowledged_via: str = Field(default="sms", description="Channel of receipt")
    patient_response: Optional[str] = Field(default=None, description="Patient's message or confirmation text")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role recording acknowledgement")


class RecordAcknowledgementOutput(BaseModel):
    case_id: str
    patient_acknowledged: bool
    acknowledged_at: str
    completed_task_count: int


# ==============================================================================
# 4. Referral Tool Schemas
# ==============================================================================
class CreateReferralRequestInput(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    patient_id: str = Field(description="UUID of the patient")
    target_facility: str = Field(description="Facility receiving the referral")
    specialty: str = Field(description="Clinical specialty requested")
    reason: Optional[str] = Field(default=None, description="Clinical reason based on screening finding")
    reason_for_referral: Optional[str] = Field(default=None, description="Clinical reason alias")
    actor_role: Optional[str] = Field(default="care_coordinator", description="Role creating referral")

    @model_validator(mode="after")
    def set_reason(self) -> "CreateReferralRequestInput":
        if not self.reason and self.reason_for_referral:
            self.reason = self.reason_for_referral
        elif not self.reason:
            self.reason = "Clinical referral based on screening finding"
        return self


class ReferralRequestOutput(BaseModel):
    referral_id: str
    case_id: str
    patient_id: str
    target_facility: str
    specialty: str
    status: str
    acceptance_deadline: str


class CheckReferralStatusInput(BaseModel):
    referral_id: str = Field(description="UUID of the referral")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role checking referral")


class ReferralStatusOutput(BaseModel):
    referral_id: str
    case_id: str
    status: str
    target_facility: str
    specialty: str
    acceptance_deadline: Optional[str] = None
    responded_at: Optional[str] = None
    is_overdue: bool


class RetrieveReferralInformationInput(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role retrieving referral info")


class ReferralInformationOutput(BaseModel):
    case_id: str
    active_referral: Optional[Dict[str, Any]] = None
    all_referrals: List[Dict[str, Any]] = Field(default_factory=list)
    referral_count: int


# ==============================================================================
# 5. Appointment Tool Schemas
# ==============================================================================
class SearchAvailableAppointmentsInput(BaseModel):
    facility: str = Field(description="Facility or clinic name")
    specialty: str = Field(description="Medical specialty")
    timeframe: Optional[str] = Field(default="next_14_days", description="Search window timeframe")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role searching slots")


class AvailableAppointmentsOutput(BaseModel):
    facility: str
    specialty: str
    slots: List[str]


class BookAppointmentInput(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    patient_id: str = Field(description="UUID of the patient")
    facility: str = Field(description="Healthcare facility")
    scheduled_time: str = Field(description="ISO-8601 formatted datetime")
    appointment_type: str = Field(description="e.g. 'diagnostic_evaluation', 'biopsy', 'consultation'")
    provider_name: Optional[str] = Field(default="Specialist Clinician", description="Provider name")
    notes: Optional[str] = Field(default=None, description="Scheduling notes")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role booking appointment")


class BookAppointmentOutput(BaseModel):
    appointment_id: str
    case_id: str
    patient_id: str
    facility: str
    scheduled_time: str
    status: str
    appointment_type: str


class RescheduleAppointmentInput(BaseModel):
    appointment_id: str = Field(description="UUID of the appointment to reschedule")
    case_id: str = Field(description="UUID of the care case")
    new_scheduled_time: str = Field(description="ISO-8601 formatted new datetime")
    reason: str = Field(description="Mandatory reason for rescheduling")
    notes: Optional[str] = Field(default=None, description="Optional rescheduling context")
    actor_role: Optional[str] = Field(default="care_coordinator", description="Role rescheduling")


class RescheduleAppointmentOutput(BaseModel):
    previous_appointment_id: str
    new_appointment_id: str
    case_id: str
    new_scheduled_time: str
    reason: str
    requires_dual_acceptance: bool


class RetrieveAppointmentStatusInput(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role retrieving appointment status")


class AppointmentStatusOutput(BaseModel):
    case_id: str
    active_appointment: Optional[Dict[str, Any]] = None
    all_appointments: List[Dict[str, Any]] = Field(default_factory=list)
    has_attended: bool


# ==============================================================================
# 6. Recovery Tool Schemas
# ==============================================================================
class CreateFollowupTaskInput(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    title: str = Field(description="Actionable task title")
    description: str = Field(description="Detailed task instructions")
    task_type: str = Field(description="'patient_outreach', 'referral_followup', 'recovery_play', 'clinical_followup'")
    due_date: str = Field(description="ISO-8601 formatted due date")
    assigned_role: Optional[str] = Field(default="care_coordinator", description="Assigned role")
    assigned_to_id: Optional[str] = Field(default=None, description="Specific owner UUID")
    actor_role: Optional[str] = Field(default="care_coordinator", description="Role creating task")


class FollowupTaskOutput(BaseModel):
    task_id: str
    case_id: str
    title: str
    status: str
    due_date: str
    assigned_role: str


class IdentifyStalledCasesInput(BaseModel):
    case_id: Optional[str] = Field(default=None, description="Optional single case UUID to inspect")
    days_threshold: int = Field(default=5, description="Days of inactivity threshold")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role identifying stalled cases")


class StalledCaseItem(BaseModel):
    case_id: str
    case_number: str
    days_inactive: float
    last_activity_at: str
    accountable_owner: Optional[str] = None
    recommendation: str


class StalledCasesOutput(BaseModel):
    stalled: bool
    stalled_case_count: int
    cases: List[StalledCaseItem]


class ProposeRecoveryActionInput(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    dropoff_reasons: Optional[List[str]] = Field(default=None, description="Optional dropoff reason codes")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role proposing recovery")


class RecoveryActionOutput(BaseModel):
    case_id: str
    recommended_strategy: str
    action_plan: str
    recovery_attempts: int
    escalation_recommended: bool


class EscalateCaseInput(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    urgency: str = Field(default="urgent", description="'urgent', 'critical'")
    reason: str = Field(description="Mandatory rationale for escalation")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role escalating case")


class EscalateCaseOutput(BaseModel):
    case_id: str
    status: str
    priority: str
    escalation_reason: str
    escalated_at: str


# ==============================================================================
# 7. Closure Tool Schemas
# ==============================================================================
class RetrieveClosureEvidenceInput(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role retrieving closure evidence")


class ClosureEvidenceItem(BaseModel):
    id: str
    evidence_type: str
    evidence_summary: str
    verifying_clinician_id: Optional[str] = None
    is_verified: bool
    verified_at: Optional[str] = None


class ClosureEvidenceOutput(BaseModel):
    case_id: str
    evidences: List[ClosureEvidenceItem]
    has_verified_signoff: bool
    checklist_status: Dict[str, bool]


class RequestClosureVerificationInput(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    evidence_type: str = Field(description="'pathology_report', 'clinical_verification', 'imaging_surveillance'")
    evidence_summary: str = Field(description="Detailed clinical summary supporting closure")
    clinician_id: str = Field(description="UUID of attending clinician required to sign off")
    actor_role: Optional[str] = Field(default="ai_coordinator", description="Role requesting verification")


class RequestClosureVerificationOutput(BaseModel):
    evidence_id: str
    case_id: str
    clinician_id: str
    is_verified: bool
    requires_human_approval: bool
    message: str
