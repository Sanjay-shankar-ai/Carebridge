"""
CareBridge Synchronized Narration + Low-Volume Background Music Generator (Part D).

Generates an exact 170.0-second (2:50) 44.1 kHz 16-bit PCM WAV soundtrack:
  demo_assets/audio/CareBridge_Final_Soundtrack_2m50s.wav

1. Uses the approved narration lines from demo_assets/narration_transcript.txt,
   time-aligned to the exact 8-scene storyboard timestamps:
     - Scene 1 (0:00–0:12): Opening & empty 14-stage journey (Patient login 0:03–0:08.3)
     - Scene 2 (0:12–0:40): Patient intake -> Coordinator login (0:23–0:28.3) -> Task & notification
     - Scene 3 (0:40–1:05): Screening order (Stage 1 pending) -> Performed (Stage 1 green) -> PDF upload (Stage 2 pending) -> Finalized (Stage 2 & 3 green)
     - Scene 4 (1:05–1:30): Patient receives result notification & understands actual report via AI explanation (Stage 4 green)
     - Scene 5 (1:30–1:50): Natural, contextual patient AI conversation
     - Scene 6 (1:50–2:25): Doctor review (Doctor login 2:03–2:08.3), referral acceptance, dual-confirmed appointment (same version v1) & consultation
     - Scene 7 (2:25–2:42): Coordinator closure restriction (403 once) followed by doctor-authorized closure (14/14 with events & referrals)
     - Scene 8 (2:42–2:50): Patient, doctor and coordinator dashboards & closing screen
2. Mixes a warm, low-volume ambient background pad (-26 dB, automatically ducked -32 dB under voice)
   so narration remains crisp and clear throughout.
"""

import array
import math
import subprocess
import wave
from pathlib import Path

OUT_DIR = Path("c:/CareBridge/demo_assets/audio")
CUES_DIR = OUT_DIR / "cues"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CUES_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_RATE = 44100
TOTAL_SECONDS = 170.0
TOTAL_SAMPLES = int(SAMPLE_RATE * TOTAL_SECONDS)

# Approved narration lines synchronized to exact scene action timestamps (seconds)
NARRATION_CUES = [
    # Scene 1: 0:00 - 0:12 (Opening, Patient login, empty 14-stage journey)
    (
        0.4,
        "s1_open",
        "A screening journey is only complete when care happens. This is CareBridge — closing the screening to care loop.",
    ),
    (
        6.5,
        "s1_journey",
        "The patient signs in to her empty fourteen-stage care pathway, where every stage completes only from persisted evidence.",
    ),
    # Scene 2: 0:12 - 0:40 (Patient intake, Coordinator login at 0:23, persisted task & notification)
    (
        12.5,
        "s2_intake",
        "She speaks naturally with the role-aware AI assistant, which captures her screening need and creates a real task for the Care Coordinator.",
    ),
    (
        23.5,
        "s2_coord",
        "The Care Coordinator signs in. Watch the coordinator task and notification arrive — from a persisted database record, not from a chat promise.",
    ),
    # Scene 3: 0:40 - 1:05 (Screening order pending -> performed green; PDF upload pending -> finalized green)
    (
        40.4,
        "s3_order",
        "The coordinator creates the screening order. Notice Stage One remains pending: an order alone is not proof that screening took place.",
    ),
    (
        48.5,
        "s3_performed",
        "Once the performed screening is recorded, Stage One turns green. Next, the coordinator uploads the actual synthetic PDF report.",
    ),
    (
        56.8,
        "s3_finalized",
        "Upload alone does not complete Stage Two. Only after the report is validated and finalized do Stage Two and Stage Three complete.",
    ),
    # Scene 4: 1:05 - 1:30 (Patient receives notification & understands actual report through AI explanation)
    (
        65.5,
        "s4_notif",
        "The patient receives her result notification and asks what the finalized BI-RADS Four report means.",
    ),
    (
        74.0,
        "s4_explain",
        "The assistant retrieves the actual finalized report and explains it in clear, plain language without diagnosing.",
    ),
    (
        82.5,
        "s4_stage4",
        "Delivery of that persisted explanation is recorded as evidence to complete Stage Four.",
    ),
    # Scene 5: 1:30 - 1:50 (Natural, contextual patient AI conversation)
    (
        90.5,
        "s5_convo1",
        "In a natural follow-up conversation, the patient asks where she is in her care journey and what happens next with her doctor.",
    ),
    (
        100.0,
        "s5_convo2",
        "Using her authorized case context, the AI answers directly with one persisted response — never repeating or inventing clinical facts.",
    ),
    # Scene 6: 1:50 - 2:25 (Doctor review, referral acceptance, same-version appointment confirmation, consultation)
    (
        110.5,
        "s6_ref_appt",
        "A specialist referral is created and accepted. Stage Nine turns green only after both doctor and patient confirm the exact same appointment version.",
    ),
    (
        123.5,
        "s6_doc_login",
        "Doctor Arjun Menon signs in, reviews the diagnostic findings, and records the clinical decision and biopsy consultation outcome.",
    ),
    (
        136.0,
        "s6_followup",
        "Stage Ten completes, and treatment monitoring, follow-up, and the ten-point documentation checklist advance from persisted records.",
    ),
    # Scene 7: 2:25 - 2:42 (Coordinator closure restriction 403 -> Doctor-authorized closure 14/14)
    (
        145.4,
        "s7_boundary",
        "Now test the role boundary: the Care Coordinator attempts to close the case and is blocked.",
    ),
    (
        151.8,
        "s7_closure",
        "Only an authorized doctor can sign off clinical closure — completing fourteen of fourteen stages with full timeline events and referral evidence.",
    ),
    # Scene 8: 2:42 - 2:50 (Patient, doctor and coordinator dashboards & closing screen)
    (
        162.2,
        "s8_close",
        "Patient, doctor, and care coordinator share one PostgreSQL-backed workflow. Synthetic data only. Team Ai Mavericks.",
    ),
]


def synthesize_cues_with_sapi() -> None:
    """Uses Windows System.Speech.Synthesis via a PowerShell script file to render 44.1kHz mono WAV cues."""
    ps1_path = CUES_DIR / "render_cues.ps1"
    lines = [
        "Add-Type -AssemblyName System.Speech",
        "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer",
        "$synth.Rate = 1",
        "$synth.Volume = 100",
        "foreach ($v in $synth.GetInstalledVoices()) {",
        "    if ($v.VoiceInfo.Name -match 'Zira|Hazel|Aria|Jenny|David') {",
        "        $synth.SelectVoice($v.VoiceInfo.Name)",
        "        break",
        "    }",
        "}",
        "$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(44100, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)",
    ]
    for _, cue_id, text in NARRATION_CUES:
        wav_path = (CUES_DIR / f"{cue_id}.wav").resolve()
        safe_text = text.replace("'", "''")
        lines.append(f"$synth.SetOutputToWaveFile('{wav_path}', $fmt)")
        lines.append(f"$synth.Speak('{safe_text}')")
    lines.append("$synth.SetOutputToNull()")
    lines.append("$synth.Dispose()")
    ps1_path.write_text("\n".join(lines), encoding="utf-8")

    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1_path)],
        check=True,
    )


def build_master_soundtrack() -> Path:
    synthesize_cues_with_sapi()

    # Initialize master buffer with low-volume ambient harmonic pad (C major9 / F major7 gentle progression)
    master = array.array("h", [0] * TOTAL_SAMPLES)
    voice_mask = bytearray(TOTAL_SAMPLES)

    # First load and place all voice cues onto master buffer and mark voice_mask for ducking
    prev_end_sec = 0.0
    for start_sec, cue_id, _ in NARRATION_CUES:
        wav_path = CUES_DIR / f"{cue_id}.wav"
        if not wav_path.exists():
            continue
        with wave.open(str(wav_path), "rb") as wf:
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
            samples = array.array("h")
            samples.frombytes(raw)

        # Trim trailing silence from SAPI cue
        while len(samples) > 1000 and abs(samples[-1]) < 120:
            samples.pop()

        effective_start_sec = max(start_sec, prev_end_sec + 0.35)
        start_idx = int(effective_start_sec * SAMPLE_RATE)
        dur_sec = len(samples) / float(SAMPLE_RATE)
        prev_end_sec = effective_start_sec + dur_sec
        print(f"  [CUE] {cue_id:14s} @ {effective_start_sec:6.2f}s -> {prev_end_sec:6.2f}s ({dur_sec:.2f}s)")
        for i, val in enumerate(samples):
            idx = start_idx + i
            if 0 <= idx < TOTAL_SAMPLES:
                # Boost clarity slightly with soft limiter
                boosted = int(val * 1.05)
                if boosted > 30000:
                    boosted = 30000
                elif boosted < -30000:
                    boosted = -30000
                master[idx] = boosted
                voice_mask[idx] = 1

    # Add warm, low-volume ambient background music pad (ducked when voice_mask is active)
    # Two-chord ambient cycle every 8 seconds: Cmaj9 (130.81, 164.81, 196.00, 246.94, 293.66 Hz)
    # and Fmaj9 (174.61, 220.00, 261.63, 329.63, 392.00 Hz)
    chord_a = (130.81, 196.00, 246.94, 293.66, 329.63)
    chord_b = (174.61, 220.00, 261.63, 329.63, 392.00)
    two_pi = 2.0 * math.pi

    for idx in range(TOTAL_SAMPLES):
        t = idx / float(SAMPLE_RATE)
        # Smooth crossfade between chord_a and chord_b every 8.5s
        blend = 0.5 * (1.0 - math.cos(two_pi * t / 17.0))
        lfo = 0.85 + 0.15 * math.sin(two_pi * 0.25 * t)

        sig_a = (
            0.40 * math.sin(two_pi * chord_a[0] * t)
            + 0.25 * math.sin(two_pi * chord_a[1] * t)
            + 0.15 * math.sin(two_pi * chord_a[2] * t)
            + 0.12 * math.sin(two_pi * chord_a[3] * t)
            + 0.08 * math.sin(two_pi * chord_a[4] * t)
        )
        sig_b = (
            0.40 * math.sin(two_pi * chord_b[0] * t)
            + 0.25 * math.sin(two_pi * chord_b[1] * t)
            + 0.15 * math.sin(two_pi * chord_b[2] * t)
            + 0.12 * math.sin(two_pi * chord_b[3] * t)
            + 0.08 * math.sin(two_pi * chord_b[4] * t)
        )
        pad = ((1.0 - blend) * sig_a + blend * sig_b) * lfo

        # Global fade-in (first 1.5s) and fade-out (last 2.0s)
        env = 1.0
        if t < 1.5:
            env = t / 1.5
        elif t > TOTAL_SECONDS - 2.0:
            env = max(0.0, (TOTAL_SECONDS - t) / 2.0)

        # Low volume background music: amplitude ~950 (~-30 dBFS) during speech, ~1650 (~-25 dBFS) during pauses
        amp = 920.0 if voice_mask[idx] else 1600.0
        mixed = int(master[idx] + pad * amp * env)
        if mixed > 32760:
            mixed = 32760
        elif mixed < -32760:
            mixed = -32760
        master[idx] = mixed

    out_wav = OUT_DIR / "CareBridge_Final_Soundtrack_2m50s.wav"
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(master.tobytes())

    print(f"[AUDIO] Generated synchronized narration + low-volume music track: {out_wav} ({TOTAL_SECONDS:.2f}s)")
    return out_wav


if __name__ == "__main__":
    build_master_soundtrack()
