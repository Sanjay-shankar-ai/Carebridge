"""
CareBridge Idempotency & Duplicate Message Prevention Engine (Phase 8)
Protects against repeated side effects, webhook retries, and outbound communication spam.
Maintains in-memory TTL records with optional database persistence.
"""

import hashlib
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger("carebridge.workflows.idempotency")


class IdempotencyManager:
    """Guarantees that repeated executions with the same key produce identical results without duplicate side effects."""

    _cache: Dict[str, Dict[str, Any]] = {}
    _lock = threading.Lock()

    @classmethod
    def get_result(cls, key: str) -> Optional[Dict[str, Any]]:
        """Retrieves cached outcome if key exists and has not expired."""
        with cls._lock:
            entry = cls._cache.get(key)
            if not entry:
                return None
            if datetime.now(timezone.utc) > entry["expires_at"]:
                del cls._cache[key]
                return None
            return entry["result"]

    @classmethod
    def record_result(cls, key: str, result: Any, ttl_seconds: int = 86400):
        """Records an idempotent result with a time-to-live."""
        with cls._lock:
            cls._cache[key] = {
                "result": result,
                "recorded_at": datetime.now(timezone.utc),
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            }

    @classmethod
    def execute_idempotent(
        cls,
        idempotency_key: str,
        operation: Callable[..., Any],
        *args,
        ttl_seconds: int = 86400,
        **kwargs
    ) -> Any:
        """
        Executes operation only once per idempotency_key.
        Returns cached result on subsequent invocations.
        """
        existing = cls.get_result(idempotency_key)
        if existing is not None:
            logger.info(f"[Idempotency] Returning cached result for key: {idempotency_key}")
            return existing

        result = operation(*args, **kwargs)
        cls.record_result(idempotency_key, result, ttl_seconds=ttl_seconds)
        return result

    @classmethod
    def clear(cls):
        """Clears the in-memory cache (primarily for unit tests)."""
        with cls._lock:
            cls._cache.clear()


class DuplicateMessageFilter:
    """Filters duplicate inbound webhooks and prevents duplicate outbound patient messages."""

    _inbound_seen: Dict[str, datetime] = {}
    _outbound_sent: Dict[str, datetime] = {}
    _lock = threading.Lock()

    @classmethod
    def generate_inbound_fingerprint(cls, case_id: str, sender: str, content: str) -> str:
        """Computes deterministic hash for inbound messages."""
        norm_content = (content or "").strip().lower()
        raw = f"{case_id}:{sender}:{norm_content}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def is_duplicate_inbound(
        cls,
        case_id: str,
        sender: str,
        content: str,
        window_seconds: int = 120
    ) -> bool:
        """
        Detects if an identical inbound message arrived from the same sender within window_seconds.
        Useful for handling webhook network retries from SMS providers.
        """
        fingerprint = cls.generate_inbound_fingerprint(case_id, sender, content)
        now = datetime.now(timezone.utc)

        with cls._lock:
            last_seen = cls._inbound_seen.get(fingerprint)
            if last_seen and (now - last_seen).total_seconds() < window_seconds:
                logger.warning(
                    f"[De-duplication] Dropping duplicate inbound message for case {case_id} (Fingerprint: {fingerprint[:8]})"
                )
                return True

            cls._inbound_seen[fingerprint] = now
            return False

    @classmethod
    def is_duplicate_outbound(
        cls,
        case_id: str,
        category: str,
        cooldown_hours: int = 12
    ) -> bool:
        """
        Prevents outbound message spam by ensuring messages in the same category
        are not repeatedly dispatched to the patient within cooldown_hours.
        """
        key = f"{case_id}:{category}"
        now = datetime.now(timezone.utc)

        with cls._lock:
            last_sent = cls._outbound_sent.get(key)
            if last_sent and (now - last_sent).total_seconds() < (cooldown_hours * 3600):
                logger.warning(
                    f"[De-duplication] Suppressing duplicate outbound outreach '{category}' for case {case_id}. Cooldown active."
                )
                return True

            cls._outbound_sent[key] = now
            return False

    @classmethod
    def clear(cls):
        """Clears seen records (primarily for testing)."""
        with cls._lock:
            cls._inbound_seen.clear()
            cls._outbound_sent.clear()
