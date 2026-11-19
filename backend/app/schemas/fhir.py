"""
CareBridge HL7 FHIR R4 Pydantic Schemas
Conforms to HL7 FHIR Release 4 (v4.0.1) specification.
Provides type validation, serialization, and structure definitions for core clinical resources.
"""

from typing import List, Optional, Dict, Any, Union, Literal
from pydantic import BaseModel, Field


class FHIRCoding(BaseModel):
    system: Optional[str] = None
    version: Optional[str] = None
    code: Optional[str] = None
    display: Optional[str] = None
    userSelected: Optional[bool] = None


class FHIRCodeableConcept(BaseModel):
    coding: Optional[List[FHIRCoding]] = None
    text: Optional[str] = None


class FHIRIdentifier(BaseModel):
    use: Optional[str] = None # "usual" | "official" | "temp" | "secondary" | "old"
    type: Optional[FHIRCodeableConcept] = None
    system: Optional[str] = None
    value: Optional[str] = None


class FHIRHumanName(BaseModel):
    use: Optional[str] = None # "usual" | "official" | "temp" | "nickname" | "anonymous" | "old" | "maiden"
    text: Optional[str] = None
    family: Optional[str] = None
    given: Optional[List[str]] = None
    prefix: Optional[List[str]] = None
    suffix: Optional[List[str]] = None


class FHIRContactPoint(BaseModel):
    system: Optional[str] = None # "phone" | "fax" | "email" | "pager" | "url" | "sms" | "other"
    value: Optional[str] = None
    use: Optional[str] = None # "home" | "work" | "temp" | "old" | "mobile"


class FHIRPeriod(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None


class FHIRReference(BaseModel):
    reference: Optional[str] = None
    type: Optional[str] = None
    identifier: Optional[FHIRIdentifier] = None
    display: Optional[str] = None


class FHIRNarrative(BaseModel):
    status: str = "generated"
    div: str


class FHIRMeta(BaseModel):
    versionId: Optional[str] = "1"
    lastUpdated: Optional[str] = None
    profile: Optional[List[str]] = None


# =============================================================================
# 1. Patient Resource
# =============================================================================

class FHIRPatientCommunication(BaseModel):
    language: FHIRCodeableConcept
    preferred: Optional[bool] = True


class FHIRPatient(BaseModel):
    resourceType: Literal["Patient"] = "Patient"
    id: str
    meta: Optional[FHIRMeta] = None
    text: Optional[FHIRNarrative] = None
    identifier: Optional[List[FHIRIdentifier]] = None
    active: bool = True
    name: Optional[List[FHIRHumanName]] = None
    telecom: Optional[List[FHIRContactPoint]] = None
    gender: Optional[str] = None # "male" | "female" | "other" | "unknown"
    birthDate: Optional[str] = None
    communication: Optional[List[FHIRPatientCommunication]] = None


# =============================================================================
# 2. DiagnosticReport Resource
# =============================================================================

class FHIRDiagnosticReport(BaseModel):
    resourceType: Literal["DiagnosticReport"] = "DiagnosticReport"
    id: str
    meta: Optional[FHIRMeta] = None
    text: Optional[FHIRNarrative] = None
    status: str = "final" # "registered" | "preliminary" | "final" | "amended" | "corrected" | "appended" | "cancelled" | "entered-in-error" | "unknown"
    category: Optional[List[FHIRCodeableConcept]] = None
    code: FHIRCodeableConcept
    subject: FHIRReference
    effectiveDateTime: Optional[str] = None
    issued: Optional[str] = None
    performer: Optional[List[FHIRReference]] = None
    conclusion: Optional[str] = None
    conclusionCode: Optional[List[FHIRCodeableConcept]] = None


# =============================================================================
# 3. ServiceRequest Resource (Referral / Diagnostic Request)
# =============================================================================

class FHIRServiceRequest(BaseModel):
    resourceType: Literal["ServiceRequest"] = "ServiceRequest"
    id: str
    meta: Optional[FHIRMeta] = None
    text: Optional[FHIRNarrative] = None
    status: str = "active" # "draft" | "active" | "on-hold" | "revoked" | "completed" | "entered-in-error" | "unknown"
    intent: str = "order" # "proposal" | "plan" | "directive" | "order" | "original-order" | "reflex-order" | "filler-order" | "instance-order" | "option"
    priority: Optional[str] = "urgent" # "routine" | "urgent" | "asap" | "stat"
    category: Optional[List[FHIRCodeableConcept]] = None
    code: Optional[FHIRCodeableConcept] = None
    subject: FHIRReference
    authoredOn: Optional[str] = None
    requester: Optional[FHIRReference] = None
    performer: Optional[List[FHIRReference]] = None
    reasonCode: Optional[List[FHIRCodeableConcept]] = None
    supportingInfo: Optional[List[FHIRReference]] = None


# =============================================================================
# 4. Task Resource (Care Coordination / Recovery)
# =============================================================================

class FHIRTask(BaseModel):
    resourceType: Literal["Task"] = "Task"
    id: str
    meta: Optional[FHIRMeta] = None
    text: Optional[FHIRNarrative] = None
    status: str = "requested" # "draft" | "requested" | "received" | "accepted" | "rejected" | "ready" | "cancelled" | "in-progress" | "on-hold" | "failed" | "completed" | "entered-in-error"
    intent: str = "order"
    priority: Optional[str] = "routine" # "routine" | "urgent" | "asap" | "stat"
    code: Optional[FHIRCodeableConcept] = None
    description: Optional[str] = None
    focus: Optional[FHIRReference] = None
    for_: Optional[FHIRReference] = Field(None, alias="for")
    executionPeriod: Optional[FHIRPeriod] = None
    authoredOn: Optional[str] = None
    lastModified: Optional[str] = None
    owner: Optional[FHIRReference] = None

    class Config:
        populate_by_name = True


# =============================================================================
# 5. Appointment Resource
# =============================================================================

class FHIRAppointmentParticipant(BaseModel):
    actor: Optional[FHIRReference] = None
    required: Optional[str] = "required"
    status: str = "accepted" # "accepted" | "declined" | "tentative" | "needs-action"


class FHIRAppointment(BaseModel):
    resourceType: Literal["Appointment"] = "Appointment"
    id: str
    meta: Optional[FHIRMeta] = None
    text: Optional[FHIRNarrative] = None
    status: str = "booked" # "proposed" | "pending" | "booked" | "arrived" | "fulfilled" | "cancelled" | "noshow" | "entered-in-error" | "checked-in" | "waitlist"
    serviceType: Optional[List[FHIRCodeableConcept]] = None
    description: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    created: Optional[str] = None
    comment: Optional[str] = None
    cancelationReason: Optional[FHIRCodeableConcept] = None
    participant: List[FHIRAppointmentParticipant] = Field(default_factory=list)


# =============================================================================
# 6. Communication Resource
# =============================================================================

class FHIRCommunicationPayload(BaseModel):
    contentString: Optional[str] = None


class FHIRCommunication(BaseModel):
    resourceType: Literal["Communication"] = "Communication"
    id: str
    meta: Optional[FHIRMeta] = None
    text: Optional[FHIRNarrative] = None
    status: str = "completed" # "preparation" | "in-progress" | "not-done" | "on-hold" | "stopped" | "completed" | "entered-in-error" | "unknown"
    category: Optional[List[FHIRCodeableConcept]] = None
    medium: Optional[List[FHIRCodeableConcept]] = None
    subject: Optional[FHIRReference] = None
    recipient: Optional[List[FHIRReference]] = None
    sender: Optional[FHIRReference] = None
    sent: Optional[str] = None
    payload: Optional[List[FHIRCommunicationPayload]] = None


# =============================================================================
# 7. Consent Resource
# =============================================================================

class FHIRConsentProvision(BaseModel):
    type: str = "permit" # "deny" | "permit"
    period: Optional[FHIRPeriod] = None


class FHIRConsent(BaseModel):
    resourceType: Literal["Consent"] = "Consent"
    id: str
    meta: Optional[FHIRMeta] = None
    text: Optional[FHIRNarrative] = None
    status: str = "active" # "draft" | "proposed" | "active" | "rejected" | "inactive" | "entered-in-error"
    scope: FHIRCodeableConcept
    category: List[FHIRCodeableConcept]
    patient: FHIRReference
    dateTime: Optional[str] = None
    provision: Optional[FHIRConsentProvision] = None


# =============================================================================
# 8. AuditEvent Resource
# =============================================================================

class FHIRAuditEventAgent(BaseModel):
    type: Optional[FHIRCodeableConcept] = None
    who: Optional[FHIRReference] = None
    requestor: bool = True


class FHIRAuditEventEntity(BaseModel):
    what: Optional[FHIRReference] = None
    type: Optional[FHIRCoding] = None


class FHIRAuditEvent(BaseModel):
    resourceType: Literal["AuditEvent"] = "AuditEvent"
    id: str
    meta: Optional[FHIRMeta] = None
    text: Optional[FHIRNarrative] = None
    type: FHIRCoding
    subtype: Optional[List[FHIRCoding]] = None
    action: Optional[str] = None # "C" | "R" | "U" | "D" | "E"
    recorded: str
    outcome: Optional[str] = "0" # "0" (Success) | "4" (Minor failure) | "8" (Serious failure) | "12" (Major failure)
    outcomeDesc: Optional[str] = None
    agent: List[FHIRAuditEventAgent] = Field(default_factory=list)
    entity: Optional[List[FHIRAuditEventEntity]] = None


# =============================================================================
# Bundle and CapabilityStatement Resources
# =============================================================================

class FHIRBundleEntry(BaseModel):
    fullUrl: Optional[str] = None
    resource: Dict[str, Any]


class FHIRBundle(BaseModel):
    resourceType: Literal["Bundle"] = "Bundle"
    id: str
    type: str = "searchset" # "searchset" | "collection" | "transaction"
    total: int = 0
    entry: List[FHIRBundleEntry] = Field(default_factory=list)


class FHIRCapabilityResource(BaseModel):
    type: str
    interaction: List[Dict[str, str]]
    searchParam: Optional[List[Dict[str, str]]] = None


class FHIRCapabilityStatement(BaseModel):
    resourceType: Literal["CapabilityStatement"] = "CapabilityStatement"
    id: str = "carebridge-fhir-r4"
    status: str = "active"
    date: str
    publisher: str = "CareBridge Interoperability Platform"
    kind: str = "instance"
    software: Dict[str, str] = Field(default_factory=lambda: {"name": "CareBridge FHIR Engine", "version": "1.0.0"})
    fhirVersion: str = "4.0.1"
    format: List[str] = Field(default_factory=lambda: ["application/fhir+json", "application/json"])
    rest: List[Dict[str, Any]]


class FHIROperationOutcomeIssue(BaseModel):
    severity: str = "error" # "fatal" | "error" | "warning" | "information"
    code: str = "processing"
    diagnostics: str


class FHIROperationOutcome(BaseModel):
    resourceType: Literal["OperationOutcome"] = "OperationOutcome"
    issue: List[FHIROperationOutcomeIssue]
