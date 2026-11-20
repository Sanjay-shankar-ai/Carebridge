# CareBridge API Specification

Base URL: `/api/v1`

## Endpoints

### Health & Readiness
- `GET /health`: Liveness probe (root)
- `GET /api/v1/health`: Detailed service health probe and version metadata

### Care Cases
- `GET /api/v1/cases`: List active cases with owner and SLA statuses
- `POST /api/v1/cases`: Ingest actionable screening result (DiagnosticReport)
- `GET /api/v1/cases/{case_id}`: Retrieve comprehensive case timeline and memory

### Patients
- `GET /api/v1/patients`: List patients
- `GET /api/v1/patients/{patient_id}`: Retrieve patient profile, language preference, and history

### Appointments
- `GET /api/v1/appointments`: List appointments and status (booked, attended, no-show)
- `POST /api/v1/appointments`: Book or reschedule appointment

### Referrals
- `GET /api/v1/referrals`: List active specialist and clinic referrals
- `POST /api/v1/referrals`: Create referral request (FHIR ServiceRequest)

### Care Recovery
- `GET /api/v1/recovery`: List interrupted cases undergoing active recovery plays
- `POST /api/v1/recovery/trigger`: Manually trigger recovery playbook on stuck case
