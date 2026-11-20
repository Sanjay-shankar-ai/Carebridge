"""
Patient Behaviour Router (AI behaviours B1-B4).

Deterministic, tool-grounded flows that run BEFORE the generic cognitive engine.
Every statement that an action happened is built from a successful tool result in the same
turn; otherwise the reply says what is pending or what can be done.

Design:
  handle_turn(...)   -> BehaviourResult | None   (None = not a behaviour turn; use generic engine)
  finalize_turn(...) -> persists the outbound reply, then runs post-delivery actions
                        (e.g. completing Stage 4 only after the full text is persisted).
Works without an LLM. Conversation flow state is stored per (session, user, role).
"""

import re
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.care_case import CareCase
from app.models.communication import Communication
from app.models.patient import Patient
from app.models.transport import ConversationFlowState, TransportRequest

logger = logging.getLogger("carebridge.behaviour_router")


# --------------------------------------------------------------------------
# Intent triggers (misspellings and fragments tolerated by normalisation + stems)
# --------------------------------------------------------------------------
REPORT_PATTERNS = [
    r"report\s+summar", r"summar\w*\s+(of\s+)?(my\s+)?report", r"explain\s+(my\s+|the\s+)?(report|results?|findings)",
    r"what\s+(does|do|is)\s+(my\s+|the\s+)?(report|result)", r"(my\s+)?report\s+(what|wat)\s+sa", r"what\s+report\s+sa",
    r"read\s+(my\s+)?report", r"tell\s+me\s+(about\s+)?my\s+(report|results?)", r"want\s+(to\s+know\s+)?(my\s+)?report",
    r"que\s+dice\s+mi\s+informe", r"resumen\s+(de\s+)?mi\s+informe", r"explica\w*\s+mi\s+informe",
    r"ماذا\s+يقول\s+تقريري", r"ملخص\s+تقريري", r"اشرح\w*\s+(لي\s+)?تقريري",
]

TRANSPORT_PATTERNS = [
    r"\btransport\w*\b", r"\bneed\s+(a\s+)?ride\b", r"\bhelp\s+with\s+(a\s+)?ride\b", r"\bride\s+to\b",
    r"\bcan(?:'t|not|t)\s+travel\b", r"\bno\s+way\s+to\s+(reach|get)\b", r"\bno\s+ride\b",
    r"\bpick[\s-]?up\b", r"\btransporte\b", r"\bمواصلات\b", r"\bتوصيل\b",
]

COMPANION_YES_PATTERNS = [
    r"\b(daughter|son|husband|wife|sister|brother|mother|father|caregiver|companion|friend|family)\b",
    r"\bwith\s+me\b", r"\bcoming\s+with\b", r"\btravel\w*\s+with\b",
]

COMPANION_NO_PATTERNS = [
    r"\balone\b", r"\bjust\s+me\b", r"\bno\s+(caregiver|companion|one)\b", r"\bby\s+myself\b", r"\bonly\s+me\b",
]


def _lead_phrase() -> str:
    from app.core.config import settings
    mins = settings.TRANSPORT_LEAD_MINUTES
    return "1 hour" if mins == 60 else f"{mins} minutes"


def _detect_companion(text: str) -> Optional[bool]:
    if _any(COMPANION_NO_PATTERNS, text):
        return False
    if _any(COMPANION_YES_PATTERNS, text):
        return True
    return None


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def _any(patterns: List[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


@dataclass
class BehaviourResult:
    reply: str
    intent: str
    tool_observations: List[Dict[str, Any]] = field(default_factory=list)
    post_delivery: List[Dict[str, Any]] = field(default_factory=list)
    escalated: bool = False
    case_id: Optional[str] = None


class PatientBehaviourRouter:
    """Entry point used by the chat endpoint and by tests."""

    # ------------------------------------------------------------------
    # Flow state helpers (per conversation, user, role)
    # ------------------------------------------------------------------
    @classmethod
    def get_state(cls, db: Session, session_id, user_id, role: str) -> Dict[str, Any]:
        row = (
            db.query(ConversationFlowState)
            .filter(
                ConversationFlowState.session_id == session_id,
                ConversationFlowState.user_id == user_id,
                ConversationFlowState.role == role,
            )
            .first()
        )
        return dict(row.state or {}) if row else {}

    @classmethod
    def set_state(cls, db: Session, session_id, user_id, role: str, state: Dict[str, Any]) -> None:
        row = (
            db.query(ConversationFlowState)
            .filter(
                ConversationFlowState.session_id == session_id,
                ConversationFlowState.user_id == user_id,
                ConversationFlowState.role == role,
            )
            .first()
        )
        if row:
            row.state = dict(state)
        else:
            db.add(ConversationFlowState(
                id=uuid.uuid4(), session_id=session_id, user_id=user_id, role=role, state=dict(state)
            ))
        db.flush()

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------
    @classmethod
    def handle_turn(
        cls,
        db: Session,
        *,
        user_id,
        role: str,
        patient_id,
        session_id,
        message: str,
        case_id=None,
        language: str = "en",
        now: Optional[datetime] = None,
    ) -> Optional[BehaviourResult]:
        """Returns a BehaviourResult when a behaviour owns this turn, else None."""
        if (role or "").lower() != "patient" or not patient_id:
            return None
        text = _norm(message)
        pid = patient_id if isinstance(patient_id, uuid.UUID) else uuid.UUID(str(patient_id))
        state = cls.get_state(db, session_id, user_id, role) if session_id else {}

        # Active multi-turn transport continuations
        flow = state.get("flow")
        if flow in ("transport_select_appt", "transport_need_address"):
            return cls._continue_transport_flow(db, pid, user_id, role, session_id, message, text, state, language)
        if flow == "transport_update_details" and (
            _detect_companion(text) is not None or re.search(r"\b(yes|no|address|street|road|from)\b", text)
        ) and not _any(REPORT_PATTERNS, text) and not _any(TRANSPORT_PATTERNS, text):
            return cls._update_transport_details(db, pid, user_id, role, session_id, message, text, state, language)

        # B1 - report summary
        if _any(REPORT_PATTERNS, text):
            return cls._handle_report_summary(db, pid, language)

        # B2 - transport request
        if _any(TRANSPORT_PATTERNS, text):
            return cls._handle_transport_request(db, pid, user_id, role, session_id, message, text, language)

        return None

    # ------------------------------------------------------------------
    # B1 - Report summary in plain language
    # ------------------------------------------------------------------
    @classmethod
    def _handle_report_summary(cls, db: Session, patient_id: uuid.UUID, language: str) -> BehaviourResult:
        from app.services.report_explanation_service import ReportExplanationService

        res = ReportExplanationService.explain_report(db, patient_id, language=language)
        obs = [{"tool": "explain_report", "success": bool(res.get("success")), "result": {
            "state": res.get("state"), "stage_4_completed": False
        }}]
        state = res.get("state")
        case_id = res.get("case_id")

        if state == "ready":
            data = res["data"]
            return BehaviourResult(
                reply=data["full_text"],
                intent="report_explanation",
                tool_observations=obs,
                post_delivery=[{"action": "mark_report_delivered", "case_id": case_id, "language": language}],
                case_id=case_id,
            )
        if state == "unreadable":
            reply = (
                "I could not read the text of your report clearly, so I do not want to guess what it says. "
                "Your doctor can go through the original report with you. "
                "Would you like me to ask your doctor's team to review it with you?"
            )
        elif state == "no_case":
            reply = (
                "I cannot find a report in your record yet. Your care team will add it when it is ready, "
                "and I can tell you as soon as it appears."
            )
        else:  # not_finalized
            reply = (
                "Your report is not ready yet. A report only goes to your doctor and to you once it has been "
                "checked and finalized. When it is ready, your doctor will go through it with you, and I can "
                "explain it in plain words too. Would you like me to let your coordinator know you are waiting for it?"
            )
        return BehaviourResult(reply=reply, intent="report_explanation", tool_observations=obs, case_id=case_id)

    # ------------------------------------------------------------------
    # B2 - Transport requests
    # ------------------------------------------------------------------
    @classmethod
    def _handle_transport_request(
        cls, db: Session, patient_id: uuid.UUID, user_id, role: str, session_id,
        raw_message: str, text: str, language: str, selected_appt=None,
    ) -> BehaviourResult:
        from app.services.transport_service import TransportService

        appts = [selected_appt] if selected_appt else TransportService.find_candidate_appointments(db, patient_id)
        if not appts:
            if session_id:
                cls.set_state(db, session_id, user_id, role, {})
            if language == "es":
                reply = "Todavía no veo una cita próxima en su registro. ¿Quiere que primero le ayude a programar una cita?"
            elif language == "ar":
                reply = "لا أرى موعداً قادماً مسجلاً لديكِ حالياً. هل تودين أن أساعدكِ في حجز موعد أولاً؟"
            else:
                reply = (
                    "I do not see an upcoming appointment on your schedule yet, so I cannot request a ride just yet. "
                    "Would you like help booking an appointment first?"
                )
            return BehaviourResult(reply=reply, intent="transport_request")

        if len(appts) > 1:
            lines = [
                f"{i + 1}. {_utc(a.scheduled_time).strftime('%Y-%m-%d %H:%M')} with {a.provider_name}"
                for i, a in enumerate(appts[:3])
            ]
            if session_id:
                cls.set_state(db, session_id, user_id, role, {
                    "flow": "transport_select_appt",
                    "appointment_ids": [str(a.id) for a in appts[:3]],
                })
            reply = (
                "You have more than one upcoming appointment:\n"
                + "\n".join(lines)
                + "\n\nWhich appointment do you need transport for?"
            )
            return BehaviourResult(reply=reply, intent="transport_request", case_id=str(appts[0].case_id))

        appt = appts[0]
        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        profile_addr = ((patient.patient_context or {}).get("address") or "").strip() if patient else ""
        companion_hint = _detect_companion(text)

        if not profile_addr:
            if session_id:
                cls.set_state(db, session_id, user_id, role, {
                    "flow": "transport_need_address",
                    "appointment_id": str(appt.id),
                    "companion": companion_hint,
                })
            reply = (
                f"I can request a ride for your appointment at {_utc(appt.scheduled_time).strftime('%H:%M')}. "
                "What pickup address should we use?"
            )
            return BehaviourResult(reply=reply, intent="transport_request", case_id=str(appt.case_id))

        return cls._execute_transport_request(
            db, appt, profile_addr, companion_hint, patient_id, user_id, role, session_id, language
        )

    @classmethod
    def _continue_transport_flow(
        cls, db: Session, patient_id: uuid.UUID, user_id, role: str, session_id,
        raw_message: str, text: str, state: Dict[str, Any], language: str,
    ) -> BehaviourResult:
        from app.models.appointment import Appointment
        flow = state.get("flow")

        if flow == "transport_select_appt":
            ids = state.get("appointment_ids") or []
            chosen_id = None
            m = re.search(r"\b([1-3])\b", text)
            if m and int(m.group(1)) <= len(ids):
                chosen_id = ids[int(m.group(1)) - 1]
            else:
                for aid in ids:
                    a = db.query(Appointment).filter(Appointment.id == uuid.UUID(aid), Appointment.patient_id == patient_id).first()
                    if a and (a.scheduled_time.strftime("%H:%M") in text or a.provider_name.lower() in text):
                        chosen_id = aid
                        break
            if not chosen_id:
                return BehaviourResult(
                    reply="Please tell me the number (1, 2, or 3) or time of the appointment you need a ride for?",
                    intent="transport_request",
                )
            appt = db.query(Appointment).filter(
                Appointment.id == uuid.UUID(chosen_id), Appointment.patient_id == patient_id
            ).first()
            if not appt:
                cls.set_state(db, session_id, user_id, role, {})
                return BehaviourResult(reply="I could not find that appointment. Could you try again?", intent="transport_request")
            return cls._handle_transport_request(
                db, patient_id, user_id, role, session_id, raw_message, text, language, selected_appt=appt
            )

        # flow == "transport_need_address"
        appt_id = state.get("appointment_id")
        appt = db.query(Appointment).filter(
            Appointment.id == uuid.UUID(appt_id), Appointment.patient_id == patient_id
        ).first() if appt_id else None
        if not appt:
            cls.set_state(db, session_id, user_id, role, {})
            return BehaviourResult(reply="I could not find that appointment anymore. Would you like to check your schedule?", intent="transport_request")

        address = raw_message.strip()
        companion_hint = state.get("companion")
        if companion_hint is None:
            companion_hint = _detect_companion(text)
        return cls._execute_transport_request(
            db, appt, address, companion_hint, patient_id, user_id, role, session_id, language
        )

    @classmethod
    def _update_transport_details(
        cls, db: Session, patient_id: uuid.UUID, user_id, role: str, session_id,
        raw_message: str, text: str, state: Dict[str, Any], language: str,
    ) -> BehaviourResult:
        tr_id = state.get("transport_request_id")
        tr = db.query(TransportRequest).filter(
            TransportRequest.id == uuid.UUID(tr_id), TransportRequest.patient_id == patient_id
        ).first() if tr_id else None
        cls.set_state(db, session_id, user_id, role, {})
        if not tr:
            return BehaviourResult(reply="Thank you for letting me know. How else can I help?", intent="transport_request")

        comp = _detect_companion(text)
        if comp is None and re.search(r"\byes\b", text):
            comp = True
        elif comp is None and re.search(r"\bno\b", text):
            comp = False
        if comp is not None:
            tr.companion = comp
        m_addr = re.search(r"(?:from|address(?:\s+is)?)\s+(.+)", raw_message, re.I)
        if m_addr:
            tr.pickup_address = m_addr.group(1).strip()
        db.commit()
        comp_note = "a caregiver travelling with you" if tr.companion else "you travelling alone"
        reply = (
            f"Thank you. I have updated your pickup request for {tr.pickup_time.strftime('%H:%M')} "
            f"from {tr.pickup_address} with {comp_note}. Your care coordinator will confirm it soon."
        )
        return BehaviourResult(
            reply=reply,
            intent="transport_request",
            tool_observations=[{"tool": "update_transport_request", "success": True, "result": {"transport_request_id": str(tr.id)}}],
            case_id=str(tr.case_id),
        )

    @classmethod
    def _execute_transport_request(
        cls, db: Session, appt, address: str, companion_hint: Optional[bool],
        patient_id: uuid.UUID, user_id, role: str, session_id, language: str,
    ) -> BehaviourResult:
        from app.services.transport_service import TransportService

        pickup = TransportService.compute_pickup_time(appt.scheduled_time)
        res = TransportService.create_transport_request(
            db=db,
            appointment_id=appt.id,
            pickup_time=pickup,
            address=address,
            companion=bool(companion_hint),
            patient_id=patient_id,
            actor_role=role,
            actor_id=str(user_id),
        )
        obs = [{"tool": "create_transport_request", "success": bool(res.get("success")), "result": res}]
        coord = res.get("coordinator_name", "your care coordinator")

        if not res.get("success"):
            if session_id:
                cls.set_state(db, session_id, user_id, role, {})
            reply = (
                f"I tried to request your ride, but could not complete the request right now. "
                f"I have created a follow-up task for {coord} so they can help arrange your pickup directly. "
                "Would you like me to note any preferred phone number for them?"
            )
            return BehaviourResult(reply=reply, intent="transport_request", tool_observations=obs, case_id=str(appt.case_id))

        hhmm = res["pickup_hhmm"]
        lead = _lead_phrase()
        if session_id:
            cls.set_state(db, session_id, user_id, role, {
                "flow": "transport_update_details",
                "transport_request_id": res["transport_request_id"],
                "appointment_id": str(appt.id),
            })
        if language == "es":
            reply = (
                f"He solicitado un traslado a las {hhmm}, {lead} antes de su cita, "
                f"y pedí a {coord} que lo confirme. Le avisaré en cuanto esté confirmado."
            )
        elif language == "ar":
            reply = (
                f"لقد طلبت وسيلة نقل الساعة {hhmm}، قبل موعدكِ بـ {lead}، "
                f"وطلبت من {coord} تأكيد الطلب. سأبلغكِ فور تأكيده."
            )
        else:
            reply = (
                f"I have requested a pickup at {hhmm}, {lead} before your appointment, "
                f"and asked {coord} to confirm. I will tell you as soon as it is confirmed."
            )
            if companion_hint is None:
                reply += f" Will a caregiver travel with you from {address}?"
        return BehaviourResult(reply=reply, intent="transport_request", tool_observations=obs, case_id=str(appt.case_id))

    # ------------------------------------------------------------------
    # Persist reply + post-delivery actions
    # ------------------------------------------------------------------
    @classmethod
    def finalize_turn(
        cls,
        db: Session,
        result: BehaviourResult,
        *,
        session_id,
        patient_id,
        case_id=None,
        channel: str = "in_app_chat",
        language: str = "en",
    ) -> Communication:
        """Persist the full reply, THEN run post-delivery actions (e.g. complete Stage 4)."""
        cid = case_id or result.case_id
        comm = Communication(
            id=uuid.uuid4(),
            case_id=uuid.UUID(str(cid)) if cid else None,
            patient_id=uuid.UUID(str(patient_id)) if patient_id else None,
            session_id=session_id,
            sender="ai_coordinator",
            channel=channel,
            language=language,
            content=result.reply,
            acknowledged=True,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(comm)
        db.commit()  # the full text is durable before anything is marked delivered

        for action in result.post_delivery:
            try:
                if action.get("action") == "mark_report_delivered":
                    from app.services.report_explanation_service import ReportExplanationService
                    out = ReportExplanationService.mark_delivered(
                        db, action["case_id"], language=action.get("language", "en")
                    )
                    result.tool_observations.append({
                        "tool": "mark_report_delivered", "success": bool(out.get("success")), "result": out
                    })
            except Exception as exc:  # never break the chat turn
                logger.warning(f"Post-delivery action failed: {exc}")
        return comm
