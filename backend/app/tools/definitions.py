"""
CareBridge Tool Definitions and Structured Argument Schemas
16 Standard Care Coordination Tools with Pydantic validation.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ------------------------------------------------------------------------------
# 1. Context & History Tools
# ------------------------------------------------------------------------------
class GetPatientContextArgs(BaseModel):
    patient_id: str = Field(description="UUID of the patient")

class GetCaseStatusArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case to check status and SLA")

class GetScreeningResultArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case to retrieve screening findings")

class GetReferralStatusArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case to check referral handoff status")

class GetCaseHistoryArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case")

class UpdateCaseNotesArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    note: str = Field(description="Clinical or administrative progress note")
    barrier_detected: Optional[str] = Field(
        default=None,
        description="Optional social/logistical barrier identified (e.g., 'transportation', 'childcare', 'fear')"
    )

class CreateCareCaseArgs(BaseModel):
    patient_id: str = Field(description="UUID of the patient")
    screening_result_id: str = Field(description="UUID of the screening finding")
    clinical_pathway: str = Field(description="Assigned clinical pathway name")
    priority: str = Field(default="standard", description="'standard', 'urgent', 'critical'")


# ------------------------------------------------------------------------------
# 2. Patient Communication & Translation Tools
# ------------------------------------------------------------------------------
class SendPatientMessageArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    patient_id: str = Field(description="UUID of the patient")
    message: str = Field(description="Message body adapted to patient language and literacy")
    language: str = Field(default="en", description="Target language ('en', 'ta', 'mixed')")
    channel: str = Field(default="sms", description="Communication channel ('sms', 'whatsapp', 'in_app_chat')")

class TranslateMessageArgs(BaseModel):
    text: str = Field(description="Original message text")
    source_language: str = Field(default="auto", description="Source language code")
    target_language: str = Field(description="Target language code ('en', 'ta')")


# ------------------------------------------------------------------------------
# 3. Appointments & Scheduling Tools
# ------------------------------------------------------------------------------
class SearchAvailableAppointmentsArgs(BaseModel):
    facility: str = Field(description="Healthcare facility or clinic name")
    specialty: str = Field(description="Medical specialty or department")
    timeframe: Optional[str] = Field(default="next_14_days", description="Search window timeframe")

class SearchAppointmentsArgs(BaseModel):
    facility: str = Field(description="Healthcare facility or clinic name")
    specialty: str = Field(description="Medical specialty or department")
    timeframe: Optional[str] = Field(default="next_14_days", description="Search window timeframe")

class BookAppointmentArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    patient_id: str = Field(description="UUID of the patient")
    facility: str = Field(description="Facility name where slot is reserved")
    scheduled_time: str = Field(description="ISO-8601 formatted datetime of appointment")
    appointment_type: str = Field(description="'consultation', 'biopsy', 'ultrasound', 'surveillance'")
    notes: Optional[str] = Field(default=None, description="Clinical or scheduling notes")

class CancelAppointmentArgs(BaseModel):
    appointment_id: str = Field(description="UUID of the appointment to cancel")
    case_id: str = Field(description="UUID of the associated care case")
    reason: str = Field(description="Specific cancellation reason (e.g. 'caregiver_transport_unavailable', 'patient_unwell', 'patient_refused')")
    outcome: str = Field(
        default="reschedule_pending",
        description="Structured outcome path: 'reschedule_pending', 'recovery_play_initiated', 'escalated_to_coordinator', 'care_declined'"
    )
    detailed_notes: Optional[str] = Field(default=None, description="Explanatory notes regarding the cancellation")


# ------------------------------------------------------------------------------
# 4. Referral Tools
# ------------------------------------------------------------------------------
class CheckReferralStatusArgs(BaseModel):
    referral_id: str = Field(description="UUID of the referral")

class CreateReferralRequestArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    patient_id: str = Field(description="UUID of the patient")
    target_facility: str = Field(description="Recipient clinic or hospital facility")
    specialty: str = Field(description="Required specialty")
    reason: str = Field(description="Clinical reason based on screening finding")


# ------------------------------------------------------------------------------
# 5. Task & Workflow Tools
# ------------------------------------------------------------------------------
class CreateFollowupTaskArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    title: str = Field(description="Task title")
    description: str = Field(description="Actionable task instructions")
    task_type: str = Field(description="'patient_outreach', 'referral_followup', 'recovery_play', 'clinical_review'")
    due_date: str = Field(description="ISO-8601 formatted due date")
    assigned_role: str = Field(default="ai_coordinator", description="'ai_coordinator', 'care_coordinator', 'clinician'")

class RecordCaseEventArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    event_type: str = Field(description="Event category (e.g. 'patient_inquiry', 'barrier_identified', 'referral_checked')")
    description: str = Field(description="Summary of what occurred")
    event_data: Optional[Dict[str, Any]] = Field(default=None, description="Structured event payload")

class AssignCoordinatorArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    coordinator_id: str = Field(description="UUID of the designated human case owner")

# ------------------------------------------------------------------------------
# 5b. End-to-End Case Ownership Tools
# ------------------------------------------------------------------------------
class GetCaseOwnerArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case to query for the designated accountable owner")

class AssignCaseOwnerArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    new_owner_id: str = Field(description="UUID of the new accountable care coordinator")
    assigned_by: str = Field(description="Authorized user ID or supervisor role initiating assignment")
    reason: str = Field(description="Operational rationale for assignment")

class TransferCaseOwnershipArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    from_owner_id: str = Field(description="UUID of current owner relinquishing case")
    to_owner_id: str = Field(description="UUID of incoming owner accepting accountability")
    transferred_by: str = Field(description="Authorized user ID or supervisor role executing transfer")
    reason: str = Field(description="Audit explanation for transferring case ownership")

class GetPendingCaseTasksArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case to check incomplete tasks and overdue milestones")

class DetectStalledCaseArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case to evaluate for inactivity")
    days_threshold: int = Field(default=5, description="Number of inactive days before flagging case as stalled")

class NotifyCaseOwnerArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    priority: str = Field(default="urgent", description="'normal', 'urgent', 'critical'")
    message: str = Field(description="Actionable alert message for the designated care coordinator")

class EscalateUnownedCaseArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case lacking an accountable coordinator")
    reason: str = Field(description="Reason for unowned emergency escalation to administrative team")

class GetCaseClosureRequirementsArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case to verify closure readiness checklist")

class CalculateSLAArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case")

class EscalateCaseArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    urgency: str = Field(description="'urgent', 'critical'")
    reason: str = Field(description="Detailed reason for supervisor/clinical escalation")


# ------------------------------------------------------------------------------
# 6. Closure & Evidence Tools (Level 3 Human Authorized)
# ------------------------------------------------------------------------------
class RetrieveClosureEvidenceArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case")

class RequestClosureVerificationArgs(BaseModel):
    case_id: str = Field(description="UUID of the care case")
    evidence_type: str = Field(description="'pathology_report', 'consultation_note', 'imaging_surveillance'")
    evidence_summary: str = Field(description="Summary of clinical findings proving care completion")
    clinician_id: str = Field(description="UUID of the clinician requested to verify and sign off")
