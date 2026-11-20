export type CareCaseStatus =
  | "intake"
  | "intake_ready"
  | "intake_submitted"
  | "screening_scheduled"
  | "screening_completed"
  | "result_generated"
  | "result_received"
  | "notified"
  | "acknowledged"
  | "referred"
  | "appointment_booked"
  | "appointment_scheduled"
  | "missed_visit"
  | "recovering"
  | "consulted"
  | "diagnostic_completed"
  | "closed"
  | "care_completed"
  | "escalated"
  | "UNASSIGNED_ESCALATED";

export type SLASeverity = "normal" | "warning" | "breached";

export interface Patient {
  id: string;
  mrn: string;
  first_name: string;
  last_name: string;
  phone: string;
  email?: string;
  date_of_birth: string;
  gender: string;
  preferred_language: string;
  communication_channel: string;
  accessibility_requirements?: Record<string, boolean>;
  patient_context?: {
    caregiver_name?: string;
    caregiver_phone?: string;
    transportation_support?: boolean;
    known_barriers?: string[];
  };
  created_at: string;
}

export interface CareCase {
  id: string;
  case_number: string;
  patient_id: string;
  patient_name: string;
  patient_phone?: string;
  patient_language: string;
  screening_type: string;
  finding_code: string;
  finding_summary: string;
  status: CareCaseStatus;
  priority: "standard" | "urgent" | "critical";
  current_owner: string;
  sla_deadline: string;
  sla_status: SLASeverity;
  inferred_barriers: string[];
  recovery_attempts: number;
  created_at: string;
}

export interface Appointment {
  id: string;
  case_id: string;
  case_number: string;
  patient_id: string;
  patient_name: string;
  facility: string;
  provider_name: string;
  appointment_type: string;
  scheduled_time: string;
  status: "booked" | "confirmed" | "attended" | "no_show" | "cancelled" | "rescheduled";
  attendance_recorded_at?: string;
  cancellation_reason?: string;
  cancellation_outcome?: string;
  notes?: string;
}

export interface Referral {
  id: string;
  case_id: string;
  case_number: string;
  patient_id: string;
  patient_name: string;
  referring_provider: string;
  target_facility: string;
  specialty: string;
  reason_for_referral: string;
  status: "draft" | "sent" | "accepted" | "rejected" | "rerouted" | "completed";
  rejection_reason?: string;
  acceptance_deadline?: string;
  responded_at?: string;
  created_at?: string;
}

export interface CaseTimelineEvent {
  event_id: string;
  event_type: string;
  description: string;
  event_data?: Record<string, any>;
  timestamp: string;
}

export interface NotificationItem {
  id: string;
  user_id: string;
  role: string;
  event_type: string;
  title: string;
  message: string;
  priority: "normal" | "urgent" | "critical";
  case_id?: string | null;
  patient_id?: string | null;
  is_read: boolean;
  read_at?: string | null;
  action_link?: string | null;
  idempotency_key?: string | null;
  metadata?: Record<string, any>;
  created_at: string;
}

export interface WorkflowActionTrace {
  trace_id: string;
  timestamp: string;
  workflow: string;
  node: string;
  status: string;
  step_number: number;
  duration_ms: number;
  coordinator_explanation: string;
  has_error: boolean;
  error_details?: string;
}

export interface AIActivityItem {
  id: string;
  timestamp: string;
  case_id?: string;
  case_number: string;
  patient_name: string;
  triggering_event: string;
  action_explanation: string;
  tool_selected: string;
  tool_result: string;
  status: "success" | "failed" | "interrupted" | "pending";
  duration_ms: number;
  autonomy_level: 1 | 2 | 3;
  approval_status: "autonomous" | "policy_checked" | "pending_approval" | "approved" | "rejected";
}

export interface RecoveryCase {
  case_id: string;
  case_number: string;
  patient_id: string;
  patient_name: string;
  patient_phone?: string;
  patient_language: string;
  status: string;
  priority: string;
  current_owner: string;
  sla_deadline: string;
  sla_status: SLASeverity;
  recovery_attempts: number;
  active_playbook: string;
  barriers_detected: string[];
  has_no_show: boolean;
  no_show_count: number;
  last_recovery_timestamp: string;
}

export interface ToolResultChip {
  tool: string;
  status: "success" | "failed" | "warning";
  summary: string;
}

export interface ChatMessage {
  id: string;
  sender: "patient" | "ai" | "coordinator" | "clinician";
  text: string;
  timestamp: string;
  language?: string;
  isStreaming?: boolean;
  detectedIntent?: string;
  suggestedActions?: string[];
  requiresApproval?: boolean;
  toolResults?: ToolResultChip[];
  error?: boolean;
}

export interface MetricItem {
  formatted: string;
  description: string;
  rate_percent?: number;
  average_hours?: number;
  median_hours?: number;
  cases_measured?: number;
  acknowledged_count?: number;
  notified_count?: number;
  accepted_count?: number;
  total_referrals?: number;
  attended_count?: number;
  no_show_count?: number;
  total_evaluated?: number;
  recovered_count?: number;
  stalled_count?: number;
  median_days?: number;
  average_days?: number;
  cases_evaluated?: number;
  verified_closures?: number;
  total_closed_cases?: number;
  count?: number;
  case_ids?: string[];
}

export interface AnalyticsMetricsResponse {
  summary: {
    total_cases: number;
    active_cases: number;
    closed_cases: number;
    stalled_cases: number;
  };
  metrics: {
    time_from_result_to_notification: MetricItem;
    patient_acknowledgement_rate: MetricItem;
    referral_acceptance_rate: MetricItem;
    appointment_attendance_rate: MetricItem;
    drop_off_recovery_rate: MetricItem;
    median_time_to_care: MetricItem;
    verified_closure_rate: MetricItem;
    overdue_cases: MetricItem;
    unassigned_cases: MetricItem;
  };
}

export interface OperationalPriorityCase {
  case_id: string;
  case_number: string;
  patient_id?: string;
  patient_name: string;
  patient_language: string;
  patient_phone?: string;
  current_owner: string;
  current_owner_role?: string;
  status: string;
  priority: string;
  sla_status: string;
  sla_deadline?: string;
  operational_risk_score: number;
  priority_tier: "URGENT_FOLLOWUP" | "ELEVATED_ATTENTION" | "ON_TRACK";
  operational_reasons: string[];
  why_prioritized: string;
  barriers_detected: string[];
  recovery_attempts: number;
  disclaimer: string;
}

export interface FilterOptionsResponse {
  providers: Array<{ id: string; name: string; role: string; facility: string }>;
  statuses: Array<{ id: string; label: string }>;
}

export type UserRole = "doctor" | "clinician" | "patient" | "care_coordinator";

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  facility?: string;
  patient_id?: string;
  case_id?: string;
  phone?: string;
  token: string;
}

export interface BookAppointmentPayload {
  case_id: string;
  patient_id: string;
  facility: string;
  provider_name: string;
  appointment_type: string;
  scheduled_time: string;
  notes?: string;
}

export interface CancelAppointmentPayload {
  cancellation_reason: string;
  cancelled_by?: string;
  notes?: string;
}

export interface RescheduleProposePayload {
  proposed_slots: string[];
  reason: string;
  proposed_by?: string;
}

export interface RescheduleAcceptPayload {
  selected_slot: string;
  accepted_by: string;
  partner_confirmed?: boolean;
}
