"""
Memory Schemas for Patient, Conversation, and Case Contexts
Defines structured, typed data objects for agentic reasoning without prompt bloat.
"""

import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class PatientMemoryContext(BaseModel):
    """Factual patient context: preferences, language, accessibility, social support."""
    patient_id: uuid.UUID
    mrn: str
    full_name: str
    phone: str
    preferred_language: str = Field(description="'en', 'ta', or 'mixed'")
    communication_channel: str = Field(description="'sms', 'whatsapp', 'in_app_chat'")
    accessibility_requirements: Dict[str, Any] = Field(default_factory=dict)
    known_barriers: List[str] = Field(default_factory=list)
    caregiver_name: Optional[str] = None
    caregiver_phone: Optional[str] = None
    active_consents: List[str] = Field(default_factory=list)


class MessageItem(BaseModel):
    id: uuid.UUID
    sender: str
    language: str
    channel: str
    content: str
    translated_content: Optional[str] = None
    acknowledged: bool
    sent_at: datetime


class ConversationMemoryContext(BaseModel):
    """Dialogue and relationship memory: commitments, unanswered questions, summaries."""
    session_id: Optional[uuid.UUID] = None
    patient_id: uuid.UUID
    case_id: Optional[uuid.UUID] = None
    recent_messages: List[MessageItem] = Field(default_factory=list)
    summary: Optional[str] = None
    unanswered_questions: List[str] = Field(default_factory=list)
    patient_commitments: List[Dict[str, Any]] = Field(default_factory=list)


class ReferralSummary(BaseModel):
    id: uuid.UUID
    target_facility: str
    specialty: str
    status: str
    acceptance_deadline: datetime
    rejection_reason: Optional[str] = None


class AppointmentSummary(BaseModel):
    id: uuid.UUID
    facility: str
    provider_name: str
    appointment_type: str
    scheduled_time: datetime
    status: str
    notes: Optional[str] = None


class TaskSummary(BaseModel):
    id: uuid.UUID
    title: str
    assigned_role: str
    status: str
    due_date: datetime


class CaseMemoryContext(BaseModel):
    """Complete case longitudinal memory: finding, owner, SLA clocks, referrals, evidence."""
    case_id: uuid.UUID
    patient_id: Optional[uuid.UUID] = None
    case_number: str
    status: str
    priority: str
    clinical_pathway: str
    current_owner_name: Optional[str] = None
    current_owner_role: Optional[str] = None
    
    # Screening finding
    screening_type: str
    finding_code: str
    finding_summary: str
    urgency_level: str
    
    # SLA timers
    sla_start_time: datetime
    sla_deadline: datetime
    sla_status: str
    
    # Case dynamics
    inferred_barriers: List[str] = Field(default_factory=list)
    recovery_attempts: int = 0
    last_recovery_strategy: Optional[str] = None
    patient_understanding_confirmed: bool = False
    
    # Related records
    active_referral: Optional[ReferralSummary] = None
    all_referrals: List[ReferralSummary] = Field(default_factory=list)
    upcoming_appointment: Optional[AppointmentSummary] = None
    appointment_history: List[AppointmentSummary] = Field(default_factory=list)
    pending_tasks: List[TaskSummary] = Field(default_factory=list)
    is_closed: bool = False
    closure_evidences: List[Dict[str, Any]] = Field(default_factory=list)
    
    # 14-Stage Lifecycle and Longitudinal Clinical Records
    lifecycle_stages: List[Dict[str, Any]] = Field(default_factory=list)
    current_stage_number: int = 1
    current_stage_id: str = "SCREENING"
    clinical_review: Optional[Dict[str, Any]] = None
    consultation_outcome: Optional[Dict[str, Any]] = None
    treatment_monitoring: Optional[Dict[str, Any]] = None
    follow_up: Optional[Dict[str, Any]] = None
    documentation_evidence: Optional[Dict[str, Any]] = None


class UnifiedCareContext(BaseModel):
    """Composite context passed to the LangGraph cognitive loop."""
    patient: PatientMemoryContext
    case: CaseMemoryContext
    conversation: ConversationMemoryContext
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now())
