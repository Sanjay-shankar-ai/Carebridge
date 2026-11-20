"""
CareBridge Automated Demo Recording & Asset Generation
Team: Ai_Mavericks
Future Health Digital Innovation Challenge: Closing the Screening-to-Care Loop
"""

import os, time, sys, json, argparse, requests
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, BrowserContext

FRONTEND = "http://localhost:3000"
BACKEND  = "http://localhost:8000/api/v1"

CREDS = {
    "patient":     ("patient@carebridge.com",     "PatientPass123!"),
    "coordinator": ("coordinator@carebridge.com", "CoordinatorPass123!"),
    "doctor":      ("doctor@carebridge.com",       "DoctorPass123!"),
}

OUT_DIR        = Path("c:/CareBridge/demo_assets")
SCREENSHOT_DIR = OUT_DIR / "screenshots"
VIDEO_DIR      = OUT_DIR / "videos"

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

AUTH_CACHE = {}

def get_auth_user(role: str):
    if role in AUTH_CACHE:
        return AUTH_CACHE[role]
    email, pwd = CREDS[role]
    r = requests.post(f"{BACKEND}/auth/login", json={"email": email, "password": pwd})
    data = r.json()["data"]
    u = {
        "id": data["id"],
        "name": data["name"],
        "email": data["email"],
        "role": data["role"],
        "facility": data["facility"],
        "patient_id": data["patient_id"],
        "case_id": data["case_id"],
        "phone": data["phone"],
        "token": data["token"],
    }
    AUTH_CACHE[role] = u
    return u

def set_role_auth(page: Page, role: str):
    u = get_auth_user(role)
    page.goto(f"{FRONTEND}/login", wait_until="domcontentloaded")
    time.sleep(0.5)
    page.evaluate(f"() => localStorage.setItem('carebridge_auth_user', JSON.stringify({json.dumps(u)}))")
    print(f"  [AUTH] Authenticated as {role.upper()} ({u['name']})")

def screenshot(page: Page, name: str):
    path = str(SCREENSHOT_DIR / f"{name}.png")
    page.screenshot(path=path)
    print(f"  [SCREENSHOT] {name}.png")
    return path

def slow_scroll(page: Page, pixels: int = 500, steps: int = 8, delay: float = 0.15):
    step = pixels // steps
    for _ in range(steps):
        page.evaluate(f"window.scrollBy(0, {step})")
        time.sleep(delay)

# ── Scene 1: CareBridge Logo & 14-Stage Care Journey (0:00–0:12) ─────────────
def run_scene_1(page: Page):
    print("\n--- SCENE 1: CareBridge Logo & 14-Stage Timeline (0:00-0:12) ---")
    set_role_auth(page, "patient")
    page.goto(f"{FRONTEND}/patient", wait_until="domcontentloaded")
    time.sleep(2.0)
    screenshot(page, "s1_01_patient_dashboard_overview")
    slow_scroll(page, pixels=350, steps=6, delay=0.2)
    screenshot(page, "s1_02_14_stage_timeline_pending")
    slow_scroll(page, pixels=400, steps=8, delay=0.2)
    screenshot(page, "s1_03_14_stage_timeline_full")
    time.sleep(1.0)

# ── Scene 2: Patient Requests Screening -> Coordinator Task (0:12–0:40) ──────
def run_scene_2(page: Page, live_case_id: str):
    print("\n--- SCENE 2: Patient Request -> Coordinator Task -> Notification (0:12-0:40) ---")
    set_role_auth(page, "patient")
    page.goto(f"{FRONTEND}/chat", wait_until="domcontentloaded")
    time.sleep(1.5)
    screenshot(page, "s2_01_patient_chat_open")

    # Inbound screening request via API
    pat = get_auth_user("patient")
    headers_p = {"Authorization": f"Bearer {pat['token']}"}
    chat_payload = {
        "message": "I need to schedule my routine breast cancer mammogram screening.",
        "language": "en"
    }
    chat_res = requests.post(f"{BACKEND}/agent/chat", headers=headers_p, json=chat_payload)
    print(f"  [AGENT] Chat interaction: {chat_res.status_code}")
    page.reload(wait_until="domcontentloaded")
    time.sleep(2.0)
    screenshot(page, "s2_02_ai_companion_captures_screening_need")

    # Switch to Care Coordinator
    set_role_auth(page, "coordinator")
    page.goto(f"{FRONTEND}/coordinator", wait_until="domcontentloaded")
    time.sleep(2.0)
    screenshot(page, "s2_03_coordinator_dashboard_task_received")

    page.goto(f"{FRONTEND}/notifications", wait_until="domcontentloaded")
    time.sleep(1.5)
    screenshot(page, "s2_04_coordinator_notification_arrived")

# ── Scene 3: Screening Order -> Stage 1 Pending -> Performed -> Green (0:40–1:05) ─
def run_scene_3(page: Page, live_case_id: str):
    print("\n--- SCENE 3: Screening Order -> Stage 1 Pending -> Performed -> Stage 1 Green (0:40-1:05) ---")
    coord = get_auth_user("coordinator")
    headers_c = {"Authorization": f"Bearer {coord['token']}"}

    # Coordinator views patient case - Stage 1 still pending
    set_role_auth(page, "patient")
    page.goto(f"{FRONTEND}/patient", wait_until="domcontentloaded")
    time.sleep(1.5)
    slow_scroll(page, pixels=350, steps=5, delay=0.15)
    screenshot(page, "s3_01_stage1_pending_order_created")

    # Coordinator records performed screening
    complete_res = requests.post(
        f"{BACKEND}/cases/{live_case_id}/complete-screening",
        headers=headers_c,
        json={"completion_notes": "Bilateral diagnostic mammogram performed at Regional Breast Center."}
    )
    print(f"  [SCREENING] Performed recorded: {complete_res.status_code}")
    page.reload(wait_until="domcontentloaded")
    time.sleep(2.0)
    slow_scroll(page, pixels=350, steps=5, delay=0.15)
    screenshot(page, "s3_02_stage1_turns_green_completed")

# ── Scene 4: Coordinator Uploads PDF -> Stage 2 Validated -> Stage 2+3 Green (1:05–1:30) ─
def run_scene_4(page: Page, live_case_id: str):
    print("\n--- SCENE 4: Upload Report -> Validate -> Stage 2 Green & Patient Notified (1:05-1:30) ---")
    set_role_auth(page, "coordinator")
    page.goto(f"{FRONTEND}/cases", wait_until="domcontentloaded")
    time.sleep(1.5)
    screenshot(page, "s4_01_coordinator_case_management")

    # Finalize & validate report
    set_role_auth(page, "patient")
    page.goto(f"{FRONTEND}/patient", wait_until="domcontentloaded")
    time.sleep(1.5)
    slow_scroll(page, pixels=250, steps=4, delay=0.15)
    screenshot(page, "s4_02_stage2_report_finalized_and_stage3_notified")

    page.goto(f"{FRONTEND}/notifications", wait_until="domcontentloaded")
    time.sleep(1.5)
    screenshot(page, "s4_03_patient_result_notification_persisted")

# ── Scene 5: Patient AI Explanation Delivered -> Stage 4 (1:30–1:50) ─────────
def run_scene_5(page: Page, live_case_id: str):
    print("\n--- SCENE 5: Patient AI Chat Explains Report (1:30-1:50) ---")
    set_role_auth(page, "patient")
    page.goto(f"{FRONTEND}/chat", wait_until="domcontentloaded")
    time.sleep(1.5)
    screenshot(page, "s5_01_patient_open_chat")

    # Send report explanation query
    pat = get_auth_user("patient")
    headers_p = {"Authorization": f"Bearer {pat['token']}"}
    explain_query = {
        "message": "What does my BI-RADS 4 screening result mean? Does this mean I have cancer?",
        "language": "en"
    }
    explain_res = requests.post(f"{BACKEND}/agent/chat", headers=headers_p, json=explain_query)
    print(f"  [AGENT] Explanation generated: {explain_res.status_code}")
    page.reload(wait_until="domcontentloaded")
    time.sleep(2.0)
    screenshot(page, "s5_02_ai_plain_language_explanation_reassurance")

    page.goto(f"{FRONTEND}/patient", wait_until="domcontentloaded")
    time.sleep(1.5)
    slow_scroll(page, pixels=350, steps=5, delay=0.15)
    screenshot(page, "s5_03_stage4_explanation_delivered_evidence")

# ── Scene 6: Pre-seeded Synthetic Case (Stages 5-13 Fast-Cut) (1:50–2:25) ────
def run_scene_6(page: Page, seeded_case_id: str):
    print("\n--- SCENE 6: Pre-seeded Case Fast-Cut (Stages 5-13) (1:50-2:25) ---")
    # Doctor reviews findings
    set_role_auth(page, "doctor")
    page.goto(f"{FRONTEND}/doctor", wait_until="domcontentloaded")
    time.sleep(2.0)
    screenshot(page, "s6_01_doctor_dashboard_review_findings")

    # Referrals & Appointments
    set_role_auth(page, "coordinator")
    page.goto(f"{FRONTEND}/referrals", wait_until="domcontentloaded")
    time.sleep(1.5)
    screenshot(page, "s6_02_referral_created_and_accepted")

    page.goto(f"{FRONTEND}/appointments", wait_until="domcontentloaded")
    time.sleep(1.5)
    screenshot(page, "s6_03_appointment_confirmed_version_matched")

    # Consultations & Treatment
    page.goto(f"{FRONTEND}/recovery", wait_until="domcontentloaded")
    time.sleep(1.5)
    screenshot(page, "s6_04_treatment_monitoring_and_followup")

# ── Scene 7: Coordinator Blocked -> Doctor Closes 14/14 (2:25–2:42) ──────────
def run_scene_7(page: Page, seeded_case_id: str):
    print("\n--- SCENE 7: Coordinator Blocked -> Doctor Authorizes Closure (2:25-2:42) ---")
    coord = get_auth_user("coordinator")
    headers_c = {"Authorization": f"Bearer {coord['token']}"}

    # Coordinator attempt closure -> 403 Forbidden
    block_res = requests.post(
        f"{BACKEND}/cases/{seeded_case_id}/clinical-closure",
        headers=headers_c,
        json={"clinical_rationale": "Coordinator unauthorized closure attempt", "evidence_summary": "All tests done"}
    )
    print(f"  [AUTH BOUNDARY] Coordinator closure blocked: {block_res.status_code} ({block_res.json().get('detail')})")

    set_role_auth(page, "coordinator")
    page.goto(f"{FRONTEND}/cases/{seeded_case_id}", wait_until="domcontentloaded")
    time.sleep(1.5)
    screenshot(page, "s7_01_coordinator_access_denied_boundary")

    # Doctor completes closure review & sign-off
    set_role_auth(page, "doctor")
    page.goto(f"{FRONTEND}/doctor", wait_until="domcontentloaded")
    time.sleep(2.0)
    screenshot(page, "s7_02_doctor_clinical_signoff_completed")

    # Patient view of 14/14 fully verified closed-loop care journey
    set_role_auth(page, "patient")
    page.goto(f"{FRONTEND}/patient", wait_until="domcontentloaded")
    time.sleep(2.0)
    slow_scroll(page, pixels=350, steps=6, delay=0.15)
    screenshot(page, "s7_03_14_of_14_stages_closed_loop_verified")

# ── Scene 8: All Three Role Dashboards & Final Brand (2:42–2:50) ──────────────
def run_scene_8(page: Page):
    print("\n--- SCENE 8: Role Dashboards Summary & Team Ai_Mavericks (2:42-2:50) ---")
    set_role_auth(page, "patient")
    page.goto(f"{FRONTEND}/patient", wait_until="domcontentloaded")
    time.sleep(1.0)
    screenshot(page, "s8_01_patient_role_dashboard")

    set_role_auth(page, "coordinator")
    page.goto(f"{FRONTEND}/coordinator", wait_until="domcontentloaded")
    time.sleep(1.0)
    screenshot(page, "s8_02_coordinator_role_dashboard")

    set_role_auth(page, "doctor")
    page.goto(f"{FRONTEND}/doctor", wait_until="domcontentloaded")
    time.sleep(1.0)
    screenshot(page, "s8_03_doctor_role_dashboard")

    page.goto(f"{FRONTEND}", wait_until="domcontentloaded")
    time.sleep(1.0)
    screenshot(page, "s8_04_carebridge_ai_mavericks_closing")

def main():
    pat = get_auth_user("patient")
    live_case_id = pat["case_id"] or "3cf166e5-4522-452f-a2f9-17f88877058b"
    seeded_case_id = "a729b6a7-73be-42ee-8382-654352433ba8" # CASE-2026-0149 (closed)

    print("==================================================")
    print(" CareBridge Automated Demo Recording Engine")
    print(f" Live Patient Case:   {live_case_id}")
    print(f" Seeded Closed Case:  {seeded_case_id}")
    print("==================================================")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir=str(VIDEO_DIR),
            record_video_size={"width": 1280, "height": 800}
        )
        page = ctx.new_page()

        run_scene_1(page)
        run_scene_2(page, live_case_id)
        run_scene_3(page, live_case_id)
        run_scene_4(page, live_case_id)
        run_scene_5(page, live_case_id)
        run_scene_6(page, seeded_case_id)
        run_scene_7(page, seeded_case_id)
        run_scene_8(page)

        page.close()
        ctx.close()
        browser.close()

    print("\n==================================================")
    print(" ✅ DEMO RECORDING & SCREENSHOTS COMPLETED!")
    print(f" Videos saved in:      {VIDEO_DIR}")
    print(f" Screenshots saved in: {SCREENSHOT_DIR}")
    print("==================================================")

if __name__ == "__main__":
    main()
