"""
Captures high-resolution full-page screenshots of CareBridge FHIR R4 Gateway:
  1. FHIR Gateway Overview (/fhir) -> fhir_gateway_overview.png
  2. FHIR Raw JSON Inspector Modal -> fhir_json_inspector.png
  3. FHIR Live $validate Tool Modal with OperationOutcome -> fhir_validator_tool.png
"""

import os
import sys
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\HARIHARAN\.gemini\antigravity\brain\a1de062f-eaa1-4d4d-9b76-7a918e1af223"

def capture_fhir_screenshots():
    print("Launching Chromium browser for Phase 8 FHIR screenshots...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 960})
        page = context.new_page()

        # ---------------------------------------------------------------------
        # 1. LOGIN AS DOCTOR
        # ---------------------------------------------------------------------
        print("\n[1/3] Logging in as Doctor persona...")
        page.goto("http://localhost:3000/login", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        # Use 1-click doctor persona
        doctor_btn = page.locator("button:has-text('Dr. Aris Thorne, MD')").first
        if doctor_btn.is_visible():
            doctor_btn.click()
        else:
            page.fill("input[type='email']", "doctor@carebridge.com")
            page.fill("input[type='password']", "DoctorPass123!")
            page.click("button[type='submit']")

        page.wait_for_timeout(2500)

        # Navigate to /fhir
        print("Navigating to /fhir gateway...")
        page.goto("http://localhost:3000/fhir", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Switch to DiagnosticReport tab to show clinical screening records
        print("Selecting DiagnosticReport tab...")
        page.locator("button:has-text('DiagnosticReport')").first.click()
        page.wait_for_timeout(2000)

        # 1. SCREENSHOT: Gateway Overview
        overview_path = os.path.join(ARTIFACT_DIR, "fhir_gateway_overview.png")
        page.screenshot(path=overview_path, full_page=True)
        print(f"Captured FHIR Gateway Overview -> {overview_path}")

        # ---------------------------------------------------------------------
        # 2. SCREENSHOT: JSON Inspector Modal
        # ---------------------------------------------------------------------
        print("\n[2/3] Opening JSON Inspector for first DiagnosticReport...")
        inspect_btn = page.locator("button:has-text('Inspect JSON')").first
        if inspect_btn.is_visible():
            inspect_btn.click()
            page.wait_for_timeout(1200)
            inspector_path = os.path.join(ARTIFACT_DIR, "fhir_json_inspector.png")
            page.screenshot(path=inspector_path, full_page=False)
            print(f"Captured FHIR JSON Inspector -> {inspector_path}")
            # Close inspector
            page.locator("button:has-text('Close')").first.click()
            page.wait_for_timeout(800)

        # ---------------------------------------------------------------------
        # 3. SCREENSHOT: $validate Tool Modal
        # ---------------------------------------------------------------------
        print("\n[3/3] Opening $validate tool and validating resource...")
        page.locator("button:has-text('Validate Resource')").first.click()
        page.wait_for_timeout(1200)

        # Click Validate against FHIR R4 button
        page.locator("button:has-text('Validate against FHIR R4')").first.click()
        page.wait_for_timeout(2000)

        validator_path = os.path.join(ARTIFACT_DIR, "fhir_validator_tool.png")
        page.screenshot(path=validator_path, full_page=False)
        print(f"Captured FHIR $validate Tool -> {validator_path}")

        browser.close()
        print("\nAll Phase 8 FHIR screenshots successfully captured!")

if __name__ == "__main__":
    capture_fhir_screenshots()
