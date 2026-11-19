"""
CareBridge Concurrent Transition Guard (Phase 6)
Prevents two concurrent requests from advancing the same care case lifecycle
simultaneously, which would produce split-brain stage transitions.

PostgreSQL: uses pg_try_advisory_xact_lock (hash of the case_id string).
SQLite / testing: uses an in-process threading.Lock-protected dict.
"""

import threading
import logging
from typing import Dict

logger = logging.getLogger("carebridge.core.concurrent_guard")

# ---------------------------------------------------------------------------
# In-process fallback lock map (SQLite / unit tests)
# ---------------------------------------------------------------------------
_locks: Dict[str, str] = {}       # case_id → correlation_id currently holding
_lock_mutex = threading.Lock()


class ConcurrentTransitionError(Exception):
    """Raised when a concurrent lifecycle transition is detected for the same case."""

    def __init__(self, case_id: object, detail: str):
        self.case_id = case_id
        self.detail = detail
        super().__init__(f"[ConcurrentTransition] case_id={case_id}: {detail}")


def acquire_case_lock(db, case_id: object, correlation_id: str = "", timeout_ms: int = 5000) -> bool:
    """
    Attempt to acquire an exclusive lock for the given case_id within the
    current database transaction.

    PostgreSQL:
        Executes ``SELECT pg_try_advisory_xact_lock(hashtext(:key))`` which
        automatically releases at transaction end.  Returns True on success,
        False if another transaction already holds the lock.

    SQLite / any other dialect:
        Uses a module-level threading.Lock-protected dict.  Grants the lock if
        no other *different* correlation_id currently holds it.

    Args:
        db:             SQLAlchemy Session (sync).
        case_id:        The CareCase primary-key (UUID or str).
        correlation_id: X-Correlation-ID of the current request.
        timeout_ms:     Advisory-lock timeout hint (not enforced on SQLite).

    Returns:
        True  → lock acquired, safe to proceed.
        False → another holder detected, caller should raise ConcurrentTransitionError.
    """
    case_key = str(case_id)

    # ------------------------------------------------------------------
    # PostgreSQL path: advisory transaction lock
    # ------------------------------------------------------------------
    try:
        bind = db.get_bind()
        dialect = bind.dialect.name if bind else "sqlite"
    except Exception:
        dialect = "sqlite"

    if dialect == "postgresql":
        try:
            from sqlalchemy import text
            result = db.execute(
                text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
                {"key": case_key}
            )
            acquired: bool = result.scalar()
            if not acquired:
                logger.warning(
                    f"[ConcurrentGuard] pg_try_advisory_xact_lock FAILED for "
                    f"case={case_key} corr={correlation_id}"
                )
            return bool(acquired)
        except Exception as exc:
            # If the advisory lock call itself fails (e.g., RDS restriction),
            # fall through to the in-memory guard so we don't silently lose protection.
            logger.warning(f"[ConcurrentGuard] pg advisory lock error ({exc}); falling back to in-process guard")

    # ------------------------------------------------------------------
    # SQLite / fallback path: in-process threading lock
    # ------------------------------------------------------------------
    with _lock_mutex:
        current_holder = _locks.get(case_key)
        if current_holder is None:
            # No holder → acquire
            _locks[case_key] = correlation_id or "anonymous"
            return True
        if current_holder == (correlation_id or "anonymous"):
            # Same correlation ID (re-entrant call) → allow
            return True
        # Different holder → reject
        logger.warning(
            f"[ConcurrentGuard] In-process lock HELD by corr={current_holder} "
            f"for case={case_key}; rejecting corr={correlation_id}"
        )
        return False


def release_case_lock(case_id: object, correlation_id: str = "") -> None:
    """
    Release the in-process lock for a case (SQLite / testing only).
    PostgreSQL advisory locks are released automatically at transaction end;
    calling this for PG is harmless.
    """
    case_key = str(case_id)
    with _lock_mutex:
        current_holder = _locks.get(case_key)
        if current_holder == (correlation_id or "anonymous"):
            del _locks[case_key]
