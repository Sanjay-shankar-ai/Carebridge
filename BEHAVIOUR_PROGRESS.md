# CareBridge AI Behaviours - Progress

Branch: `feat/ai-behaviours` (never pushed). Synthetic data only.

| ID | Behaviour | Status | Files | Test result (exact) |
|----|-----------|--------|-------|---------------------|
| B0 | Baseline full suite (before changes) | DONE | `backend/tests/.baseline_failures.txt` | `pytest backend/tests -q` -> **37 failed, 256 passed, 13 errors in 262.81s** (50 failing/erroring IDs saved). Causes seen: tests using an SQLite DB with missing tables (`no such table: case_owners`) and tests needing the live API server on :8000 (not running during the run). Not caused by this work. |
| B1 | Report summary in plain language | DONE | `services/report_explanation_service.py` (explain_report tool, mark_delivered, finalized check, JSON-copy fix), `services/patient_behaviour_router.py`, `models/transport.py`, `api/v1/endpoints/agent.py` (router wired into stream), `tests/behaviours/conftest.py`, `tests/behaviours/test_b1_report_summary.py` | `pytest backend/tests/behaviours/test_b1_report_summary.py` -> **10 passed in 4.87s** (real Postgres `carebridge_test`, LLM mocked). Live-server smoke check still pending (end of run). |
| B2 | Transport requests | TODO | - | - |
| B3 | Cancellation with WHY question | TODO | - | - |
| B4 | Fear / panic about the report | TODO | - | - |
| B5 | Proactive follow-up job | TODO | - | - |
| B6 | Conversation quality + reviewed knowledge | TODO | - | - |

## Notes
- The brief says "CONVERSATION PROMPT and knowledge files below" but none were attached; B6 creates them from the rules in the brief.
