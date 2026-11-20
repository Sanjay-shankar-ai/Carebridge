"""
CareBridge Recovery Agent
Specialized agent responsible for:
- Detecting and resolving missed appointments, no-shows, and cancellations
- Analyzing patient-reported barriers (transportation/caregiver, financial, childcare, fear/anxiety)
- Recommending and initiating tailored recovery playbooks
- Generating prioritized follow-up outreach tasks for Care Coordinators
- Tracking recovery attempt counts and escalating if recovery threshold is exceeded
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from app.agents.state import CoordinationPlan, ProposedAction, IntentAnalysis


class RecoveryAgent:
    """Specialized agent for barrier mitigation, missed appointment recovery, and care retention."""

    @classmethod
    def _resolve_lang(cls, intent: IntentAnalysis, patient_context: Dict[str, Any]) -> str:
        raw_q = intent.raw_query or ""
        # Strictly English unless non-English script is typed
        if any("\u0b80" <= c <= "\u0bff" for c in raw_q):
            return "ta"
        if any("\u0600" <= c <= "\u06ff" for c in raw_q):
            return "ar"
        if intent.detected_language == "es" and any(w in raw_q.lower() for w in ["hola", "cita", "médico", "biopsia", "gracias"]):
            return "es"
        return "en"

    @classmethod
    def formulate_barrier_reschedule_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any]
    ) -> CoordinationPlan:
        """Formulates a recovery plan addressing transportation, caregiver, or scheduling barriers."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = patient_context.get("first_name") or (patient_context.get("full_name", "").split()[0] if patient_context.get("full_name") else "")
        lang = cls._resolve_lang(intent, patient_context)
        doc_name = case_context.get("assigned_doctor_name") or case_context.get("doctor_name") or "Dr. Arjun Menon"
        facility = case_context.get("facility") or "CareBridge Demo Clinic"
        specialty = case_context.get("specialty") or "Breast Oncology"

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="update_case_notes",
                arguments={
                    "case_id": case_id,
                    "note": "Patient reported caregiver/transportation barrier. Scheduling flexibility required.",
                    "barrier_detected": "transportation_caregiver"
                },
                rationale="Document social determinant barrier in persistent case memory.",
                autonomy_level=1
            ),
            ProposedAction(
                step_number=2,
                tool_name="search_available_appointments",
                arguments={
                    "facility": facility,
                    "specialty": specialty,
                    "timeframe": "next_10_days"
                },
                rationale="Identify rescheduled slot that accommodates caregiver availability within SLA clock.",
                autonomy_level=1
            ),
            ProposedAction(
                step_number=3,
                tool_name="create_followup_task",
                arguments={
                    "case_id": case_id,
                    "title": "Verify caregiver return date and finalize rebooked visit",
                    "description": "Confirm transportation arrangements with patient or designated caregiver.",
                    "task_type": "recovery_play",
                    "due_date": (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT10:00:00Z"),
                    "assigned_role": "care_coordinator"
                },
                rationale="Schedule proactive recovery check so case maintains continuous ownership.",
                autonomy_level=1
            )
        ]

        p_disp = f", {patient_name}" if patient_name else ""
        has_transit_barrier = any(b.barrier_type in ("transportation", "transit", "travel", "ride") for b in intent.detected_barriers)
        has_caregiver_barrier = any(b.barrier_type in ("caregiver", "family") for b in intent.detected_barriers)

        if has_transit_barrier and not has_caregiver_barrier:
            if lang == "ta":
                msg = (
                    f"போக்குவரத்து வசதி பெறுவது சில நேரங்களில் கடினமாக இருக்கும் என்பதை நாங்கள் புரிந்துகொள்கிறோம்{p_disp}. "
                    "மருத்துவமனைக்கு வந்து செல்ல போக்குவரத்து உதவி மற்றும் பயண வவுச்சர்களை எங்களால் ஏற்பாடு செய்ய முடியும். "
                    "உங்களுக்கு இந்த உதவி தேவைப்படுகிறதா?"
                )
            elif lang == "es":
                msg = (
                    f"Comprendemos que conseguir transporte para asistir a su consulta puede ser difícil{p_disp}. "
                    "En CareBridge podemos coordinar vales de transporte clínico o asistencia de viaje para asegurar su traslado seguro. "
                    "¿Desea que organicemos este apoyo para su próxima visita?"
                )
            elif lang == "ar":
                msg = (
                    f"نتفهم تماماً أن تأمين وسيلة مواصلات للوصول إلى العيادة قد يمثل تحدياً{p_disp}. "
                    "يمكننا التنسيق لتوفير قسائم مواصلات طبية تضمن وصولكِ بأمان. "
                    "هل تودين أن نقوم بترتيب مساعدة في المواصلات لموعدكِ القادم؟"
                )
            else:
                msg = (
                    f"We understand that arranging transportation can feel challenging while navigating care{p_disp}. "
                    "Our coordination team can provide medical ride assistance or transit vouchers so you can attend safely. "
                    "Would you like us to arrange transportation support for your upcoming clinic visit?"
                )
        else:
            if lang == "ta":
                msg = (
                    f"உங்கள் நிலைமையை நாங்கள் முழுமையாகப் புரிந்துகொள்கிறோம்{p_disp}. உங்கள் குடும்பத்தாரின் வருகைக்கு ஏற்ப நாங்கள் மருத்துவரை சந்திக்கும் "
                    "நேரத்தை மாற்றி அமைக்கிறோம். அவர் எப்போது ஊரிலிருந்து திரும்புவார் என்று கூற இயலுமா? அதற்கேற்ப புதிய நேரத்தை ஒதுக்குகிறோம்."
                )
            elif lang == "es":
                msg = (
                    f"Comprendemos perfectamente su situación{p_disp}. Coordinaremos con la clínica para reprogramar su consulta "
                    "de modo que su familiar o cuidador pueda acompañarle con tranquilidad. ¿Podría indicarnos qué día estarán de regreso?"
                )
            elif lang == "ar":
                msg = (
                    f"نتفهم تماماً ظروفكِ{p_disp}. سنقوم بالتنسيق مع العيادة لتعديل موعد استشارتكِ بحيث يتمكن مرافقكِ من الحضور معكِ براحة. هل يمكنكِ إعلامنا بتاريخ عودتهم؟"
                )
            else:
                msg = (
                    f"We completely understand how important family and caregiver support is{p_disp}. We will coordinate with the clinic to reschedule "
                    "your consultation so your caregiver or family member can safely accompany you. Could you share what day they return?"
                )

        return CoordinationPlan(
            goal="Resolve transportation/caregiver barrier and maintain screening-to-care SLA continuity.",
            situation_summary="Patient flagged inability to attend appointment due to caregiver travel or transport barrier.",
            actions=actions,
            patient_response_draft=msg,
            target_language=lang
        )

    @classmethod
    def formulate_assistance_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any]
    ) -> CoordinationPlan:
        """Handles financial, cost, or childcare assistance requests."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = patient_context.get("first_name") or (patient_context.get("full_name", "").split()[0] if patient_context.get("full_name") else "")
        lang = cls._resolve_lang(intent, patient_context)
        barrier_type = "financial" if any(b.barrier_type == "financial" for b in intent.detected_barriers) else "childcare_family"

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="update_case_notes",
                arguments={
                    "case_id": case_id,
                    "note": f"Patient requested logistical assistance. Barrier identified: {barrier_type}.",
                    "barrier_detected": barrier_type
                },
                rationale="Record social barrier requiring coordinator assistance.",
                autonomy_level=1
            ),
            ProposedAction(
                step_number=2,
                tool_name="create_followup_task",
                arguments={
                    "case_id": case_id,
                    "title": f"Connect patient with {barrier_type.replace('_', ' ')} support program",
                    "description": "Assess patient eligibility for hospital copay assistance or community support resources.",
                    "task_type": "barrier_resolution",
                    "due_date": (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00Z"),
                    "assigned_role": "care_coordinator"
                },
                rationale="Route social determinant need to dedicated care navigator.",
                autonomy_level=1
            )
        ]

        if lang == "ta":
            msg = (
                f"கவலைப்பட வேண்டாம் {patient_name}. எங்கள் பராமரிப்பு குழுவில் உள்ள மருத்துவ சமூக நல அலுவலர் "
                "தங்களுக்கு தேவையான நிதி உதவி மற்றும் வழிகாட்டுதல்களை வழங்க விரைவில் தொடர்பு கொள்வார்."
            )
        else:
            msg = (
                f"Your health and peace of mind come first, {patient_name}. We have financial counseling and community assistance "
                "programs specifically designed to support patients. Your care coordinator Priya Nair will reach out to discuss available coverage options."
            )

        return CoordinationPlan(
            goal=f"Mitigate {barrier_type} barrier and connect patient to institutional support.",
            situation_summary=f"Patient expressed logistical or financial concern ({barrier_type}).",
            actions=actions,
            patient_response_draft=msg,
            target_language=lang
        )

    @classmethod
    def formulate_missed_visit_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any]
    ) -> CoordinationPlan:
        """Formulates proactive outreach recovery plan following a missed appointment."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = patient_context.get("first_name") or (patient_context.get("full_name", "").split()[0] if patient_context.get("full_name") else "")
        lang = cls._resolve_lang(intent, patient_context)
        doc_name = case_context.get("assigned_doctor_name") or case_context.get("doctor_name") or "Dr. Arjun Menon"
        facility = case_context.get("facility") or "CareBridge Demo Clinic"
        specialty = case_context.get("specialty") or "Breast Oncology"

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="update_case_notes",
                arguments={
                    "case_id": case_id,
                    "note": "Patient missed scheduled clinical visit. Recovery play initiated.",
                    "barrier_detected": "schedule_conflict"
                },
                rationale="Flag missed milestone in audit history.",
                autonomy_level=1
            ),
            ProposedAction(
                step_number=2,
                tool_name="search_available_appointments",
                arguments={
                    "facility": facility,
                    "specialty": specialty,
                    "timeframe": "next_7_days"
                },
                rationale="Identify immediate replacement openings within SLA clock.",
                autonomy_level=1
            ),
            ProposedAction(
                step_number=3,
                tool_name="create_followup_task",
                arguments={
                    "case_id": case_id,
                    "title": "Engage patient for missed visit recovery",
                    "description": "Assess root-cause obstacle that led to missed appointment and confirm new date.",
                    "task_type": "recovery_play",
                    "due_date": (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00Z"),
                    "assigned_role": "care_coordinator"
                },
                rationale="Ensure human coordinator follow-up so patient does not drop out of care loop.",
                autonomy_level=1
            )
        ]

        if lang == "ta":
            msg = (
                f"மருத்துவரை சந்திக்க முடியாத நிலை ஏற்பட்டதை நாங்கள் உணர்கிறோம் {patient_name}. "
                f"தங்களின் உடல்நலம் எங்களுக்கு மிக முக்கியம். டாக்டர் {doc_name} அவர்களின் மையத்தில் "
                "அடுத்த சில நாட்களில் உள்ள புதிய நேரங்களில் எப்போது உங்களால் வர இயலும்?"
            )
        else:
            msg = (
                f"We noticed you were unable to make your appointment, {patient_name}. We understand unexpected things arise and our team is right here with you. "
                f"Because following up on your screening is important, we have held priority slots with {doc_name} next week. "
                "Would morning or afternoon work better for you to reschedule?"
            )

        return CoordinationPlan(
            goal="Recover missed appointment and secure replacement visit within SLA window.",
            situation_summary="Patient reported or incurred missed diagnostic appointment.",
            actions=actions,
            patient_response_draft=msg,
            target_language=lang
        )

    @classmethod
    def formulate_cancellation_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any]
    ) -> CoordinationPlan:
        """Handles explicit patient cancellation or care drop-out risk."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = patient_context.get("first_name") or (patient_context.get("full_name", "").split()[0] if patient_context.get("full_name") else "")
        lang = cls._resolve_lang(intent, patient_context)
        appointment_id = case_context.get("upcoming_appointment_id") or str(case_context.get("appointment_id") or "")

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="cancel_appointment",
                arguments={
                    "appointment_id": appointment_id,
                    "case_id": case_id,
                    "reason": "Patient requested cancellation / expressed reluctance",
                    "outcome": "recovery_play_initiated",
                    "detailed_notes": "Patient requested cancellation. Clinical navigation outreach triggered."
                },
                rationale="Record cancellation reason and transition case to recovery pathway.",
                autonomy_level=2
            ),
            ProposedAction(
                step_number=2,
                tool_name="escalate_case",
                arguments={
                    "case_id": case_id,
                    "urgency": "urgent",
                    "reason": "Patient requested appointment cancellation for actionable screening finding."
                },
                rationale="Never let actionable finding become a dead end: escalate to clinical team for outreach.",
                autonomy_level=2
            )
        ]

        msg = (
            f"Your appointment has been cancelled as requested, {patient_name}. Because your screening result is important for your health, "
            "our clinical care coordinator Priya Nair will remain available should you wish to discuss your options or reschedule at any time."
        )

        return CoordinationPlan(
            goal="Process patient cancellation while escalating to prevent care drop-out.",
            situation_summary="Patient requested cancellation of actionable screening follow-up.",
            actions=actions,
            patient_response_draft=msg,
            target_language=lang
        )

    @classmethod
    def formulate_referral_deferral_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any],
        conversation_context: Optional[Dict[str, Any]] = None
    ) -> CoordinationPlan:
        """Handles respectful patient deferral of referral or consultation without coercion or false acceptance."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = patient_context.get("first_name") or (patient_context.get("full_name", "").split()[0] if patient_context.get("full_name") else "")
        lang = cls._resolve_lang(intent, patient_context)
        finding_code = case_context.get("finding_code", "BI-RADS 4")

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="update_case_notes",
                arguments={
                    "case_id": case_id,
                    "note": f"Patient requested to defer referral/appointment for {finding_code}. Documented timeline with supportive empathy.",
                    "barrier_detected": "patient_deferral"
                },
                rationale="Record patient deferral in case notes without coercing immediate booking.",
                autonomy_level=1
            ),
            ProposedAction(
                step_number=2,
                tool_name="create_followup_task",
                arguments={
                    "case_id": case_id,
                    "title": "Respectful follow-up check-in for deferred referral",
                    "description": "Patient chose to wait before scheduling. Follow up gently in 7 days to reassess readiness.",
                    "task_type": "patient_outreach",
                    "due_date": (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%dT10:00:00Z"),
                    "assigned_role": "care_coordinator"
                },
                rationale="Schedule non-intrusive reminder follow-up with care coordinator.",
                autonomy_level=1
            )
        ]

        if lang == "ta":
            msg = (
                f"உங்கள் முடிவை நாங்கள் மதிக்கிறோம் {patient_name}. மருத்துவ முடிவுகளை எடுப்பது சில நேரங்களில் தயக்கத்தை ஏற்படுத்தலாம், "
                "நீங்கள் யோசித்து முடிவெடுக்க முழு உரிமை உண்டு. அதே சமயம், தங்களின் பரிசோதனை ({finding_code}) குறித்த பாதுகாப்பிற்காக "
                "சரியான நேரத்தில் பரிசோதிப்பது நல்லது. நாங்கள் உங்களை அவசரப்படுத்த மாட்டோம்; எப்போது தயாராக உணர்கிறீர்களோ அப்போது எங்களை "
                "தொடர்பு கொள்ளலாம். உங்களுக்கு ஏதேனும் சந்தேகம் இருந்தால் தயங்காமல் கேளுங்கள்."
            )
        else:
            msg = (
                f"We completely respect your pace, {patient_name}. We understand that making healthcare decisions can feel overwhelming, "
                "and you have every right to take time to consider your next steps. At the same time, because your screening noted a "
                f"{finding_code} finding, timely evaluation is the safest way to ensure your peace of mind and protect your health. "
                "We will not rush you. Your care coordinator Priya Nair, RN can check in with you in a week to see how you are feeling, "
                "or you can message us whenever you are ready. Is there any specific concern or question on your mind that I can help address?"
            )

        return CoordinationPlan(
            goal="Honor patient deferral decision while maintaining safe follow-up continuity.",
            situation_summary="Patient requested to wait or delay referral evaluation.",
            actions=actions,
            patient_response_draft=msg,
            target_language=lang
        )
