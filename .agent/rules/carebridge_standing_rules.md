# CareBridge: Standing Rules

CareBridge is an existing AI-powered healthcare care-coordination platform.
Stack: FastAPI, PostgreSQL 17, SQLAlchemy, LangGraph Supervisor, Patient AI,
Doctor LangGraph Subgraph, Care Coordination / Recovery / Clinical Escalation /
Doctor Review agents, Next.js/React, SSE notifications, FHIR R4, 14-stage lifecycle.
Application roles are exactly: PATIENT, DOCTOR, CARE_COORDINATOR. Never add an Admin role.

## Core invariants
1. PostgreSQL domain records are the only source of truth for identity, cases,
   screening requirements/orders, reports, assignments, referrals, appointments,
   consultations, follow-up, tasks, notifications, lifecycle stages and closure.
2. AI memory and frontend state never decide that an action is complete.
3. Lifecycle stages change only through ONE transition service, and only with
   persisted evidence. Invalid transitions are rejected.
4. Agents select and invoke tools. Domain services own business rules, auth,
   validation, transactions, idempotency, evidence and events.
5. A notification is never a substitute for a task. Every handoff creates a
   persisted task or assignment request.
6. The assistant may only report state supported by a successful tool result in
   the current turn. A final guard must reject or rewrite any reply claiming an
   action (booking, order, referral, notification, upload) with no matching
   successful tool result.
7. Every authenticated role gets only its own context. A new coordinator
   conversation never inherits patient context. A patient never sees another
   patient's data. A doctor never receives an unauthorized case.
8. Routing uses LLM-based interpretation, structured output and authorized tool
   calls, not keyword-only rules.

## Strict rules
- Do not rebuild the platform, replace the database, or add parallel agent systems.
- Audit what exists before adding anything. Extend or consolidate; do not create
  a second notification service or a second lifecycle system.
- Do not add unnecessary agents. Do not hardcode individual patient examples.
- Do not bypass authorization. Do not weaken or delete tests to make them pass.
- Do not silently swallow exceptions. Do not fabricate tool success.
- Never log passwords, JWTs, API keys or unnecessary clinical details.
- Use synthetic patient data only. Preserve existing FHIR functionality.
- Schema changes require Alembic migrations, a backup step and a backfill or
  reconciliation plan. Stop and report any migration or data-integrity risk.
- Never claim tests passed unless you ran them and show the exact command and output.
- Implement one approved phase at a time. Stop for approval after each phase.
