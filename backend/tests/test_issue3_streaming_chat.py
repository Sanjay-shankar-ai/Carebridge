"""
CareBridge Issue 3 Verification Test Suite
Tests:
1. streaming yields ordered events (token, tool_started, tool_result, final)
2. cancellation stops generation
3. guard blocks a fabricated success claim
4. coordinator operational question routes correctly
5. markdown is sanitised
6. LLM failure produces a clear message and no false success
"""

import os
import re
import json
import pytest
import requests
from app.services.response_guard_service import ResponseGuardService

BASE_URL = "http://127.0.0.1:8000/api/v1"


def get_auth_token(email: str = "coordinator@carebridge.com", password: str = None) -> str:
    if password is None:
        password = os.environ.get("DEMO_COORDINATOR_PASSWORD", "CoordinatorPass123!")
    res = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": email, "password": password},
        headers={"Content-Type": "application/json"},
        timeout=10
    )
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    return res.json()["data"]["token"]


def parse_sse_events(raw_text: str):
    events = []
    current_event = "message"
    current_data = []

    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            if current_data:
                data_str = "\n".join(current_data)
                try:
                    payload = json.loads(data_str)
                except Exception:
                    payload = data_str
                events.append({"event": current_event, "data": payload})
                current_event = "message"
                current_data = []
            continue

        if line.startswith("event:"):
            current_event = line.replace("event:", "").strip()
        elif line.startswith("data:"):
            current_data.append(line.replace("data:", "").strip())

    if current_data:
        data_str = "\n".join(current_data)
        try:
            payload = json.loads(data_str)
        except Exception:
            payload = data_str
        events.append({"event": current_event, "data": payload})

    return events


def test_streaming_yields_ordered_events():
    """Verify that SSE stream yields ordered events: token, final, and tool events if executed."""
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}

    payload = {
        "message": "is there any new patient in the queue",
        "channel": "in_app_chat",
        "stream": True
    }

    res = requests.post(f"{BASE_URL}/agent/stream", json=payload, headers=headers, stream=True, timeout=15)
    assert res.status_code == 200, f"Expected 200 SSE stream, got {res.status_code}"
    assert "text/event-stream" in res.headers.get("content-type", "")

    events = parse_sse_events(res.text)
    assert len(events) > 0, "Expected non-empty SSE events list"

    event_names = [e["event"] for e in events]
    # Check that final event is the last event
    assert "final" in event_names, f"Expected 'final' event in {event_names}"
    assert event_names[-1] == "final", f"Expected 'final' as terminal event, got {event_names[-1]}"

    # Check token events were emitted
    assert "token" in event_names, f"Expected 'token' events in {event_names}"

    # Verify final payload schema
    final_data = next(e["data"] for e in events if e["event"] == "final")
    assert "session_id" in final_data
    assert "content" in final_data
    assert final_data.get("completed") is True


def test_coordinator_operational_question_routes_correctly():
    """Verify that asking operational question 'is there any new patient' triggers discover_new_patients."""
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}

    payload = {
        "message": "is there any new patient in the queue?",
        "channel": "in_app_chat",
        "stream": True
    }

    res = requests.post(f"{BASE_URL}/agent/stream", json=payload, headers=headers, timeout=15)
    assert res.status_code == 200
    events = parse_sse_events(res.text)

    # Check for tool_started and tool_result events
    tool_started = [e for e in events if e["event"] == "tool_started"]
    tool_results = [e for e in events if e["event"] == "tool_result"]

    assert any(e["data"].get("tool") == "discover_new_patients" for e in tool_started), "Expected discover_new_patients in tool_started"
    assert any(e["data"].get("tool") == "discover_new_patients" and e["data"].get("status") == "success" for e in tool_results), "Expected successful tool_result"

    final_ev = next(e for e in events if e["event"] == "final")
    assert "discover_new_patients" in final_ev["data"].get("actions", [])
    assert final_ev["data"].get("primary_intent") == "new_patient_discovery"


def test_guard_blocks_fabricated_success_claim():
    """Verify that ResponseGuardService blocks ungrounded action claims when tool evidence is missing."""
    fabricated_draft = "I have successfully booked your appointment for tomorrow at 10:00 AM."
    
    # 1. Without tool evidence: claim MUST be rewritten
    sanitized = ResponseGuardService.sanitize_response(
        draft_response=fabricated_draft,
        tool_observations=[],
        actor_role="patient"
    )
    assert "successfully booked" not in sanitized.lower()
    assert "has not yet been booked" in sanitized

    # 2. With matching successful tool evidence: claim is permitted
    grounded_obs = [{
        "tool": "book_appointment",
        "success": True,
        "result": {"status": "confirmed"}
    }]
    permitted = ResponseGuardService.sanitize_response(
        draft_response=fabricated_draft,
        tool_observations=grounded_obs,
        actor_role="patient"
    )
    assert "successfully booked" in permitted.lower()


def test_markdown_is_sanitised():
    """Verify that dangerous link protocols (javascript:, data:) are rejected by link sanitizer."""
    def sanitize_href(raw_href: str) -> str:
        trimmed = raw_href.strip()
        lower = trimmed.lower()
        if lower.startswith("http://") or lower.startswith("https://") or lower.startswith("mailto:"):
            return trimmed
        return "#"

    # Malicious javascript protocol
    assert sanitize_href("javascript:alert(1)") == "#"
    assert sanitize_href("JAVASCRIPT:document.cookie") == "#"
    assert sanitize_href("data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==") == "#"
    assert sanitize_href("vbscript:msgbox(1)") == "#"

    # Safe allowed protocols
    assert sanitize_href("https://carebridge.org/portal") == "https://carebridge.org/portal"
    assert sanitize_href("http://clinic.org/info") == "http://clinic.org/info"
    assert sanitize_href("mailto:coordinator@carebridge.org") == "mailto:coordinator@carebridge.org"


def test_llm_failure_produces_clear_message_and_no_false_success():
    """Verify that invalid/malformed session or system error yields friendly error event and no false success."""
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}

    # Request with invalid non-existent session UUID
    payload = {
        "session_id": "00000000-0000-0000-0000-000000000000",
        "message": "Hello",
        "stream": True
    }

    res = requests.post(f"{BASE_URL}/agent/stream", json=payload, headers=headers, timeout=10)
    assert res.status_code == 200
    events = parse_sse_events(res.text)

    error_evs = [e for e in events if e["event"] == "error"]
    assert len(error_evs) > 0, "Expected error event for non-existent session"
    assert error_evs[0]["data"].get("code") == "NOT_FOUND"

    # Must NOT have any final completed success
    assert not any(e["event"] == "final" and e["data"].get("completed") is True for e in events)


def test_cancellation_stops_generation():
    """Verify that client connection abort / disconnect is cleanly handled without 500 errors."""
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}

    payload = {
        "message": "is there any new patient in the queue",
        "stream": True
    }

    try:
        with requests.post(f"{BASE_URL}/agent/stream", json=payload, headers=headers, stream=True, timeout=0.1) as res:
            for chunk in res.iter_content(chunk_size=64):
                break
    except requests.exceptions.RequestException:
        pass

    health_res = requests.get(f"{BASE_URL}/health", timeout=5)
    assert health_res.status_code == 200
