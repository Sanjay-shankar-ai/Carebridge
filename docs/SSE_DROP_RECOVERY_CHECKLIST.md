# CareBridge SSE Connection Drop & Recovery Manual Checklist

This document provides the standard operating procedures and test checklist for verifying real-time Server-Sent Events (SSE) notification streaming, failure recovery, and dashboard domain synchronization across all CareBridge portals (`PATIENT`, `DOCTOR`, `CARE_COORDINATOR`).

---

## 1. Architectural Design & Synchronization Invariants

| Component | Responsibility | Authoritative Source |
| :--- | :--- | :--- |
| **Backend Stream** | `/api/v1/notifications/stream?token=<jwt>` | PostgreSQL `notifications` table |
| **Client Listener** | `frontend/components/NotificationCenter.tsx` | EventSource with exponential backoff reconnect |
| **Event Broadcast** | `window.dispatchEvent("carebridge:data_updated")` | Global DOM CustomEvent |
| **Portals** | `/patient`, `/doctor`, `/coordinator` | Refetches `/api/v1/dashboards/*` upon SSE event |
| **Page Refresh** | Hard reload (`F5` / `Ctrl+R`) | 100% reconstructed from PostgreSQL database state |

---

## 2. Test Verification Matrix

| Test ID | Failure Simulation | Expected Behavior | Verification Steps | Pass / Fail |
| :--- | :--- | :--- | :--- | :--- |
| **SSE-01** | **Normal Event Delivery** | SSE dispatches `notification` event; badge increments; dashboard refetches. | 1. Advance case stage or book appointment.<br>2. Observe instant dashboard update without manual refresh. | [ ] PASS |
| **SSE-02** | **Network Cable Disconnect / Wi-Fi Drop (15s)** | EventSource triggers `onerror`; stale socket is closed; reconnect scheduled for 5s. | 1. Disable network adapter in dev tools.<br>2. Observe `SSE connection error` warning.<br>3. Re-enable adapter.<br>4. Verify auto-reconnect completes. | [ ] PASS |
| **SSE-03** | **Missed Events During Outage** | Events dispatched while offline are retrieved upon reconnection. | 1. Disconnect network.<br>2. Complete action on backend (e.g., upload report).<br>3. Reconnect network.<br>4. Verify notification center loads missed notifications via fallback sync. | [ ] PASS |
| **SSE-04** | **Backend Worker Restart** | Server process restarts; client handles EOF, waits 5s backoff, and reconnects cleanly. | 1. Restart FastAPI backend process.<br>2. Verify frontend does not crash or spam reconnect loops.<br>3. Verify connection re-establishes within 5 seconds. | [ ] PASS |
| **SSE-05** | **Duplicate Event Suppression** | Retried notifications or reconnections never produce duplicate notification items. | 1. Inspect notification state in React dev tools.<br>2. Verify `notifications.some(n => n.id === data.id)` deduplication filter. | [ ] PASS |
| **SSE-06** | **Mid-Workflow Browser Refresh** | Page refresh mid-journey preserves exact clinical stage, evidence, and appointment state. | 1. Navigate to patient/doctor dashboard at Stage 9.<br>2. Hard refresh page.<br>3. Verify current stage, appointments, and doctor remain identical. | [ ] PASS |
| **SSE-07** | **Arabic RTL Switching** | Language dropdown changes text direction to RTL and language to Arabic without losing state. | 1. Select "العربية (Arabic - RTL)" in header.<br>2. Verify `document.documentElement.dir === "rtl"`.<br>3. Verify Arabic indicators displayed across cards. | [ ] PASS |

---

## 3. Manual Operator Verification Protocol

1. **Start Services**:
   - Backend: `uvicorn app.main:create_application --factory --port 8000`
   - Frontend: `npm run dev`
2. **Open DevTools Console** in Chrome/Firefox:
   - Filter by `SSE` or `carebridge:data_updated`.
3. **Simulate Connection Drop**:
   - In browser DevTools > Network tab, select **Offline**.
   - Wait 10 seconds.
   - Switch back to **Online**.
   - Verify log: `SSE connection re-established`.
4. **Trigger Consistency Checker**:
   - As Care Coordinator, click **Audit Projections** in the Coordinator Command Center.
   - Confirm all stages report 100% verified clinical evidence.
