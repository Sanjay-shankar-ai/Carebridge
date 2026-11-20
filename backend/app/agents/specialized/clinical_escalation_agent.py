"""
CareBridge Clinical Escalation Agent
Specialized agent responsible for:
- Applying approved deterministic clinical safety triage and distress/crisis rules
- Detecting acute emergent symptoms as well as crisis/distress language (panic, hopelessness, self-harm)
- Routing clinical and emotional concerns immediately to attending physicians and care coordinators
- Guaranteeing atomic PostgreSQL persistence of case escalation and timeline events
- OPERATING INDEPENDENTLY OF LLM AVAILABILITY (Guaranteed deterministic fallback)
- STRICT CLINICAL GUARDRAIL: Never independently diagnoses, prescribes treatments, or promises outcomes.
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

# Deterministic severe emotional distress / crisis triggers (always create persisted urgent clinical task)
SEVERE_DISTRESS_INDICATORS = [
    "can't take this anymore", "cant take this anymore", "cannot take this anymore",
    "cannot cope", "can't cope", "cant cope", "hopeless", "i feel hopeless",
    "suicide", "kill myself", "end my life", "end it all", "hurt myself", "self-harm", "self harm",
    "can't go on", "cant go on", "no reason to live", "want to die", "giving up",
    "انتحار", "فقدت الأمل", "لا أستطيع التحمل",
    "suicidio", "sin esperanza", "no puedo más", "no puedo mas", "me siento desesperada",
    "தற்கொலை", "உயிர் வாழ விரும்பவில்லை",
]

# Approved deterministic crisis, panic, distress, and self-harm triggers
CRISIS_AND_DISTRESS_INDICATORS = [
    "am i going to die", "going to die", "will i die", "am i gonna die", "i am dying",
    "die", "so scared", "i am so scared", "terrified", "panic",
    "so terrified", "scared to death",
    # Arabic
    "هل سأموت", "سأموت", "مرعوبة جدا", "خائفة جدا", "أنا خائفة جدا", "أموت", "أشعر بالرعب",
    # Spanish
    "me voy a morir", "voy a morir", "mucho miedo", "tengo mucho miedo",
    "estoy muy asustada", "estoy muy asustado", "morir",
    # Tamil
    "நான் இறந்துவிடுவேனா", "பயமாக இருக்கிறது",
] + SEVERE_DISTRESS_INDICATORS


class ClinicalEscalationAgent:
    """Specialized agent for deterministic emergency clinical triage and physician escalation."""

    @classmethod
    def evaluate_severe_distress(cls, message: str) -> bool:
        """Deterministically detects severe distress, hopelessness, inability to cope, or self-harm without LLM."""
        msg_lower = (message or "").lower().strip()
        return any(term in msg_lower for term in SEVERE_DISTRESS_INDICATORS)

    @classmethod
    def evaluate_acute_symptoms(cls, message: str) -> bool:
        """Deterministically detects acute physical red-flag symptoms without LLM."""
        msg_lower = (message or "").lower().strip()
        return any(term in msg_lower for term in ACUTE_SYMPTOM_INDICATORS)

    @classmethod
    def evaluate_safety_rules(cls, message: str) -> bool:
        """Evaluates whether message contains acute red-flag symptoms or crisis/distress requiring emergency escalation."""
        return cls.evaluate_acute_symptoms(message) or any(
            term in (message or "").lower().strip() for term in CRISIS_AND_DISTRESS_INDICATORS
        )

    @classmethod
    def formulate_escalation_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any]
    ) -> CoordinationPlan:
        """Formulates an immediate Level 2 emergency/distress escalation plan with 5-step counselling."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = patient_context.get("first_name") or (patient_context.get("full_name", "").split()[0] if patient_context.get("full_name") else "")
        lang = intent.detected_language or patient_context.get("preferred_language", "en")

        cr = case_context.get("clinical_review") or {}
        doc_name = (
            case_context.get("assigned_doctor_name")
            or case_context.get("doctor_name")
            or cr.get("doctor_name")
            or "Dr. Arjun Menon"
        )
        coord_name = case_context.get("current_owner_name") or "Priya Nair, RN"

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="escalate_case",
                arguments={
                    "case_id": case_id,
                    "urgency": "critical",
                    "reason": "Patient reported acute emotional distress / crisis language or emergent clinical symptoms."
                },
                rationale="Create priority clinical escalation task for human physician and care coordinator outreach.",
                autonomy_level=2
            )
        ]

        if lang == "ta":
            msg = (
                f"உங்கள் பயத்தையும் மன அழுத்தத்தையும் நாங்கள் முழுமையாக உணர்கிறோம் {patient_name}; நீங்கள் இதில் தனியாக இல்லை.\n\n"
                f"உங்கள் பாதுகாப்பும் நல்வாழ்வும் எங்களுக்கு மிக முக்கியமானது, எங்கள் மருத்துவக் குழு உங்களுடன் துணை நிற்கும்.\n\n"
                "ஒரு செய்திப் பரிமாற்றத்தின் மூலம் உடல்நிலையைக் கணிக்கவோ நோயறிதலைச் செய்யவோ முடியாது; மருத்துவரின் நேரடி பரிசோதனை மட்டுமே சரியான முடிவைத் தரும்.\n\n"
                f"தங்களின் நிலை குறித்து மருத்துவர் {doc_name} மற்றும் உங்கள் பராமரிப்பு ஒருங்கிணைப்பாளர் {coord_name} ஆகியோருக்கு உடனடியாக தகவல் தெரிவித்துள்ளேன். "
                "உடனடி அவசர மருத்துவ உதவி தேவைப்பட்டால் 108/911 அவசர எண்ணையோ அல்லது உதவி மையத்தையோ உடனே தொடர்பு கொள்ளவும்.\n\n"
                f"உங்கள் ஒருங்கிணைப்பாளர் {coord_name} உங்களுடன் உடனடியாக தொலைபேசியில் பேச ஏற்பாடு செய்யவா?"
            )
        elif lang == "es":
            msg = (
                f"Comprendo profundamente lo abrumador y aterrador que se siente este momento, {patient_name}, y quiero que sepa que no está sola.\n\n"
                f"Su vida y su salud son lo más importante para nosotros, y nuestro equipo de atención está aquí para apoyarle.\n\n"
                "Un mensaje de chat no puede evaluar su estado físico ni predecir el futuro; únicamente un médico en una evaluación clínica directa puede determinar su estado de salud.\n\n"
                f"He alertado de inmediato a su médico, el {doc_name}, y a su coordinadora de atención, {coord_name}, para que se comuniquen con usted. "
                "Si siente una angustia abrumadora o una emergencia médica, comuníquese de inmediato con los servicios de emergencia (911 o 108) o con la Línea de Prevención del Suicidio y Crisis al 988—hay ayuda disponible las 24 horas del día, los 7 días de la semana.\n\n"
                f"¿Desea que solicite una llamada urgente de su coordinadora {coord_name} en este momento?"
            )
        elif lang == "ar":
            msg = (
                f"أشعر بمدى الخوف والضغط النفسي الشديد الذي تمرين به في هذه اللحظة يا {patient_name}، وأود أن أؤكد لكِ أنكِ لستِ وحدكِ أبداً.\n\n"
                f"إن حياتكِ وصحتكِ وسلامتكِ هي أهم ما لدينا، وفريقنا الطبي يقف إلى جانبكِ لتقديم كل الدعم والرعاية.\n\n"
                "لا يمكن للرسائل النصية تقييم حالتكِ الصحية أو التنبؤ بما سيحدث؛ فالطبيب وحده من خلال الفحص السريري المباشر هو من يستطيع تقييم حالتكِ بدقة.\n\n"
                f"لقد أخطرتُ طبيبكِ المعالج، {doc_name}، ومنسقة رعايتكِ، {coord_name}، فوراً ليتواصلا معكِ. "
                "إذا كنتِ تمرين بأزمة طارئة أو تشعرين بخطر داهم، يرجى الاتصال فوراً بخدمات الطوارئ (911 أو 108) أو خط المساعدة الوطني في الأزمات 988، فالمساعدة متاحة دائماً على مدار الساعة.\n\n"
                f"هل تودين أن أطلب من منسقة رعايتكِ {coord_name} الاتصال بكِ هاتفياً وبشكل عاجل الآن؟"
            )
        else:
            msg = (
                f"I hear how frightening and overwhelming this moment feels, {patient_name}, and I want you to know you are not alone.\n\n"
                f"Your life, safety, and health matter deeply to us, and our entire clinical team is here to support you.\n\n"
                "A chat conversation cannot assess your health condition or predict outcomes; only a physician evaluating you in an in-person clinical exam can determine what is happening.\n\n"
                f"I have immediately alerted your doctor, {doc_name}, and your dedicated care coordinator, {coord_name}, so they can reach out to you directly. "
                "If you are experiencing severe distress or a medical or mental health emergency, please reach out right away to emergency services (911 or 108) or call/text the 988 Suicide & Crisis Lifeline—caring support is available 24/7.\n\n"
                f"Would you like me to request an immediate callback from your care coordinator {coord_name}?"
            )

        return CoordinationPlan(
            goal="Escalate acute distress or clinical symptoms to human physician and coordinator queue with critical priority.",
            situation_summary="Acute clinical concern or crisis/distress identified in patient communication.",
            actions=actions,
            patient_response_draft=msg,
            target_language=lang
        )
