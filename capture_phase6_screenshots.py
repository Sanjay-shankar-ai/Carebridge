"""
Captures high-resolution full-page screenshots of all three CareBridge role dashboards:
  1. Patient Dashboard (/patient)
  2. Doctor Dashboard (/doctor)
  3. Care Coordinator Dashboard (/coordinator)
Using Playwright to automate authentication and render the exact browser UI.
"""

import os
import sys
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\HARIHARAN\.gemini\antigravity\brain\a1de062f-eaa1-4d4d-9b76-7a918e1af223"

def capture_dashboards():
    print("Launching Chromium browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 960})
        page = context.new_page()

        # ---------------------------------------------------------------------
        # 1. PATIENT DASHBOARD
        # ---------------------------------------------------------------------
        print("\n[1/3] Navigating to Patient Dashboard...")
        page.goto("http://localhost:3000/login", wait_until="networkidle")
        time.sleep(1)

        # Login as Patient
        page.fill("input[type='email']", "patient@carebridge.com")
        page.fill("input[type='password']", "PatientPass123!")
        page.click("button[type='submit']")
        
        page.wait_for_url("**/patient", timeout=10000)
        time.sleep(2.5) # Allow dynamic cards, AI assistant, and journey steps to settle

        patient_path = os.path.join(ARTIFACT_DIR, "patient_dashboard.png")
        page.screenshot(path=patient_path, full_page=True)
        print(f"Captured Patient Dashboard -> {patient_path}")

        # ---------------------------------------------------------------------
        # 2. DOCTOR DASHBOARD
        # ---------------------------------------------------------------------
        print("\n[2/3] Navigating to Doctor Dashboard...")
        page.goto("http://localhost:3000/login", wait_until="networkidle")
        time.sleep(1)

        # Login as Doctor
        page.fill("input[type='email']", "doctor@carebridge.com")
        page.fill("input[type='password']", "DoctorPass123!")
        page.click("button[type='submit']")

        page.wait_for_url("**/doctor", timeout=10000)
        time.sleep(2.5) # Allow escalation queue, roster, checklist, and referrals to render

        doctor_path = os.path.join(ARTIFACT_DIR, "doctor_dashboard.png")
        page.screenshot(path=doctor_path, full_page=True)
        print(f"Captured Doctor Dashboard -> {doctor_path}")

        # ---------------------------------------------------------------------
        # 3. CARE COORDINATOR DASHBOARD
        # ---------------------------------------------------------------------
        print("\n[3/3] Navigating to Care Coordinator Dashboard...")
        page.goto("http://localhost:3000/login", wait_until="networkidle")
        time.sleep(1)

        # Login as Coordinator
        page.fill("input[type='email']", "coordinator@carebridge.com")
        page.fill("input[type='password']", "CoordinatorPass123!")
        page.click("button[type='submit']")

        page.wait_for_url("**/coordinator", timeout=10000)
        time.sleep(2.5) # Allow surveillance queue, radar, active referrals, and SLA countdowns to render

        coord_path = os.path.join(ARTIFACT_DIR, "coordinator_dashboard.png")
        page.screenshot(path=coord_path, full_page=True)
        print(f"Captured Care Coordinator Dashboard -> {coord_path}")

        browser.close()
        print("\nAll 3 dashboard screenshots successfully captured!")

if __name__ == "__main__":
    capture_dashboards()
