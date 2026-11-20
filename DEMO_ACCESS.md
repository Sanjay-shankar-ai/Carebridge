# CareBridge — Judge Demo Access & Evaluation Guide

This guide describes how to run and evaluate CareBridge closed-loop screening-to-care platform.

---

## 1. Quick Start & Setup

### Environment Variables
Configure the demo credentials in your environment or local `.env.demo` file:
```bash
DEMO_PATIENT_PASSWORD=<your_patient_password>
DEMO_DOCTOR_PASSWORD=<your_doctor_password>
DEMO_COORDINATOR_PASSWORD=<your_coordinator_password>
```
*(Passwords are never committed or printed).*

### Restore Starting State (Before Every Demo Run)
To ensure judges begin from a clean, known starting state:
```bash
python scripts/reset_judge_demo.py
```
This restores:
- **Meera Krishnan** (CASE-2026-JUDGE01): Stages 1..3 Completed, Stage 4 Pending, assigned to Dr. Arjun Menon.
- **Dr. Arjun Menon**: Breast Surgery / Oncology schedule with Mon/Wed/Fri availability for the next 4 weeks.
- **Rahul Das** (CASE-2026-UNASSIGNED01): New abnormal screening in the Coordinator intake queue.
- **3 Database Notifications** in patient, coordinator, and doctor inboxes.
- **Synthetic Mammogram Report PDF** in `backend/uploads/reports/`.

---

## 2. Seeded Demo Accounts

| Role | Name | Email (Login ID) | Starting State |
| :--- | :--- | :--- | :--- |
| **PATIENT** | Meera Krishnan (Age 46) | `meera.krishnan@carebridge.com` *(or `patient@carebridge.com`)* | Screening & report finalized (Stages 1–3 done). Stage 4 pending. |
| **DOCTOR** | Dr. Arjun Menon, MD | `arjun.menon@carebridge.com` *(or `doctor@carebridge.com`)* | Assigned breast surgical oncologist; Mon/Wed/Fri weekly calendar. |
| **CARE COORDINATOR** | Priya Nair, RN | `priya.nair@carebridge.com` *(or `coordinator@carebridge.com`)* | Active coordinator oversight; managing queue with unassigned patient Rahul Das. |

---

## 3. Recommended Judge Evaluation Walkthrough (Under 5 Minutes)

### Flow A: Patient Experience (Stage 4 AI Education & Appointment Booking)
1. **Log In** as Patient (`meera.krishnan@carebridge.com`).
2. **Review Homepage**: Note the notification banner indicating screening results are ready.
3. **Open AI Chat**:
   - The user lands on a clean, private chat interface for their role.
   - Click the suggested prompt: **"Explain my report"**.
4. **Observe Plain-Language Explanation**:
   - The AI explains the BI-RADS Category 4 finding with warmth and clinical boundaries (no robotic jargon, no cancer diagnosis, no false reassurance).
   - Once the explanation is delivered, **Stage 4 (AI Education & Understanding) advances to COMPLETED** in the database lifecycle engine.
5. **Book Consultation**:
   - Ask: *"What times is Dr. Menon available next week?"*
   - Observe real availability slots presented from Dr. Menon's Mon/Wed/Fri calendar.
   - Reply: *"Book the first option on Monday at 10:00 AM."*
   - AI reserves the appointment and dispatches confirmation to the care team.

---

### Flow B: Care Coordinator Oversight (Patients Area & Task Queue)
1. **Log In** as Care Coordinator (`priya.nair@carebridge.com`).
2. **Click "Patients"** in the sidebar navigation:
   - View multidimensional patient list: search, stage filters (1..14), SLA breach indicators.
   - Click the **"Needs My Action"** filter: Observe Rahul Das (Positive FIT screening) in the intake queue.
3. **Open Meera Krishnan's Case**:
   - View the 14-stage lifecycle timeline directly backed by PostgreSQL.
   - Note Stages 1, 2, 3, 4 marked complete with immutable evidence timestamps.
   - Observe Dr. Arjun Menon assigned as attending specialist.
4. **Report Upload & Verification**:
   - In any case requiring diagnostic evidence, test the **"Upload Report"** zone with drag-and-drop or file browser (supports PDF, PNG, JPG up to 10MB).
   - Review extracted metadata, clinical coding, and execute Stage 2 finalization.

---

### Flow C: Attending Physician Review & Sign-Off
1. **Log In** as Doctor (`arjun.menon@carebridge.com`).
2. **View Clinical Inbox**:
   - Observe assigned case notification for Meera Krishnan.
   - Review patient's question history and AI explanation transcript.
3. **Confirm Appointment & Clinical Plan**:
   - Doctor confirms the proposed Monday consultation slot.
   - Record clinical assessment and authorize care pathway.
4. **Clinical Closure Gate**:
   - Doctor is the sole authorized role permitted to execute Level 3 final clinical closure (Stage 14 sign-off).
   - Verification checklist validates all 10 clinical milestones before closure is permitted.

---

## 4. Resetting Data Between Demos
Whenever you want to run the demonstration again from the beginning:
```bash
python scripts/reset_judge_demo.py
```
This restores all records without needing server restarts or database drops.
