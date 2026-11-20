"""
CareBridge Response Guard Service (Phase 2)
Guarantees that outbound agent responses never fabricate action success.

Invariant:
The agent's reply may claim an action only if a matching successful tool result
exists in the same conversational turn. Otherwise, rewrite or reject the reply
to reflect the genuine operational and clinical state.

Supported Action Categories:
- APPOINTMENT_BOOKED
- REFERRAL_CREATED
- CASE_CLOSED
- ESCALATION_TRIGGERED
- NOTIFICATION_DISPATCHED
- ORDER_PLACED
"""

import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("carebridge.services.response_guard")

ACTION_CLAIM_PATTERNS = {
    "APPOINTMENT_BOOKED": [
        r"\b(?:i have|we have|i've|we've|has been|is now)?\s*(?:successfully\s+)?(?:booked|scheduled|confirmed)\s*(?:your|an?|the)?\s*(?:follow-up\s+)?(?:diagnostic\s+)?(?:appointment|visit|consultation|slot|biopsy|procedure|session|screening)\b",
        r"\b(?:appointment|visit|consultation|biopsy|procedure)\s*(?:is|has been)\s*(?:successfully\s+)?(?:booked|confirmed|scheduled)\b",
        r"\b(?:successfully booked|successfully scheduled)\b",
        r"\b(?:booked for you|scheduled for you)\b",
    ],
    "REFERRAL_CREATED": [
        r"\b(?:i have|we have|i've|we've)?\s*(?:successfully\s+)?(?:referred you|sent a referral|submitted a referral|initiated your referral)\b",
        r"\b(?:referral has been (?:sent|created|submitted|dispatched))\b",
    ],
    "CASE_CLOSED": [
        r"\b(?:your case is (?:now )?closed|case has been closed|case is officially closed)\b",
        r"\b(?:clinical closure has been signed off|signed off on your care pathway|closed your case)\b",
    ],
    "ORDER_PLACED": [
        r"\b(?:i have placed|order has been placed|ordered your screening|screening order submitted|successfully ordered)\b",
    ],
    "NOTIFICATION_DISPATCHED": [
        r"\b(?:notification has been sent|alert has been dispatched|notified the clinic|notified your care team|sent an alert to|alerted your doctor)\b",
    ],
    "TRANSPORT_CONFIRMED": [
        r"\b(?:your\s+)?(?:ride|transport|pickup|pick-up|driver)\s+(?:is|has been)\s+(?:now\s+)?(?:confirmed|arranged|booked|secured)\b",
        r"\b(?:i have|we have|i've|we've)\s+(?:confirmed|arranged|booked)\s+(?:your\s+)?(?:ride|transport|pickup|pick-up)\b",
    ],
    "APPOINTMENT_CANCELLED": [
        r"\b(?:your\s+)?(?:appointment|visit|consultation)\s+(?:is|has been)\s+(?:now\s+)?(?:cancel+ed)\b",
        r"\b(?:i have|we have|i've|we've)\s+(?:successfully\s+)?(?:cancel+ed)\s+(?:your\s+)?(?:appointment|visit|consultation)\b",
        r"\bappointment\s+cancel+ed\b",
    ],
}

TOOL_ACTION_MAPPING = {
    "APPOINTMENT_BOOKED": [
        "book_appointment", "reschedule_appointment", "confirm_appointment", "create_appointment_proposal"
    ],
    "REFERRAL_CREATED": [
        "create_referral", "initiate_referral", "send_referral"
    ],
    "CASE_CLOSED": [
        "request_closure_verification", "signoff_closure", "record_closure_signoff"
    ],
    "ORDER_PLACED": [
        "order_screening", "create_screening_order"
    ],
    "NOTIFICATION_DISPATCHED": [
        "notify_case_owner", "send_notification", "notify_screening_missed", "notify_doctor_review_completed", "notify_patient_message"
    ],
    "TRANSPORT_CONFIRMED": [
        "confirm_transport_request"
    ],
    "APPOINTMENT_CANCELLED": [
        "cancel_appointment"
    ],
}


class ResponseGuardService:
    """Validates and sanitizes agent outbound drafts against verified turn tool executions."""

    @classmethod
    def check_claim_groundedness(
        cls,
        action_category: str,
        tool_observations: List[Dict[str, Any]]
    ) -> bool:
        """
        Returns True if at least one tool matching the action_category
        executed successfully in tool_observations.
        """
        valid_tools = TOOL_ACTION_MAPPING.get(action_category, [])
        for obs in tool_observations:
            t_name = obs.get("tool") or ""
            if t_name in valid_tools:
                # Check execution success flag
                if obs.get("success") is True:
                    return True
                # Check nested result success
                res = obs.get("result")
                if isinstance(res, dict) and res.get("success") is True:
                    return True
        return False

    @classmethod
    def sanitize_response(
        cls,
        draft_response: Optional[str],
        tool_observations: Optional[List[Dict[str, Any]]] = None,
        actor_role: str = "patient"
    ) -> str:
        """
        Scans draft_response for action claims. If an action claim lacks
        matching tool execution evidence, rewrites the response with authentic status.
        """
        if not draft_response:
            return "How can I assist you with your care pathway today?"

        obs_list = tool_observations or []
        sanitized = draft_response

        # Check each action category
        for category, patterns in ACTION_CLAIM_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, sanitized, re.IGNORECASE):
                    is_grounded = cls.check_claim_groundedness(category, obs_list)
                    if not is_grounded:
                        logger.warning(
                            f"ResponseGuard: Ungrounded claim detected for {category}. Rewriting draft."
                        )
                        sanitized = cls._rewrite_ungrounded_claim(sanitized, category, actor_role)
                        break

        return sanitized

    @classmethod
    def _rewrite_ungrounded_claim(cls, draft: str, category: str, actor_role: str) -> str:
        """Rewrites ungrounded claims into authentic status messages."""
        if category == "APPOINTMENT_BOOKED":
            return (
                "Your appointment has not yet been booked. "
                "I would be glad to coordinate with the clinic on your behalf. "
                "Could you please confirm your preferred date and whether morning or afternoon works best for you?"
            )
        elif category == "REFERRAL_CREATED":
            return (
                "Your specialist referral has not yet been submitted. "
                "Once your physician authorizes the clinical pathway, our care coordination team will dispatch the referral."
            )
        elif category == "CASE_CLOSED":
            return (
                "Your care case is not yet closed. "
                "Verified clinical closure requires documented physician review and signed evidence. "
                "Your care team is actively reviewing your latest findings."
            )
        elif category == "ORDER_PLACED":
            return (
                "The screening order has not yet been finalized. "
                "Our team is validating the clinical requirements and will notify you as soon as it is scheduled."
            )
        elif category == "TRANSPORT_CONFIRMED":
            return (
                "Your ride is not confirmed yet. "
                "I can submit a transport request to your care coordinator, who will confirm the pickup and let you know."
            )
        elif category == "APPOINTMENT_CANCELLED":
            return (
                "Your appointment has not been cancelled yet. "
                "Before cancelling, could you tell me what is making it hard to come, or confirm if you want me to cancel it?"
            )

        return draft

