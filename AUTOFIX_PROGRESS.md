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
- **Status:** TODO
- **Goal:** After login the user always lands on a NEW empty chat for their own role, and can reopen past chats deliberately.
- **Root Cause (file:line):** Pending
- **Files Changed:** Pending
- **Exact Test Commands & Results:** Pending
- **Remaining Problems:** Pending

---

## Issue 3: AI Chat Quality (Similar to ChatGPT / Claude)
- **Status:** TODO
- **Goal:** Smooth, trustworthy streaming chat with tool verification guard, coordinator routing, and UI polish.
- **Root Cause (file:line):** Pending
- **Files Changed:** Pending
- **Exact Test Commands & Results:** Pending
- **Remaining Problems:** Pending

---

## Issue 2: Coordinator Needs a Patients Area to Manage and Complete Tasks (14 Stages)
- **Status:** TODO
- **Goal:** Coordinator can see every patient, open a case, and perform coordinator-allowed actions producing evidence.
- **Root Cause (file:line):** Pending
- **Files Changed:** Pending
- **Exact Test Commands & Results:** Pending
- **Remaining Problems:** Pending
