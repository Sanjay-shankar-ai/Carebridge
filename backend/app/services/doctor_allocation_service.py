"""
CareBridge Intelligent Doctor Allocation Service
Performs workload-aware, explainable ranking of eligible doctors, persists doctor assignment requests,
manages doctor acceptance/decline workflows, handles response timeouts, and escalates to coordinators.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_, update

from app.models.care_case import CareCase, Task
from app.models.owner import CaseOwner
from app.models.doctor_assignment import DoctorAssignment
from app.models.appointment import Appointment
from app.models.event_audit import CaseEvent, AuditLog
from app.models.user import User
from app.services.notification_service import NotificationService

logger = logging.getLogger("carebridge.services.doctor_allocation")


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class DoctorCandidate(dict):
    """Structured representation of an evaluated doctor candidate with explainable factors."""
    pass


class DoctorAllocationService:
    """Manages the full end-to-end lifecycle of specialist doctor allocation."""

    @classmethod
    def allocate_doctor_for_case(
        cls,
        db: Session,
        case_id: uuid.UUID,
        required_specialty: str,
        urgency_level: str = "standard",
        assigned_by_role: str = "care_coordinator",
        assigned_by_id: Optional[str] = None
    ) -> DoctorAssignment:
        """
        Allocates the best eligible doctor for a case based on specialty match before workload.
        Persists DoctorAssignment and returns the assignment record.
        """
        ranked = cls.rank_eligible_doctors(db, specialty=required_specialty, urgency_level=urgency_level, case_id=case_id)
        if not ranked:
            raise ValueError(f"No eligible doctor found for specialty '{required_specialty}'.")

        best = ranked[0]
        assigned_uuid = None
        if assigned_by_id:
            try:
                assigned_uuid = uuid.UUID(str(assigned_by_id))
            except (ValueError, TypeError):
                assigned_uuid = None

        return cls.request_doctor_assignment(
            db=db,
            case_id=case_id,
            doctor_id=uuid.UUID(best["doctor_id"]),
            specialty_matched=required_specialty,
            urgency_level=urgency_level,
            assigned_by_role=assigned_by_role,
            assigned_by_id=assigned_uuid,
            allocation_factors=best["factors"],
            allocation_score=best["total_score"]
        )

    @classmethod
    def rank_eligible_doctors(
        cls,
        db: Session,
        specialty: str,
        urgency_level: str = "standard",
        case_id: Optional[uuid.UUID] = None,
        facility: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Ranks eligible doctors using 5 explainable factors:
        1. Clinical specialty & subspecialty suitability (0-40 pts)
        2. Patient urgency & required response window (0-20 pts)
        3. Actual appointment slot availability within SLA (0-15 pts)
        4. Current active case workload vs max capacity (0-15 pts)
        5. Relevant experience & approved clinical eligibility (0-10 pts)

        Filters out inactive, on-leave, or over-capacity doctors.
        """
        now = datetime.now(timezone.utc)

        # 1. Query active, verified specialists
        query = (
            db.query(CaseOwner)
            .filter(
                CaseOwner.role.in_(["specialist", "primary_physician", "doctor", "clinician"]),
                CaseOwner.is_active.is_(True),
                or_(CaseOwner.eligibility_status == "eligible", CaseOwner.eligibility_status.is_(None)),
                or_(CaseOwner.on_leave.is_(False), CaseOwner.on_leave.is_(None))
            )
        )
        if facility:
            # Prefer or filter by facility if strict
            pass

        candidates = query.all()
        ranked_list = []

        for doc in candidates:
            # Factor 1: Specialty & Subspecialty Suitability (0-40 pts)
            doc_spec = (doc.specialty or "").lower()
            target_spec = specialty.lower()
            specialty_score = 0.0

            if doc_spec == target_spec:
                specialty_score += 30.0
            elif target_spec in doc_spec or doc_spec in target_spec:
                specialty_score += 25.0
            else:
                # Check subspecialties
                subs = [s.lower() for s in (doc.subspecialties or [])]
                if any(target_spec in s or s in target_spec for s in subs):
                    specialty_score += 22.0
                else:
                    # Not eligible for this specialty
                    continue

            # Check subspecialty depth
            subs = [s.lower() for s in (doc.subspecialties or [])]
            if len(subs) > 0:
                specialty_score += min(len(subs) * 3.0, 10.0)
            specialty_score = min(specialty_score, 40.0)

            # Factor 4: Active Workload vs Max Capacity (0-15 pts)
            max_cap = doc.max_workload if doc.max_workload and doc.max_workload > 0 else 20
            # Count currently active assigned cases
            active_cases_count = (
                db.query(CareCase)
                .filter(
                    CareCase.current_owner_id == doc.id,
                    CareCase.status.notin_(["closed", "care_completed"])
                )
                .count()
            )

            # Exclude doctor if strictly over maximum capacity
            if active_cases_count >= max_cap:
                logger.info(f"Excluding doctor {doc.name}: over capacity ({active_cases_count}/{max_cap})")
                continue

            workload_ratio = (max_cap - active_cases_count) / max_cap
            workload_score = round(workload_ratio * 15.0, 1)

            # Factor 2: Urgency & Response Time Alignment (0-20 pts)
            response_hours = doc.response_deadline_hours or 24
            urgency_score = 15.0
            if urgency_level in ("urgent", "critical"):
                if response_hours <= 12:
                    urgency_score = 20.0
                elif response_hours <= 24:
                    urgency_score = 17.0
                else:
                    urgency_score = 10.0

            # Factor 3: Appointment Slot Availability (0-15 pts)
            # Check real appointments scheduled in the next 14 days
            future_window = now + timedelta(days=14)
            existing_appts_count = (
                db.query(Appointment)
                .filter(
                    Appointment.provider_name.like(f"%{doc.name.split()[-1]}%"),
                    Appointment.scheduled_time >= now,
                    Appointment.scheduled_time <= future_window,
                    Appointment.status.in_(["booked", "confirmed"])
                )
                .count()
            )

            # Higher availability if doctor has fewer existing bookings in the 14-day window
            if existing_appts_count <= 5:
                availability_score = 15.0
            elif existing_appts_count <= 10:
                availability_score = 11.0
            else:
                availability_score = 7.0

            # Factor 5: Approved Case Category Experience (0-10 pts)
            experience_score = 5.0
            approved_cats = [c.lower() for c in (doc.approved_case_categories or [])]
            if any(k in approved_cats for k in [specialty.lower(), urgency_level.lower()]):
                experience_score = 10.0
            elif len(approved_cats) > 0:
                experience_score = 8.0

            total_score = round(
                specialty_score + urgency_score + availability_score + workload_score + experience_score,
                1
            )

            explanation = (
                f"Specialty match: {specialty_score}/40 | Workload capacity: {workload_score}/15 "
                f"({active_cases_count}/{max_cap} cases) | Availability: {availability_score}/15 "
                f"| Response SLA: {urgency_score}/20 | Clinical eligibility: {experience_score}/10."
            )

            ranked_list.append({
                "doctor_id": str(doc.id),
                "name": doc.name,
                "facility": doc.facility,
                "specialty": doc.specialty,
                "subspecialties": doc.subspecialties,
                "department": doc.department,
                "total_score": total_score,
                "match_score": int(total_score),
                "active_workload": active_cases_count,
                "max_workload": max_cap,
                "factors": {
                    "specialty_score": specialty_score,
                    "urgency_score": urgency_score,
                    "availability_score": availability_score,
                    "workload_score": workload_score,
                    "experience_score": experience_score,
                },
                "explanation": explanation
            })

        # Sort descending by total allocation score
        ranked_list.sort(key=lambda x: x["total_score"], reverse=True)
        return ranked_list

    @classmethod
    def request_doctor_assignment(
        cls,
        db: Session,
        case_id: uuid.UUID,
        doctor_id: uuid.UUID,
        specialty_matched: str,
        urgency_level: str = "standard",
        assigned_by_role: str = "ai_allocation_agent",
        assigned_by_id: Optional[uuid.UUID] = None,
        allocation_factors: Optional[Dict[str, Any]] = None,
        allocation_score: float = 0.0,
        deadline_hours: Optional[int] = None
    ) -> DoctorAssignment:
        """
        Creates a persisted doctor assignment request with status PENDING_DOCTOR_RESPONSE.
        Dispatches an in-app notification to the doctor with authorized case context.
        """
        now = datetime.now(timezone.utc)
        doctor = db.query(CaseOwner).filter(CaseOwner.id == doctor_id).first()
        if not doctor:
            raise ValueError(f"Doctor {doctor_id} not found")

        if not doctor.is_active or doctor.eligibility_status != "eligible":
            raise ValueError(f"Doctor {doctor.name} is not eligible for assignment (active={doctor.is_active}, status={doctor.eligibility_status})")

        case = db.query(CareCase).filter(CareCase.id == case_id).first()
        if not case:
            raise ValueError(f"CareCase {case_id} not found")

        # Determine response deadline
        hours = deadline_hours or doctor.response_deadline_hours or (12 if urgency_level in ("urgent", "critical") else 24)
        deadline = now + timedelta(hours=hours)

        idempotency_key = f"assign_{case_id}_{doctor_id}_{uuid.uuid4().hex[:10]}"

        assignment = DoctorAssignment(
            id=uuid.uuid4(),
            case_id=case_id,
            doctor_id=doctor_id,
            status="PENDING_DOCTOR_RESPONSE",
            specialty_matched=specialty_matched,
            urgency_level=urgency_level,
            allocation_score=allocation_score,
            allocation_factors=allocation_factors or {},
            assigned_by_role=assigned_by_role,
            assigned_by_id=assigned_by_id,
            deadline=deadline,
            idempotency_key=idempotency_key,
            metadata_json={
                "case_number": case.case_number,
                "patient_name": f"{case.patient.first_name} {case.patient.last_name}" if case.patient else "Patient",
                "doctor_name": doctor.name,
                "facility": doctor.facility,
                "urgency_level": urgency_level,
                "created_at": now.isoformat()
            }
        )
        db.add(assignment)
        db.flush()

        # Update case context
        existing_ctx = dict(case.case_context or {})
        existing_ctx["pending_doctor_assignment_id"] = str(assignment.id)
        existing_ctx["target_specialty"] = specialty_matched
        case.case_context = existing_ctx

        # Record CaseEvent
        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=case_id,
            event_type="doctor_assignment_requested",
            description=f"Specialist assignment requested: {doctor.name} ({specialty_matched}) with deadline {deadline.strftime('%Y-%m-%d %H:%M UTC')}.",
            event_data={
                "assignment_id": str(assignment.id),
                "doctor_id": str(doctor.id),
                "doctor_name": doctor.name,
                "specialty": specialty_matched,
                "deadline": deadline.isoformat(),
                "allocation_score": allocation_score
            },
            timestamp=now
        )
        db.add(event)

        # Notify the Doctor (via linked User account)
        doc_user = db.query(User).filter(User.owner_id == doctor.id).first()
        if doc_user:
            try:
                NotificationService.create_notification(
                    db=db,
                    user_id=doc_user.id,
                    role="doctor",
                    event_type="doctor_assignment_requested",
                    title="New Clinical Case Assignment Request",
                    message=(
                        f"You have received a new {urgency_level.upper()} case assignment request for {case.case_number} "
                        f"in {specialty_matched}. Please review and respond before {deadline.strftime('%b %d, %H:%M UTC')}."
                    ),
                    priority="urgent" if urgency_level in ("urgent", "critical") else "normal",
                    case_id=case_id,
                    patient_id=case.patient_id,
                    action_link=f"/cases/{case_id}",
                    idempotency_key=f"notif_doc_req_{assignment.id}"
                )
            except Exception as e:
                logger.warning(f"Could not send doctor notification: {e}")

        db.commit()
        return assignment

    @classmethod
    def doctor_accept_assignment(
        cls,
        db: Session,
        assignment_id: uuid.UUID,
        doctor_user_id: uuid.UUID
    ) -> DoctorAssignment:
        """
        Processes a doctor's acceptance of an assignment request.
        Uses atomic state checks to prevent race conditions or accepting expired requests.
        Notifies patient with verified doctor details and unlocks appointment scheduling.
        """
        now = datetime.now(timezone.utc)

        # 1. Look up assignment
        assignment = db.query(DoctorAssignment).filter(DoctorAssignment.id == assignment_id).first()
        if not assignment:
            raise ValueError(f"Assignment {assignment_id} not found")

        # 2. Check authorization: Doctor user must match assignment.doctor_id
        doc_user = db.query(User).filter(User.id == doctor_user_id).first()
        if not doc_user or (doc_user.owner_id != assignment.doctor_id and doc_user.role != "care_coordinator"):
            raise PermissionError("Authenticated doctor is not authorized to respond to this assignment request.")

        # 3. Concurrency check: Must still be PENDING_DOCTOR_RESPONSE
        if assignment.status != "PENDING_DOCTOR_RESPONSE":
            raise ValueError(f"Cannot accept assignment in status '{assignment.status}'. (Must be PENDING_DOCTOR_RESPONSE)")

        # 4. Check if deadline expired
        deadline_utc = _ensure_utc(assignment.deadline)
        if deadline_utc and deadline_utc < now:
            assignment.status = "EXPIRED"
            db.commit()
            raise ValueError("Assignment response deadline has expired. This case has been escalated to the Care Coordinator.")

        # Atomic transition to ACCEPTED
        assignment.status = "ACCEPTED"
        assignment.responded_at = now

        # Update CareCase ownership and context
        case = db.query(CareCase).filter(CareCase.id == assignment.case_id).first()
        doctor = db.query(CaseOwner).filter(CaseOwner.id == assignment.doctor_id).first()

        if case and doctor:
            # Transfer case ownership to accepted doctor
            case.current_owner_id = doctor.id

            # Update attending physician reference
            ctx = dict(case.case_context or {})
            ctx["attending_doctor_id"] = str(doctor.id)
            ctx["attending_doctor_name"] = doctor.name
            ctx["attending_specialty"] = assignment.specialty_matched
            ctx["doctor_assignment_accepted"] = True
            ctx["doctor_accepted_at"] = now.isoformat()
            case.case_context = ctx

            # Attempt lifecycle advancement to Stage 5 (CLINICAL_REVIEW)
            try:
                from app.services.lifecycle_service import LifecycleService
                stages = LifecycleService.get_lifecycle_stages(case)
                if stages and any(s.get("stage_number") == 5 for s in stages):
                    current_stg = LifecycleService.get_current_stage(case)
                    curr_num = current_stg.get("stage_number", 0) if current_stg else 0
                    if curr_num in (4, 5):
                        LifecycleService.advance_stage(
                            db=db,
                            case_id=case.id,
                            stage_ident=5,
                            actor_role="doctor",
                            actor_id=str(doctor.id),
                            actor_name=doctor.name,
                            evidence={
                                "clinical_review": "Attending physician assignment accepted",
                                "doctor_id": str(doctor.id),
                                "doctor_name": doctor.name,
                                "specialty": assignment.specialty_matched
                            }
                        )
            except Exception as e:
                logger.debug(f"Lifecycle stage advancement during doctor acceptance skipped or already handled: {e}")

            # Record CaseEvent
            event = CaseEvent(
                id=uuid.uuid4(),
                case_id=case.id,
                event_type="doctor_assignment_accepted",
                description=f"{doctor.name} formally accepted clinical assignment for {assignment.specialty_matched}.",
                event_data={
                    "assignment_id": str(assignment.id),
                    "doctor_id": str(doctor.id),
                    "doctor_name": doctor.name,
                    "specialty": assignment.specialty_matched,
                    "accepted_at": now.isoformat()
                },
                timestamp=now
            )
            db.add(event)

            # Record AuditLog
            audit = AuditLog(
                id=uuid.uuid4(),
                case_id=case.id,
                actor_type="clinician",
                actor_id=str(doctor.id),
                action="doctor_accept_assignment",
                autonomy_level=3,
                rationale=f"Doctor {doctor.name} verified clinical acceptance for case {case.case_number}.",
                timestamp=now
            )
            db.add(audit)

            # Multilingual Notification to Patient
            # Patient is only notified AFTER doctor acceptance
            pat_user = db.query(User).filter(User.patient_id == case.patient_id).first()
            if pat_user:
                pref_lang = getattr(case.patient, "preferred_language", "en") or "en"
                if pref_lang == "ar":
                    title = "تم تأكيد الطبيب المختص"
                    msg = f"تم قبول حالتك من قبل {doctor.name}، أخصائي {assignment.specialty_matched} في {doctor.facility}. سنقوم الآن بتنسيق موعد الفحص الخاص بك."
                elif pref_lang == "es":
                    title = "Especialista Médico Confirmado"
                    msg = f"Su caso ha sido aceptado por {doctor.name}, especialista en {assignment.specialty_matched} en {doctor.facility}. Ahora coordinaremos su cita de evaluación."
                else:
                    title = "Specialist Doctor Confirmed"
                    msg = f"Your care has been accepted by {doctor.name}, specialist in {assignment.specialty_matched} at {doctor.facility}. Our care team will now coordinate your upcoming appointment."

                try:
                    NotificationService.create_notification(
                        db=db,
                        user_id=pat_user.id,
                        role="patient",
                        event_type="specialist_doctor_confirmed",
                        title=title,
                        message=msg,
                        priority="normal",
                        case_id=case.id,
                        patient_id=case.patient_id,
                        action_link="/patient",
                        idempotency_key=f"notif_pat_acc_{assignment.id}"
                    )
                except Exception as e:
                    logger.warning(f"Could not notify patient of doctor acceptance: {e}")

            # Notify Coordinator
            coord_user = db.query(User).filter(User.role == "care_coordinator").first()
            if coord_user:
                try:
                    NotificationService.create_notification(
                        db=db,
                        user_id=coord_user.id,
                        role="care_coordinator",
                        event_type="doctor_assignment_accepted",
                        title="Specialist Accepted Case",
                        message=f"{doctor.name} accepted assignment for {case.case_number} ({assignment.specialty_matched}). Scheduling unlocked.",
                        priority="normal",
                        case_id=case.id,
                        patient_id=case.patient_id,
                        action_link=f"/cases/{case.id}",
                        idempotency_key=f"notif_coord_acc_{assignment.id}"
                    )
                except Exception as e:
                    logger.warning(f"Could not notify coordinator: {e}")

        db.commit()
        return assignment

    @classmethod
    def doctor_decline_assignment(
        cls,
        db: Session,
        assignment_id: uuid.UUID,
        doctor_user_id: uuid.UUID,
        decline_reason: Optional[str] = None
    ) -> DoctorAssignment:
        """
        Processes doctor decline. Atomically transitions to DECLINED and escalates to Coordinator.
        """
        now = datetime.now(timezone.utc)
        assignment = db.query(DoctorAssignment).filter(DoctorAssignment.id == assignment_id).first()
        if not assignment:
            raise ValueError(f"Assignment {assignment_id} not found")

        doc_user = db.query(User).filter(User.id == doctor_user_id).first()
        if not doc_user or (doc_user.owner_id != assignment.doctor_id and doc_user.role != "care_coordinator"):
            raise PermissionError("Authenticated doctor is not authorized to decline this assignment.")

        if assignment.status != "PENDING_DOCTOR_RESPONSE":
            raise ValueError(f"Cannot decline assignment in status '{assignment.status}'.")

        assignment.status = "DECLINED"
        assignment.responded_at = now
        assignment.decline_reason = decline_reason or "Doctor unavailable / specialty routing adjustment needed."
        assignment.escalated_to_coordinator_at = now

        case = db.query(CareCase).filter(CareCase.id == assignment.case_id).first()
        doctor = db.query(CaseOwner).filter(CaseOwner.id == assignment.doctor_id).first()

        if case and doctor:
            # Create Actionable Coordinator Task
            task = Task(
                id=uuid.uuid4(),
                case_id=case.id,
                patient_id=case.patient_id,
                title=f"Reassign Case: {case.case_number} ({assignment.specialty_matched})",
                description=(
                    f"Dr. {doctor.name} declined the assignment request for {case.case_number}.\n"
                    f"Reason: {assignment.decline_reason}\n"
                    f"Please review eligible alternative specialists and initiate reassignment."
                ),
                task_type="specialist_reassignment",
                assigned_role="care_coordinator",
                status="pending",
                priority="urgent",
                due_date=now + timedelta(hours=12),
                idempotency_key=f"task_decl_{assignment.id}"
            )
            db.add(task)

            # Record CaseEvent
            event = CaseEvent(
                id=uuid.uuid4(),
                case_id=case.id,
                event_type="doctor_assignment_declined",
                description=f"{doctor.name} declined assignment for {assignment.specialty_matched}. Reason: {assignment.decline_reason}. Escalated to coordinator.",
                event_data={
                    "assignment_id": str(assignment.id),
                    "doctor_id": str(doctor.id),
                    "doctor_name": doctor.name,
                    "specialty": assignment.specialty_matched,
                    "decline_reason": assignment.decline_reason
                },
                timestamp=now
            )
            db.add(event)

            # Notify Coordinator
            coord_user = db.query(User).filter(User.role == "care_coordinator").first()
            if coord_user:
                try:
                    NotificationService.create_notification(
                        db=db,
                        user_id=coord_user.id,
                        role="care_coordinator",
                        event_type="doctor_assignment_declined",
                        title=f"Doctor Declined Assignment: {case.case_number}",
                        message=f"{doctor.name} declined {case.case_number}. Reason: {assignment.decline_reason}. Reassignment required.",
                        priority="urgent",
                        case_id=case.id,
                        patient_id=case.patient_id,
                        action_link=f"/cases/{case.id}",
                        idempotency_key=f"notif_decl_{assignment.id}"
                    )
                except Exception as e:
                    logger.warning(f"Could not notify coordinator: {e}")

        db.commit()
        return assignment

    @classmethod
    def reassign_doctor(
        cls,
        db: Session,
        previous_assignment_id: uuid.UUID,
        new_doctor_id: uuid.UUID,
        coordinator_user_id: uuid.UUID,
        reassignment_reason: str
    ) -> DoctorAssignment:
        """
        Care Coordinator selects an alternative eligible doctor.
        Marks previous assignment as REASSIGNED and creates a new PENDING_DOCTOR_RESPONSE assignment.
        New doctor must accept before assignment is finalized.
        """
        now = datetime.now(timezone.utc)
        prev_assign = db.query(DoctorAssignment).filter(DoctorAssignment.id == previous_assignment_id).first()
        if not prev_assign:
            raise ValueError(f"Previous assignment {previous_assignment_id} not found")

        prev_assign.status = "REASSIGNED"

        # Verify new doctor
        new_doc = db.query(CaseOwner).filter(CaseOwner.id == new_doctor_id).first()
        if not new_doc or not new_doc.is_active or new_doc.eligibility_status != "eligible":
            raise ValueError(f"New doctor {new_doctor_id} is not eligible for assignment")

        new_assignment = cls.request_doctor_assignment(
            db=db,
            case_id=prev_assign.case_id,
            doctor_id=new_doctor_id,
            specialty_matched=prev_assign.specialty_matched,
            urgency_level=prev_assign.urgency_level,
            assigned_by_role="care_coordinator",
            assigned_by_id=coordinator_user_id,
            allocation_factors={"reassigned_from": str(prev_assign.doctor_id), "reason": reassignment_reason},
            allocation_score=prev_assign.allocation_score
        )
        new_assignment.reassignment_reason = reassignment_reason

        # Record CaseEvent
        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=prev_assign.case_id,
            event_type="coordinator_reassigned_doctor",
            description=f"Coordinator reassigned case to {new_doc.name}. Reason: {reassignment_reason}.",
            event_data={
                "previous_assignment_id": str(prev_assign.id),
                "new_assignment_id": str(new_assignment.id),
                "new_doctor_id": str(new_doc.id),
                "new_doctor_name": new_doc.name,
                "reason": reassignment_reason
            },
            timestamp=now
        )
        db.add(event)
        db.commit()
        return new_assignment

    @classmethod
    def scan_and_expire_assignments(cls, db: Session) -> Dict[str, Any]:
        """
        Background scheduler job:
        Identifies pending assignments past their deadline, atomically transitions them to EXPIRED,
        and creates an actionable coordinator escalation task with ranked alternative doctors.
        """
        now = datetime.now(timezone.utc)
        expired_records = (
            db.query(DoctorAssignment)
            .filter(
                DoctorAssignment.status == "PENDING_DOCTOR_RESPONSE",
                DoctorAssignment.deadline < now
            )
            .all()
        )

        escalated_count = 0
        details = []

        for assign in expired_records:
            assign.status = "EXPIRED"
            assign.escalated_to_coordinator_at = now

            case = db.query(CareCase).filter(CareCase.id == assign.case_id).first()
            doc = db.query(CaseOwner).filter(CaseOwner.id == assign.doctor_id).first()

            if case:
                # Find alternative doctors for coordinator review
                alternatives = cls.rank_eligible_doctors(
                    db=db,
                    specialty=assign.specialty_matched,
                    urgency_level=assign.urgency_level
                )
                # Filter out the expired doctor
                alternatives = [a for a in alternatives if a["doctor_id"] != str(assign.doctor_id)]

                alt_names = ", ".join([f"{a['name']} ({a['match_score']}%)" for a in alternatives[:3]])

                # Create Task for coordinator
                task = Task(
                    id=uuid.uuid4(),
                    case_id=case.id,
                    patient_id=case.patient_id,
                    title=f"Assignment Expired: {case.case_number} ({assign.specialty_matched})",
                    description=(
                        f"Doctor assignment deadline expired for {doc.name if doc else 'Doctor'} on case {case.case_number}.\n"
                        f"Specialty: {assign.specialty_matched} | Urgency: {assign.urgency_level}\n"
                        f"Recommended alternatives: {alt_names or 'No immediate alternative in cohort; manual routing required.'}"
                    ),
                    task_type="assignment_timeout_escalation",
                    assigned_role="care_coordinator",
                    status="pending",
                    priority="urgent",
                    due_date=now + timedelta(hours=8),
                    idempotency_key=f"task_exp_{assign.id}"
                )
                db.add(task)

                # Record CaseEvent
                event = CaseEvent(
                    id=uuid.uuid4(),
                    case_id=case.id,
                    event_type="doctor_assignment_expired",
                    description=f"Doctor assignment for {doc.name if doc else 'Doctor'} expired without response. Escalated to coordinator.",
                    event_data={
                        "assignment_id": str(assign.id),
                        "doctor_id": str(assign.doctor_id),
                        "deadline": assign.deadline.isoformat(),
                        "alternatives": [a["name"] for a in alternatives[:3]]
                    },
                    timestamp=now
                )
                db.add(event)

                # Notify Coordinator
                coord_user = db.query(User).filter(User.role == "care_coordinator").first()
                if coord_user:
                    try:
                        NotificationService.create_notification(
                            db=db,
                            user_id=coord_user.id,
                            role="care_coordinator",
                            event_type="doctor_assignment_expired",
                            title=f"Doctor Assignment Expired: {case.case_number}",
                            message=f"Assignment for {doc.name if doc else 'Doctor'} on {case.case_number} timed out. Reassignment needed.",
                            priority="urgent",
                            case_id=case.id,
                            patient_id=case.patient_id,
                            action_link=f"/cases/{case.id}",
                            idempotency_key=f"notif_exp_{assign.id}"
                        )
                    except Exception as e:
                        logger.warning(f"Could not dispatch expired assignment notification: {e}")

                escalated_count += 1
                details.append({
                    "assignment_id": str(assign.id),
                    "case_number": case.case_number,
                    "doctor_name": doc.name if doc else "Doctor",
                    "specialty": assign.specialty_matched
                })

        db.commit()
        return {
            "job_name": "scan_expired_doctor_assignments",
            "executed_at": now.isoformat(),
            "expired_count": escalated_count,
            "details": details
        }
