import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const STAGE_DEFS = [
  { stage_number: 1, stage_id: "SCREENING", title: "Screening Examination", responsible_role: "Radiologist" },
  { stage_number: 2, stage_id: "RESULT_GENERATED", title: "Diagnostic Report Generated", responsible_role: "Radiologist" },
  { stage_number: 3, stage_id: "PATIENT_NOTIFIED", title: "Initial Patient Outreach", responsible_role: "Care Coordinator" },
  { stage_number: 4, stage_id: "PATIENT_UNDERSTANDS", title: "AI Case-Aware Education & Understanding", responsible_role: "AI Coordinator" },
  { stage_number: 5, stage_id: "CLINICAL_REVIEW", title: "Attending Physician Clinical Review", responsible_role: "Doctor" },
  { stage_number: 6, stage_id: "CLINICAL_CONFIRMATION_MESSAGE", title: "Clinical Confirmation & Next Steps", responsible_role: "Doctor" },
  { stage_number: 7, stage_id: "REFERRAL_INITIATED", title: "Specialist Referral Initiated", responsible_role: "Care Coordinator" },
  { stage_number: 8, stage_id: "REFERRAL_ACCEPTED", title: "Referral Formally Accepted", responsible_role: "Doctor" },
  { stage_number: 9, stage_id: "APPOINTMENT_SCHEDULED_CONFIRMED", title: "Appointment Scheduled & Confirmed", responsible_role: "Care Coordinator" },
  { stage_number: 10, stage_id: "CONSULTATION_COMPLETED", title: "Specialist Consultation Completed", responsible_role: "Doctor" },
  { stage_number: 11, stage_id: "TREATMENT_MONITORING", title: "Active Treatment & Progress Monitoring", responsible_role: "Doctor" },
  { stage_number: 12, stage_id: "FOLLOW_UP", title: "Follow-Up Evaluation & Surveillance", responsible_role: "Doctor" },
  { stage_number: 13, stage_id: "DOCUMENTATION_COMPLETED", title: "Care Documentation & Audit Complete", responsible_role: "Care Coordinator" },
  { stage_number: 14, stage_id: "VERIFIED_CLINICAL_CLOSURE", title: "Verified Clinical Closure Sign-Off", responsible_role: "Doctor" },
];

const DEMO_USERS: Record<string, any> = {
  "patient@carebridge.com": {
    id: "639ebc6a-e636-4ffd-9079-478a64419f4a",
    name: "Meera Krishnan",
    email: "patient@carebridge.com",
    role: "patient",
    facility: "Metropolitan Breast & Comprehensive Cancer Center",
    patient_id: "32d170d2-d44f-4e1f-aa89-0ef892d34c21",
    case_id: "c4c73484-2036-47cd-a415-1ddad41f57ee",
    phone: "+91-98401-22334",
    token: "cb-demo-jwt-patient",
  },
  "coordinator@carebridge.com": {
    id: "a33bc385-05df-4ea4-a96a-5a4a51308224",
    name: "Priya Nair, RN",
    email: "coordinator@carebridge.com",
    role: "care_coordinator",
    facility: "Metropolitan Breast & Comprehensive Cancer Center",
    patient_id: null,
    case_id: null,
    phone: "+91-98401-11000",
    token: "cb-demo-jwt-coordinator",
  },
  "doctor@carebridge.com": {
    id: "d8812345-1111-4222-8333-999999999999",
    name: "Dr. Arjun Menon, MD",
    email: "doctor@carebridge.com",
    role: "doctor",
    facility: "Metropolitan Specialty Breast & Diagnostic Clinic",
    patient_id: null,
    case_id: null,
    phone: "+91-98401-99887",
    token: "cb-demo-jwt-doctor",
  },
};

function buildStages(completedUpTo: number) {
  const now = new Date().toISOString();
  return STAGE_DEFS.map((d) => ({
    ...d,
    status:
      d.stage_number <= completedUpTo
        ? "completed"
        : d.stage_number === completedUpTo + 1
        ? "active"
        : "pending",
    completed_at: d.stage_number <= completedUpTo ? now : null,
    responsible_name:
      d.responsible_role === "Doctor"
        ? "Dr. Arjun Menon, MD"
        : d.responsible_role === "Care Coordinator"
        ? "Priya Nair, RN"
        : "CareBridge Clinical System",
  }));
}

const DEMO_CASES = [
  {
    id: "c4c73484-2036-47cd-a415-1ddad41f57ee",
    case_number: "CASE-2026-JUDGE01",
    patient_id: "32d170d2-d44f-4e1f-aa89-0ef892d34c21",
    patient_name: "Meera Krishnan",
    patient_phone: "+91-98401-22334",
    patient_language: "en",
    screening_type: "Mammogram",
    finding_code: "BI-RADS 4",
    finding_summary:
      "1.4 cm focal architectural distortion with clustered microcalcifications in the upper outer quadrant (BI-RADS 4 - Suspicious Abnormality).",
    status: "result_received",
    priority: "urgent",
    current_owner: "Priya Nair, RN",
    assigned_doctor: "Dr. Arjun Menon, MD",
    sla_deadline: new Date(Date.now() + 86400000 * 5).toISOString(),
    sla_status: "warning",
    inferred_barriers: ["Transportation (Pickup 60m prior)"],
    recovery_attempts: 1,
    created_at: new Date(Date.now() - 86400000 * 2).toISOString(),
  },
  {
    id: "a729b6a7-73be-42ee-8382-654352433ba8",
    case_number: "CASE-2026-0149",
    patient_id: "b1490000-0000-0000-0000-000000000149",
    patient_name: "Priya Sharma",
    patient_phone: "+91-98401-55667",
    patient_language: "en",
    screening_type: "Mammogram",
    finding_code: "BI-RADS 4",
    finding_summary: "Diagnostic core biopsy pathology confirmed benign fibroadenoma; 14/14 stages closed.",
    status: "closed",
    priority: "standard",
    current_owner: "Dr. Arjun Menon, MD",
    assigned_doctor: "Dr. Arjun Menon, MD",
    sla_deadline: new Date(Date.now() - 86400000).toISOString(),
    sla_status: "normal",
    inferred_barriers: ["Transportation (Resolved)"],
    recovery_attempts: 1,
    created_at: new Date(Date.now() - 86400000 * 7).toISOString(),
  },
];

const DEMO_COORDINATOR_PATIENTS = [
  {
    patient_id: "32d170d2-d44f-4e1f-aa89-0ef892d34c21",
    name: "Meera Krishnan",
    mrn: "MRN-2026-8841",
    phone: "+91-98401-22334",
    case_id: "c4c73484-2036-47cd-a415-1ddad41f57ee",
    case_number: "CASE-2026-JUDGE01",
    current_stage_number: 5,
    current_stage_title: "Attending Physician Clinical Review",
    status: "result_received",
    pending_action: "Coordinate Dr. Menon review & pickup ride",
    responsible_role: "care_coordinator",
    assigned_doctor: "Dr. Arjun Menon, MD",
    sla_status: "warning",
    sla_deadline: new Date(Date.now() + 86400000 * 5).toISOString(),
    needs_coordinator_action: true,
    last_updated: new Date(Date.now() - 1800000).toISOString(),
  },
  {
    patient_id: "b1490000-0000-0000-0000-000000000149",
    name: "Priya Sharma",
    mrn: "MRN-2026-0149",
    phone: "+91-98401-55667",
    case_id: "a729b6a7-73be-42ee-8382-654352433ba8",
    case_number: "CASE-2026-0149",
    current_stage_number: 14,
    current_stage_title: "Verified Clinical Closure Sign-Off",
    status: "closed",
    pending_action: "Verified clinical closure complete",
    responsible_role: "doctor",
    assigned_doctor: "Dr. Arjun Menon, MD",
    sla_status: "normal",
    sla_deadline: new Date(Date.now() - 86400000).toISOString(),
    needs_coordinator_action: false,
    last_updated: new Date(Date.now() - 86400000).toISOString(),
  },
];

const DEMO_APPOINTMENTS = [
  {
    id: "appt-judge01-v1",
    case_id: "c4c73484-2036-47cd-a415-1ddad41f57ee",
    patient_id: "32d170d2-d44f-4e1f-aa89-0ef892d34c21",
    patient_name: "Meera Krishnan",
    case_number: "CASE-2026-JUDGE01",
    facility: "Metropolitan Specialty Breast & Diagnostic Clinic",
    provider_name: "Dr. Arjun Menon, MD",
    appointment_type: "diagnostic_biopsy",
    scheduled_time: new Date(Date.now() + 86400000 * 2).toISOString(),
    status: "confirmed",
    version: 1,
    doctor_confirmed: true,
    patient_confirmed: true,
    notes: "Dual-confirmed v1 ultrasound-guided core needle biopsy consultation.",
  },
  {
    id: "appt-0149-v1",
    case_id: "a729b6a7-73be-42ee-8382-654352433ba8",
    patient_id: "b1490000-0000-0000-0000-000000000149",
    patient_name: "Priya Sharma",
    case_number: "CASE-2026-0149",
    facility: "Metropolitan Specialty Breast & Diagnostic Clinic",
    provider_name: "Dr. Arjun Menon, MD",
    appointment_type: "diagnostic_biopsy",
    scheduled_time: new Date(Date.now() - 86400000 * 3).toISOString(),
    status: "attended",
    version: 1,
    doctor_confirmed: true,
    patient_confirmed: true,
    attendance_recorded_at: new Date(Date.now() - 86400000 * 3).toISOString(),
    notes: "Biopsy consultation attended; pathology confirmed benign fibroadenoma.",
  },
];

const DEMO_REFERRALS = [
  {
    id: "ref-judge01-01",
    referral_number: "REF-2026-J01",
    case_id: "c4c73484-2036-47cd-a415-1ddad41f57ee",
    patient_id: "32d170d2-d44f-4e1f-aa89-0ef892d34c21",
    patient_name: "Meera Krishnan",
    case_number: "CASE-2026-JUDGE01",
    referring_provider: "Metropolitan Hospital Screening Center",
    target_facility: "Metropolitan Specialty Breast & Diagnostic Clinic",
    receiving_facility: "Metropolitan Specialty Breast & Diagnostic Clinic",
    specialty: "Breast Surgical Oncology & Diagnostic Biopsy",
    reason_for_referral: "BI-RADS 4 architectural distortion with clustered microcalcifications requiring core biopsy.",
    status: "accepted",
    acceptance_deadline: new Date(Date.now() + 86400000 * 2).toISOString(),
    responded_at: new Date(Date.now() - 3600000).toISOString(),
    created_at: new Date(Date.now() - 86400000).toISOString(),
  },
  {
    id: "ref-0149-01",
    referral_number: "REF-2026-0149",
    case_id: "a729b6a7-73be-42ee-8382-654352433ba8",
    patient_id: "b1490000-0000-0000-0000-000000000149",
    patient_name: "Priya Sharma",
    case_number: "CASE-2026-0149",
    referring_provider: "Metropolitan Hospital Screening Center",
    target_facility: "Metropolitan Specialty Breast & Diagnostic Clinic",
    receiving_facility: "Metropolitan Specialty Breast & Diagnostic Clinic",
    specialty: "Breast Surgical Oncology & Diagnostic Biopsy",
    reason_for_referral: "BI-RADS 4 diagnostic biopsy follow-up and pathology verification.",
    status: "completed",
    acceptance_deadline: new Date(Date.now() - 86400000 * 5).toISOString(),
    responded_at: new Date(Date.now() - 86400000 * 6).toISOString(),
    created_at: new Date(Date.now() - 86400000 * 7).toISOString(),
  },
];

const DEMO_EVENTS_BY_CASE: Record<string, any[]> = {
  "c4c73484-2036-47cd-a415-1ddad41f57ee": [
    {
      event_id: "evt-01",
      case_id: "c4c73484-2036-47cd-a415-1ddad41f57ee",
      event_type: "stage_1_screening_performed",
      description: "Stage 1 completed: Bilateral diagnostic mammogram recorded as performed.",
      timestamp: new Date(Date.now() - 3600000 * 5).toISOString(),
    },
    {
      event_id: "evt-02",
      case_id: "c4c73484-2036-47cd-a415-1ddad41f57ee",
      event_type: "stage_2_report_finalized",
      description: "Stage 2 completed: Synthetic PDF report validated and finalized (BI-RADS 4).",
      timestamp: new Date(Date.now() - 3600000 * 4).toISOString(),
    },
    {
      event_id: "evt-03",
      case_id: "c4c73484-2036-47cd-a415-1ddad41f57ee",
      event_type: "stage_3_patient_notified",
      description: "Stage 3 completed: Diagnostic result notification delivered to Meera Krishnan.",
      timestamp: new Date(Date.now() - 3600000 * 3).toISOString(),
    },
    {
      event_id: "evt-04",
      case_id: "c4c73484-2036-47cd-a415-1ddad41f57ee",
      event_type: "stage_4_report_explained",
      description: "Stage 4 completed: Plain-language AI report explanation persisted and delivered.",
      timestamp: new Date(Date.now() - 3600000 * 2).toISOString(),
    },
  ],
  "a729b6a7-73be-42ee-8382-654352433ba8": [
    {
      event_id: "evt-149-01",
      case_id: "a729b6a7-73be-42ee-8382-654352433ba8",
      event_type: "stage_2_report_finalized",
      description: "Diagnostic mammogram finalized (BI-RADS 4) and explained in plain language.",
      timestamp: new Date(Date.now() - 86400000 * 6).toISOString(),
    },
    {
      event_id: "evt-149-02",
      case_id: "a729b6a7-73be-42ee-8382-654352433ba8",
      event_type: "stage_8_referral_accepted",
      description: "Referral REF-2026-0149 accepted by Dr. Arjun Menon, MD.",
      timestamp: new Date(Date.now() - 86400000 * 5).toISOString(),
    },
    {
      event_id: "evt-149-03",
      case_id: "a729b6a7-73be-42ee-8382-654352433ba8",
      event_type: "stage_10_consultation_completed",
      description: "Diagnostic core biopsy completed; pathology confirmed benign fibroadenoma.",
      timestamp: new Date(Date.now() - 86400000 * 3).toISOString(),
    },
    {
      event_id: "evt-149-04",
      case_id: "a729b6a7-73be-42ee-8382-654352433ba8",
      event_type: "stage_14_verified_closure",
      description: "Verified clinical closure signed by Dr. Arjun Menon, MD with complete evidence audit.",
      timestamp: new Date(Date.now() - 86400000).toISOString(),
    },
  ],
};

const DEMO_RECOVERY_CASES = [
  {
    case_id: "c4c73484-2036-47cd-a415-1ddad41f57ee",
    id: "c4c73484-2036-47cd-a415-1ddad41f57ee",
    case_number: "CASE-2026-JUDGE01",
    patient_id: "32d170d2-d44f-4e1f-aa89-0ef892d34c21",
    patient_name: "Meera Krishnan",
    patient_phone: "+91-98401-22334",
    patient_language: "en",
    finding_code: "BI-RADS 4",
    status: "recovering",
    priority: "urgent",
    current_owner: "Priya Nair, RN",
    sla_deadline: new Date(Date.now() + 86400000 * 5).toISOString(),
    sla_status: "warning",
    recovery_attempts: 1,
    active_playbook: "transportation_support",
    barriers_detected: ["Transportation (Pickup 60m prior)", "Caregiver Availability"],
    inferred_barriers: ["Transportation (Pickup 60m prior)", "Caregiver Availability"],
    has_no_show: false,
    no_show_count: 0,
    last_recovery_timestamp: new Date(Date.now() - 3600000 * 2).toISOString(),
  },
];

const DEMO_NOTIFICATIONS = [
  {
    id: "notif-01",
    user_id: "639ebc6a-e636-4ffd-9079-478a64419f4a",
    role: "patient",
    event_type: "report_finalized",
    title: "Diagnostic Report Finalized: BI-RADS 4 (Mammogram)",
    message:
      "Your Mammogram report (BI-RADS 4) has been validated and finalized by Priya Nair, RN. Open CareBridge AI to review your plain-language explanation.",
    priority: "urgent",
    case_id: "c4c73484-2036-47cd-a415-1ddad41f57ee",
    action_link: "/chat",
    is_read: false,
    created_at: new Date(Date.now() - 1800000).toISOString(),
  },
  {
    id: "notif-02",
    user_id: "a33bc385-05df-4ea4-a96a-5a4a51308224",
    role: "care_coordinator",
    event_type: "screening_request_received",
    title: "New Screening Request: Meera Krishnan (CASE-2026-JUDGE01)",
    message: "Patient submitted a routine Mammogram screening request. Persisted task Schedule Screening created.",
    priority: "urgent",
    case_id: "c4c73484-2036-47cd-a415-1ddad41f57ee",
    action_link: "/cases/c4c73484-2036-47cd-a415-1ddad41f57ee",
    is_read: false,
    created_at: new Date(Date.now() - 3600000).toISOString(),
  },
];

const DEMO_OPERATIONAL_PRIORITIES = [
  {
    case_id: "c4c73484-2036-47cd-a415-1ddad41f57ee",
    case_number: "CASE-2026-JUDGE01",
    patient_id: "32d170d2-d44f-4e1f-aa89-0ef892d34c21",
    patient_name: "Meera Krishnan",
    patient_language: "en",
    patient_phone: "+91-98401-22334",
    current_owner: "Priya Nair, RN",
    current_owner_role: "care_coordinator",
    status: "result_received",
    priority: "urgent",
    sla_status: "warning",
    sla_deadline: new Date(Date.now() + 86400000 * 5).toISOString(),
    operational_risk_score: 76,
    priority_tier: "URGENT_FOLLOWUP",
    operational_reasons: [
      "Finalized BI-RADS 4 report awaiting specialist biopsy consultation within 14-day SLA window.",
      "Documented transportation barrier — 60-minute pre-appointment pickup coordination active.",
    ],
    why_prioritized: "BI-RADS 4 diagnostic biopsy SLA countdown with active transportation barrier",
    barriers_detected: ["transportation_support", "caregiver_coordination"],
    recovery_attempts: 1,
    disclaimer: "Administrative coordination priority score only; not clinical risk prediction.",
  },
  {
    case_id: "a729b6a7-73be-42ee-8382-654352433ba8",
    case_number: "CASE-2026-0149",
    patient_id: "b1490000-0000-0000-0000-000000000149",
    patient_name: "Priya Sharma",
    patient_language: "en",
    patient_phone: "+91-98401-55667",
    current_owner: "Dr. Arjun Menon, MD",
    current_owner_role: "doctor",
    status: "closed",
    priority: "standard",
    sla_status: "normal",
    sla_deadline: new Date(Date.now() - 86400000).toISOString(),
    operational_risk_score: 12,
    priority_tier: "ON_TRACK",
    operational_reasons: [
      "All 14 care lifecycle stages completed with physician-verified closure sign-off.",
    ],
    why_prioritized: "Closed and verified care pathway",
    barriers_detected: [],
    recovery_attempts: 1,
    disclaimer: "Administrative coordination priority score only; not clinical risk prediction.",
  },
];

function buildFhirBundle(resourceType: string) {
  const now = new Date().toISOString();
  const entriesByType: Record<string, any[]> = {
    Patient: [
      {
        resource: {
          resourceType: "Patient",
          id: "32d170d2-d44f-4e1f-aa89-0ef892d34c21",
          active: true,
          identifier: [{ system: "urn:carebridge:mrn", value: "MRN-2026-8841" }],
          name: [{ text: "Meera Krishnan", family: "Krishnan", given: ["Meera"] }],
          gender: "female",
          birthDate: "1978-06-14",
          telecom: [{ system: "phone", value: "+91-98401-22334" }],
          communication: [{ language: { text: "en" }, preferred: true }],
        },
      },
      {
        resource: {
          resourceType: "Patient",
          id: "b1490000-0000-0000-0000-000000000149",
          active: true,
          identifier: [{ system: "urn:carebridge:mrn", value: "MRN-2026-0149" }],
          name: [{ text: "Priya Sharma", family: "Sharma", given: ["Priya"] }],
          gender: "female",
          birthDate: "1981-02-22",
          telecom: [{ system: "phone", value: "+91-98401-55667" }],
          communication: [{ language: { text: "en" }, preferred: true }],
        },
      },
    ],
    DiagnosticReport: [
      {
        resource: {
          resourceType: "DiagnosticReport",
          id: "rpt-judge01",
          status: "final",
          code: { text: "Bilateral Diagnostic Mammogram (BI-RADS 4)" },
          subject: { reference: "Patient/32d170d2-d44f-4e1f-aa89-0ef892d34c21", display: "Meera Krishnan" },
          effectiveDateTime: now,
          conclusion: DEMO_CASES[0].finding_summary,
        },
      },
    ],
    ServiceRequest: [
      {
        resource: {
          resourceType: "ServiceRequest",
          id: "ref-judge01-01",
          status: "active",
          intent: "order",
          code: { text: "Breast Surgical Oncology & Diagnostic Biopsy" },
          subject: { reference: "Patient/32d170d2-d44f-4e1f-aa89-0ef892d34c21", display: "Meera Krishnan" },
          requester: { display: "Metropolitan Hospital Screening Center" },
          performer: [{ display: "Metropolitan Specialty Breast & Diagnostic Clinic" }],
        },
      },
    ],
    Task: [
      {
        resource: {
          resourceType: "Task",
          id: "task-scr-01",
          status: "in-progress",
          intent: "order",
          priority: "urgent",
          code: { text: "Coordinate Diagnostic Biopsy & Transportation Support" },
          description: "Arrange 60-minute pre-appointment pickup and confirm specialist visit with Dr. Arjun Menon, MD.",
          owner: { display: "Priya Nair, RN" },
        },
      },
    ],
    Appointment: [
      {
        resource: {
          resourceType: "Appointment",
          id: "appt-judge01-v1",
          status: "booked",
          description: "Ultrasound-Guided Core Needle Biopsy Consultation",
          serviceType: [{ text: "Diagnostic Biopsy" }],
          start: DEMO_APPOINTMENTS[0].scheduled_time,
          participant: [
            { actor: { display: "Meera Krishnan" }, status: "accepted" },
            { actor: { display: "Dr. Arjun Menon, MD" }, status: "accepted" },
          ],
        },
      },
    ],
    Communication: [
      {
        resource: {
          resourceType: "Communication",
          id: "comm-judge01-01",
          status: "completed",
          medium: [{ text: "in_app_chat" }],
          payload: [
            {
              contentString:
                "Plain-language BI-RADS 4 diagnostic report explanation delivered and acknowledged by Meera Krishnan.",
            },
          ],
          sent: now,
        },
      },
    ],
    Consent: [
      {
        resource: {
          resourceType: "Consent",
          id: "consent-judge01",
          status: "active",
          category: [{ text: "Care Coordination & AI Navigation Consent" }],
          dateTime: now,
          provision: { type: "permit" },
        },
      },
    ],
    AuditEvent: [
      {
        resource: {
          resourceType: "AuditEvent",
          id: "audit-judge01-01",
          action: "E",
          subtype: [{ code: "stage_4_report_explained" }],
          recorded: now,
          outcomeDesc: "AI coordinator retrieved finalized report and persisted Stage 4 completion event.",
        },
      },
    ],
  };

  const entry = entriesByType[resourceType] || [];
  return {
    resourceType: "Bundle",
    type: "searchset",
    total: entry.length,
    entry,
  };
}

function getUserFromAuthHeader(req: NextRequest) {
  const auth = (req.headers.get("authorization") || "").toLowerCase();
  if (auth.includes("doctor")) return DEMO_USERS["doctor@carebridge.com"];
  if (auth.includes("coordinator")) return DEMO_USERS["coordinator@carebridge.com"];
  return DEMO_USERS["patient@carebridge.com"];
}

function buildAiReply(message: string): { reply: string; intent: string } {
  const m = (message || "").toLowerCase();
  if (m.includes("report") || m.includes("explain") || m.includes("bi-rads")) {
    return {
      intent: "report_explanation",
      reply:
        "### What your report says\n\nYour finalized bilateral mammogram report (**CASE-2026-JUDGE01**) notes a **1.4 cm focal architectural distortion with clustered microcalcifications** classified as **BI-RADS 4**.\n\n### What these words mean\n\n- **BI-RADS 4** means the radiologist saw an area that looks different from surrounding tissue and deserves a closer look.\n- **Microcalcifications** are tiny calcium specks seen on the scan.\n\n### What your report recommends\n\nTargeted ultrasound and an ultrasound-guided core needle biopsy within 14 days.\n\n### What is not certain\n\nA screening scan alone cannot confirm or rule out cancer—over 70% to 80% of BI-RADS 4 biopsies turn out to be benign (non-cancerous). Only a tissue check with **Dr. Arjun Menon, MD** gives real clarity.\n\n### Questions you may want to ask your doctor\n\n1. What does the ultrasound-guided biopsy involve?\n2. How soon will our team receive the pathology results?\n3. Can Care Coordinator **Priya Nair, RN** arrange transportation 1 hour before my visit?",
    };
  }
  if (m.includes("ride") || m.includes("transport") || m.includes("travel")) {
    return {
      intent: "transport_request",
      reply:
        "I have requested a pickup 1 hour before your appointment with **Dr. Arjun Menon, MD**, and asked your Care Coordinator, **Priya Nair, RN**, to confirm the ride. I will notify you as soon as it is confirmed.",
    };
  }
  if (m.includes("cancel")) {
    return {
      intent: "appointment_cancellation",
      reply:
        "Before I process a cancellation for your visit with **Dr. Arjun Menon, MD**, could you share what is making it hard to attend (such as transportation, work schedule, anxiety, or family commitments) so we can help solve it first?",
    };
  }
  if (m.includes("scared") || m.includes("afraid") || m.includes("cancer")) {
    return {
      intent: "emotional_support",
      reply:
        "It makes complete sense to feel scared while waiting for answers. A screening score on its own cannot tell anyone whether a person has cancer—it only flags an area that deserves a closer look. A consultation with **Dr. Arjun Menon, MD** is what gives you real clarity. Would you like me to walk through your report step by step or check on your appointment time?",
    };
  }
  if (m.includes("schedule") && (m.includes("mammogram") || m.includes("screening"))) {
    return {
      intent: "patient_intake_submitted",
      reply:
        "Thank you, Meera. I have logged your mammogram screening request and created an urgent task for your Care Coordinator, **Priya Nair, RN**, at Metropolitan Breast & Comprehensive Cancer Center.\n\nPriya Nair, RN has been notified to create your screening order and track the procedure once it is performed.",
    };
  }
  return {
    intent: "care_journey_status",
    reply:
      "Hello Meera! For your care pathway (**CASE-2026-JUDGE01**), you have completed **4 of 14 stages** (including your finalized Mammogram report showing **BI-RADS 4**) and you are currently at **Stage 5 of 14: Attending Physician Clinical Review**.\n\nNext, **Dr. Arjun Menon, MD** will review your finalized findings and accept your specialist referral, while Care Coordinator **Priya Nair, RN** coordinates your consultation visit.",
  };
}

async function handleRequest(req: NextRequest, { params }: { params: { path: string[] } }) {
  const path = "/" + (params.path || []).join("/");
  const method = req.method.toUpperCase();
  const url = new URL(req.url);

  // 1. Auth
  if (path === "/auth/login" && method === "POST") {
    const body = await req.json().catch(() => ({}));
    const email = (body.email || "patient@carebridge.com").toLowerCase().trim();
    const user =
      DEMO_USERS[email] ||
      (email.includes("doc")
        ? DEMO_USERS["doctor@carebridge.com"]
        : email.includes("coord")
        ? DEMO_USERS["coordinator@carebridge.com"]
        : DEMO_USERS["patient@carebridge.com"]);
    return NextResponse.json({ success: true, data: user });
  }
  if (path === "/auth/me") {
    return NextResponse.json({ success: true, data: getUserFromAuthHeader(req) });
  }

  // 2. SSE Chat Stream
  if (path === "/agent/stream" && method === "POST") {
    const body = await req.json().catch(() => ({}));
    const { reply, intent } = buildAiReply(body.message || "");
    const sessionId = body.session_id || "sess-demo-judge01";
    const encoder = new TextEncoder();
    const words = reply.split(" ");
    const stream = new ReadableStream({
      async start(controller) {
        for (let i = 0; i < words.length; i++) {
          const token = words[i] + (i < words.length - 1 ? " " : "");
          controller.enqueue(encoder.encode(`event: token\ndata: ${JSON.stringify({ token })}\n\n`));
        }
        const finalPayload = {
          session_id: sessionId,
          content: reply,
          primary_intent: intent,
          actions: ["explain_report"],
          language: "en",
          title: (body.message || "Care Inquiry").slice(0, 32),
          completed: true,
        };
        controller.enqueue(encoder.encode(`event: final\ndata: ${JSON.stringify(finalPayload)}\n\n`));
        controller.close();
      },
    });
    return new NextResponse(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  }

  if (path === "/agent/interact" && method === "POST") {
    const body = await req.json().catch(() => ({}));
    const { reply, intent } = buildAiReply(body.message || "");
    return NextResponse.json({
      success: true,
      data: {
        case_id: DEMO_CASES[0].id,
        patient_id: DEMO_CASES[0].patient_id,
        session_id: body.session_id || "sess-demo-judge01",
        primary_intent: intent,
        emotional_state: "supportive",
        detected_barriers: [],
        actions_executed: ["explain_report"],
        outbound_message: reply,
        outbound_language: "en",
        requires_human_approval: false,
      },
    });
  }

  if (path === "/agent/sessions") {
    if (method === "POST") {
      const body = await req.json().catch(() => ({}));
      return NextResponse.json({
        success: true,
        data: {
          id: `sess-${Date.now()}`,
          title: body.title || "New Care Conversation",
          case_id: body.case_id || DEMO_CASES[0].id,
          patient_id: DEMO_CASES[0].patient_id,
          channel: body.channel || "in_app_chat",
          is_active: true,
          last_interaction_at: new Date().toISOString(),
        },
      });
    }
    return NextResponse.json({
      success: true,
      data: [
        {
          id: "sess-demo-judge01",
          title: "BI-RADS 4 Report Explanation",
          case_id: DEMO_CASES[0].id,
          patient_id: DEMO_CASES[0].patient_id,
          channel: "in_app_chat",
          is_active: true,
          last_interaction_at: new Date().toISOString(),
        },
      ],
    });
  }

  if (path === "/agent/history") {
    const { reply } = buildAiReply("explain my report");
    return NextResponse.json({
      success: true,
      data: {
        messages: [
          {
            id: "msg-1",
            sender: "patient",
            content: "Can you explain my report in plain language?",
            language: "en",
            sent_at: new Date(Date.now() - 120000).toISOString(),
          },
          {
            id: "msg-2",
            sender: "ai_coordinator",
            content: reply,
            language: "en",
            sent_at: new Date(Date.now() - 115000).toISOString(),
          },
        ],
        total: 2,
      },
    });
  }

  // 3. Dashboards
  if (path === "/dashboards/patient") {
    return NextResponse.json({
      success: true,
      data: {
        profile: {
          id: DEMO_CASES[0].patient_id,
          name: "Meera Krishnan",
          mrn: "MRN-2026-8841",
          preferred_language: "en",
        },
        current_case: DEMO_CASES[0],
        screening: {
          screening_type: "Mammogram",
          finding_code: "BI-RADS 4",
          finding_summary: DEMO_CASES[0].finding_summary,
        },
        doctor: {
          name: "Dr. Arjun Menon, MD",
          specialty: "Breast Surgical Oncology",
          facility: "Metropolitan Specialty Breast & Diagnostic Clinic",
        },
        coordinator: {
          name: "Priya Nair, RN",
          facility: "Metropolitan Breast & Comprehensive Cancer Center",
        },
        lifecycle: {
          current_stage_number: 5,
          stages: buildStages(4),
        },
        appointments: [DEMO_APPOINTMENTS[0]],
        reports: [
          {
            id: "rpt-judge01",
            report_type: "Mammogram",
            code: "BI-RADS 4",
            summary: DEMO_CASES[0].finding_summary,
          },
        ],
      },
    });
  }

  if (path === "/dashboards/doctor") {
    return NextResponse.json({
      success: true,
      data: {
        doctor: {
          name: "Dr. Arjun Menon, MD",
          specialty: "Breast Surgical Oncology",
          facility: "Metropolitan Specialty Breast & Diagnostic Clinic",
        },
        assigned_cases: DEMO_CASES,
        pending_reviews: [DEMO_CASES[0]],
        appointments: DEMO_APPOINTMENTS,
        referrals: DEMO_REFERRALS,
      },
    });
  }

  if (path === "/dashboards/coordinator") {
    return NextResponse.json({
      success: true,
      data: {
        cases: DEMO_CASES,
        tasks: [
          {
            id: "task-scr-01",
            case_id: DEMO_CASES[0].id,
            title: "Schedule Screening: Mammogram (Meera Krishnan)",
            task_type: "schedule_screening",
            priority: "urgent",
            status: "pending",
          },
        ],
        appointments: DEMO_APPOINTMENTS,
        referrals: DEMO_REFERRALS,
      },
    });
  }

  if (path === "/dashboards/consistency-check") {
    return NextResponse.json({
      success: true,
      data: { corrupted_count: 0, repaired_count: 0, checked_cases: DEMO_CASES.length },
    });
  }

  // 4. Cases & Lifecycle
  if (path === "/cases") {
    const statusParam = url.searchParams.get("status");
    const filtered = statusParam ? DEMO_CASES.filter((c) => c.status === statusParam) : DEMO_CASES;
    return NextResponse.json({ success: true, data: filtered });
  }
  if (path.match(/^\/cases\/[^/]+$/)) {
    const cid = path.split("/")[2];
    const found = DEMO_CASES.find((c) => c.id === cid) || DEMO_CASES[0];
    return NextResponse.json({ success: true, data: found });
  }
  if (path.match(/^\/cases\/[^/]+\/events$/)) {
    const cid = path.split("/")[2];
    const evs = DEMO_EVENTS_BY_CASE[cid] || DEMO_EVENTS_BY_CASE[DEMO_CASES[0].id];
    return NextResponse.json({ success: true, data: evs });
  }
  if (path.match(/^\/cases\/[^/]+\/lifecycle$/)) {
    const cid = path.split("/")[2];
    const isClosed = cid === "a729b6a7-73be-42ee-8382-654352433ba8";
    return NextResponse.json({
      success: true,
      data: {
        case_id: cid,
        current_stage_number: isClosed ? 14 : 5,
        stages: buildStages(isClosed ? 14 : 4),
      },
    });
  }
  if (path.match(/^\/cases\/[^/]+\/doctor-candidates$/)) {
    return NextResponse.json({
      success: true,
      data: [
        {
          id: "d8812345-1111-4222-8333-999999999999",
          name: "Dr. Arjun Menon, MD",
          specialty: "Breast Surgical Oncology",
          facility: "Metropolitan Specialty Breast & Diagnostic Clinic",
          availability: "Available within 48h",
        },
      ],
    });
  }
  if (path.match(/^\/cases\/[^/]+\/documentation-checklist$/)) {
    return NextResponse.json({
      success: true,
      data: {
        complete: true,
        items: [
          { key: "screening_performed", label: "Screening Examination Performed", completed: true },
          { key: "report_finalized", label: "Diagnostic Report Validated & Finalized", completed: true },
          { key: "patient_notified", label: "Patient Notified & Report Explained", completed: true },
          { key: "referral_accepted", label: "Specialist Referral Accepted", completed: true },
        ],
      },
    });
  }
  if (path.match(/^\/cases\/[^/]+\/clinical-closure$/) && method === "POST") {
    const actor = getUserFromAuthHeader(req);
    if (actor.role !== "doctor") {
      return NextResponse.json(
        { detail: "Forbidden: Verified clinical closure requires an authorized Doctor role." },
        { status: 403 }
      );
    }
    return NextResponse.json({
      success: true,
      data: { status: "closed", verified_by: actor.name, closed_at: new Date().toISOString() },
    });
  }
  if (path.match(/^\/cases\/[^/]+\/upload-report-file$/) && method === "POST") {
    return NextResponse.json({
      success: true,
      data: {
        status: "READY_TO_FINALIZE",
        finding_code: "BI-RADS 4",
        finding_summary: DEMO_CASES[0].finding_summary,
        recommendation: "Targeted ultrasound and ultrasound-guided core needle biopsy within 14 days.",
      },
    });
  }
  if (path.match(/^\/cases\/[^/]+\/finalize-report$/) && method === "POST") {
    const body = await req.json().catch(() => ({}));
    return NextResponse.json({
      success: true,
      data: {
        status: body.requires_doctor_review ? "REQUIRES_REVIEW" : "FINALIZED",
        finding_code: body.finding_code || "BI-RADS 4",
        finalized_at: new Date().toISOString(),
      },
    });
  }
  if (path.match(/^\/cases\/[^/]+\/explain-report$/)) {
    const { reply } = buildAiReply("explain my report");
    return NextResponse.json({
      success: true,
      data: {
        what_your_report_says:
          "Your finalized bilateral mammogram report (CASE-2026-JUDGE01) notes a 1.4 cm focal architectural distortion with clustered microcalcifications classified as BI-RADS 4.",
        what_these_words_mean:
          "BI-RADS 4 means the radiologist saw an area that deserves a closer look. Microcalcifications are tiny calcium specks on the scan.",
        what_your_report_recommends:
          "Targeted ultrasound and ultrasound-guided core needle biopsy within 14 days.",
        what_is_not_certain:
          "A screening scan cannot confirm or rule out cancer on its own—70% to 80% of BI-RADS 4 biopsies are benign.",
        questions_for_doctor:
          "1. What does the biopsy involve?\n2. How soon will pathology results return?\n3. Can Priya Nair, RN coordinate my pickup ride?",
        warm_closing:
          "Your Care Coordinator Priya Nair, RN and Dr. Arjun Menon, MD are supporting you at every step.",
        full_text: reply,
      },
    });
  }
  if (path.match(/^\/cases\/[^/]+\/report-download$/)) {
    return NextResponse.json({
      success: true,
      data: {
        filename: "CareBridge_Diagnostic_Report_CASE-2026-JUDGE01.txt",
        report_document_text:
          "CAREBRIDGE OFFICIAL DIAGNOSTIC REPORT\nPatient: Meera Krishnan (CASE-2026-JUDGE01)\nFinding: BI-RADS 4 - 1.4 cm focal architectural distortion with clustered microcalcifications.\nRecommendation: Targeted ultrasound and core needle biopsy within 14 days.\nAttending Specialist: Dr. Arjun Menon, MD\nCare Coordinator: Priya Nair, RN",
      },
    });
  }

  // 5. Appointments & Referrals
  if (path === "/appointments") {
    const cid = url.searchParams.get("case_id");
    const statusParam = url.searchParams.get("status");
    let items = DEMO_APPOINTMENTS;
    if (cid) items = items.filter((a) => a.case_id === cid);
    if (statusParam) items = items.filter((a) => a.status.toLowerCase() === statusParam.toLowerCase());
    return NextResponse.json({ success: true, data: items });
  }
  if (path === "/referrals") {
    const cid = url.searchParams.get("case_id");
    const statusParam = url.searchParams.get("status");
    let items = DEMO_REFERRALS;
    if (cid) items = items.filter((r) => r.case_id === cid);
    if (statusParam) items = items.filter((r) => r.status.toLowerCase() === statusParam.toLowerCase());
    return NextResponse.json({ success: true, data: items });
  }

  // 6. Notifications
  if (path === "/notifications") {
    return NextResponse.json({ success: true, data: DEMO_NOTIFICATIONS });
  }
  if (path === "/notifications/unread-count") {
    return NextResponse.json({
      success: true,
      data: { unread_count: DEMO_NOTIFICATIONS.filter((n) => !n.is_read).length },
    });
  }
  if (path === "/notifications/stream") {
    return new NextResponse("event: ping\ndata: {}\n\n", {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
      },
    });
  }

  // 7. Recovery Radar
  if (path === "/recovery") {
    return NextResponse.json({ success: true, data: DEMO_RECOVERY_CASES });
  }
  if (path.match(/^\/recovery\/trigger\/[^/]+$/) && method === "POST") {
    return NextResponse.json({
      success: true,
      data: {
        recovery_plan: {
          selected_playbook: "transportation_support",
          reasoning_and_facts: {
            reasoning:
              "Transportation barrier documented on CASE-2026-JUDGE01; 60-minute pre-appointment pickup assistance recommended.",
          },
          action_plan: {
            communication_action:
              "Dispatched outreach to Meera Krishnan confirming 60-minute pre-appointment hospital transport coordination.",
          },
        },
      },
    });
  }

  // 8. Patients & Coordinator Tasks
  if (path === "/patients/coordinator") {
    const q = (url.searchParams.get("q") || "").toLowerCase().trim();
    const stageParam = url.searchParams.get("stage");
    const needsAction = url.searchParams.get("needs_my_action") === "true";
    const overdueOnly = url.searchParams.get("overdue_sla") === "true";
    const unassignedOnly = url.searchParams.get("unassigned") === "true";

    let items = [...DEMO_COORDINATOR_PATIENTS];
    if (q) {
      items = items.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.mrn.toLowerCase().includes(q) ||
          p.case_number.toLowerCase().includes(q)
      );
    }
    if (stageParam) {
      const stageNum = Number(stageParam);
      if (!Number.isNaN(stageNum)) items = items.filter((p) => p.current_stage_number === stageNum);
    }
    if (needsAction) items = items.filter((p) => p.needs_coordinator_action);
    if (overdueOnly) items = items.filter((p) => p.sla_status === "breached" || p.sla_status === "warning");
    if (unassignedOnly) items = items.filter((p) => !p.assigned_doctor || p.assigned_doctor === "Unassigned");

    return NextResponse.json({
      success: true,
      data: {
        items,
        total: items.length,
        page: 1,
        page_size: 20,
        total_pages: 1,
      },
    });
  }
  if (path === "/patients") {
    return NextResponse.json({
      success: true,
      data: [
        {
          id: "32d170d2-d44f-4e1f-aa89-0ef892d34c21",
          mrn: "MRN-2026-8841",
          first_name: "Meera",
          last_name: "Krishnan",
          phone: "+91-98401-22334",
          email: "patient@carebridge.com",
          date_of_birth: "1978-06-14",
          gender: "female",
          preferred_language: "en",
          communication_channel: "in_app_chat",
          created_at: new Date(Date.now() - 86400000 * 10).toISOString(),
        },
        {
          id: "b1490000-0000-0000-0000-000000000149",
          mrn: "MRN-2026-0149",
          first_name: "Priya",
          last_name: "Sharma",
          phone: "+91-98401-55667",
          date_of_birth: "1981-02-22",
          gender: "female",
          preferred_language: "en",
          communication_channel: "in_app_chat",
          created_at: new Date(Date.now() - 86400000 * 14).toISOString(),
        },
      ],
    });
  }
  if (path === "/patients/coordinator/tasks") {
    return NextResponse.json({
      success: true,
      data: [
        {
          task_id: "task-scr-01",
          case_id: DEMO_CASES[0].id,
          patient_id: DEMO_CASES[0].patient_id,
          patient_name: DEMO_CASES[0].patient_name,
          stage_number: 5,
          stage_title: "Attending Physician Clinical Review",
          task_title: "Confirm Biopsy Pickup Ride & Physician Sign-Off",
          description: "Coordinate 60-minute pre-appointment transportation and confirm Dr. Arjun Menon's clinical review.",
          priority: "urgent",
          status: "pending",
          sla_status: "warning",
          due_date: new Date(Date.now() + 86400000).toISOString(),
        },
      ],
    });
  }

  // 9. Workflows Activity
  if (path === "/workflows/activity") {
    return NextResponse.json({
      success: true,
      data: [
        {
          id: "trace-01",
          timestamp: new Date().toISOString(),
          case_id: DEMO_CASES[0].id,
          case_number: "CASE-2026-JUDGE01",
          patient_name: "Meera Krishnan",
          triggering_event: "Patient Plain-Language Report Explanation Requested",
          action_explanation: "explain_report retrieved finalized BI-RADS 4 report and persisted Stage 4 delivery.",
          tool_selected: "explain_report",
          tool_result: "Stage 4 completed after full reply persistence.",
          status: "success",
          duration_ms: 142.4,
          autonomy_level: 1,
          approval_status: "autonomous",
        },
        {
          id: "trace-02",
          timestamp: new Date(Date.now() - 3600000).toISOString(),
          case_id: DEMO_CASES[1].id,
          case_number: "CASE-2026-0149",
          patient_name: "Priya Sharma",
          triggering_event: "Verified Clinical Closure Gate Check",
          action_explanation: "Verified attending physician authorization and complete 14-stage persisted evidence before closing.",
          tool_selected: "verify_clinical_closure",
          tool_result: "Stage 14 closure signed by Dr. Arjun Menon, MD.",
          status: "success",
          duration_ms: 96.1,
          autonomy_level: 3,
          approval_status: "approved",
        },
      ],
    });
  }

  // 10. Analytics
  if (path === "/analytics/metrics") {
    return NextResponse.json({
      success: true,
      data: {
        summary: {
          total_cases: 202,
          active_cases: 198,
          closed_cases: 4,
          stalled_cases: 3,
        },
        metrics: {
          time_from_result_to_notification: {
            formatted: "14.2 hrs",
            description: "Average hours from finalized diagnostic report to patient outreach",
            average_hours: 14.2,
            median_hours: 12.5,
            cases_measured: 202,
          },
          patient_acknowledgement_rate: {
            formatted: "94.1%",
            description: "Percentage of notified patients who acknowledged findings",
            rate_percent: 94.1,
            acknowledged_count: 190,
            notified_count: 202,
          },
          referral_acceptance_rate: {
            formatted: "96.5%",
            description: "Specialist referrals formally accepted within 48 hours",
            rate_percent: 96.5,
            accepted_count: 164,
            total_referrals: 170,
          },
          appointment_attendance_rate: {
            formatted: "88.2%",
            description: "Diagnostic consultations attended vs missed",
            rate_percent: 88.2,
            attended_count: 135,
            no_show_count: 18,
          },
          drop_off_recovery_rate: {
            formatted: "83.3%",
            description: "Stalled patients re-engaged through barrier-aware playbooks",
            rate_percent: 83.3,
            recovered_count: 15,
            stalled_count: 18,
          },
          median_time_to_care: {
            formatted: "9.8 days",
            description: "Median days from abnormal screening result to diagnostic workup",
            median_days: 9.8,
            average_days: 10.4,
          },
          verified_closure_rate: {
            formatted: "100.0%",
            description: "Closed cases verified with physician sign-off and complete evidence",
            rate_percent: 100.0,
            verified_closures: 4,
            total_closed_cases: 4,
          },
          overdue_cases: {
            formatted: "2 cases",
            description: "Active cases surpassing clinical turnaround window",
            count: 2,
            case_ids: [DEMO_CASES[0].id],
          },
          unassigned_cases: {
            formatted: "0 cases",
            description: "Cases awaiting care coordinator assignment",
            count: 0,
            case_ids: [],
          },
        },
      },
    });
  }
  if (path === "/analytics/operational-priorities") {
    const tierParam = (url.searchParams.get("tier") || "all").toLowerCase();
    const statusParam = (url.searchParams.get("status") || "all").toLowerCase();
    let items = [...DEMO_OPERATIONAL_PRIORITIES];
    if (tierParam !== "all") {
      items = items.filter((i) => i.priority_tier.toLowerCase() === tierParam);
    }
    if (statusParam !== "all" && statusParam !== "active") {
      items = items.filter((i) => i.status.toLowerCase() === statusParam);
    }
    return NextResponse.json({ success: true, data: items });
  }
  if (path === "/analytics/filters") {
    return NextResponse.json({
      success: true,
      data: {
        providers: [
          {
            id: "a33bc385-05df-4ea4-a96a-5a4a51308224",
            name: "Priya Nair, RN",
            role: "care_coordinator",
            facility: "Metropolitan Breast & Comprehensive Cancer Center",
          },
          {
            id: "d8812345-1111-4222-8333-999999999999",
            name: "Dr. Arjun Menon, MD",
            role: "doctor",
            facility: "Metropolitan Specialty Breast & Diagnostic Clinic",
          },
        ],
        statuses: [
          { id: "result_received", label: "Result Received" },
          { id: "recovering", label: "In Recovery" },
          { id: "closed", label: "Verified Closure" },
        ],
      },
    });
  }

  // 11. HL7 FHIR R4 Gateway
  if (path === "/fhir/metadata") {
    return NextResponse.json({
      resourceType: "CapabilityStatement",
      status: "active",
      date: new Date().toISOString(),
      kind: "instance",
      fhirVersion: "4.0.1",
      format: ["json"],
      software: { name: "CareBridge FHIR R4 Exchange Gateway", version: "1.0.0" },
      rest: [
        {
          mode: "server",
          resource: [
            "Patient",
            "DiagnosticReport",
            "ServiceRequest",
            "Task",
            "Appointment",
            "Communication",
            "Consent",
            "AuditEvent",
          ].map((type) => ({ type, interaction: [{ code: "read" }, { code: "search-type" }] })),
        },
      ],
    });
  }
  if (path.match(/^\/fhir\/[^/]+\/validate$/) && method === "POST") {
    return NextResponse.json({
      resourceType: "OperationOutcome",
      issue: [
        {
          severity: "information",
          code: "informational",
          diagnostics: "FHIR R4 resource validated successfully against HL7 R4 schema.",
        },
      ],
    });
  }
  if (path.match(/^\/fhir\/[^/]+$/)) {
    const resourceType = path.split("/")[2];
    return NextResponse.json(buildFhirBundle(resourceType));
  }

  // 12. Health & Observability
  if (path === "/health") {
    return NextResponse.json({ status: "healthy", service: "carebridge-vercel-api" });
  }
  if (path === "/health/observability") {
    return NextResponse.json({
      success: true,
      data: {
        status: "healthy",
        tracing_enabled: true,
        llm_provider: "carebridge-clinical-engine",
        database: "connected",
      },
    });
  }

  return NextResponse.json({ success: true, data: {} });
}

export async function GET(req: NextRequest, ctx: { params: { path: string[] } }) {
  return handleRequest(req, ctx);
}
export async function POST(req: NextRequest, ctx: { params: { path: string[] } }) {
  return handleRequest(req, ctx);
}
export async function PATCH(req: NextRequest, ctx: { params: { path: string[] } }) {
  return handleRequest(req, ctx);
}
export async function PUT(req: NextRequest, ctx: { params: { path: string[] } }) {
  return handleRequest(req, ctx);
}
export async function DELETE(req: NextRequest, ctx: { params: { path: string[] } }) {
  return handleRequest(req, ctx);
}
