"""
CareBridge Redaction Utilities (Phase 6)
Scrubs sensitive keys and JWT tokens from dicts and strings before they reach
trace storage, logs, or error responses.
"""

import re
import copy
from typing import Any

REDACT_KEYS = {
    "password", "token", "jwt", "api_key", "secret", "authorization",
    "access_token", "refresh_token", "credential", "private_key", "passwd"
}

CLINICAL_CONTENT_KEYS = {
    "clinical_note", "free_text", "clinical_content", "patient_message",
    "transcript", "symptoms", "diagnosis_text", "clinical_summary_text",
    "physician_notes", "narrative", "unstructured_note"
}

# Matches a 3-part base64url JWT (header.payload.signature)
JWT_PATTERN = re.compile(
    r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"
)


def redact_str(value: str) -> str:
    """Replace JWT-shaped tokens embedded in a string with [REDACTED_TOKEN]."""
    return JWT_PATTERN.sub("[REDACTED_TOKEN]", value)


def redact_dict(data: Any, max_str_len: int = 200, redact_clinical: bool = True) -> Any:
    """
    Recursively redact sensitive keys, JWT tokens, and free-text clinical content.
    - Keys in REDACT_KEYS → value replaced with '[REDACTED]'
    - Keys in CLINICAL_CONTENT_KEYS → value replaced with '[CLINICAL_CONTENT_REDACTED]'
    - String values longer than max_str_len are truncated
    - JWT patterns inside string values are replaced with '[REDACTED_TOKEN]'
    Never mutates the original; returns a scrubbed clone.
    """
    if data is None:
        return data

    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            k_lower = str(k).lower() if isinstance(k, str) else ""
            if k_lower in REDACT_KEYS:
                result[k] = "[REDACTED]"
            elif redact_clinical and k_lower in CLINICAL_CONTENT_KEYS:
                result[k] = "[CLINICAL_CONTENT_REDACTED]"
            else:
                result[k] = redact_dict(v, max_str_len=max_str_len, redact_clinical=redact_clinical)
        return result

    if isinstance(data, list):
        return [redact_dict(item, max_str_len=max_str_len, redact_clinical=redact_clinical) for item in data]

    if isinstance(data, str):
        # Redact JWT tokens first
        cleaned = redact_str(data)
        # Truncate to avoid unbounded trace storage
        if len(cleaned) > max_str_len:
            cleaned = cleaned[:max_str_len] + "...[truncated]"
        return cleaned

    # int, float, bool, None — return as-is
    return copy.copy(data)
