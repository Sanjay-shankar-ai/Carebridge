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
    sla_status: "on_track",
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
    sla_status: "resolved",
    inferred_barriers: ["Transportation (Resolved)"],
    recovery_attempts: 1,
    created_at: new Date(Date.now() - 86400000 * 7).toISOString(),
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
    status: "CONFIRMED",
    version: 1,
    doctor_confirmed: true,
    patient_confirmed: true,
    notes: "Dual-confirmed v1 ultrasound-guided core needle biopsy consultation.",
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
    status: "accepted",
    acceptance_deadline: new Date(Date.now() + 86400000 * 2).toISOString(),
    created_at: new Date(Date.now() - 86400000).toISOString(),
  },
];

const DEMO_EVENTS = [
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
];

const DEMO_NOTIFICATIONS = [
  {
    id: "notif-01",
    event_type: "report_finalized",
    title: "Diagnostic Report Finalized: BI-RADS 4 (Mammogram)",
    message:
      "Your Mammogram report (BI-RADS 4) has been validated and finalized by Priya Nair, RN. Open CareBridge AI to review your plain-language explanation.",
    priority: "urgent",
    is_read: false,
    created_at: new Date(Date.now() - 1800000).toISOString(),
  },
  {
    id: "notif-02",
    event_type: "screening_request_received",
    title: "New Screening Request: Meera Krishnan (CASE-2026-JUDGE01)",
    message: "Patient submitted a routine Mammogram screening request. Persisted task Schedule Screening created.",
    priority: "urgent",
    is_read: false,
    created_at: new Date(Date.now() - 3600000).toISOString(),
  },
];

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
    return NextResponse.json({ success: true, data: DEMO_USERS["patient@carebridge.com"] });
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
        appointments: DEMO_APPOINTMENTS,
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

  // 4. Cases & Lifecycle
  if (path === "/cases") {
    return NextResponse.json({ success: true, data: DEMO_CASES });
  }
  if (path.match(/^\/cases\/[^/]+$/)) {
    const cid = path.split("/")[2];
    const found = DEMO_CASES.find((c) => c.id === cid) || DEMO_CASES[0];
    return NextResponse.json({ success: true, data: found });
  }
  if (path.match(/^\/cases\/[^/]+\/events$/)) {
    return NextResponse.json({ success: true, data: DEMO_EVENTS });
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

  // 5. Appointments, Referrals, Notifications, Recovery, Analytics, Patients, FHIR
  if (path === "/appointments") {
    return NextResponse.json({ success: true, data: DEMO_APPOINTMENTS });
  }
  if (path === "/referrals") {
    return NextResponse.json({ success: true, data: DEMO_REFERRALS });
  }
  if (path === "/notifications") {
    return NextResponse.json({ success: true, data: DEMO_NOTIFICATIONS });
  }
  if (path === "/notifications/unread-count") {
    return NextResponse.json({ success: true, data: { unread_count: DEMO_NOTIFICATIONS.length } });
  }
  if (path === "/recovery") {
    return NextResponse.json({
      success: true,
      data: [
        {
          id: DEMO_CASES[0].id,
          case_number: DEMO_CASES[0].case_number,
          patient_name: DEMO_CASES[0].patient_name,
          finding_code: "BI-RADS 4",
          priority: "urgent",
          inferred_barriers: ["transportation_caregiver"],
          recovery_attempts: 1,
          status: "recovering",
        },
      ],
    });
  }
  if (path === "/patients" || path === "/patients/coordinator") {
    return NextResponse.json({
      success: true,
      data: {
        items: DEMO_CASES,
        total: DEMO_CASES.length,
        page: 1,
        page_size: 20,
        total_pages: 1,
      },
    });
  }
  if (path === "/patients/coordinator/tasks") {
    return NextResponse.json({
      success: true,
      data: [
        {
          id: "task-scr-01",
          case_id: DEMO_CASES[0].id,
          case_number: DEMO_CASES[0].case_number,
          patient_name: DEMO_CASES[0].patient_name,
          title: "Schedule Screening: Mammogram",
          task_type: "schedule_screening",
          priority: "urgent",
          status: "pending",
          assigned_role: "care_coordinator",
          due_date: new Date(Date.now() + 86400000).toISOString(),
        },
      ],
    });
  }
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
          action_explanation: "Explain_report tool retrieved finalized BI-RADS 4 report and persisted Stage 4 delivery.",
          tool_selected: "explain_report",
          tool_result: "Stage 4 completed after full reply persistence.",
          status: "success",
          duration_ms: 142.4,
          autonomy_level: 1,
          approval_status: "autonomous",
        },
      ],
    });
  }
  if (path === "/analytics/metrics") {
    return NextResponse.json({
      success: true,
      data: {
        total_cases: 202,
        active_cases: 198,
        closed_cases: 4,
        stalled_cases: 3,
        sla_compliance_rate: 96.4,
        average_days_to_diagnostic: 6.2,
        recovery_success_rate: 88.5,
      },
    });
  }
  if (path === "/health") {
    return NextResponse.json({ status: "healthy", service: "carebridge-vercel-api" });
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
