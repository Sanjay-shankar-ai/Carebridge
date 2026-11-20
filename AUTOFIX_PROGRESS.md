# CareBridge Autofix Progress Tracker

**Branch:** `fix/website-issues`  
**Initial Test Suite Baseline:**
- Collected: 249 tests
- Passed: 228
- Failed: 21
- Command: `cd c:\CareBridge\backend; pytest tests -v`
- Execution Timestamp: 2026-11-20T09:43:39Z

---

## Issue 4: Existing Demo Users Get "Wrong Password"
- **Status:** DONE
- **Goal:** Every seeded demo user (patient, doctor, coordinator) can log in with its documented password.
- **Root Cause (file:line):**
  1. `backend/app/api/v1/endpoints/auth.py:366-383`: Leaked credential failure specifics by distinguishing non-existent user (`detail=f"Invalid credentials. No registered user found for '{req.email}'."`) vs incorrect password (`detail="Invalid credentials. Incorrect password provided."`), allowing user enumeration and oracle attacks. Lacked correlation ID tagging and standard masking on unexpected 500 errors.
  2. Missing idempotent reset tool `scripts/reset_demo_users.py` reading credentials from environment variables or gitignored local secrets without hardcoding in repository.
- **Files Changed:**
  - `backend/app/api/v1/endpoints/auth.py`
  - `scripts/reset_demo_users.py`
  - `.env.example`
  - `.gitignore`
  - `backend/tests/test_issue4_auth_fixes.py`
- **Exact Test Commands & Results:**
  - `python scripts/reset_demo_users.py` -> Successfully updated all 6 demo users across doctor, coordinator, and patient roles idempotently.
  - `cd backend; pytest tests/test_issue4_auth_fixes.py -v` -> 7 passed, 0 failed (Doctor login 200, Coordinator login 200, Patient login 200, Case/whitespace variants 200, Non-leaking wrong password 401 generic message, Non-leaking non-existent email 401 generic message, Deactivated account 403).
- **Remaining Problems:** None. Issue 4 is completely resolved.

---

## Issue 1: Previous Chat Appears After Login; New Chat Must Be Shown
- **Status:** DONE
- **Goal:** After login the user always lands on a NEW empty chat for their own role, and can reopen past chats deliberately.
- **Root Cause (file:line):**
  1. `frontend/app/chat/page.tsx:86-90`: Client forcibly defaulted to `targetCase = caseList[0]` and auto-fetched `loadCaseMessages(caseList[0])` upon page load, immediately displaying old case chat messages.
  2. `frontend/context/AuthContext.tsx`: Did not invoke chat state and conversation storage clearing during login and logout, leaking conversation IDs across user sessions.
  3. `backend/app/models/communication.py:11-30`: `conversation_sessions` lacked explicit `(user_id, role, title)` columns and `communications` table lacked `(user_id, role)`, tying sessions only to case/patient rather than authenticated user context.
  4. `backend/app/api/v1/endpoints/agent.py`: Missing server-side ownership enforcement on `GET /agent/history`, `GET /agent/sessions`, `PATCH /agent/sessions/{session_id}`, and `DELETE /agent/sessions/{session_id}`.
- **Files Changed:**
  - `backend/app/models/communication.py`
  - `backend/app/api/v1/endpoints/agent.py`
  - `backend/scripts/sync_db_schema.py`
  - `frontend/context/AuthContext.tsx`
  - `frontend/services/api.ts`
  - `frontend/app/chat/page.tsx`
  - `backend/tests/test_issue1_chat_isolation.py`
- **Exact Test Commands & Results:**
  - `cd backend; pytest tests/test_issue1_chat_isolation.py -v` -> 6 passed in 6.66s:
    - `test_user_a_creates_chat_and_receives_session`: PASSED (Session lazily initialized with `user_id` and `role`)
    - `test_user_b_cannot_access_user_a_session`: PASSED (Strict 403 Forbidden on foreign conversation)
    - `test_nonexistent_session_returns_404`: PASSED (404 Not Found on invalid session)
    - `test_sessions_list_isolation`: PASSED (Sessions filtered strictly by authenticated user)
    - `test_rename_and_delete_session_permissions`: PASSED (Owner can rename/delete; foreign user gets 403)
    - `test_coordinator_starts_with_no_patient_context`: PASSED (Empty context initialized with zero patient data)
- **Remaining Problems:** None. Issue 1 is completely resolved.

---

## Issue 3: AI Chat Quality (Similar to ChatGPT / Claude)
- **Status:** DONE
- **Goal:** Smooth, trustworthy streaming chat with tool verification guard, coordinator routing, and UI polish.
- **Root Cause (file:line):**
  1. `backend/app/api/v1/endpoints/agent.py:103-160`: Missing SSE token streaming endpoints (`POST /agent/stream` and `/agent/interact?stream=true`). Chat was previously blocking and returned monolithic responses without `token`, `tool_started`, `tool_result`, `final`, or `error` events.
  2. `backend/app/services/response_guard_service.py:25-58`: Missing `NOTIFICATION_DISPATCHED` action mapping and strict rewrite validation for ungrounded claims during streaming.
  3. `frontend/app/chat/page.tsx:265-330`: Lacked SSE stream consumption, Stop generating button with `AbortController`, auto-scroll pause with "scroll to bottom" button, action status chip row derived strictly from `tool_result` events, multi-line auto-growing textarea, and markdown rendering.
- **Files Changed:**
  - `backend/app/api/v1/endpoints/agent.py`
  - `backend/app/services/response_guard_service.py`
  - `frontend/types/index.ts`
  - `frontend/services/api.ts`
  - `frontend/components/MarkdownRenderer.tsx`
  - `frontend/app/chat/page.tsx`
  - `backend/tests/test_issue3_streaming_chat.py`
- **Exact Test Commands & Results:**
  - `cd backend; pytest tests/test_issue3_streaming_chat.py -v` -> 6 passed in 3.90s:
    - `test_streaming_yields_ordered_events`: PASSED (Ordered sequence `token`, `tool_started`, `tool_result`, `final`)
    - `test_coordinator_operational_question_routes_correctly`: PASSED (Operational query triggers `discover_new_patients` with DB query)
    - `test_guard_blocks_fabricated_success_claim`: PASSED (Response guard blocks ungrounded action claims and rewrites them)
    - `test_markdown_is_sanitised`: PASSED (Dangerous protocols `javascript:`, `data:` sanitized to `#`)
    - `test_llm_failure_produces_clear_message_and_no_false_success`: PASSED (Yields friendly `error` event, never false success)
    - `test_cancellation_stops_generation`: PASSED (Clean disconnect on Stop button abort, zero server 500s)
- **Remaining Problems:** None. Issue 3 is completely resolved.

---

## Issue 2: Coordinator Needs a Patients Area to Manage and Complete Tasks (14 Stages)
- **Status:** TODO
- **Goal:** Coordinator can see every patient, open a case, and perform coordinator-allowed actions producing evidence.
- **Root Cause (file:line):** Pending
- **Files Changed:** Pending
- **Exact Test Commands & Results:** Pending
- **Remaining Problems:** Pending
