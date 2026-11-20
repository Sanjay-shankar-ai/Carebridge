"""
CareBridge Final Product Demonstration Video Generator (Exact 2:50 Runtime)
Team: Ai_Mavericks
Future Health Digital Innovation Challenge: Closing the Screening-to-Care Loop
Target Runtime: 2:50 (170.0 seconds) | Hard Limit: 2:55 (175.0 seconds)

Storyboard (Exact 8 Scenes):
  1. 0:00–0:12 — Opening and empty 14-stage journey (includes visible loginAs("patient") at 0:03–0:08.3).
  2. 0:12–0:40 — Patient intake, coordinator task and notification (includes visible loginAs("coordinator") at 0:23–0:28.3).
  3. 0:40–1:05 — Screening performed and report finalized (order pending -> performed Stage 1 green; PDF upload pending -> finalized Stages 2 & 3 green).
  4. 1:05–1:30 — Patient receives and understands the actual report through AI explanation (Stage 4 green).
  5. 1:30–1:50 — Natural, contextual patient AI conversation (single persisted reply, real case context).
  6. 1:50–2:25 — Doctor review, referral acceptance, appointment (same version v1 dual-confirmed) and consultation (includes visible loginAs("doctor") at 2:03–2:08.3).
  7. 2:25–2:42 — Coordinator closure restriction (403 shown once) followed by successful doctor-authorized closure (14/14 with full timeline events & referrals).
  8. 2:42–2:50 — Patient, doctor and coordinator dashboards and closing screen.

Deliverables:
  - demo_assets/videos/CareBridge_Final_Demo_Ai_Mavericks.mp4 (H.264 video + AAC synchronized narration & low-volume background music)
  - demo_assets/videos/CareBridge_Cinematic_Demo_Final.mp4
  - demo_assets/videos/CareBridge_Cinematic_Demo_Final.webm
  - demo_assets/videos/CareBridge_Demo_Video_Ai_Mavericks.webm
"""

import io
import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

import imageio_ffmpeg
import requests
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

ROOT_DIR = Path("c:/CareBridge")
BACKEND_DIR = ROOT_DIR / "backend"
SCRIPTS_DIR = ROOT_DIR / "scripts"
for p in (str(ROOT_DIR), str(BACKEND_DIR), str(SCRIPTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.database.session import get_sync_db
from app.models import Appointment, CareCase, Referral, Task, User
from app.services.appointment_service import AppointmentService
from app.services.lifecycle_service import LifecycleService
from generate_narration_and_music import build_master_soundtrack
from prepare_clean_demo_state import (
    deduplicate_communications,
    repair_closed_cases,
    reset_judge_case_for_scene_1,
)

FRONTEND = "http://localhost:3000"
BACKEND = "http://localhost:8000/api/v1"
FFMPEG_FULL_BIN = imageio_ffmpeg.get_ffmpeg_exe()

# Synthetic demo credentials (passwords are never logged, printed, or exposed)
CREDS = {
    "patient": ("patient@carebridge.com", os.getenv("DEMO_PATIENT_PASSWORD", "PatientPass123!")),
    "coordinator": ("coordinator@carebridge.com", os.getenv("DEMO_COORDINATOR_PASSWORD", "CoordinatorPass123!")),
    "doctor": ("doctor@carebridge.com", os.getenv("DEMO_DOCTOR_PASSWORD", "DoctorPass123!")),
}

ROLE_BADGE_LABELS = {
    "patient": "Patient",
    "coordinator": "Care Coordinator",
    "doctor": "Doctor",
}

ROLE_EXPECTED_PATHS = {
    "patient": "/patient",
    "coordinator": "/coordinator",
    "doctor": "/doctor",
}

OUT_DIR = ROOT_DIR / "demo_assets"
VIDEO_DIR = OUT_DIR / "videos"
SHOT_DIR = OUT_DIR / "screenshots"
LOGIN_FRAMES_DIR = OUT_DIR / "login_verification_frames"
SCENE_VERIFY_DIR = OUT_DIR / "scene_verification_frames"
FAILED_SCENES_PATH = ROOT_DIR / "FAILED_SCENES.md"

for d in (VIDEO_DIR, SHOT_DIR, LOGIN_FRAMES_DIR, SCENE_VERIFY_DIR):
    d.mkdir(parents=True, exist_ok=True)

FPS = 25
AUTH_CACHE: Dict[str, dict] = {}


def fail_scene(scene_label: str, reason: str) -> None:
    """Writes failure details to FAILED_SCENES.md (without secrets) and stops immediately."""
    safe_reason = reason
    for _, pwd in CREDS.values():
        if pwd:
            safe_reason = safe_reason.replace(pwd, "[REDACTED]")
    content = (
        "# CareBridge Demo Recording - Failed Scene Report\n\n"
        f"- **Scene / Step:** {scene_label}\n"
        f"- **Timestamp (UTC):** {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
        f"- **Reason:** {safe_reason}\n"
    )
    FAILED_SCENES_PATH.write_text(content, encoding="utf-8")
    print(f"\n[FATAL] {scene_label} failed: {safe_reason}. Written to {FAILED_SCENES_PATH}", file=sys.stderr)
    sys.exit(1)


def get_auth_user(role: str) -> dict:
    """Fetches API token for authorized backend actions (never logs token or password)."""
    if role in AUTH_CACHE:
        return AUTH_CACHE[role]
    email, pwd = CREDS[role]
    r = requests.post(f"{BACKEND}/auth/login", json={"email": email, "password": pwd}, timeout=10)
    if r.status_code != 200:
        fail_scene(f"API preflight ({role})", f"Backend /auth/login returned HTTP {r.status_code} for {email}")
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


def build_synthetic_pdf_bytes(case_number: str) -> bytes:
    """Builds a real, valid %PDF-1.4 binary document containing the synthetic BI-RADS 4 mammogram report."""
    report_text = (
        f"CAREBRIDGE DIAGNOSTIC MAMMOGRAM REPORT - CASE {case_number}. "
        "Patient: Meera Krishnan. Modality: Bilateral Digital Diagnostic Mammography. "
        "Finding Code: BI-RADS 4 (Suspicious Abnormality). "
        "Findings: 1.4 cm focal architectural distortion with clustered microcalcifications in the upper outer quadrant. "
        "Recommendation: Targeted ultrasound and ultrasound-guided core needle biopsy within 14 days."
    )
    stream_body = f"BT /F1 11 Tf 40 740 Td ({report_text}) Tj ET".encode("latin-1")
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length " + str(len(stream_body)).encode("ascii") + b" >>\nstream\n"
        + stream_body
        + b"\nendstream\nendobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n"
        b"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n9\n%%EOF\n"
    )
    return pdf


class UnifiedPipeRecorder:
    """
    Records a single continuous 25fps H.264 video stream across multiple persistent BrowserContexts.
    Guarantees exact scene duration budgets while capturing real interactive frames.
    """

    def __init__(self, raw_video_path: Path, fps: int = FPS):
        self.raw_video_path = raw_video_path
        self.fps = fps
        self.frames_written = 0
        self.active_page: Optional[Page] = None
        self.last_jpg: Optional[bytes] = None
        self.proc = subprocess.Popen(
            [
                FFMPEG_FULL_BIN,
                "-y",
                "-loglevel",
                "error",
                "-f",
                "image2pipe",
                "-c:v",
                "mjpeg",
                "-r",
                str(fps),
                "-i",
                "pipe:0",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(fps),
                str(raw_video_path),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @property
    def elapsed_video_seconds(self) -> float:
        return self.frames_written / float(self.fps)

    def set_active_page(self, page: Page) -> None:
        self.active_page = page

    def capture_frame(self, page: Optional[Page] = None) -> bytes:
        target = page or self.active_page
        assert target is not None, "No active page set on recorder"
        try:
            jpg = target.screenshot(type="jpeg", quality=90)
            self.last_jpg = jpg
            return jpg
        except Exception:
            assert self.last_jpg is not None
            return self.last_jpg

    def write_frames(self, count: int, jpg: Optional[bytes] = None) -> None:
        if count <= 0:
            return
        frame = jpg if jpg is not None else self.capture_frame()
        for _ in range(count):
            self.proc.stdin.write(frame)
        self.frames_written += count

    def hold(self, duration_sec: float, page: Optional[Page] = None, refresh_interval: float = 0.20) -> None:
        """Holds on the active page for exact `duration_sec` of video time, sampling live animations."""
        target_frames = max(1, int(round(duration_sec * self.fps)))
        chunk_frames = max(1, int(round(refresh_interval * self.fps)))
        remaining = target_frames
        while remaining > 0:
            n = min(chunk_frames, remaining)
            t0 = time.time()
            jpg = self.capture_frame(page)
            self.write_frames(n, jpg)
            spent = time.time() - t0
            sleep_needed = (n / float(self.fps)) - spent
            if sleep_needed > 0:
                time.sleep(min(sleep_needed, 0.15))
            remaining -= n

    def pad_to_video_time(self, target_video_sec: float, page: Optional[Page] = None) -> None:
        """Pads final hold in a scene so cumulative video time lands on exact target_video_sec."""
        target_total_frames = int(round(target_video_sec * self.fps))
        delta_frames = target_total_frames - self.frames_written
        if delta_frames > 0:
            self.hold(delta_frames / float(self.fps), page=page, refresh_interval=0.25)

    def close(self) -> None:
        if self.proc and self.proc.stdin:
            self.proc.stdin.close()
            self.proc.wait(timeout=120)


def wait_for_page_ready(page: Page, timeout_sec: float = 8.0) -> None:
    """
    Waits for all API requests and DOM data to settle and verifies zero loading skeletons
    or spinners are visible before any video frame is captured.
    """
    try:
        page.wait_for_load_state("domcontentloaded", timeout=6000)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=3500)
    except Exception:
        pass

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            is_loading = page.evaluate(
                """() => {
                    const text = document.body ? document.body.innerText : '';
                    if (
                        text.includes('Loading your care pathway...') ||
                        text.includes('Loading Case Detail...') ||
                        text.includes('Loading clinical workspace...') ||
                        text.includes('Loading coordination queue...')
                    ) {
                        return true;
                    }
                    const spinners = document.querySelectorAll('.animate-spin, .animate-pulse');
                    for (const sp of spinners) {
                        const rect = sp.getBoundingClientRect();
                        if (rect.width > 20 && rect.height > 20) {
                            return true;
                        }
                    }
                    return false;
                }"""
            )
            if not is_loading:
                break
        except Exception:
            break
        time.sleep(0.12)
    time.sleep(0.15)


def inject_overlay(
    page: Page,
    scene_idx: int,
    timecode: str,
    caption: str,
    supporting: str,
) -> None:
    """
    Injects synchronized bottom broadcast overlay.
    NOTE: Never displays any 'PRE-SEEDED SYNTHETIC CASE' or developer warning badge.
    """
    overlay_html = f"""
        <div style="display: flex; align-items: center; gap: 14px; min-width: 0;">
            <div style="background: #0F766E; color: white; padding: 6px 12px; border-radius: 8px; font-weight: 800; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; white-space: nowrap;">
                SCENE {scene_idx}/8 [{timecode}]
            </div>
            <div style="min-width: 0;">
                <div style="font-size: 15px; font-weight: 800; color: #34D399; letter-spacing: 0.02em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                    {caption}
                </div>
                <div style="font-size: 12px; font-weight: 500; color: #94A3B8; margin-top: 2px;">
                    Supporting evidence: <span style="color: #F8FAFC; font-weight: 600;">{supporting}</span>
                </div>
            </div>
        </div>
        <div style="display: flex; align-items: center; gap: 12px; flex-shrink: 0;">
            <div style="text-align: right; border-left: 1px solid #334155; padding-left: 16px;">
                <div style="font-size: 9px; font-weight: 700; color: #64748B; letter-spacing: 0.08em; text-transform: uppercase;">Future Health Challenge</div>
                <div style="font-size: 12px; font-weight: 800; color: #38BDF8;">Team: Ai_Mavericks</div>
            </div>
        </div>
    """

    page.evaluate(
        """(htmlContent) => {
            let existing = document.getElementById('demo-tv-overlay');
            if (existing) existing.remove();

            let overlay = document.createElement('div');
            overlay.id = 'demo-tv-overlay';
            overlay.style.position = 'fixed';
            overlay.style.bottom = '14px';
            overlay.style.left = '50%';
            overlay.style.transform = 'translateX(-50%)';
            overlay.style.zIndex = '9999999';
            overlay.style.width = '92%';
            overlay.style.maxWidth = '1120px';
            overlay.style.background = 'rgba(15, 23, 42, 0.94)';
            overlay.style.backdropFilter = 'blur(16px)';
            overlay.style.border = '1.5px solid #0F766E';
            overlay.style.borderRadius = '14px';
            overlay.style.padding = '9px 20px';
            overlay.style.color = '#FFFFFF';
            overlay.style.fontFamily = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
            overlay.style.boxShadow = '0 20px 45px rgba(0,0,0,0.5), 0 0 15px rgba(15, 118, 110, 0.3)';
            overlay.style.display = 'flex';
            overlay.style.alignItems = 'center';
            overlay.style.justifyContent = 'space-between';
            overlay.innerHTML = htmlContent;
            document.body.appendChild(overlay);
        }""",
        overlay_html,
    )


def show_role_badge(page: Page, role: str) -> None:
    """
    Injects the lower-left role badge ("Patient", "Care Coordinator", or "Doctor")
    with a 1.5s fade so viewers always know who is logged in.
    """
    label = ROLE_BADGE_LABELS[role]
    accent = {"patient": "#10B981", "coordinator": "#F59E0B", "doctor": "#38BDF8"}[role]
    page.evaluate(
        """({label, accent}) => {
            let old = document.getElementById('demo-role-badge');
            if (old) old.remove();

            let badge = document.createElement('div');
            badge.id = 'demo-role-badge';
            badge.style.position = 'fixed';
            badge.style.left = '28px';
            badge.style.bottom = '84px';
            badge.style.zIndex = '10000001';
            badge.style.background = 'rgba(15, 23, 42, 0.96)';
            badge.style.border = '2px solid ' + accent;
            badge.style.borderRadius = '999px';
            badge.style.padding = '7px 16px';
            badge.style.display = 'inline-flex';
            badge.style.alignItems = 'center';
            badge.style.gap = '10px';
            badge.style.color = '#F8FAFC';
            badge.style.fontFamily = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
            badge.style.fontSize = '12.5px';
            badge.style.fontWeight = '800';
            badge.style.letterSpacing = '0.03em';
            badge.style.boxShadow = '0 10px 25px rgba(0,0,0,0.45)';
            badge.style.opacity = '1';
            badge.style.transition = 'opacity 1.5s ease-in-out';
            badge.innerHTML = `
                <span style="width: 10px; height: 10px; border-radius: 50%; background: ${accent}; display: inline-block; box-shadow: 0 0 8px ${accent};"></span>
                <span>Role: ${label}</span>
            `;
            document.body.appendChild(badge);
            setTimeout(() => {
                if (badge && badge.parentNode) {
                    badge.style.opacity = '0.20';
                }
            }, 950);
        }""",
        {"label": label, "accent": accent},
    )


def assert_no_secret_exposed(page: Page, role: str, step_tag: str) -> None:
    """Verifies that neither the password nor any JWT token is visible in URL, DOM text, or input[type!=password]."""
    _, pwd = CREDS[role]
    url = page.url
    if pwd in url or "eyJ" in url:
        fail_scene(f"Credential leak check ({role} - {step_tag})", "Secret or token detected in page URL")

    dom_check = page.evaluate(
        """(pwd) => {
            const bodyText = document.body ? document.body.innerText : '';
            const pwdInText = pwd && bodyText.includes(pwd);
            const jwtInText = /eyJ[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}/.test(bodyText);
            const pwdInput = document.querySelector('input[type="password"]');
            const allInputs = Array.from(document.querySelectorAll('input'));
            let plainPwdInput = false;
            for (const inp of allInputs) {
                if (inp.value === pwd && inp.getAttribute('type') !== 'password') {
                    plainPwdInput = true;
                }
            }
            return {
                pwdInText,
                jwtInText,
                plainPwdInput,
                hasPasswordInput: !!pwdInput,
            };
        }""",
        pwd,
    )
    if dom_check["pwdInText"] or dom_check["jwtInText"] or dom_check["plainPwdInput"]:
        fail_scene(
            f"Credential leak check ({role} - {step_tag})",
            f"Secret exposure detected in DOM: {json.dumps(dom_check)}",
        )


def loginAs(
    role: str,
    pages: Dict[str, Page],
    rec: UnifiedPipeRecorder,
    scene_idx: int,
    timecode: str,
    caption: str,
    supporting: str,
) -> Page:
    """
    Visible login helper (5.32s total, strictly within 5-6s):
    1. Opens REAL /login page in the role's dedicated BrowserContext and holds empty form for 1.0s.
    2. Types synthetic demo email slowly (42ms/char, within 35-60ms/char).
    3. Types password into input[type="password"] so it appears ONLY as dots.
    4. Moves visible cursor with eased motion (560ms, within 400-700ms) to Login button, shows click pulse, clicks.
    5. Waits for real dashboard data to finish loading (zero loading skeletons), shows lower-left Role Badge, and holds 1.0s.
    """
    email, pwd = CREDS[role]
    page = pages[role]
    rec.set_active_page(page)
    print(f"  [LOGIN] Visible loginAs('{role}') -> {email} (password masked as dots)")

    try:
        page.goto(f"{FRONTEND}/login", wait_until="domcontentloaded", timeout=15000)
    except Exception as exc:
        fail_scene(f"loginAs({role}) navigation", f"Could not load {FRONTEND}/login: {exc}")

    email_sel = 'input[type="email"]'
    pwd_sel = 'input[type="password"]'
    submit_sel = 'button[type="submit"]'
    try:
        page.wait_for_selector(email_sel, state="visible", timeout=8000)
        page.wait_for_selector(pwd_sel, state="visible", timeout=8000)
        page.wait_for_selector(submit_sel, state="visible", timeout=8000)
        page.fill(email_sel, "")
        page.fill(pwd_sel, "")
    except Exception as exc:
        fail_scene(f"loginAs({role}) form elements", f"Login form inputs not found on /login: {exc}")

    inject_overlay(page, scene_idx, timecode, caption, supporting)
    assert_no_secret_exposed(page, role, "empty_form")

    # 1. Show empty login form for 1.0s (25 frames)
    rec.hold(1.0, page=page)
    page.screenshot(path=str(LOGIN_FRAMES_DIR / f"login_{role}_1_empty_form.png"))

    # 2. Type demo email slowly (42ms/char -> 26 frames)
    page.focus(email_sel)
    email_frames_budget = 26
    chars_per_capture = max(1, len(email) // 13)
    written_e = 0
    for idx, ch in enumerate(email):
        page.keyboard.type(ch, delay=42)
        if (idx + 1) % chars_per_capture == 0 or idx == len(email) - 1:
            target_f = int(round(((idx + 1) / len(email)) * email_frames_budget))
            df = max(1, target_f - written_e)
            rec.write_frames(df)
            written_e += df
    assert_no_secret_exposed(page, role, "after_email")
    page.screenshot(path=str(LOGIN_FRAMES_DIR / f"login_{role}_2_email_typed.png"))

    # 3. Type password into password field so it appears ONLY as dots (18 frames)
    input_type = page.get_attribute(pwd_sel, "type")
    if input_type != "password":
        fail_scene(f"loginAs({role}) password field check", f"Expected type='password', found type='{input_type}'")

    page.focus(pwd_sel)
    pwd_frames_budget = 18
    chars_per_pwd_cap = max(1, len(pwd) // 9)
    written_p = 0
    for idx, ch in enumerate(pwd):
        page.keyboard.type(ch, delay=40)
        if (idx + 1) % chars_per_pwd_cap == 0 or idx == len(pwd) - 1:
            target_f = int(round(((idx + 1) / len(pwd)) * pwd_frames_budget))
            df = max(1, target_f - written_p)
            rec.write_frames(df)
            written_p += df
    assert_no_secret_exposed(page, role, "after_password_dots")

    # 4. Eased cursor movement (560ms = 14 frames) + click pulse (240ms = 6 frames)
    pwd_box = page.locator(pwd_sel).bounding_box()
    btn_box = page.locator(submit_sel).bounding_box()
    if not pwd_box or not btn_box:
        fail_scene(f"loginAs({role}) button bounding box", "Could not resolve bounding box for submit button")

    start_x = pwd_box["x"] + pwd_box["width"] * 0.55
    start_y = pwd_box["y"] + pwd_box["height"] * 0.5
    end_x = btn_box["x"] + btn_box["width"] * 0.5
    end_y = btn_box["y"] + btn_box["height"] * 0.5

    page.evaluate(
        """({x, y}) => {
            let cur = document.getElementById('demo-cursor');
            if (cur) cur.remove();
            cur = document.createElement('div');
            cur.id = 'demo-cursor';
            cur.style.position = 'fixed';
            cur.style.left = x + 'px';
            cur.style.top = y + 'px';
            cur.style.width = '22px';
            cur.style.height = '22px';
            cur.style.borderRadius = '50%';
            cur.style.background = 'rgba(20, 184, 166, 0.92)';
            cur.style.border = '2.5px solid #FFFFFF';
            cur.style.boxShadow = '0 4px 14px rgba(0,0,0,0.45)';
            cur.style.zIndex = '10000002';
            cur.style.pointerEvents = 'none';
            cur.style.transform = 'translate(-50%, -50%)';
            document.body.appendChild(cur);
        }""",
        {"x": start_x, "y": start_y},
    )

    motion_frames = 14
    for step in range(1, motion_frames + 1):
        t = step / float(motion_frames)
        eased = 4 * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2
        cx = start_x + (end_x - start_x) * eased
        cy = start_y + (end_y - start_y) * eased
        page.evaluate(
            """({x, y}) => {
                const cur = document.getElementById('demo-cursor');
                if (cur) { cur.style.left = x + 'px'; cur.style.top = y + 'px'; }
            }""",
            {"x": cx, "y": cy},
        )
        time.sleep(0.015)
        rec.write_frames(1)

    page.evaluate(
        """({x, y}) => {
            let pulse = document.createElement('div');
            pulse.id = 'demo-click-pulse';
            pulse.style.position = 'fixed';
            pulse.style.left = x + 'px';
            pulse.style.top = y + 'px';
            pulse.style.width = '44px';
            pulse.style.height = '44px';
            pulse.style.borderRadius = '50%';
            pulse.style.border = '3px solid #2DD4BF';
            pulse.style.background = 'rgba(45, 212, 191, 0.25)';
            pulse.style.zIndex = '10000001';
            pulse.style.pointerEvents = 'none';
            pulse.style.transform = 'translate(-50%, -50%)';
            document.body.appendChild(pulse);
        }""",
        {"x": end_x, "y": end_y},
    )
    assert_no_secret_exposed(page, role, "cursor_and_pulse_on_submit")
    page.screenshot(path=str(LOGIN_FRAMES_DIR / f"login_{role}_3_dots_and_click_pulse.png"))
    rec.write_frames(6)

    expected_path = ROLE_EXPECTED_PATHS[role]
    try:
        page.click(submit_sel)
        page.evaluate(
            """() => {
                const c = document.getElementById('demo-cursor');
                if (c) c.remove();
                const p = document.getElementById('demo-click-pulse');
                if (p) p.remove();
            }"""
        )
        page.wait_for_url(f"**{expected_path}**", timeout=12000)
        wait_for_page_ready(page)
    except Exception as exc:
        fail_scene(
            f"loginAs({role}) dashboard redirect",
            f"Did not redirect to {expected_path} after clicking submit (current URL: {page.url}): {exc}",
        )

    has_auth = page.evaluate("() => !!localStorage.getItem('carebridge_auth_user')")
    if not has_auth:
        fail_scene(f"loginAs({role}) session check", "localStorage 'carebridge_auth_user' missing after login")

    inject_overlay(page, scene_idx, timecode, caption, supporting)
    show_role_badge(page, role)
    assert_no_secret_exposed(page, role, "dashboard_loaded")
    rec.hold(0.76, page=page)
    page.screenshot(path=str(LOGIN_FRAMES_DIR / f"login_{role}_4_dashboard_with_role_badge.png"))
    rec.hold(1.0, page=page)
    return page


def switch_to_role(
    role: str,
    path: str,
    pages: Dict[str, Page],
    rec: UnifiedPipeRecorder,
    scene_idx: int,
    timecode: str,
    caption: str,
    supporting: str,
    force_reload: bool = False,
) -> Page:
    """
    Cuts to an already-logged-in role's persistent BrowserContext page,
    waits for all required API data before capturing a single frame,
    injects the synchronized scene overlay, and shows the lower-left Role Badge.
    """
    page = pages[role]
    rec.set_active_page(page)
    target_url = f"{FRONTEND}{path}"
    if page.url != target_url:
        page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
        wait_for_page_ready(page)
    elif force_reload:
        # Trigger silent data update first; reload only if needed
        page.evaluate("window.dispatchEvent(new Event('carebridge:data_updated'))")
        wait_for_page_ready(page)
    inject_overlay(page, scene_idx, timecode, caption, supporting)
    show_role_badge(page, role)
    assert_no_secret_exposed(page, role, f"switch_to_{role}_{path}")
    return page


def type_and_submit_single_chat_turn(
    rec: UnifiedPipeRecorder,
    page: Page,
    prompt_text: str,
    type_duration_sec: float,
    stream_wait_sec: float,
) -> None:
    """
    Types a chat message once into the UI textarea, presses Enter ONCE,
    and records the real streamed response without ever double-submitting.
    """
    chat_box = "textarea"
    page.wait_for_selector(chat_box, state="visible", timeout=8000)
    page.fill(chat_box, "")

    total_frames = max(1, int(round(type_duration_sec * rec.fps)))
    chunks = 12
    chunk_size = max(1, math.ceil(len(prompt_text) / float(chunks)))
    frames_per_chunk = max(1, total_frames // chunks)
    written = 0
    for i in range(0, len(prompt_text), chunk_size):
        piece = prompt_text[i : i + chunk_size]
        page.type(chat_box, piece, delay=12)
        df = (
            min(frames_per_chunk, total_frames - written)
            if (i + chunk_size < len(prompt_text))
            else (total_frames - written)
        )
        if df > 0:
            rec.write_frames(df)
            written += df

    # Submit ONCE via Enter key
    page.keyboard.press("Enter")
    rec.hold(stream_wait_sec, page=page, refresh_interval=0.16)


# ==============================================================================
# SCENE 1 (0:00–0:12 = 12s) — Opening and empty 14-stage journey
# ==============================================================================
def scene_1(pages: Dict[str, Page], rec: UnifiedPipeRecorder) -> None:
    print("\n>>> [0:00 - 0:12] SCENE 1: Opening, Patient Login & Empty 14-Stage Journey (12s)")
    page = pages["patient"]
    rec.set_active_page(page)
    page.goto(f"{FRONTEND}/login", wait_until="domcontentloaded")
    wait_for_page_ready(page)
    inject_overlay(
        page,
        1,
        "0:00–0:12",
        "Stages complete only from persisted evidence",
        "Opening & empty 14-stage care journey (0 of 14 stages complete)",
    )

    # 0:00 - 0:02.5: Opening view on CareBridge portal
    rec.pad_to_video_time(2.5, page=page)

    # 0:02.5 - 0:07.82 (5.32s): Visible Patient login (first appearance of Patient)
    loginAs(
        "patient",
        pages,
        rec,
        scene_idx=1,
        timecode="0:00–0:12",
        caption="Stages complete only from persisted evidence",
        supporting="Opening & empty 14-stage care journey (0 of 14 stages complete)",
    )

    # 0:07.82 - 0:12.0: Patient dashboard showing empty 14-stage journey above the fold (0 of 14 Stages Complete)
    wait_for_page_ready(page)
    inject_overlay(
        page,
        1,
        "0:00–0:12",
        "Stages complete only from persisted evidence",
        "Opening & empty 14-stage care journey (0 of 14 stages complete)",
    )
    page.screenshot(path=str(SHOT_DIR / "scene1_empty_14_stage_journey.png"))
    page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_01_empty_14_stage_journey.png"))
    rec.pad_to_video_time(12.0, page=page)


# ==============================================================================
# SCENE 2 (0:12–0:40 = 28s) — Patient intake, coordinator task and notification
# ==============================================================================
def scene_2(pages: Dict[str, Page], rec: UnifiedPipeRecorder, live_case_id: str) -> None:
    print("\n>>> [0:12 - 0:40] SCENE 2: Patient Intake -> Coordinator Login (0:23-0:29) -> Task & Notification (28s)")
    p_page = switch_to_role(
        "patient",
        "/chat",
        pages,
        rec,
        scene_idx=2,
        timecode="0:12–0:40",
        caption="Stages complete only from persisted evidence",
        supporting="Patient screening request → Persisted coordinator task & notification",
    )
    rec.hold(1.0, page=p_page)

    # Patient submits screening request ONCE via UI -> triggers persisted task + coordinator notification
    type_and_submit_single_chat_turn(
        rec,
        p_page,
        "I need to schedule my routine mammogram screening. Can you help me?",
        type_duration_sec=2.8,
        stream_wait_sec=5.5,
    )
    p_page.screenshot(path=str(SHOT_DIR / "scene2_patient_screening_request_chat.png"))
    p_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_02a_patient_intake_single_reply.png"))
    # Land at exact 0:23.0 for Coordinator login
    rec.pad_to_video_time(23.0, page=p_page)

    # 0:23.0 - 0:28.32 (5.32s): Visible Coordinator login (first appearance of Care Coordinator)
    c_page = loginAs(
        "coordinator",
        pages,
        rec,
        scene_idx=2,
        timecode="0:12–0:40",
        caption="Stages complete only from persisted evidence",
        supporting="Patient screening request → Persisted coordinator task & notification",
    )
    wait_for_page_ready(c_page)
    inject_overlay(
        c_page,
        2,
        "0:12–0:40",
        "Stages complete only from persisted evidence",
        "Persisted coordinator task: Schedule Screening (Mammogram)",
    )
    c_page.screenshot(path=str(SHOT_DIR / "scene2_coordinator_task.png"))
    c_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_02b_coordinator_persisted_task.png"))
    rec.hold(5.5, page=c_page)

    # 0:33.8 - 0:40.0: Coordinator notifications page showing persisted screening request notification
    c_page.goto(f"{FRONTEND}/notifications", wait_until="domcontentloaded")
    wait_for_page_ready(c_page)
    inject_overlay(
        c_page,
        2,
        "0:12–0:40",
        "Stages complete only from persisted evidence",
        "Persisted coordinator notification: New Screening Request (Meera Krishnan)",
    )
    show_role_badge(c_page, "coordinator")
    c_page.screenshot(path=str(SHOT_DIR / "scene2_coordinator_notification.png"))
    c_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_02c_coordinator_notification.png"))
    rec.pad_to_video_time(40.0, page=c_page)


# ==============================================================================
# SCENE 3 (0:40–1:05 = 25s) — Screening performed and report finalized
# ==============================================================================
def scene_3(pages: Dict[str, Page], rec: UnifiedPipeRecorder, live_case_id: str) -> None:
    print("\n>>> [0:40 - 1:05] SCENE 3: Order Created (Stage 1 Pending) -> Performed (Stage 1 Green) -> PDF Upload -> Finalized (Stages 2 & 3 Green) (25s)")
    coord = get_auth_user("coordinator")
    headers = {"Authorization": f"Bearer {coord['token']}"}

    # Step 3A (0:40 - 0:46.5): Coordinator creates screening order -> Stage 1 remains PENDING
    sched_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    r_order = requests.post(
        f"{BACKEND}/cases/{live_case_id}/schedule-screening",
        headers=headers,
        json={
            "scheduled_time": sched_time,
            "facility": "Metropolitan Hospital Screening Center",
            "provider_name": "Bilateral Mammography Unit",
            "notes": "Screening order ORD-SCR created by Priya Nair, RN.",
        },
        timeout=10,
    )
    if r_order.status_code != 200:
        fail_scene("Scene 3 create screening order", f"HTTP {r_order.status_code}: {r_order.text}")

    p_page = switch_to_role(
        "patient",
        "/patient",
        pages,
        rec,
        scene_idx=3,
        timecode="0:40–1:05",
        caption="Stages complete only from persisted evidence",
        supporting="Screening order created → Stage 1 remains PENDING until procedure is performed",
        force_reload=True,
    )
    p_page.screenshot(path=str(SHOT_DIR / "scene3_01_order_created_stage1_pending.png"))
    p_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_03a_order_created_stage1_pending.png"))
    rec.pad_to_video_time(46.5, page=p_page)

    # Step 3B (0:46.5 - 0:53.0): Screening recorded as performed -> Stage 1 completes (turns green)
    r_perf = requests.post(
        f"{BACKEND}/cases/{live_case_id}/complete-screening",
        headers=headers,
        json={
            "completion_notes": "Bilateral digital diagnostic mammogram performed and verified at Metropolitan Hospital Screening Center."
        },
        timeout=10,
    )
    if r_perf.status_code != 200:
        fail_scene("Scene 3 record performed screening", f"HTTP {r_perf.status_code}: {r_perf.text}")

    p_page.evaluate("window.dispatchEvent(new Event('carebridge:data_updated'))")
    time.sleep(0.45)
    wait_for_page_ready(p_page)
    inject_overlay(
        p_page,
        3,
        "0:40–1:05",
        "Stages complete only from persisted evidence",
        "Screening recorded as performed → Stage 1 COMPLETED (1 of 14)",
    )
    p_page.screenshot(path=str(SHOT_DIR / "scene3_02_screening_performed_stage1_green.png"))
    p_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_03b_screening_performed_stage1_green.png"))
    rec.pad_to_video_time(53.0, page=p_page)

    # Step 3C (0:53.0 - 0:58.5): Coordinator uploads actual synthetic PDF report -> Stage 2 remains PENDING
    pdf_bytes = build_synthetic_pdf_bytes("CASE-2026-JUDGE01")
    r_up = requests.post(
        f"{BACKEND}/cases/{live_case_id}/upload-report-file",
        headers=headers,
        files={"file": ("CareBridge_Mammogram_Report_CASE-2026-JUDGE01.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        data={"screening_order_id": "ORD-SCR-JUDGE01", "screening_type": "Mammogram"},
        timeout=10,
    )
    if r_up.status_code != 200:
        fail_scene("Scene 3 upload synthetic PDF report", f"HTTP {r_up.status_code}: {r_up.text}")

    c_page = switch_to_role(
        "coordinator",
        f"/cases/{live_case_id}",
        pages,
        rec,
        scene_idx=3,
        timecode="0:40–1:05",
        caption="Stages complete only from persisted evidence",
        supporting="Synthetic PDF report uploaded (READY_TO_FINALIZE) → Stage 2 remains PENDING",
    )
    c_page.screenshot(path=str(SHOT_DIR / "scene3_03_pdf_uploaded_stage2_pending.png"))
    c_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_03c_pdf_uploaded_stage2_pending.png"))
    rec.pad_to_video_time(58.5, page=c_page)

    # Step 3D (0:58.5 - 1:05.0): Coordinator validates & finalizes report -> Stage 2 & Stage 3 turn green
    r_fin = requests.post(
        f"{BACKEND}/cases/{live_case_id}/finalize-report",
        headers=headers,
        json={
            "finding_code": "BI-RADS 4",
            "finding_summary": (
                "1.4 cm focal architectural distortion with clustered microcalcifications in the upper outer quadrant "
                "(BI-RADS 4 - Suspicious Abnormality)."
            ),
            "clinical_recommendation": "Targeted ultrasound and ultrasound-guided core needle biopsy within 14 days.",
            "disease_condition": "Breast Health",
            "urgency_level": "urgent",
            "requires_doctor_review": False,
        },
        timeout=10,
    )
    if r_fin.status_code != 200:
        fail_scene("Scene 3 finalize report", f"HTTP {r_fin.status_code}: {r_fin.text}")

    p_page = switch_to_role(
        "patient",
        "/patient",
        pages,
        rec,
        scene_idx=3,
        timecode="0:40–1:05",
        caption="Stages complete only from persisted evidence",
        supporting="Report validated & finalized → Stage 2 & Stage 3 COMPLETED (3 of 14)",
        force_reload=True,
    )
    p_page.screenshot(path=str(SHOT_DIR / "scene3_04_report_finalized_stage2_stage3_green.png"))
    p_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_03d_report_finalized_stage2_stage3_green.png"))
    rec.pad_to_video_time(65.0, page=p_page)


# ==============================================================================
# SCENE 4 (1:05–1:30 = 25s) — Patient receives and understands actual report through AI explanation
# ==============================================================================
def scene_4(pages: Dict[str, Page], rec: UnifiedPipeRecorder, live_case_id: str) -> None:
    print("\n>>> [1:05 - 1:30] SCENE 4: Patient Result Notification & Plain-Language AI Report Explanation (Stage 4) (25s)")
    # 1:05 - 1:10.5: Patient sees result notification on /notifications
    p_page = switch_to_role(
        "patient",
        "/notifications",
        pages,
        rec,
        scene_idx=4,
        timecode="1:05–1:30",
        caption="Stages complete only from persisted evidence",
        supporting="Stage 3 — Patient receives finalized diagnostic report notification",
    )
    p_page.screenshot(path=str(SHOT_DIR / "scene4_01_patient_result_notification.png"))
    p_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_04a_patient_result_notification.png"))
    rec.pad_to_video_time(70.5, page=p_page)

    # 1:10.5 - 1:24.0: Patient asks AI to explain her finalized report in /chat
    p_page = switch_to_role(
        "patient",
        "/chat",
        pages,
        rec,
        scene_idx=4,
        timecode="1:05–1:30",
        caption="Stages complete only from persisted evidence",
        supporting="AI explains actual finalized BI-RADS 4 report in plain language (Stage 4)",
    )
    # Start a clean chat view for the report explanation
    try:
        new_chat_btn = p_page.locator("button:has-text('New Chat')")
        if new_chat_btn.count() > 0:
            new_chat_btn.first.click()
            time.sleep(0.2)
    except Exception:
        pass

    type_and_submit_single_chat_turn(
        rec,
        p_page,
        "Can you explain my report in plain language?",
        type_duration_sec=2.4,
        stream_wait_sec=9.5,
    )
    p_page.screenshot(path=str(SHOT_DIR / "scene4_02_ai_report_explanation.png"))
    p_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_04b_ai_report_explanation.png"))
    rec.pad_to_video_time(84.0, page=p_page)

    # 1:24.0 - 1:30.0: Patient dashboard shows Stage 4 completed (4 of 14 Stages Complete)
    p_page = switch_to_role(
        "patient",
        "/patient",
        pages,
        rec,
        scene_idx=4,
        timecode="1:05–1:30",
        caption="Stages complete only from persisted evidence",
        supporting="Stage 4 COMPLETED — Report explanation persisted & delivered (4 of 14)",
        force_reload=True,
    )
    p_page.screenshot(path=str(SHOT_DIR / "scene4_03_stage4_completed.png"))
    p_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_04c_stage4_completed_on_dashboard.png"))
    rec.pad_to_video_time(90.0, page=p_page)


# ==============================================================================
# SCENE 5 (1:30–1:50 = 20s) — Natural, contextual patient AI conversation
# ==============================================================================
def scene_5(pages: Dict[str, Page], rec: UnifiedPipeRecorder, live_case_id: str) -> None:
    print("\n>>> [1:30 - 1:50] SCENE 5: Natural, Contextual Patient AI Conversation (20s)")
    p_page = switch_to_role(
        "patient",
        "/chat",
        pages,
        rec,
        scene_idx=5,
        timecode="1:30–1:50",
        caption="Stages complete only from persisted evidence",
        supporting="Case-aware patient AI conversation — single persisted response",
    )
    try:
        new_chat_btn = p_page.locator("button:has-text('New Chat')")
        if new_chat_btn.count() > 0:
            new_chat_btn.first.click()
            time.sleep(0.2)
    except Exception:
        pass
    inject_overlay(
        p_page,
        5,
        "1:30–1:50",
        "Stages complete only from persisted evidence",
        "Case-aware patient AI conversation — single persisted response",
    )
    rec.hold(1.0, page=p_page)

    # Natural greeting + case-aware question in one clean turn (no duplicate submission)
    type_and_submit_single_chat_turn(
        rec,
        p_page,
        "Where am I in my care journey right now, and what happens next with Dr. Arjun Menon?",
        type_duration_sec=3.2,
        stream_wait_sec=9.0,
    )
    p_page.screenshot(path=str(SHOT_DIR / "scene5_natural_contextual_conversation.png"))
    p_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_05_natural_contextual_ai_chat.png"))
    rec.pad_to_video_time(110.0, page=p_page)


# ==============================================================================
# SCENE 6 (1:50–2:25 = 35s) — Doctor review, referral acceptance, appointment and consultation
# ==============================================================================
def scene_6(pages: Dict[str, Page], rec: UnifiedPipeRecorder, live_case_id: str) -> None:
    print("\n>>> [1:50 - 2:25] SCENE 6: Doctor Review, Referral Acceptance, Dual-Confirmed v1 Appointment & Consultation (35s)")
    label_s6 = "Stages 5–13 — Doctor review · Referral accepted · v1 Appointment · Consultation"

    # Persist real clinical review (Stages 5 & 6), accepted referral (Stages 7 & 8),
    # and dual-confirmed same-version appointment (version=1, Stage 9) on live_case_id
    with get_sync_db() as db:
        cid = uuid.UUID(live_case_id)
        cc = db.query(CareCase).filter(CareCase.id == cid).first()
        patient_id = cc.patient_id
        patient_user = db.query(User).filter(User.email == "patient@carebridge.com").first()
        coord_user = db.query(User).filter(User.email == "coordinator@carebridge.com").first()
        doctor_user = db.query(User).filter(User.email == "doctor@carebridge.com").first()

        # Stages 5 & 6: Doctor clinical review
        LifecycleService.record_clinical_review(
            db=db,
            case_id=cid,
            doctor_id=str(doctor_user.owner_id or doctor_user.id),
            doctor_name="Dr. Arjun Menon, MD",
            clinical_assessment=(
                "Reviewed bilateral diagnostic mammogram (BI-RADS 4, 1.4 cm focal architectural distortion). "
                "Approved specialist referral and ultrasound-guided core needle biopsy."
            ),
            approved_pathway="Breast Surgical Oncology & Diagnostic Biopsy Pathway",
            patient_safe_explanation=(
                "Dr. Arjun Menon, MD has reviewed your finalized report and approved a specialist biopsy appointment for complete clarity."
            ),
            referral_approved=True,
        )

        # Stages 7 & 8: Create & accept specialist referral
        ref = Referral(
            id=uuid.uuid4(),
            case_id=cid,
            patient_id=patient_id,
            referring_provider="Metropolitan Hospital Screening Center",
            target_facility="Metropolitan Specialty Breast & Diagnostic Clinic",
            specialty="Breast Surgical Oncology & Diagnostic Biopsy",
            reason_for_referral="Urgent BI-RADS 4 diagnostic biopsy evaluation.",
            clinical_rationale="Accepted by Dr. Arjun Menon, MD for targeted ultrasound-guided core biopsy.",
            status="sent",
            acceptance_deadline=datetime.now(timezone.utc) + timedelta(days=2),
        )
        db.add(ref)
        db.commit()

        LifecycleService.advance_stage(
            db=db,
            case_id=cid,
            stage_ident=7,
            actor_role="care_coordinator",
            actor_id=str(coord_user.id),
            actor_name="Priya Nair, RN",
            evidence={"referral_id": str(ref.id), "status": "sent"},
            notes="Specialist referral transmitted to Metropolitan Specialty Breast & Diagnostic Clinic.",
        )
        LifecycleService.accept_referral(
            db=db,
            referral_id=ref.id,
            receiving_provider_name="Dr. Arjun Menon, MD",
            acceptance_notes="Referral accepted by Dr. Arjun Menon, MD within SLA.",
        )

        # Stage 9: Propose appointment v1 and confirm the SAME version (v1) by both Doctor and Patient
        appt_obj = AppointmentService.create_appointment_proposal(
            db=db,
            case_id=cid,
            patient_id=patient_id,
            facility="Metropolitan Specialty Breast & Diagnostic Clinic",
            provider_name="Dr. Arjun Menon, MD",
            appointment_type="diagnostic_biopsy",
            scheduled_time=datetime.now(timezone.utc) + timedelta(days=2, hours=3),
            proposed_by_role="care_coordinator",
            proposed_by_id=str(coord_user.id),
            notes="Dual-confirmed v1 specialist consultation & core biopsy with Dr. Arjun Menon, MD.",
        )
        db.commit()
        AppointmentService.confirm_appointment(
            db=db, appointment_id=appt_obj.id, actor_role="doctor", actor_id=str(doctor_user.id), version=1
        )
        AppointmentService.confirm_appointment(
            db=db, appointment_id=appt_obj.id, actor_role="patient", actor_id=str(patient_user.id), version=1
        )

    # 1:50 - 1:56.5: Coordinator Referrals page showing accepted referral (Stages 7 & 8)
    c_page = switch_to_role(
        "coordinator",
        "/referrals",
        pages,
        rec,
        scene_idx=6,
        timecode="1:50–2:25",
        caption="Stages complete only from persisted evidence",
        supporting="Stages 7–8 — Specialist referral created & accepted by Dr. Arjun Menon, MD",
        force_reload=True,
    )
    c_page.screenshot(path=str(SHOT_DIR / "scene6_01_referral_accepted.png"))
    c_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_06a_referral_accepted.png"))
    rec.pad_to_video_time(116.5, page=c_page)

    # 1:56.5 - 2:03.0: Coordinator Appointments page showing dual-confirmed v1 appointment (Stage 9)
    c_page = switch_to_role(
        "coordinator",
        "/appointments",
        pages,
        rec,
        scene_idx=6,
        timecode="1:50–2:25",
        caption="Stages complete only from persisted evidence",
        supporting="Stage 9 — Doctor & Patient confirmed the same appointment version (v1)",
        force_reload=True,
    )
    c_page.screenshot(path=str(SHOT_DIR / "scene6_02_appointment_v1_dual_confirmed.png"))
    c_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_06b_appointment_v1_dual_confirmed.png"))
    rec.pad_to_video_time(123.0, page=c_page)

    # 2:03.0 - 2:08.32 (5.32s): Visible Doctor login (first appearance of Doctor)
    d_page = loginAs(
        "doctor",
        pages,
        rec,
        scene_idx=6,
        timecode="1:50–2:25",
        caption="Stages complete only from persisted evidence",
        supporting=label_s6,
    )

    # Record Stage 10 consultation outcome, Stage 11 treatment monitoring, Stage 12 follow-up, Stage 13 checklist
    with get_sync_db() as db:
        cid = uuid.UUID(live_case_id)
        doctor_user = db.query(User).filter(User.email == "doctor@carebridge.com").first()
        LifecycleService.record_consultation_outcome(
            db=db,
            case_id=cid,
            doctor_id=str(doctor_user.owner_id or doctor_user.id),
            doctor_name="Dr. Arjun Menon, MD",
            consultation_notes="Patient attended diagnostic biopsy consultation; ultrasound-guided core biopsy completed.",
            biopsy_pathology_outcome="Benign fibroadenoma with stromal fibrosis; negative for malignancy.",
            clinical_recommendations="Routine annual screening mammogram; no surgical intervention needed.",
            treatment_plan="Benign pathology concordance verified; annual breast surveillance plan established.",
            next_followup_date=(datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%d"),
        )
        LifecycleService.record_treatment_update(
            db=db,
            case_id=cid,
            sender_role="care_coordinator",
            message="Patient counselled on benign biopsy pathology and annual surveillance plan.",
            category="adherence",
        )
        LifecycleService.record_followup_status(
            db=db,
            case_id=cid,
            status="completed",
            notes="Post-biopsy follow-up completed; patient questions answered.",
            actor_role="doctor",
        )
        LifecycleService.verify_documentation_checklist(db, cid)

    wait_for_page_ready(d_page)
    inject_overlay(
        d_page,
        6,
        "1:50–2:25",
        "Stages complete only from persisted evidence",
        "Stages 5–6 & 10 — Doctor clinical review and biopsy consultation recorded",
    )
    d_page.screenshot(path=str(SHOT_DIR / "scene6_03_doctor_review_and_consultation.png"))
    d_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_06c_doctor_review_and_consultation.png"))
    rec.pad_to_video_time(137.0, page=d_page)

    # 2:17.0 - 2:25.0: Doctor views Case Detail showing timeline events, accepted referral & appointment (Stages 10-13 complete)
    d_page = switch_to_role(
        "doctor",
        f"/cases/{live_case_id}",
        pages,
        rec,
        scene_idx=6,
        timecode="1:50–2:25",
        caption="Stages complete only from persisted evidence",
        supporting="Stages 10–13 — Consultation, follow-up & 10-point documentation checklist verified",
        force_reload=True,
    )
    d_page.screenshot(path=str(SHOT_DIR / "scene6_04_case_evidence_ready_for_closure.png"))
    d_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_06d_case_detail_before_closure.png"))
    rec.pad_to_video_time(145.0, page=d_page)


# ==============================================================================
# SCENE 7 (2:25–2:42 = 17s) — Coordinator closure restriction followed by doctor-authorized closure
# ==============================================================================
def scene_7(pages: Dict[str, Page], rec: UnifiedPipeRecorder, live_case_id: str) -> None:
    print("\n>>> [2:25 - 2:42] SCENE 7: Coordinator Closure Restriction (403) -> Doctor-Authorized Closure (14/14) (17s)")
    coord = get_auth_user("coordinator")
    doctor = get_auth_user("doctor")

    # 1. Execute real backend call as Coordinator to verify HTTP 403 Forbidden
    r_403 = requests.post(
        f"{BACKEND}/cases/{live_case_id}/clinical-closure",
        headers={"Authorization": f"Bearer {coord['token']}"},
        json={
            "clinical_rationale": "Coordinator attempting closure.",
            "evidence_summary": "Attempted by coordinator.",
        },
        timeout=10,
    )
    if r_403.status_code != 403:
        fail_scene("Scene 7 coordinator closure restriction", f"Expected HTTP 403, got {r_403.status_code}")

    # 2:25.0 - 2:30.5: Show Coordinator blocked by 403 ONCE
    c_page = switch_to_role(
        "coordinator",
        f"/cases/{live_case_id}",
        pages,
        rec,
        scene_idx=7,
        timecode="2:25–2:42",
        caption="Stages complete only from persisted evidence",
        supporting="Role boundary enforced: Care Coordinator blocked from doctor-only closure (HTTP 403)",
    )
    c_page.evaluate(
        """(detailMsg) => {
            let old = document.getElementById('demo-403-modal');
            if (old) old.remove();
            let modal = document.createElement('div');
            modal.id = 'demo-403-modal';
            modal.style.position = 'fixed';
            modal.style.top = '0';
            modal.style.left = '0';
            modal.style.width = '100vw';
            modal.style.height = '100vh';
            modal.style.background = 'rgba(15, 23, 42, 0.72)';
            modal.style.backdropFilter = 'blur(8px)';
            modal.style.zIndex = '999999';
            modal.style.display = 'flex';
            modal.style.alignItems = 'center';
            modal.style.justifyContent = 'center';
            modal.innerHTML = `
                <div style="background: white; border: 2px solid #EF4444; border-radius: 16px; padding: 26px 34px; max-width: 520px; box-shadow: 0 25px 50px rgba(0,0,0,0.3); text-align: center;">
                    <div style="width: 52px; height: 52px; background: #FEE2E2; color: #DC2626; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 14px; font-size: 26px; font-weight: 800;">
                        ✕
                    </div>
                    <div style="font-size: 12px; font-weight: 800; color: #DC2626; letter-spacing: 0.08em; text-transform: uppercase;">
                        HTTP 403 Forbidden • Role Restriction Enforced
                    </div>
                    <h3 style="font-size: 18px; font-weight: 800; color: #0F172A; margin: 8px 0;">
                        Physician Closure Authority Required
                    </h3>
                    <p style="font-size: 13px; color: #475569; line-height: 1.5; margin: 0 0 18px;">
                        ${detailMsg}
                    </p>
                    <div style="display: inline-block; background: #F1F5F9; border: 1px solid #CBD5E1; color: #334155; font-size: 11px; font-weight: 600; padding: 6px 14px; border-radius: 6px;">
                        Level 3 Human Physician Governance Gate
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }""",
        r_403.json().get("detail", "Forbidden: Only an authorized physician/clinician may execute clinical closure sign-off."),
    )
    c_page.screenshot(path=str(SHOT_DIR / "scene7_01_coordinator_blocked_403.png"))
    c_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_07a_coordinator_403_once.png"))
    rec.pad_to_video_time(150.5, page=c_page)
    c_page.evaluate("() => { let m = document.getElementById('demo-403-modal'); if (m) m.remove(); }")

    # 2. Execute real Doctor-authorized clinical closure via backend endpoint
    r_close = requests.post(
        f"{BACKEND}/cases/{live_case_id}/clinical-closure",
        headers={"Authorization": f"Bearer {doctor['token']}"},
        json={
            "clinical_rationale": (
                "Benign fibroadenoma confirmed on core biopsy pathology; 10-point documentation checklist, "
                "accepted referral, dual-confirmed appointment, and patient follow-up verified complete."
            ),
            "evidence_summary": "All 14 longitudinal care stages verified from persisted PostgreSQL evidence.",
        },
        timeout=10,
    )
    if r_close.status_code != 200:
        fail_scene("Scene 7 doctor authorized closure", f"HTTP {r_close.status_code}: {r_close.text}")

    # 2:30.5 - 2:36.5: Doctor view of closed case with full timeline events (30+ Events Logged) & accepted referral
    d_page = switch_to_role(
        "doctor",
        f"/cases/{live_case_id}",
        pages,
        rec,
        scene_idx=7,
        timecode="2:25–2:42",
        caption="Stages complete only from persisted evidence",
        supporting="Stage 14 — Doctor-authorized closure with full timeline events & accepted referral",
        force_reload=True,
    )
    d_page.reload(wait_until="domcontentloaded")
    wait_for_page_ready(d_page)
    inject_overlay(
        d_page,
        7,
        "2:25–2:42",
        "Stages complete only from persisted evidence",
        "Stage 14 — Doctor-authorized closure with full timeline events & accepted referral",
    )
    show_role_badge(d_page, "doctor")
    d_page.screenshot(path=str(SHOT_DIR / "scene7_02_doctor_authorized_closure_with_evidence.png"))
    d_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_07b_doctor_closed_case_with_events_and_referral.png"))
    rec.pad_to_video_time(156.5, page=d_page)

    # 2:36.5 - 2:42.0: Patient dashboard showing 14 of 14 Stages Complete (all 14 stage cards green)
    p_page = switch_to_role(
        "patient",
        "/patient",
        pages,
        rec,
        scene_idx=7,
        timecode="2:25–2:42",
        caption="Stages complete only from persisted evidence",
        supporting="14 of 14 Stages Complete • Verified Clinical Closure",
        force_reload=True,
    )
    p_page.screenshot(path=str(SHOT_DIR / "scene7_03_patient_14_of_14_complete.png"))
    p_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_07c_patient_14_of_14_complete.png"))
    rec.pad_to_video_time(162.0, page=p_page)


# ==============================================================================
# SCENE 8 (2:42–2:50 = 8s) — Patient, doctor and coordinator dashboards and closing screen
# ==============================================================================
def scene_8(pages: Dict[str, Page], rec: UnifiedPipeRecorder) -> None:
    print("\n>>> [2:42 - 2:50] SCENE 8: Patient, Doctor & Coordinator Dashboards & Closing Screen (8s)")
    label_s8 = "CareBridge · Team Ai_Mavericks · Future Health Digital Innovation Challenge"

    # 2:42.0 - 2:44.0: Patient dashboard
    p_page = switch_to_role(
        "patient", "/patient", pages, rec, 8, "2:42–2:50", "Stages complete only from persisted evidence", label_s8
    )
    p_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_08a_patient_dashboard.png"))
    rec.pad_to_video_time(164.0, page=p_page)

    # 2:44.0 - 2:46.0: Doctor dashboard
    d_page = switch_to_role(
        "doctor", "/doctor", pages, rec, 8, "2:42–2:50", "Stages complete only from persisted evidence", label_s8, force_reload=True
    )
    d_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_08b_doctor_dashboard.png"))
    rec.pad_to_video_time(166.0, page=d_page)

    # 2:46.0 - 2:47.8: Coordinator dashboard
    c_page = switch_to_role(
        "coordinator", "/coordinator", pages, rec, 8, "2:42–2:50", "Stages complete only from persisted evidence", label_s8, force_reload=True
    )
    c_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_08c_coordinator_dashboard.png"))
    rec.pad_to_video_time(167.8, page=c_page)

    # 2:47.8 - 2:50.0: Final closing brand slate
    c_page.evaluate(
        """() => {
            let slate = document.createElement('div');
            slate.style.position = 'fixed';
            slate.style.top = '0';
            slate.style.left = '0';
            slate.style.width = '100vw';
            slate.style.height = '100vh';
            slate.style.background = 'linear-gradient(135deg, #042F2E 0%, #0F172A 100%)';
            slate.style.zIndex = '99999999';
            slate.style.display = 'flex';
            slate.style.flexDirection = 'column';
            slate.style.alignItems = 'center';
            slate.style.justifyContent = 'center';
            slate.style.color = '#FFFFFF';
            slate.style.fontFamily = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
            slate.style.textAlign = 'center';
            slate.innerHTML = `
                <div style="width: 72px; height: 72px; background: #0F766E; border-radius: 20px; display: flex; align-items: center; justify-content: center; margin-bottom: 24px; box-shadow: 0 10px 30px rgba(15, 118, 110, 0.5);">
                    <span style="font-size: 36px; font-weight: 800; color: #FFFFFF;">CB</span>
                </div>
                <h1 style="font-size: 44px; font-weight: 800; letter-spacing: -0.02em; margin: 0 0 8px; color: #FFFFFF;">
                    CareBridge
                </h1>
                <p style="font-size: 18px; font-weight: 600; color: #2DD4BF; margin: 0 0 32px; letter-spacing: 0.05em; text-transform: uppercase;">
                    Closing the Screening-to-Care Loop
                </p>
                <div style="background: rgba(255, 255, 255, 0.07); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 12px; padding: 18px 36px; max-width: 620px; margin-bottom: 28px;">
                    <div style="font-size: 14px; color: #94A3B8; margin-bottom: 6px;">
                        Future Health Digital Innovation Challenge
                    </div>
                    <div style="font-size: 22px; font-weight: 800; color: #F8FAFC;">
                        Team: Ai_Mavericks
                    </div>
                </div>
                <p style="font-size: 13px; color: #94A3B8; margin: 0;">
                    Patient, Doctor & Care Coordinator share one PostgreSQL-backed workflow • English, Arabic, Spanish • Synthetic data only
                </p>
            `;
            document.body.appendChild(slate);
        }"""
    )
    c_page.screenshot(path=str(SHOT_DIR / "scene8_closing_slate.png"))
    c_page.screenshot(path=str(SCENE_VERIFY_DIR / "scene_08d_closing_slate.png"))
    rec.pad_to_video_time(170.0, page=c_page)


def mux_video_and_audio(raw_video: Path, audio_wav: Path, final_mp4: Path, final_webm: Path) -> None:
    """Muxes the 170.0s video stream with the synchronized narration + low-volume background music WAV track."""
    # 1. Export primary MP4 (H.264 video + AAC 192kbps audio)
    subprocess.run(
        [
            FFMPEG_FULL_BIN,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(raw_video),
            "-i",
            str(audio_wav),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(final_mp4),
        ],
        check=True,
    )

    # 2. Export WebM copy (VP8 video + Vorbis/Opus audio) for browser compatibility
    subprocess.run(
        [
            FFMPEG_FULL_BIN,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(raw_video),
            "-i",
            str(audio_wav),
            "-c:v",
            "libvpx",
            "-deadline",
            "realtime",
            "-cpu-used",
            "4",
            "-b:v",
            "2500k",
            "-c:a",
            "libvorbis",
            "-b:a",
            "160k",
            "-shortest",
            str(final_webm),
        ],
        check=True,
    )


def probe_media_streams(media_path: Path) -> str:
    res = subprocess.run([FFMPEG_FULL_BIN, "-i", str(media_path)], capture_output=True, text=True)
    info_lines = []
    for line in res.stderr.splitlines():
        s = line.strip()
        if s.startswith("Duration:") or s.startswith("Stream #"):
            info_lines.append(s)
    return "\n  ".join(info_lines)


def main() -> None:
    if FAILED_SCENES_PATH.exists():
        FAILED_SCENES_PATH.unlink()

    # 1. Prepare clean database state (0/14 stages on CASE-2026-JUDGE01, repair closed cases, remove duplicate comms)
    with get_sync_db() as db:
        removed_dups = deduplicate_communications(db)
        repaired_closed = repair_closed_cases(db)
        judge_info = reset_judge_case_for_scene_1(db)
        live_case_id = judge_info["case_id"]
        print(
            f"[DB_PREP] Deduplicated comms={removed_dups}, repaired closed cases={repaired_closed}, "
            f"reset {judge_info['case_number']} ({live_case_id}) to 0/14 stages."
        )

    # 2. Build synchronized narration + low-volume background music soundtrack
    soundtrack_wav = build_master_soundtrack()

    raw_video_mp4 = VIDEO_DIR / "_raw_video_stream.mp4"
    final_mp4 = VIDEO_DIR / "CareBridge_Final_Demo_Ai_Mavericks.mp4"
    cinematic_mp4 = VIDEO_DIR / "CareBridge_Cinematic_Demo_Final.mp4"
    final_webm = VIDEO_DIR / "CareBridge_Cinematic_Demo_Final.webm"
    submission_webm = VIDEO_DIR / "CareBridge_Demo_Video_Ai_Mavericks.webm"

    print("==================================================================")
    print(" CareBridge Final Demo Video Recorder (Exact 2:50 / 170.0s)")
    print(" Team: Ai_Mavericks | Challenge: Future Health")
    print(f" Case ID: {live_case_id} (CASE-2026-JUDGE01)")
    print("==================================================================")

    rec = UnifiedPipeRecorder(raw_video_mp4, fps=FPS)

    with sync_playwright() as pw:
        browser: Browser = pw.chromium.launch(headless=True)
        contexts: Dict[str, BrowserContext] = {
            "patient": browser.new_context(viewport={"width": 1280, "height": 800}),
            "coordinator": browser.new_context(viewport={"width": 1280, "height": 800}),
            "doctor": browser.new_context(viewport={"width": 1280, "height": 800}),
        }
        pages: Dict[str, Page] = {role: ctx.new_page() for role, ctx in contexts.items()}

        scene_1(pages, rec)
        scene_2(pages, rec, live_case_id)
        scene_3(pages, rec, live_case_id)
        scene_4(pages, rec, live_case_id)
        scene_5(pages, rec, live_case_id)
        scene_6(pages, rec, live_case_id)
        scene_7(pages, rec, live_case_id)
        scene_8(pages, rec)

        rec.close()
        for p in pages.values():
            p.close()
        for c in contexts.values():
            c.close()
        browser.close()

    print("\n[MUX] Mixing H.264 video stream with synchronized narration + low-volume background music...")
    mux_video_and_audio(raw_video_mp4, soundtrack_wav, final_mp4, final_webm)
    shutil.copy2(final_mp4, cinematic_mp4)
    shutil.copy2(final_webm, submission_webm)
    if raw_video_mp4.exists():
        raw_video_mp4.unlink()

    mp4_info = probe_media_streams(final_mp4)
    webm_info = probe_media_streams(final_webm)

    print("\n==================================================================")
    print(" ✅ FINAL DEMO VIDEO RECORDING, AUDIO MUXING & VERIFICATION DONE!")
    print(f" Primary MP4 Output:    {final_mp4}")
    print(f"  {mp4_info}")
    print(f" Primary WebM Output:   {final_webm}")
    print(f"  {webm_info}")
    print(f" Scene Verification:    {SCENE_VERIFY_DIR}")
    print("==================================================================")


if __name__ == "__main__":
    main()
