"""
CareBridge HL7 FHIR Interoperability Service
Transforms PostgreSQL relational entities to official HL7 FHIR Release 4 (v4.0.1) resources.
Enforces patient privacy boundaries, role-based authorization, and FHIR validation rules.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from fastapi import HTTPException, status

from app.models import (
    Patient, ScreeningResult, Referral, Task, Appointment,
    Communication, Consent, AuditLog, CareCase, CaseOwner, User
)
from app.schemas.fhir import (
    FHIRPatient, FHIRDiagnosticReport, FHIRServiceRequest, FHIRTask,
    FHIRAppointment, FHIRCommunication, FHIRConsent, FHIRAuditEvent,
    FHIRBundle, FHIRBundleEntry, FHIRCapabilityStatement,
    FHIRCodeableConcept, FHIRCoding, FHIRIdentifier, FHIRHumanName,
    FHIRContactPoint, FHIRPeriod, FHIRReference, FHIRNarrative, FHIRMeta,
    FHIRPatientCommunication, FHIRAppointmentParticipant,
    FHIRCommunicationPayload, FHIRConsentProvision,
    FHIRAuditEventAgent, FHIRAuditEventEntity, FHIROperationOutcome,
    FHIROperationOutcomeIssue
)
from app.core.security import UserPrincipal


class FHIRService:
    """Core translation and authorization engine for HL7 FHIR R4 interoperability."""

    # =========================================================================
    # 1. Transformers: PostgreSQL -> FHIR R4
    # =========================================================================

    @classmethod
    def patient_to_fhir(cls, p: Patient) -> FHIRPatient:
        """Transforms CareBridge Patient model into HL7 FHIR Patient resource."""
        telecoms = []
        if p.phone:
            telecoms.append(FHIRContactPoint(system="phone", value=p.phone, use="mobile"))
        if p.email:
            telecoms.append(FHIRContactPoint(system="email", value=p.email, use="home"))

        lang_name = "Tamil" if p.preferred_language == "ta" else "English"
        comm = [
            FHIRPatientCommunication(
                language=FHIRCodeableConcept(
                    coding=[FHIRCoding(system="urn:ietf:bcp:47", code=p.preferred_language, display=lang_name)],
                    text=lang_name
                ),
                preferred=True
            )
        ]

        return FHIRPatient(
            id=str(p.id),
            meta=FHIRMeta(
                versionId="1",
                lastUpdated=p.updated_at.isoformat() if p.updated_at else datetime.now(timezone.utc).isoformat(),
                profile=["http://hl7.org/fhir/StructureDefinition/Patient"]
            ),
            text=FHIRNarrative(
                status="generated",
                div=f'<div xmlns="http://www.w3.org/1999/xhtml"><p><b>{p.first_name} {p.last_name}</b> (MRN: {p.mrn})</p></div>'
            ),
            identifier=[
                FHIRIdentifier(
                    use="official",
                    type=FHIRCodeableConcept(
                        coding=[FHIRCoding(system="http://terminology.hl7.org/CodeSystem/v2-0203", code="MR", display="Medical Record Number")],
                        text="Medical Record Number"
                    ),
                    system="https://carebridge.health/mrn",
                    value=p.mrn
                )
            ],
            active=True,
            name=[
                FHIRHumanName(
                    use="official",
                    family=p.last_name,
                    given=[p.first_name],
                    text=f"{p.first_name} {p.last_name}"
                )
            ],
            telecom=telecoms,
            gender=p.gender.lower() if p.gender in ("male", "female", "other", "unknown") else "unknown",
            birthDate=p.date_of_birth.isoformat() if hasattr(p.date_of_birth, "isoformat") else str(p.date_of_birth),
            communication=comm
        )

    @classmethod
    def screening_to_diagnostic_report(cls, sr: ScreeningResult) -> FHIRDiagnosticReport:
        """Transforms CareBridge ScreeningResult into HL7 FHIR DiagnosticReport resource."""
        loinc_code = "24606-6" if "mammogram" in sr.screening_type.lower() else "LP29684-5"
        
        return FHIRDiagnosticReport(
            id=str(sr.id),
            meta=FHIRMeta(
                versionId="1",
                lastUpdated=sr.updated_at.isoformat() if sr.updated_at else datetime.now(timezone.utc).isoformat(),
                profile=["http://hl7.org/fhir/StructureDefinition/DiagnosticReport"]
            ),
            text=FHIRNarrative(
                status="generated",
                div=f'<div xmlns="http://www.w3.org/1999/xhtml"><p>DiagnosticReport: {sr.screening_type} ({sr.finding_code})</p></div>'
            ),
            status="final",
            category=[
                FHIRCodeableConcept(
                    coding=[FHIRCoding(system="http://terminology.hl7.org/CodeSystem/v2-0074", code="RAD", display="Radiology")],
                    text="Radiology"
                )
            ],
            code=FHIRCodeableConcept(
                coding=[FHIRCoding(system="http://loinc.org", code=loinc_code, display=sr.screening_type)],
                text=sr.screening_type
            ),
            subject=FHIRReference(reference=f"Patient/{sr.patient_id}", type="Patient"),
            effectiveDateTime=sr.test_date.isoformat() if sr.test_date else None,
            issued=sr.created_at.isoformat() if sr.created_at else None,
            performer=[FHIRReference(display=sr.performing_facility)],
            conclusion=sr.finding_summary,
            conclusionCode=[
                FHIRCodeableConcept(
                    coding=[FHIRCoding(system="https://carebridge.health/findings", code=sr.finding_code, display=sr.finding_code)],
                    text=sr.finding_code
                )
            ]
        )

    @classmethod
    def referral_to_service_request(cls, ref: Referral) -> FHIRServiceRequest:
        """Transforms CareBridge Referral into HL7 FHIR ServiceRequest resource."""
        status_map = {
            "draft": "draft",
            "sent": "active",
            "accepted": "active",
            "completed": "completed",
            "rejected": "revoked",
            "rerouted": "active"
        }
        fhir_status = status_map.get(ref.status.lower(), "active")

        return FHIRServiceRequest(
            id=str(ref.id),
            meta=FHIRMeta(
                versionId="1",
                lastUpdated=ref.updated_at.isoformat() if ref.updated_at else datetime.now(timezone.utc).isoformat(),
                profile=["http://hl7.org/fhir/StructureDefinition/ServiceRequest"]
            ),
            text=FHIRNarrative(
                status="generated",
                div=f'<div xmlns="http://www.w3.org/1999/xhtml"><p>Referral: {ref.specialty} to {ref.target_facility}</p></div>'
            ),
            status=fhir_status,
            intent="order",
            priority="urgent",
            category=[
                FHIRCodeableConcept(
                    coding=[FHIRCoding(system="http://snomed.info/sct", code="103693007", display="Diagnostic procedure")],
                    text="Diagnostic procedure"
                )
            ],
            code=FHIRCodeableConcept(
                coding=[FHIRCoding(system="https://carebridge.health/specialties", code=ref.specialty, display=ref.specialty)],
                text=ref.specialty
            ),
            subject=FHIRReference(reference=f"Patient/{ref.patient_id}", type="Patient"),
            authoredOn=ref.created_at.isoformat() if ref.created_at else None,
            requester=FHIRReference(display=ref.referring_provider),
            performer=[FHIRReference(display=ref.target_facility)],
            reasonCode=[FHIRCodeableConcept(text=ref.reason_for_referral)],
            supportingInfo=[FHIRReference(reference=f"CareCase/{ref.case_id}")]
        )

    @classmethod
    def task_to_fhir(cls, task: Task) -> FHIRTask:
        """Transforms CareBridge Task into HL7 FHIR Task resource."""
        status_map = {
            "pending": "requested",
            "in_progress": "in-progress",
            "completed": "completed",
            "cancelled": "cancelled",
            "overdue": "failed"
        }
        fhir_status = status_map.get(task.status.lower(), "requested")
        is_urgent = "urgent" in task.title.lower() or "critical" in task.title.lower()

        patient_ref = None
        if task.care_case and task.care_case.patient_id:
            patient_ref = FHIRReference(reference=f"Patient/{task.care_case.patient_id}", type="Patient")

        owner_ref = None
        if task.assigned_to_id:
            owner_ref = FHIRReference(reference=f"Practitioner/{task.assigned_to_id}", display=task.assigned_role)
        else:
            owner_ref = FHIRReference(display=task.assigned_role)

        return FHIRTask(
            id=str(task.id),
            meta=FHIRMeta(
                versionId="1",
                lastUpdated=task.updated_at.isoformat() if task.updated_at else datetime.now(timezone.utc).isoformat(),
                profile=["http://hl7.org/fhir/StructureDefinition/Task"]
            ),
            text=FHIRNarrative(
                status="generated",
                div=f'<div xmlns="http://www.w3.org/1999/xhtml"><p>Task: {task.title} ({task.status})</p></div>'
            ),
            status=fhir_status,
            intent="order",
            priority="urgent" if is_urgent else "routine",
            code=FHIRCodeableConcept(
                coding=[FHIRCoding(system="https://carebridge.health/task-types", code=task.task_type, display=task.title)],
                text=task.title
            ),
            description=task.description,
            for_=patient_ref,
            executionPeriod=FHIRPeriod(end=task.due_date.isoformat() if task.due_date else None),
            authoredOn=task.created_at.isoformat() if task.created_at else None,
            lastModified=task.updated_at.isoformat() if task.updated_at else None,
            owner=owner_ref
        )

    @classmethod
    def appointment_to_fhir(cls, appt: Appointment) -> FHIRAppointment:
        """Transforms CareBridge Appointment into HL7 FHIR Appointment resource."""
        status_map = {
            "booked": "booked",
            "confirmed": "booked",
            "attended": "fulfilled",
            "no_show": "noshow",
            "cancelled": "cancelled",
            "rescheduled": "cancelled"
        }
        fhir_status = status_map.get(appt.status.lower(), "pending")

        start_time = appt.scheduled_time
        end_time = start_time + timedelta(minutes=45) if start_time else None

        participants = [
            FHIRAppointmentParticipant(
                actor=FHIRReference(reference=f"Patient/{appt.patient_id}", type="Patient"),
                status="accepted"
            ),
            FHIRAppointmentParticipant(
                actor=FHIRReference(display=appt.provider_name),
                status="accepted"
            ),
            FHIRAppointmentParticipant(
                actor=FHIRReference(display=appt.facility),
                status="accepted"
            )
        ]

        cancel_reason = None
        if appt.cancellation_reason:
            cancel_reason = FHIRCodeableConcept(text=appt.cancellation_reason)

        return FHIRAppointment(
            id=str(appt.id),
            meta=FHIRMeta(
                versionId="1",
                lastUpdated=appt.updated_at.isoformat() if appt.updated_at else datetime.now(timezone.utc).isoformat(),
                profile=["http://hl7.org/fhir/StructureDefinition/Appointment"]
            ),
            text=FHIRNarrative(
                status="generated",
                div=f'<div xmlns="http://www.w3.org/1999/xhtml"><p>Appointment: {appt.appointment_type} with {appt.provider_name}</p></div>'
            ),
            status=fhir_status,
            serviceType=[
                FHIRCodeableConcept(
                    coding=[FHIRCoding(system="https://carebridge.health/appointment-types", code=appt.appointment_type, display=appt.appointment_type)],
                    text=appt.appointment_type
                )
            ],
            description=f"{appt.appointment_type.capitalize()} at {appt.facility}",
            start=start_time.isoformat() if start_time else None,
            end=end_time.isoformat() if end_time else None,
            created=appt.created_at.isoformat() if appt.created_at else None,
            comment=appt.notes,
            cancelationReason=cancel_reason,
            participant=participants
        )

    @classmethod
    def communication_to_fhir(cls, comm: Communication) -> FHIRCommunication:
        """Transforms CareBridge Communication into HL7 FHIR Communication resource."""
        is_from_patient = comm.sender.lower() == "patient"
        sender_ref = FHIRReference(reference=f"Patient/{comm.patient_id}", type="Patient") if is_from_patient else FHIRReference(display=comm.sender)
        recipient_refs = [FHIRReference(display="Care Team")] if is_from_patient else [FHIRReference(reference=f"Patient/{comm.patient_id}", type="Patient")]

        payloads = [FHIRCommunicationPayload(contentString=comm.content)]
        if comm.translated_content:
            payloads.append(FHIRCommunicationPayload(contentString=f"Translated: {comm.translated_content}"))

        return FHIRCommunication(
            id=str(comm.id),
            meta=FHIRMeta(
                versionId="1",
                lastUpdated=comm.updated_at.isoformat() if comm.updated_at else datetime.now(timezone.utc).isoformat(),
                profile=["http://hl7.org/fhir/StructureDefinition/Communication"]
            ),
            text=FHIRNarrative(
                status="generated",
                div=f'<div xmlns="http://www.w3.org/1999/xhtml"><p>Communication via {comm.channel}: {comm.content[:60]}...</p></div>'
            ),
            status="completed",
            category=[
                FHIRCodeableConcept(
                    coding=[FHIRCoding(system="http://terminology.hl7.org/CodeSystem/communication-category", code="notification", display="Notification")],
                    text="Notification"
                )
            ],
            medium=[
                FHIRCodeableConcept(
                    coding=[FHIRCoding(system="http://terminology.hl7.org/CodeSystem/v3-ParticipationMode", code="WRITTEN", display=comm.channel)],
                    text=comm.channel
                )
            ],
            subject=FHIRReference(reference=f"Patient/{comm.patient_id}", type="Patient"),
            recipient=recipient_refs,
            sender=sender_ref,
            sent=comm.sent_at.isoformat() if comm.sent_at else None,
            payload=payloads
        )

    @classmethod
    def consent_to_fhir(cls, c: Consent) -> FHIRConsent:
        """Transforms CareBridge Consent into HL7 FHIR Consent resource."""
        fhir_status = "active" if c.status.lower() == "active" else ("inactive" if c.status.lower() == "revoked" else "draft")

        period = FHIRPeriod(
            start=c.granted_at.isoformat() if c.granted_at else None,
            end=c.expires_at.isoformat() if c.expires_at else None
        )

        return FHIRConsent(
            id=str(c.id),
            meta=FHIRMeta(
                versionId="1",
                lastUpdated=c.updated_at.isoformat() if c.updated_at else datetime.now(timezone.utc).isoformat(),
                profile=["http://hl7.org/fhir/StructureDefinition/Consent"]
            ),
            text=FHIRNarrative(
                status="generated",
                div=f'<div xmlns="http://www.w3.org/1999/xhtml"><p>Consent: {c.scope} ({c.status})</p></div>'
            ),
            status=fhir_status,
            scope=FHIRCodeableConcept(
                coding=[FHIRCoding(system="http://terminology.hl7.org/CodeSystem/consentscope", code="patient-privacy", display="Privacy Consent")],
                text="Privacy Consent"
            ),
            category=[
                FHIRCodeableConcept(
                    coding=[FHIRCoding(system="https://carebridge.health/consent-categories", code=c.scope, display=c.scope)],
                    text=c.scope
                )
            ],
            patient=FHIRReference(reference=f"Patient/{c.patient_id}", type="Patient"),
            dateTime=c.granted_at.isoformat() if c.granted_at else None,
            provision=FHIRConsentProvision(
                type="permit" if c.status.lower() == "active" else "deny",
                period=period
            )
        )

    @classmethod
    def audit_to_audit_event(cls, a: AuditLog) -> FHIRAuditEvent:
        """Transforms CareBridge AuditLog into HL7 FHIR AuditEvent resource."""
        action_map = {
            "CREATE": "C",
            "READ": "R",
            "UPDATE": "U",
            "DELETE": "D",
            "EXECUTE": "E"
        }
        action_code = "E"
        for key in action_map:
            if key in a.action.upper():
                action_code = action_map[key]
                break

        entities = []
        if a.patient_id:
            entities.append(FHIRAuditEventEntity(
                what=FHIRReference(reference=f"Patient/{a.patient_id}", type="Patient")
            ))
        elif a.case_id:
            entities.append(FHIRAuditEventEntity(
                what=FHIRReference(reference=f"CareCase/{a.case_id}", type="CareCase")
            ))
        else:
            entities.append(FHIRAuditEventEntity(
                what=FHIRReference(reference="CareBridge/System", display="CareBridge Clinical System")
            ))

        return FHIRAuditEvent(
            id=str(a.id),
            meta=FHIRMeta(
                versionId="1",
                lastUpdated=a.updated_at.isoformat() if a.updated_at else datetime.now(timezone.utc).isoformat(),
                profile=["http://hl7.org/fhir/StructureDefinition/AuditEvent"]
            ),
            text=FHIRNarrative(
                status="generated",
                div=f'<div xmlns="http://www.w3.org/1999/xhtml"><p>AuditEvent: {a.action} by {a.actor_type}</p></div>'
            ),
            type=FHIRCoding(
                system="http://terminology.hl7.org/CodeSystem/audit-event-type",
                code="rest",
                display="RESTful Operation"
            ),
            subtype=[
                FHIRCoding(
                    system="https://carebridge.health/audit-actions",
                    code=a.action,
                    display=a.action
                )
            ],
            action=action_code,
            recorded=a.timestamp.isoformat() if a.timestamp else datetime.now(timezone.utc).isoformat(),
            outcome="0",
            outcomeDesc=a.rationale,
            agent=[
                FHIRAuditEventAgent(
                    type=FHIRCodeableConcept(
                        coding=[FHIRCoding(system="http://terminology.hl7.org/CodeSystem/extra-security-role-type", code=a.actor_type, display=a.actor_type)]
                    ),
                    who=FHIRReference(
                        identifier=FHIRIdentifier(value=a.actor_id),
                        display=f"{a.actor_type}:{a.actor_id}"
                    ),
                    requestor=True
                )
            ],
            entity=entities
        )

    # =========================================================================
    # 2. Bundle Packaging & Capability Statement
    # =========================================================================

    @classmethod
    def wrap_bundle(cls, resource_type: str, entries: List[Dict[str, Any]], base_url: str = "") -> Dict[str, Any]:
        """Wraps search results in a standard HL7 FHIR R4 Bundle searchset."""
        bundle_id = f"bundle-{uuid.uuid4().hex[:8]}"
        bundle_entries = [
            {
                "fullUrl": f"{base_url}/api/v1/fhir/{resource_type}/{item.get('id')}",
                "resource": item
            }
            for item in entries
        ]
        return {
            "resourceType": "Bundle",
            "id": bundle_id,
            "type": "searchset",
            "total": len(entries),
            "entry": bundle_entries
        }

    @classmethod
    def get_capability_statement(cls) -> Dict[str, Any]:
        """Returns the official HL7 FHIR R4 CapabilityStatement describing server capabilities."""
        now_str = datetime.now(timezone.utc).isoformat()
        supported_resources = [
            "Patient", "DiagnosticReport", "ServiceRequest", "Task",
            "Appointment", "Communication", "Consent", "AuditEvent"
        ]
        resource_declarations = [
            {
                "type": r,
                "interaction": [
                    {"code": "read"},
                    {"code": "search-type"}
                ],
                "searchParam": [
                    {"name": "_id", "type": "token"},
                    {"name": "patient", "type": "reference"}
                ]
            }
            for r in supported_resources
        ]

        return {
            "resourceType": "CapabilityStatement",
            "id": "carebridge-fhir-r4",
            "status": "active",
            "date": now_str,
            "publisher": "CareBridge Interoperability Platform",
            "kind": "instance",
            "software": {
                "name": "CareBridge FHIR R4 Interoperability Engine",
                "version": "1.0.0"
            },
            "implementation": {
                "description": "CareBridge Closed-Loop Diagnostic Navigation Platform FHIR Endpoint",
                "url": "http://127.0.0.1:8000/api/v1/fhir"
            },
            "fhirVersion": "4.0.1",
            "format": ["application/fhir+json", "application/json"],
            "rest": [
                {
                    "mode": "server",
                    "documentation": "CareBridge HL7 FHIR R4 RESTful API supporting Patient Journey Navigation.",
                    "security": {
                        "cors": True,
                        "service": [
                            {
                                "coding": [
                                    {
                                        "system": "http://terminology.hl7.org/CodeSystem/restful-security-service",
                                        "code": "SMART-on-FHIR",
                                        "display": "SMART-on-FHIR / OAuth2 Bearer Token"
                                    }
                                ]
                            }
                        ]
                    },
                    "resource": resource_declarations
                }
            ]
        }

    # =========================================================================
    # 3. Security, Access Authorization, and Audit Dispatch
    # =========================================================================

    @classmethod
    def enforce_patient_isolation(cls, patient_id_str: str, current_user: UserPrincipal, resource_type: str):
        """
        Enforces strict patient isolation.
        Patients may ONLY access resources pertaining to their own patient profile.
        """
        if current_user.role == "patient":
            if not current_user.patient_id or str(current_user.patient_id) != str(patient_id_str):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Forbidden: You do not have permission to access another patient's {resource_type} resource."
                )

    @classmethod
    def log_fhir_access(cls, db: Session, resource_type: str, resource_id: str, current_user: UserPrincipal, patient_id: Optional[uuid.UUID] = None):
        """Records a persistent HIPAA-compliant AuditLog in PostgreSQL for FHIR access."""
        try:
            audit = AuditLog(
                id=uuid.uuid4(),
                patient_id=patient_id,
                actor_type=current_user.role,
                actor_id=str(current_user.user_id),
                action=f"FHIR_READ_{resource_type.upper()}",
                autonomy_level=1,
                new_state={"resource_type": resource_type, "resource_id": resource_id},
                rationale=f"User {current_user.email} ({current_user.role}) accessed FHIR {resource_type}/{resource_id}.",
                timestamp=datetime.now(timezone.utc)
            )
            db.add(audit)
            db.commit()
        except Exception:
            db.rollback()

    # =========================================================================
    # 4. Resource Retrieval & Search Methods
    # =========================================================================

    @classmethod
    def get_patient(cls, db: Session, patient_id: uuid.UUID, current_user: UserPrincipal) -> Dict[str, Any]:
        """Retrieves FHIR Patient by UUID."""
        p = db.query(Patient).filter(Patient.id == patient_id).first()
        if not p:
            raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")

        cls.enforce_patient_isolation(str(p.id), current_user, "Patient")
        cls.log_fhir_access(db, "Patient", str(p.id), current_user, patient_id=p.id)
        return cls.patient_to_fhir(p).model_dump(by_alias=True)

    @classmethod
    def search_patients(cls, db: Session, current_user: UserPrincipal, mrn: Optional[str] = None, name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Searches FHIR Patients with role filtering."""
        query = db.query(Patient)
        if current_user.role == "patient":
            if not current_user.patient_id:
                return []
            query = query.filter(Patient.id == uuid.UUID(current_user.patient_id))
        else:
            if mrn:
                query = query.filter(Patient.mrn.ilike(f"%{mrn}%"))
            if name:
                query = query.filter((Patient.first_name.ilike(f"%{name}%")) | (Patient.last_name.ilike(f"%{name}%")))

        patients = query.limit(50).all()
        return [cls.patient_to_fhir(p).model_dump(by_alias=True) for p in patients]

    @classmethod
    def get_diagnostic_report(cls, db: Session, report_id: uuid.UUID, current_user: UserPrincipal) -> Dict[str, Any]:
        """Retrieves FHIR DiagnosticReport by UUID."""
        sr = db.query(ScreeningResult).filter(ScreeningResult.id == report_id).first()
        if not sr:
            raise HTTPException(status_code=404, detail=f"DiagnosticReport {report_id} not found")

        cls.enforce_patient_isolation(str(sr.patient_id), current_user, "DiagnosticReport")
        cls.log_fhir_access(db, "DiagnosticReport", str(sr.id), current_user, patient_id=sr.patient_id)
        return cls.screening_to_diagnostic_report(sr).model_dump(by_alias=True)

    @classmethod
    def search_diagnostic_reports(cls, db: Session, current_user: UserPrincipal, patient_id: Optional[uuid.UUID] = None) -> List[Dict[str, Any]]:
        """Searches DiagnosticReports."""
        query = db.query(ScreeningResult)
        if current_user.role == "patient":
            if not current_user.patient_id:
                return []
            query = query.filter(ScreeningResult.patient_id == uuid.UUID(current_user.patient_id))
        elif patient_id:
            query = query.filter(ScreeningResult.patient_id == patient_id)

        reports = query.order_by(ScreeningResult.test_date.desc()).limit(50).all()
        return [cls.screening_to_diagnostic_report(sr).model_dump(by_alias=True) for sr in reports]

    @classmethod
    def get_service_request(cls, db: Session, req_id: uuid.UUID, current_user: UserPrincipal) -> Dict[str, Any]:
        """Retrieves FHIR ServiceRequest by UUID."""
        ref = db.query(Referral).filter(Referral.id == req_id).first()
        if not ref:
            raise HTTPException(status_code=404, detail=f"ServiceRequest {req_id} not found")

        cls.enforce_patient_isolation(str(ref.patient_id), current_user, "ServiceRequest")
        cls.log_fhir_access(db, "ServiceRequest", str(ref.id), current_user, patient_id=ref.patient_id)
        return cls.referral_to_service_request(ref).model_dump(by_alias=True)

    @classmethod
    def search_service_requests(cls, db: Session, current_user: UserPrincipal, patient_id: Optional[uuid.UUID] = None, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Searches ServiceRequests."""
        query = db.query(Referral)
        if current_user.role == "patient":
            if not current_user.patient_id:
                return []
            query = query.filter(Referral.patient_id == uuid.UUID(current_user.patient_id))
        elif patient_id:
            query = query.filter(Referral.patient_id == patient_id)

        if status_filter:
            query = query.filter(Referral.status == status_filter)

        refs = query.order_by(Referral.created_at.desc()).limit(50).all()
        return [cls.referral_to_service_request(r).model_dump(by_alias=True) for r in refs]

    @classmethod
    def get_task(cls, db: Session, task_id: uuid.UUID, current_user: UserPrincipal) -> Dict[str, Any]:
        """Retrieves FHIR Task by UUID."""
        t = db.query(Task).filter(Task.id == task_id).first()
        if not t:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        if t.care_case and t.care_case.patient_id:
            cls.enforce_patient_isolation(str(t.care_case.patient_id), current_user, "Task")

        cls.log_fhir_access(db, "Task", str(t.id), current_user, patient_id=t.care_case.patient_id if t.care_case else None)
        return cls.task_to_fhir(t).model_dump(by_alias=True)

    @classmethod
    def search_tasks(cls, db: Session, current_user: UserPrincipal, patient_id: Optional[uuid.UUID] = None, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Searches Tasks."""
        query = db.query(Task).join(CareCase, Task.case_id == CareCase.id)
        if current_user.role == "patient":
            if not current_user.patient_id:
                return []
            query = query.filter(CareCase.patient_id == uuid.UUID(current_user.patient_id))
        elif patient_id:
            query = query.filter(CareCase.patient_id == patient_id)

        if status_filter:
            query = query.filter(Task.status == status_filter)

        tasks = query.order_by(Task.created_at.desc()).limit(50).all()
        return [cls.task_to_fhir(t).model_dump(by_alias=True) for t in tasks]

    @classmethod
    def get_appointment(cls, db: Session, appt_id: uuid.UUID, current_user: UserPrincipal) -> Dict[str, Any]:
        """Retrieves FHIR Appointment by UUID."""
        a = db.query(Appointment).filter(Appointment.id == appt_id).first()
        if not a:
            raise HTTPException(status_code=404, detail=f"Appointment {appt_id} not found")

        cls.enforce_patient_isolation(str(a.patient_id), current_user, "Appointment")
        cls.log_fhir_access(db, "Appointment", str(a.id), current_user, patient_id=a.patient_id)
        return cls.appointment_to_fhir(a).model_dump(by_alias=True)

    @classmethod
    def search_appointments(cls, db: Session, current_user: UserPrincipal, patient_id: Optional[uuid.UUID] = None, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Searches Appointments."""
        query = db.query(Appointment)
        if current_user.role == "patient":
            if not current_user.patient_id:
                return []
            query = query.filter(Appointment.patient_id == uuid.UUID(current_user.patient_id))
        elif patient_id:
            query = query.filter(Appointment.patient_id == patient_id)

        if status_filter:
            query = query.filter(Appointment.status == status_filter)

        appts = query.order_by(Appointment.scheduled_time.desc()).limit(50).all()
        return [cls.appointment_to_fhir(a).model_dump(by_alias=True) for a in appts]

    @classmethod
    def get_communication(cls, db: Session, comm_id: uuid.UUID, current_user: UserPrincipal) -> Dict[str, Any]:
        """Retrieves FHIR Communication by UUID."""
        c = db.query(Communication).filter(Communication.id == comm_id).first()
        if not c:
            raise HTTPException(status_code=404, detail=f"Communication {comm_id} not found")

        cls.enforce_patient_isolation(str(c.patient_id), current_user, "Communication")
        cls.log_fhir_access(db, "Communication", str(c.id), current_user, patient_id=c.patient_id)
        return cls.communication_to_fhir(c).model_dump(by_alias=True)

    @classmethod
    def search_communications(cls, db: Session, current_user: UserPrincipal, patient_id: Optional[uuid.UUID] = None) -> List[Dict[str, Any]]:
        """Searches Communications."""
        query = db.query(Communication)
        if current_user.role == "patient":
            if not current_user.patient_id:
                return []
            query = query.filter(Communication.patient_id == uuid.UUID(current_user.patient_id))
        elif patient_id:
            query = query.filter(Communication.patient_id == patient_id)

        comms = query.order_by(Communication.sent_at.desc()).limit(50).all()
        return [cls.communication_to_fhir(c).model_dump(by_alias=True) for c in comms]

    @classmethod
    def get_consent(cls, db: Session, consent_id: uuid.UUID, current_user: UserPrincipal) -> Dict[str, Any]:
        """Retrieves FHIR Consent by UUID."""
        c = db.query(Consent).filter(Consent.id == consent_id).first()
        if not c:
            raise HTTPException(status_code=404, detail=f"Consent {consent_id} not found")

        cls.enforce_patient_isolation(str(c.patient_id), current_user, "Consent")
        cls.log_fhir_access(db, "Consent", str(c.id), current_user, patient_id=c.patient_id)
        return cls.consent_to_fhir(c).model_dump(by_alias=True)

    @classmethod
    def search_consents(cls, db: Session, current_user: UserPrincipal, patient_id: Optional[uuid.UUID] = None) -> List[Dict[str, Any]]:
        """Searches Consents."""
        query = db.query(Consent)
        if current_user.role == "patient":
            if not current_user.patient_id:
                return []
            query = query.filter(Consent.patient_id == uuid.UUID(current_user.patient_id))
        elif patient_id:
            query = query.filter(Consent.patient_id == patient_id)

        consents = query.order_by(Consent.granted_at.desc()).limit(50).all()
        return [cls.consent_to_fhir(c).model_dump(by_alias=True) for c in consents]

    @classmethod
    def get_audit_event(cls, db: Session, audit_id: uuid.UUID, current_user: UserPrincipal) -> Dict[str, Any]:
        """Retrieves FHIR AuditEvent by UUID."""
        a = db.query(AuditLog).filter(AuditLog.id == audit_id).first()
        if not a:
            raise HTTPException(status_code=404, detail=f"AuditEvent {audit_id} not found")

        if a.patient_id:
            cls.enforce_patient_isolation(str(a.patient_id), current_user, "AuditEvent")

        return cls.audit_to_audit_event(a).model_dump(by_alias=True)

    @classmethod
    def search_audit_events(cls, db: Session, current_user: UserPrincipal, patient_id: Optional[uuid.UUID] = None, action_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Searches AuditEvents."""
        query = db.query(AuditLog)
        if current_user.role == "patient":
            if not current_user.patient_id:
                return []
            query = query.filter(AuditLog.patient_id == uuid.UUID(current_user.patient_id))
        elif patient_id:
            query = query.filter(AuditLog.patient_id == patient_id)

        if action_filter:
            query = query.filter(AuditLog.action.ilike(f"%{action_filter}%"))

        logs = query.order_by(AuditLog.timestamp.desc()).limit(50).all()
        return [cls.audit_to_audit_event(a).model_dump(by_alias=True) for a in logs]

    # =========================================================================
    # 5. Inbound Validation: Rejection of Invalid / Malformed FHIR Payloads
    # =========================================================================

    @classmethod
    def validate_and_parse_inbound(cls, resource_type: str, payload: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validates incoming FHIR R4 payload against schema definitions."""
        if not isinstance(payload, dict):
            return False, "Payload must be a JSON object"

        if payload.get("resourceType") != resource_type:
            return False, f"Expected resourceType '{resource_type}', got '{payload.get('resourceType')}'"

        schema_map = {
            "Patient": FHIRPatient,
            "DiagnosticReport": FHIRDiagnosticReport,
            "ServiceRequest": FHIRServiceRequest,
            "Task": FHIRTask,
            "Appointment": FHIRAppointment,
            "Communication": FHIRCommunication,
            "Consent": FHIRConsent,
            "AuditEvent": FHIRAuditEvent
        }

        schema_cls = schema_map.get(resource_type)
        if not schema_cls:
            return False, f"Unsupported FHIR resource type '{resource_type}'"

        try:
            schema_cls(**payload)
            return True, None
        except Exception as e:
            return False, str(e)
