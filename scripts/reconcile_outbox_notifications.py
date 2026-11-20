#!/usr/bin/env python3
"""
CareBridge Outbox Notifications Reconciliation & Backfill Script (Phase 3)
Audits notifications for transactional outbox integrity, valid statuses, and recipient alignment.

Rules:
- Dry-run by default: does not mutate records unless --apply is passed explicitly.
- Ensures all historical notifications have an authoritative status ('delivered').
- Audits recipient user IDs against application roles to identify unauthorized or orphaned alerts.
- Provides dead-letter recovery inspection.
"""

import os
import sys
import uuid
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

# Ensure backend is in python path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker, Session

from app.models.notification import Notification
from app.models.user import User
from app.models.care_case import CareCase

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("carebridge.reconciliation.outbox")


def reconcile_outbox_notifications(db: Session, apply_changes: bool = False) -> Dict[str, Any]:
    notifications = db.query(Notification).all()
    total = len(notifications)
    missing_status_count = 0
    invalid_recipient_count = 0
    delivered_count = 0
    pending_count = 0
    failed_count = 0
    dead_letter_count = 0

    logger.info(f"Auditing {total} notification record(s)...")

    for n in notifications:
        # Check status
        st = getattr(n, "status", None)
        if not st:
            missing_status_count += 1
            if apply_changes:
                n.status = "delivered"
                if not getattr(n, "delivered_at", None):
                    n.delivered_at = n.created_at or datetime.now(timezone.utc)
        elif st == "delivered":
            delivered_count += 1
        elif st == "pending":
            pending_count += 1
        elif st == "failed":
            failed_count += 1
        elif st == "dead_letter":
            dead_letter_count += 1

        # Check recipient
        user = db.query(User).filter(User.id == n.user_id).first()
        if not user or user.role != n.role:
            invalid_recipient_count += 1
            logger.warning(
                f"[Discrepancy] Notification {n.id}: Recipient user {n.user_id} has role "
                f"'{getattr(user, 'role', 'MISSING')}', notification role is '{n.role}'"
            )

    report = {
        "total_notifications": total,
        "missing_status_count": missing_status_count,
        "invalid_recipient_count": invalid_recipient_count,
        "delivered_count": delivered_count + (missing_status_count if apply_changes else 0),
        "pending_count": pending_count,
        "failed_count": failed_count,
        "dead_letter_count": dead_letter_count,
        "apply_changes": apply_changes
    }

    if apply_changes and missing_status_count > 0:
        db.commit()
        logger.info(f"Successfully backfilled {missing_status_count} notification(s) to 'delivered' status.")
    elif not apply_changes and missing_status_count > 0:
        logger.info(f"[DRY-RUN] Found {missing_status_count} notification(s) needing backfill. Run with --apply to commit.")
    else:
        logger.info("All notification outbox statuses are consistent.")

    return report


def main():
    parser = argparse.ArgumentParser(description="CareBridge Outbox Reconciliation & Backfill")
    parser.add_argument("--db-url", type=str, default=None, help="Database connection URL")
    parser.add_argument("--apply", action="store_true", help="Apply backfill updates to database")
    args = parser.parse_args()

    db_url = args.db_url or os.getenv(
        "DATABASE_URL",
        f"sqlite:///{backend_path / 'carebridge.db'}"
    )

    if db_url.startswith("sqlite+aiosqlite:"):
        db_url = db_url.replace("sqlite+aiosqlite:", "sqlite:")

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        report = reconcile_outbox_notifications(db, apply_changes=args.apply)
        print("\n--- RECONCILIATION SUMMARY ---")
        for k, v in report.items():
            print(f"  {k}: {v}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
