"""
CareBridge Diagnostic CLI — Workflow Trace Inspector
Phase 6, Item 4

Usage:
    python -m scripts.trace_workflow --patient <patient_id>
    python -m scripts.trace_workflow --workflow <run_id>
    python -m scripts.trace_workflow --case <case_id>
"""

import argparse
import sys
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.database.session import get_sync_db
from app.models.workflow_trace import WorkflowExecutionTrace
from app.models.care_case import CareCase
from app.models.patient import Patient
from app.models.notification import Notification


# ─── Formatting helpers ────────────────────────────────────────────────────────

COL_WIDTHS = {
    "STEP":      5,
    "NODE":      28,
    "STATUS":    13,
    "DURATION":  12,
    "TIMESTAMP": 26,
    "NOTE":      35,
}

HEADER = (
    f"{'STEP':<{COL_WIDTHS['STEP']}} "
    f"{'NODE':<{COL_WIDTHS['NODE']}} "
    f"{'STATUS':<{COL_WIDTHS['STATUS']}} "
    f"{'DURATION':>{COL_WIDTHS['DURATION']}} "
    f"{'TIMESTAMP':<{COL_WIDTHS['TIMESTAMP']}} "
    f"{'NOTE':<{COL_WIDTHS['NOTE']}}"
)
DIVIDER = "-" * len(HEADER)


def _fmt_duration(ms: float) -> str:
    if ms < 1000:
        return f"{ms:.1f}ms"
    return f"{ms / 1000:.2f}s"


def _fmt_ts(dt: datetime) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _fmt_note(note: str | None) -> str:
    if not note:
        return ""
    return note[:COL_WIDTHS["NOTE"] - 1]


def _print_trace_row(t: WorkflowExecutionTrace) -> None:
    print(
        f"{t.step_number:<{COL_WIDTHS['STEP']}} "
        f"{t.node_name[:COL_WIDTHS['NODE']]:<{COL_WIDTHS['NODE']}} "
        f"{t.status:<{COL_WIDTHS['STATUS']}} "
        f"{_fmt_duration(t.duration_ms):>{COL_WIDTHS['DURATION']}} "
        f"{_fmt_ts(t.executed_at):<{COL_WIDTHS['TIMESTAMP']}} "
        f"{_fmt_note(t.coordinator_note):<{COL_WIDTHS['NOTE']}}"
    )


def _print_traces(traces: list[WorkflowExecutionTrace], label: str) -> None:
    print(f"\n{'=' * len(HEADER)}")
    print(f"  Workflow Trace — {label}")
    print(f"{'=' * len(HEADER)}")
    print(HEADER)
    print(DIVIDER)
    for t in traces:
        _print_trace_row(t)
    print(DIVIDER)
    print(f"  {len(traces)} step(s) total")


def analyze_traces(traces: list[WorkflowExecutionTrace]) -> dict:
    """Analyze traces to extract last success and first failure details."""
    successes = [t for t in traces if t.status == "success" and not t.error_message]
    failures = [
        t for t in traces
        if t.status in ("failed", "interrupted", "dead_lettered", "error")
        or bool(t.error_message)
        or getattr(t, "db_result", None) == "error"
    ]

    last_success = None
    if successes:
        s = successes[-1]
        last_success = {
            "step_number": s.step_number,
            "node_name": s.node_name,
            "status": s.status,
            "executed_at": s.executed_at,
        }

    first_failure = None
    if failures:
        f = failures[0]
        first_failure = {
            "step_number": f.step_number,
            "node_name": f.node_name,
            "status": f.status,
            "error_message": f.error_message or "Failure recorded",
            "executed_at": f.executed_at,
        }

    return {
        "last_success": last_success,
        "first_failure": first_failure,
        "total_steps": len(traces),
    }


def diagnose_workflow(db, case_id: uuid.UUID = None, run_id: str = None, patient_id: uuid.UUID = None) -> dict:
    """Programmatic diagnostic function returning structured analysis."""
    traces = []
    if run_id:
        traces = _traces_by_run_id(db, run_id)
    elif case_id:
        traces = _traces_by_case(db, case_id)
    elif patient_id:
        cases = _cases_by_patient(db, patient_id)
        for c in cases:
            traces.extend(_traces_by_case(db, c.id))

    analysis = analyze_traces(traces)
    dead_letters = []
    if case_id:
        stmt = (
            select(Notification)
            .where(
                Notification.case_id == case_id,
                Notification.status == "dead_letter",
            )
            .order_by(Notification.created_at.asc())
        )
        dead_letters = list(db.execute(stmt).scalars().all())

    return {
        "traces": traces,
        "last_success": analysis["last_success"],
        "first_failure": analysis["first_failure"],
        "dead_letters": dead_letters,
        "has_failure": analysis["first_failure"] is not None,
    }


def _print_diagnostic_summary(traces: list[WorkflowExecutionTrace]) -> None:
    print("\n── Diagnostic Summary ──────────────────────────────────────────────")
    analysis = analyze_traces(traces)
    last = analysis["last_success"]
    if last:
        print(f"  ✓ Last success:   step {last['step_number']} — {last['node_name']}")
    else:
        print("  ✓ Last success:   NONE")

    first_fail = analysis["first_failure"]
    if first_fail:
        err = first_fail["error_message"] or "MISSING"
        print(f"  ✗ First failure:  step {first_fail['step_number']} — {first_fail['node_name']} — {err}")
    else:
        print("  ✗ First failure:  NONE")

    # Gap detection: check for missing step numbers
    if traces:
        expected = set(range(1, traces[-1].step_number + 1))
        actual   = {t.step_number for t in traces}
        gaps     = sorted(expected - actual)
        if gaps:
            print(f"  ⚠ Step gaps detected: {gaps}")

    print("────────────────────────────────────────────────────────────────────")


def _print_dead_letters(db, case_id: uuid.UUID) -> None:
    stmt = (
        select(Notification)
        .where(
            Notification.case_id == case_id,
            Notification.status == "dead_letter",
        )
        .order_by(Notification.created_at.asc())
    )
    dead = db.execute(stmt).scalars().all()

    print(f"\n── Dead-Lettered Notifications ({len(dead)}) ────────────────────────────")
    if not dead:
        print("  None.")
    else:
        for n in dead:
            ts = _fmt_ts(n.created_at)
            print(f"  [{ts}] id={n.id}  type={n.event_type}  retries={n.retry_count}/{n.max_retries}")
            if n.last_error:
                print(f"           error: {n.last_error[:120]}")
    print("────────────────────────────────────────────────────────────────────")


# ─── Query helpers ─────────────────────────────────────────────────────────────

def _traces_by_case(db, case_id: uuid.UUID) -> list[WorkflowExecutionTrace]:
    stmt = (
        select(WorkflowExecutionTrace)
        .where(WorkflowExecutionTrace.case_id == case_id)
        .order_by(WorkflowExecutionTrace.executed_at.asc())
    )
    return db.execute(stmt).scalars().all()


def _traces_by_run_id(db, run_id: str) -> list[WorkflowExecutionTrace]:
    stmt = (
        select(WorkflowExecutionTrace)
        .where(WorkflowExecutionTrace.run_id == run_id)
        .order_by(WorkflowExecutionTrace.executed_at.asc())
    )
    return db.execute(stmt).scalars().all()


def _cases_by_patient(db, patient_id: uuid.UUID) -> list[CareCase]:
    stmt = select(CareCase).where(CareCase.patient_id == patient_id)
    return db.execute(stmt).scalars().all()


# ─── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.trace_workflow",
        description="CareBridge Diagnostic CLI — Inspect workflow execution traces.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--patient",  metavar="PATIENT_ID",  help="UUID of the patient")
    group.add_argument("--workflow", metavar="RUN_ID",       help="Workflow run_id string")
    group.add_argument("--case",     metavar="CASE_ID",      help="UUID of the care case")
    args = parser.parse_args()

    db = get_sync_db()
    try:
        # ── --workflow ──────────────────────────────────────────────────────
        if args.workflow:
            run_id = args.workflow
            traces = _traces_by_run_id(db, run_id)
            if not traces:
                print(f"No traces found for run_id={run_id!r}.")
                return
            _print_traces(traces, label=f"run_id={run_id}")
            _print_diagnostic_summary(traces)

            # Attempt dead-letter lookup using case_id from first trace
            case_id = traces[0].case_id
            if case_id:
                _print_dead_letters(db, case_id)

        # ── --case ──────────────────────────────────────────────────────────
        elif args.case:
            try:
                case_id = uuid.UUID(args.case)
            except ValueError:
                print(f"ERROR: '{args.case}' is not a valid UUID.", file=sys.stderr)
                sys.exit(1)

            traces = _traces_by_case(db, case_id)
            if not traces:
                print(f"No traces found for case_id={case_id}.")
                return
            _print_traces(traces, label=f"case_id={case_id}")
            _print_diagnostic_summary(traces)
            _print_dead_letters(db, case_id)

        # ── --patient ───────────────────────────────────────────────────────
        elif args.patient:
            try:
                patient_id = uuid.UUID(args.patient)
            except ValueError:
                print(f"ERROR: '{args.patient}' is not a valid UUID.", file=sys.stderr)
                sys.exit(1)

            cases = _cases_by_patient(db, patient_id)
            if not cases:
                print(f"No care cases found for patient_id={patient_id}.")
                return

            found_any = False
            for case in cases:
                traces = _traces_by_case(db, case.id)
                if not traces:
                    continue
                found_any = True
                _print_traces(
                    traces,
                    label=f"patient={patient_id} / case={case.id} ({case.case_number})"
                )
                _print_diagnostic_summary(traces)
                _print_dead_letters(db, case.id)

            if not found_any:
                print(f"No traces found for any case belonging to patient_id={patient_id}.")

    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
