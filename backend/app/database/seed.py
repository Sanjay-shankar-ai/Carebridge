"""
CareBridge Synthetic Seed Data Generator
Populates realistic closed-loop screening-to-care cases, including Patient P-0147 from the pitch deck.
Can be executed synchronously or asynchronously against PostgreSQL / SQLite.
"""

import uuid
from datetime import datetime, timezone, timedelta, date
from typing import List
from sqlalchemy.orm import Session
from app.database.session import Base, sync_engine, sync_session_factory
from app.models import (
    User,
    Patient,
    Consent,
    ScreeningResult,
    CaseOwner,
    CareCase,
    Task,
    Referral,
    Appointment,
    Communication,
    ConversationSession,
    CaseEvent,
    AuditLog,
    ClosureEvidence,
    CaseOwnershipHistory,
)
from app.core.security import hash_password


def seed_database(db: Session, extended: bool = False) -> dict:
    """Populates the database with synthetic patients, clinical pathways, and active cases."""
    print("Seeding database with synthetic healthcare cohort...")

    # Ensure all tables exist before clearing/seeding
    from app.database.session import Base
    Base.metadata.create_all(bind=db.get_bind())

    # Clear existing data if any (in reverse dependency order)
    for model in [
        User, ClosureEvidence, AuditLog, CaseEvent, Communication,
        ConversationSession, Appointment, Referral, Task,
        CaseOwnershipHistory, CareCase, CaseOwner, ScreeningResult, Consent, Patient
    ]:
        try:
            db.query(model).delete()
        except Exception:
            pass
    db.commit()

    now = datetime.now(timezone.utc)

    # --------------------------------------------------------------------------
    # 1. Case Owners (Care Coordinator & Clinicians)
    # --------------------------------------------------------------------------
    coordinator_priya = CaseOwner(
        id=uuid.uuid4(),
        name="Priya Nair, RN",
        role="care_coordinator",
        email="priya.nair@metrogovhealth.org",
        phone="+91-98765-43210",
        facility="Metropolitan Breast & Cancer Care Center",
        is_active=True
    )
    coordinator_marcus = CaseOwner(
        id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        name="Marcus Vance, RN",
        role="care_coordinator",
        email="marcus.vance@metrogovhealth.org",
        phone="+91-98765-43211",
        facility="Metropolitan Pulmonology Center",
        is_active=True
    )
    coordinator_sarah = CaseOwner(
        id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        name="Sarah Jenkins, RN",
        role="care_coordinator",
        email="sarah.jenkins@metrogovhealth.org",
        phone="+91-98765-43212",
        facility="Metropolitan Wellness & Screening Center",
        is_active=True
    )
    clinician_dr_thorne = CaseOwner(
        id=uuid.uuid4(),
        name="Dr. Aris Thorne, MD",
        role="specialist",
        email="aris.thorne@specialtyclinic.org",
        phone="+91-98765-11223",
        facility="Clinic A - Women's Specialty Breast Center",
        is_active=True
    )
    clinician_dr_chen = CaseOwner(
        id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
        name="Dr. Robert Chen, MD",
        role="specialist",
        email="robert.chen@specialtyclinic.org",
        phone="+91-98765-11224",
        facility="Metropolitan Pulmonology Center",
        is_active=True
    )
    clinician_dr_rostova = CaseOwner(
        id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
        name="Dr. Elena Rostova, MD",
        role="specialist",
        email="elena.rostova@specialtyclinic.org",
        phone="+91-98765-11225",
        facility="Metropolitan Health Center",
        is_active=True
    )
    db.add_all([
        coordinator_priya,
        coordinator_marcus,
        coordinator_sarah,
        clinician_dr_thorne,
        clinician_dr_chen,
        clinician_dr_rostova
    ])
    db.commit()

    # --------------------------------------------------------------------------
    # 2. Patient 1: Mrs. Meenakshi Ramanathan (The Exemplar Case P-0147)
    # --------------------------------------------------------------------------
    patient_meenakshi = Patient(
        id=uuid.uuid4(),
        mrn="MRN-2026-0147",
        first_name="Meenakshi",
        last_name="Ramanathan",
        phone="+91-94440-12345",
        email="meenakshi.r52@example.com",
        date_of_birth=date(1974, 6, 15),
        gender="female",
        preferred_language="en", # English preferred
        communication_channel="whatsapp",
        accessibility_requirements={
            "large_text": True,
            "voice_preferred": False,
            "mobility_assistance": False
        },
        patient_context={
            "caregiver_name": "Ananya Ramanathan (Daughter)",
            "caregiver_phone": "+91-94440-54321",
            "transportation_support": False, # Relies on daughter
            "known_barriers": ["transportation_caregiver_dependency"]
        }
    )
    db.add(patient_meenakshi)
    db.commit()

    # --------------------------------------------------------------------------
    # 2b. User Identity Accounts (Hashed passwords & verified roles)
    # --------------------------------------------------------------------------
    user_doctor = User(
        id=uuid.uuid4(),
        email="doctor@carebridge.com",
        password_hash=hash_password("DoctorPass123!"),
        role="doctor",
        full_name="Dr. Aris Thorne, MD",
        is_active=True,
        is_verified=True,
        owner_id=clinician_dr_thorne.id,
    )
    user_doctor_alt = User(
        id=uuid.uuid4(),
        email="aris.thorne@specialtyclinic.org",
        password_hash=hash_password("DoctorPass123!"),
        role="doctor",
        full_name="Dr. Aris Thorne, MD",
        is_active=True,
        is_verified=True,
        owner_id=clinician_dr_thorne.id,
    )
    user_coordinator = User(
        id=uuid.uuid4(),
        email="coordinator@carebridge.com",
        password_hash=hash_password("CoordinatorPass123!"),
        role="care_coordinator",
        full_name="Priya Nair, RN",
        is_active=True,
        is_verified=True,
        owner_id=coordinator_priya.id,
    )
    user_coordinator_alt = User(
        id=uuid.uuid4(),
        email="priya.nair@metrogovhealth.org",
        password_hash=hash_password("CoordinatorPass123!"),
        role="care_coordinator",
        full_name="Priya Nair, RN",
        is_active=True,
        is_verified=True,
        owner_id=coordinator_priya.id,
    )
    user_patient = User(
        id=uuid.uuid4(),
        email="patient@carebridge.com",
        password_hash=hash_password("PatientPass123!"),
        role="patient",
        full_name="Meenakshi Ramanathan",
        is_active=True,
        is_verified=True,
        patient_id=patient_meenakshi.id,
    )
    user_patient_alt = User(
        id=uuid.uuid4(),
        email="meenakshi.r52@example.com",
        password_hash=hash_password("PatientPass123!"),
        role="patient",
        full_name="Meenakshi Ramanathan",
        is_active=True,
        is_verified=True,
        patient_id=patient_meenakshi.id,
    )
    user_admin = User(
        id=uuid.uuid4(),
        email="admin@carebridge.com",
        password_hash=hash_password("AdminPass123!"),
        role="admin",
        full_name="System Administrator",
        is_active=False,
        is_verified=True,
    )
    user_admin_alt = User(
        id=uuid.uuid4(),
        email="admin@carebridge.health",
        password_hash=hash_password("AdminPass123!"),
        role="admin",
        full_name="System Administrator",
        is_active=False,
        is_verified=True,
    )
    db.add_all([
        user_doctor, user_doctor_alt,
        user_coordinator, user_coordinator_alt,
        user_patient, user_patient_alt,
        user_admin, user_admin_alt
    ])
    db.commit()

    # Consents for Patient 1
    consent_comm = Consent(
        id=uuid.uuid4(),
        patient_id=patient_meenakshi.id,
        scope="automated_patient_outreach",
        status="active",
        granted_at=now - timedelta(days=30)
    )
    consent_referral = Consent(
        id=uuid.uuid4(),
        patient_id=patient_meenakshi.id,
        scope="cross_facility_referral_sharing",
        status="active",
        granted_at=now - timedelta(days=30)
    )
    db.add_all([consent_comm, consent_referral])

    # Screening Result for Patient 1 (Abnormal Mammogram BI-RADS 4)
    screening_meenakshi = ScreeningResult(
        id=uuid.uuid4(),
        patient_id=patient_meenakshi.id,
        screening_type="Mammogram",
        test_date=now - timedelta(days=7),
        finding_code="BI-RADS-4",
        finding_summary="4.2cm irregular mass with clustered microcalcifications in upper outer quadrant of right breast. Tissue biopsy strongly indicated.",
        urgency_level="urgent",
        performing_facility="Metropolitan Breast Screening Lab",
        raw_report_data={
            "laterality": "right",
            "quadrant": "upper_outer",
            "density": "heterogeneously_dense",
            "recommendation": "Targeted ultrasound and core needle biopsy within 14 days"
        }
    )
    db.add(screening_meenakshi)
    db.commit()

    # Care Case P-0147
    case_p0147 = CareCase(
        id=uuid.uuid4(),
        case_number="CASE-2026-0147",
        patient_id=patient_meenakshi.id,
        screening_result_id=screening_meenakshi.id,
        current_owner_id=coordinator_priya.id,
        status="recovering", # In active recovery after transport barrier
        clinical_pathway="mammogram_abnormal_bi_rads_4",
        priority="urgent",
        sla_start_time=now - timedelta(days=7),
        sla_deadline=now + timedelta(days=7), # 14 days total SLA
        sla_status="normal",
        case_context={
            "inferred_barriers": ["transportation_caregiver"],
            "recovery_attempts": 1,
            "last_recovery_strategy": "reschedule_with_daughter_availability",
            "patient_understanding_confirmed": True,
            "notes": [
                "Day 0: Abnormal mammogram result received, assigned to Care Coordinator Priya Nair.",
                "Day 1: Plain-language notification dispatched; patient confirmed receipt and understanding.",
                "Day 1: Referral to Clinic A generated and accepted.",
                "Day 2: Appointment set for Day 6.",
                "Day 5: Patient messaged stating daughter is out of town and cannot provide transport.",
                "Day 6: Care Recovery Agent engaged; confirmed daughter returns on Day 8; rescheduled visit to Day 9."
            ]
        }
    )
    db.add(case_p0147)
    db.commit()

    # Seed continuous ownership history for Case P-0147
    history_p0147 = CaseOwnershipHistory(
        id=uuid.uuid4(),
        case_id=case_p0147.id,
        previous_owner_id=None,
        new_owner_id=coordinator_priya.id,
        transferred_by="screening_intake_system",
        reason="Initial assignment: Abnormal mammogram screening result (BI-RADS 4).",
        effective_from=now - timedelta(days=7),
        is_active=True
    )
    db.add(history_p0147)
    db.commit()

    # Referral for Case P-0147
    referral_clinic_a = Referral(
        id=uuid.uuid4(),
        case_id=case_p0147.id,
        patient_id=patient_meenakshi.id,
        referring_provider="Dr. V. Raman, Radiologist",
        target_facility="Clinic A - Women's Specialty Breast Center",
        specialty="Diagnostic Breast Oncology",
        reason_for_referral="BI-RADS 4 lesion evaluation and core needle biopsy",
        status="accepted",
        acceptance_deadline=now - timedelta(days=5),
        responded_at=now - timedelta(days=6)
    )
    db.add(referral_clinic_a)

    # Appointments for Case P-0147 (Original missed/rescheduled + Recovery appointment)
    appt_missed = Appointment(
        id=uuid.uuid4(),
        case_id=case_p0147.id,
        patient_id=patient_meenakshi.id,
        facility="Clinic A - Women's Specialty Breast Center",
        provider_name="Dr. Aris Thorne, MD",
        appointment_type="biopsy_consultation",
        scheduled_time=now - timedelta(days=1),
        status="rescheduled",
        notes="Patient could not travel without caregiver daughter. Proactively rescheduled via recovery agent."
    )
    db.add(appt_missed)
    db.commit()

    appt_recovered = Appointment(
        id=uuid.uuid4(),
        case_id=case_p0147.id,
        patient_id=patient_meenakshi.id,
        facility="Clinic A - Women's Specialty Breast Center",
        provider_name="Dr. Aris Thorne, MD",
        appointment_type="biopsy_consultation",
        scheduled_time=now + timedelta(days=2), # Day 9
        status="booked",
        rescheduled_from_id=appt_missed.id,
        notes="Confirmed with patient that daughter Ananya will drive her to the appointment."
    )
    db.add(appt_recovered)

    # Active Conversation Session for P-0147
    session_p0147 = ConversationSession(
        id=uuid.uuid4(),
        patient_id=patient_meenakshi.id,
        case_id=case_p0147.id,
        channel="whatsapp",
        summary="Patient acknowledged mammogram results in English. Overcame transportation barrier by aligning consultation with daughter's travel return date.",
        unanswered_questions=[],
        patient_commitments=[
            {
                "commitment": "Bring prior imaging CD and attend consultation with daughter Ananya",
                "target_date": (now + timedelta(days=2)).strftime("%Y-%m-%d"),
                "status": "pending"
            }
        ],
        is_active=True,
        last_interaction_at=now - timedelta(hours=2)
    )
    db.add(session_p0147)
    db.commit()

    # Communications for Case P-0147
    msg_outreach = Communication(
        id=uuid.uuid4(),
        case_id=case_p0147.id,
        patient_id=patient_meenakshi.id,
        session_id=session_p0147.id,
        sender="ai_coordinator",
        channel="whatsapp",
        language="en",
        content="Hello Mrs. Meenakshi, your mammogram screening requires a brief follow-up evaluation. We have reserved a specialist consultation at Clinic A. Please let us know if you need any assistance.",
        translated_content="Hello Mrs. Meenakshi, your mammogram screening requires a brief follow-up evaluation. We have reserved a specialist consultation at Clinic A. Please let us know if you need any assistance.",
        acknowledged=True,
        acknowledgement_details={"comprehension_verified": True, "patient_confirmed_at": (now - timedelta(days=6)).isoformat()},
        sent_at=now - timedelta(days=6)
    )
    msg_inbound_barrier = Communication(
        id=uuid.uuid4(),
        case_id=case_p0147.id,
        patient_id=patient_meenakshi.id,
        session_id=session_p0147.id,
        sender="patient",
        channel="whatsapp",
        language="en",
        content="I can't come tomorrow. My daughter is out of town and I have nobody to take me.",
        translated_content="I can't come tomorrow. My daughter is out of town and I have nobody to take me.",
        acknowledged=True,
        acknowledgement_details={"barrier_detected": "transportation_caregiver"},
        sent_at=now - timedelta(days=2)
    )
    msg_ai_recovery = Communication(
        id=uuid.uuid4(),
        case_id=case_p0147.id,
        patient_id=patient_meenakshi.id,
        session_id=session_p0147.id,
        sender="ai_coordinator",
        channel="whatsapp",
        language="en",
        content="Do not worry Mrs. Meenakshi. We have coordinated with Clinic A to reschedule your visit to fit your daughter's return. Does that work comfortably for you?",
        translated_content="Do not worry Mrs. Meenakshi. We have coordinated with Clinic A to reschedule your visit to fit your daughter's return. Does that work comfortably for you?",
        acknowledged=True,
        acknowledgement_details={"reschedule_confirmed": True},
        sent_at=now - timedelta(days=1)
    )
    db.add_all([msg_outreach, msg_inbound_barrier, msg_ai_recovery])

    # Pending Task for Case P-0147
    task_followup = Task(
        id=uuid.uuid4(),
        case_id=case_p0147.id,
        title="Verify Clinic A appointment attendance",
        description="Check attendance log for Dr. Thorne consultation and confirm biopsy scheduling.",
        task_type="attendance_verification",
        assigned_to_id=coordinator_priya.id,
        assigned_role="ai_coordinator",
        status="pending",
        due_date=now + timedelta(days=3)
    )
    db.add(task_followup)

    # Case Events & Audit Logs for P-0147
    event_intake = CaseEvent(
        id=uuid.uuid4(),
        case_id=case_p0147.id,
        event_type="screening_result_received",
        description="BI-RADS 4 abnormal mammogram ingested from screening lab.",
        event_data={"finding_code": "BI-RADS-4", "urgency": "urgent"},
        timestamp=now - timedelta(days=7)
    )
    event_barrier = CaseEvent(
        id=uuid.uuid4(),
        case_id=case_p0147.id,
        event_type="barrier_detected",
        description="Patient flagged inability to attend Day 6 visit due to daughter's travel.",
        event_data={"barrier": "transportation_caregiver", "source": "patient_whatsapp"},
        timestamp=now - timedelta(days=2)
    )
    db.add_all([event_intake, event_barrier])

    audit_recovery = AuditLog(
        id=uuid.uuid4(),
        case_id=case_p0147.id,
        patient_id=patient_meenakshi.id,
        actor_type="ai_agent",
        actor_id="carebridge_recovery_agent",
        action="PROACTIVE_RESCHEDULE_APPOINTMENT",
        autonomy_level=2,
        previous_state={"appointment_id": str(appt_missed.id), "status": "booked"},
        new_state={"appointment_id": str(appt_recovered.id), "status": "booked", "date": (now + timedelta(days=2)).isoformat()},
        rationale="Patient flagged transportation barrier due to caregiver travel. Autonomous recovery play rebooked within 14-day clinical SLA window.",
        timestamp=now - timedelta(days=1)
    )
    db.add(audit_recovery)

    # --------------------------------------------------------------------------
    # 3. Patient 2: John Doe (P-0148 - Urgent Colorectal Screening Case)
    # --------------------------------------------------------------------------
    patient_john = Patient(
        id=uuid.uuid4(),
        mrn="MRN-2026-0148",
        first_name="John",
        last_name="Doe",
        phone="+91-98880-99887",
        email="john.doe@example.com",
        date_of_birth=date(1962, 3, 21),
        gender="male",
        preferred_language="en",
        communication_channel="sms",
        accessibility_requirements={"large_text": False},
        patient_context={"known_barriers": []}
    )
    db.add(patient_john)
    db.commit()

    screening_john = ScreeningResult(
        id=uuid.uuid4(),
        patient_id=patient_john.id,
        screening_type="Colorectal FIT",
        test_date=now - timedelta(days=3),
        finding_code="FIT-POSITIVE",
        finding_summary="Fecal Immunochemical Test (FIT) positive (>100 ug/g). Diagnostic colonoscopy required.",
        urgency_level="urgent",
        performing_facility="Central Pathology Laboratory",
        raw_report_data={"fit_value": 142}
    )
    db.add(screening_john)
    db.commit()

    case_p0148 = CareCase(
        id=uuid.uuid4(),
        case_number="CASE-2026-0148",
        patient_id=patient_john.id,
        screening_result_id=screening_john.id,
        current_owner_id=coordinator_priya.id,
        status="notified",
        clinical_pathway="colorectal_fit_positive_pathway",
        priority="urgent",
        sla_start_time=now - timedelta(days=3),
        sla_deadline=now + timedelta(days=2), # Close to SLA deadline
        sla_status="warning",
        case_context={
            "inferred_barriers": [],
            "patient_understanding_confirmed": False
        }
    )
    db.add(case_p0148)

    # --------------------------------------------------------------------------
    # 4. Patient 3: Priya Sharma (P-0149 - Closed Case with Verified Clinical Evidence)
    # --------------------------------------------------------------------------
    patient_priya = Patient(
        id=uuid.uuid4(),
        mrn="MRN-2026-0149",
        first_name="Priya",
        last_name="Sharma",
        phone="+91-97770-11223",
        email="priya.sharma@example.com",
        date_of_birth=date(1982, 11, 4),
        gender="female",
        preferred_language="en",
        communication_channel="in_app_chat",
        accessibility_requirements={},
        patient_context={"known_barriers": []}
    )
    db.add(patient_priya)
    db.commit()

    screening_priya = ScreeningResult(
        id=uuid.uuid4(),
        patient_id=patient_priya.id,
        screening_type="Mammogram",
        test_date=now - timedelta(days=45),
        finding_code="BI-RADS-4",
        finding_summary="Small 1.5cm circumscribed density in left breast.",
        urgency_level="standard",
        performing_facility="Metropolitan Breast Screening Lab",
        raw_report_data={}
    )
    db.add(screening_priya)
    db.commit()

    case_p0149 = CareCase(
        id=uuid.uuid4(),
        case_number="CASE-2026-0149",
        patient_id=patient_priya.id,
        screening_result_id=screening_priya.id,
        current_owner_id=clinician_dr_thorne.id,
        status="closed",
        clinical_pathway="mammogram_abnormal_bi_rads_4",
        priority="standard",
        sla_start_time=now - timedelta(days=45),
        sla_deadline=now + timedelta(days=15),
        sla_status="normal",
        case_context={
            "patient_understanding_confirmed": True,
            "closure_type": "clinical_evidence_verified"
        }
    )
    db.add(case_p0149)
    db.commit()

    # Closure Evidence for P-0149 (Verified by Clinician)
    evidence_closure = ClosureEvidence(
        id=uuid.uuid4(),
        case_id=case_p0149.id,
        evidence_type="pathology_report",
        evidence_summary="Core needle biopsy completed: Benign fibroadenoma. No atypia or malignancy. Routine annual screening recommended.",
        verifying_clinician_id=clinician_dr_thorne.id,
        verified_at=now - timedelta(days=5),
        evidence_metadata={
            "biopsy_result": "benign",
            "pathologist": "Dr. E. Vance, MD",
            "next_screening_due": "2027-11-01"
        },
        is_verified=True
    )
    db.add(evidence_closure)

    audit_closure = AuditLog(
        id=uuid.uuid4(),
        case_id=case_p0149.id,
        patient_id=patient_priya.id,
        actor_type="clinician",
        actor_id=str(clinician_dr_thorne.id),
        action="VERIFIED_CLINICAL_CLOSURE",
        autonomy_level=3,
        previous_state={"status": "consulted"},
        new_state={"status": "closed", "evidence_id": str(evidence_closure.id)},
        rationale="Benign pathology report verified by Dr. Thorne. Care loop closed with documented resolution.",
        timestamp=now - timedelta(days=5)
    )
    db.add(audit_closure)

    db.commit()
    print("Database seeding completed successfully!")

    if extended:
        print("Seeding extended demo cohort for analytics & operational risk prioritization...")
        # Attended appointment and outreach for Priya Sharma (Case P-0149)
        appt_priya = Appointment(
            id=uuid.uuid4(),
            case_id=case_p0149.id,
            patient_id=patient_priya.id,
            facility="Clinic A - Women's Specialty Breast Center",
            provider_name="Dr. Aris Thorne, MD",
            appointment_type="core_needle_biopsy",
            scheduled_time=now - timedelta(days=6),
            status="attended",
            attendance_recorded_at=now - timedelta(days=6),
            notes="Biopsy completed successfully under ultrasound guidance. Specimen forwarded to pathology."
        )
        comm_priya = Communication(
            id=uuid.uuid4(),
            case_id=case_p0149.id,
            patient_id=patient_priya.id,
            sender="ai_coordinator",
            channel="in_app_chat",
            language="en",
            content="Hello Priya, your screening results require follow-up biopsy evaluation. We have reserved an appointment for you.",
            acknowledged=True,
            sent_at=now - timedelta(days=44)
        )
        db.add_all([appt_priya, comm_priya])

        # Patient 4: Carlos Mendez (Overdue SLA Breached Case)
        patient_carlos = Patient(
            id=uuid.uuid4(),
            mrn="MRN-2026-0150",
            first_name="Carlos",
            last_name="Mendez",
            phone="+1-555-019-3382",
            email="carlos.m@example.com",
            date_of_birth=date(1968, 8, 14),
            gender="male",
            preferred_language="es",
            communication_channel="sms",
            patient_context={"known_barriers": ["work_schedule_conflict", "hourly_wage_loss"]}
        )
        db.add(patient_carlos)
        db.commit()

        screening_carlos = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=patient_carlos.id,
            screening_type="Low-Dose CT Lung",
            test_date=now - timedelta(days=22),
            finding_code="Lung-RADS-4A",
            finding_summary="Suspicious 9mm solid nodule in right middle lobe. Diagnostic PET-CT or biopsy indicated within 14 days.",
            urgency_level="urgent",
            performing_facility="Metropolitan Imaging Center"
        )
        db.add(screening_carlos)
        db.commit()

        case_p0150 = CareCase(
            id=uuid.uuid4(),
            case_number="CASE-2026-0150",
            patient_id=patient_carlos.id,
            screening_result_id=screening_carlos.id,
            current_owner_id=coordinator_priya.id,
            status="missed_visit",
            clinical_pathway="lung_screening_abnormal_pathway",
            priority="urgent",
            sla_start_time=now - timedelta(days=22),
            sla_deadline=now - timedelta(days=8), # Overdue by 8 days!
            sla_status="breached",
            case_context={
                "inferred_barriers": ["work_schedule_conflict"],
                "recovery_attempts": 2,
                "notes": ["Missed visit due to inflexible shift hours. Needs evening or weekend consultation."]
            }
        )
        db.add(case_p0150)
        db.commit()

        appt_carlos_missed = Appointment(
            id=uuid.uuid4(),
            case_id=case_p0150.id,
            patient_id=patient_carlos.id,
            facility="Metropolitan Pulmonology Center",
            provider_name="Dr. Sarah Lin, MD",
            appointment_type="pulmonology_diagnostic",
            scheduled_time=now - timedelta(days=9),
            status="no_show",
            cancellation_reason="Patient unable to leave hourly job during standard clinic hours."
        )
        comm_carlos = Communication(
            id=uuid.uuid4(),
            case_id=case_p0150.id,
            patient_id=patient_carlos.id,
            sender="ai_coordinator",
            channel="sms",
            language="es",
            content="Estimado Carlos, notamos que no pudo asistir a su cita. ¿Podemos ayudarle a reprogramar para un sábado?",
            translated_content="Dear Carlos, we noticed you missed your visit. Can we help you reschedule for a Saturday?",
            acknowledged=True,
            sent_at=now - timedelta(days=21)
        )
        db.add_all([appt_carlos_missed, comm_carlos])

        # Patient 5: Amina Al-Mansoor (Unassigned Escalated Case)
        patient_amina = Patient(
            id=uuid.uuid4(),
            mrn="MRN-2026-0151",
            first_name="Amina",
            last_name="Al-Mansoor",
            phone="+1-555-014-9901",
            email="amina.m@example.com",
            date_of_birth=date(1977, 4, 30),
            gender="female",
            preferred_language="ar",
            communication_channel="sms",
            patient_context={"known_barriers": ["language_barrier", "cultural_modesty"]}
        )
        db.add(patient_amina)
        db.commit()

        screening_amina = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=patient_amina.id,
            screening_type="Cervical Cytology / HPV",
            test_date=now - timedelta(days=2),
            finding_code="HPV-16-HSIL",
            finding_summary="High-grade squamous intraepithelial lesion with HPV-16. Colposcopy mandatory.",
            urgency_level="critical",
            performing_facility="Women's Health Diagnostic Center"
        )
        db.add(screening_amina)
        db.commit()

        case_p0151 = CareCase(
            id=uuid.uuid4(),
            case_number="CASE-2026-0151",
            patient_id=patient_amina.id,
            screening_result_id=screening_amina.id,
            current_owner_id=None, # UNASSIGNED CASE!
            status="UNASSIGNED_ESCALATED",
            clinical_pathway="cervical_abnormal_colposcopy_pathway",
            priority="critical",
            sla_start_time=now - timedelta(days=2),
            sla_deadline=now + timedelta(days=2),
            sla_status="warning",
            case_context={
                "inferred_barriers": ["language_barrier"],
                "notes": ["Case requires immediate coordinator assignment and Arabic-speaking care navigator."]
            }
        )
        db.add(case_p0151)
        db.commit()

        comm_amina = Communication(
            id=uuid.uuid4(),
            case_id=case_p0151.id,
            patient_id=patient_amina.id,
            sender="ai_coordinator",
            channel="sms",
            language="ar",
            content="مرحبًا أمينة، يرجى التواصل مع فريق الرعاية الصحية بشأن نتائج الفحص الخاصة بك.",
            translated_content="Hello Amina, please contact your care team regarding your screening results.",
            acknowledged=False,
            sent_at=now - timedelta(days=1, hours=8)
        )
        db.add(comm_amina)

        # Patient 6: David Chen (Active Case with Dr. Aris Thorne)
        patient_david = Patient(
            id=uuid.uuid4(),
            mrn="MRN-2026-0152",
            first_name="David",
            last_name="Chen",
            phone="+1-555-018-8833",
            email="david.chen@example.com",
            date_of_birth=date(1959, 10, 12),
            gender="male",
            preferred_language="en",
            communication_channel="in_app_chat",
            patient_context={"known_barriers": []}
        )
        db.add(patient_david)
        db.commit()

        screening_david = ScreeningResult(
            id=uuid.uuid4(),
            patient_id=patient_david.id,
            screening_type="Serum PSA",
            test_date=now - timedelta(days=5),
            finding_code="PSA-ELEVATED",
            finding_summary="PSA elevated at 9.8 ng/mL (Normal < 4.0). Urology consult advised.",
            urgency_level="standard",
            performing_facility="Central Pathology Laboratory"
        )
        db.add(screening_david)
        db.commit()

        case_p0152 = CareCase(
            id=uuid.uuid4(),
            case_number="CASE-2026-0152",
            patient_id=patient_david.id,
            screening_result_id=screening_david.id,
            current_owner_id=clinician_dr_thorne.id, # Provider: Dr. Thorne
            status="referred",
            clinical_pathway="psa_elevated_urology_pathway",
            priority="standard",
            sla_start_time=now - timedelta(days=5),
            sla_deadline=now + timedelta(days=25),
            sla_status="normal",
            case_context={
                "patient_understanding_confirmed": True,
                "notes": ["Referral accepted by Urology. Diagnostic appointment scheduled for next week."]
            }
        )
        db.add(case_p0152)
        db.commit()

        referral_david = Referral(
            id=uuid.uuid4(),
            case_id=case_p0152.id,
            patient_id=patient_david.id,
            referring_provider="Primary Care Team",
            target_facility="Metropolitan Urology Specialty Center",
            specialty="Urology",
            reason_for_referral="Evaluation of elevated PSA (9.8 ng/mL)",
            status="accepted",
            acceptance_deadline=now + timedelta(days=2),
            responded_at=now - timedelta(days=3)
        )
        appt_david = Appointment(
            id=uuid.uuid4(),
            case_id=case_p0152.id,
            patient_id=patient_david.id,
            facility="Metropolitan Urology Specialty Center",
            provider_name="Dr. Aris Thorne, MD",
            appointment_type="urology_diagnostic_consult",
            scheduled_time=now + timedelta(days=4),
            status="booked"
        )
        comm_david = Communication(
            id=uuid.uuid4(),
            case_id=case_p0152.id,
            patient_id=patient_david.id,
            sender="ai_coordinator",
            channel="in_app_chat",
            language="en",
            content="Hello David, your urology referral has been accepted and consultation is confirmed for next Tuesday.",
            acknowledged=True,
            sent_at=now - timedelta(days=4, hours=12)
        )
        db.add_all([referral_david, appt_david, comm_david])
        db.commit()

        print("Extended analytics cohort seeded successfully (6 total cases).")
        return {
            "patients": 6,
            "cases": 6,
            "exemplar_case": "CASE-2026-0147 (Meenakshi Ramanathan)"
        }

    return {
        "patients": 3,
        "cases": 3,
        "exemplar_case": "CASE-2026-0147 (Meenakshi Ramanathan)"
    }


if __name__ == "__main__":
    # Ensure tables exist when run directly
    Base.metadata.create_all(bind=sync_engine)
    with sync_session_factory() as session:
        seed_database(session)
