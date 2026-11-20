"""
CareBridge Dashboard Consistency Checker CLI
Usage:
    python scripts/check_dashboard_consistency.py --dry-run
    python scripts/check_dashboard_consistency.py --apply
"""

import sys
import os
from pathlib import Path

# Ensure backend directory is in sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import argparse
from app.database.session import get_sync_db
from app.services.consistency_checker import ConsistencyCheckerService


def main():
    parser = argparse.ArgumentParser(description="CareBridge Dashboard Consistency Checker")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply repairs to database (revert unverified stages and create reconciliation tasks).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Simulate check without applying changes (default mode).",
    )
    args = parser.parse_args()

    # If --apply is explicitly specified, turn off dry_run
    dry_run = not args.apply

    mode_str = "DRY-RUN (Read-Only Audit)" if dry_run else "APPLY (Active Repair & Reconciliation)"
    print(f"=== CareBridge Dashboard Consistency Audit: {mode_str} ===")

    try:
        with get_sync_db() as db:
            result = ConsistencyCheckerService.audit_cases(db, dry_run=dry_run)
    except Exception as exc:
        if "5432" in str(exc) or "psycopg" in str(exc) or "connection to server at" in str(exc):
            print("[NOTICE] PostgreSQL unreachable on port 5432. Auditing local database (carebridge.db).")
            os.environ["TESTING"] = "1"
            import importlib
            import app.database.session
            importlib.reload(app.database.session)
            with app.database.session.get_sync_db() as db:
                result = ConsistencyCheckerService.audit_cases(db, dry_run=dry_run)
        else:
            raise

    print(f"Total Cases Scanned: {result['total_cases_scanned']}")
    print(f"Corrupted Projections Found: {result['corrupted_count']}")
    if not dry_run:
        print(f"Repairs Applied: {result['repaired_count']}")

    if result["anomalies"]:
        print("\nDetected Anomalies:")
        for idx, a in enumerate(result["anomalies"], start=1):
            print(f"  [{idx}] Case: {a['case_number']} (ID: {a['case_id']})")
            print(f"      Stage: {a['stage_number']} - {a['title']}")
            print(f"      Reason: {a['reason']}")
    else:
        print("\nAll case projections and lifecycle stages are fully consistent with verified clinical evidence!")

    sys.exit(0)


if __name__ == "__main__":
    main()
