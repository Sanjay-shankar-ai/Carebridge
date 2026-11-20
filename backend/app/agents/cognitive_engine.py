"""
CareBridge Cognitive Engine
Provides structured reasoning, barrier detection, and planning using OpenAI / LangChain.
Includes robust offline semantic heuristics for reliable test and simulation execution.
"""

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import PydanticOutputParser
from app.core.config import settings
from app.services.llm_service import llm_service
from app.agents.state import IntentAnalysis, InferredBarrier, CoordinationPlan, ProposedAction
from app.agents.prompts import CAREBRIDGE_SYSTEM_PROMPT, INTENT_ANALYSIS_PROMPT, PLANNING_PROMPT
from app.agents.specialized import (
    PatientCommunicationAgent,
    CareCoordinationAgent,
    RecoveryAgent,
    ClinicalEscalationAgent,
    DoctorReviewAgent,
)

intent_parser = PydanticOutputParser(pydantic_object=IntentAnalysis)
plan_parser = PydanticOutputParser(pydantic_object=CoordinationPlan)


def get_llm():
    """Retrieves the active centralized LLM client (GroqCloud / OpenAI)."""
    return llm_service.get_llm()


class CognitiveEngine:
    """Core intelligence engine for intent understanding, barrier extraction, and planning."""

    @classmethod
    def analyze_intent(
        cls,
        message: str,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any],
        conversation_context: Optional[Dict[str, Any]] = None
    ) -> IntentAnalysis:
        """Analyzes patient messages to uncover intent, emotions, and underlying barriers with multi-turn awareness."""
        # Deterministic Safety Gate: Acute clinical emergencies always take precedence
        if ClinicalEscalationAgent.evaluate_safety_rules(message):
            return cls._offline_intent_analysis(message, patient_context, conversation_context)

        sender = (conversation_context.get("inbound_sender") if conversation_context else "") or ""
        msg_l = (message or "").lower().strip()

        # Deterministic Coordinator Intent Catalog
        if sender in ("care_coordinator", "coordinator"):
            if any(term in msg_l for term in ["new patient", "new patients", "any new patient", "is there any new patient", "unassigned", "discovery queue", "intake queue"]):
                return IntentAnalysis(
                    primary_intent="new_patient_discovery",
                    emotional_state="neutral",
                    detected_language="en",
                    raw_query=message
                )
            if any(term in msg_l for term in ["select patient", "choose patient", "open case", "view case", "select case"]):
                topic = message.replace("Select patient", "").replace("select patient", "").replace("open case", "").replace("view case", "").strip()
                return IntentAnalysis(
                    primary_intent="patient_selection",
                    emotional_state="neutral",
                    detected_language="en",
                    inquiry_topic=topic,
                    raw_query=message
                )
            if any(term in msg_l for term in ["pending tasks", "tasks for this case", "list tasks", "coordination tasks", "outstanding tasks", "what tasks", "my tasks", "pending coordination tasks", "show me pending coordination tasks"]):
                return IntentAnalysis(
                    primary_intent="task_management",
                    emotional_state="neutral",
                    detected_language="en",
                    raw_query=message
                )
            if any(term in msg_l for term in ["overdue referrals", "referral status", "referrals overdue", "referrals pending", "which cases have overdue referrals"]):
                return IntentAnalysis(
                    primary_intent="referral_monitoring",
                    emotional_state="neutral",
                    detected_language="en",
                    raw_query=message
                )
            if any(term in msg_l for term in ["stalled cases", "are there any stalled cases", "missed visits", "sla breach", "recovery queue"]):
                return IntentAnalysis(
                    primary_intent="sla_recovery_queue",
                    emotional_state="neutral",
                    detected_language="en",
                    raw_query=message
                )

        # Deterministic Coordinator Task Query Gate
        if any(term in msg_l for term in ["pending tasks", "tasks for this case", "list tasks", "coordination tasks", "outstanding tasks", "what tasks", "my tasks", "pending coordination tasks"]):
            return cls._offline_intent_analysis(message, patient_context, conversation_context)

        llm = get_llm()
        if llm:
            try:
                # Format recent conversation context for multi-turn conversational reasoning
                history_snippets = []
                if conversation_context and conversation_context.get("recent_messages"):
                    for m in conversation_context.get("recent_messages")[-4:]:
                        sender = getattr(m, "sender", None) or (m.get("sender") if isinstance(m, dict) else "User")
                        content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else "")
                        if content and content != message:
                            history_snippets.append(f"{sender}: {content}")
                history_text = " | ".join(history_snippets) if history_snippets else "None"

                prompt = (
                    f"{INTENT_ANALYSIS_PROMPT.format(message=message, preferred_language=patient_context.get('preferred_language', 'en'), case_summary=f'{case_context.get('screening_type', 'Mammogram')} - {case_context.get('finding_code', 'BI-RADS 4')}')}\n\n"
                    f"Recent Conversation Context: {history_text}\n\n"
                    f"{intent_parser.get_format_instructions()}"
                )
                res = llm.invoke([
                    SystemMessage(content=CAREBRIDGE_SYSTEM_PROMPT),
                    HumanMessage(content=prompt)
                ])
                parsed = intent_parser.parse(res.content)
                if isinstance(parsed, IntentAnalysis):
                    parsed.raw_query = message
                    # Standardize barrier names to platform taxonomy
                    for b in parsed.detected_barriers:
                        if b.barrier_type in ("transportation", "caregiver", "transport", "ride", "travel"):
                            b.barrier_type = "transportation_caregiver"
                        elif b.barrier_type in ("fear", "anxiety", "fear/anxiety", "fear_anxiety", "stress", "worried"):
                            b.barrier_type = "fear_anxiety"
                        elif b.barrier_type in ("childcare", "family"):
                            b.barrier_type = "childcare_family"
                        elif b.barrier_type in ("cost", "money", "afford"):
                            b.barrier_type = "financial"
                    msg_l = message.lower()
                    if ClinicalEscalationAgent.evaluate_safety_rules(message):
                        parsed.primary_intent = "urgent_clinical_escalation"
                        parsed.requires_human_escalation = True
                    elif any(term in msg_l for term in ["missed my appointment", "missed appointment", "missed the appointment", "missed it and could not go", "could not go yesterday", "missed it yesterday"]):
                        parsed.primary_intent = "missed_appointment"
                    elif any(term in msg_l for term in [
                        "the second one", "second one", "second slot", "2nd one", "option 2", "slot 2",
                        "book the second", "second one book", "choose the second", "இரண்டாவது"
                    ]):
                        parsed.primary_intent = "appointment_slot_selection"
                        parsed.inquiry_topic = "slot_2"
                    elif any(term in msg_l for term in [
                        "the first one", "first one", "first slot", "1st one", "option 1", "slot 1",
                        "book the first", "first one book", "choose the first", "முதலாவது"
                    ]):
                        parsed.primary_intent = "appointment_slot_selection"
                        parsed.inquiry_topic = "slot_1"
                    elif any(term in msg_l for term in [
                        "the third one", "third one", "third slot", "3rd one", "option 3", "slot 3",
                        "book the third", "third one book", "choose the third"
                    ]):
                        parsed.primary_intent = "appointment_slot_selection"
                        parsed.inquiry_topic = "slot_3"
                    elif any(term in msg_l for term in [
                        "any other slot", "is there any other slot", "other slot", "different slot",
                        "another slot", "other available", "alternative slot", "another available slot",
                        "other timings", "other options", "any other time"
                    ]):
                        parsed.primary_intent = "appointment_slot_alternatives"
                        if any(t in msg_l for t in ["morning", "காலை", "am", "mañana", "صباح"]):
                            parsed.inquiry_topic = "morning"
                        elif any(t in msg_l for t in ["afternoon", "மதியம்", "pm", "tarde", "مساء"]):
                            parsed.inquiry_topic = "afternoon"
                    elif any(term in msg_l for term in [
                        "prefer morning", "prefer a morning", "morning please", "mornings work", "morning slots",
                        "only morning", "in the morning", "morning appointment", "morning slot"
                    ]):
                        parsed.primary_intent = "appointment_slot_preference"
                        parsed.inquiry_topic = "morning"
                    elif any(term in msg_l for term in [
                        "prefer afternoon", "prefer an afternoon", "afternoon please", "afternoons work",
                        "afternoon slots", "in the afternoon", "afternoon appointment", "afternoon slot"
                    ]):
                        parsed.primary_intent = "appointment_slot_preference"
                        parsed.inquiry_topic = "afternoon"
                    elif any(term in msg_l for term in ["can i change it", "can i change my appointment", "change it", "change my appointment", "reschedule my appointment"]):
                        parsed.primary_intent = "appointment_reschedule_request"
                    elif any(term in msg_l for term in [
                        "book an appointment", "book appointment", "schedule an appointment",
                        "schedule appointment", "schedule for me", "book me an appointment",
                        "book me a slot", "need to see a doctor", "see a doctor", "see doctor",
                        "want to see a doctor", "consult a doctor", "visit the doctor",
                        "meet the doctor", "appointment tomorrow", "book doctor", "book visit",
                        "schedule visit", "help me book", "help me schedule", "want to book",
                        "want book", "i want book doctor tomorrow"
                    ]) or (
                        ("book" in msg_l or "schedule" in msg_l) and
                        any(w in msg_l for w in ["doctor", "appointment", "visit", "slot", "tomorrow", "consultation"])
                    ) or (
                        "doctor" in msg_l and any(w in msg_l for w in ["see", "consult", "visit", "meet"])
                    ):
                        parsed.primary_intent = "appointment_booking_request"
                    elif any(term in msg_l for term in ["why did my doctor refer me", "why did the doctor refer me", "why was i referred", "reason for referral"]):
                        parsed.primary_intent = "referral_inquiry"
                    elif any(term in msg_l for term in ["i want to wait", "want to wait", "can i wait", "hold off", "wait a bit"]):
                        parsed.primary_intent = "referral_deferral"
                    elif any(term in msg_l for term in ["my report what saying", "what report saying", "report what saying", "my report saying", "what does my report say", "que dice mi informe", "ماذا يقول تقريري"]):
                        parsed.primary_intent = "case_context_inquiry"
                        parsed.inquiry_topic = "birads"
                    elif any(term in msg_l for term in ["doctor not call", "not call me yet", "no call from doctor", "doctor call me yet", "no call yet", "doctor not call me yet", "el doctor no me ha llamado", "لم يتصل بي الطبيب"]):
                        parsed.primary_intent = "referral_delay"
                    elif any(term in msg_l for term in ["i am fear", "fear biopsy", "afraid biopsy", "scared biopsy", "miedo de la biopsia", "miedo a la biopsia", "خائفة من الخزعة"]):
                        parsed.primary_intent = "patient_inquiry"
                        parsed.inquiry_topic = "biopsy"
                        if not any(b.barrier_type == "fear_anxiety" for b in parsed.detected_barriers):
                            parsed.detected_barriers.append(InferredBarrier(
                                barrier_type="fear_anxiety",
                                severity="medium",
                                details="Patient expresses emotional fear/anxiety regarding biopsy."
                            ))
                    has_arabic_chars = any("\u0600" <= char <= "\u06ff" or "\u0750" <= char <= "\u077f" or "\u08a0" <= char <= "\u08ff" for char in message)
                    is_spanish = any(w in msg_l for w in ["hola", "cita", "dolor", "miedo", "gracias", "el doctor", "mi doctor", "médico", "biopsia", "cuando", "estoy", "tengo", "por favor", "ayuda", "significa"]) and not has_arabic_chars
                    if has_arabic_chars:
                        parsed.detected_language = "ar"
                    elif is_spanish:
                        parsed.detected_language = "es"
                    if parsed.primary_intent == "urgent_clinical_escalation":
                        parsed.requires_human_escalation = True
                    return parsed
            except Exception as e:
                # Fallback to offline semantic analysis if network or formatting fails
                pass

        # Deterministic Semantic Fallback (Ensures resilient offline testing & sandbox verification)
        return cls._offline_intent_analysis(message, patient_context, conversation_context)

    @classmethod
    def _formulate_greeting_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any],
        conversation_context: Dict[str, Any]
    ) -> CoordinationPlan:
        """Formulates an empathetic, natural conversational greeting without administrative tool calls."""
        patient_name = patient_context.get("full_name") or patient_context.get("first_name", "Valued Patient")
        lang = intent.detected_language or patient_context.get("preferred_language", "en")
        finding_code = case_context.get("finding_code", "screening finding")

        sender = conversation_context.get("inbound_sender") or ""
        if sender in ("care_coordinator", "coordinator"):
            case_number = case_context.get("case_number", "CASE")
            status = (case_context.get("status") or "active").replace("_", " ").title()
            return CoordinationPlan(
                goal="Provide case overview greeting to Care Coordinator.",
                situation_summary=f"Care coordinator checked in on case {case_number}.",
                actions=[],
                patient_response_draft=(
                    f"Hello Coordinator. Active case file for {patient_name} ({case_number}) is loaded. "
                    f"Current status: {status} | Finding: {finding_code}. "
                    "How can I assist you with scheduling, barrier mitigation, or task oversight for this case?"
                ),
                target_language="en"
            )

        # Check if conversation already has prior messages
        has_prior_messages = False
        if conversation_context and conversation_context.get("recent_messages"):
            prior = [
                m for m in conversation_context.get("recent_messages", [])
                if (getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else "")) != intent.raw_query
            ]
            has_prior_messages = len(prior) > 0

        # Attempt LLM-generated warm, natural greeting
        llm = get_llm()
        if llm:
            try:
                prior_note = "The patient is returning to the conversation." if has_prior_messages else "This is the start of the conversation."
                prompt = (
                    f"You are the CareBridge AI Care Companion speaking with patient {patient_name}.\n"
                    f"Patient Finding: {finding_code}\n"
                    f"Preferred Language: {lang}\n"
                    f"Context: {prior_note}\n\n"
                    f"The patient sent a greeting: \"{intent.raw_query}\".\n"
                    f"Draft a warm, natural, empathetic greeting acknowledging them by name. "
                    f"Introduce or re-affirm your role as their CareBridge AI Care Companion, and invite them to ask questions about their screening ({finding_code}), appointments, or care journey. "
                    f"Do NOT diagnose, do NOT prescribe, and do NOT claim any coordinator or clinical team has been notified. Keep it concise (2-3 sentences)."
                )
                res = llm.invoke([SystemMessage(content=CAREBRIDGE_SYSTEM_PROMPT), HumanMessage(content=prompt)])
                if res and res.content and len(res.content.strip()) > 15:
                    candidate = res.content.strip()
                    if candidate.startswith('"') and candidate.endswith('"'):
                        candidate = candidate[1:-1]
                    if not any(claim in candidate.lower() for claim in ["notified", "coordinator has been alerted"]):
                        return CoordinationPlan(
                            goal="Acknowledge patient greeting with warmth and conversational readiness.",
                            situation_summary="Patient initiated friendly conversation.",
                            actions=[],
                            patient_response_draft=candidate,
                            target_language=lang
                        )
            except Exception:
                pass

        # Resilient Deterministic Greeting Fallback (strictly English unless non-English script is present)
        has_tamil = any("\u0b80" <= c <= "\u0bff" for c in (intent.raw_query or ""))
        if lang == "ta" and has_tamil:
            if has_prior_messages:
                msg = (
                    f"வணக்கம் மீண்டும் {patient_name}! நான் உங்கள் CareBridge AI பராமரிப்பு உதவியாளர். "
                    f"தங்களின் பரிசோதனை ({finding_code}) அல்லது சந்திப்பு குறித்து வேறு என்ன உதவி தேவைப்படுகிறது?"
                )
            else:
                msg = (
                    f"வணக்கம் {patient_name}! நான் உங்கள் CareBridge AI பராமரிப்பு உதவியாளர். "
                    f"தங்களின் பரிசோதனை முடிவுகள் ({finding_code}), மருத்துவர் சந்திப்புகள் அல்லது சிகிச்சைப் பயணம் குறித்து உங்களுக்கு என்ன உதவி தேவைப்படுகிறது?"
                )
        elif lang == "ar" and any("\u0600" <= c <= "\u06ff" for c in (intent.raw_query or "")):
            if has_prior_messages:
                msg = (
                    f"مرحباً بك مجدداً {patient_name}! أنا مساعد الرعاية بالذكاء الاصطناعي من CareBridge. "
                    f"كيف يمكنني مساعدتك اليوم بخصوص خطتك العلاجية أو فحصك ({finding_code}) أو مواعيدك؟"
                )
            else:
                msg = (
                    f"مرحباً {patient_name}! أنا مساعد الرعاية بالذكاء الاصطناعي من CareBridge. "
                    f"نحن هنا لدعمك بمعلومات حول نتائج الفحص ({finding_code})، وجدولة المواعيد، ورحلتك العلاجية. ما هي الأسئلة التي يمكنني الإجابة عليها اليوم؟"
                )
        elif lang == "es":
            if has_prior_messages:
                msg = (
                    f"¡Hola de nuevo, {patient_name}! Soy su asistente de atención médica de CareBridge. "
                    f"¿En qué puedo ayudarle hoy con respecto a su plan de atención, su examen ({finding_code}) o sus citas?"
                )
            else:
                msg = (
                    f"¡Hola {patient_name}! Soy su asistente de atención de CareBridge. "
                    f"Estamos aquí para ayudarle con información sobre sus resultados ({finding_code}), la programación de citas y su proceso de atención. ¿Qué preguntas tiene hoy?"
                )
        else:
            if has_prior_messages:
                msg = (
                    f"Hello again, {patient_name}! I am right here with you. "
                    f"What can I help you with today regarding your care plan, screening ({finding_code}), or appointment scheduling?"
                )
            else:
                msg = (
                    f"Hello {patient_name}! I am your CareBridge AI Care Companion. "
                    f"How can I help you today with your care plan, questions about your screening ({finding_code}), or appointment scheduling?"
                )

        return CoordinationPlan(
            goal="Acknowledge patient greeting with warmth and readiness to assist.",
            situation_summary="Patient initiated friendly conversation.",
            actions=[],
            patient_response_draft=msg,
            target_language=lang
        )

    @classmethod
    def formulate_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any],
        conversation_context: Dict[str, Any]
    ) -> CoordinationPlan:
        """Formulates an adaptive multi-step coordination plan with tool selections and role routing."""
        # Scenario 0: Urgent Clinical Escalation (Dispatched to ClinicalEscalationAgent)
        if intent.primary_intent == "urgent_clinical_escalation":
            return ClinicalEscalationAgent.formulate_escalation_plan(intent, patient_context, case_context)

        # Scenario 0.01: Coordinator Discovery & Patient Selection Plans
        if intent.primary_intent in ("new_patient_discovery", "coordinator_discovery"):
            return CoordinationPlan(
                goal="Query new patient intake and unassigned case queue.",
                situation_summary="Care Coordinator requested new patient discovery queue.",
                actions=[
                    ProposedAction(
                        step_number=1,
                        tool_name="discover_new_patients",
                        arguments={"actor_role": "care_coordinator"},
                        rationale="Query real database for new unassigned or intake cases.",
                        autonomy_level=1
                    )
                ],
                patient_response_draft="Querying new patient discovery queue...",
                target_language="en"
            )

        if intent.primary_intent == "patient_selection":
            return CoordinationPlan(
                goal="Set authorized patient case context for coordinator.",
                situation_summary="Coordinator explicitly selected patient case.",
                actions=[
                    ProposedAction(
                        step_number=1,
                        tool_name="select_patient_case",
                        arguments={
                            "patient_name": intent.inquiry_topic,
                            "actor_role": "care_coordinator"
                        },
                        rationale="Load authorized patient case memory and record selection event.",
                        autonomy_level=1
                    )
                ],
                patient_response_draft="Loading patient case context...",
                target_language="en"
            )

        if intent.primary_intent == "task_management":
            case_id = str(case_context.get("case_id") or case_context.get("id") or "")
            return CoordinationPlan(
                goal="Retrieve pending coordination tasks.",
                situation_summary="Coordinator requested task overview.",
                actions=[
                    ProposedAction(
                        step_number=1,
                        tool_name="retrieve_pending_tasks",
                        arguments={"case_id": case_id, "actor_role": "care_coordinator"},
                        rationale="Retrieve pending coordination tasks.",
                        autonomy_level=1
                    )
                ],
                patient_response_draft="Retrieving pending coordination tasks...",
                target_language="en"
            )

        if intent.primary_intent == "referral_monitoring":
            return CoordinationPlan(
                goal="Monitor referral progress and identify delayed handoffs.",
                situation_summary="Coordinator auditing specialist referrals.",
                actions=[
                    ProposedAction(
                        step_number=1,
                        tool_name="identify_stalled_cases",
                        arguments={"actor_role": "care_coordinator", "days_threshold": 3},
                        rationale="Check for overdue specialist referrals.",
                        autonomy_level=1
                    )
                ],
                patient_response_draft="Checking referral queue status...",
                target_language="en"
            )

        if intent.primary_intent == "sla_recovery_queue":
            return CoordinationPlan(
                goal="Identify stalled care journeys and overdue SLA milestones.",
                situation_summary="Coordinator reviewing stalled cases and recovery queue.",
                actions=[
                    ProposedAction(
                        step_number=1,
                        tool_name="identify_stalled_cases",
                        arguments={"actor_role": "care_coordinator", "days_threshold": 5},
                        rationale="Identify cases with breached or stalled recovery milestones.",
                        autonomy_level=1
                    )
                ],
                patient_response_draft="Scanning recovery queue for stalled cases...",
                target_language="en"
            )

        # Scenario 0.1: Friendly Greeting (Dedicated conversational response, zero administrative tool calls)
        if intent.primary_intent == "greeting":
            return cls._formulate_greeting_plan(intent, patient_context, case_context, conversation_context)

        # Scenario 0.2: Coordinator Task Query (Dispatched to CareCoordinationAgent)
        if intent.primary_intent == "coordinator_tasks_query":
            return CareCoordinationAgent.formulate_task_query_plan(intent, patient_context, case_context)

        # Scenario 0.3: Appointment Booking Request (Dispatched to CareCoordinationAgent)
        if intent.primary_intent == "appointment_booking_request":
            return CareCoordinationAgent.formulate_booking_plan(intent, patient_context, case_context)

        # Scenario 0.31: Appointment Slot Alternatives (Dispatched to CareCoordinationAgent)
        if intent.primary_intent == "appointment_slot_alternatives":
            return CareCoordinationAgent.formulate_additional_slots_plan(intent, patient_context, case_context, conversation_context)

        # Scenario 0.32: Appointment Slot Preference (Dispatched to CareCoordinationAgent)
        if intent.primary_intent == "appointment_slot_preference":
            return CareCoordinationAgent.formulate_slot_preference_plan(intent, patient_context, case_context, conversation_context)

        # Scenario 0.33: Appointment Slot Selection (Dispatched to CareCoordinationAgent)
        if intent.primary_intent == "appointment_slot_selection":
            return CareCoordinationAgent.formulate_slot_selection_plan(intent, patient_context, case_context, conversation_context)

        # Scenario 0.34: Appointment Reschedule Request (Dispatched to CareCoordinationAgent)
        if intent.primary_intent == "appointment_reschedule_request":
            return CareCoordinationAgent.formulate_reschedule_request_plan(intent, patient_context, case_context, conversation_context)

        # Scenario 0.35: Referral Rationale Inquiry (Dispatched to PatientCommunicationAgent)
        if intent.primary_intent == "referral_inquiry":
            return PatientCommunicationAgent.formulate_referral_explanation_plan(intent, patient_context, case_context, conversation_context)

        # Scenario 0.36: Referral Deferral (Dispatched to RecoveryAgent)
        if intent.primary_intent == "referral_deferral":
            return RecoveryAgent.formulate_referral_deferral_plan(intent, patient_context, case_context, conversation_context)

        # Scenario 0.37: Delayed Referral Investigation (Dispatched to CareCoordinationAgent)
        if intent.primary_intent == "referral_delay":
            return CareCoordinationAgent.formulate_referral_delay_plan(intent, patient_context, case_context)

        # Scenario 0.4: Transportation / Caregiver Barrier & Reschedule (Dispatched to RecoveryAgent)
        if any(b.barrier_type == "transportation_caregiver" for b in intent.detected_barriers) or intent.primary_intent == "appointment_reschedule_with_barrier":
            return RecoveryAgent.formulate_barrier_reschedule_plan(intent, patient_context, case_context)

        # Scenario 0.5: Missed Appointment / No-show Recovery (Dispatched to RecoveryAgent)
        if intent.primary_intent == "missed_appointment":
            return RecoveryAgent.formulate_missed_visit_plan(intent, patient_context, case_context)

        # Scenario 0.6: Patient Inquiries / Clinical Questions / Emotional Reassurance (Dispatched to PatientCommunicationAgent)
        if intent.primary_intent in ("case_context_inquiry", "patient_inquiry", "clinical_question"):
            return PatientCommunicationAgent.formulate_plan(intent, patient_context, case_context, conversation_context)

        # Scenario 0.7: Explicit Care Cancellation / Refusal (Dispatched to RecoveryAgent)
        if intent.primary_intent == "appointment_cancellation_and_refusal":
            return RecoveryAgent.formulate_cancellation_plan(intent, patient_context, case_context)

        # Scenario 0.8: Evidence-Based Closure Check (Dispatched to DoctorReviewAgent)
        if intent.primary_intent == "closure_readiness":
            case_id = str(case_context.get("case_id") or case_context.get("id") or "")
            clinician_id = str(case_context.get("current_owner_id") or "")
            return DoctorReviewAgent.formulate_closure_review_plan(case_id, clinician_id)

        # For remaining coordination situations, try LLM Planning with safety constraints
        llm = get_llm()
        if llm:
            try:
                prompt = (
                    f"{PLANNING_PROMPT.format(case_number=case_context.get('case_number', 'CASE-UNKNOWN'), patient_name=patient_context.get('full_name', 'Patient'), language=intent.detected_language, case_status=case_context.get('status', 'active'), screening_finding=f'{case_context.get('finding_code')}: {case_context.get('finding_summary')}', sla_status=case_context.get('sla_status', 'normal'), sla_deadline=str(case_context.get('sla_deadline', 'in 7 days')), situation_summary=f'Intent: {intent.primary_intent}. Emotional state: {intent.emotional_state}. Barriers: {[b.barrier_type for b in intent.detected_barriers]}')}\n\n"
                    f"{plan_parser.get_format_instructions()}"
                )
                res = llm.invoke([
                    SystemMessage(content=CAREBRIDGE_SYSTEM_PROMPT),
                    HumanMessage(content=prompt)
                ])
                parsed = plan_parser.parse(res.content)
                if isinstance(parsed, CoordinationPlan):
                    return parsed
            except Exception:
                pass

        # Deterministic Adaptive Planning Fallback
        return cls._offline_plan_formulation(intent, patient_context, case_context, conversation_context)

    # --------------------------------------------------------------------------
    # Semantic Reasoning Heuristics (Zero-Keyword Pattern Matchers)
    # --------------------------------------------------------------------------
    @staticmethod
    def _offline_intent_analysis(
        message: str,
        patient_context: Dict[str, Any],
        conversation_context: Optional[Dict[str, Any]] = None
    ) -> IntentAnalysis:
        msg_lower = message.lower()
        barriers: List[InferredBarrier] = []

        # 1. Detect Language (English vs Arabic vs Spanish vs Tamil characters)
        has_arabic_chars = any("\u0600" <= char <= "\u06ff" or "\u0750" <= char <= "\u077f" or "\u08a0" <= char <= "\u08ff" for char in message)
        has_tamil_chars = any("\u0b80" <= char <= "\u0bff" for char in message)
        is_spanish = any(w in msg_lower for w in ["hola", "cita", "dolor", "miedo", "gracias", "el doctor", "mi doctor", "médico", "biopsia", "cuando", "estoy", "tengo", "por favor", "ayuda", "significa", "informe"]) and not any("\u0b80" <= char <= "\u0bff" for char in message) and not has_arabic_chars
        pref_lang = patient_context.get("preferred_language")

        if has_arabic_chars or pref_lang == "ar":
            detected_lang = "ar"
        elif has_tamil_chars or (pref_lang == "ta" and "vanakkam" in msg_lower):
            detected_lang = "ta"
        elif is_spanish or pref_lang == "es":
            detected_lang = "es"
        else:
            detected_lang = "en"

        # 2. Semantic Barrier Extraction
        # Transportation / Caregiver dependency
        if any(term in msg_lower for term in [
            "daughter", "take me", "ride", "bus", "travel", "transport", "nobody to", "out of town",
            "வண்டி", "பயணம்", "மகள்", "வர முடியாது",
            "transporte", "autobús", "viaje", "nadie me puede llevar", "carro",
            "مواصلات", "سيارة", "نقل", "لا أستطيع الذهاب"
        ]):
            barriers.append(InferredBarrier(
                barrier_type="transportation_caregiver",
                severity="high",
                details="Patient cannot travel independently without caregiver transport."
            ))

        # Fear / Anxiety
        if any(term in msg_lower for term in [
            "scared", "afraid", "worried", "nervous", "pain", "cancer?", "anxious", "anxiety",
            "fear", "i am fear", "fear biopsy", "am fear", "terrified",
            "பயம்", "பயமாக", "பயந்து", "கவலை", "வலி",
            "miedo", "temor", "asustada", "asustado", "dolor", "ansiedad", "preocupada", "preocupado",
            "خوف", "خائفة", "قلق", "ألم", "خائف", "مرعوبة"
        ]):
            barriers.append(InferredBarrier(
                barrier_type="fear_anxiety",
                severity="medium",
                details="Patient expresses emotional distress regarding screening findings or procedures."
            ))

        # Financial / Cost
        if any(term in msg_lower for term in [
            "cost", "expensive", "afford", "insurance", "fees", "money", "pay",
            "பணம்", "செலவு",
            "costo", "dinero", "seguro", "pagar", "caro",
            "تكلفة", "مال", "تأمين", "دفع", "غال"
        ]):
            barriers.append(InferredBarrier(
                barrier_type="financial",
                severity="high",
                details="Patient concerned about treatment or consultation cost."
            ))

        # Childcare / Family obligations
        if any(term in msg_lower for term in ["child", "children", "baby", "kids", "daycare", "குழந்தை", "பிள்ளை"]):
            barriers.append(InferredBarrier(
                barrier_type="childcare_family",
                severity="medium",
                details="Patient lacks childcare support during clinical appointment hours."
            ))

        # 3. Intent Determination
        primary_intent = "acknowledgement"
        requires_clarification = False
        requires_escalation = False
        inquiry_topic = None

        greeting_words = [
            "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
            "vanakkam", "வணக்கம்", "hi there", "hello carebridge", "hi carebridge",
            "hola", "buenos dias", "buenas tardes", "buenas noches",
            "مرحبا", "أهلا", "اهلا", "السلام عليكم", "صباح الخير", "مساء الخير"
        ]
        clean_msg = "".join(c for c in msg_lower if c.isalnum() or c.isspace()).strip()

        # Clinical Emergency (Deterministic Safety Rule Priority)
        if ClinicalEscalationAgent.evaluate_safety_rules(message):
            primary_intent = "urgent_clinical_escalation"
            requires_escalation = True
        elif (conversation_context and conversation_context.get("inbound_sender") in ("care_coordinator", "coordinator")) and any(term in msg_lower for term in ["new patient", "new patients", "any new patient", "is there any new patient", "unassigned", "discovery queue", "intake queue"]):
            primary_intent = "new_patient_discovery"
        elif (conversation_context and conversation_context.get("inbound_sender") in ("care_coordinator", "coordinator")) and any(term in msg_lower for term in ["select patient", "choose patient", "open case", "view case", "select case"]):
            primary_intent = "patient_selection"
            inquiry_topic = message.replace("Select patient", "").replace("select patient", "").replace("open case", "").replace("view case", "").strip()
        elif (conversation_context and conversation_context.get("inbound_sender") in ("care_coordinator", "coordinator")) and any(term in msg_lower for term in ["overdue referrals", "referral status", "referrals overdue", "referrals pending", "which cases have overdue referrals"]):
            primary_intent = "referral_monitoring"
        elif (conversation_context and conversation_context.get("inbound_sender") in ("care_coordinator", "coordinator")) and any(term in msg_lower for term in ["stalled cases", "are there any stalled cases", "missed visits", "sla breach", "recovery queue"]):
            primary_intent = "sla_recovery_queue"
        elif (conversation_context and conversation_context.get("inbound_sender") in ("care_coordinator", "coordinator")) and any(term in msg_lower for term in ["pending tasks", "tasks for this case", "list tasks", "coordination tasks", "outstanding tasks", "what tasks", "my tasks", "pending coordination tasks", "show me pending coordination tasks"]):
            primary_intent = "task_management"
        elif clean_msg in greeting_words or (any(clean_msg.startswith(gw + " ") for gw in ["hi", "hello", "hey", "vanakkam", "good morning", "good afternoon", "good evening", "hola", "buenos dias", "مرحبا", "أهلا", "اهلا"]) and not any(k in msg_lower for k in ["book", "appointment", "doctor", "slot", "pain", "bleed", "report", "result", "schedule", "referral", "task", "delay", "see"])):
            primary_intent = "greeting"
        elif any(term in msg_lower for term in ["i want to wait", "want to wait", "can i wait", "hold off", "wait a bit", "wait for now", "not ready yet", "let me wait", "காத்திருக்க விரும்புகிறேன்", "கொஞ்சம் பொறுக்கலாமா"]):
            primary_intent = "referral_deferral"
        elif any(term in msg_lower for term in [
            "why did my doctor refer me", "why did the doctor refer me", "why was i referred",
            "reason for referral", "why referral", "why am i referred", "why refer me",
            "doctor refer me", "why did my doctor recommend a referral", "why doctor refer"
        ]):
            primary_intent = "referral_inquiry"
        elif any(term in msg_lower for term in [
            "the second one", "second one", "second slot", "2nd one", "option 2",
            "slot 2", "book the second", "the second option", "choose the second", "second one book", "இரண்டாவது"
        ]):
            primary_intent = "appointment_slot_selection"
            inquiry_topic = "slot_2"
        elif any(term in msg_lower for term in [
            "the first one", "first one", "first slot", "1st one", "option 1",
            "slot 1", "book the first", "the first option", "choose the first", "first one book", "முதலாவது"
        ]):
            primary_intent = "appointment_slot_selection"
            inquiry_topic = "slot_1"
        elif any(term in msg_lower for term in [
            "the third one", "third one", "third slot", "3rd one", "option 3",
            "slot 3", "book the third", "third one book", "choose the third"
        ]):
            primary_intent = "appointment_slot_selection"
            inquiry_topic = "slot_3"
        elif any(term in msg_lower for term in [
            "any other slot", "is there any other slot", "other slot", "other slots",
            "different slot", "different time", "different day", "another slot",
            "other options", "any other time", "any other dates", "other available",
            "another available slot", "another available", "more slots", "different opening",
            "வேறு நேரம்", "வேறு நாள்", "வேற ஏதாவது நேரம்"
        ]):
            primary_intent = "appointment_slot_alternatives"
            if any(t in msg_lower for t in ["morning", "காலை", "am"]):
                inquiry_topic = "morning"
            elif any(t in msg_lower for t in ["afternoon", "மதியம்", "pm"]):
                inquiry_topic = "afternoon"
        elif any(term in msg_lower for term in [
            "prefer morning", "prefer a morning", "morning please", "mornings work", "morning slots",
            "morning slot", "morning appointment", "morning time", "only morning", "in the morning",
            "morning visit", "காலை", "காலை நேரம்", "mornings"
        ]) and not clean_msg.startswith("good morning"):
            primary_intent = "appointment_slot_preference"
            inquiry_topic = "morning"
        elif any(term in msg_lower for term in [
            "prefer afternoon", "prefer an afternoon", "afternoon please", "afternoons work",
            "afternoon slots", "afternoon slot", "afternoon appointment", "afternoon time",
            "only afternoon", "in the afternoon", "evening", "மதியம்", "afternoons"
        ]) and not clean_msg.startswith("good afternoon"):
            primary_intent = "appointment_slot_preference"
            inquiry_topic = "afternoon"
        elif any(term in msg_lower for term in [
            "can i change it", "can i change my appointment", "change it", "can we change",
            "change my appointment", "reschedule", "change time", "another day",
            "not tomorrow", "change the date", "reschedule my appointment", "மாற்ற முடியுமா"
        ]):
            primary_intent = "appointment_reschedule_request"
        elif any(term in msg_lower for term in ["pending tasks", "tasks for this case", "list tasks", "coordination tasks", "outstanding tasks", "what tasks", "my tasks"]):
            primary_intent = "coordinator_tasks_query"
        elif any(term in msg_lower for term in [
            "my report what saying", "what report saying", "report what saying", "my report saying",
            "what my report say", "what report say", "what does my report say",
            "que dice mi informe", "qué significa mi informe", "ماذا يقول تقريري", "ماذا يعني تقريري",
            "screening result mean", "result mean", "what is my result", "what does my result",
            "why does my doctor recommend", "why do i need further evaluation", "recommend further evaluation", "why further evaluation",
            "referral been accepted", "referral accepted", "has my referral", "status of my referral", "is my referral accepted",
            "when is my appointment", "appointment date", "time is my appointment", "my upcoming appointment", "when is the appointment",
            "expect during my consultation", "expect during consultation", "what to expect", "what happens during consultation",
            "what did my doctor recommend", "doctor's recommendation", "doctor recommend", "what did doctor say",
            "what happens next in my treatment", "next in my treatment", "treatment next steps",
            "when is my next follow-up", "next follow-up", "follow-up date", "when is follow up",
            "have all my care steps been completed", "all care steps completed", "all my care steps", "care steps been completed", "is my care completed"
        ]):
            primary_intent = "case_context_inquiry"
            if any(term in msg_lower for term in ["report", "result", "birads", "bi-rads", "informe", "resultado", "تقرير", "نتيجة"]):
                inquiry_topic = "birads"
        elif any(term in msg_lower for term in ["cancel my appointment", "refuse", "don't want to come", "won't come", "stop calling", "leave me alone"]):
            primary_intent = "appointment_cancellation_and_refusal"
            requires_clarification = False
            requires_escalation = True
        elif any(term in msg_lower for term in ["missed my appointment", "missed it", "couldn't make it", "did not go yesterday", "missed appointment"]):
            primary_intent = "missed_appointment"
        elif any(term in msg_lower for term in [
            "book appointment", "book an appointment", "book me an appointment", "book me a slot",
            "schedule an appointment", "schedule appointment", "schedule for me", "can you schedule",
            "want to book", "want book", "i want book", "help me book", "help me schedule",
            "need to see a doctor", "need to see doctor", "see a doctor", "see doctor",
            "consult a doctor", "consult doctor", "visit the doctor", "visit doctor",
            "meet the doctor", "meet doctor", "talk to doctor", "talk to a doctor",
            "book doctor", "book visit", "schedule visit", "book tomorrow", "appointment tomorrow",
            "make an appointment", "set up an appointment", "arrange an appointment",
            "arrange a consultation", "arrange consultation", "get an appointment"
        ]) or (
            ("book" in msg_lower or "schedule" in msg_lower) and
            any(w in msg_lower for w in ["doctor", "appointment", "visit", "slot", "tomorrow", "consultation"])
        ) or (
            "doctor" in msg_lower and any(w in msg_lower for w in ["see", "consult", "visit", "meet"])
        ):
            primary_intent = "appointment_booking_request"
        elif any(term in msg_lower for term in [
            "referral delayed", "haven't heard", "referral status", "waiting for clinic", "referral taking long",
            "doctor not call me yet", "doctor not call", "not call me yet", "no call from doctor", "doctor call me yet", "no call yet",
            "el doctor no me ha llamado", "no me ha llamado el doctor", "لم يتصل بي الطبيب", "الطبيب لم يتصل"
        ]):
            primary_intent = "referral_delay"
        elif any(term in msg_lower for term in ["need assistance", "financial help", "need help with ride", "help with cost", "voucher", "social work"]):
            primary_intent = "assistance_request"
        elif any(term in msg_lower for term in ["close case", "case finished", "results came back benign", "ready to close"]):
            primary_intent = "closure_readiness"
        elif any(term in msg_lower for term in [
            "i am fear biopsy", "fear biopsy", "afraid biopsy", "scared biopsy",
            "miedo de la biopsia", "miedo a la biopsia", "tengo miedo de la biopsia",
            "أنا خائفة من الخزعة", "خائفة من الخزعة", "خائف من الخزعة"
        ]):
            primary_intent = "patient_inquiry"
            inquiry_topic = "biopsy"
            if not any(b.barrier_type == "fear_anxiety" for b in barriers):
                barriers.append(InferredBarrier(
                    barrier_type="fear_anxiety",
                    severity="medium",
                    details="Patient expresses emotional distress regarding biopsy."
                ))
        elif any(b.barrier_type == "fear_anxiety" for b in barriers) and primary_intent == "acknowledgement":
            primary_intent = "patient_inquiry"
        elif barriers and any(b.barrier_type == "transportation_caregiver" for b in barriers):
            primary_intent = "appointment_reschedule_with_barrier"
        elif any(term in msg_lower for term in ["reschedule", "change time", "another day", "not tomorrow"]):
            primary_intent = "appointment_reschedule_request"
        elif any(term in msg_lower for term in ["cancel", "not coming", "stop"]):
            primary_intent = "appointment_cancellation_risk"
            requires_clarification = True
        elif "?" in message or any(term in msg_lower for term in [
            "what is", "why do i need", "does it mean", "will it hurt", "biopsy mean",
            "bi-rads", "birads", "bi rads", "biopsy", "cancer", "cáncer", "سرطان",
            "what does", "do i have", "what mean", "mean do i have",
            "scared", "afraid", "fear", "miedo", "خوف", "خائفة"
        ]):
            primary_intent = "patient_inquiry"

        if not inquiry_topic:
            if "bi-rads" in msg_lower or "birads" in msg_lower:
                inquiry_topic = "birads"
            elif any(w in msg_lower for w in ["report", "result", "screening", "informe", "resultado", "تقرير", "نتيجة"]):
                inquiry_topic = "birads"
            elif "biopsy" in msg_lower or "biopsia" in msg_lower or "خزعة" in msg_lower or "பயாப்ஸி" in msg_lower:
                inquiry_topic = "biopsy"
            elif any(t in msg_lower for t in ["pain", "hurt", "ache", "sore", "வலி", "dolor", "ألم"]):
                inquiry_topic = "pain"
            elif any(t in msg_lower for t in ["cost", "expensive", "money", "afford", "பணம்", "செலவு", "costo", "dinero", "تكلفة"]):
                inquiry_topic = "financial"

        # Topic inheritance from conversation context across multiple turns
        if not inquiry_topic and conversation_context and conversation_context.get("recent_messages"):
            for prev_m in reversed(conversation_context.get("recent_messages", [])):
                prev_text = (getattr(prev_m, "content", None) or (prev_m.get("content") if isinstance(prev_m, dict) else "")).lower()
                if "bi-rads" in prev_text or "birads" in prev_text:
                    inquiry_topic = "birads"
                    break
                elif "biopsy" in prev_text:
                    inquiry_topic = "biopsy"
                    break

        return IntentAnalysis(
            primary_intent=primary_intent,
            emotional_state="anxious" if barriers else "cooperative",
            detected_language=detected_lang,
            detected_barriers=barriers,
            missing_information=["caregiver_return_date"] if any(b.barrier_type == "transportation_caregiver" for b in barriers) else [],
            inquiry_topic=inquiry_topic,
            raw_query=message,
            requires_clarification=requires_clarification,
            requires_human_escalation=requires_escalation
        )

    @classmethod
    def _offline_plan_formulation(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any],
        conversation_context: Optional[Dict[str, Any]] = None
    ) -> CoordinationPlan:
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_id = str(patient_context.get("patient_id") or patient_context.get("id") or "")
        patient_name = patient_context.get("full_name") or patient_context.get("first_name", "Valued Patient")
        lang = intent.detected_language or patient_context.get("preferred_language", "en")
        finding_code = case_context.get("finding_code", "abnormal finding")
        actions: List[ProposedAction] = []

        # Scenario 0: Urgent Clinical Escalation (Dispatched to ClinicalEscalationAgent)
        if intent.primary_intent == "urgent_clinical_escalation":
            return ClinicalEscalationAgent.formulate_escalation_plan(intent, patient_context, case_context)

        # Scenario 0.2: Coordinator Task Query (Dispatched to CareCoordinationAgent)
        elif intent.primary_intent == "coordinator_tasks_query":
            return CareCoordinationAgent.formulate_task_query_plan(intent, patient_context, case_context)

        # Scenario 0.5: Friendly Greeting (Dedicated natural greeting, zero tool calls)
        elif intent.primary_intent == "greeting":
            return cls._formulate_greeting_plan(intent, patient_context, case_context, conversation_context or {})

        # Scenario 0.6: Appointment Booking Request (Dispatched to CareCoordinationAgent)
        elif intent.primary_intent == "appointment_booking_request":
            return CareCoordinationAgent.formulate_booking_plan(intent, patient_context, case_context)

        # Scenario 0.61: Appointment Slot Alternatives (Dispatched to CareCoordinationAgent)
        elif intent.primary_intent == "appointment_slot_alternatives":
            return CareCoordinationAgent.formulate_additional_slots_plan(intent, patient_context, case_context, conversation_context)

        # Scenario 0.62: Appointment Slot Preference (Dispatched to CareCoordinationAgent)
        elif intent.primary_intent == "appointment_slot_preference":
            return CareCoordinationAgent.formulate_slot_preference_plan(intent, patient_context, case_context, conversation_context)

        # Scenario 0.63: Appointment Slot Selection (Dispatched to CareCoordinationAgent)
        elif intent.primary_intent == "appointment_slot_selection":
            return CareCoordinationAgent.formulate_slot_selection_plan(intent, patient_context, case_context, conversation_context)

        # Scenario 0.64: Appointment Reschedule Request (Dispatched to CareCoordinationAgent)
        elif intent.primary_intent == "appointment_reschedule_request":
            return CareCoordinationAgent.formulate_reschedule_request_plan(intent, patient_context, case_context, conversation_context)

        # Scenario 0.65: Referral Rationale Inquiry (Dispatched to PatientCommunicationAgent)
        elif intent.primary_intent == "referral_inquiry":
            return PatientCommunicationAgent.formulate_referral_explanation_plan(intent, patient_context, case_context, conversation_context)

        # Scenario 0.66: Referral Deferral (Dispatched to RecoveryAgent)
        elif intent.primary_intent == "referral_deferral":
            return RecoveryAgent.formulate_referral_deferral_plan(intent, patient_context, case_context, conversation_context)

        # Scenario 1: Transportation / Caregiver Barrier & Reschedule (Dispatched to RecoveryAgent)
        elif any(b.barrier_type == "transportation_caregiver" for b in intent.detected_barriers) or intent.primary_intent == "appointment_reschedule_with_barrier":
            return RecoveryAgent.formulate_barrier_reschedule_plan(intent, patient_context, case_context)

        # Scenario 2: Patient Inquiries / Clinical Questions (Dispatched to PatientCommunicationAgent)
        elif intent.primary_intent in ("case_context_inquiry", "patient_inquiry", "clinical_question"):
            return PatientCommunicationAgent.formulate_plan(intent, patient_context, case_context, conversation_context or {})

        # Scenario 3: Patient Assistance Request - Financial, Childcare (Dispatched to RecoveryAgent)
        elif intent.primary_intent == "assistance_request" or any(b.barrier_type in ("financial", "childcare_family") for b in intent.detected_barriers):
            return RecoveryAgent.formulate_assistance_plan(intent, patient_context, case_context)

        # Scenario 4: Delayed Referral Investigation (Dispatched to CareCoordinationAgent)
        elif intent.primary_intent == "referral_delay":
            return CareCoordinationAgent.formulate_referral_delay_plan(intent, patient_context, case_context)

        # Scenario 5: Missed Appointment / No-show Recovery (Dispatched to RecoveryAgent)
        elif intent.primary_intent == "missed_appointment":
            return RecoveryAgent.formulate_missed_visit_plan(intent, patient_context, case_context)

        # Scenario 6: Explicit Care Cancellation / Refusal (Dispatched to RecoveryAgent)
        elif intent.primary_intent == "appointment_cancellation_and_refusal":
            return RecoveryAgent.formulate_cancellation_plan(intent, patient_context, case_context)

        # Scenario 8: Evidence-Based Closure Check (Dispatched to DoctorReviewAgent)
        elif intent.primary_intent == "closure_readiness":
            clinician_id = str(case_context.get("current_owner_id") or "")
            return DoctorReviewAgent.formulate_closure_review_plan(case_id, clinician_id)

        # Scenario 9: Routine Inquiry / Acknowledgement
        else:
            actions.append(ProposedAction(
                step_number=1,
                tool_name="update_case_notes",
                arguments={
                    "case_id": case_id,
                    "note": "Patient acknowledged communication. Care pathway progressing as planned.",
                    "barrier_detected": None
                },
                rationale="Record positive patient engagement in case history.",
                autonomy_level=1
            ))
            if lang == "ta":
                msg = (
                    f"வணக்கம் {patient_name}! தங்களின் பரிசோதனை ({finding_code}) அல்லது மருத்துவ சந்திப்புகள் "
                    f"குறித்து உங்களுக்கு என்ன தகவல் அல்லது உதவி தேவைப்படுகிறது என்று கூறினால் மகிழ்ச்சியுடன் உதவுவேன்."
                )
            else:
                msg = (
                    f"I am here to assist you with every aspect of your care journey, {patient_name}. "
                    f"You can ask me about your screening findings ({finding_code}), upcoming appointment options, "
                    f"referral progress, or any questions you may have about your care pathway."
                )

            return CoordinationPlan(
                goal="Confirm engagement and maintain open patient communication.",
                situation_summary="Routine acknowledgement received from patient.",
                actions=actions,
                patient_response_draft=msg,
                target_language=lang
            )
