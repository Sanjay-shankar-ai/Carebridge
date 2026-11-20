#!/usr/bin/env python3
"""
CareBridge — Judge Demo Seeding Script (Idempotent)
Creates or updates the required judge demo cohort:
- PATIENT: "Meera Krishnan", age 46, preferred language English
- DOCTOR: "Dr. Arjun Menon", breast surgery/oncology, Mon/Wed/Fri weekly schedule for next 4 weeks
- CARE_COORDINATOR: "Priya Nair"
- Starting State: Stage 1 (Done), Stage 2 (Done), Stage 3 (Done), Stage 4 (Pending).
- Synthetic Report PDF in backend/uploads/reports/
- Unassigned New Patient: "Rahul Das" (Colorectal FIT Screening)
- 3 Real Database Notifications

All records are created through domain models and LifecycleService.
Passwords are read strictly from ambient environment or local gitignored files.
No passwords or hashes are hardcoded or printed.
"""

import os
import sys
import uuid
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

# Add backend directory to sys.path
repo_root = Path(__file__).resolve().parent.parent
backend_dir = repo_root / "backend"
sys.path.insert(0, str(backend_dir))

def load_local_env_file(file_path: Path):
    """Load key-value pairs from a file into os.environ if not already set."""
    if not file_path.exists():
        return
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k and k not in os.environ:
                os.environ[k] = v

# Load environment variables
load_local_env_file(repo_root / ".env.demo")
load_local_env_file(repo_root / ".env")
load_local_env_file(backend_dir / ".env")

doctor_pw = os.getenv("DEMO_DOCTOR_PASSWORD")
coordinator_pw = os.getenv("DEMO_COORDINATOR_PASSWORD")
patient_pw = os.getenv("DEMO_PATIENT_PASSWORD")

if not doctor_pw or not coordinator_pw or not patient_pw:
    print(
        "ERROR: Environment variables DEMO_PATIENT_PASSWORD, DEMO_DOCTOR_PASSWORD, "
        "and DEMO_COORDINATOR_PASSWORD must be set.",
        file=sys.stderr
    )
    sys.exit(1)

from sqlalchemy import select, and_
from app.core.security import hash_password
from app.database.session import get_sync_db
from app.models.user import User
from app.models.patient import Patient, Consent
from app.models.owner import CaseOwner
from app.models.screening import ScreeningResult
from app.models.care_case import CareCase, Task
from app.models.doctor_assignment import DoctorAssignment
from app.models.notification import Notification
from app.models.appointment import Appointment
from app.models.event_audit import CaseEvent
from app.services.lifecycle_service import LifecycleService


def generate_schedule_slots(start_date: datetime, weeks: int = 4) -> list:
    """Generate ISO-8601 slots for Mon, Wed, Fri for the next 4 weeks at 10:00 AM and 2:00 PM."""
    slots = []
    # 0 = Monday, 2 = Wednesday, 4 = Friday
    target_days = {0, 2, 4}
    current = start_date.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)

    end_date = start_date + timedelta(weeks=weeks)
    while current <= end_date:
        if current.weekday() in target_days:
            # Morning slot (10:00 AM UTC)
            slots.append(current.strftime("%Y-%m-%dT10:00:00Z"))
            # Afternoon slot (2:00 PM UTC)
            afternoon = current.replace(hour=14)
            slots.append(afternoon.strftime("%Y-%m-%dT14:00:00Z"))
        current += timedelta(days=1)
    return slots


def generate_synthetic_mammogram_pdf(target_path: Path):
    """Generates a professional diagnostic mammogram report PDF using ReportLab."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        target_path.parent.mkdir(parents=True, exist_ok=True)
        doc = SimpleDocTemplate(
            str(target_path),
            pagesize=letter,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40
        )

        styles = getSampleStyleSheet()
        header_style = ParagraphStyle(
            'Header',
            parent=styles['Heading1'],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor('#0F52BA'),
            alignment=1
        )
        sub_header = ParagraphStyle(
            'SubHeader',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#555555'),
            alignment=1
        )
        section_style = ParagraphStyle(
            'Section',
            parent=styles['Heading2'],
            fontSize=12,
            leading=16,
            textColor=colors.HexColor('#1E3A8A'),
            spaceBefore=10,
            spaceAfter=4
        )
        body_style = ParagraphStyle(
            'Body',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#1F2937')
        )
        bold_alert = ParagraphStyle(
            'BoldAlert',
            parent=body_style,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#B91C1C')
        )

        story = []
        story.append(Paragraph("METROPOLITAN COMPREHENSIVE BREAST CENTER", header_style))
        story.append(Paragraph("1200 Healthcare Parkway, Medical District • Tel: (555) 019-2834 • Accredited Breast Imaging Center", sub_header))
        story.append(Spacer(1, 10))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0F52BA'), spaceAfter=15))

        # Patient Info Table
        info_data = [
            [Paragraph("<b>Patient Name:</b> Meera Krishnan", body_style), Paragraph("<b>MRN:</b> MRN-2026-0461", body_style)],
            [Paragraph("<b>Date of Birth:</b> 1980-05-14 (Age: 46)", body_style), Paragraph("<b>Exam Date:</b> November 17, 2026", body_style)],
            [Paragraph("<b>Referring Clinician:</b> Dr. Arjun Menon, MD", body_style), Paragraph("<b>Accession:</b> ACC-2026-8812", body_style)]
        ]
        info_table = Table(info_data, colWidths=[260, 260])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F3F4F6')),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#D1D5DB')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
        ]))
        story.append(info_table)
        story.append(Spacer(1, 15))

        # Report Sections
        story.append(Paragraph("STUDY TYPE", section_style))
        story.append(Paragraph("Diagnostic Bilateral Digital Mammography with 3D Tomosynthesis (DBT) and Supplementary Right Breast Target Ultrasound.", body_style))

        story.append(Paragraph("CLINICAL INDICATION", section_style))
        story.append(Paragraph("Routine screening follow-up; patient reports 3-week history of mild localized fullness in right upper quadrant. No nipple discharge. Family history significant for maternal postmenopausal breast cancer.", body_style))

        story.append(Paragraph("BREAST DENSITY", section_style))
        story.append(Paragraph("<b>Category C:</b> Heterogeneously dense breast tissue, which may obscure small masses.", body_style))

        story.append(Paragraph("FINDINGS", section_style))
        findings_text = (
            "<b>Right Breast:</b> There is an irregular, hypoechoic solid mass measuring <b>4.2 cm</b> in greatest dimension "
            "with ill-defined, partially spiculated margins located in the <b>upper outer quadrant</b> at the 10:00 position, "
            "approximately 4 cm from the nipple. Associated fine, pleomorphic clustered microcalcifications are identified within "
            "and immediately adjacent to the mass. Targeted color Doppler ultrasound confirms internal vascularity.<br/><br/>"
            "<b>Left Breast:</b> Normal parenchymal pattern without focal architectural distortion, suspicious mass, or suspicious microcalcifications.<br/><br/>"
            "<b>Axilla:</b> Bilateral axillary lymph nodes show preserved fatty hila and normal cortical thickness with no radiologic evidence of adenopathy."
        )
        story.append(Paragraph(findings_text, body_style))

        story.append(Paragraph("IMPRESSION & ASSESSMENT", section_style))
        story.append(Paragraph("4.2 cm dominant solid mass in right breast upper outer quadrant with clustered pleomorphic microcalcifications.", body_style))
        story.append(Spacer(1, 5))
        story.append(Paragraph("<b>BI-RADS CATEGORY 4: Suspicious Abnormality</b>", bold_alert))

        story.append(Paragraph("RECOMMENDATIONS", section_style))
        recs = (
            "1. <b>Ultrasound-guided core needle tissue biopsy</b> of the right breast 10:00 position mass is recommended for definitive histological characterization.<br/>"
            "2. Consultation with a breast surgical oncologist (Dr. Arjun Menon) within 14 days.<br/>"
            "3. Post-biopsy clip placement and verification mammogram."
        )
        story.append(Paragraph(recs, body_style))
        story.append(Spacer(1, 15))

        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#9CA3AF'), spaceAfter=10))
        story.append(Paragraph("<b>Interpreting Radiologist:</b> Sunita Rao, MD (Board Certified Diagnostic Radiologist) • Finalized: 2026-11-18T10:30:00Z", sub_header))

        doc.build(story)
        print(f"Generated synthetic report PDF at: {target_path}")
    except Exception as e:
        print(f"Notice: PDF generation notice ({e}). Creating plain document placeholder.", file=sys.stderr)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "wb") as f:
            f.write(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000108 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n180\n%%EOF\n")


def seed_judge_demo():
    """Populates the complete judge demo state idempotently."""
    print("Starting CareBridge Judge Demo Data Seeding...")
    now = datetime.now(timezone.utc)

    # 1. Generate Report PDF in backend uploads store
    pdf_rel_path = "uploads/reports/meera_krishnan_mammogram_report.pdf"
    pdf_full_path = backend_dir / pdf_rel_path
    generate_synthetic_mammogram_pdf(pdf_full_path)

    schedule_slots = generate_schedule_slots(now, weeks=4)

    with get_sync_db() as db:
        # ----------------------------------------------------------------------
        # 2. DOCTOR: Dr. Arjun Menon, MD
        # ----------------------------------------------------------------------
        doc_email = "arjun.menon@carebridge.com"
        doctor_owner = db.execute(
            select(CaseOwner).where(CaseOwner.email == doc_email)
        ).scalar_one_or_none()

        working_hours = {
            "monday": ["09:00-12:00", "14:00-17:00"],
            "wednesday": ["09:00-12:00", "14:00-17:00"],
            "friday": ["09:00-12:00", "14:00-17:00"],
            "schedule_slots": schedule_slots
        }

        if not doctor_owner:
            doctor_owner = CaseOwner(
                id=uuid.uuid4(),
                name="Dr. Arjun Menon, MD",
                role="specialist",
                email=doc_email,
                phone="+91-98765-11230",
                facility="Metropolitan Breast & Comprehensive Cancer Center",
                is_active=True,
                specialty="Breast Oncology",
                subspecialties=["Breast Surgery", "Surgical Oncology", "Diagnostic Biopsy"],
                department="Department of Breast Surgery & Oncology",
                max_workload=20,
                working_hours=working_hours,
                eligibility_status="eligible",
                approved_case_categories=["bi_rads_4", "bi_rads_5", "breast_mass", "targeted_biopsy"],
                response_deadline_hours=24
            )
            db.add(doctor_owner)
            db.flush()
            print("Created CaseOwner: Dr. Arjun Menon, MD")
        else:
            doctor_owner.name = "Dr. Arjun Menon, MD"
            doctor_owner.specialty = "Breast Oncology"
            doctor_owner.subspecialties = ["Breast Surgery", "Surgical Oncology", "Diagnostic Biopsy"]
            doctor_owner.facility = "Metropolitan Breast & Comprehensive Cancer Center"
            doctor_owner.working_hours = working_hours
            doctor_owner.is_active = True
            db.flush()
            print("Updated CaseOwner: Dr. Arjun Menon, MD")

        # Doctor User Accounts
        for email in [doc_email, "doctor@carebridge.com"]:
            u = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if not u:
                u = User(
                    id=uuid.uuid4(),
                    email=email,
                    password_hash=hash_password(doctor_pw),
                    role="doctor",
                    full_name="Dr. Arjun Menon, MD",
                    is_active=True,
                    is_verified=True,
                    owner_id=doctor_owner.id
                )
                db.add(u)
            else:
                u.password_hash = hash_password(doctor_pw)
                u.role = "doctor"
                u.full_name = "Dr. Arjun Menon, MD"
                u.is_active = True
                u.is_verified = True
                u.owner_id = doctor_owner.id
        db.commit()

        # ----------------------------------------------------------------------
        # 3. CARE COORDINATOR: Priya Nair, RN
        # ----------------------------------------------------------------------
        coord_email = "priya.nair@carebridge.com"
        coord_owner = db.execute(
            select(CaseOwner).where(CaseOwner.email == coord_email)
        ).scalar_one_or_none()

        if not coord_owner:
            coord_owner = CaseOwner(
                id=uuid.uuid4(),
                name="Priya Nair, RN",
                role="care_coordinator",
                email=coord_email,
                phone="+91-98765-43210",
                facility="Metropolitan Breast & Comprehensive Cancer Center",
                is_active=True,
                working_hours={"monday": ["08:00-17:00"], "tuesday": ["08:00-17:00"], "wednesday": ["08:00-17:00"], "thursday": ["08:00-17:00"], "friday": ["08:00-17:00"]}
            )
            db.add(coord_owner)
            db.flush()
            print("Created CaseOwner: Priya Nair, RN")
        else:
            coord_owner.name = "Priya Nair, RN"
            coord_owner.role = "care_coordinator"
            coord_owner.is_active = True
            db.flush()
            print("Updated CaseOwner: Priya Nair, RN")

        # Coordinator User Accounts
        for email in [coord_email, "coordinator@carebridge.com"]:
            u = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if not u:
                u = User(
                    id=uuid.uuid4(),
                    email=email,
                    password_hash=hash_password(coordinator_pw),
                    role="care_coordinator",
                    full_name="Priya Nair, RN",
                    is_active=True,
                    is_verified=True,
                    owner_id=coord_owner.id
                )
                db.add(u)
            else:
                u.password_hash = hash_password(coordinator_pw)
                u.role = "care_coordinator"
                u.full_name = "Priya Nair, RN"
                u.is_active = True
                u.is_verified = True
                u.owner_id = coord_owner.id
        db.commit()

        # ----------------------------------------------------------------------
        # 4. PATIENT: Meera Krishnan (Age 46)
        # ----------------------------------------------------------------------
        patient_email = "meera.krishnan@carebridge.com"
        patient_meera = db.execute(
            select(Patient).where(Patient.mrn == "MRN-2026-0461")
        ).scalar_one_or_none()

        if not patient_meera:
            patient_meera = Patient(
                id=uuid.uuid4(),
                mrn="MRN-2026-0461",
                first_name="Meera",
                last_name="Krishnan",
                phone="+91-98765-43201",
                email=patient_email,
                date_of_birth=date(1980, 5, 14), # Age 46
                gender="female",
                preferred_language="en",
                communication_channel="sms",
                accessibility_requirements={"large_text": False, "voice_preferred": False, "mobility_assistance": False},
                patient_context={
                    "caregiver_name": "Rohan Krishnan (Spouse)",
                    "caregiver_phone": "+91-98765-43209",
                    "transportation_support": True,
                    "known_barriers": []
                }
            )
            db.add(patient_meera)
            db.flush()
            print("Created Patient: Meera Krishnan")
        else:
            patient_meera.first_name = "Meera"
            patient_meera.last_name = "Krishnan"
            patient_meera.date_of_birth = date(1980, 5, 14)
            patient_meera.email = patient_email
            patient_meera.preferred_language = "en"
            db.flush()
            print("Updated Patient: Meera Krishnan")

        # Patient User Accounts
        for email in [patient_email, "patient@carebridge.com"]:
            u = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if not u:
                u = User(
                    id=uuid.uuid4(),
                    email=email,
                    password_hash=hash_password(patient_pw),
                    role="patient",
                    full_name="Meera Krishnan",
                    is_active=True,
                    is_verified=True,
                    patient_id=patient_meera.id
                )
                db.add(u)
            else:
                u.password_hash = hash_password(patient_pw)
                u.role = "patient"
                u.full_name = "Meera Krishnan"
                u.is_active = True
                u.is_verified = True
                u.patient_id = patient_meera.id
        db.commit()

        # Consents for Meera Krishnan
        for scope in ["automated_patient_outreach", "cross_facility_referral_sharing"]:
            existing_c = db.execute(
                select(Consent).where(
                    and_(Consent.patient_id == patient_meera.id, Consent.scope == scope)
                )
            ).scalar_one_or_none()
            if not existing_c:
                c = Consent(
                    id=uuid.uuid4(),
                    patient_id=patient_meera.id,
                    scope=scope,
                    status="active",
                    granted_at=now - timedelta(days=10)
                )
                db.add(c)
        db.commit()

        # ----------------------------------------------------------------------
        # 5. SCREENING RESULT & CARE CASE FOR MEERA KRISHNAN
        # ----------------------------------------------------------------------
        screening_meera = db.execute(
            select(ScreeningResult).where(
                and_(ScreeningResult.patient_id == patient_meera.id, ScreeningResult.finding_code == "BI-RADS-4")
            )
        ).scalar_one_or_none()

        report_raw_data = {
            "study_type": "Diagnostic Bilateral Digital Mammogram with 3D Tomosynthesis",
            "date": (now - timedelta(days=3)).strftime("%Y-%m-%d"),
            "breast_density": "Heterogeneously dense (Category C)",
            "findings": "4.2 cm irregular hypoechoic mass with ill-defined margins and clustered pleomorphic microcalcifications in upper outer quadrant of right breast at 10 o'clock position, 4 cm from nipple.",
            "impression": "Suspicious right breast mass with associated microcalcifications.",
            "bi_rads_category": "BI-RADS Category 4",
            "recommendation": "Ultrasound-guided core needle tissue biopsy and clinical consultation with breast surgical oncologist within 14 days.",
            "report_filename": "meera_krishnan_mammogram_report.pdf",
            "report_pdf_path": pdf_rel_path,
            "uploaded_by": "Priya Nair, RN",
            "uploaded_at": (now - timedelta(days=2)).isoformat(),
            "finalized": True,
            "finalized_at": (now - timedelta(days=2)).isoformat()
        }

        if not screening_meera:
            screening_meera = ScreeningResult(
                id=uuid.uuid4(),
                patient_id=patient_meera.id,
                screening_type="Mammogram",
                test_date=now - timedelta(days=3),
                finding_code="BI-RADS-4",
                finding_summary="4.2cm irregular hypoechoic mass with clustered pleomorphic microcalcifications in upper outer quadrant of right breast. Ultrasound-guided core biopsy strongly indicated.",
                urgency_level="urgent",
                performing_facility="Metropolitan Breast Screening Center",
                raw_report_data=report_raw_data
            )
            db.add(screening_meera)
            db.flush()
        else:
            screening_meera.raw_report_data = report_raw_data
            screening_meera.finding_summary = "4.2cm irregular hypoechoic mass with clustered pleomorphic microcalcifications in upper outer quadrant of right breast. Ultrasound-guided core biopsy strongly indicated."
            db.flush()

        # Care Case
        case_meera = db.execute(
            select(CareCase).where(CareCase.case_number == "CASE-2026-JUDGE01")
        ).scalar_one_or_none()

        if not case_meera:
            case_meera = CareCase(
                id=uuid.uuid4(),
                case_number="CASE-2026-JUDGE01",
                patient_id=patient_meera.id,
                screening_result_id=screening_meera.id,
                current_owner_id=coord_owner.id,
                status="notified",
                clinical_pathway="mammogram_abnormal_bi_rads_4",
                priority="urgent",
                sla_start_time=now - timedelta(days=3),
                sla_deadline=now + timedelta(days=11),
                sla_status="normal",
                case_context={
                    "assigned_doctor": "Dr. Arjun Menon, MD",
                    "assigned_doctor_id": str(doctor_owner.id),
                    "doctor_name": "Dr. Arjun Menon, MD",
                    "specialty": "Breast Oncology",
                    "facility": "Metropolitan Breast & Comprehensive Cancer Center",
                    "screening_type": "Mammogram",
                    "finding_code": "BI-RADS-4",
                    "finding_summary": screening_meera.finding_summary,
                    "inferred_barriers": [],
                    "recovery_attempts": 0,
                    "patient_understanding_confirmed": False,
                    "notes": [
                        f"Day 0: Screening performed at Metropolitan Breast Screening Center.",
                        f"Day 1: Diagnostic report uploaded, validated and finalized (BI-RADS 4, 4.2cm mass).",
                        f"Day 2: Assigned to Dr. Arjun Menon, MD for Breast Oncology review.",
                        f"Day 2: Plain-language results notification dispatched to patient via SMS."
                    ]
                }
            )
            db.add(case_meera)
            db.flush()
            print("Created CareCase: CASE-2026-JUDGE01")
        else:
            case_meera.current_owner_id = coord_owner.id
            case_meera.status = "notified"
            ctx = dict(case_meera.case_context or {})
            ctx.update({
                "assigned_doctor": "Dr. Arjun Menon, MD",
                "assigned_doctor_id": str(doctor_owner.id),
                "doctor_name": "Dr. Arjun Menon, MD",
                "specialty": "Breast Oncology",
                "facility": "Metropolitan Breast & Comprehensive Cancer Center",
                "screening_type": "Mammogram",
                "finding_code": "BI-RADS-4",
                "finding_summary": screening_meera.finding_summary,
            })
            case_meera.case_context = ctx
            db.flush()
            print("Updated CareCase: CASE-2026-JUDGE01")

        # Doctor Assignment for Dr. Arjun Menon
        existing_assign = db.execute(
            select(DoctorAssignment).where(
                and_(DoctorAssignment.case_id == case_meera.id, DoctorAssignment.doctor_id == doctor_owner.id)
            )
        ).scalar_one_or_none()

        if not existing_assign:
            assignment = DoctorAssignment(
                id=uuid.uuid4(),
                case_id=case_meera.id,
                doctor_id=doctor_owner.id,
                specialty_matched="Breast Oncology",
                subspecialty_matched="Breast Surgery",
                urgency_level="urgent",
                allocation_score=0.98,
                allocation_factors={
                    "specialty_match": 1.0,
                    "subspecialty_match": 1.0,
                    "workload_capacity": 0.95,
                    "schedule_availability": 1.0,
                    "geographic_proximity": 0.95
                },
                assigned_by_role="care_coordinator",
                status="ACCEPTED",
                deadline=now + timedelta(hours=24),
                responded_at=now - timedelta(days=2)
            )
            db.add(assignment)
        else:
            existing_assign.status = "ACCEPTED"
            existing_assign.specialty_matched = "Breast Oncology"
        db.commit()

        # ----------------------------------------------------------------------
        # 6. LIFECYCLE INITIALIZATION: STAGES 1, 2, 3 COMPLETED, STAGE 4 PENDING
        # ----------------------------------------------------------------------
        LifecycleService.initialize_lifecycle(case_meera, screening_meera, patient_meera, db=db)

        # Update Stage 1 and 2 evidence
        stages = LifecycleService.get_lifecycle_stages(case_meera)
        for st in stages:
            if st["stage_number"] == 1:
                st["status"] = "completed"
                st["evidence"] = {
                    "screening_completion": True,
                    "procedure_performed": "Diagnostic Bilateral Digital Mammography with 3D Tomosynthesis",
                    "facility": "Metropolitan Breast Screening Center",
                    "test_date": (now - timedelta(days=3)).isoformat()
                }
            elif st["stage_number"] == 2:
                st["status"] = "completed"
                st["evidence"] = {
                    "diagnostic_report": True,
                    "finding_code": "BI-RADS-4",
                    "finding_summary": screening_meera.finding_summary,
                    "urgency_level": "urgent",
                    "report_filename": "meera_krishnan_mammogram_report.pdf",
                    "finalized": True
                }

        ctx = dict(case_meera.case_context or {})
        ctx["lifecycle_stages"] = stages
        case_meera.case_context = ctx
        db.commit()

        # Advance Stage 3 (PATIENT_NOTIFIED) if not already completed
        stage_3 = next((s for s in stages if s["stage_number"] == 3), None)
        if stage_3 and stage_3.get("status") != "completed":
            LifecycleService.advance_stage(
                db=db,
                case_id=case_meera.id,
                stage_ident=3,
                actor_role="care_coordinator",
                actor_id=str(coord_owner.id),
                actor_name="Priya Nair, RN",
                evidence={
                    "notification_delivery": True,
                    "channel": "sms",
                    "outreach_dispatched": True,
                    "delivery_status": "delivered",
                    "notified_at": (now - timedelta(days=1)).isoformat()
                },
                notes="Notification dispatched to Meera Krishnan via SMS. Delivery confirmed."
            )

        # Ensure Stage 4 remains PENDING (as required for demo!)
        stages = LifecycleService.get_lifecycle_stages(case_meera)
        for st in stages:
            if st["stage_number"] == 4:
                st["status"] = "pending"
                st["completed_at"] = None
                st["evidence"] = {}
            elif st["stage_number"] > 4:
                st["status"] = "pending"
                st["completed_at"] = None
                st["evidence"] = {}

        ctx = dict(case_meera.case_context or {})
        ctx["lifecycle_stages"] = stages
        ctx["current_stage_number"] = 4
        ctx["current_stage_id"] = "PATIENT_UNDERSTANDS"
        case_meera.case_context = ctx
        case_meera.status = "notified"
        db.commit()
        print("Configured Meera Krishnan lifecycle: Stages 1..3 COMPLETED, Stage 4 PENDING.")

        # ----------------------------------------------------------------------
        # 7. UNASSIGNED NEW PATIENT: Rahul Das (Synthetic)
        # ----------------------------------------------------------------------
        patient_rahul = db.execute(
            select(Patient).where(Patient.mrn == "MRN-2026-0522")
        ).scalar_one_or_none()

        if not patient_rahul:
            patient_rahul = Patient(
                id=uuid.uuid4(),
                mrn="MRN-2026-0522",
                first_name="Rahul",
                last_name="Das",
                phone="+91-98765-43202",
                email="rahul.das@carebridge.com",
                date_of_birth=date(1974, 9, 20), # Age 52
                gender="male",
                preferred_language="en",
                communication_channel="sms",
                accessibility_requirements={"large_text": False, "voice_preferred": False, "mobility_assistance": False},
                patient_context={"transportation_support": True, "known_barriers": []}
            )
            db.add(patient_rahul)
            db.flush()
            print("Created Patient: Rahul Das")

        # Screening Result for Rahul Das
        screening_rahul = db.execute(
            select(ScreeningResult).where(
                and_(ScreeningResult.patient_id == patient_rahul.id, ScreeningResult.finding_code == "FIT-POSITIVE")
            )
        ).scalar_one_or_none()

        if not screening_rahul:
            screening_rahul = ScreeningResult(
                id=uuid.uuid4(),
                patient_id=patient_rahul.id,
                screening_type="Colorectal FIT",
                test_date=now - timedelta(days=1),
                finding_code="FIT-POSITIVE",
                finding_summary="Fecal Immunochemical Test (FIT) positive for occult blood (125 ug Hb/g feces). Clinical colonoscopy evaluation indicated within 30 days.",
                urgency_level="urgent",
                performing_facility="City Community Diagnostic Lab",
                raw_report_data={
                    "test_type": "Fecal Immunochemical Test",
                    "hb_concentration": "125 ug/g",
                    "recommendation": "Diagnostic colonoscopy within 30 days"
                }
            )
            db.add(screening_rahul)
            db.flush()

        # Unassigned Care Case for Rahul Das
        case_rahul = db.execute(
            select(CareCase).where(CareCase.case_number == "CASE-2026-UNASSIGNED01")
        ).scalar_one_or_none()

        if not case_rahul:
            case_rahul = CareCase(
                id=uuid.uuid4(),
                case_number="CASE-2026-UNASSIGNED01",
                patient_id=patient_rahul.id,
                screening_result_id=screening_rahul.id,
                current_owner_id=None, # UNASSIGNED
                status="result_received",
                clinical_pathway="colorectal_fit_positive_followup",
                priority="urgent",
                sla_start_time=now - timedelta(days=1),
                sla_deadline=now + timedelta(days=29),
                sla_status="normal",
                case_context={
                    "screening_type": "Colorectal FIT",
                    "finding_code": "FIT-POSITIVE",
                    "finding_summary": screening_rahul.finding_summary,
                    "needs_coordinator_action": True,
                    "unassigned": True,
                    "notes": ["Day 0: Positive FIT screening result received. Awaiting coordinator intake assignment."]
                }
            )
            db.add(case_rahul)
            db.flush()
            print("Created Unassigned CareCase: CASE-2026-UNASSIGNED01 for Rahul Das")

        # Pending task for Rahul Das
        task_rahul = db.execute(
            select(Task).where(
                and_(Task.case_id == case_rahul.id, Task.task_type == "intake_coordination")
            )
        ).scalar_one_or_none()

        if not task_rahul:
            task_rahul = Task(
                id=uuid.uuid4(),
                case_id=case_rahul.id,
                patient_id=patient_rahul.id,
                title="Intake & Coordinator Assignment: Rahul Das",
                description="New abnormal FIT result received. Review case context and assign care coordinator.",
                task_type="intake_coordination",
                assigned_role="care_coordinator",
                status="pending",
                priority="urgent",
                due_date=now + timedelta(hours=24)
            )
            db.add(task_rahul)
        db.commit()

        # ----------------------------------------------------------------------
        # 8. THREE PERSISTENT NOTIFICATIONS
        # ----------------------------------------------------------------------
        # Find user IDs
        user_meera = db.execute(select(User).where(User.email == "meera.krishnan@carebridge.com")).scalar_one_or_none()
        user_priya = db.execute(select(User).where(User.email == "priya.nair@carebridge.com")).scalar_one_or_none()
        user_arjun = db.execute(select(User).where(User.email == "arjun.menon@carebridge.com")).scalar_one_or_none()

        if user_meera:
            existing_notif_meera = db.execute(
                select(Notification).where(
                    and_(Notification.user_id == user_meera.id, Notification.idempotency_key == "demo_notif_meera_results")
                )
            ).scalar_one_or_none()
            if not existing_notif_meera:
                n1 = Notification(
                    id=uuid.uuid4(),
                    user_id=user_meera.id,
                    role="patient",
                    event_type="screening_result_available",
                    title="Mammogram Screening Results Available",
                    message="Your diagnostic mammography report from Metropolitan Breast Center is ready. Connect with CareBridge AI to review plain-language findings.",
                    priority="normal",
                    case_id=case_meera.id,
                    patient_id=patient_meera.id,
                    idempotency_key="demo_notif_meera_results"
                )
                db.add(n1)

        if user_priya:
            existing_notif_priya = db.execute(
                select(Notification).where(
                    and_(Notification.user_id == user_priya.id, Notification.idempotency_key == "demo_notif_priya_rahul_intake")
                )
            ).scalar_one_or_none()
            if not existing_notif_priya:
                n2 = Notification(
                    id=uuid.uuid4(),
                    user_id=user_priya.id,
                    role="care_coordinator",
                    event_type="new_patient_intake",
                    title="New Unassigned Patient Requirement: Rahul Das",
                    message="A new abnormal screening result has arrived for Rahul Das (Positive FIT Screening). Please review and assign care coordination.",
                    priority="normal",
                    case_id=case_rahul.id,
                    patient_id=patient_rahul.id,
                    idempotency_key="demo_notif_priya_rahul_intake"
                )
                db.add(n2)

        if user_arjun:
            existing_notif_arjun = db.execute(
                select(Notification).where(
                    and_(Notification.user_id == user_arjun.id, Notification.idempotency_key == "demo_notif_arjun_meera_assigned")
                )
            ).scalar_one_or_none()
            if not existing_notif_arjun:
                n3 = Notification(
                    id=uuid.uuid4(),
                    user_id=user_arjun.id,
                    role="doctor",
                    event_type="doctor_case_assigned",
                    title="New Patient Case Assigned: Meera Krishnan",
                    message="Care case CASE-2026-JUDGE01 (Meera Krishnan, BI-RADS 4 Mammogram) has been assigned for breast oncology review.",
                    priority="normal",
                    case_id=case_meera.id,
                    patient_id=patient_meera.id,
                    idempotency_key="demo_notif_arjun_meera_assigned"
                )
                db.add(n3)

        db.commit()
        print("Created/verified 3 persistent database notifications.")

    print("\nSUCCESS: CareBridge Judge Demo Cohort Successfully Seeded!")
    print("- PATIENT: Meera Krishnan (meera.krishnan@carebridge.com, Stage 3 Done, Stage 4 Pending)")
    print("- DOCTOR: Dr. Arjun Menon (arjun.menon@carebridge.com, Mon/Wed/Fri weekly slots)")
    print("- CARE COORDINATOR: Priya Nair (priya.nair@carebridge.com)")
    print("- UNASSIGNED PATIENT: Rahul Das (CASE-2026-UNASSIGNED01 in queue)")
    print("- SYNTHETIC REPORT: backend/uploads/reports/meera_krishnan_mammogram_report.pdf")


if __name__ == "__main__":
    seed_judge_demo()
