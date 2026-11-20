# CareBridge Demo Implementation Progress

## Baseline Test Suite Status
- **Initial Baseline Run:** `pytest tests -q`
- **Results:** 242 passed, 21 failed, 13 errors, 3 warnings (Total: 276 tests executed)
- Note: Pre-existing failures are largely from legacy SQLite fixture tests vs PostgreSQL 17 runtime or unmocked external providers. None of the existing tests will be weakened, skipped, or deleted.

---

## Task 1: Judge Demo Data (One Doctor, One Patient, One Coordinator)
- **Status:** DONE
- **Root Cause & Objective:** Seed the exact judge demo cohort (Meera Krishnan, Dr. Arjun Menon, Priya Nair) using domain models and lifecycle transitions.
- **Files Changed / Added:**
  - `scripts/seed_judge_demo.py` (idempotent seed script creating Meera Krishnan at Stage 3 done, Stage 4 pending, Dr. Arjun Menon with 4-week Mon/Wed/Fri calendar, Priya Nair, Rahul Das unassigned intake, 3 notifications, and synthetic report PDF)
  - `scripts/reset_judge_demo.py` (restores exact starting state before judge demos)
  - `DEMO_ACCESS.md` (complete judge access and evaluation walkthrough, no passwords)
  - `backend/tests/test_judge_demo_data.py` (6/6 verification tests)
- **Exact Test Commands & Results:**
  - Command: `pytest tests/test_judge_demo_data.py -v`
  - Output: `6 passed in 10.05s`
    - `test_seeded_users_can_login_with_env_passwords` PASSED
    - `test_seeded_patient_shows_stage_3_complete_and_stage_4_pending` PASSED
    - `test_seed_twice_creates_no_duplicates` PASSED
    - `test_reset_returns_to_exact_starting_state` PASSED
    - `test_unassigned_patient_in_coordinator_queue` PASSED
    - `test_doctor_weekly_schedule_table` PASSED

---

## Task 2: Counselling-Style Patient AI (Replace Cold Answers)
- **Status:** TODO
- **Goal:** Implement patient counselling prompt and deterministic distress/crisis safety guard.
- **Files:** TBD
- **Test Commands & Results:** TBD

---

## Task 3: Coordinator Report Upload with Browse Button
- **Status:** TODO
- **Goal:** Add Browse files + drag-and-drop component, backend validation, OCR/text extraction, and finalize workflow.
- **Files:** TBD
- **Test Commands & Results:** TBD

---

## Task 4: Medical Report -> Plain Language
- **Status:** TODO
- **Goal:** Implement `explain_report` with structured summary, reviewed glossary, reading level grade 6-8, streaming, and Stage 4 lifecycle completion.
- **Files:** TBD
- **Test Commands & Results:** TBD
