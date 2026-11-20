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

CANCEL_PATTERNS = [
    r"\bcancel\w*\s+(my\s+|the\s+)?(appointment|visit|consultation|booking)\b",
    r"\bneed\s+to\s+cancel\b", r"\bwant\s+to\s+cancel\b", r"\bi\s+can(?:'t|not|t)\s+come\b",
    r"\bcan(?:'t|not|t)\s+make\s+it\b", r"\bcancelar\s+mi\s+cita\b", r"\bno\s+puedo\s+ir\b",
    r"\bإلغاء\s+موعدي\b", r"\bلا\s+أستطيع\s+الحضور\b",
]

EXPLICIT_CANCEL_CONFIRM_PATTERNS = [
    r"\byes[\s,]+cancel\b", r"\bconfirm\s+cancel\w*\b", r"\bs[ií][\s,]+cancelar\b", r"\bنعم[\s،,]+إلغاء\b",
]

FEAR_PATTERNS = [
    r"\bscared\b", r"\bafraid\b", r"\bterrified\b", r"\bpanic\w*\b", r"\bfrightened\b",
    r"\bis\s+it\s+cancer\b", r"\bdo\s+i\s+have\s+cancer\b", r"\bhave\s+cancer\b",
    r"\bgoing\s+to\s+die\b", r"\bgonna\s+die\b", r"\bwill\s+i\s+die\b",
    r"\btengo\s+miedo\b", r"\basustad[oa]\b", r"\bes\s+c[aá]ncer\b", r"\bvoy\s+a\s+morir\b",
    r"\bخائف[ة]?\b", r"\bمرعوب[ة]?\b", r"\bهل\s+هو\s+سرطان\b", r"\bهل\s+سأموت\b",
]

GREETING_PATTERNS = [
    r"^\s*(hi|hello|hey|good\s+morning|good\s+afternoon|good\s+evening|greetings|hola|buenos\s+d[ií]as|buenas\s+tardes|مرحبا|أهلا|السلام\s+عليكم)(\s+there|\s+carebridge)?[!.,?\s]*$",
]

SCREENING_REQUEST_PATTERNS = [
    r"\b(schedule|request|book|need|want|arrange|submit)\b.*\b(mammogram|screening|colonoscopy|cervical|pap\s+smear)\b",
    r"\broutine\s+(mammogram|screening)\b",
    r"\b(mammogram|screening)\b.*\b(schedule|request|intake|order)\b",
    r"\bprogramar\b.*\b(mamograf[ií]a|detecci[oó]n|tamizaje)\b",
    r"\bحجز\b.*\b(فحص|ماموجرام)\b",
]

CARE_JOURNEY_PATTERNS = [
    r"\bwhere\s+am\s+i\s+in\s+my\s+care\s+(journey|pathway)\b",
    r"\bmy\s+care\s+(journey|pathway|stage)\b",
    r"\bwhat\s+happens\s+next\s+with\b",
    r"\bwhat\s+is\s+my\s+(next\s+step|current\s+stage)\b",
    r"\bd[oó]nde\s+estoy\s+en\s+mi\s+(proceso|camino)\b",
    r"\bأين\s+أنا\s+في\s+رحلتي\b",
]

WEEKDAY_WORDS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "weekend", "weekday"]


def _classify_cancel_reason(text: str) -> str:
    if any(w in text for w in ["transport", "ride", "bus", "car", "drive", "travel", "no way to get", "no way to reach"]):
        return "transport"
    if any(w in text for w in ["cost", "money", "afford", "expensive", "pay", "insurance", "bill", "financial"]):
        return "cost"
    if any(w in text for w in ["scared", "afraid", "fear", "anxious", "anxiety", "nervous", "panic", "cancer", "die", "terrified", "worried"]):
        return "fear_or_anxiety"
    if any(w in text for w in ["sick", "ill", "fever", "pain", "bleed", "dizzy", "chest", "unwell", "flu", "cough", "nausea", "vomit", "symptom"]):
        return "illness"
    if any(w in text for w in ["daughter", "son", "husband", "wife", "child", "kids", "baby", "family", "caregiver", "mother", "father", "parent"]):
        return "caregiver_or_family"
    if any(w in text for w in ["work", "shift", "job", "meeting", "schedule", "busy", "office", "evening", "morning", "afternoon", "conflict"] + WEEKDAY_WORDS):
        return "work_or_schedule"
    return "other"


def _parse_slot_constraints(text: str) -> Dict[str, Any]:
    tod = None
    if re.search(r"\bevening\w*\b|\bafter\s+(5|6|work)\b|\bnight\b", text):
        tod = "evening"
    elif re.search(r"\bmorning\w*\b|\b(?:am|early)\b", text):
        tod = "morning"
    elif re.search(r"\bafternoon\w*\b|\bmidday\b", text):
        tod = "afternoon"
    days = [d for d in WEEKDAY_WORDS if re.search(rf"\b{d}s?\b", text)]
    constraints: Dict[str, Any] = {}
    if tod:
        constraints["time_of_day"] = tod
    if days:
        constraints["days"] = days
    return constraints


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

        # B1-B4 dispatch helper with automatic opening-sentence deduplication
        result = cls._dispatch_turn(
            db, pid=pid, user_id=user_id, role=role, session_id=session_id,
            message=message, text=text, state=state, case_id=case_id, language=language,
        )
        if result is not None and session_id:
            prev = (
                db.query(Communication)
                .filter(
                    Communication.session_id == session_id,
                    Communication.sender.in_(("ai", "ai_coordinator")),
                )
                .order_by(Communication.sent_at.desc())
                .first()
            )
            if prev and prev.content:
                from app.services.response_guard_service import ResponseGuardService
                result.reply = ResponseGuardService.deduplicate_opening_sentence(
                    result.reply, previous_reply=prev.content, language=language
                )
        return result

    @classmethod
    def _dispatch_turn(
        cls,
        db: Session,
        *,
        pid: uuid.UUID,
        user_id,
        role: str,
        session_id,
        message: str,
        text: str,
        state: Dict[str, Any],
        case_id=None,
        language: str = "en",
    ) -> Optional[BehaviourResult]:
        # B4 (Severe distress / crisis) ALWAYS takes top priority — deterministic, no LLM required
        from app.agents.specialized.clinical_escalation_agent import ClinicalEscalationAgent
        if ClinicalEscalationAgent.evaluate_severe_distress(message):
            return cls._handle_severe_distress(db, pid, case_id, message, language)

        # Active multi-turn continuations
        flow = state.get("flow")
        if flow in ("transport_select_appt", "transport_need_address"):
            return cls._continue_transport_flow(db, pid, user_id, role, session_id, message, text, state, language)
        if flow in (
            "cancel_select_appt", "cancel_awaiting_reason", "cancel_offer_transport",
            "cancel_work_prefs", "cancel_pick_slot", "cancel_confirm",
            "cancel_confirm_or_keep", "cancel_confirm_or_reschedule",
        ):
            return cls._continue_cancel_flow(db, pid, user_id, role, session_id, message, text, state, language)
        if flow == "transport_update_details" and (
            _detect_companion(text) is not None or re.search(r"\b(yes|no|address|street|road|from)\b", text)
        ) and not _any(REPORT_PATTERNS, text) and not _any(TRANSPORT_PATTERNS, text) and not _any(CANCEL_PATTERNS, text) and not _any(FEAR_PATTERNS, text):
            return cls._update_transport_details(db, pid, user_id, role, session_id, message, text, state, language)

        # B4 - fear or panic about the report (check before report summary so "scared about my report" gets warm fear flow)
        if _any(FEAR_PATTERNS, text):
            return cls._handle_fear_about_report(db, pid, case_id, text, language)

        # B1 - report summary
        if _any(REPORT_PATTERNS, text):
            return cls._handle_report_summary(db, pid, language)

        # B3 - cancellation with WHY question (check before transport so "cancel because no ride" starts cancel flow)
        if _any(CANCEL_PATTERNS, text):
            return cls._handle_cancel_start(db, pid, user_id, role, session_id, language)

        # B2 - transport request
        if _any(TRANSPORT_PATTERNS, text):
            return cls._handle_transport_request(db, pid, user_id, role, session_id, message, text, language)

        # Patient screening intake request -> creates persisted coordinator task + notification
        if _any(SCREENING_REQUEST_PATTERNS, text):
            return cls._handle_screening_request(db, pid, case_id, message, language)

        # Case-aware care journey & next steps inquiry
        if _any(CARE_JOURNEY_PATTERNS, text):
            return cls._handle_care_journey_inquiry(db, pid, case_id, language)

        # Natural conversational greeting with real authorized case context
        if _any(GREETING_PATTERNS, text):
            return cls._handle_greeting(db, pid, case_id, language)

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
    # B3 - Cancellation with a WHY question
    # ------------------------------------------------------------------
    @classmethod
    def _handle_cancel_start(
        cls, db: Session, patient_id: uuid.UUID, user_id, role: str, session_id, language: str, selected_appt=None
    ) -> BehaviourResult:
        from app.services.transport_service import TransportService

        appts = [selected_appt] if selected_appt else TransportService.find_candidate_appointments(db, patient_id)
        if not appts:
            if session_id:
                cls.set_state(db, session_id, user_id, role, {})
            return BehaviourResult(
                reply="I do not see an active upcoming appointment on your schedule to cancel.",
                intent="appointment_cancellation",
            )

        if len(appts) > 1:
            lines = [
                f"{i + 1}. {_utc(a.scheduled_time).strftime('%Y-%m-%d %H:%M')} with {a.provider_name}"
                for i, a in enumerate(appts[:3])
            ]
            if session_id:
                cls.set_state(db, session_id, user_id, role, {
                    "flow": "cancel_select_appt",
                    "appointment_ids": [str(a.id) for a in appts[:3]],
                })
            reply = (
                "You have more than one upcoming appointment:\n"
                + "\n".join(lines)
                + "\n\nWhich appointment are you asking about?"
            )
            return BehaviourResult(reply=reply, intent="appointment_cancellation", case_id=str(appts[0].case_id))

        appt = appts[0]
        if session_id:
            cls.set_state(db, session_id, user_id, role, {
                "flow": "cancel_awaiting_reason",
                "appointment_id": str(appt.id),
            })
        when = _utc(appt.scheduled_time).strftime("%Y-%m-%d at %H:%M")
        if language == "es":
            reply = f"Veo su cita el {when} con {appt.provider_name}. ¿Puede contarme qué le dificulta asistir?"
        elif language == "ar":
            reply = f"أرى موعدكِ في {when} مع {appt.provider_name}. هل يمكنكِ إخباري بما يجعل الحضور صعباً؟"
        else:
            reply = (
                f"I see your appointment on {when} with {appt.provider_name}. "
                "Can you tell me what is making it hard to come?"
            )
        return BehaviourResult(reply=reply, intent="appointment_cancellation", case_id=str(appt.case_id))

    @classmethod
    def _continue_cancel_flow(
        cls, db: Session, patient_id: uuid.UUID, user_id, role: str, session_id,
        raw_message: str, text: str, state: Dict[str, Any], language: str,
    ) -> BehaviourResult:
        from app.models.appointment import Appointment
        from app.services.appointment_service import AppointmentService
        from app.services.task_service import TaskService
        from app.services.transport_service import TransportService

        flow = state.get("flow")

        if flow == "cancel_select_appt":
            ids = state.get("appointment_ids") or []
            chosen_id = None
            m = re.search(r"\b([1-3])\b", text)
            if m and int(m.group(1)) <= len(ids):
                chosen_id = ids[int(m.group(1)) - 1]
            if not chosen_id:
                return BehaviourResult(
                    reply="Please reply with the number (1, 2, or 3) of the appointment you want to change or cancel?",
                    intent="appointment_cancellation",
                )
            appt = db.query(Appointment).filter(
                Appointment.id == uuid.UUID(chosen_id), Appointment.patient_id == patient_id
            ).first()
            if not appt:
                cls.set_state(db, session_id, user_id, role, {})
                return BehaviourResult(reply="I could not find that appointment.", intent="appointment_cancellation")
            return cls._handle_cancel_start(db, patient_id, user_id, role, session_id, language, selected_appt=appt)

        appt_id = state.get("appointment_id")
        appt = db.query(Appointment).filter(
            Appointment.id == uuid.UUID(appt_id), Appointment.patient_id == patient_id
        ).first() if appt_id else None
        if not appt:
            cls.set_state(db, session_id, user_id, role, {})
            return BehaviourResult(reply="I could not find that appointment anymore.", intent="appointment_cancellation")

        case = db.query(CareCase).filter(CareCase.id == appt.case_id).first()
        coord = TransportService.get_coordinator_name(db, case)

        # Explicit cancellation confirmation from any post-WHY state
        if _any(EXPLICIT_CANCEL_CONFIRM_PATTERNS, text) and flow != "cancel_awaiting_reason":
            reason_cat = state.get("reason_category") or "other"
            reason_txt = state.get("reason_text") or "Patient confirmed cancellation"
            res = AppointmentService.cancel_appointment(
                db=db,
                appointment_id=appt.id,
                reason=reason_txt,
                reason_category=reason_cat,
                patient_id=patient_id,
                actor_role="patient",
                actor_id=str(user_id),
            )
            cls.set_state(db, session_id, user_id, role, {})
            obs = [{"tool": "cancel_appointment", "success": bool(res.get("success")), "result": res}]
            if not res.get("success"):
                return BehaviourResult(
                    reply="I could not cancel the appointment right now. I have asked your coordinator to help.",
                    intent="appointment_cancellation", tool_observations=obs, case_id=str(appt.case_id),
                )
            reply = (
                f"Your appointment with {appt.provider_name} has been cancelled. "
                f"I have let {appt.provider_name} and {coord} know, and {coord} will check in with you "
                "to help when you are ready for a new time."
            )
            return BehaviourResult(
                reply=reply, intent="appointment_cancellation", tool_observations=obs, case_id=str(appt.case_id)
            )

        # Step 2: Classify reason after WHY question
        if flow == "cancel_awaiting_reason":
            reason_cat = _classify_cancel_reason(text)
            reason_txt = raw_message.strip()
            new_state = {
                "appointment_id": str(appt.id),
                "reason_category": reason_cat,
                "reason_text": reason_txt,
            }
            # Persist structured reason on case_context inquiry log
            if case:
                ctx = dict(case.case_context or {})
                inquiries = list(ctx.get("cancellation_inquiries") or [])
                inquiries.append({
                    "appointment_id": str(appt.id),
                    "reason_category": reason_cat,
                    "reason_text": reason_txt,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                })
                ctx["cancellation_inquiries"] = inquiries
                case.case_context = ctx
                db.flush()

            if reason_cat == "transport":
                new_state["flow"] = "cancel_offer_transport"
                cls.set_state(db, session_id, user_id, role, new_state)
                reply = (
                    "Thank you for sharing that. Getting to the clinic can be hard, and I can request a ride "
                    "for you before we cancel anything. If you still want to cancel, that is completely okay too. "
                    "Would you like me to request transport for this visit, or reply 'yes, cancel' to cancel it?"
                )
                return BehaviourResult(reply=reply, intent="appointment_cancellation", case_id=str(appt.case_id))

            if reason_cat in ("work_or_schedule", "caregiver_or_family"):
                constraints = _parse_slot_constraints(text)
                if constraints:
                    return cls._offer_real_slots_for_reschedule(
                        db, appt, coord, constraints, new_state, user_id, role, session_id
                    )
                new_state["flow"] = "cancel_work_prefs"
                cls.set_state(db, session_id, user_id, role, new_state)
                q = (
                    "What days and time of day usually work best for you?"
                    if reason_cat == "work_or_schedule"
                    else "What day works best for you and your family?"
                )
                reply = f"I understand how hard it is to fit visits around everything else. {q}"
                return BehaviourResult(reply=reply, intent="appointment_cancellation", case_id=str(appt.case_id))

            if reason_cat == "fear_or_anxiety":
                new_state["flow"] = "cancel_confirm_or_keep"
                cls.set_state(db, session_id, user_id, role, new_state)
                reply = (
                    "It makes complete sense to feel scared or overwhelmed before a medical visit. "
                    f"This appointment with {appt.provider_name} is a calm conversation to talk through your report "
                    "and answer your questions—nothing is forced on you, and it is always your choice. "
                    "Would you like to keep this visit, look for another time, or reply 'yes, cancel' if you prefer to cancel?"
                )
                return BehaviourResult(reply=reply, intent="appointment_cancellation", case_id=str(appt.case_id))

            if reason_cat == "illness":
                from app.agents.specialized.clinical_escalation_agent import ClinicalEscalationAgent
                obs = []
                escalated = False
                if ClinicalEscalationAgent.evaluate_safety_rules(raw_message):
                    esc_task = TaskService.create_clinical_escalation_task(
                        db=db,
                        case_id=appt.case_id,
                        patient_id=patient_id,
                        red_flag_symptoms=["patient_reported_red_flag_during_cancellation"],
                        patient_statement=raw_message,
                        idempotency_key=f"esc_cancel_{appt.id}_{uuid.uuid4().hex[:6]}",
                    )
                    db.commit()
                    obs.append({"tool": "create_clinical_escalation_task", "success": True, "result": {"task_id": str(esc_task.id)}})
                    escalated = True
                    new_state["flow"] = "cancel_confirm_or_reschedule"
                    cls.set_state(db, session_id, user_id, role, new_state)
                    reply = (
                        "I am really sorry you are feeling unwell, and the symptoms you described need prompt medical attention. "
                        "I have alerted your clinical team right away. Please contact your doctor or local emergency services now if you feel unsafe. "
                        "Whenever you are ready, reply if you want to reschedule or 'yes, cancel' to cancel your upcoming visit?"
                    )
                    return BehaviourResult(
                        reply=reply, intent="urgent_clinical_escalation", tool_observations=obs,
                        escalated=escalated, case_id=str(appt.case_id),
                    )
                new_state["flow"] = "cancel_confirm_or_reschedule"
                cls.set_state(db, session_id, user_id, role, new_state)
                reply = (
                    "I am sorry you are not feeling well. Please contact your doctor if your symptoms are worrying or getting worse. "
                    "Would you like to reschedule this visit for a later day, or reply 'yes, cancel' to cancel it?"
                )
                return BehaviourResult(reply=reply, intent="appointment_cancellation", case_id=str(appt.case_id))

            if reason_cat == "cost":
                fin_task = TaskService.create_task(
                    db=db,
                    case_id=appt.case_id,
                    patient_id=patient_id,
                    title="Financial Counselling Request (Appointment Cost Barrier)",
                    description=f"Patient cited cost barrier when considering cancelling appointment {appt.id}: '{reason_txt}'.",
                    task_type="financial_counselling",
                    assigned_role="care_coordinator",
                    priority="urgent",
                    idempotency_key=f"fin_counsel_{appt.id}_v{appt.version}",
                )
                db.commit()
                new_state["flow"] = "cancel_confirm"
                cls.set_state(db, session_id, user_id, role, new_state)
                obs = [{"tool": "create_financial_counselling_task", "success": True, "result": {"task_id": str(fin_task.id)}}]
                reply = (
                    "Thank you for telling me—worrying about cost is very understandable. "
                    f"I have requested financial counselling from {coord} (it is requested, not resolved yet), "
                    "and they will reach out to discuss options. "
                    "Would you like to wait to hear from them, or reply 'yes, cancel' if you still want to cancel?"
                )
                return BehaviourResult(
                    reply=reply, intent="appointment_cancellation", tool_observations=obs, case_id=str(appt.case_id)
                )

            # other
            new_state["flow"] = "cancel_confirm"
            cls.set_state(db, session_id, user_id, role, new_state)
            reply = (
                f"Thank you for letting me know. Your appointment on {_utc(appt.scheduled_time).strftime('%Y-%m-%d at %H:%M')} "
                "is still active until you confirm. Would you like me to cancel it? Please reply 'yes, cancel' to confirm."
            )
            return BehaviourResult(reply=reply, intent="appointment_cancellation", case_id=str(appt.case_id))

        # Offering transport before cancelling
        if flow == "cancel_offer_transport":
            if re.search(r"\b(yes|ride|transport|pickup|please|help)\b", text) and "cancel" not in text:
                cls.set_state(db, session_id, user_id, role, {})
                return cls._handle_transport_request(
                    db, patient_id, user_id, role, session_id, raw_message, text, language, selected_appt=appt
                )
            state["flow"] = "cancel_confirm"
            cls.set_state(db, session_id, user_id, role, state)
            return BehaviourResult(
                reply="That is completely fine. Please reply 'yes, cancel' to confirm cancelling your appointment.",
                intent="appointment_cancellation", case_id=str(appt.case_id),
            )

        # Gathering preferred day/time for work/schedule or caregiver/family
        if flow == "cancel_work_prefs":
            if "cancel" in text:
                state["flow"] = "cancel_confirm"
                cls.set_state(db, session_id, user_id, role, state)
                return BehaviourResult(
                    reply="No problem. Please reply 'yes, cancel' to confirm cancelling your appointment.",
                    intent="appointment_cancellation", case_id=str(appt.case_id),
                )
            constraints = _parse_slot_constraints(text)
            return cls._offer_real_slots_for_reschedule(
                db, appt, coord, constraints, state, user_id, role, session_id
            )

        # Picking one of the real offered slots to reschedule instead of cancelling
        if flow == "cancel_pick_slot":
            slots = state.get("offered_slots") or []
            chosen = None
            m = re.search(r"\b([1-3])\b", text)
            if m and int(m.group(1)) <= len(slots):
                chosen = slots[int(m.group(1)) - 1]
            else:
                for sl in slots:
                    if sl.get("hhmm") and sl["hhmm"] in text:
                        chosen = sl
                        break
            if chosen:
                new_dt = datetime.fromisoformat(chosen["iso"].replace("Z", "+00:00"))
                moved = AppointmentService.reschedule_appointment(
                    db=db,
                    appointment_id=appt.id,
                    new_scheduled_time=new_dt,
                    actor_role="patient",
                    actor_id=str(user_id),
                    reason=state.get("reason_text") or "Patient schedule preference",
                )
                db.commit()
                cls.set_state(db, session_id, user_id, role, {})
                obs = [{"tool": "reschedule_appointment", "success": True, "result": {
                    "appointment_id": str(moved.id), "version": moved.version, "scheduled_time": chosen["iso"]
                }}]
                reply = (
                    f"I have moved your appointment to {chosen['display']} (version {moved.version}) "
                    f"and notified {moved.provider_name} to confirm the new time."
                )
                return BehaviourResult(
                    reply=reply, intent="appointment_rescheduled", tool_observations=obs, case_id=str(appt.case_id)
                )
            state["flow"] = "cancel_confirm"
            cls.set_state(db, session_id, user_id, role, state)
            return BehaviourResult(
                reply="Understood. If none of those times work, please reply 'yes, cancel' to confirm cancelling your appointment.",
                intent="appointment_cancellation", case_id=str(appt.case_id),
            )

        # cancel_confirm / cancel_confirm_or_keep / cancel_confirm_or_reschedule
        if re.search(r"\bkeep\b|\bdon'?t\s+cancel\b|\bnever\s*mind\b|\bstay\b", text):
            cls.set_state(db, session_id, user_id, role, {})
            return BehaviourResult(
                reply=f"Your appointment on {_utc(appt.scheduled_time).strftime('%Y-%m-%d at %H:%M')} stays on your schedule. How else can I help?",
                intent="appointment_kept", case_id=str(appt.case_id),
            )
        if re.search(r"\b(move|reschedule|another\s+time|different\s+day|later)\b", text):
            state["flow"] = "cancel_work_prefs"
            cls.set_state(db, session_id, user_id, role, state)
            return BehaviourResult(
                reply="What days and time of day work best for you?",
                intent="appointment_cancellation", case_id=str(appt.case_id),
            )

        state["flow"] = "cancel_confirm"
        cls.set_state(db, session_id, user_id, role, state)
        return BehaviourResult(
            reply="Your appointment is not cancelled yet. Please reply 'yes, cancel' if you want me to cancel it.",
            intent="appointment_cancellation", case_id=str(appt.case_id),
        )

    @classmethod
    def _offer_real_slots_for_reschedule(
        cls, db: Session, appt, coord: str, constraints: Dict[str, Any],
        state: Dict[str, Any], user_id, role: str, session_id,
    ) -> BehaviourResult:
        from app.services.appointment_service import AppointmentService
        from app.services.task_service import TaskService

        slots = AppointmentService.get_available_slots(db, doctor=appt.provider_name, constraints=constraints, limit=3)
        obs = [{"tool": "get_available_slots", "success": True, "result": {"count": len(slots), "constraints": constraints}}]

        if slots:
            state["flow"] = "cancel_pick_slot"
            state["offered_slots"] = slots
            cls.set_state(db, session_id, user_id, role, state)
            lines = [f"{i + 1}. {s['display']}" for i, s in enumerate(slots)]
            reply = (
                f"Here are real open times with {appt.provider_name}:\n"
                + "\n".join(lines)
                + "\n\nWould you like to move your appointment to one of these (reply 1, 2, or 3), or reply 'yes, cancel' to cancel?"
            )
            return BehaviourResult(
                reply=reply, intent="appointment_cancellation", tool_observations=obs, case_id=str(appt.case_id)
            )

        # No real slots match -> NEVER invent a slot; create coordinator task and say so honestly
        task = TaskService.create_task(
            db=db,
            case_id=appt.case_id,
            patient_id=appt.patient_id,
            title=f"Find Matching Appointment Slot ({appt.provider_name})",
            description=(
                f"Patient requested reschedule matching constraints {constraints} for appointment {appt.id}, "
                "but no real schedule slots matched. Please assist patient directly."
            ),
            task_type="reschedule_assistance",
            assigned_role="care_coordinator",
            priority="urgent",
            idempotency_key=f"resched_assist_{appt.id}_{uuid.uuid4().hex[:6]}",
        )
        db.commit()
        obs.append({"tool": "create_coordinator_task", "success": True, "result": {"task_id": str(task.id)}})
        state["flow"] = "cancel_confirm"
        cls.set_state(db, session_id, user_id, role, state)
        reply = (
            f"I checked {appt.provider_name}'s schedule and there are no open slots matching that time right now. "
            f"I have asked {coord} to look for an option and follow up with you. "
            "Would you like to wait for them, or reply 'yes, cancel' if you want to cancel your current visit?"
        )
        return BehaviourResult(
            reply=reply, intent="appointment_cancellation", tool_observations=obs, case_id=str(appt.case_id)
        )

    # ------------------------------------------------------------------
    # B4 - Fear, panic, and severe distress
    # ------------------------------------------------------------------
    @classmethod
    def _resolve_case_and_doctor(cls, db: Session, patient_id: uuid.UUID, case_id=None):
        from app.models.appointment import Appointment
        from app.models.doctor_assignment import DoctorAssignment
        from app.models.owner import CaseOwner

        case = None
        if case_id:
            cid = case_id if isinstance(case_id, uuid.UUID) else uuid.UUID(str(case_id))
            case = db.query(CareCase).filter(CareCase.id == cid, CareCase.patient_id == patient_id).first()
        if not case:
            case = db.query(CareCase).filter(CareCase.patient_id == patient_id).order_by(CareCase.created_at.desc()).first()

        doctor_name = None
        if case:
            da = db.query(DoctorAssignment).filter(DoctorAssignment.case_id == case.id).order_by(DoctorAssignment.created_at.desc()).first()
            if da:
                doc_owner = db.query(CaseOwner).filter(CaseOwner.id == da.doctor_id).first()
                if doc_owner:
                    doctor_name = doc_owner.name
            if not doctor_name:
                appt = db.query(Appointment).filter(Appointment.case_id == case.id).order_by(Appointment.created_at.desc()).first()
                if appt and appt.provider_name:
                    doctor_name = appt.provider_name
        if not doctor_name:
            doc_owner = (
                db.query(CaseOwner)
                .filter(CaseOwner.role.in_(("primary_physician", "specialist", "doctor")), CaseOwner.is_active.is_(True))
                .first()
            )
            doctor_name = doc_owner.name if doc_owner else "your assigned doctor"
        return case, doctor_name

    @classmethod
    def _handle_fear_about_report(
        cls, db: Session, patient_id: uuid.UUID, case_id, text: str, language: str
    ) -> BehaviourResult:
        case, doctor_name = cls._resolve_case_and_doctor(db, patient_id, case_id)
        asking_cancer_or_die = bool(re.search(r"cancer|c[aá]ncer|سرطان|die|morir|سأموت", text))

        if language == "es":
            ack = "Es completamente comprensible sentir miedo o angustia mientras espera respuestas claras."
            answer = (
                "Un informe de detección por sí solo no puede confirmar ni descartar cáncer ni mostrar el panorama completo; "
                "solo indica si hace falta revisar algo más de cerca."
                if asking_cancer_or_die
                else "Las palabras médicas de un informe solo describen lo que se ve en la imagen y por sí solas no dan el panorama completo."
            )
            doctor_part = f"Una consulta con {doctor_name} es lo que le dará respuestas claras y un plan seguro."
            next_step = "¿Le gustaría que revisemos su informe despacio paso a paso, o prefiere que le ayude a ver horarios con su médico?"
            reply = f"{ack}\n\n{answer}\n\n{doctor_part}\n\n{next_step}"
        elif language == "ar":
            ack = "من الطبيعي جداً أن تشعري بالخوف أو القلق أثناء انتظار إجابات واضحة."
            answer = (
                "التقرير وحده لا يستطيع أن يثبت أو ينفي وجود مرض ولا يعطي الصورة الكاملة؛ هو فقط يشير إلى الحاجة لمراجعة أدق."
                if asking_cancer_or_die
                else "المصطلحات الواردة في التقرير تصف الصورة فقط ولا تعطي الصورة الكاملة بمفردها."
            )
            doctor_part = f"الزيارة مع {doctor_name} هي التي ستمنحكِ إجابات حقيقية وواضحة."
            next_step = "هل تودين أن نمر على التقرير معاً بهدوء، أم أساعدكِ في حجز أو تعديل موعد الاستشارة قريباً؟"
            reply = f"{ack}\n\n{answer}\n\n{doctor_part}\n\n{next_step}"
        else:
            ack = "It makes complete sense to feel scared while you are waiting for answers."
            if asking_cancer_or_die:
                answer = (
                    "A screening report or a score on its own cannot tell anyone whether a person has cancer or show the full picture. "
                    "It simply flags an area that deserves a closer look."
                )
            else:
                answer = (
                    "Medical terms on a report only describe what was seen on the scan—a report alone cannot tell anyone the full picture."
                )
            doctor_part = f"A visit with your doctor, {doctor_name}, is what gives you real clarity and explains what applies to you."
            next_step = (
                "Would you like me to go through your report slowly with you, or help book or move your consultation soon?"
            )
            reply = f"{ack}\n\n{answer}\n\n{doctor_part}\n\n{next_step}"

        return BehaviourResult(
            reply=reply,
            intent="emotional_support",
            case_id=str(case.id) if case else None,
        )

    @classmethod
    def _handle_severe_distress(
        cls, db: Session, patient_id: uuid.UUID, case_id, raw_message: str, language: str
    ) -> BehaviourResult:
        from app.services.task_service import TaskService

        case, doctor_name = cls._resolve_case_and_doctor(db, patient_id, case_id)
        obs = []
        if case:
            esc_task = TaskService.create_clinical_escalation_task(
                db=db,
                case_id=case.id,
                patient_id=patient_id,
                red_flag_symptoms=["severe_emotional_distress"],
                patient_statement=raw_message,
                idempotency_key=f"distress_esc_{case.id}_{uuid.uuid4().hex[:8]}",
            )
            db.commit()
            obs.append({
                "tool": "create_clinical_escalation_task",
                "success": True,
                "result": {"task_id": str(esc_task.id), "priority": esc_task.priority},
            })

        if language == "es":
            reply = (
                "Siento mucho que esté pasando por un momento tan difícil, y estoy aquí con usted.\n\n"
                f"He creado una alerta urgente para que su equipo clínico ({doctor_name} y su coordinadora) se comunique con usted.\n\n"
                "Si siente que no está segura ahora mismo, por favor llame de inmediato a su equipo de atención o a los servicios de emergencia locales."
            )
        elif language == "ar":
            reply = (
                "أشعر بمدى صعوبة هذه اللحظة عليكِ، وأنا هنا معكِ.\n\n"
                f"لقد أرسلتُ تنبيهاً عاجلاً لفريقكِ الطبي ({doctor_name} ومنسقة الرعاية) للتواصل معكِ.\n\n"
                "إذا كنتِ تشعرين بعدم الأمان الآن، يرجى الاتصال فوراً بفريق رعايتكِ أو بخدمات الطوارئ المحلية."
            )
        else:
            reply = (
                "I am really sorry you are carrying so much right now, and I am right here with you.\n\n"
                f"I have created an urgent alert for your clinical team ({doctor_name} and your care coordinator) so someone reaches out to you directly.\n\n"
                "If you feel unsafe right now, please contact your care team or your local emergency services immediately."
            )

        return BehaviourResult(
            reply=reply,
            intent="urgent_clinical_escalation",
            tool_observations=obs,
            escalated=True,
            case_id=str(case.id) if case else None,
        )

    # ------------------------------------------------------------------
    # Patient Screening Intake Request & Case-Aware Greeting
    # ------------------------------------------------------------------
    @classmethod
    def _handle_screening_request(
        cls, db: Session, patient_id: uuid.UUID, case_id, raw_message: str, language: str
    ) -> BehaviourResult:
        from app.models.event_audit import CaseEvent
        from app.models.owner import CaseOwner
        from app.models.user import User
        from app.services.notification_service import NotificationService
        from app.services.task_service import TaskService

        case, doctor_name = cls._resolve_case_and_doctor(db, patient_id, case_id)
        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        first_name = patient.first_name if patient else "there"
        full_name = f"{patient.first_name} {patient.last_name}".strip() if patient else "Patient"

        coord_owner = db.query(CaseOwner).filter(CaseOwner.role == "care_coordinator").first()
        coord_name = coord_owner.name if coord_owner else "Priya Nair, RN"
        facility_name = (coord_owner.facility if coord_owner and coord_owner.facility else None) or "Metropolitan Hospital Screening Center"

        text_low = (raw_message or "").lower()
        if "colonoscopy" in text_low:
            screening_type = "Colonoscopy"
        elif "cervical" in text_low or "pap" in text_low:
            screening_type = "Cervical Screening"
        else:
            screening_type = "Mammogram"

        obs: List[Dict[str, Any]] = []
        if case:
            ctx = dict(case.case_context or {})
            ctx["screening_request"] = raw_message.strip()
            ctx["onboarding_stage"] = "intake_submitted"
            ctx["requested_screening_type"] = screening_type
            case.case_context = ctx

            task = TaskService.create_screening_handoff_task(
                db=db,
                case_id=case.id,
                patient_id=patient_id,
                screening_type=screening_type,
                notes=raw_message.strip(),
                idempotency_key=f"screening_req_{case.id}",
            )
            obs.append({
                "tool": "create_screening_handoff_task",
                "success": True,
                "result": {"task_id": str(task.id), "screening_type": screening_type, "assigned_to": coord_name},
            })

            now = datetime.now(timezone.utc)
            db.add(CaseEvent(
                id=uuid.uuid4(),
                case_id=case.id,
                event_type="screening_request_submitted",
                description=(
                    f"Patient submitted {screening_type} screening request: '{raw_message.strip()}'. "
                    f"Persisted task assigned to {coord_name}."
                ),
                event_data={
                    "screening_type": screening_type,
                    "request_text": raw_message.strip(),
                    "task_id": str(task.id),
                    "coordinator": coord_name,
                },
                timestamp=now,
            ))

            coord_users = db.query(User).filter(User.role == "care_coordinator", User.is_active.is_(True)).all()
            notif_id = None
            for cu in coord_users:
                try:
                    notif = NotificationService.stage_notification(
                        db=db,
                        user_id=cu.id,
                        role="care_coordinator",
                        event_type="screening_request_received",
                        title=f"New Screening Request: {full_name}",
                        message=(
                            f"{full_name} ({case.case_number}) submitted a {screening_type} screening request: "
                            f"\"{raw_message.strip()}\". Please create the screening order."
                        ),
                        priority="urgent",
                        case_id=case.id,
                        patient_id=patient_id,
                        action_link=f"/cases/{case.id}",
                        idempotency_key=f"notif_scr_req_{case.id}_{cu.id}",
                        metadata_json={"task_id": str(task.id), "screening_type": screening_type},
                    )
                    notif_id = str(notif.id)
                except Exception as exc:
                    logger.warning(f"Screening request notification staging notice: {exc}")

            db.commit()
            try:
                NotificationService.process_outbox_batch(db)
            except Exception:
                pass
            if notif_id:
                obs.append({
                    "tool": "notify_coordinator_screening_request",
                    "success": True,
                    "result": {"notification_id": notif_id, "recipient": coord_name},
                })

        if language == "es":
            reply = (
                f"Gracias, {first_name}. He registrado su solicitud de {screening_type} y he creado una tarea prioritaria "
                f"para su coordinadora de atención, {coord_name}, en {facility_name}.\n\n"
                f"{coord_name} ha recibido una notificación para crear la orden de detección y registrar el procedimiento cuando se realice. "
                "Le avisaré en cuanto la orden y el informe estén listos."
            )
        elif language == "ar":
            reply = (
                f"شكراً لكِ يا {first_name}. لقد سجلتُ طلب فحص ({screening_type}) وأنشأتُ مهمة لمنسقة الرعاية {coord_name} في {facility_name}.\n\n"
                f"تم إرسال إشعار إلى {coord_name} لإنشاء طلب الفحص ومتابعة إجرائه. سأخبركِ فور تحديث حالة الفحص والتقرير."
            )
        else:
            reply = (
                f"Thank you, {first_name}. I have logged your {screening_type.lower()} screening request and created an urgent task "
                f"for your Care Coordinator, {coord_name}, at {facility_name}.\n\n"
                f"{coord_name} has been notified to create your screening order and track the procedure once it is performed. "
                "Your Stage 1 screening milestone will update as soon as the procedure is completed, and I will be right here to explain your finalized report."
            )

        return BehaviourResult(
            reply=reply,
            intent="patient_intake_submitted",
            tool_observations=obs,
            case_id=str(case.id) if case else None,
        )

    @classmethod
    def _handle_greeting(
        cls, db: Session, patient_id: uuid.UUID, case_id, language: str
    ) -> BehaviourResult:
        from app.models.owner import CaseOwner
        from app.services.lifecycle_service import LifecycleService

        case, doctor_name = cls._resolve_case_and_doctor(db, patient_id, case_id)
        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        first_name = patient.first_name if patient else "there"

        coord_owner = db.query(CaseOwner).filter(CaseOwner.role == "care_coordinator").first()
        coord_name = coord_owner.name if coord_owner else "Priya Nair, RN"

        stage_summary = "at the start of your 14-stage care pathway"
        if case:
            stages = LifecycleService.get_lifecycle_stages(case)
            completed = [s for s in stages if s.get("status") == "completed"]
            if len(completed) == 0:
                stage_summary = f"at the start of your 14-stage care pathway (Case {case.case_number})"
            elif len(completed) == 14:
                stage_summary = f"at 14 of 14 stages complete with full clinical closure (Case {case.case_number})"
            else:
                curr = LifecycleService.get_current_stage(case)
                stage_summary = (
                    f"at Stage {curr.get('stage_number', len(completed) + 1)} of 14 — "
                    f"{curr.get('title', 'Active Care Coordination')} (Case {case.case_number})"
                )

        if language == "es":
            reply = (
                f"Hola {first_name}, me alegra saludarle. Actualmente se encuentra {stage_summary}, "
                f"con el apoyo de {coord_name} y {doctor_name}. "
                "¿Le gustaría solicitar una prueba de detección, revisar su informe o consultar sobre su próxima cita?"
            )
        elif language == "ar":
            reply = (
                f"مرحباً {first_name}، يسعدني تواصلكِ. أنتِ حالياً في {stage_summary} بدعم من {coord_name} و{doctor_name}. "
                "هل تودين تقديم طلب فحص، أو شرح تقريركِ الطبي، أو الاستفسار عن موعدكِ القادم؟"
            )
        else:
            reply = (
                f"Hello {first_name}! You are currently {stage_summary}, supported by Care Coordinator {coord_name} and {doctor_name}. "
                "How can I help you today—would you like to submit a screening request, go over your report in plain language, or check on your appointment and transport?"
            )

        return BehaviourResult(
            reply=reply,
            intent="greeting",
            case_id=str(case.id) if case else None,
        )

    @classmethod
    def _handle_care_journey_inquiry(
        cls, db: Session, patient_id: uuid.UUID, case_id, language: str
    ) -> BehaviourResult:
        from app.models.appointment import Appointment
        from app.models.owner import CaseOwner
        from app.services.lifecycle_service import LifecycleService

        case, doctor_name = cls._resolve_case_and_doctor(db, patient_id, case_id)
        patient = db.query(Patient).filter(Patient.id == patient_id).first()
        first_name = patient.first_name if patient else "there"

        coord_owner = db.query(CaseOwner).filter(CaseOwner.role == "care_coordinator").first()
        coord_name = coord_owner.name if coord_owner else "Priya Nair, RN"

        if not case:
            return BehaviourResult(
                reply=f"Hello {first_name}, I do not see an active care case on your profile yet. Would you like me to help you request a screening?",
                intent="care_journey_status",
            )

        stages = LifecycleService.get_lifecycle_stages(case)
        completed = [s for s in stages if s.get("status") == "completed"]
        completed_count = len(completed)
        curr = LifecycleService.get_current_stage(case)
        curr_title = curr.get("title", "Attending Physician Clinical Review")
        curr_num = curr.get("stage_number", completed_count + 1)

        sr = case.screening_result
        finding_code = sr.finding_code if sr and sr.finding_code else "INTAKE-PENDING"
        modality = sr.screening_type if sr and sr.screening_type else "Mammogram"

        appt = (
            db.query(Appointment)
            .filter(
                Appointment.case_id == case.id,
                Appointment.status.in_(("CONFIRMED", "confirmed", "booked", "PROPOSED")),
            )
            .order_by(Appointment.scheduled_time.desc())
            .first()
        )
        appt_line = ""
        if appt and appt.scheduled_time:
            appt_line = f" Your next scheduled visit is on {_utc(appt.scheduled_time).strftime('%B %d at %H:%M UTC')} at {appt.facility} ({appt.status})."

        obs = [{
            "tool": "get_care_journey_context",
            "success": True,
            "result": {
                "case_number": case.case_number,
                "completed_stages": completed_count,
                "current_stage": curr_num,
                "finding_code": finding_code,
                "doctor": doctor_name,
                "coordinator": coord_name,
            },
        }]

        if language == "es":
            reply = (
                f"{first_name}, en su caso **{case.case_number}** ha completado **{completed_count} de las 14 etapas** "
                f"(informe de {modality} finalizado con resultado **{finding_code}**) y ahora se encuentra en la **Etapa {curr_num}: {curr_title}**.\n\n"
                f"El siguiente paso es que **{doctor_name}** revise sus hallazgos diagnósticos y autorice la referencia con el especialista, "
                f"mientras su coordinadora **{coord_name}** prepara su cita.{appt_line} ¿Desea que revisemos preguntas para su consulta o necesita ayuda con el transporte?"
            )
        elif language == "ar":
            reply = (
                f"يا {first_name}، في ملفكِ الطبي (**{case.case_number}**) تم إكمال **{completed_count} من أصل 14 مرحلة** "
                f"(تقرير {modality} المعتمد بنتيجة **{finding_code}**) وأنتِ الآن في **المرحلة {curr_num}: {curr_title}**.\n\n"
                f"الخطوة التالية هي مراجعة **{doctor_name}** لنتائج التقرير واعتماد الإحالة التخصصية، بينما تتابع منسقة الرعاية **{coord_name}** ترتيب موعدكِ.{appt_line}"
            )
        else:
            reply = (
                f"Hello {first_name}! For your care pathway (**{case.case_number}**), you have completed **{completed_count} of 14 stages** "
                f"(including your finalized {modality} report showing **{finding_code}**) and you are currently at **Stage {curr_num} of 14: {curr_title}**.\n\n"
                f"Next, **{doctor_name}** will review your finalized findings, record the clinical decision, and accept your specialist referral, "
                f"while Care Coordinator **{coord_name}** prepares your specialist consultation options.\n\n"
                "Would you like help preparing questions for Dr. Arjun Menon or requesting a pickup ride once your visit time is selected?"
            )

        return BehaviourResult(
            reply=reply,
            intent="care_journey_status",
            tool_observations=obs,
            case_id=str(case.id),
        )

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
