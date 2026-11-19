"""
CareBridge Diagnostic CLI — Outbox Health Check
Phase 6, Item 6

Usage:
    python -m scripts.health_check

Prints a one-line summary:
    Outbox: N pending, oldest Xs, N dead-lettered — STATUS
"""

import sys

from app.core.outbox_health import get_outbox_stats
from app.database.session import get_sync_db


def main() -> None:
    db = get_sync_db()
    try:
        stats = get_outbox_stats(db)
    except Exception as exc:
        print(f"ERROR: failed to query outbox — {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()

    pending     = stats["pending_count"]
    dead        = stats["dead_letter_count"]
    oldest_secs = stats["oldest_pending_seconds"]
    status      = stats["status"].upper()

    if oldest_secs is None:
        oldest_str = "none"
    elif oldest_secs < 60:
        oldest_str = f"{oldest_secs:.1f}s"
    elif oldest_secs < 3600:
        oldest_str = f"{oldest_secs / 60:.1f}m"
    else:
        oldest_str = f"{oldest_secs / 3600:.2f}h"

    print(
        f"Outbox: {pending} pending, oldest {oldest_str}, {dead} dead-lettered — {status}"
    )

    # Exit non-zero when unhealthy so CI/monitoring scripts can detect problems
    if status == "CRITICAL":
        sys.exit(2)
    elif status == "DEGRADED":
        sys.exit(1)


if __name__ == "__main__":
    main()
