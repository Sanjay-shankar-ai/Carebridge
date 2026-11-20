"""
Captures high-resolution full-page screenshots of all three CareBridge role dashboards
with the Notification Center dropdown open showing real-time PostgreSQL notifications:
  1. Patient Dashboard (/patient) -> patient_notifications.png
  2. Doctor Dashboard (/doctor) -> doctor_notifications.png
  3. Care Coordinator Dashboard (/coordinator) -> coordinator_notifications.png
"""

import os
import sys
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\HARIHARAN\.gemini\antigravity\brain\a1de062f-eaa1-4d4d-9b76-7a918e1af223"

def capture_notification_dashboards():
    print("Launching Chromium browser for Phase 7 screenshots...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 960})
        page = context.new_page()

        # ---------------------------------------------------------------------
        # 1. PATIENT DASHBOARD NOTIFICATIONS
        # ---------------------------------------------------------------------
        print("\n[1/3] Logging in as Patient and opening Notification Center...")
        page.goto("http://localhost:3000/login", wait_until="networkidle")
        page.fill("input[type='email']", "patient@carebridge.com")
        page.fill("input[type='password']", "PatientPass123!")
        page.click("button[type='submit']")
        
        page.wait_for_url("**/patient", timeout=10000)
        time.sleep(2.0)

        # Click Notification Bell
        page.click("button[aria-label='View notifications']")
        time.sleep(1.0) # Popover animation

        patient_path = os.path.join(ARTIFACT_DIR, "patient_notifications.png")
        page.screenshot(path=patient_path, full_page=True)
        print(f"Captured Patient Notifications -> {patient_path}")

        # ---------------------------------------------------------------------
        # 2. DOCTOR DASHBOARD NOTIFICATIONS
        # ---------------------------------------------------------------------
        print("\n[2/3] Logging in as Doctor and opening Notification Center...")
        page.goto("http://localhost:3000/login", wait_until="networkidle")
        page.fill("input[type='email']", "doctor@carebridge.com")
        page.fill("input[type='password']", "DoctorPass123!")
        page.click("button[type='submit']")

        page.wait_for_url("**/doctor", timeout=10000)
        time.sleep(2.0)

        # Click Notification Bell
        page.click("button[aria-label='View notifications']")
        time.sleep(1.0) # Popover animation

        doctor_path = os.path.join(ARTIFACT_DIR, "doctor_notifications.png")
        page.screenshot(path=doctor_path, full_page=True)
        print(f"Captured Doctor Notifications -> {doctor_path}")

        # ---------------------------------------------------------------------
        # 3. CARE COORDINATOR DASHBOARD NOTIFICATIONS
        # ---------------------------------------------------------------------
        print("\n[3/3] Logging in as Care Coordinator and opening Notification Center...")
        page.goto("http://localhost:3000/login", wait_until="networkidle")
        page.fill("input[type='email']", "coordinator@carebridge.com")
        page.fill("input[type='password']", "CoordinatorPass123!")
        page.click("button[type='submit']")

        page.wait_for_url("**/coordinator", timeout=10000)
        time.sleep(2.0)

        # Click Notification Bell
        page.click("button[aria-label='View notifications']")
        time.sleep(1.0) # Popover animation

        coord_path = os.path.join(ARTIFACT_DIR, "coordinator_notifications.png")
        page.screenshot(path=coord_path, full_page=True)
        print(f"Captured Care Coordinator Notifications -> {coord_path}")

        browser.close()
        print("\nAll 3 Phase 7 notification screenshots successfully captured!")

if __name__ == "__main__":
    capture_notification_dashboards()
