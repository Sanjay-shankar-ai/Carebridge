"""
CareBridge Context-Aware Recovery Playbooks & Dynamic Messaging (Phase 7)
Provides barrier-specific recovery playbooks, multi-attempt progressions,
and non-fixed, empathetic, multilingual patient communications.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("carebridge.recovery.playbooks")


# ==============================================================================
# Multilingual Dynamic Messaging Engine
# ==============================================================================

MESSAGES = {
    "en": {
        "clarification_inquiry": [
            "Hello {patient_name}, this is your CareBridge team. We noticed you were unable to make your appointment on {date_or_recent}. We want to make sure you are doing well—did anything come up, and how can we best assist you with rescheduling?",
            "Hi {patient_name}, CareBridge reaching out. We missed you at your scheduled diagnostic visit. We know life can get busy or unexpected things happen. Could you let us know what happened so we can find a time or support that works better for you?",
            "Dear {patient_name}, your care team wants to check in regarding your missed visit. Your health and peace of mind are our priority. Is there any difficulty or question we can help you with before we reschedule?"
        ],
        "transportation_support": [
            "Hello {patient_name}, we understand that getting transportation can be challenging. CareBridge can help arrange complimentary clinic transit vouchers or medical ride assistance. Would that help you attend your follow-up visit?",
            "Hi {patient_name}, no worry about transportation—our care team coordinates with transit partners to ensure you have a safe, round-trip ride directly to the facility. When would you like us to schedule this for you?",
            "Dear {patient_name}, getting to the clinic shouldn't stand in the way of your care. We have door-to-door shuttle support and travel reimbursement options available. Let us know if you would like us to set that up."
        ],
        "caregiver_coordination": [
            "Hello {patient_name}, we understand your schedule depends on family or caregiver availability. We have weekend and evening appointment slots open so your family member can accompany you. What days work best for both of you?",
            "Hi {patient_name}, we know coordinating with loved ones takes time. We can coordinate directly with {caregiver_name} if you prefer, and find an appointment slot that fits both of your schedules.",
            "Dear {patient_name}, having a trusted caregiver with you is important. We can hold an appointment slot on a Saturday or late afternoon so your caregiver is free to join you."
        ],
        "fear_anxiety_support": [
            "Hello {patient_name}, it is completely natural to feel nervous or worried about clinical procedures. Our nurse specialist is available for a brief, reassuring phone call to explain every step and answer all your questions. Would you like to speak with her?",
            "Hi {patient_name}, we want you to feel safe and fully comfortable. The diagnostic team uses gentle comfort measures and explains everything beforehand. We can also arrange a pre-visit phone chat with a nurse so there are no surprises.",
            "Dear {patient_name}, please know you are in compassionate hands. Many patients feel anxious before these tests, and our team is trained to make the visit as gentle and painless as possible. We are here beside you."
        ],
        "financial_assistance": [
            "Hello {patient_name}, concerns about medical bills or insurance should never delay your health. CareBridge has patient assistance counselors and sliding-scale charity programs available to cover visit costs. May we connect you with a financial navigator?",
            "Hi {patient_name}, we can assist you with coverage navigation or zero-out-of-pocket screening programs. We will put your appointment on hold so you don't lose your spot while we help resolve insurance questions.",
            "Dear {patient_name}, financial assistance is readily available at our partner clinic. Our coordinator can guide you through a simple one-page assistance form so you receive care without financial stress."
        ],
        "scheduling_work_conflict": [
            "Hello {patient_name}, we know work hours can be demanding. We have early morning (7:30 AM), late evening (5:30 PM), and Saturday appointments available, as well as formal work verification letters. Which time slot suits your work hours?",
            "Hi {patient_name}, your health comes first, and we can work around your job schedule. Would an early morning or weekend appointment make it easier for you to attend without missing work?",
            "Dear {patient_name}, we can provide multiple flexible time slots outside normal working hours, and supply medical excuse documentation for your employer if helpful."
        ],
        "unacknowledged_attempt_1": [
            "Hello {patient_name}, this is your CareBridge care coordinator. We recently reached out regarding your screening results. Could you please reply YES or call us back at {phone} to confirm you received this?",
            "Hi {patient_name}, checking in to make sure you received our message about your doctor's follow-up recommendation. Please let us know if you need any assistance.",
            "Dear {patient_name}, your care team wants to make sure you have the information you need. Please reply when you have a moment so we can assist you."
        ],
        "unacknowledged_attempt_2": [
            "Hello {patient_name}, your CareBridge coordinator has tried reaching you. Your screening follow-up is important for your ongoing wellness. Would a phone call at a specific time be better for you?",
            "Hi {patient_name}, we want to make sure you don't miss important next steps. If texting is inconvenient, please let us know a good time to call or if you prefer an alternate contact."
        ],
        "unacknowledged_attempt_3": [
            "URGENT: Hello {patient_name}, your CareBridge care coordinator is concerned about your health journey. Please contact our coordination desk immediately at {phone} or reply to this message.",
            "IMPORTANT NOTICE: {patient_name}, we have been unable to reach you regarding required diagnostic care. A care coordinator is reviewing your case today. Please call {phone} as soon as possible."
        ]
    },
    "es": {
        "clarification_inquiry": [
            "Hola {patient_name}, le escribe el equipo de CareBridge. Notamos que no pudo asistir a su cita del {date_or_recent}. Deseamos asegurarnos de que se encuentre bien. ¿Ocurrió algo y cómo podemos ayudarle a reprogramar?",
            "Estimado/a {patient_name}, nos preocupamos por su salud. ¿Podría decirnos si tuvo alguna dificultad para asistir a su consulta para que podamos brindarle el apoyo necesario?"
        ],
        "transportation_support": [
            "Hola {patient_name}, entendemos que el transporte puede ser un reto. CareBridge puede coordinar transporte gratuito o vales de viaje para su cita médica. ¿Le gustaría que lo organicemos?",
            "Estimado/a {patient_name}, no se preocupe por el viaje. Contamos con transporte seguro de ida y vuelta para su consulta médica."
        ],
        "fear_anxiety_support": [
            "Hola {patient_name}, es normal sentirse nervioso/a ante estos procedimientos. Una enfermera especializada puede llamarle para explicarle cada paso con calma. ¿Le gustaría hablar con ella?",
            "Estimado/a {patient_name}, nuestro equipo médico le brindará una atención compasiva y cómoda. Estamos aquí para acompañarle."
        ],
        "unacknowledged_attempt_1": [
            "Hola {patient_name}, le escribe su coordinador de CareBridge sobre sus resultados médicos. Por favor responda a este mensaje para confirmar que lo recibió.",
            "Estimado/a {patient_name}, su equipo médico desea asegurarse de que tenga la información necesaria. Por favor avísenos cómo podemos ayudarle."
        ]
    },
    "ta": {
        "clarification_inquiry": [
            "வணக்கம் {patient_name}, இது உங்கள் CareBridge பராமரிப்பு குழு. நீங்கள் உங்கள் மருத்துவ சந்திப்பில் கலந்துகொள்ள முடியவில்லை என்பதை கவனித்தோம். உங்களுக்கு ஏதேனும் சிரமம் உள்ளதா? உங்களுக்கு உதவ நாங்கள் தயாராக உள்ளோம்.",
            "அன்புள்ள {patient_name}, உங்கள் உடல்நலம் எங்கள் முன்னுரிமை. உங்கள் மருத்துவ சந்திப்பை மீண்டும் திட்டமிட நாங்கள் எவ்வாறு உதவலாம் என்பதை எங்களுக்குத் தெரிவிக்கவும்."
        ],
        "transportation_support": [
            "வணக்கம் {patient_name}, மருத்துவமனைக்கு வர போக்குவரத்து உதவி தேவையா? எங்கள் குழு உங்களுக்கு இலவச போக்குவரத்து வசதியை ஏற்பாடு செய்ய முடியும். தயவுசெய்து எங்களுக்குத் தெரியப்படுத்துங்கள்."
        ],
        "fear_anxiety_support": [
            "வணக்கம் {patient_name}, மருத்துவ பரிசோதனை குறித்து அச்சம் கொள்வது இயல்பானது. எங்கள் செவிலியர் உங்களுக்கு அனைத்து விவரங்களையும் அன்புடன் விளக்குவார். நீங்கள் அவருடன் பேச விரும்புகிறீர்களா?"
        ],
        "unacknowledged_attempt_1": [
            "வணக்கம் {patient_name}, உங்கள் CareBridge ஒருங்கிணைப்பாளர் உங்களை தொடர்பு கொள்ள முயற்சிக்கிறார். தயவுசெய்து இந்த செய்திக்கு பதிலளிக்கவும்."
        ]
    }
}


class RecoveryPlaybookEngine:
    """Selects and structures recovery strategies based on verified facts and attempt progressions."""

    @classmethod
    def select_playbook(
        cls,
        stalled_signals: List[Dict[str, Any]],
        known_facts: List[Dict[str, Any]],
        assumptions: List[Dict[str, Any]],
        detected_barriers: List[str],
        needs_clarification: bool,
        recovery_attempts: int,
        sla_breached: bool,
        is_referral_stalled: bool
    ) -> str:
        """
        Determines the appropriate recovery playbook:
        1. If SLA is breached or attempts >= 3 -> emergency_escalation
        2. If administrative referral stalled -> delayed_referral_liaison
        3. If needs clarification (cause unknown) -> clarification_inquiry
        4. If specific barrier known -> barrier-specific playbook
        5. If unacknowledged outreach -> unacknowledged_reengagement
        6. Default -> adaptive_coordination_outreach
        """
        if sla_breached or recovery_attempts >= 3:
            return "emergency_escalation"

        if is_referral_stalled:
            return "delayed_referral_liaison"

        if needs_clarification:
            return "clarification_inquiry"

        if "transportation" in detected_barriers:
            return "transportation_support"
        elif "caregiver_family" in detected_barriers:
            return "caregiver_coordination"
        elif "fear_anxiety" in detected_barriers:
            return "fear_anxiety_support"
        elif "financial" in detected_barriers:
            return "financial_assistance"
        elif "scheduling_work" in detected_barriers:
            return "schedule_work_conflict"

        # Check for unacknowledged outreach
        for s in stalled_signals:
            if s.get("type") == "unacknowledged_outreach":
                return "unacknowledged_reengagement"

        return "adaptive_coordination_outreach"

    @classmethod
    def generate_patient_message(
        cls,
        playbook: str,
        patient_name: str,
        language: str = "en",
        attempt: int = 0,
        caregiver_name: Optional[str] = None,
        coordinator_phone: str = "(800) 555-CARE"
    ) -> str:
        """
        Generates a non-fixed, context-aware empathetic message in the patient's language.
        Varies message based on attempt count and specific barriers.
        """
        lang = language if language in MESSAGES else "en"
        lang_dict = MESSAGES[lang]

        # Select category key
        if playbook == "clarification_inquiry":
            cat = "clarification_inquiry"
        elif playbook == "transportation_support":
            cat = "transportation_support"
        elif playbook == "caregiver_coordination":
            cat = "caregiver_coordination"
        elif playbook == "fear_anxiety_support":
            cat = "fear_anxiety_support"
        elif playbook == "financial_assistance":
            cat = "financial_assistance"
        elif playbook == "schedule_work_conflict":
            cat = "schedule_work_conflict"
        elif playbook == "unacknowledged_reengagement":
            if attempt >= 2:
                cat = "unacknowledged_attempt_3"
            elif attempt == 1:
                cat = "unacknowledged_attempt_2"
            else:
                cat = "unacknowledged_attempt_1"
        else:
            cat = "clarification_inquiry"

        # Fallback to English if category not in chosen language
        templates = lang_dict.get(cat) or MESSAGES["en"].get(cat) or MESSAGES["en"]["clarification_inquiry"]

        # Pick template using attempt index modulo length for variety without being purely random
        template_idx = attempt % len(templates)
        template = templates[template_idx]

        return template.format(
            patient_name=patient_name,
            date_or_recent="recently",
            caregiver_name=caregiver_name or "your caregiver",
            phone=coordinator_phone
        )

    @classmethod
    def build_action_plan(
        cls,
        playbook: str,
        case_id: str,
        patient_id: str,
        owner_id: Optional[str],
        patient_name: str,
        language: str,
        attempt: int,
        barriers: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Builds a structured recovery action plan for the agent to execute.
        """
        plan = []

        if playbook == "emergency_escalation":
            plan.append({
                "action": "escalate_case",
                "tool": "escalate_case",
                "parameters": {
                    "case_id": case_id,
                    "urgency": "critical",
                    "reason": f"Care recovery exhausted after {attempt} attempts or SLA breached. Urgent clinical intervention required."
                },
                "autonomy_level": 2,
                "requires_approval": False
            })
            plan.append({
                "action": "notify_coordinator",
                "tool": "notify_case_owner",
                "parameters": {
                    "case_id": case_id,
                    "priority": "critical",
                    "message": "URGENT: Care case escalated to supervisory queue due to recovery exhaustion."
                },
                "autonomy_level": 1,
                "requires_approval": False
            })
            return plan

        if playbook == "delayed_referral_liaison":
            plan.append({
                "action": "create_clinic_liaison_task",
                "tool": "create_followup_task",
                "parameters": {
                    "case_id": case_id,
                    "title": "Liaison with specialist clinic for overdue referral acceptance",
                    "description": "Call receiving clinic radiology/oncology desk to expedite referral acceptance and appointment slot booking.",
                    "task_type": "referral_liaison",
                    "assigned_to_id": owner_id,
                    "assigned_role": "care_coordinator",
                    "due_date": (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
                },
                "autonomy_level": 2,
                "requires_approval": False
            })
            plan.append({
                "action": "notify_coordinator",
                "tool": "notify_case_owner",
                "parameters": {
                    "case_id": case_id,
                    "priority": "urgent",
                    "message": "Referral overdue at receiving clinic. Direct clinic liaison initiated."
                },
                "autonomy_level": 1,
                "requires_approval": False
            })
            return plan

        # Communication action for patient-facing playbooks
        msg_text = cls.generate_patient_message(
            playbook=playbook,
            patient_name=patient_name,
            language=language,
            attempt=attempt
        )

        plan.append({
            "action": "send_recovery_communication",
            "tool": "send_permitted_communication",
            "parameters": {
                "case_id": case_id,
                "patient_id": patient_id,
                "message": msg_text,
                "channel": "sms",
                "language": language
            },
            "autonomy_level": 2,
            "requires_approval": False
        })

        # Update case notes
        note_text = f"Care Recovery Agent (Attempt #{attempt + 1}): Triggered playbook '{playbook}' for barriers: {', '.join(barriers) if barriers else 'unspecified'}."
        plan.append({
            "action": "update_case_notes",
            "tool": "update_permitted_case_notes",
            "parameters": {
                "case_id": case_id,
                "note": note_text
            },
            "autonomy_level": 2,
            "requires_approval": False
        })

        # Follow-up task for the coordinator
        task_title = f"Recovery Follow-up (#{attempt + 1}): {playbook.replace('_', ' ').title()}"
        task_desc = f"Monitor patient response to {playbook}. If no response within 24h, advance recovery protocol."
        plan.append({
            "action": "create_recovery_task",
            "tool": "create_followup_task",
            "parameters": {
                "case_id": case_id,
                "title": task_title,
                "description": task_desc,
                "task_type": "recovery_play",
                "assigned_to_id": owner_id,
                "assigned_role": "care_coordinator",
                "due_date": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            },
            "autonomy_level": 2,
            "requires_approval": False
        })

        # Notify coordinator of the action taken
        plan.append({
            "action": "notify_coordinator",
            "tool": "notify_case_owner",
            "parameters": {
                "case_id": case_id,
                "priority": "normal" if attempt == 0 else "urgent",
                "message": f"Care Recovery Agent executed playbook '{playbook}' (Attempt #{attempt + 1}). Accountable coordinator kept informed."
            },
            "autonomy_level": 1,
            "requires_approval": False
        })

        return plan
