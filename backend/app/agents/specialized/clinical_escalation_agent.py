"""
CareBridge Clinical Escalation Agent
Specialized agent responsible for:
- Applying approved deterministic clinical safety triage rules
- Detecting acute, emergent, or red-flag clinical symptoms in patient communication
- Routing clinical concerns immediately to on-duty physicians / coordinators
- Guaranteeing atomic PostgreSQL persistence of case escalation and timeline events
- OPERATING INDEPENDENTLY OF LLM AVAILABILITY (Guaranteed deterministic fallback)
- STRICT CLINICAL GUARDRAIL: Never independently diagnoses or prescribes treatments.
"""

from typing import Dict, Any, List, Optional
from app.agents.state import CoordinationPlan, ProposedAction, IntentAnalysis


# Approved deterministic acute symptom triggers
ACUTE_SYMPTOM_INDICATORS = [
    "emergency", "chest pain", "bleeding", "severe", "fever", "swelling",
    "redness", "fainted", "breathless", "infection", "acute", "unbearable",
    "agony", "high fever", "mastitis", "pus", "discharge", "severe pain",
    "நெஞ்சு வலி", "அவசரம்", "அதிக காய்ச்சல்", "கடுமையான வலி", "வீக்கம்"
]


class ClinicalEscalationAgent:
    """Specialized agent for deterministic emergency clinical triage and physician escalation."""

    @classmethod
    def evaluate_safety_rules(cls, message: str) -> bool:
        """Evaluates whether message contains acute red-flag symptoms requiring emergency escalation."""
        msg_lower = (message or "").lower().strip()
        return any(term in msg_lower for term in ACUTE_SYMPTOM_INDICATORS)

    @classmethod
    def formulate_escalation_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any]
    ) -> CoordinationPlan:
        """Formulates an immediate Level 2 emergency escalation plan."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = patient_context.get("full_name") or patient_context.get("first_name", "Valued Patient")
        lang = intent.detected_language or patient_context.get("preferred_language", "en")

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="escalate_case",
                arguments={
                    "case_id": case_id,
                    "urgency": "critical",
                    "reason": "Patient reported acute clinical symptoms requiring immediate human physician oversight."
                },
                rationale="Route urgent medical issue to on-duty clinician or nurse coordinator immediately.",
                autonomy_level=2
            )
        ]

        if lang == "ta":
            msg = (
                f"தங்களின் பாதுகாப்பு எங்களுக்கு மிக முக்கியமானது {patient_name}. "
                "தங்களின் தீவிர அறிகுறிகள் குறித்து எங்கள் அவசர மருத்துவக் குழுவிற்கு உடனடியாக தகவல் தெரிவித்துள்ளேன். "
                "உடனடி அவசர மருத்துவ உதவி தேவைப்பட்டால், தயவுசெய்து அவசர சிகிச்சை மையத்தை (108/911) அணுகவும்."
            )
        else:
            msg = (
                f"Your safety is our highest priority, {patient_name}. I have immediately alerted our on-duty clinician and care coordinator. "
                "If you are experiencing severe distress or a medical emergency, please call emergency services (108/911) or visit the nearest emergency room immediately."
            )

        return CoordinationPlan(
            goal="Escalate acute clinical symptoms to human physician queue with critical priority.",
            situation_summary="Acute clinical concern identified in patient communication.",
            actions=actions,
            patient_response_draft=msg,
            target_language=lang
        )
