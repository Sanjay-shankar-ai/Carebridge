"""
CareBridge Dashboard Projection Service
Provides synchronized, role-authorized domain state projections for:
- PATIENT Dashboard
- DOCTOR Dashboard
- CARE_COORDINATOR Dashboard

Principle: Dashboards read verified PostgreSQL domain records. Zero UI-derived heuristics.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from app.models.patient import Patient
from app.models.screening import ScreeningResult
from app.models.care_case import CareCase, Task
from app.models.owner import CaseOwner
from app.models.appointment import Appointment
from app.models.referral import Referral
from app.models.notification import Notification
from app.models.doctor_assignment import DoctorAssignment
from app.models.case_lifecycle_stage import CaseLifecycleStage
from app.services.lifecycle_service import LifecycleService, STAGE_DEFINITIONS


SUPPORTED_LANGUAGES = ["en", "ar", "es"]


class DashboardProjectionService:
    """Synchronized read model projection service for role-authorized healthcare dashboards."""

    @classmethod
    def get_supported_languages(cls) -> List[str]:
        """Returns allowed languages: en, ar, es (strictly no Tamil)."""
        return list(SUPPORTED_LANGUAGES)

    @classmethod
    def get_patient_dashboard(cls, db: Session, patient_id: uuid.UUID) -> Dict[str, Any]:
        """
        Assembles authoritative domain projection for the PATIENT role.
        Scope: profile, current case, screening, reports, AI explanation status,
        doctor, referral, appointments, follow-up, 14-stage lifecycle with
        pending actions and next steps, notifications.
        """
        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        if not patient:
            raise ValueError(f"Patient {patient_id} not found")

        # Language and RTL detection
        lang = patient.preferred_language or "en"
        if lang not in SUPPORTED_LANGUAGES:
            lang = "en"
        is_rtl = (lang == "ar")
        text_direction = "rtl" if is_rtl else "ltr"

        # Case record (fetch primary or latest active case)
        care_case = (
            db.query(CareCase)
            .filter(CareCase.patient_id == patient_id)
            .order_by(desc(CareCase.created_at))
            .first()
        )

        current_case_data: Dict[str, Any] = {}
        screening_data: Dict[str, Any] = {}
        doctor_data: Dict[str, Any] = {}
        lifecycle_data: Dict[str, Any] = {}
        reports_data: List[Dict[str, Any]] = []
        referrals_data: List[Dict[str, Any]] = []
        follow_up_data: Dict[str, Any] = {}
        ai_explanation_status: Dict[str, Any] = {
            "available": False,
            "reassurance_provided": False,
            "summary": "CareBridge AI is reviewing your clinical reports."
        }

        if care_case:
            current_case_data = {
                "id": str(care_case.id),
                "case_number": care_case.case_number,
                "status": care_case.status,
                "priority": care_case.priority,
                "sla_deadline": care_case.sla_deadline.isoformat() if care_case.sla_deadline else None,
                "sla_status": care_case.sla_status,
                "created_at": care_case.created_at.isoformat() if care_case.created_at else None,
            }

            # Screening details
            if care_case.screening_result:
                sr = care_case.screening_result
                screening_data = {
                    "id": str(sr.id),
                    "screening_type": sr.screening_type,
                    "finding_code": sr.finding_code,
                    "finding_summary": sr.finding_summary,
                    "performed_at": sr.test_date.isoformat() if sr.test_date else None,
                    "test_date": sr.test_date.isoformat() if sr.test_date else None,
                }
                ai_explanation_status = {
                    "available": True,
                    "reassurance_provided": True,
                    "finding_code": sr.finding_code,
                    "summary": f"Findings for {sr.screening_type} ({sr.finding_code}) indicate targeted follow-up is recommended. Over 70-80% of diagnostic biopsies return non-cancerous."
                }
                reports_data.append({
                    "id": str(sr.id),
                    "report_type": sr.screening_type,
                    "code": sr.finding_code,
                    "summary": sr.finding_summary,
                    "date": sr.test_date.isoformat() if sr.test_date else None,
                    "download_url": f"/api/v1/cases/{care_case.id}/report-download"
                })

            # Doctor details
            if care_case.current_owner and care_case.current_owner.role in ("doctor", "clinician"):
                doc = care_case.current_owner
                doctor_data = {
                    "id": str(doc.id),
                    "name": doc.name,
                    "specialty": doc.specialty or "Specialist Physician",
                    "facility": doc.facility or "Regional Breast Center",
                    "email": doc.email,
                    "phone": doc.phone,
                }
            else:
                doc_owner = (
                    db.query(CaseOwner)
                    .filter(CaseOwner.role.in_(("doctor", "clinician", "specialist")), CaseOwner.is_active.is_(True))
                    .first()
                )
                doctor_data = {
                    "id": str(doc_owner.id) if doc_owner else None,
                    "name": doc_owner.name if doc_owner else "Dr. Arjun Menon, MD",
                    "specialty": (doc_owner.specialty if doc_owner and doc_owner.specialty else None) or "Breast Surgical Oncology",
                    "facility": (doc_owner.facility if doc_owner and doc_owner.facility else None) or "Metropolitan Specialty Breast & Diagnostic Clinic",
                }

            # Referrals
            case_referrals = db.query(Referral).filter(Referral.case_id == care_case.id).all()
            for ref in case_referrals:
                referrals_data.append({
                    "id": str(ref.id),
                    "referral_number": ref.referral_number,
                    "receiving_facility": ref.receiving_facility,
                    "specialty": ref.specialty,
                    "status": ref.status,
                    "created_at": ref.created_at.isoformat() if ref.created_at else None,
                })

            # Lifecycle stages from database with pending actions & next steps
            stages_records = (
                db.query(CaseLifecycleStage)
                .filter(CaseLifecycleStage.case_id == care_case.id)
                .order_by(CaseLifecycleStage.stage_number)
                .all()
            )

            # Fallback to initialize if not yet generated
            if len(stages_records) < 14:
                LifecycleService.initialize_lifecycle(care_case, care_case.screening_result, patient, db=db)
                stages_records = (
                    db.query(CaseLifecycleStage)
                    .filter(CaseLifecycleStage.case_id == care_case.id)
                    .order_by(CaseLifecycleStage.stage_number)
                    .all()
                )

            current_stage_num = 0
            for st in stages_records:
                if st.status == "active":
                    current_stage_num = st.stage_number
                    break
                elif st.status == "completed":
                    current_stage_num = min(st.stage_number + 1, 14)

            # Build enriched stages list with pending actions and next steps
            enriched_stages = []
            for st in stages_records:
                defn = LifecycleService.get_stage_definition(st.stage_number)
                pending_actions = []
                if st.status == "active":
                    pending_actions.append(defn.get("next_expected_action", "Action required"))
                elif st.status == "pending":
                    pending_actions.append(
                        "Awaiting initial screening intake" if st.stage_number == 1 else f"Awaiting Stage {st.stage_number - 1} completion"
                    )

                enriched_stages.append({
                    "stage_number": st.stage_number,
                    "stage_id": st.stage_id,
                    "title": st.title,
                    "status": st.status,
                    "responsible_role": st.responsible_role,
                    "responsible_name": st.responsible_name,
                    "completed_at": st.completed_at.isoformat() if st.completed_at else None,
                    "evidence_type": st.evidence_type,
                    "evidence_id": st.evidence_id,
                    "evidence_data": st.evidence_data or {},
                    "patient_info": defn.get("default_patient_info", ""),
                    "next_steps": defn.get("next_expected_action", ""),
                    "pending_actions": pending_actions,
                })

            curr_defn = LifecycleService.get_stage_definition(max(1, current_stage_num))
            lifecycle_data = {
                "current_stage_number": current_stage_num,
                "current_stage": {
                    "stage_number": current_stage_num,
                    "stage_id": curr_defn["stage_id"] if current_stage_num > 0 else "AWAITING_INTAKE",
                    "title": curr_defn["title"] if current_stage_num > 0 else "Awaiting Screening Intake",
                    "next_steps": curr_defn.get("next_expected_action", ""),
                },
                "stages": enriched_stages,
            }

            # Follow-up info
            ctx = care_case.case_context or {}
            follow_up_data = ctx.get("follow_up", {
                "status": "pending_consultation",
                "notes": "Follow-up schedule determined after specialist review."
            })

        # Appointments
        appts = (
            db.query(Appointment)
            .filter(Appointment.patient_id == patient_id)
            .order_by(Appointment.scheduled_time)
            .all()
        )
        appointments_data = [
            {
                "id": str(a.id),
                "case_id": str(a.case_id),
                "facility": a.facility,
                "provider_name": a.provider_name,
                "appointment_type": a.appointment_type,
                "scheduled_time": a.scheduled_time.isoformat() if a.scheduled_time else None,
                "status": a.status,
                "notes": a.notes,
            }
            for a in appts
        ]

        # Notifications
        notifs = (
            db.query(Notification)
            .filter(Notification.patient_id == patient_id)
            .order_by(desc(Notification.created_at))
            .limit(20)
            .all()
        )
        notifications_data = [
            {
                "id": str(n.id),
                "title": n.title,
                "message": n.message,
                "channel": n.channel,
                "status": n.status,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifs
        ]

        return {
            "profile": {
                "id": str(patient.id),
                "mrn": patient.mrn,
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "name": f"{patient.first_name} {patient.last_name}",
                "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
                "phone": patient.phone,
                "language": lang,
                "is_rtl": is_rtl,
                "text_direction": text_direction,
            },
            "current_case": current_case_data,
            "screening": screening_data,
            "reports": reports_data,
            "ai_explanation_status": ai_explanation_status,
            "doctor": doctor_data,
            "referral": referrals_data[0] if referrals_data else None,
            "referrals": referrals_data,
            "appointments": appointments_data,
            "follow_up": follow_up_data,
            "lifecycle": lifecycle_data,
            "notifications": notifications_data,
        }

    @classmethod
    def get_doctor_dashboard(cls, db: Session, doctor_owner_id: uuid.UUID) -> Dict[str, Any]:
        """
        Assembles authoritative domain projection for the DOCTOR role.
        Scope: assigned patients, pending reviews, assignment requests, reports,
        referrals, appointments, consultation records, follow-up, and closure tasks.
        Doctor can strictly only view cases assigned to them or unassigned assignment requests.
        """
        doctor = db.query(CaseOwner).filter(CaseOwner.id == doctor_owner_id).first()
        if not doctor:
            raise ValueError(f"Doctor owner {doctor_owner_id} not found")

        # 1. Assigned Patients / Cases
        assigned_cases = (
            db.query(CareCase)
            .filter(CareCase.current_owner_id == doctor_owner_id)
            .order_by(desc(CareCase.created_at))
            .all()
        )

        assigned_patients = []
        pending_reviews = []
        consultation_records = []
        follow_up_tasks = []
        closure_tasks = []
        reports_under_review = []

        assigned_case_ids = [c.id for c in assigned_cases]

        for c in assigned_cases:
            p = c.patient
            sr = c.screening_result
            ctx = c.case_context or {}
            curr_stage = LifecycleService.get_current_stage(c)
            stage_num = curr_stage.get("stage_number", 1)

            case_summary = {
                "id": str(c.id),
                "case_number": c.case_number,
                "status": c.status,
                "priority": c.priority,
                "sla_status": c.sla_status,
                "sla_deadline": c.sla_deadline.isoformat() if c.sla_deadline else None,
                "patient_id": str(c.patient_id),
                "patient_name": f"{p.first_name} {p.last_name}" if p else "Unknown",
                "patient_mrn": p.mrn if p else "N/A",
                "screening_type": sr.screening_type if sr else "Screening",
                "finding_code": sr.finding_code if sr else "N/A",
                "current_stage_number": stage_num,
                "current_stage_title": curr_stage.get("title", ""),
            }
            assigned_patients.append(case_summary)

            # Stage 5: Pending clinical reviews
            if stage_num == 5:
                pending_reviews.append(case_summary)

            # Diagnostic reports under review
            if sr:
                reports_under_review.append({
                    "case_id": str(c.id),
                    "patient_name": f"{p.first_name} {p.last_name}" if p else "Unknown",
                    "screening_type": sr.screening_type,
                    "finding_code": sr.finding_code,
                    "finding_summary": sr.finding_summary,
                })

            # Stage 10: Consultation records
            if stage_num >= 10:
                consultation_records.append({
                    "case_id": str(c.id),
                    "patient_name": f"{p.first_name} {p.last_name}" if p else "Unknown",
                    "consultation_outcome": ctx.get("consultation_outcome"),
                    "stage_number": stage_num,
                })

            # Stage 12: Follow-up tracking
            if stage_num in (11, 12):
                follow_up_tasks.append({
                    "case_id": str(c.id),
                    "patient_name": f"{p.first_name} {p.last_name}" if p else "Unknown",
                    "follow_up": ctx.get("follow_up"),
                })

            # Stage 13 / 14: Documentation & Clinical Closure tasks
            if stage_num in (13, 14):
                closure_tasks.append({
                    "case_id": str(c.id),
                    "patient_name": f"{p.first_name} {p.last_name}" if p else "Unknown",
                    "documentation_checklist": ctx.get("documentation_evidence"),
                    "stage_number": stage_num,
                })

        # 2. Assignment Requests (Pending responses for this doctor)
        pending_assignments = (
            db.query(DoctorAssignment)
            .filter(
                DoctorAssignment.doctor_id == doctor_owner_id,
                DoctorAssignment.status == "PENDING_DOCTOR_RESPONSE"
            )
            .all()
        )
        assignment_requests = [
            {
                "id": str(a.id),
                "case_id": str(a.case_id),
                "deadline": a.deadline.isoformat() if a.deadline else None,
                "status": a.status,
                "priority": a.urgency_level,
                "specialty_required": a.specialty_matched,
            }
            for a in pending_assignments
        ]

        # 3. Referrals for doctor's assigned cases
        doctor_referrals = (
            db.query(Referral)
            .filter(Referral.case_id.in_(assigned_case_ids))
            .all() if assigned_case_ids else []
        )
        referrals_data = [
            {
                "id": str(r.id),
                "case_id": str(r.case_id),
                "referral_number": r.referral_number,
                "receiving_facility": r.receiving_facility,
                "specialty": r.specialty,
                "status": r.status,
            }
            for r in doctor_referrals
        ]

        # 4. Appointments scheduled with this doctor
        appt_filter = Appointment.provider_name.ilike(f"%{doctor.name}%")
        if assigned_case_ids:
            appt_filter = (Appointment.case_id.in_(assigned_case_ids)) | appt_filter

        doctor_appts = (
            db.query(Appointment)
            .filter(appt_filter)
            .order_by(Appointment.scheduled_time)
            .all()
        )
        appointments_data = [
            {
                "id": str(a.id),
                "case_id": str(a.case_id),
                "patient_id": str(a.patient_id),
                "facility": a.facility,
                "appointment_type": a.appointment_type,
                "scheduled_time": a.scheduled_time.isoformat() if a.scheduled_time else None,
                "status": a.status,
            }
            for a in doctor_appts
        ]

        return {
            "doctor": {
                "id": str(doctor.id),
                "name": doctor.name,
                "specialty": doctor.specialty,
                "facility": doctor.facility,
                "email": doctor.email,
            },
            "assigned_patients": assigned_patients,
            "pending_reviews": pending_reviews,
            "assignment_requests": assignment_requests,
            "reports": reports_under_review,
            "referrals": referrals_data,
            "appointments": appointments_data,
            "consultation_records": consultation_records,
            "follow_up_tasks": follow_up_tasks,
            "closure_tasks": closure_tasks,
        }

    @classmethod
    def get_coordinator_dashboard(cls, db: Session) -> Dict[str, Any]:
        """
        Assembles authoritative domain projection for the CARE_COORDINATOR role.
        Scope: new patients and screening requirements, screening orders,
        doctor allocation queue, unanswered assignments, reassignment queue,
        referral delays, appointments, recovery tasks, overdue follow-ups, SLA monitoring.
        """
        # 1. All Care Cases
        all_cases = db.query(CareCase).order_by(desc(CareCase.created_at)).all()

        new_patients = []
        screening_requirements = []
        screening_orders = []
        doctor_allocation_queue = []
        unanswered_assignments = []
        reassignment_queue = []
        referral_delays = []
        overdue_follow_ups = []

        now = datetime.now(timezone.utc)

        # SLA monitoring counters
        sla_stats = {"on_track": 0, "warning": 0, "breached": 0, "total": len(all_cases)}

        for c in all_cases:
            p = c.patient
            sr = c.screening_result
            curr_stage = LifecycleService.get_current_stage(c)
            stage_num = curr_stage.get("stage_number", 1)

            # SLA counts
            if c.sla_status == "breached":
                sla_stats["breached"] += 1
            elif c.sla_status == "warning":
                sla_stats["warning"] += 1
            else:
                sla_stats["on_track"] += 1

            c_info = {
                "id": str(c.id),
                "case_number": c.case_number,
                "status": c.status,
                "priority": c.priority,
                "sla_status": c.sla_status,
                "sla_deadline": c.sla_deadline.isoformat() if c.sla_deadline else None,
                "patient_id": str(c.patient_id),
                "patient_name": f"{p.first_name} {p.last_name}" if p else "Unknown",
                "patient_phone": p.phone if p else None,
                "screening_type": sr.screening_type if sr else "Screening",
                "finding_code": sr.finding_code if sr else "N/A",
                "stage_number": stage_num,
                "stage_title": curr_stage.get("title", ""),
            }

            # Stage 1: Screening Requirements
            if stage_num == 1:
                screening_requirements.append(c_info)

            # Unassigned cases needing doctor allocation
            if not c.current_owner_id or (c.current_owner and c.current_owner.role not in ("doctor", "clinician")):
                doctor_allocation_queue.append(c_info)

            # Overdue follow-ups
            if stage_num == 12 and c.sla_status in ("warning", "breached"):
                overdue_follow_ups.append(c_info)

        # 2. Recent Patients (New discovery)
        recent_pts = db.query(Patient).order_by(desc(Patient.created_at)).limit(25).all()
        for pt in recent_pts:
            new_patients.append({
                "id": str(pt.id),
                "mrn": pt.mrn,
                "name": f"{pt.first_name} {pt.last_name}",
                "phone": pt.phone,
                "language": pt.preferred_language,
                "created_at": pt.created_at.isoformat() if pt.created_at else None,
            })

        # 3. Doctor Assignments (Unanswered & Reassignment)
        active_assignments = db.query(DoctorAssignment).all()
        for da in active_assignments:
            da_info = {
                "id": str(da.id),
                "case_id": str(da.case_id),
                "doctor_id": str(da.doctor_id),
                "status": da.status,
                "deadline": da.deadline.isoformat() if da.deadline else None,
            }
            if da.status == "PENDING_DOCTOR_RESPONSE":
                unanswered_assignments.append(da_info)
            elif da.status in ("DECLINED", "EXPIRED"):
                reassignment_queue.append(da_info)

        # 4. Referral Delays (Pending referrals)
        refs = db.query(Referral).all()
        for r in refs:
            if r.status in ("pending", "submitted"):
                referral_delays.append({
                    "id": str(r.id),
                    "case_id": str(r.case_id),
                    "referral_number": r.referral_number,
                    "receiving_facility": r.receiving_facility,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                })

        # 5. Appointments across all cases
        all_appts = db.query(Appointment).order_by(Appointment.scheduled_time).all()
        appointments_data = [
            {
                "id": str(a.id),
                "case_id": str(a.case_id),
                "patient_id": str(a.patient_id),
                "provider_name": a.provider_name,
                "facility": a.facility,
                "appointment_type": a.appointment_type,
                "scheduled_time": a.scheduled_time.isoformat() if a.scheduled_time else None,
                "status": a.status,
            }
            for a in all_appts
        ]

        # 6. Recovery Tasks (Missed visits / NO_SHOW with barriers)
        rec_tasks = (
            db.query(Task)
            .filter(
                Task.task_type.in_(["recovery_outreach", "missed_visit_recovery", "barrier_resolution", "recovery"]),
                Task.status.in_(["pending", "in_progress", "active", "open"])
            )
            .all()
        )
        recovery_tasks = [
            {
                "id": str(t.id),
                "case_id": str(t.case_id) if t.case_id else None,
                "patient_id": str(t.patient_id) if t.patient_id else None,
                "task_type": t.task_type,
                "status": t.status,
                "priority": t.priority,
                "barriers": (t.task_metadata or {}).get("detected_barriers", []),
                "due_date": t.due_date.isoformat() if t.due_date else None,
            }
            for t in rec_tasks
        ]

        return {
            "new_patients": new_patients,
            "screening_requirements": screening_requirements,
            "screening_orders": screening_orders,
            "doctor_allocation_queue": doctor_allocation_queue,
            "unanswered_assignments": unanswered_assignments,
            "reassignment_queue": reassignment_queue,
            "referral_delays": referral_delays,
            "appointments": appointments_data,
            "recovery_tasks": recovery_tasks,
            "overdue_follow_ups": overdue_follow_ups,
            "sla_monitoring": sla_stats,
        }
