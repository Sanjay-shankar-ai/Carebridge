# CareBridge Demo Recording Checklist
**Team:** Ai_Mavericks | **Challenge:** Future Health Digital Innovation Challenge
**Target Runtime:** 2:50 | **Maximum:** 2:55 | **Voice-over:** 295 words

---

## 🖥️ System Requirements Before Recording
- [ ] Backend FastAPI running on `http://localhost:8000` (task-3696)
- [ ] Frontend Next.js running on `http://localhost:3000` (task-3713)
- [ ] PostgreSQL running on `localhost:5432` (carebridge DB)
- [ ] OBS Studio open, scene configured at 1280×800, 30fps
- [ ] CapCut or video editor ready for assembly

## 🔑 Demo Credentials
| Role | Email | Password | Dashboard |
|---|---|---|---|
| Patient | patient@carebridge.com | PatientPass123! | /patient |
| Coordinator | coordinator@carebridge.com | CoordinatorPass123! | /coordinator |
| Doctor | doctor@carebridge.com | DoctorPass123! | /doctor |

## 📋 Pre-Recording Checks
- [ ] Run `python c:\CareBridge\test_demo_prep.py` → all 4 sections pass
- [ ] Login as patient → confirm CASE-2026-0147 loads with 14 stages
- [ ] Stage 1 (SCREENING) = completed ✅
- [ ] Stage 2 (RESULT_GENERATED) = completed ✅
- [ ] Stages 3–14 = pending (ready to demonstrate)
- [ ] Login as coordinator → Priya Nair, RN loads correctly
- [ ] Login as doctor → Dr. Aris Thorne, MD loads correctly
- [ ] CASE-2026-0149 exists and shows "closed" status (pre-seeded demo)

---

## 🎬 Scene-by-Scene Guide

### Scene 1 — CareBridge Logo & 14-Stage Timeline
**Timestamp:** 0:00–0:12 | **Duration:** 12s
**Screen:** Patient dashboard overview → 14-stage timeline

**Steps:**
1. Open `http://localhost:3000/login`
2. Login as PATIENT (patient@carebridge.com)
3. Navigate to `/patient`
4. Slowly pan across the full 14-stage timeline (all stages visible)

**Caption:** "Stages complete only from persisted evidence" | "14-stage care journey"
**OBS Scene:** "Scene1_Timeline"
**Screenshot file:** `demo_assets/screenshots/s1_03_timeline_full.png`

---

### Scene 2 — Patient Requests Screening → Coordinator Task → Notification
**Timestamp:** 0:12–0:40 | **Duration:** 28s
**Screen:** Patient chat → AI response → Coordinator receives notification

**Steps:**
1. Login as PATIENT → go to `/chat`
2. Type: *"I need to schedule a mammogram screening. Can you help me?"*
3. Show AI capturing the need and creating a coordinator task
4. Switch to COORDINATOR → navigate to `/notifications`
5. Show the coordinator notification arrived

**Caption:** "Patient request → Coordinator task → Notification"
**Screenshot files:** `s2_03_patient_ai_response.png`, `s2_06_coordinator_notifications.png`

---

### Scene 3 — Screening Order → Stage 1 Pending → Recorded → Stage 1 Green
**Timestamp:** 0:40–1:05 | **Duration:** 25s
**Screen:** Coordinator creates order → Stage 1 still pending → Records performed → Stage 1 turns green

**Steps:**
1. Login as COORDINATOR → open case CASE-2026-0147
2. Show Stage 1 is still PENDING (order ≠ evidence)
3. Click "Complete Screening" / use the schedule + complete workflow
4. Refresh → Stage 1 turns green ✅

**Caption:** "Stage 1 — Screening"
**Key point:** Demonstrate that an order alone does NOT complete Stage 1
**Screenshot files:** `s3_03_stage1_pending.png`, `s3_05_stage1_green.png`

---

### Scene 4 — Upload PDF → Stage 2 Pending → Finalize → Stage 2 Green + Patient Notified
**Timestamp:** 1:05–1:30 | **Duration:** 25s
**Screen:** Coordinator uploads PDF → Stage 2 still pending → Finalizes → Stage 2 + Stage 3 green

**Steps:**
1. Stay as COORDINATOR on CASE-2026-0147
2. Upload synthetic PDF report (`screening_report.pdf`)
3. Show Stage 2 remains PENDING (upload alone insufficient)
4. Finalize and validate → Stage 2 turns green, patient notification appears

**Caption:** "Stage 2 — Result finalized · Stage 3 — Patient notified"
**Screenshot files:** `s4_02_report_uploaded_stage2_pending.png`, `s4_03_stage2_green_stage3_notified.png`

---

### Scene 5 — Patient Asks AI About Report → Stage 4 Evidence
**Timestamp:** 1:30–1:50 | **Duration:** 20s
**Screen:** Patient chat → AI explains BI-RADS 4 → Stage 4 evidence recorded

**Steps:**
1. Login as PATIENT → go to `/chat`
2. Ask: *"What does my BI-RADS 4 result mean? Should I be worried?"*
3. Show AI response explaining (70-80% benign) — not diagnostic
4. Navigate to patient timeline → Stage 4 shows evidence

**Caption:** "Stage 4 — Report explanation delivered"
**Key point:** AI explains but does NOT diagnose; delivery is recorded as evidence
**Screenshot files:** `s5_03_ai_response.png`, `s5_05_stage4_evidence.png`

---

### Scene 6 — Pre-seeded Case: Stages 5–13 Fast-cut
**Timestamp:** 1:50–2:25 | **Duration:** 35s
**Screen:** Show "Pre-seeded synthetic case" label → fast-cut through doctor/coordinator dashboards

**Steps:**
1. Display visible label: *"Pre-seeded synthetic case"* (can be a caption overlay)
2. Login as DOCTOR → show CASE-2026-0149 with doctor review
3. Fast-cut: Clinical decision → Patient confirmation → Referral created → Referral accepted
4. Fast-cut: Appointment confirmed by doctor AND patient (same version)
5. Fast-cut: Consultation recorded → Stage 10 completes
6. Fast-cut: Treatment monitoring → Follow-up → Documentation (Stages 11–13 green)

**Caption:** "Stages 5–13 — Review · Referral · Appointment · Consultation · Follow-up"
**Screenshot files:** `s6_01_preseeded_case_label.png` through `s6_07_stages_11_12_13.png`

---

### Scene 7 — Coordinator Blocked → Doctor Authorizes 14/14 Closure
**Timestamp:** 2:25–2:42 | **Duration:** 17s
**Screen:** Coordinator gets 403 Forbidden → Doctor completes closure → 14/14 green

**Steps:**
1. Login as COORDINATOR → attempt clinical-closure on CASE-2026-0149
2. Show the **403 Forbidden** / "Access Denied" message clearly
3. Login as DOCTOR → execute authorized closure sign-off
4. Show 14/14 timeline with timestamps + evidence

**Caption:** "Stage 14 — Doctor-authorized closure"
**Key point:** Role enforcement is real, not simulated — backend returns HTTP 403
**Screenshot files:** `s7_02_coordinator_blocked_403.png`, `s7_04_14_14_all_green.png`

---

### Scene 8 — All Role Dashboards + Logo
**Timestamp:** 2:42–2:50 | **Duration:** 8s
**Screen:** Patient → Coordinator → Doctor dashboards → CareBridge logo

**Steps:**
1. Brief view of patient dashboard
2. Brief view of coordinator dashboard
3. Brief view of doctor dashboard
4. Return to CareBridge homepage / logo

**Caption:** "CareBridge · Ai_Mavericks · Future Health Digital Innovation Challenge"
**Screenshot files:** `s8_01_patient_dashboard.png` through `s8_04_carebridge_logo.png`

---

## 🎞️ OBS Studio Setup

### Recording Settings
- Resolution: 1280×800
- Frame Rate: 30 fps
- Encoder: x264 (or hardware H.264)
- Output Format: MP4
- Bitrate: 3000–5000 kbps

### Scene Layout (OBS)
```
[Window Capture: Chrome - localhost:3000]
[Text Overlay: Caption bottom-center, Montserrat Bold 36px, white with shadow]
[Text Overlay: Supporting label, 24px below caption]
```

### Hotkeys Suggested
- `F8` → Start/Stop Recording
- `F9` → Pause Recording (between scenes)

---

## 🎙️ CapCut Assembly Guide

### Step 1: Import clips in order
- s1 → s2 → s3 → s4 → s5 → s6 → s7 → s8

### Step 2: Add voice-over
- Import `demo_assets/narration_transcript.txt`
- Record narration or use TTS (ElevenLabs / Google TTS)
- Sync against timestamps

### Step 3: Add captions
Per scene captions are in the script above. Use CapCut's auto-caption or manual text boxes.

### Step 4: Trim to 2:50
- Target: 2:50 exactly
- Hard limit: 2:55

### Step 5: Export
- Format: MP4, H.264
- Resolution: 1920×1080 (upscaled) or 1280×800 native
- Bitrate: 8 Mbps for submission quality

---

## ⚠️ What Requires Manual Recording

The Playwright script captures screenshots automatically. For smooth video you should:

1. **Record screen manually using OBS** while running `python scripts/record_demo_workflow.py`
   — Playwright opens a visible Chromium window you can capture directly

2. **Scene 2 (Chat):** The AI response timing depends on the LLM. Wait for complete response before proceeding.

3. **Scene 6 fast-cuts:** Use CapCut speed ramp to compress 35 seconds of content

4. **Voice-over:** Record separately into `narration_transcript.txt` timing markers

---

## ✅ Final Demo Readiness Status

| Check | Status |
|---|---|
| Backend API health | ✅ 200 OK |
| Patient dashboard (200) | ✅ |
| Coordinator dashboard (200) | ✅ |
| Doctor dashboard (200) | ✅ |
| Outbox health | ✅ Healthy |
| All 14 lifecycle stages loading | ✅ |
| Stage 1 completed (screening) | ✅ |
| Stage 2 completed (result) | ✅ |
| Coordinator closure blocked (403) | ✅ |
| Pre-seeded case CASE-2026-0149 | ✅ closed |
| Playwright automation script | ✅ ready |
| Narration transcript | ✅ ready |
| PostgreSQL schema fully synced | ✅ |
| Frontend on port 3000 | ✅ |
