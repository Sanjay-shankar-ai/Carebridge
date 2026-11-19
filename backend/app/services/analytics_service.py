"""
CareBridge Analytics & Operational Prioritization Service (Phase 10)
Calculates core closed-loop care metrics, operational drop-off risk, and multi-criteria filters
from actual database records.

IMPORTANT CLINICAL GOVERNANCE NOTICE:
Operational drop-off risk prioritization reflects administrative follow-up coordination,
communication responsiveness, barrier prevalence, and SLA countdowns.
It does NOT represent clinical risk prediction, medical triage, or disease prognosis.
"""

import statistics
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from app.models.care_case import CareCase
from app.models.patient import Patient
from app.models.screening import ScreeningResult
from app.models.appointment import Appointment
from app.models.referral import Referral
from app.models.communication import Communication
from app.models.closure import ClosureEvidence
from app.models.owner import CaseOwner
from app.models.event_audit import CaseEvent


class CareBridgeAnalyticsService:
    """Computes data-driven closed-loop care metrics and operational follow-up priorities."""

    @classmethod
    def apply_case_filters(
        cls,
        query,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        status: Optional[str] = None,
        provider_id: Optional[str] = None
    ):
        """Applies date, case status, and provider filters to a CareCase query."""
        if from_date:
            query = query.filter(func.coalesce(CareCase.sla_start_time, CareCase.created_at) >= from_date)
        if to_date:
            query = query.filter(func.coalesce(CareCase.sla_start_time, CareCase.created_at) <= to_date)

        if status and status != "all":
            if status == "active":
                query = query.filter(CareCase.status.notin_(["closed", "care_completed"]))
            elif status == "overdue":
                now = datetime.now(timezone.utc)
                query = query.filter(
                    and_(
                        CareCase.status.notin_(["closed", "care_completed"]),
                        or_(CareCase.sla_deadline < now, CareCase.sla_status == "breached")
                    )
                )
            elif status == "warning":
                query = query.filter(CareCase.sla_status.in_(["warning", "breached"]))
            elif status == "recovering":
                query = query.filter(CareCase.status.in_(["recovering", "missed_visit"]))
            elif status == "closed":
                query = query.filter(CareCase.status.in_(["closed", "care_completed"]))
            elif status == "unassigned":
                query = query.filter(or_(CareCase.current_owner_id.is_(None), CareCase.status == "UNASSIGNED_ESCALATED"))
            else:
                query = query.filter(CareCase.status == status)

        if provider_id and provider_id != "all":
            if provider_id == "unassigned":
                query = query.filter(CareCase.current_owner_id.is_(None))
            else:
                try:
                    p_uuid = uuid.UUID(provider_id)
                    query = query.filter(CareCase.current_owner_id == p_uuid)
                except ValueError:
                    # Filter by provider name if string passed
                    query = query.join(CareCase.current_owner).filter(CaseOwner.name.ilike(f"%{provider_id}%"))

        return query

    @classmethod
    def calculate_all_metrics(
        cls,
        db: Session,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        status: Optional[str] = None,
        provider_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculates all 9 core operational and closed-loop care metrics:
        1. Time from result to notification
        2. Patient acknowledgement rate
        3. Referral acceptance rate
        4. Appointment attendance rate
        5. Drop-off recovery rate
        6. Median time to care
        7. Verified closure rate
        8. Overdue cases
        9. Unassigned cases
        """
        now = datetime.now(timezone.utc)

        # 1. Retrieve filtered cohort of cases
        case_query = db.query(CareCase)
        case_query = cls.apply_case_filters(case_query, from_date, to_date, status, provider_id)
        cases = case_query.all()
        case_ids = [c.id for c in cases]

        if not cases:
            return cls._empty_metrics_response()

        # ----------------------------------------------------------------------
        # Metric 1: Time from result to notification
        # ----------------------------------------------------------------------
        notification_durations_hours = []
        for case in cases:
            screening = db.query(ScreeningResult).filter(ScreeningResult.id == case.screening_result_id).first()
            if not screening:
                continue

            # Find earliest outbound communication or notification event
            comm = (
                db.query(Communication)
                .filter(Communication.case_id == case.id)
                .order_by(Communication.sent_at.asc())
                .first()
            )

            test_dt = screening.test_date
            if test_dt and test_dt.tzinfo is None:
                test_dt = test_dt.replace(tzinfo=timezone.utc)

            if comm and comm.sent_at:
                sent_dt = comm.sent_at
                if sent_dt.tzinfo is None:
                    sent_dt = sent_dt.replace(tzinfo=timezone.utc)
                diff = sent_dt - test_dt
                hours = max(0.1, diff.total_seconds() / 3600.0)
                notification_durations_hours.append(hours)
            else:
                # Fallback to case creation timestamp if communication not logged
                created_dt = case.created_at
                if created_dt and created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=timezone.utc)
                if test_dt:
                    diff = created_dt - test_dt
                    hours = max(0.1, diff.total_seconds() / 3600.0)
                    notification_durations_hours.append(hours)

        avg_notif_hours = round(statistics.mean(notification_durations_hours), 1) if notification_durations_hours else 0.0
        med_notif_hours = round(statistics.median(notification_durations_hours), 1) if notification_durations_hours else 0.0

        # ----------------------------------------------------------------------
        # Metric 2: Patient acknowledgement rate
        # ----------------------------------------------------------------------
        notified_cases = [c for c in cases if c.status != "result_received"]
        acknowledged_cases = 0
        for c in notified_cases:
            ctx = c.case_context or {}
            # Check context flag
            if ctx.get("patient_understanding_confirmed") is True:
                acknowledged_cases += 1
                continue
            # Check case status progression beyond initial notification
            if c.status in ("acknowledged", "referred", "appointment_booked", "appointment_scheduled",
                            "recovering", "consulted", "diagnostic_completed", "closed", "care_completed"):
                acknowledged_cases += 1
                continue
            # Check communication acknowledgment flags
            has_ack_comm = (
                db.query(Communication)
                .filter(Communication.case_id == c.id, Communication.acknowledged == True)
                .first()
            )
            if has_ack_comm:
                acknowledged_cases += 1

        ack_rate = round((acknowledged_cases / len(notified_cases) * 100.0), 1) if notified_cases else 0.0

        # ----------------------------------------------------------------------
        # Metric 3: Referral acceptance rate
        # ----------------------------------------------------------------------
        referrals = db.query(Referral).filter(Referral.case_id.in_(case_ids)).all()
        total_eval_referrals = [r for r in referrals if r.status != "draft"]
        accepted_referrals = [r for r in total_eval_referrals if r.status in ("accepted", "completed")]
        referral_acceptance_rate = (
            round((len(accepted_referrals) / len(total_eval_referrals) * 100.0), 1)
            if total_eval_referrals else 0.0
        )

        # ----------------------------------------------------------------------
        # Metric 4: Appointment attendance rate
        # ----------------------------------------------------------------------
        appts = db.query(Appointment).filter(Appointment.case_id.in_(case_ids)).all()
        eval_appts = [a for a in appts if a.status in ("attended", "no_show", "cancelled", "rescheduled")]
        attended_appts = [a for a in appts if a.status == "attended"]
        no_show_appts = [a for a in appts if a.status == "no_show"]
        attendance_rate = (
            round((len(attended_appts) / len(eval_appts) * 100.0), 1)
            if eval_appts else 0.0
        )

        # ----------------------------------------------------------------------
        # Metric 5: Drop-off recovery rate
        # ----------------------------------------------------------------------
        # Identify cases that experienced an interruption / stall
        stalled_cases = []
        for c in cases:
            ctx = c.case_context or {}
            has_no_show = any(a.status == "no_show" for a in appts if a.case_id == c.id)
            has_rescheduled = any(a.status == "rescheduled" for a in appts if a.case_id == c.id)
            if (
                c.status in ("recovering", "missed_visit", "escalated", "recovery_exhausted") or
                ctx.get("recovery_attempts", 0) > 0 or
                has_no_show or
                has_rescheduled
            ):
                stalled_cases.append(c)

        recovered_cases = 0
        for sc in stalled_cases:
            # Case recovered if it has an active booked/attended appointment following reschedule,
            # or reached consulted, diagnostic_completed, or closed
            case_appts = [a for a in appts if a.case_id == sc.id]
            has_recovered_appt = any(a.status in ("booked", "confirmed", "attended") for a in case_appts)
            if sc.status in ("consulted", "diagnostic_completed", "closed", "care_completed") or has_recovered_appt:
                recovered_cases += 1

        drop_off_recovery_rate = (
            round((recovered_cases / len(stalled_cases) * 100.0), 1)
            if stalled_cases else 0.0
        )

        # ----------------------------------------------------------------------
        # Metric 6: Median time to care
        # ----------------------------------------------------------------------
        time_to_care_days = []
        for c in cases:
            # Cases that reached clinical workup completion or closed
            if c.status in ("consulted", "diagnostic_completed", "closed", "care_completed"):
                screening = db.query(ScreeningResult).filter(ScreeningResult.id == c.screening_result_id).first()
                if not screening:
                    continue

                start_dt = screening.test_date or c.created_at
                if start_dt and start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)

                # End date: earliest of verified closure, attended appointment, or update
                closure_ev = (
                    db.query(ClosureEvidence)
                    .filter(ClosureEvidence.case_id == c.id, ClosureEvidence.is_verified == True)
                    .first()
                )
                end_dt = None
                if closure_ev and closure_ev.verified_at:
                    end_dt = closure_ev.verified_at
                else:
                    attended_a = next((a for a in appts if a.case_id == c.id and a.status == "attended"), None)
                    if attended_a and attended_a.attendance_recorded_at:
                        end_dt = attended_a.attendance_recorded_at
                    else:
                        end_dt = c.updated_at

                if end_dt and end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)

                if start_dt and end_dt:
                    days = max(1.0, (end_dt - start_dt).total_seconds() / 86400.0)
                    time_to_care_days.append(days)

        median_time_to_care = round(statistics.median(time_to_care_days), 1) if time_to_care_days else 0.0
        avg_time_to_care = round(statistics.mean(time_to_care_days), 1) if time_to_care_days else 0.0

        # ----------------------------------------------------------------------
        # Metric 7: Verified closure rate
        # ----------------------------------------------------------------------
        closed_cases = [c for c in cases if c.status in ("closed", "care_completed")]
        verified_closures = 0
        for cc in closed_cases:
            ev = (
                db.query(ClosureEvidence)
                .filter(ClosureEvidence.case_id == cc.id, ClosureEvidence.is_verified == True)
                .first()
            )
            if ev and ev.verifying_clinician_id:
                verified_closures += 1

        verified_closure_rate = (
            round((verified_closures / len(closed_cases) * 100.0), 1)
            if closed_cases else 0.0
        )

        # ----------------------------------------------------------------------
        # Metric 8: Overdue cases
        # ----------------------------------------------------------------------
        overdue_cases = [
            c for c in cases
            if c.status not in ("closed", "care_completed") and (
                (c.sla_deadline and (c.sla_deadline.replace(tzinfo=timezone.utc) if c.sla_deadline.tzinfo is None else c.sla_deadline) < now) or
                c.sla_status == "breached"
            )
        ]

        # ----------------------------------------------------------------------
        # Metric 9: Unassigned cases
        # ----------------------------------------------------------------------
        unassigned_cases = [
            c for c in cases
            if c.current_owner_id is None or c.status == "UNASSIGNED_ESCALATED"
        ]

        # ----------------------------------------------------------------------
        # Synthesize Complete Metrics Payload
        # ----------------------------------------------------------------------
        return {
            "summary": {
                "total_cases": len(cases),
                "active_cases": len([c for c in cases if c.status not in ("closed", "care_completed")]),
                "closed_cases": len(closed_cases),
                "stalled_cases": len(stalled_cases),
            },
            "metrics": {
                "time_from_result_to_notification": {
                    "average_hours": avg_notif_hours,
                    "median_hours": med_notif_hours,
                    "cases_measured": len(notification_durations_hours),
                    "formatted": f"{avg_notif_hours} hrs" if avg_notif_hours < 48 else f"{round(avg_notif_hours / 24.0, 1)} days",
                    "description": "Elapsed duration from screening test completion to initial outreach dispatch"
                },
                "patient_acknowledgement_rate": {
                    "rate_percent": ack_rate,
                    "acknowledged_count": acknowledged_cases,
                    "notified_count": len(notified_cases),
                    "formatted": f"{ack_rate}%",
                    "description": "Percentage of notified patients who confirmed receipt and comprehension"
                },
                "referral_acceptance_rate": {
                    "rate_percent": referral_acceptance_rate,
                    "accepted_count": len(accepted_referrals),
                    "total_referrals": len(total_eval_referrals),
                    "formatted": f"{referral_acceptance_rate}%",
                    "description": "Specialist referrals formally accepted within facility SLA"
                },
                "appointment_attendance_rate": {
                    "rate_percent": attendance_rate,
                    "attended_count": len(attended_appts),
                    "no_show_count": len(no_show_appts),
                    "total_evaluated": len(eval_appts),
                    "formatted": f"{attendance_rate}%",
                    "description": "Compliance rate for scheduled diagnostic appointments"
                },
                "drop_off_recovery_rate": {
                    "rate_percent": drop_off_recovery_rate,
                    "recovered_count": recovered_cases,
                    "stalled_count": len(stalled_cases),
                    "formatted": f"{drop_off_recovery_rate}%",
                    "description": "Interrupted or stalled journeys successfully recovered without losing ownership"
                },
                "median_time_to_care": {
                    "median_days": median_time_to_care,
                    "average_days": avg_time_to_care,
                    "cases_evaluated": len(time_to_care_days),
                    "formatted": f"{median_time_to_care} days",
                    "description": "Median days from screening result to verified diagnostic workup"
                },
                "verified_closure_rate": {
                    "rate_percent": verified_closure_rate,
                    "verified_closures": verified_closures,
                    "total_closed_cases": len(closed_cases),
                    "formatted": f"{verified_closure_rate}%",
                    "description": "Closed cases backed by physician-verified diagnostic or pathology evidence"
                },
                "overdue_cases": {
                    "count": len(overdue_cases),
                    "case_ids": [str(c.id) for c in overdue_cases],
                    "formatted": f"{len(overdue_cases)} cases",
                    "description": "Active care cases that have surpassed their clinical SLA deadline"
                },
                "unassigned_cases": {
                    "count": len(unassigned_cases),
                    "case_ids": [str(c.id) for c in unassigned_cases],
                    "formatted": f"{len(unassigned_cases)} cases",
                    "description": "Cases lacking accountable Care Coordinator ownership"
                }
            }
        }

    @classmethod
    def get_operational_dropoff_priorities(
        cls,
        db: Session,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        status: Optional[str] = None,
        provider_id: Optional[str] = None,
        tier_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Calculates operational drop-off risk prioritization for active cases.
        Analyzes patient interaction history and case progression milestones to prioritize
        cases requiring proactive coordinator outreach.

        GOVERNANCE NOTICE:
        Clearly explains operational reasons. Strictly non-clinical.
        """
        now = datetime.now(timezone.utc)

        case_query = db.query(CareCase).filter(CareCase.status.notin_(["closed", "care_completed"]))
        case_query = cls.apply_case_filters(case_query, from_date, to_date, status, provider_id)
        active_cases = case_query.all()

        prioritized_cases = []

        for case in active_cases:
            patient = db.query(Patient).filter(Patient.id == case.patient_id).first()
            owner = db.query(CaseOwner).filter(CaseOwner.id == case.current_owner_id).first() if case.current_owner_id else None
            comms = db.query(Communication).filter(Communication.case_id == case.id).order_by(Communication.sent_at.desc()).all()
            appts = db.query(Appointment).filter(Appointment.case_id == case.id).all()
            referrals = db.query(Referral).filter(Referral.case_id == case.id).all()
            ctx = case.case_context or {}

            score = 0
            operational_reasons = []

            # ------------------------------------------------------------------
            # Dimension A: Interaction History & Responsiveness Signals
            # ------------------------------------------------------------------
            if not comms:
                score += 25
                operational_reasons.append("Zero outbound communications recorded since screening result ingestion.")
            else:
                last_comm = comms[0]
                last_sent = last_comm.sent_at
                if last_sent and last_sent.tzinfo is None:
                    last_sent = last_sent.replace(tzinfo=timezone.utc)

                days_inactive = (now - last_sent).total_seconds() / 86400.0

                # Inbound response analysis
                inbound_comms = [c for c in comms if c.sender == "patient"]
                if not inbound_comms and days_inactive > 2:
                    score += 25
                    operational_reasons.append(f"Patient has not responded to outreach in {round(days_inactive, 1)} days.")
                elif days_inactive > 5:
                    score += 20
                    operational_reasons.append(f"No communication exchanged for over {int(days_inactive)} days.")

            # Inferred SDOH / Behavioral Barriers from Patient Profile & Messages
            barriers = ctx.get("inferred_barriers", [])
            if patient and patient.patient_context:
                barriers = list(set(barriers + patient.patient_context.get("known_barriers", [])))

            if barriers:
                score += min(30, len(barriers) * 15)
                barrier_labels = ", ".join(b.replace("_", " ") for b in barriers)
                operational_reasons.append(f"Documented coordination barriers: {barrier_labels}.")

            # ------------------------------------------------------------------
            # Dimension B: Case Progress & Milestone Signals
            # ------------------------------------------------------------------
            # Ownership Gap
            if not case.current_owner_id or case.status == "UNASSIGNED_ESCALATED":
                score += 45
                operational_reasons.append("CRITICAL: Case is unassigned with no designated Care Coordinator.")

            # SLA Countdown Status
            deadline = case.sla_deadline
            if deadline and deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)

            if case.sla_status == "breached" or (deadline and deadline < now):
                score += 40
                overdue_days = round((now - deadline).total_seconds() / 86400.0, 1) if deadline else 1.0
                operational_reasons.append(f"SLA deadline breached by {overdue_days} days without diagnostic workup completion.")
            elif case.sla_status == "warning":
                score += 25
                hours_left = max(0, round((deadline - now).total_seconds() / 3600.0, 1)) if deadline else 0
                operational_reasons.append(f"SLA Warning: Approximately {hours_left} hours remaining before deadline.")

            # Broken Appointments (No-shows / unrescheduled cancellations)
            no_shows = [a for a in appts if a.status == "no_show"]
            rescheduled_pending = [a for a in appts if a.status == "rescheduled"]
            if no_shows:
                score += 30
                operational_reasons.append(f"Patient recorded {len(no_shows)} unattended appointment (no-show).")
            elif rescheduled_pending and not any(a.status in ("booked", "confirmed") for a in appts):
                score += 20
                operational_reasons.append("Appointment was rescheduled but replacement date is not yet confirmed.")

            # Pending Referral Bottleneck
            pending_referrals = [r for r in referrals if r.status in ("sent", "draft")]
            for pr in pending_referrals:
                score += 15
                operational_reasons.append(f"Specialist referral to '{pr.target_facility}' is awaiting facility acceptance.")

            # Stalled Recovery Attempts
            rec_attempts = ctx.get("recovery_attempts", 0)
            if rec_attempts >= 2:
                score += 25
                operational_reasons.append(f"Multiple automated recovery attempts ({rec_attempts}) executed without complete resolution.")

            # Cap score at 100
            score = min(100, max(5, score))

            # Determine Tier
            if score >= 70:
                tier = "URGENT_FOLLOWUP"
            elif score >= 40:
                tier = "ELEVATED_ATTENTION"
            else:
                tier = "ON_TRACK"

            if tier_filter and tier_filter != "all" and tier.lower() != tier_filter.lower():
                continue

            prioritized_cases.append({
                "case_id": str(case.id),
                "case_number": case.case_number,
                "patient_id": str(patient.id) if patient else None,
                "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "Unknown",
                "patient_language": patient.preferred_language if patient else "en",
                "patient_phone": patient.phone if patient else None,
                "current_owner": owner.name if owner else "Unassigned",
                "current_owner_role": owner.role if owner else None,
                "status": case.status,
                "priority": case.priority,
                "sla_status": case.sla_status,
                "sla_deadline": case.sla_deadline.isoformat() if case.sla_deadline else None,
                "operational_risk_score": score,
                "priority_tier": tier,
                "operational_reasons": operational_reasons,
                "why_prioritized": " • ".join(operational_reasons) if operational_reasons else "Normal progression within standard operational parameters.",
                "barriers_detected": barriers,
                "recovery_attempts": rec_attempts,
                "disclaimer": "Operational coordination prioritization only. Does NOT indicate medical disease severity or clinical prognosis."
            })

        # Sort by highest operational risk score descending
        prioritized_cases.sort(key=lambda x: x["operational_risk_score"], reverse=True)
        return prioritized_cases

    @classmethod
    def get_filter_options(cls, db: Session) -> Dict[str, Any]:
        """Returns available providers and case statuses for dashboard filtering."""
        owners = db.query(CaseOwner).filter(CaseOwner.is_active == True).all()
        providers = [{"id": str(o.id), "name": o.name, "role": o.role, "facility": o.facility} for o in owners]
        providers.insert(0, {"id": "unassigned", "name": "Unassigned Cases Only", "role": "unassigned", "facility": "None"})
        providers.insert(0, {"id": "all", "name": "All Providers & Coordinators", "role": "all", "facility": "All"})

        statuses = [
            {"id": "all", "label": "All Case Statuses"},
            {"id": "active", "label": "All Active Cases"},
            {"id": "notified", "label": "Outreach Notified"},
            {"id": "acknowledged", "label": "Acknowledged"},
            {"id": "recovering", "label": "In Recovery / Missed Visit"},
            {"id": "referred", "label": "Referred to Specialist"},
            {"id": "appointment_booked", "label": "Appointment Booked"},
            {"id": "overdue", "label": "SLA Overdue / Breached"},
            {"id": "closed", "label": "Closed & Care Completed"}
        ]

        return {
            "providers": providers,
            "statuses": statuses
        }

    @classmethod
    def _empty_metrics_response(cls) -> Dict[str, Any]:
        """Graceful response when filtered cohort yields zero cases."""
        return {
            "summary": {"total_cases": 0, "active_cases": 0, "closed_cases": 0, "stalled_cases": 0},
            "metrics": {
                "time_from_result_to_notification": {"average_hours": 0.0, "median_hours": 0.0, "cases_measured": 0, "formatted": "0 hrs"},
                "patient_acknowledgement_rate": {"rate_percent": 0.0, "acknowledged_count": 0, "notified_count": 0, "formatted": "0%"},
                "referral_acceptance_rate": {"rate_percent": 0.0, "accepted_count": 0, "total_referrals": 0, "formatted": "0%"},
                "appointment_attendance_rate": {"rate_percent": 0.0, "attended_count": 0, "no_show_count": 0, "total_evaluated": 0, "formatted": "0%"},
                "drop_off_recovery_rate": {"rate_percent": 0.0, "recovered_count": 0, "stalled_count": 0, "formatted": "0%"},
                "median_time_to_care": {"median_days": 0.0, "average_days": 0.0, "cases_evaluated": 0, "formatted": "0 days"},
                "verified_closure_rate": {"rate_percent": 0.0, "verified_closures": 0, "total_closed_cases": 0, "formatted": "0%"},
                "overdue_cases": {"count": 0, "case_ids": [], "formatted": "0 cases"},
                "unassigned_cases": {"count": 0, "case_ids": [], "formatted": "0 cases"}
            }
        }
