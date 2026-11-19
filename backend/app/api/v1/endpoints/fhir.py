"""
CareBridge HL7 FHIR Interoperability API Endpoints
Implements HL7 FHIR Release 4 (v4.0.1) RESTful interface:
- GET /api/v1/fhir/metadata (CapabilityStatement)
- GET /api/v1/fhir/Patient/{id} and GET /api/v1/fhir/Patient
- GET /api/v1/fhir/DiagnosticReport/{id} and GET /api/v1/fhir/DiagnosticReport
- GET /api/v1/fhir/ServiceRequest/{id} and GET /api/v1/fhir/ServiceRequest
- GET /api/v1/fhir/Task/{id} and GET /api/v1/fhir/Task
- GET /api/v1/fhir/Appointment/{id} and GET /api/v1/fhir/Appointment
- GET /api/v1/fhir/Communication/{id} and GET /api/v1/fhir/Communication
- GET /api/v1/fhir/Consent/{id} and GET /api/v1/fhir/Consent
- GET /api/v1/fhir/AuditEvent/{id} and GET /api/v1/fhir/AuditEvent
- POST /api/v1/fhir/{resource_type}/$validate (FHIR validation endpoint)
- POST /api/v1/fhir/{resource_type} (Strict inbound submission with validation)
"""

import uuid
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Query, Path, Body, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database.session import get_sync_db
from app.core.security import get_current_user, UserPrincipal
from app.services.fhir_service import FHIRService

router = APIRouter(prefix="/fhir", tags=["HL7 FHIR Interoperability"])

FHIR_MEDIA_TYPE = "application/fhir+json; charset=utf-8"


def fhir_response(data: Dict[str, Any], status_code: int = 200) -> Response:
    """Returns standard FHIR JSON response with application/fhir+json content type."""
    import json
    return Response(
        content=json.dumps(data, indent=2),
        status_code=status_code,
        media_type=FHIR_MEDIA_TYPE
    )


def parse_uuid(val: str, resource_name: str) -> uuid.UUID:
    """Validates UUID format, raising 400 Bad Request on malformed identifiers."""
    try:
        return uuid.UUID(val)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {resource_name} ID '{val}'. Expected valid RFC 4122 UUID."
        )


# =============================================================================
# 0. Server Metadata / Capability Statement
# =============================================================================

@router.get("/metadata", summary="FHIR R4 CapabilityStatement")
async def get_capability_statement():
    """Returns the HL7 FHIR R4 CapabilityStatement describing supported interactions and resources."""
    cs = FHIRService.get_capability_statement()
    return fhir_response(cs)


# =============================================================================
# 1. Patient
# =============================================================================

@router.get("/Patient/{id}", summary="Read FHIR Patient")
async def get_patient(
    id: str = Path(..., description="Patient UUID"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Retrieves a single Patient resource by UUID."""
    p_uuid = parse_uuid(id, "Patient")
    patient = FHIRService.get_patient(db, p_uuid, current_user)
    return fhir_response(patient)


@router.get("/Patient", summary="Search FHIR Patients")
async def search_patients(
    request: Request,
    mrn: Optional[str] = Query(None, description="Filter by Medical Record Number"),
    name: Optional[str] = Query(None, description="Filter by patient name"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Searches Patient resources, returning a FHIR Bundle searchset."""
    patients = FHIRService.search_patients(db, current_user, mrn=mrn, name=name)
    base_url = str(request.base_url).rstrip("/")
    bundle = FHIRService.wrap_bundle("Patient", patients, base_url=base_url)
    return fhir_response(bundle)


# =============================================================================
# 2. DiagnosticReport
# =============================================================================

@router.get("/DiagnosticReport/{id}", summary="Read FHIR DiagnosticReport")
async def get_diagnostic_report(
    id: str = Path(..., description="ScreeningResult UUID"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Retrieves a single DiagnosticReport by UUID."""
    r_uuid = parse_uuid(id, "DiagnosticReport")
    report = FHIRService.get_diagnostic_report(db, r_uuid, current_user)
    return fhir_response(report)


@router.get("/DiagnosticReport", summary="Search FHIR DiagnosticReports")
async def search_diagnostic_reports(
    request: Request,
    patient: Optional[str] = Query(None, description="Filter by patient UUID"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Searches DiagnosticReports, returning a FHIR Bundle searchset."""
    p_uuid = parse_uuid(patient, "Patient") if patient else None
    reports = FHIRService.search_diagnostic_reports(db, current_user, patient_id=p_uuid)
    base_url = str(request.base_url).rstrip("/")
    bundle = FHIRService.wrap_bundle("DiagnosticReport", reports, base_url=base_url)
    return fhir_response(bundle)


# =============================================================================
# 3. ServiceRequest
# =============================================================================

@router.get("/ServiceRequest/{id}", summary="Read FHIR ServiceRequest")
async def get_service_request(
    id: str = Path(..., description="Referral UUID"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Retrieves a single ServiceRequest (referral) by UUID."""
    r_uuid = parse_uuid(id, "ServiceRequest")
    req = FHIRService.get_service_request(db, r_uuid, current_user)
    return fhir_response(req)


@router.get("/ServiceRequest", summary="Search FHIR ServiceRequests")
async def search_service_requests(
    request: Request,
    patient: Optional[str] = Query(None, description="Filter by patient UUID"),
    status: Optional[str] = Query(None, description="Filter by status (e.g. active, completed, draft)"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Searches ServiceRequests, returning a FHIR Bundle searchset."""
    p_uuid = parse_uuid(patient, "Patient") if patient else None
    requests = FHIRService.search_service_requests(db, current_user, patient_id=p_uuid, status_filter=status)
    base_url = str(request.base_url).rstrip("/")
    bundle = FHIRService.wrap_bundle("ServiceRequest", requests, base_url=base_url)
    return fhir_response(bundle)


# =============================================================================
# 4. Task
# =============================================================================

@router.get("/Task/{id}", summary="Read FHIR Task")
async def get_task(
    id: str = Path(..., description="Task UUID"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Retrieves a single Task by UUID."""
    t_uuid = parse_uuid(id, "Task")
    task = FHIRService.get_task(db, t_uuid, current_user)
    return fhir_response(task)


@router.get("/Task", summary="Search FHIR Tasks")
async def search_tasks(
    request: Request,
    patient: Optional[str] = Query(None, description="Filter by patient UUID"),
    status: Optional[str] = Query(None, description="Filter by status (e.g. requested, in-progress, completed)"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Searches Tasks, returning a FHIR Bundle searchset."""
    p_uuid = parse_uuid(patient, "Patient") if patient else None
    tasks = FHIRService.search_tasks(db, current_user, patient_id=p_uuid, status_filter=status)
    base_url = str(request.base_url).rstrip("/")
    bundle = FHIRService.wrap_bundle("Task", tasks, base_url=base_url)
    return fhir_response(bundle)


# =============================================================================
# 5. Appointment
# =============================================================================

@router.get("/Appointment/{id}", summary="Read FHIR Appointment")
async def get_appointment(
    id: str = Path(..., description="Appointment UUID"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Retrieves a single Appointment by UUID."""
    a_uuid = parse_uuid(id, "Appointment")
    appt = FHIRService.get_appointment(db, a_uuid, current_user)
    return fhir_response(appt)


@router.get("/Appointment", summary="Search FHIR Appointments")
async def search_appointments(
    request: Request,
    patient: Optional[str] = Query(None, description="Filter by patient UUID"),
    status: Optional[str] = Query(None, description="Filter by status (e.g. booked, fulfilled, cancelled)"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Searches Appointments, returning a FHIR Bundle searchset."""
    p_uuid = parse_uuid(patient, "Patient") if patient else None
    appts = FHIRService.search_appointments(db, current_user, patient_id=p_uuid, status_filter=status)
    base_url = str(request.base_url).rstrip("/")
    bundle = FHIRService.wrap_bundle("Appointment", appts, base_url=base_url)
    return fhir_response(bundle)


# =============================================================================
# 6. Communication
# =============================================================================

@router.get("/Communication/{id}", summary="Read FHIR Communication")
async def get_communication(
    id: str = Path(..., description="Communication UUID"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Retrieves a single Communication record by UUID."""
    c_uuid = parse_uuid(id, "Communication")
    comm = FHIRService.get_communication(db, c_uuid, current_user)
    return fhir_response(comm)


@router.get("/Communication", summary="Search FHIR Communications")
async def search_communications(
    request: Request,
    patient: Optional[str] = Query(None, description="Filter by patient UUID"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Searches Communication records, returning a FHIR Bundle searchset."""
    p_uuid = parse_uuid(patient, "Patient") if patient else None
    comms = FHIRService.search_communications(db, current_user, patient_id=p_uuid)
    base_url = str(request.base_url).rstrip("/")
    bundle = FHIRService.wrap_bundle("Communication", comms, base_url=base_url)
    return fhir_response(bundle)


# =============================================================================
# 7. Consent
# =============================================================================

@router.get("/Consent/{id}", summary="Read FHIR Consent")
async def get_consent(
    id: str = Path(..., description="Consent UUID"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Retrieves a single Consent record by UUID."""
    c_uuid = parse_uuid(id, "Consent")
    consent = FHIRService.get_consent(db, c_uuid, current_user)
    return fhir_response(consent)


@router.get("/Consent", summary="Search FHIR Consents")
async def search_consents(
    request: Request,
    patient: Optional[str] = Query(None, description="Filter by patient UUID"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Searches Consent records, returning a FHIR Bundle searchset."""
    p_uuid = parse_uuid(patient, "Patient") if patient else None
    consents = FHIRService.search_consents(db, current_user, patient_id=p_uuid)
    base_url = str(request.base_url).rstrip("/")
    bundle = FHIRService.wrap_bundle("Consent", consents, base_url=base_url)
    return fhir_response(bundle)


# =============================================================================
# 8. AuditEvent
# =============================================================================

@router.get("/AuditEvent/{id}", summary="Read FHIR AuditEvent")
async def get_audit_event(
    id: str = Path(..., description="AuditLog UUID"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Retrieves a single AuditEvent by UUID."""
    a_uuid = parse_uuid(id, "AuditEvent")
    audit = FHIRService.get_audit_event(db, a_uuid, current_user)
    return fhir_response(audit)


@router.get("/AuditEvent", summary="Search FHIR AuditEvents")
async def search_audit_events(
    request: Request,
    patient: Optional[str] = Query(None, description="Filter by patient UUID"),
    action: Optional[str] = Query(None, description="Filter by action keyword"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """Searches AuditEvents, returning a FHIR Bundle searchset."""
    p_uuid = parse_uuid(patient, "Patient") if patient else None
    audits = FHIRService.search_audit_events(db, current_user, patient_id=p_uuid, action_filter=action)
    base_url = str(request.base_url).rstrip("/")
    bundle = FHIRService.wrap_bundle("AuditEvent", audits, base_url=base_url)
    return fhir_response(bundle)


# =============================================================================
# 9. Validation & Safe Inbound Submission Gate
# =============================================================================

@router.post("/{resource_type}/validate", summary="Validate FHIR Resource")
@router.post("/{resource_type}/$validate", summary="Validate FHIR Resource ($validate)")
async def validate_fhir_resource(
    resource_type: str = Path(..., description="FHIR Resource Type"),
    payload: Dict[str, Any] = Body(..., description="FHIR resource payload")
):
    """
    Validates a FHIR resource against HL7 FHIR R4 schema rules.
    Returns OperationOutcome with diagnostics.
    """
    is_valid, error_msg = FHIRService.validate_and_parse_inbound(resource_type, payload)
    if is_valid:
        outcome = {
            "resourceType": "OperationOutcome",
            "issue": [
                {
                    "severity": "information",
                    "code": "informational",
                    "diagnostics": f"Resource conforms to HL7 FHIR R4 {resource_type} specification."
                }
            ]
        }
        return fhir_response(outcome, status_code=200)
    else:
        outcome = {
            "resourceType": "OperationOutcome",
            "issue": [
                {
                    "severity": "error",
                    "code": "structure",
                    "diagnostics": f"Validation failure: {error_msg}"
                }
            ]
        }
        return fhir_response(outcome, status_code=422)


@router.post("/{resource_type}", summary="Submit Inbound FHIR Resource")
async def submit_inbound_fhir_resource(
    resource_type: str = Path(..., description="FHIR Resource Type"),
    payload: Dict[str, Any] = Body(..., description="FHIR resource payload"),
    current_user: UserPrincipal = Depends(get_current_user),
    db: Session = Depends(get_sync_db)
):
    """
    Safely receives an inbound FHIR resource.
    Validates structural compliance and verifies actor authorization.
    Rejects unauthorized modifications or invalid payloads.
    """
    # 1. Structural Validation
    is_valid, error_msg = FHIRService.validate_and_parse_inbound(resource_type, payload)
    if not is_valid:
        outcome = {
            "resourceType": "OperationOutcome",
            "issue": [
                {
                    "severity": "error",
                    "code": "invalid",
                    "diagnostics": f"FHIR structural validation failed: {error_msg}"
                }
            ]
        }
        return fhir_response(outcome, status_code=422)

    # 2. Authorization Gate: Only Doctors and Care Coordinators can ingest external FHIR records
    if current_user.role not in ("doctor", "clinician", "care_coordinator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Inbound FHIR resource ingestion requires clinical authorization."
        )

    # 3. Provenance Audit Log
    FHIRService.log_fhir_access(
        db=db,
        resource_type=resource_type,
        resource_id=payload.get("id", "inbound-new"),
        current_user=current_user
    )

    return fhir_response(
        {
            "resourceType": "OperationOutcome",
            "issue": [
                {
                    "severity": "information",
                    "code": "informational",
                    "diagnostics": f"Inbound {resource_type} successfully validated and queued with clinical provenance."
                }
            ]
        },
        status_code=201
    )
