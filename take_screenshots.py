import os
import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(line_buffering=True)

output_dir = r"c:\CareBridge\screenshots"
os.makedirs(output_dir, exist_ok=True)

targets = [
    {
        "url": "http://localhost:3000/patient",
        "tab_click": None,
        "name_desktop": "patient_overview_desktop.png",
        "name_mobile": "patient_overview_mobile.png",
    },
    {
        "url": "http://localhost:3000/patient",
        "tab_click": "My Journey",
        "name_desktop": "patient_journey_desktop.png",
        "name_mobile": "patient_journey_mobile.png",
    },
    {
        "url": "http://localhost:3000/doctor",
        "tab_click": None,
        "name_desktop": "doctor_overview_desktop.png",
        "name_mobile": "doctor_overview_mobile.png",
    },
    {
        "url": "http://localhost:3000/doctor",
        "tab_click": "My Patients",
        "name_desktop": "doctor_patients_desktop.png",
        "name_mobile": "doctor_patients_mobile.png",
    },
    {
        "url": "http://localhost:3000/coordinator",
        "tab_click": None,
        "name_desktop": "coordinator_overview_desktop.png",
        "name_mobile": "coordinator_overview_mobile.png",
    },
    {
        "url": "http://localhost:3000/coordinator",
        "tab_click": "All Cases",
        "name_desktop": "coordinator_all_cases_desktop.png",
        "name_mobile": "coordinator_all_cases_mobile.png",
    },
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # 1. Desktop (1280x800)
    page_d = browser.new_page(viewport={"width": 1280, "height": 800})
    for t in targets:
        print(f"[Desktop] Loading {t['url']}...")
        page_d.goto(t["url"], wait_until="domcontentloaded", timeout=10000)
        time.sleep(1.5)
        if t["tab_click"]:
            try:
                page_d.get_by_text(t["tab_click"], exact=False).first.click(timeout=3000)
                time.sleep(1)
            except Exception as e:
                print(f"Could not click tab {t['tab_click']}: {e}")
        out_path = os.path.join(output_dir, t["name_desktop"])
        page_d.screenshot(path=out_path, full_page=True)
        print(f"Saved {out_path}")
    page_d.close()

    # 2. Mobile (375x812)
    page_m = browser.new_page(viewport={"width": 375, "height": 812})
    for t in targets:
        print(f"[Mobile] Loading {t['url']}...")
        page_m.goto(t["url"], wait_until="domcontentloaded", timeout=10000)
        time.sleep(1.5)
        if t["tab_click"]:
            try:
                page_m.get_by_text(t["tab_click"], exact=False).first.click(timeout=3000)
                time.sleep(1)
            except Exception as e:
                print(f"Could not click tab {t['tab_click']}: {e}")
        out_path = os.path.join(output_dir, t["name_mobile"])
        page_m.screenshot(path=out_path, full_page=True)
        print(f"Saved {out_path}")
    page_m.close()

    browser.close()
    print("All screenshots successfully captured!")
