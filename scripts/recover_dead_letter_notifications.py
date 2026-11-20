#!/usr/bin/env python3
"""
CareBridge Manual Dead-Letter Outbox Recovery Tool (Phase 3)
Internal administrative command to inspect and reprocess dead-lettered outbox notifications.

Usage:
  python scripts/recover_dead_letter_notifications.py --list
  python scripts/recover_dead_letter_notifications.py --recover <notification_uuid>
  python scripts/recover_dead_letter_notifications.py --recover-all
"""

import os
import sys
import uuid
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend is in python path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.notification import Notification
from app.services.notification_service import NotificationService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("carebridge.recovery.dead_letter")


def list_dead_letters(db):
    items = db.query(Notification).filter(Notification.status == "dead_letter").all()
    print(f"\nFound {len(items)} dead-lettered notification(s):")
    for item in items:
        print(f"  • ID: {item.id} | Event: {item.event_type} | User: {item.user_id} ({item.role})")
        print(f"    Retries: {item.retry_count}/{item.max_retries} | Error: {item.last_error}")
        print(f"    Title: {item.title}\n")
    return len(items)


def recover_notification(db, notif_id: uuid.UUID):
    res = NotificationService.reprocess_dead_letter_notification(db, notif_id)
    if res.get("success"):
        logger.info(f"Successfully re-queued notification {notif_id} to pending.")
    else:
        logger.error(f"Failed to recover {notif_id}: {res.get('error')}")
    return res


def recover_all(db):
    items = db.query(Notification).filter(Notification.status == "dead_letter").all()
    recovered = 0
    for item in items:
        res = NotificationService.reprocess_dead_letter_notification(db, item.id)
        if res.get("success"):
            recovered += 1
    logger.info(f"Batch recovered {recovered}/{len(items)} dead-lettered notifications.")
    return recovered


def main():
    parser = argparse.ArgumentParser(description="CareBridge Dead-Letter Outbox Recovery")
    parser.add_argument("--list", action="store_true", help="List all dead-lettered notifications")
    parser.add_argument("--recover", type=str, default=None, help="UUID of specific notification to recover")
    parser.add_argument("--recover-all", action="store_true", help="Recover all dead-lettered notifications")
    parser.add_argument("--db-url", type=str, default=None, help="Database connection URL")
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
        if args.list or (not args.recover and not args.recover_all):
            list_dead_letters(db)
        if args.recover:
            recover_notification(db, uuid.UUID(args.recover))
        elif args.recover_all:
            recover_all(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
