# CareBridge Architecture Overview

## Monorepo Layout
- `backend/`: FastAPI backend service containing LangGraph agent orchestration, tools, and persistence.
- `frontend/`: Next.js 14 App Router dashboard, care coordinator control center, and patient portal.
- `infrastructure/`: Docker Compose configurations and Alembic migration scripts.
- `docs/`: System documentation, clinical pathway specs, and simulation cohorts.
- `tests/`: End-to-end integration test suite.

## The Cognitive Care Coordination Loop
Unlike fixed chatbots or hardcoded state machines, CareBridge operates as an autonomous agent:
1. **Understand**: Natural language ingestion (English, Tamil, Tanglish/code-mixing), emotional/barrier extraction (fear, transport, financial, childcare, skepticism).
2. **Context Retrieval**: Load patient memory, case memory, conversation history, accountable coordinator, open tasks, referral state, and SLA countdowns.
3. **Reason & Plan**: Determine optimal next actions using LangGraph with Groq `openai/gpt-oss-120b` without static branching.
4. **Safety Gatekeeper**: Verify autonomy level (Level 1 Autonomous, Level 2 Constrained, Level 3 Clinical Human-in-the-Loop).
5. **Tool Execution**: Invoke validated tools with backend integrity checks.
6. **Observe & Replan**: Reflect on tool results, update memory, and schedule proactive recovery if barriers arise.

---

## Three Levels of Autonomy

| Level | Classification | Governance | Examples |
|---|---|---|---|
| **Level 1** | Autonomous | No routine approval | Understand messages, answer admin questions, translate, summarize cases, send routine reminders, monitor progress. |
| **Level 2** | Constrained Autonomy | Permission-based validation | Suggest appointment slots, book appointments, reschedule/cancel with documented reason, create referrals, reassign coordinator, escalate overdue cases. |
| **Level 3** | Human Authorization | Clinical Oversight Mandatory | Clinical diagnosis, treatment decisions, changing clinical urgency, exceptional routing, final clinical closure verification. |

---

## End-to-End Care Case Ownership

Every active care case must maintain **one accountable Care Coordinator** throughout the journey from abnormal screening detection to verified clinical closure.

### 1. Invariant Ownership Rule
Accountability is **never dropped** due to operational disruptions:
- A doctor cancels an appointment $\rightarrow$ Coordinator ownership is preserved.
- A patient misses an appointment or cancels due to transportation $\rightarrow$ Coordinator ownership is preserved.
- A referral or biopsy report is delayed $\rightarrow$ Coordinator ownership is preserved.
- Patient goes unresponsive $\rightarrow$ Coordinator ownership is preserved while proactive recovery is initiated.

### 2. Emergency Escalation (`UNASSIGNED_ESCALATED`)
If an active case lacks an accountable coordinator, the AI Supervisor immediately transitions the case to `UNASSIGNED_ESCALATED` with `critical` priority, raising immediate administrative alerts.

### 3. Case Closure Requirements (5-Point Checklist)
Before any case can be closed, the Supervisor enforces the 5-point verification checklist:
1. All pending coordination tasks and milestones completed.
2. Clinical evidence (e.g. pathology report, biopsy result) attached to the case.
3. Attending clinician verification and sign-off recorded.
4. No unresolved care barriers or exceptions.
5. Explicit coordinator concurrence.

### 4. Ownership Tools Registry
1. `get_case_owner`: Retrieves the assigned coordinator and their caseload status.
2. `assign_case_owner`: Assigns initial coordinator and seeds `CaseOwnershipHistory`.
3. `transfer_case_ownership`: Reassigns case with reason and maintains an auditable transfer log.
4. `get_pending_case_tasks`: Lists outstanding milestones and overdue work items.
5. `detect_stalled_case`: Flags inactive cases exceeding the threshold (e.g. 5 days) without recorded touchpoints.
6. `notify_case_owner`: Dispatches urgent in-app and email alerts to the coordinator.
7. `escalate_unowned_case`: Triggers emergency administrative supervisor intervention for unassigned active cases.
8. `get_case_closure_requirements`: Evaluates the mandatory 5-point closure checklist.

---

## Doctor Subgraph Architecture

The **Doctor Subgraph** is an integrated extension of the central LangGraph Supervisor. It does not operate as a disconnected system; instead, it shares database persistence, memory layers, and case state with the patient care coordination workflow.

### 1. Core Principles & Governance
- **Physician Authority (Level 3)**: Clinical decisions (impressions, diagnoses, treatment recommendations) and clinical closure sign-offs remain strictly under physician authority. The AI never diagnoses, prescribes, or independently closes cases.
- **End-to-End Coordinator Ownership**: Doctor actions (e.g., appointment cancellations, referral rejections) never strip the Care Coordinator of case accountability.
- **Mandatory Cancellation Reason**: When a doctor cancels an appointment, a specific clinical or operational reason is required before the action is executed.
- **Dual Acceptance for Replacements**: Any replacement appointment created following cancellation or rescheduling requires explicit mutual acceptance from both the doctor and the patient.
- **Immutable Clinician Audit Trail**: All actions executed through the Doctor Subgraph are logged with `actor_type="clinician"`, recording full audit rationale, autonomy levels, and state deltas.

### 2. The 11 Doctor Nodes

| Node | Name | Responsibility | Autonomy Level |
|---|---|---|---|
| 1 | `doctor_intake` | Ingests natural-language requests and classifies doctor intent (NLU + keyword fallback). | Level 1 |
| 2 | `doctor_auth_check` | Validates clinician identity, active status, and doctor-to-patient case assignment permissions. | Level 1 |
| 3 | `doctor_context_retrieval` | Hydrates case context, screening findings, referral status, appointments, and recent timeline events. | Level 1 |
| 4 | `doctor_case_review` | Generates a structured clinical summary of the patient's care trajectory for physician review. | Level 1 |
| 5 | `referral_management` | Executes referral acceptance, rejection (with documented reason), or rerouting. | Level 2 |
| 6 | `appointment_management` | Enforces mandatory cancellation reasons, sets replacement dual-acceptance flags, or confirms availability. | Level 2 |
| 7 | `consultation_management` | Records clinical notes, marks appointment attendance, and updates case clinical history. | Level 1 |
| 8 | `clinical_decision_review` | Records diagnosis impressions and treatment plans under physician authority. | Level 3 |
| 9 | `followup_management` | Schedules post-consultation surveillance, creates clinical follow-up tasks for the coordinator. | Level 2 |
| 10 | `closure_review` | Clinician provides formal verification sign-off (creating `ClosureEvidence`), fulfilling the Level 3 gate. | Level 3 |
| 11 | `doctor_response` | Dispatches structured clinical confirmations, alerts, or actionable responses back to the clinician. | Level 1 |

### 3. Subgraph Topology

```
START ──> doctor_intake ──> doctor_auth_check
                                │
                ┌───────────────┴───────────────┐
                │ [Unauthorized]                │ [Authorized]
                ▼                               ▼
         doctor_response            doctor_context_retrieval
                ▲                               │
                │                 route_doctor_intent
                │           ┌───────────────────┼───────────────────┐
                │           ▼                   ▼                   ▼
                ├─ doctor_case_review   referral_management  appointment_management
                ├─ consultation_mgmt    clinical_decision    followup_management
                └─ closure_review
                        │
                        ▼
                       END
```

---

## Phase 5: Agent Tool Ecosystem

CareBridge provides a modular, domain-driven agent tool ecosystem. Rather than a monolithic tool execution function, tools are decoupled into 7 distinct clinical and operational domains with strict input/output typing, permission verification, error containment, and audit logging.

### 1. Architectural Guardrails & Invariants
- **Strong Typing**: Every tool accepts a strongly-typed Pydantic input schema and returns a `ToolResult[T]` response envelope containing a typed output schema, execution status, and audit ID.
- **Autonomy & Role Validation**: Every tool execution validates the caller's role against permissible autonomy levels:
  - *Level 1 (Autonomous)*: Demographic lookups, context retrieval, message translation/drafting, appointment searches, status tracking.
  - *Level 2 (Constrained)*: Case creation, ownership assignment, consent-gated communication dispatch, referral creation, appointment booking, rescheduling with mandatory reasons, task generation, escalation.
  - *Level 3 (Human Gate)*: Final clinical closure verification and diagnosis impressions. AI never approves closure independently.
- **Active Patient Consent**: Outbound communication tools verify active consent scope before message dispatch.
- **Idempotency Protection**: Critical creation operations (e.g. `create_care_case`, `create_referral_request`, `book_appointment`) check for existing active entities to prevent duplicate records.
- **Immutable Audit Trails**: Every state-modifying action records an `AuditLog` entry in the database.

### 2. Domain Tool Matrix

| Domain | Tool Name | Description | Autonomy Level |
|---|---|---|---|
| **Patient** | `retrieve_patient_profile` | Retrieves demographic data, MRN, language, and known care barriers. | Level 1 |
| **Patient** | `retrieve_patient_preferences` | Retrieves language, channel preferences, accessibility requirements, and consents. | Level 1 |
| **Patient** | `retrieve_conversation_history` | Chronological communication records and active session summary. | Level 1 |
| **Case** | `create_care_case` | Initializes a care case from an abnormal screening result (idempotent). | Level 2 |
| **Case** | `retrieve_case_details` | In-depth case details, SLA status, accountable owner, and barriers. | Level 1 |
| **Case** | `retrieve_case_events` | Immutable timeline event history for a case. | Level 1 |
| **Case** | `update_case_notes` | Appends progress notes and records discovered barriers. | Level 1 |
| **Case** | `assign_administrative_ownership` | Assigns an accountable coordinator and updates ownership history. | Level 2 |
| **Communication** | `draft_patient_message` | Formulates empathetic, culturally tailored, non-alarmist outreach. | Level 1 |
| **Communication** | `translate_message` | Multilingual translation maintaining clinical tone and clarity. | Level 1 |
| **Communication** | `send_permitted_communication` | Dispatches outreach message after active consent verification. | Level 2 |
| **Communication** | `record_acknowledgement` | Records patient confirmation and completes outreach tasks. | Level 1 |
| **Referral** | `create_referral_request` | Dispatches inter-facility referral with a 48h SLA deadline. | Level 2 |
| **Referral** | `check_referral_status` | Checks acceptance status and overdue flags. | Level 1 |
| **Referral** | `retrieve_referral_information` | Retrieves all referrals and active referral details for a case. | Level 1 |
| **Appointment** | `search_available_appointments` | Searches open slots at clinics within the clinical SLA window. | Level 1 |
| **Appointment** | `book_appointment` | Reserves an appointment within SLA deadline constraints. | Level 2 |
| **Appointment** | `reschedule_appointment` | Reschedules appointment with mandatory reason and dual-acceptance flag. | Level 2 |
| **Appointment** | `retrieve_appointment_status` | Current appointment status and attendance history. | Level 1 |
| **Recovery** | `create_followup_task` | Creates actionable coordinator milestones or surveillance tasks. | Level 2 |
| **Recovery** | `identify_stalled_cases` | Flags cases exceeding inactivity thresholds without recorded touchpoints. | Level 1 |
| **Recovery** | `propose_recovery_action` | Formulates recovery playbooks based on identified barriers. | Level 1 |
| **Recovery** | `escalate_case` | Escalates at-risk cases to critical emergency queues. | Level 2 |
| **Closure** | `retrieve_closure_evidence` | Evaluates evidence and the 5-point closed-loop care verification checklist. | Level 1 |
| **Closure** | `request_closure_verification` | Requests clinician review and sign-off (Level 3 Gate). AI cannot self-close. | Level 3 |

---

## Phase 6: Autonomous Care Coordination

CareBridge implements adaptive, context-driven care coordination across the complete screening-to-care loop:
`Actionable screening result → Patient communication → Acknowledgement → Consultation → Referral → Appointment → Follow-up → Recovery → Evidence-based closure`

### 1. Adaptive Interaction Principles
Unlike fixed chatbots or rigid rule trees that force every patient through identical branching:
1. **Patient Questions First**: If the patient asks clinical or diagnostic questions (e.g., "What does BI-RADS 4 mean?", "Is it cancer?"), the AI retrieves screening context and provides compassionate, plain-language education before pushing appointment scheduling.
2. **Barrier-Aware Recovery**: When a patient cannot attend (e.g. caregiver out of town, transportation lack, childcare), the AI detects the social determinant barrier, reschedules within SLA, and creates a designated follow-up task without dropping Care Coordinator accountability.
3. **Delayed Referral Liaison**: If an inter-facility specialist referral is stalled beyond the 48-hour SLA deadline, the AI inspects referral status and raises coordinator alerts for direct clinical liaison.
4. **Missed Appointment Care Recovery**: If an appointment is missed, the AI initiates proactive recovery plays to determine the barrier rather than abandoning the case.
5. **Patient Assistance Routing**: When logistical or financial hurdles are flagged, the AI tasks the coordinator to connect the patient with social work, transport vouchers, or assistance funds.
6. **Emergency Escalation Protocol**: Acute symptoms (severe bleeding, chest pain) or explicit care refusals immediately trigger emergency escalation to human supervisory staff (`ESCALATED` / `critical` priority).
7. **Human-in-the-Loop Clinical Verification Gate (Level 3)**: Case closure requires verified clinical evidence and attending physician sign-off. AI assists in evidence collection and checklist evaluation, but never signs off independently.

---

## Phase 7: Care Recovery Agent

The **Care Recovery Agent** is a specialized, intelligent sub-agent orchestrated via LangGraph. Its purpose is to understand *why* a care journey is not progressing and dynamically formulate and execute an appropriate recovery strategy.

### 1. Multi-Source Context Retrieval (8 Operational Dimensions)
The agent retrieves and synthesizes 8 distinct operational context sources:
1. **Case History & Events**: Status, pathway, priority, created/updated timestamps, accountable owner, and complete `CaseEvent` chronological timeline.
2. **Patient Conversations & Messages**: Full inbound and outbound communications transcript, delivery channels, language, and `ConversationSession` commitments and unanswered questions.
3. **Previous Communication Attempts**: Total outreach attempts, patient replies, channels used (SMS, WhatsApp, phone), and hours elapsed since last touchpoint.
4. **Referral Status & Clinic Handoffs**: Specialty referral records, target clinics, acceptance status, deadlines, and stalled referral detection (>48h without clinic acceptance).
5. **Appointment History**: Complete visit records, attendance verification, no-show counts, cancellation reasons, and replacement status.
6. **Patient Preferences & Profile**: Preferred language, communication channel, accessibility requirements, caregiver contacts, and documented social barriers.
7. **Outstanding Tasks & Overdue Milestones**: Open coordination tasks, due dates, overdue milestones, and assigned owner.
8. **SLA Context & Telemetry**: Deterministic SLA clock (`normal`, `warning`, `breached`), hours remaining, urgency, and case inactivity duration in days.

### 2. Facts vs. Assumptions Separation Engine
A foundational principle of CareBridge recovery is that **the AI must distinguish known facts from working assumptions and must never assume all missed appointments share the same cause**:
- **Known Facts**: Verified system records (e.g. appointment marked `no_show` by clinic, referral sent 3 days ago without acceptance, SLA warning with 12h remaining) or explicit direct statements from the patient/caregiver (e.g. *"I don't have a car to drive there"*, *"I'm terrified of what the biopsy will find"*, *"My daughter is sick"*).
- **Assumptions**: Hypotheses or inferences where the patient has not confirmed the cause (e.g. guessing that a missed appointment was caused by lack of transit, or assuming unresponsiveness indicates care refusal).
- **Patient Clarification Protocol**: If the delay reason is unverified (only assumptions exist), the agent **must not** apply an arbitrary barrier playbook. Instead, it flags `needs_clarification = True` and reaches out with an empathetic, non-punitive inquiry in the patient's language asking what happened and what support would help.

### 3. Context-Aware Recovery Playbooks

| Playbook | Trigger Condition | Strategy & Actions | Autonomy |
|---|---|---|---|
| `clarification_inquiry` | Missed visit or drop-off with unverified cause (`needs_clarification = True`) | Empathetic inquiry asking what occurred, offering support, and scheduling a coordinator check-in. | Level 2 |
| `transportation_support` | Known transportation barrier confirmed | Transit vouchers, medical ride service coordination, accessible clinic routing, and appointment hold. | Level 2 |
| `caregiver_coordination` | Known family or caregiver dependency confirmed | Evening and weekend slots, dual outreach to patient and designated caregiver contact. | Level 2 |
| `fear_anxiety_support` | Known procedure dread or diagnosis fear | Compassionate procedure education, comfort measures, and nurse pre-consultation telephone call. | Level 2 |
| `financial_assistance` | Known co-pay or insurance coverage obstacle | Sliding-scale financial counseling referral, charity care assistance, and temporary appointment reservation. | Level 2 |
| `schedule_work_conflict` | Known work or shift scheduling barrier | Multi-slot offer (early morning, late evening, Saturday) and employer medical excuse documentation. | Level 2 |
| `unacknowledged_reengagement` | Outreach unacknowledged across escalating attempts | Attempt 1: Gentle primary channel reminder. Attempt 2: Channel switch / phone outreach. Attempt 3: Urgent notification. | Level 2 |
| `delayed_referral_liaison` | Specialist clinic referral stalled >48h | Direct coordinator task to contact receiving facility, expedite review, and alert clinic staff. | Level 2 |
| `emergency_escalation` | Recovery attempts $\ge 3$, SLA breached, or acute refusal | Escalates to `ESCALATED`, sets priority `critical`, and routes to urgent clinical/supervisory desk. | Level 2 |

### 4. Dynamic Multilingual Messaging Engine
The agent avoids rigid robotic copy and never uses a single fixed template:
- Adapts tone and phrasing based on recovery attempt count (Attempt 1: warm & gentle; Attempt 2: supportive options; Attempt 3: urgent notice).
- Generates culturally tailored messages in the patient's preferred language (`en`, `es`, `ta`, etc.).
- Leverages LLM prompting with structured safety fallbacks to guarantee delivery.

### 5. Multi-Attempt Progression & Adaptive Recovery Cycle
1. **Attempt 1**: Empathetic check-in, clarification inquiry, or specific barrier assistance on preferred channel.
2. **Attempt 2**: Adapted strategy, alternate channel (e.g. phone call task), or caregiver involvement.
3. **Attempt 3**: Urgent Care Coordinator direct outreach or community health worker task.
4. **Attempt $\ge 3$ or SLA Breached**: Emergency escalation to human clinical supervisor.

### 6. Coordinator Accountability & Safety Governance
- **Unbroken Ownership**: The designated Care Coordinator retains case ownership (`case.current_owner_id`) throughout all recovery plays. Recovery never drops accountability.
- **Coordinator Alerting**: Every recovery cycle notifies the accountable coordinator via `notify_case_owner` and logs structured timeline events in `CaseEvent`.
- **Level 3 Clinical Gate**: AI never diagnoses, prescribes, or independently approves clinical closure during recovery. All sensitive medical actions require human clinician authorization.

---

## Phase 8: Long-Running Agent Workflows

The CareBridge platform is designed for patient coordination journeys that span days, weeks, and months. In production, **agents never remain active in a single long-lived HTTP request** while awaiting patient responses or clinical milestones. Instead, workflows execute in short, stateless bursts and persist runtime checkpoints to PostgreSQL.

### 1. Asynchronous Workflow Suspension & PostgreSQL Checkpointing
- **Zero HTTP Blocking**: When an outreach message is dispatched or an appointment is coordinated, the workflow saves its state and suspends immediately (`status="suspended_waiting_for_patient"`). The HTTP connection terminates with status 200 or 202 without blocking.
- **PostgreSQL Checkpointer (`PostgresSaver`)**: Persistent checkpointer backing with automated fallback to `MemorySaver` for unit tests and local development.
- **Thread-Level Case Isolation**: Every workflow run is scoped to a case-specific thread ID (`care-thread-{case_id}`). Checkpoint state is strictly segregated per case.
- **State Inspection & Rollback**: Exposes `inspect_checkpoint_history(checkpointer, thread_id)` and `get_latest_checkpoint_state` to allow inspection and safe rollbacks.

### 2. Event-Driven Workflow Resumption & Webhooks
Workflows resume asynchronously in response to external events without manual polling:
1. **Inbound Patient Messages**: Resumes the cognitive supervisor loop on patient SMS, WhatsApp, or portal messages.
2. **Clinic Attendance Events**: Marks appointments as `attended`, advancing the workflow to closure verification.
3. **Clinic No-Show Events**: Marks visits as `no_show` and automatically invokes the Care Recovery Agent.
4. **Appointment Cancellation Events**: Records mandatory cancellation reasons and begins rebooking.
5. **Referral Updates**: Marks specialist referrals as `accepted` or `rejected`, advancing to appointment scheduling or coordinator alerting.
6. **Clinical Sign-Off**: Clinicians provide Level 3 verification, completing closed-loop closure.

### 3. Background Surveillance Scheduler
A dedicated, thread-safe background scheduler (`BackgroundSchedulerManager`) executes periodic surveillance jobs to monitor inactive cases without human prompting:
1. `scan_stalled_cases`: Scans active cases with $\ge 5$ days of inactivity and automatically invokes the Care Recovery Agent.
2. `scan_sla_deadlines`: Evaluates deterministic SLA clocks; raises coordinator warnings ($< 72\text{h}$) or triggers emergency escalations (`breached`).
3. `scan_unacknowledged_outreach`: Identifies patient outreach sent $> 24\text{h}$ ago with no patient confirmation, advancing drop-off triage.
4. `scan_overdue_tasks`: Scans pending coordination tasks past due dates and alerts the accountable coordinator.

### 4. Resilience, Idempotency & De-duplication
- **Idempotent Tool Execution (`IdempotencyManager`)**: Operations like case initiation, appointment booking, and referral dispatch enforce deterministic idempotency keys (`operation:{case_id}:{hash}`). Repeated calls return cached results without duplicate side effects.
- **Duplicate Message Prevention (`DuplicateMessageFilter`)**:
  - *Inbound De-duplication*: Hashes sender, case ID, and content to drop duplicate webhook retries within a 120-second window.
  - *Outbound Spam Suppression*: Enforces cooldowns (e.g. 12h) to avoid bombarding patients with identical outreach categories.
- **Exponential Backoff Retry Policy (`RetryPolicy`)**: Wraps transient network, LLM, or database failures with configurable retries, jitter, and backoff multipliers.
- **Failure Recovery (`retry_failed_workflow`)**: Allows resuming failed workflow threads from the last committed checkpoint.

### 5. Structured Execution Traces & Coordinator Action History
- **Relational Trace Persistence (`WorkflowExecutionTrace`)**: Stores node names, step numbers, execution durations (ms), input/output summaries, and error logs in PostgreSQL.
- **Coordinator-Readable Action History**: Translates technical graph transitions into plain-language prose (e.g., *"AI matched screening finding to approved clinical protocol and established diagnostic workup requirements."*), accessible via `/api/v1/workflows/{case_id}/history`.
- **Database as Source of Truth**: LangGraph checkpoints preserve execution graphs, while core relational tables (`CareCase`, `Patient`, `Appointment`, `Communication`, `Task`, `AuditLog`, `CaseEvent`) remain the immutable source of truth.



