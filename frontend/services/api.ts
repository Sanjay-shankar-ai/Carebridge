/**
 * CareBridge Frontend API Client
 * Connects Next.js UI to the FastAPI backend services.
 */

export function getApiBaseUrl(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (
    typeof window !== "undefined" &&
    window.location.hostname !== "localhost" &&
    window.location.hostname !== "127.0.0.1"
  ) {
    return "";
  }
  return "http://localhost:8000";
}

const API_BASE_URL = getApiBaseUrl();

async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${getApiBaseUrl()}/api/v1${endpoint}`;
  
  // Retrieve token from authenticated session
  let token: string | null = null;
  if (typeof window !== "undefined") {
    try {
      const stored = localStorage.getItem("carebridge_auth_user");
      if (stored) {
        const parsed = JSON.parse(stored);
        token = parsed?.token || null;
      }
    } catch {}
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  try {
    const res = await fetch(url, {
      ...options,
      headers,
      cache: "no-store",
    });

    if (!res.ok) {
      const errorBody = await res.json().catch(() => ({}));
      throw new Error(errorBody.detail || errorBody.message || `Request failed with status ${res.status}`);
    }

    const json = await res.json();
    return json.data !== undefined ? json.data : json;
  } catch (error) {
    console.error(`API Fetch Error [${endpoint}]:`, error);
    throw error;
  }
}

// -----------------------------------------------------------------------------
// Health Check
// -----------------------------------------------------------------------------
export async function fetchHealth() {
  try {
    return await apiFetch("/health");
  } catch (err) {
    return { status: "unreachable", error: String(err) };
  }
}

// -----------------------------------------------------------------------------
// Care Cases
// -----------------------------------------------------------------------------
export async function fetchCases(status?: string) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return await apiFetch<any[]>(`/cases${query}`);
}

export async function fetchCaseDetail(caseId: string) {
  return await apiFetch<any>(`/cases/${caseId}`);
}

export async function fetchCaseEvents(caseId: string) {
  return await apiFetch<any[]>(`/cases/${caseId}/events`).catch(() => []);
}

export async function reopenCase(caseId: string, clinicalRationale: string) {
  return await apiFetch<any>(`/cases/${caseId}/reopen`, {
    method: "POST",
    body: JSON.stringify({ clinical_rationale: clinicalRationale }),
  });
}

// -----------------------------------------------------------------------------
// Patients
// -----------------------------------------------------------------------------
export async function fetchPatients() {
  return await apiFetch<any[]>("/patients");
}

export async function fetchCoordinatorPatients(params?: {
  q?: string;
  stage?: number;
  needs_my_action?: boolean;
  overdue_sla?: boolean;
  unassigned?: boolean;
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_order?: string;
}) {
  const qp = new URLSearchParams();
  if (params?.q) qp.append("q", params.q);
  if (params?.stage !== undefined && params?.stage !== null) qp.append("stage", String(params.stage));
  if (params?.needs_my_action) qp.append("needs_my_action", "true");
  if (params?.overdue_sla) qp.append("overdue_sla", "true");
  if (params?.unassigned) qp.append("unassigned", "true");
  if (params?.page) qp.append("page", String(params.page));
  if (params?.page_size) qp.append("page_size", String(params.page_size));
  if (params?.sort_by) qp.append("sort_by", params.sort_by);
  if (params?.sort_order) qp.append("sort_order", params.sort_order);

  const query = qp.toString() ? `?${qp.toString()}` : "";
  return await apiFetch<{
    items: any[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
  }>(`/patients/coordinator${query}`);
}

export async function fetchCoordinatorTasks() {
  return await apiFetch<any[]>("/patients/coordinator/tasks");
}

export async function fetchPatientDetail(patientId: string) {
  return await apiFetch<any>(`/patients/${patientId}`);
}

// -----------------------------------------------------------------------------
// Appointments
// -----------------------------------------------------------------------------
export async function fetchAppointments(status?: string, caseId?: string) {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  if (caseId) params.append("case_id", caseId);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return await apiFetch<any[]>(`/appointments${qs}`).catch(() => []);
}

// -----------------------------------------------------------------------------
// Referrals
// -----------------------------------------------------------------------------
export async function fetchReferrals(status?: string, caseId?: string) {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  if (caseId) params.append("case_id", caseId);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return await apiFetch<any[]>(`/referrals${qs}`).catch(() => []);
}

// -----------------------------------------------------------------------------
// Care Recovery
// -----------------------------------------------------------------------------
export async function fetchRecoveryQueue() {
  return await apiFetch<any[]>("/recovery").catch(() => []);
}

export async function triggerRecoveryPlay(caseId: string) {
  return await apiFetch<any>(`/recovery/trigger/${caseId}`, {
    method: "POST",
  });
}

// -----------------------------------------------------------------------------
// AI Supervisor Interaction
// -----------------------------------------------------------------------------
export async function sendAgentMessage(params: {
  caseId?: string;
  sessionId?: string;
  message: string;
  channel?: string;
  sender?: string;
}) {
  return await apiFetch<any>("/agent/interact", {
    method: "POST",
    body: JSON.stringify({
      case_id: params.caseId || null,
      session_id: params.sessionId || null,
      message: params.message,
      channel: params.channel || "in_app_chat",
      sender: params.sender || "patient",
    }),
  });
}

export async function streamAgentMessage({
  caseId,
  sessionId,
  message,
  channel = "in_app_chat",
  sender = "patient",
  signal,
  onToken,
  onToolStarted,
  onToolResult,
  onFinal,
  onError,
}: {
  caseId?: string;
  sessionId?: string;
  message: string;
  channel?: string;
  sender?: string;
  signal?: AbortSignal;
  onToken?: (token: string) => void;
  onToolStarted?: (tool: string, description?: string) => void;
  onToolResult?: (result: { tool: string; status: "success" | "failed" | "warning"; summary: string }) => void;
  onFinal?: (finalData: any) => void;
  onError?: (error: any) => void;
}) {
  const url = `${getApiBaseUrl()}/api/v1/agent/stream`;
  let token: string | null = null;
  if (typeof window !== "undefined") {
    try {
      const stored = localStorage.getItem("carebridge_auth_user");
      if (stored) {
        token = JSON.parse(stored)?.token || null;
      }
    } catch {}
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify({
      case_id: caseId || null,
      session_id: sessionId || null,
      message,
      channel,
      sender,
      stream: true,
    }),
    signal,
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    throw new Error(errorBody.detail || errorBody.message || `Request failed with status ${response.status}`);
  }

  if (!response.body) {
    throw new Error("No response body received for streaming.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const ev of events) {
        if (!ev.trim()) continue;
        const lines = ev.split("\n");
        let eventType = "message";
        let dataStr = "";

        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventType = line.replace("event:", "").trim();
          } else if (line.startsWith("data:")) {
            dataStr = line.replace("data:", "").trim();
          }
        }

        if (!dataStr) continue;

        try {
          const parsed = JSON.parse(dataStr);
          if (eventType === "token" && onToken) {
            onToken(parsed.token || "");
          } else if (eventType === "tool_started" && onToolStarted) {
            onToolStarted(parsed.tool || "", parsed.description);
          } else if (eventType === "tool_result" && onToolResult) {
            onToolResult({
              tool: parsed.tool || "",
              status: parsed.status || "success",
              summary: parsed.summary || "",
            });
          } else if (eventType === "final" && onFinal) {
            onFinal(parsed);
          } else if (eventType === "error" && onError) {
            onError(parsed);
          }
        } catch (parseErr) {
          console.warn("Error parsing SSE event data:", parseErr, dataStr);
        }
      }
    }
  } catch (err: any) {
    if (signal?.aborted) {
      return;
    }
    if (onError) onError(err);
    throw err;
  }
}

export async function fetchChatHistory(caseId?: string, sessionId?: string, limit = 50, offset = 0) {
  const params = new URLSearchParams();
  if (caseId) params.append("case_id", caseId);
  if (sessionId) params.append("session_id", sessionId);
  params.append("limit", String(limit));
  params.append("offset", String(offset));

  const res = await apiFetch<any>(`/agent/history?${params.toString()}`).catch(() => null);
  if (res && res.messages) {
    return res.messages;
  }
  return [];
}

export async function fetchConversationSessions(caseId?: string, search?: string) {
  const params = new URLSearchParams();
  if (caseId) params.append("case_id", caseId);
  if (search) params.append("q", search);
  const query = params.toString() ? `?${params.toString()}` : "";
  return await apiFetch<any[]>(`/agent/sessions${query}`).catch(() => []);
}

export async function createConversationSession(options?: {
  caseId?: string;
  title?: string;
  channel?: string;
}) {
  return await apiFetch<any>("/agent/sessions", {
    method: "POST",
    body: JSON.stringify({
      title: options?.title || "New Chat",
      case_id: options?.caseId || null,
      channel: options?.channel || "in_app_chat",
    }),
  });
}

export async function renameConversationSession(sessionId: string, title: string) {
  return await apiFetch<any>(`/agent/sessions/${sessionId}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export async function deleteConversationSession(sessionId: string) {
  return await apiFetch<any>(`/agent/sessions/${sessionId}`, {
    method: "DELETE",
  });
}

// -----------------------------------------------------------------------------
// Long-Running Workflows & Observability
// -----------------------------------------------------------------------------
export async function fetchAIActivity(caseId?: string) {
  const query = caseId ? `?case_id=${encodeURIComponent(caseId)}` : "";
  return await apiFetch<any[]>(`/workflows/activity${query}`).catch(() => []);
}

export async function fetchWorkflowHistory(caseId: string) {
  return await apiFetch<any>(`/workflows/${caseId}/history`).catch(() => ({ total_actions: 0, timeline: [] }));
}

export async function fetchWorkflowCheckpoints(caseId: string) {
  return await apiFetch<any>(`/workflows/${caseId}/checkpoints`).catch(() => ({ checkpoint_count: 0, checkpoints: [] }));
}

export async function retryWorkflow(caseId: string) {
  return await apiFetch<any>(`/workflows/recovery/retry/${caseId}`, {
    method: "POST",
  });
}

// -----------------------------------------------------------------------------
// Data-Driven Analytics & Operational Drop-Off Prioritization (Phase 10)
// -----------------------------------------------------------------------------
export async function fetchAnalyticsMetrics(filters?: {
  from_date?: string;
  to_date?: string;
  status?: string;
  provider_id?: string;
}) {
  const params = new URLSearchParams();
  if (filters?.from_date) params.append("from_date", filters.from_date);
  if (filters?.to_date) params.append("to_date", filters.to_date);
  if (filters?.status && filters.status !== "all") params.append("status", filters.status);
  if (filters?.provider_id && filters.provider_id !== "all") params.append("provider_id", filters.provider_id);

  const qs = params.toString() ? `?${params.toString()}` : "";
  return await apiFetch<any>(`/analytics/metrics${qs}`);
}

export async function fetchOperationalPriorities(filters?: {
  from_date?: string;
  to_date?: string;
  status?: string;
  provider_id?: string;
  tier?: string;
}) {
  const params = new URLSearchParams();
  if (filters?.from_date) params.append("from_date", filters.from_date);
  if (filters?.to_date) params.append("to_date", filters.to_date);
  if (filters?.status && filters.status !== "all") params.append("status", filters.status);
  if (filters?.provider_id && filters.provider_id !== "all") params.append("provider_id", filters.provider_id);
  if (filters?.tier && filters.tier !== "all") params.append("tier", filters.tier);

  const qs = params.toString() ? `?${params.toString()}` : "";
  return await apiFetch<any[]>(`/analytics/operational-priorities${qs}`).catch(() => []);
}

export async function fetchAnalyticsFilterOptions() {
  return await apiFetch<any>("/analytics/filters").catch(() => ({
    providers: [],
    statuses: []
  }));
}

// -----------------------------------------------------------------------------
// Authentication & Unified Role Detection (Real Cryptographic JWT Session)
// -----------------------------------------------------------------------------
export async function loginUser(email: string, password?: string) {
  const normalized = email.trim().toLowerCase();
  return await apiFetch<any>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email: normalized, password }),
  });
}

export async function registerPatient(payload: {
  email: string;
  password?: string;
  first_name: string;
  last_name: string;
  phone?: string;
  preferred_language?: string;
  date_of_birth?: string;
}) {
  return await apiFetch<any>("/auth/register/patient", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function registerDoctor(payload: {
  email: string;
  password?: string;
  full_name: string;
  facility?: string;
  specialty?: string;
  phone?: string;
}) {
  return await apiFetch<any>("/auth/register/doctor", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchCurrentUser() {
  return await apiFetch<any>("/auth/me");
}

// -----------------------------------------------------------------------------
// Appointments Lifecycle Management
// -----------------------------------------------------------------------------
export async function bookAppointment(payload: {
  case_id: string;
  patient_id: string;
  facility: string;
  provider_name: string;
  appointment_type: string;
  scheduled_time: string;
  notes?: string;
}) {
  return await apiFetch<any>("/appointments/book", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function cancelAppointment(
  appointmentId: string,
  payload: { cancellation_reason: string; cancelled_by?: string; notes?: string }
) {
  return await apiFetch<any>(`/appointments/${appointmentId}/cancel`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function proposeReschedule(
  appointmentId: string,
  payload: { proposed_slots: string[]; reason: string; proposed_by?: string }
) {
  return await apiFetch<any>(`/appointments/${appointmentId}/reschedule-propose`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function acceptRescheduledSlot(
  appointmentId: string,
  payload: { selected_slot: string; accepted_by: string; partner_confirmed?: boolean }
) {
  return await apiFetch<any>(`/appointments/${appointmentId}/reschedule-accept`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// -----------------------------------------------------------------------------
// Real-Time & Persistent Notifications (Phase 7)
// -----------------------------------------------------------------------------
export async function fetchNotifications(unreadOnly = false, limit = 50) {
  const query = unreadOnly ? `?unread_only=true&limit=${limit}` : `?limit=${limit}`;
  return await apiFetch<any[]>(`/notifications${query}`).catch(() => []);
}

export async function fetchUnreadCount() {
  return await apiFetch<{ unread_count: number }>("/notifications/unread-count").catch(() => ({ unread_count: 0 }));
}

export async function markNotificationRead(notificationId: string) {
  return await apiFetch<any>(`/notifications/${notificationId}/read`, {
    method: "PATCH",
  });
}

export async function markAllNotificationsRead() {
  return await apiFetch<{ marked_read: number }>("/notifications/mark-all-read", {
    method: "POST",
  });
}

export async function triggerRemindersSweep(hoursAhead = 48) {
  return await apiFetch<any>(`/notifications/reminders/process?hours_ahead=${hoursAhead}`, {
    method: "POST",
  });
}

// -----------------------------------------------------------------------------
// HL7 FHIR Interoperability (Phase 8)
// -----------------------------------------------------------------------------
export async function fetchFHIRCapabilityStatement() {
  return await apiFetch<any>("/fhir/metadata");
}

export async function searchFHIRResources(resourceType: string, params: Record<string, string> = {}) {
  const queryStr = new URLSearchParams(params).toString();
  const endpoint = queryStr ? `/fhir/${resourceType}?${queryStr}` : `/fhir/${resourceType}`;
  return await apiFetch<any>(endpoint);
}

export async function fetchFHIRResource(resourceType: string, id: string) {
  return await apiFetch<any>(`/fhir/${resourceType}/${id}`);
}

export async function validateFHIRPayload(resourceType: string, payload: any) {
  return await apiFetch<any>(`/fhir/${resourceType}/validate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// -----------------------------------------------------------------------------
// 14-Stage Longitudinal Care Lifecycle
// -----------------------------------------------------------------------------
export async function fetchCaseLifecycle(caseId: string) {
  return await apiFetch<any>(`/cases/${caseId}/lifecycle`);
}

export async function submitClinicalReview(caseId: string, payload: {
  clinical_assessment: string;
  approved_pathway: string;
  additional_investigations?: string;
  patient_safe_explanation?: string;
  referral_approved?: boolean;
}) {
  return await apiFetch<any>(`/cases/${caseId}/clinical-review`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function acceptReferral(referralId: string, payload: {
  receiving_provider_name: string;
  acceptance_notes?: string;
}) {
  return await apiFetch<any>(`/referrals/${referralId}/accept`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function recordConsultationOutcome(caseId: string, payload: {
  consultation_notes: string;
  biopsy_pathology_outcome: string;
  clinical_recommendations: string;
  treatment_plan: string;
  next_followup_date?: string;
}) {
  return await apiFetch<any>(`/cases/${caseId}/consultation-outcome`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function submitTreatmentUpdate(caseId: string, payload: {
  message: string;
  category?: string;
}) {
  return await apiFetch<any>(`/cases/${caseId}/treatment-update`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function recordFollowUpStatus(caseId: string, payload: {
  status: string;
  notes?: string;
}) {
  return await apiFetch<any>(`/cases/${caseId}/follow-up`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchDoctorCandidates(caseId: string, specialtyOverride?: string) {
  const q = specialtyOverride ? `?specialty_override=${encodeURIComponent(specialtyOverride)}` : "";
  return await apiFetch<any[]>(`/cases/${caseId}/doctor-candidates${q}`).catch(() => []);
}

export async function reassignDoctor(assignmentId: string, payload: {
  new_doctor_id: string;
  reassignment_reason: string;
}) {
  return await apiFetch<any>(`/coordinator/assignments/${assignmentId}/reassign`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchDocumentationChecklist(caseId: string) {
  return await apiFetch<any>(`/cases/${caseId}/documentation-checklist`);
}

export async function executeClinicalClosure(caseId: string, payload: {
  clinical_rationale: string;
  evidence_summary?: string;
}) {
  return await apiFetch<any>(`/cases/${caseId}/clinical-closure`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function completeAppointment(appointmentId: string) {
  return await apiFetch<any>(`/appointments/${appointmentId}/complete`, {
    method: "POST",
  });
}

export async function scheduleScreening(caseId: string, payload: {
  scheduled_time: string;
  facility?: string;
  provider_name?: string;
  notes?: string;
}) {
  return await apiFetch<any>(`/cases/${caseId}/schedule-screening`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function completeScreening(caseId: string, payload?: {
  completion_notes?: string;
  completed_at?: string;
}) {
  return await apiFetch<any>(`/cases/${caseId}/complete-screening`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
}

export async function recordMissedScreening(caseId: string, payload?: {
  missed_reason?: string;
}) {
  return await apiFetch<any>(`/cases/${caseId}/missed-screening`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
}

export async function uploadTestReport(caseId: string, payload: {
  screening_type: string;
  disease_condition: string;
  finding_code: string;
  finding_summary: string;
  report_text?: string;
  report_filename?: string;
  clinical_recommendation?: string;
  urgency_level?: string;
}) {
  return await apiFetch<any>(`/cases/${caseId}/test-report`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function downloadDiagnosticReport(caseId: string) {
  return await apiFetch<any>(`/cases/${caseId}/report-download`);
}

export async function explainReport(caseId: string, language: string = "en") {
  return await apiFetch<any>(`/cases/${caseId}/explain-report`, {
    method: "POST",
    body: JSON.stringify({ language })
  });
}

export async function fetchObservabilityStatus() {
  return await apiFetch<any>("/health/observability");
}

// -----------------------------------------------------------------------------
// Synchronized Role-Authorized Dashboards (Phase 5)
// -----------------------------------------------------------------------------
export async function fetchPatientDashboard() {
  return await apiFetch<any>("/dashboards/patient");
}

export async function fetchDoctorDashboard() {
  return await apiFetch<any>("/dashboards/doctor");
}

export async function fetchCoordinatorDashboard() {
  return await apiFetch<any>("/dashboards/coordinator");
}

export async function runDashboardConsistencyCheck(dryRun = true) {
  return await apiFetch<any>(`/dashboards/consistency-check?dry_run=${dryRun}`);
}


