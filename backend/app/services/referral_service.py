"""
CareBridge Referral Domain Service
Enforces distinct doctor clinical rationale vs AI educational explanation,
tracks patient decisions ("accept", "wait", "alternative", "clarification"),
manages SLA deadlines, receiving provider responses, and lifecycle advancement.
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.referral import Referral
from app.models.care_case import CareCase
from app.models.event_audit import CaseEvent, AuditLog

logger = logging.getLogger("carebridge.services.referral")


class ReferralError(Exception):
    """Base referral error."""
    pass


class ReferralClosedCaseError(ReferralError):
    """Raised when attempting referral action on closed case."""
    pass


class ReferralService:
    """Authoritative referral domain service."""

    @classmethod
    def create_referral(
        cls,
        db: Session,
        case_id: uuid.UUID,
        patient_id: uuid.UUID,
        referring_provider: str,
        target_facility: str,
        specialty: str,
        reason_for_referral: str,
        clinical_rationale: str,
        ai_educational_summary: Optional[str] = None,
        acceptance_deadline_hours: int = 48,
        idempotency_key: Optional[str] = None
    ) -> Referral:
        """
        Creates a formal specialist referral.
        Enforces clear separation between doctor clinical rationale and AI patient educational text.
        Advances Stage 7 (REFERRAL_INITIATED).
        """
        case = db.query(CareCase).filter(CareCase.id == case_id).first()
        if not case:
            raise ValueError(f"Case {case_id} not found")

        if case.status in ("closed", "VERIFIED_CLINICAL_CLOSURE"):
            raise ReferralClosedCaseError(f"Cannot create referral for closed case {case.case_number}.")

        if idempotency_key:
            existing = db.query(Referral).filter(Referral.idempotency_key == idempotency_key).first()
            if existing:
                return existing

        now = datetime.now(timezone.utc)
        deadline = now + timedelta(hours=acceptance_deadline_hours)

        ref = Referral(
            id=uuid.uuid4(),
            case_id=case_id,
            patient_id=patient_id,
            referring_provider=referring_provider,
            target_facility=target_facility,
            specialty=specialty,
            reason_for_referral=reason_for_referral,
            clinical_rationale=clinical_rationale,
            ai_educational_summary=ai_educational_summary,
            status="sent",
            acceptance_deadline=deadline,
            idempotency_key=idempotency_key
        )
        db.add(ref)

        ev = CaseEvent(
            id=uuid.uuid4(),
            case_id=case_id,
            event_type="referral_created",
            description=f"Specialist referral created to {target_facility} for {specialty}",
            event_data={
                "referral_id": str(ref.id),
                "specialty": specialty,
                "target_facility": target_facility,
                "deadline": deadline.isoformat()
            },
            timestamp=now
        )
        db.add(ev)

        # Attempt to advance Stage 7
        try:
            from app.services.lifecycle_service import LifecycleService
            LifecycleService.advance_stage(
                db=db,
                case_id=case_id,
                stage_ident=7,
                actor_role="doctor",
                actor_id=referring_provider,
                evidence={
                    "referral_id": str(ref.id),
                    "target_facility": target_facility,
                    "specialty": specialty,
                    "clinical_rationale": clinical_rationale
                },
                notes=f"Referral initiated by {referring_provider} to {target_facility}"
            )
        except Exception as e:
            logger.warning(f"Lifecycle stage 7 advance notice: {e}")

        return ref

    @classmethod
    def record_patient_decision(
        cls,
        db: Session,
        referral_id: uuid.UUID,
        patient_id: uuid.UUID,
        decision: str,
        notes: Optional[str] = None
    ) -> Referral:
        """
        Records patient decision on a referral: 'accept', 'wait', 'alternative', 'clarification'.
        """
        valid_decisions = ["accept", "wait", "alternative", "clarification"]
        if decision.lower() not in valid_decisions:
            raise ValueError(f"Invalid patient decision '{decision}'. Allowed: {valid_decisions}")

        ref = db.query(Referral).filter(Referral.id == referral_id).first()
        if not ref:
            raise ValueError(f"Referral {referral_id} not found")

        now = datetime.now(timezone.utc)
        ref.patient_decision = decision.lower()
        ref.patient_decision_at = now
        ref.patient_decision_notes = notes

        ev = CaseEvent(
            id=uuid.uuid4(),
            case_id=ref.case_id,
            event_type="referral_patient_decision",
            description=f"Patient recorded decision '{decision}' for referral {ref.id}",
            event_data={
                "referral_id": str(ref.id),
                "decision": decision,
                "notes": notes,
                "decided_at": now.isoformat()
            },
            timestamp=now
        )
        db.add(ev)

        return ref

    @classmethod
    def accept_referral(
        cls,
        db: Session,
        referral_id: uuid.UUID,
        receiving_provider_id: str,
        receiving_provider_name: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Referral:
        """
        Receiving facility/specialist accepts inbound referral.
        Advances Stage 8 (REFERRAL_ACCEPTED).
        """
        ref = db.query(Referral).filter(Referral.id == referral_id).first()
        if not ref:
            raise ValueError(f"Referral {referral_id} not found")

        now = datetime.now(timezone.utc)
        ref.status = "accepted"
        ref.responded_at = now

        # Advance Stage 8
        from app.services.lifecycle_service import LifecycleService
        LifecycleService.advance_stage(
            db=db,
            case_id=ref.case_id,
            stage_ident=8,
            actor_role="receiving_provider",
            actor_id=receiving_provider_id,
            actor_name=receiving_provider_name,
            evidence={
                "referral_id": str(ref.id),
                "accepted_at": now.isoformat(),
                "receiving_provider": receiving_provider_name or receiving_provider_id,
                "notes": notes
            },
            notes=f"Referral accepted by receiving provider {receiving_provider_name or receiving_provider_id}"
        )

        return ref
