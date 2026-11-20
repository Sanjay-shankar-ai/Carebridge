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
from app.models.transport import ConversationFlowState

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

        # B1 - report summary
        if _any(REPORT_PATTERNS, text):
            return cls._handle_report_summary(db, pid, language)

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
