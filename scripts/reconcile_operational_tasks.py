"""
CareBridge Operational Task Reconciliation Script
Backfills missing patient_id references and standardizes task ownership attributes.

Usage:
    python scripts/reconcile_operational_tasks.py [--dry-run | --apply] [--db-url SQLITE_OR_PG_URL]
"""

import sys
import os
import argparse
import logging

# Ensure backend is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.models.care_case import CareCase, Task

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reconcile_tasks")


def reconcile_tasks(db_url: str, apply_changes: bool = False):
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        logger.info(f"Scanning tasks in {db_url} (mode: {'APPLY' if apply_changes else 'DRY RUN'})")

        # 1. Identify tasks missing patient_id
        tasks_missing_patient = (
            session.query(Task)
            .filter(Task.patient_id.is_(None))
            .all()
        )

        logger.info(f"Found {len(tasks_missing_patient)} task(s) with missing patient_id.")

        updated_count = 0
        unmatched_count = 0

        for task in tasks_missing_patient:
            case = session.query(CareCase).filter(CareCase.id == task.case_id).first()
            if case and case.patient_id:
                logger.info(
                    f"[Plan] Task '{task.id}' ('{task.title}') -> Set patient_id = {case.patient_id} (from Case {case.case_number})"
                )
                if apply_changes:
                    task.patient_id = case.patient_id
                updated_count += 1
            else:
                logger.warning(f"[Warning] Task '{task.id}' cannot be matched to a CareCase or patient.")
                unmatched_count += 1

        if apply_changes:
            session.commit()
            logger.info(f"Reconciliation applied successfully. Updated {updated_count} task(s). Unmatched: {unmatched_count}.")
        else:
            logger.info(f"Dry-run complete. {updated_count} task(s) would be updated. Run with --apply to commit.")

    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconcile CareBridge operational task ownership attributes.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Simulate changes without persisting.")
    parser.add_argument("--apply", dest="dry_run", action="store_false", help="Apply changes to the database.")
    parser.add_argument("--db-url", default=None, help="Database connection URL (defaults to carebridge.db).")
    args = parser.parse_args()

    url = args.db_url or os.getenv("DATABASE_URL") or "sqlite:///backend/carebridge.db"
    reconcile_tasks(db_url=url, apply_changes=not args.dry_run)
