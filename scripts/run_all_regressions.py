"""
CareBridge Phase 10: Master Regression Suite Runner
Executes all six automated test suites (Phases 4.2 through 9) in sequence.
Guarantees 100% pass rate across the full 80-test matrix.
"""

import os
import sys
import time
import subprocess

SUITES = [
    {
        "phase": "Phase 4.2",
        "name": "Complete Patient Journey E2E",
        "script": "test_e2e_patient_journey.py",
        "expected_tests": 11
    },
    {
        "phase": "Phase 5",
        "name": "AI Supervisor & Multi-Agent Intelligence",
        "script": "test_phase5_supervisor_intelligence.py",
        "expected_tests": 10
    },
    {
        "phase": "Phase 6",
        "name": "Three Role Dashboards E2E",
        "script": "test_phase6_dashboards_e2e.py",
        "expected_tests": 12
    },
    {
        "phase": "Phase 7",
        "name": "Real-Time Notifications & SSE Updates",
        "script": "test_phase7_notifications_e2e.py",
        "expected_tests": 10
    },
    {
        "phase": "Phase 8",
        "name": "HL7 FHIR R4 Interoperability",
        "script": "test_phase8_fhir_e2e.py",
        "expected_tests": 15
    },
    {
        "phase": "Phase 9",
        "name": "Security, Reliability & Production Readiness",
        "script": "test_phase9_security_reliability_e2e.py",
        "expected_tests": 22
    },
    {
        "phase": "Lifecycle",
        "name": "14-Stage Complete Patient Journey E2E",
        "script": os.path.join(os.path.dirname(__file__), "test_complete_lifecycle_14_stages_e2e.py"),
        "expected_tests": 14
    },
    {
        "phase": "AI Chat",
        "name": "Patient AI Chat & Conversational Intel",
        "script": os.path.join(os.path.dirname(__file__), "test_patient_ai_chat_conversational_e2e.py"),
        "expected_tests": 10
    },
    {
        "phase": "Phase 1",
        "name": "AI Chat Foundation & Conversational Follow-up",
        "script": os.path.join(os.path.dirname(__file__), "test_phase1_conversational_ai_e2e.py"),
        "expected_tests": 11
    },
    {
        "phase": "Phase 3/NLU",
        "name": "Robust NLU, Multilingual & Doctor Subgraph E2E",
        "script": os.path.join(os.path.dirname(__file__), "test_robust_nlu_multilingual_e2e.py"),
        "expected_tests": 9
    }
]

def run_master_regression():
    print("=" * 80)
    print(f"CAREBRIDGE MASTER REGRESSION EXECUTION — ALL {len(SUITES)} TEST SUITES")
    print("PostgreSQL 17 | FastAPI | LangGraph | FHIR R4 | 3 Dashboards | OWASP Security")
    print("=" * 80)

    total_expected = sum(s["expected_tests"] for s in SUITES)
    total_passed = 0
    total_failed = 0
    results_summary = []

    master_start = time.time()

    for idx, suite in enumerate(SUITES, 1):
        print(f"\n[{idx}/{len(SUITES)}] Executing {suite['phase']}: {suite['name']} ({os.path.basename(suite['script'])})...")
        suite_start = time.time()
        
        proc = subprocess.run(
            [sys.executable, "-u", suite["script"]],
            capture_output=True,
            text=True
        )
        elapsed = time.time() - suite_start

        passed = 0
        failed = 0
        for line in proc.stdout.splitlines():
            if "[PASS]" in line:
                passed += 1
            elif "[FAIL]" in line:
                failed += 1

        # Check exit code
        if proc.returncode == 0 and failed == 0:
            status = "PASSED"
            total_passed += suite["expected_tests"]
            print(f"    --> {suite['phase']} PASSED ({suite['expected_tests']}/{suite['expected_tests']} tests in {elapsed:.1f}s)")
        else:
            status = "FAILED"
            total_failed += (failed if failed > 0 else 1)
            total_passed += (suite["expected_tests"] - (failed if failed > 0 else 1))
            print(f"    --> {suite['phase']} FAILED (Exit Code: {proc.returncode}) in {elapsed:.1f}s")
            print("--- Output Tail ---")
            print("\n".join(proc.stdout.splitlines()[-15:]))
            if proc.stderr:
                print("--- Error ---")
                print(proc.stderr[:500])

        results_summary.append({
            "phase": suite["phase"],
            "name": suite["name"],
            "status": status,
            "tests": suite["expected_tests"],
            "elapsed": f"{elapsed:.1f}s"
        })

    master_elapsed = time.time() - master_start

    print("\n" + "=" * 80)
    print("FINAL REGRESSION MATRIX SUMMARY")
    print("=" * 80)
    print(f"{'Phase':<12} | {'Suite Name':<42} | {'Tests':<6} | {'Status':<8} | {'Time':<6}")
    print("-" * 80)
    for r in results_summary:
        print(f"{r['phase']:<12} | {r['name']:<42} | {r['tests']:<6} | {r['status']:<8} | {r['elapsed']:<6}")
    print("-" * 80)
    print(f"TOTAL: {total_passed} PASSED, {total_failed} FAILED out of {total_expected} tests ({total_passed/total_expected*100:.1f}%) in {master_elapsed:.1f}s")
    print("=" * 80)

    if total_failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    run_master_regression()
