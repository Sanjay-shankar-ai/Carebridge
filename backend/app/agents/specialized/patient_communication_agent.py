"""
CareBridge Patient Communication Agent
Specialized agent responsible for:
- Drafting empathetic, counselling-style patient messages in English, Arabic, Spanish, and Tamil
- Explaining screening results and clinical findings (e.g. BI-RADS 4, Mammogram) in plain language (grade 6-8)
- Explaining diagnostic procedure steps (e.g. biopsy, ultrasound) without false reassurance
- Strictly adhering to the 5-STEP COUNSELLING STRUCTURE:
    1. Acknowledge the feeling in one sentence.
    2. Answer the actual question in plain words.
    3. Be honest about what cannot be known from the conversation.
    4. Say what happens next and who will explain (the attending doctor, e.g. Dr. Arjun Menon).
    5. Offer ONE gentle next step.
- STRICT CLINICAL GUARDRAIL:
    - Never states or implies "you have cancer" or "you do not have cancer".
    - Never promises clinical outcomes (no "70% to 80% benign", no "peace of mind", no "don't worry").
    - Short paragraphs, warm tone, no lists longer than 3 items.
    - Uses finalized report ONLY as documented findings; if none exists, answers generally.
"""

from typing import Dict, Any, List, Optional
from app.agents.state import CoordinationPlan, ProposedAction, IntentAnalysis


class PatientCommunicationAgent:
    """Specialized agent for empathetic patient counselling, education, and reassurance without diagnosing."""

    @classmethod
    def _resolve_doctor_name(cls, case_context: Dict[str, Any]) -> str:
        cr = case_context.get("clinical_review") or {}
        co = case_context.get("consultation_outcome") or {}
        return (
            case_context.get("assigned_doctor_name")
            or case_context.get("doctor_name")
            or cr.get("doctor_name")
            or co.get("doctor_name")
            or "Dr. Arjun Menon"
        )

    @classmethod
    def _resolve_coordinator_name(cls, case_context: Dict[str, Any]) -> str:
        return case_context.get("current_owner_name") or "Priya Nair, RN"

    @classmethod
    def _resolve_patient_first_name(cls, patient_context: Dict[str, Any]) -> str:
        first = patient_context.get("first_name")
        if first and first.strip() and first != "Valued Patient":
            return first.strip()
        full = patient_context.get("full_name")
        if full and full.strip() and full != "Valued Patient":
            parts = full.strip().split()
            if parts:
                return parts[0]
        name = patient_context.get("name")
        if name and name.strip() and name != "Valued Patient":
            return name.strip().split()[0]
        return ""

    @classmethod
    def explain_finding(
        cls,
        finding_code: str,
        screening_type: str,
        patient_name: str,
        lang: str = "en",
        inquiry_topic: Optional[str] = None,
        case_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generates 5-step counselling explanation of screening findings in plain language.
        Never states/implies cancer diagnosis or non-diagnosis. Never promises outcomes.
        """
        ctx = case_context or {}
        doc_name = cls._resolve_doctor_name(ctx)
        coord_name = cls._resolve_coordinator_name(ctx)
        code_upper = (finding_code or "").upper()
        s_type = screening_type or "mammogram"

        if lang == "ta":
            return (
                f"மருத்துவ முடிவுகள் குறித்து அறியும்போது அச்சமும் கவலையும் ஏற்படுவது மிகவும் இயல்பானது {patient_name}.\n\n"
                f"தங்களின் {s_type} பரிசோதனையில் குறிப்பிடப்பட்டுள்ள {finding_code or 'BI-RADS 4'} என்பது, "
                "திசுக்களில் கூடுதல் தெளிவு தேவைப்படும் ஒரு மாறுபாடு கண்டறியப்பட்டுள்ளது என்பதைக் குறிக்கிறது; இதனை தெளிவுபடுத்த பயாப்ஸி பரிந்துரைக்கப்படுகிறது.\n\n"
                "ஒரு செய்திப் பரிமாற்றத்தின் மூலம் இந்த திசு மாறுபாட்டின் தன்மையைக் கணிக்கவோ நோயறிதலை உறுதிப்படுத்தவோ முடியாது; "
                "திசுவை ஆய்வகத்தில் முழுமையாக பரிசோதிப்பதன் மூலமே உண்மை நிலையை அறிய முடியும்.\n\n"
                f"மருத்துவர் {doc_name} தங்களின் முழுப் பரிசோதனைப் படங்களை ஆய்வு செய்து, பயாப்ஸி முறை குறித்தும் அடுத்த கட்ட சிகிச்சைகள் குறித்தும் உங்களிடம் விரிவாக விளக்குவார்.\n\n"
                f"மருத்துவர் {doc_name} உடனான சந்திப்பு நேரங்களை சரிபார்க்க உதவவா?"
            )
        if lang == "es":
            return (
                f"Comprendo lo preocupante y angustiante que resulta leer estos términos y preguntarse qué significan para su salud, {patient_name}.\n\n"
                f"Un hallazgo {finding_code or 'BI-RADS 4'} en su {s_type} significa que el radiólogo observó una zona que tiene características "
                "que requieren una evaluación más detallada mediante una biopsia.\n\n"
                "Una conversación o un estudio por imágenes por sí solos no pueden determinar un diagnóstico; "
                "únicamente un médico examinando una muestra de tejido en el laboratorio puede brindar una respuesta certera.\n\n"
                f"Su médico, el {doc_name}, revisará sus imágenes con usted directamente, le explicará los detalles y responderá a todas sus dudas clínicas.\n\n"
                f"¿Le gustaría que le ayude a consultar los horarios de consulta disponibles con el {doc_name}?"
            )
        if lang == "ar":
            return (
                f"أدرك تماماً مدى القلق والتساؤلات التي قد تشعرين بها عند قراءة هذه النتائج الطبية يا {patient_name}.\n\n"
                f"تشير نتيجة {finding_code or 'BI-RADS 4'} في فحص {s_type} إلى أن طبيب الأشعة لاحظ منطقة نسيجية تتطلب تقييماً إضافياً أكثر دقة من خلال أخذ عينة (خزعة).\n\n"
                "لا يمكن لمحادثة نصية أو فحص إشعاعي بمفرده إعطاء تشخيص طبي قاطع؛ فالطبيب وحده، من خلال فحص عينة النسيج مخبرياً، يمكنه تحديد طبيعة الحالة بدقة.\n\n"
                f"سيقوم طبيبكِ المعالج، {doc_name}، بمراجعة صور الفحص معكِ وشرح الخطوات التشخيصية والإجابة عن جميع استفساراتكِ الطبية.\n\n"
                f"هل ترغبين في أن أساعدكِ في مراجعة مواعيد الاستشارة المتاحة لدى عيادة {doc_name}؟"
            )

        return (
            f"I hear how stressful and concerning it is to read these terms and wonder what they mean for your health, {patient_name}.\n\n"
            f"A {finding_code or 'BI-RADS 4'} finding on your {s_type} means the radiologist identified an area of tissue with features that require further evaluation, typically through a biopsy.\n\n"
            "A chat conversation or an imaging scan alone cannot diagnose what this tissue represents; only a physician evaluating a tissue sample in a laboratory can provide a clear and definitive medical answer.\n\n"
            f"Your attending doctor, {doc_name}, will review your imaging with you, discuss the findings, and walk you through any recommended next steps.\n\n"
            f"Would you like me to help check available consultation openings with {doc_name}?"
        )

    @classmethod
    def provide_emotional_reassurance(
        cls,
        patient_name: str,
        finding_code: str,
        screening_type: str,
        lang: str = "en",
        case_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Provides compassionate, validating reassurance using the 5-step counselling structure without diagnosing."""
        ctx = case_context or {}
        doc_name = cls._resolve_doctor_name(ctx)
        coord_name = cls._resolve_coordinator_name(ctx)
        s_type = screening_type or "mammogram"

        if lang == "ta":
            return (
                f"உங்கள் கவலையையும் அச்சத்தையும் நாங்கள் முழுமையாக உணர்கிறோம் {patient_name}; இதுபோன்ற நேரத்தில் பயம் ஏற்படுவது இயல்பானது.\n\n"
                f"தங்களின் {s_type} பரிசோதனையில் ({finding_code}) கூடுதல் கவனம் தேவைப்படும் பகுதி கண்டறியப்பட்டுள்ளது, இது கவனமாக ஆராயப்பட வேண்டிய ஒன்று.\n\n"
                "ஒரு செய்தியின் வாயிலாக எவ்வித மருத்துவ முடிவையும் கணிக்க முடியாது; மருத்துவரின் நேரடி பரிசோதனை மூலமே முழுமையான தெளிவு கிடைக்கும்.\n\n"
                f"தங்களின் மருத்துவர் {doc_name} மற்றும் பராமரிப்பு ஒருங்கிணைப்பாளர் {coord_name} உங்களுக்குத் தேவையான முழு மருத்துவ வழிகாட்டுதலை வழங்குவர்.\n\n"
                f"மருத்துவர் {doc_name} உடனான ஆலோசனை நேரத்தை திட்டமிட உதவவா?"
            )
        if lang == "es":
            return (
                f"Comprendo profundamente el temor y la incertidumbre que siente en este momento, {patient_name}.\n\n"
                f"Saber que se necesita una evaluación adicional tras su {s_type} ({finding_code}) genera muchas dudas que merecen atención cuidadosa.\n\n"
                "Un mensaje de texto no puede reemplazar un diagnóstico médico ni anticipar resultados; sólo una evaluación clínica en persona puede ofrecerle claridad.\n\n"
                f"Su médico, el {doc_name}, y su coordinadora de atención, {coord_name}, están a su disposición para acompañarle en cada etapa del proceso.\n\n"
                f"¿Le gustaría revisar las opciones de citas disponibles para conversar con el {doc_name}?"
            )
        if lang == "ar":
            return (
                f"أتفهم تماماً الخوف والمشاعر الصعبة التي تمرين بها في هذا الوقت يا {patient_name}، فمن الطبيعي جداً الشعور بالقلق.\n\n"
                f"إن الحاجة إلى مزيد من التقييم بعد فحص {s_type} ({finding_code}) تعني ببساطة أن هناك ملاحظات تحتاج إلى فحص طبي إضافي متأنٍ.\n\n"
                "لا يمكن لأي محادثة تقييم الحالة الصحية بصورة قاطعة؛ فالتقييم السريري لدى الطبيب المختص هو السبيل الوحيد للحصول على وضوح كامل.\n\n"
                f"سيقوم طبيبكِ المعالج، {doc_name}، بالتعاون مع منسقة رعايتكِ {coord_name}، بمرافقتكِ وتقديم الشرح الطبي الوافي لكِ.\n\n"
                f"هل ترغبين في المساعدة في حجز موعد استشارة مع {doc_name}؟"
            )

        return (
            f"I hear how frightening it is to face this uncertainty right now, {patient_name}.\n\n"
            f"Hearing that you need further evaluation following your {s_type} ({finding_code}) brings up heavy questions that deserve careful attention.\n\n"
            "A chat message cannot diagnose your condition or tell you what the future holds; only a clinical evaluation with a physician can give you clear answers.\n\n"
            f"Your attending doctor, {doc_name}, and your care coordinator, {coord_name}, are right here to guide you through every step of this evaluation.\n\n"
            f"Would you like me to help you review consultation times to speak with {doc_name}?"
        )

    @classmethod
    def explain_procedure(
        cls,
        procedure_type: str,
        patient_name: str,
        lang: str = "en",
        case_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Explains diagnostic procedures in plain, empathetic terms without false reassurance."""
        ctx = case_context or {}
        doc_name = cls._resolve_doctor_name(ctx)
        proc_lower = (procedure_type or "").lower()

        if "biopsy" in proc_lower:
            if lang == "ta":
                return (
                    f"பயாப்ஸி பரிசோதனை குறித்து கேட்கும்போது கவலை ஏற்படுவது இயற்கையே {patient_name}.\n\n"
                    "பயாப்ஸி என்பது மருத்துவர் பகுதி மயக்க மருந்து (local numbing) அளித்து, மிகச் சிறிய திசு மாதிரியை எடுக்கும் ஒரு எளிய புறநோயாளி பரிசோதனை மட்டுமே.\n\n"
                    "செயல்முறை எவ்வாறு நடைபெறும் என்பதை நாங்கள் விளக்கினாலும், அந்த திசுவின் முடிவுகள் ஆய்வகத்தில் ஆய்வு செய்யப்பட்ட பின்னரே உண்மை நிலை தெரியவரும்.\n\n"
                    f"மருத்துவர் {doc_name} செயல்முறை குறித்து உங்களிடம் முழுமையாக விளக்கி, முடிவுகள் வந்தவுடன் உங்களுடன் கலந்துரையாடுவார்.\n\n"
                    f"பரிசோதனைக்கு முன் மருத்துவர் {doc_name}-யிடம் கேட்க வேண்டிய கேள்விகளைத் தொகுக்க உதவவா?"
                )
            if lang == "es":
                return (
                    f"Comprendo que la sola palabra biopsia pueda causarle preocupación y temor, {patient_name}.\n\n"
                    "Una biopsia mamaria es un procedimiento ambulatorio estándar donde el médico toma una pequeña muestra de tejido aplicando anestesia local para minimizar cualquier molestia.\n\n"
                    "Aunque podemos explicarle en qué consiste el procedimiento, sólo el análisis de patología en el laboratorio determinará la naturaleza del tejido.\n\n"
                    f"Su médico, el {doc_name}, le explicará los pasos exactos durante su visita y analizará los resultados con usted tan pronto como estén listos.\n\n"
                    f"¿Le gustaría preparar algunas preguntas para hacerle al {doc_name} antes de la cita?"
                )
            if lang == "ar":
                return (
                    f"أتفهم أن فكرة إجراء الخزعة قد تبعث على التوتر والقلق يا {patient_name}.\n\n"
                    "الخزعة هي إجراء تشخيصي روتيني في العيادة، حيث يأخذ الطبيب عينة صغيرة جداً من النسيج باستخدام تخدير موضعي لتفادي الألم.\n\n"
                    "ورغم توضيحنا لخطوات الإجراء، إلا أن فحص العينة في المختبر هو وحده الذي يكشف طبيعة النسيج بدقة.\n\n"
                    f"سيشرح لكِ {doc_name} كافة تفاصيل الإجراء مسبقاً، وسيراجع معكِ نتائج التحليل فور صدورها.\n\n"
                    f"هل ترغبين في تدوين بعض الأسئلة التي تودين طرحها على {doc_name}؟"
                )

            return (
                f"I understand that hearing you need a biopsy can feel stressful and unsettling, {patient_name}.\n\n"
                "A breast biopsy is a standard outpatient procedure where a doctor gently takes a small tissue sample using local numbing so you feel minimal discomfort.\n\n"
                "While we can explain what happens during the procedure, only the pathology laboratory analysis can determine what the tissue is.\n\n"
                f"Your doctor, {doc_name}, will walk you through the procedure beforehand and discuss the pathology findings directly with you.\n\n"
                f"Would you like me to help you prepare a few questions to ask {doc_name}?"
            )

        # Discomfort / pain inquiry
        if "pain" in proc_lower or "hurt" in proc_lower:
            if lang == "es":
                return (
                    f"Comprendo su preocupación por el dolor durante los exámenes, {patient_name}.\n\n"
                    "Durante estos procedimientos se utiliza anestesia local para adormecer el área, de modo que sólo sienta una leve presión.\n\n"
                    "La sensibilidad de cada persona es única y el equipo adaptará la atención a su comodidad.\n\n"
                    f"El {doc_name} se asegurará de que esté cómoda antes de iniciar cualquier paso.\n\n"
                    f"¿Desea que anote su sensibilidad en sus notas de atención para el equipo médico?"
                )
            if lang == "ar":
                return (
                    f"أتفهم تماماً قلقكِ بشأن الشعور بأي ألم يا {patient_name}.\n\n"
                    "يحرص الفريق الطبي على استخدام التخدير الموضعي لتخدير المنطقة بحيث لا تشعرين سوى بضغط خفيف.\n\n"
                    "تختلف درجة الإحساس من شخص لآخر، وسيقوم الفريق بضبط الرعاية لتوفير أقصى درجات الراحة لكِ.\n\n"
                    f"سيتأكد {doc_name} وفريق التمريض من راحتكِ طوال فترة الفحص.\n\n"
                    f"هل تودين أن أسجل ملاحظة في ملفكِ ليأخذها الفريق في الاعتبار أثناء زيارتكِ؟"
                )
            return (
                f"I understand your concern about pain and discomfort, {patient_name}.\n\n"
                "During diagnostic procedures, local numbing is applied to the area so you should only feel light pressure rather than sharp pain.\n\n"
                "Each person experiences sensations differently, and the clinical team will adjust to keep you comfortable throughout.\n\n"
                f"Your doctor, {doc_name}, will check in with you continuously during the visit.\n\n"
                f"Would you like me to note your sensitivity in your care file for {doc_name} and your coordinator?"
            )

        return cls.explain_finding("evaluation", "screening", patient_name, lang, inquiry_topic, case_context)

    @classmethod
    def answer_case_inquiry(
        cls,
        message: str,
        case_context: Dict[str, Any],
        patient_context: Dict[str, Any],
        lang: str = "en"
    ) -> Optional[str]:
        """
        Dynamically answers patient inquiries grounding in documented case facts only.
        Follows the 5-step counselling structure:
        (1) Acknowledge feeling in 1 sentence.
        (2) Answer in plain words.
        (3) Honest about what cannot be known from chat.
        (4) Say what happens next and who will explain (doctor).
        (5) ONE gentle next step.
        """
        msg_lower = (message or "").lower()
        first_name = cls._resolve_patient_first_name(patient_context)
        patient_name = first_name or (patient_context.get("full_name", "").split()[0] if patient_context.get("full_name") else "")
        p_display = f", {patient_name}" if patient_name else ""
        doc_name = cls._resolve_doctor_name(case_context)
        coord_name = cls._resolve_coordinator_name(case_context)
        screening_type = case_context.get("screening_type", "mammogram")
        finding_code = case_context.get("finding_code", "BI-RADS 4")
        finding_summary = case_context.get("finding_summary", "focal asymmetry requiring further diagnostic evaluation")

        stages = case_context.get("lifecycle_stages") or []
        cr = case_context.get("clinical_review") or {}
        co = case_context.get("consultation_outcome") or {}
        tm = case_context.get("treatment_monitoring") or {}
        fu = case_context.get("follow_up") or {}
        is_closed = case_context.get("is_closed", False) or case_context.get("status") == "closed"

        # Check if finalized report is available
        has_finalized_report = (
            case_context.get("screening_result") is not None
            or any(s.get("stage_number") == 2 and s.get("status") == "completed" for s in stages)
            or bool(case_context.get("finding_summary"))
        )

        # 0. "Where am I in my care journey?" / "What stage am I in?"
        if any(term in msg_lower for term in [
            "where am i in my care journey", "where am i in my journey", "where am i in the care journey",
            "where am i in journey", "where am i right now", "where am i", "what stage am i in",
            "what is my stage", "care journey status", "my care journey", "care journey",
            "how about my health", "my care pathway", "care pathway", "current stage",
            "dónde estoy en mi proceso", "dónde estoy en mi camino", "en qué etapa estoy",
            "أين أنا في رحلتي العلاجية", "ما هي مرحلتي الحالية", "أين وصلت في رحلتي",
            "என் மருத்துவப் பயணத்தில் நான் எங்கே இருக்கிறேன்", "நான் எந்த நிலையில் உள்ளேன்"
        ]) or (
            ("where" in msg_lower or "stage" in msg_lower or "status" in msg_lower or "journey" in msg_lower)
            and any(w in msg_lower for w in ["journey", "care", "pathway", "stage", "step"])
        ):
            curr_stage_num = case_context.get("current_stage_number")
            if not curr_stage_num and stages:
                active_s = next((s for s in stages if s.get("status") in ("active", "in_progress")), None)
                curr_stage_num = active_s.get("stage_number", 4) if active_s else 4
            else:
                curr_stage_num = curr_stage_num or 4

            if lang == "es":
                return (
                    f"Comprendo lo importante que es tener una orientación clara y paso a paso sobre su proceso de atención{p_display}.\n\n"
                    f"Actualmente se encuentra en la Etapa {curr_stage_num} de su plan de atención:\n"
                    f"• Pasos completados: Su mamografía de detección fue realizada, y su informe diagnóstico oficial ha sido finalizado.\n"
                    f"• Paso actual (Etapa 4 - Comprensión de resultados): Su informe se encuentra listo en su expediente para que lo revise junto a su equipo médico.\n"
                    f"• Próximo paso: Una consulta clínica con su médico tratante, el {doc_name}, para revisar las imágenes y planificar los pasos recomendados.\n\n"
                    f"Este canal de conversación le ayuda a orientarse en sus etapas y entender los términos médicos, pero sólo el {doc_name} puede brindar un diagnóstico definitivo.\n\n"
                    f"Su coordinadora de atención, {coord_name}, y el {doc_name} están acompañándole en cada paso de esta evaluación.\n\n"
                    f"¿Le gustaría que le explique lo que dice su informe o prefiere verificar horarios de consulta con el {doc_name}?"
                )
            elif lang == "ar":
                return (
                    f"أتفهم تماماً رغبتكِ في الحصول على رؤية واضحة ومحددة لخطوات رحلتكِ العلاجية الحالية{p_display}.\n\n"
                    f"أنتِ حالياً في المرحلة {curr_stage_num} من خطة رعايتكِ:\n"
                    f"• الخطوات المكتملة: تم إجراء فحص الماموجرام، واكتمال التقرير الإشعاعي التشخيصي وتوثيقه رسمياً في سجلكِ.\n"
                    f"• مرحلتكِ الحالية (المرحلة 4 - فهم النتائج): تقريركِ جاهز للمراجعة والاستيعاب بالتعاون مع فريق رعايتكِ.\n"
                    f"• الخطوة القادمة: استشارة سريرية مع طبيبكِ المعالج، {doc_name}، لمناقشة نتائج الفحص بالتفصيل وبحث الخطوات الطبية التالية.\n\n"
                    f"تساعدكِ هذه المحادثة في متابعة مراحل الرعاية وفهم المصطلحات، ولكن الطبيب المعالج وحده {doc_name} المخول بتقديم التقييم والتشخيص الطبي.\n\n"
                    f"منسقة رعايتكِ {coord_name} وطبيبكِ {doc_name} يتابعون كل خطوة معكِ باهتمام.\n\n"
                    f"هل تودين أن أشرح لكِ ما ورد في تقريركِ، أم ترغبين في المساعدة لمعرفة المواعيد المتاحة للتحدث مع {doc_name}؟"
                )
            elif lang == "ta":
                return (
                    f"உங்கள் மருத்துவப் பயணத்தில் நீங்கள் எந்த நிலையில் உள்ளீர்கள் என்பதைத் தெளிவாக அறிந்துகொள்ள விரும்புவது முற்றிலும் இயல்பானது{p_display}.\n\n"
                    f"தற்போது நீங்கள் உங்களின் பராமரிப்புப் பயணத்தில் நிலை {curr_stage_num}-ல் உள்ளீர்கள்:\n"
                    f"• பூர்த்தி செய்யப்பட்டவை: தங்களின் மேமோகிராம் பரிசோதனை முடிக்கப்பட்டு, அதிகாரப்பூர்வ அறிக்கை இறுதி செய்யப்பட்டுள்ளது.\n"
                    f"• தற்போதைய நிலை (நிலை 4 - முடிவுகளைப் புரிந்துகொள்ளுதல்): மருத்துவக் குழுவுடன் கலந்தாலோசிக்க உங்கள் அறிக்கை தயாராக உள்ளது.\n"
                    f"• அடுத்த கட்டம்: தங்களின் மருத்துவர் {doc_name}-உடன் நேரடி மருத்துவ ஆலோசனை மேற்கொண்டு அடுத்தகட்ட முடிவுகளைத் தீர்மானித்தல்.\n\n"
                    f"இந்த உரையாடல் உங்கள் நிலையை அறிய உதவும்; எனினும் மருத்துவர் {doc_name} மட்டுமே நேரடி மருத்துவ ஆலோசனைகளை வழங்க முடியும்.\n\n"
                    f"மருத்துவ ஒருங்கிணைப்பாளர் {coord_name} மற்றும் மருத்துவர் {doc_name} உங்களுக்குத் துணையாக உள்ளனர்.\n\n"
                    f"உங்கள் அறிக்கையில் உள்ள விவரங்களை விளக்கவா, அல்லது மருத்துவர் {doc_name}-யிடம் ஆலோசனை பெற நேரத்தை ஒதுக்கவா?"
                )

            # English default
            return (
                f"I understand how important it is to have a clear, step-by-step view of where you are in your care journey{p_display}.\n\n"
                f"You are currently at Stage {curr_stage_num} in your care pathway:\n"
                f"• Completed steps: Your screening {screening_type} was completed, and your official diagnostic report has been finalized and uploaded.\n"
                f"• Current step (Stage 4 - Understanding Results): Your report is ready in your record for you and your care team to review together.\n"
                f"• What comes next: A clinical consultation with your attending specialist, {doc_name}, to discuss your imaging findings and plan any recommended next steps.\n\n"
                f"A chat conversation helps track your timeline and milestones, but only {doc_name} can provide medical answers and determine clinical recommendations.\n\n"
                f"Your care coordinator, {coord_name}, and {doc_name} are right here to guide you through every step of this journey.\n\n"
                f"Would you like me to walk you through what is documented in your report, or help you check appointment openings to speak with {doc_name}?"
            )

        # 1. "What does my report say?" / "my report what saying" / "what does my screening result mean?" / "explain my report"
        if any(term in msg_lower for term in [
            "report what saying", "my report what saying", "what report saying", "my report saying",
            "what does my report say", "what does my screening result mean", "result mean",
            "explain my report", "explain report", "can you explain my report", "explain my results", "explain findings",
            "what is my result", "what does my result", "que dice mi informe", "qué significa mi informe",
            "ماذا يقول تقريري", "ماذا يعني تقريري"
        ]):
            if lang == "es":
                if has_finalized_report:
                    return (
                        f"Comprendo lo importante que es tener información clara sobre lo que dice su informe, {patient_name}.\n\n"
                        f"Su informe de {screening_type} documenta: hallazgo categorizado como {finding_code} ({finding_summary}).\n\n"
                        "Un chat no puede diagnosticar ni interpretar estos hallazgos de forma aislada; sólo un médico evaluando las imágenes y las pruebas diagnósticas puede determinar su significado.\n\n"
                        f"Su médico, el {doc_name}, revisará con usted estos resultados documentados y le explicará los pasos recomendados.\n\n"
                        f"¿Le gustaría consultar las fechas disponibles para reunirse con el {doc_name}?"
                    )
                return (
                    f"Comprendo su deseo de conocer los resultados de su informe, {patient_name}.\n\n"
                    "En este momento, su informe diagnóstico definitivo aún no ha sido finalizado en nuestro sistema clínico.\n\n"
                    "No podemos discutir hallazgos médicos hasta que el informe oficial esté debidamente firmado y validado.\n\n"
                    f"Tan pronto como esté listo, su médico, el {doc_name}, lo revisará en detalle con usted.\n\n"
                    f"¿Desea que le pida a su coordinadora {coord_name} que le notifique apenas esté disponible?"
                )

            if lang == "ar":
                if has_finalized_report:
                    return (
                        f"أتفهم تماماً رغبتكِ في الحصول على توضيح دقيق ومبسط لما ورد في تقريركِ الطبي يا {patient_name}.\n\n"
                        f"يوثق تقرير فحص {screening_type} المعتمد لديكِ: نتيجة مصنفة كـ {finding_code} ({finding_summary}).\n\n"
                        "لا يمكن لأي محادثة نصية وضع تشخيص أو تفسير التقرير بمعزل عن الفحص الطبي المباشر؛ فالطبيب وحده من يحدد دلالة هذه الملاحظات بدقة.\n\n"
                        f"سيقوم طبيبكِ المعالج، {doc_name}، بمراجعة هذه النتائج الموثقة معكِ وتوضيح الخطوات الطبية القادمة.\n\n"
                        f"هل ترغبين في المساعدة في مراجعة المواعيد المتاحة لدى عيادة {doc_name}؟"
                    )
                return (
                    f"أتفهم تماماً حرصكِ على معرفة ما يتضمنه تقريركِ الطبي يا {patient_name}.\n\n"
                    "تقريركِ التشخيصي النهائي لم يكتمل اعتماده بعد في نظامنا السريري وهو قيد المراجعة الرسمية.\n\n"
                    "لا يمكننا مناقشة أي نتائج طبية قبل توثيق التقرير النهائي وتوقيعه رسمياً من الفريق المختص.\n\n"
                    f"وفور اعتماده، سيقوم طبيبكِ، {doc_name}، بمراجعته معكِ وتقديم التوجيه الكامل.\n\n"
                    f"هل تودين أن أطلب من منسقة رعايتكِ {coord_name} إشعاركِ فور جهوزية التقرير؟"
                )

            # English default
            if has_finalized_report:
                return (
                    f"I understand how important it is to have clear, straightforward information about what is documented in your report, {patient_name}.\n\n"
                    f"Your finalized {screening_type} report documents: {finding_code} ({finding_summary}).\n\n"
                    "A chat conversation cannot diagnose your condition or interpret tissue characteristics from these notes alone; only a medical doctor examining your clinical tests can determine what they mean.\n\n"
                    f"Your attending doctor, {doc_name}, will review these documented findings with you directly and discuss the next steps in your care.\n\n"
                    f"Would you like me to check available consultation openings with {doc_name}?"
                )
            return (
                f"I understand how eager you are to see what your report says, {patient_name}.\n\n"
                "Your finalized diagnostic report has not yet been uploaded and approved in your medical record.\n\n"
                "We cannot interpret or speculate on findings until the official clinical report is signed off by the radiology team.\n\n"
                f"As soon as it is validated, your doctor, {doc_name}, will review it thoroughly with you.\n\n"
                f"Would you like me to ask your care coordinator {coord_name} to notify you as soon as the finalized report is available?"
            )

        # 2. "Why does my doctor recommend further evaluation?"
        if any(term in msg_lower for term in ["why does my doctor recommend", "why do i need further evaluation", "recommend further evaluation", "why further evaluation"]):
            pathway = cr.get("approved_pathway") or "specialist diagnostic biopsy and targeted ultrasound"
            assessment = cr.get("clinical_assessment") or finding_summary
            return (
                f"I understand that being recommended for further testing brings up questions and worry, {patient_name}.\n\n"
                f"Dr. {doc_name} reviewed your screening findings ({finding_code}) and recommended a {pathway} based on the assessment: {assessment}.\n\n"
                "A recommendation for further evaluation is a diagnostic investigation, not a final medical diagnosis; only specialized tissue testing can provide complete clarity.\n\n"
                f"Dr. {doc_name} will conduct this evaluation and discuss what is found directly with you.\n\n"
                f"Would you like me to help check scheduling openings with Dr. {doc_name}'s clinic?"
            )

        # 3. "Has my referral been accepted?"
        if any(term in msg_lower for term in ["referral been accepted", "referral accepted", "has my referral", "status of my referral", "is my referral accepted"]):
            ref = case_context.get("active_referral") or {}
            stage_8 = next((s for s in stages if s.get("stage_number") == 8), None)
            is_accepted = (stage_8 and stage_8.get("status") == "completed") or (ref and ref.get("status") == "accepted")
            target_facility = (ref.get("target_facility") if ref else None) or (stage_8.get("evidence", {}).get("facility") if stage_8 else "CareBridge Breast Health Clinic")
            specialty = (ref.get("specialty") if ref else None) or "Breast Surgical Oncology"

            if is_accepted:
                return (
                    f"I understand you are waiting for news on your specialty care, {patient_name}.\n\n"
                    f"Your specialist referral to {target_facility} for {specialty} has been officially accepted by the clinic.\n\n"
                    "Our coordination team is actively aligning the clinic's schedule with your preferred availability.\n\n"
                    f"Your care coordinator, {coord_name}, and Dr. {doc_name} will oversee your visit.\n\n"
                    f"Would you like to review available appointment dates with {coord_name}?"
                )
            return (
                f"I hear how anxious you are to hear about your referral status, {patient_name}.\n\n"
                f"Your specialist referral to {target_facility} has been transmitted and is currently being processed by the clinical review team.\n\n"
                "Referral processing involves verifying clinical details before appointment dates can be finalized.\n\n"
                f"Your care coordinator, {coord_name}, is monitoring this closely with the clinic to ensure timely response.\n\n"
                f"Would you like me to alert {coord_name} to check on the progress today?"
            )

        # 4. "When is my appointment?"
        if any(term in msg_lower for term in [
            "when is my appointment", "when is my next appointment", "next appointment", "upcoming appointment",
            "appointment date", "time is my appointment", "my upcoming appointment", "when is the appointment",
            "cuándo es mi cita", "mi próxima cita", "متى موعدي", "موعدي القادم"
        ]):
            appt = case_context.get("upcoming_appointment") or {}
            if not appt and case_context.get("appointment_history"):
                appt = case_context.get("appointment_history")[-1]
            stage_9 = next((s for s in stages if s.get("stage_number") == 9), None)

            if appt and appt.get("scheduled_time"):
                sched_time = appt.get("scheduled_time")
                provider = appt.get("provider_name", doc_name)
                fac = appt.get("facility", "CareBridge Breast Health Clinic")
                return (
                    f"I understand you want to verify your scheduled visit, {patient_name}.\n\n"
                    f"Your appointment is confirmed for {sched_time} with {provider} at {fac}.\n\n"
                    "Please arrive 15 minutes before your time to complete any check-in paperwork.\n\n"
                    f"{provider} will meet with you to review your care pathway in detail.\n\n"
                    f"Would you like me to help you arrange transportation or review clinic preparation details?"
                )
            return (
                f"I understand you want to know when your visit will take place, {patient_name}.\n\n"
                "You do not currently have a confirmed appointment on file in your record.\n\n"
                "Appointments are secured once clinic availability is matched with your preferences.\n\n"
                f"Your care coordinator, {coord_name}, is actively working to coordinate available openings with {doc_name}'s clinic.\n\n"
                f"Would you like me to look up available appointment slots right now?"
            )

        # 5. "What should I expect during my consultation?"
        if any(term in msg_lower for term in ["expect during my consultation", "expect during consultation", "what to expect", "what happens during consultation", "during my consultation"]):
            return (
                f"I know that preparing for a specialist consultation can bring up questions and worry, {patient_name}.\n\n"
                f"During your visit, Dr. {doc_name} will review your medical history, perform a focused physical exam, and explain any recommended diagnostic imaging or biopsy.\n\n"
                "Every patient's clinical path is unique, so the exact steps will be determined based on Dr. {doc_name}'s evaluation.\n\n"
                f"Dr. {doc_name} and the clinical nursing team will support you throughout the appointment and answer all your questions.\n\n"
                f"Would you like me to help you write down a list of questions to bring with you to your visit?"
            )

        # 6. "What did my doctor recommend?"
        if any(term in msg_lower for term in ["what did my doctor recommend", "doctor's recommendation", "doctor recommend", "what did doctor say"]):
            if co and co.get("biopsy_pathology_outcome"):
                outcome = co.get("biopsy_pathology_outcome")
                recs = co.get("clinical_recommendations", "Follow prescribed care plan")
                return (
                    f"I understand you are looking for clarity regarding the doctor's documented guidance, {patient_name}.\n\n"
                    f"Following your evaluation, Dr. {doc_name} documented: Pathology Finding: {outcome}; Recommendations: {recs}.\n\n"
                    "These clinical records represent documented findings and guidance; ongoing care requires continuous physician follow-up.\n\n"
                    f"Dr. {doc_name} will review your ongoing care plan during your next follow-up.\n\n"
                    f"Would you like me to check your next scheduled appointment with Dr. {doc_name}?"
                )
            if cr and cr.get("approved_pathway"):
                return (
                    f"I understand you want to confirm your doctor's clinical recommendation, {patient_name}.\n\n"
                    f"Dr. {doc_name} reviewed your screening findings and recommended: {cr.get('approved_pathway')}.\n\n"
                    "This recommended pathway is a diagnostic plan designed to give your care team full clarity on your breast health.\n\n"
                    f"Dr. {doc_name} will discuss this pathway in detail during your consultation.\n\n"
                    f"Would you like to explore scheduling options for this consultation?"
                )
            return (
                f"I understand you are awaiting the doctor's formal recommendation, {patient_name}.\n\n"
                f"Dr. {doc_name} has not yet finalized a specific clinical recommendation in your case record.\n\n"
                "Our team will not speculate on clinical guidance until Dr. {doc_name} completes the official review.\n\n"
                f"Your care coordinator, {coord_name}, is tracking this review and will alert you once documented.\n\n"
                f"Would you like me to notify {coord_name} to follow up on this review?"
            )

        return None

    @classmethod
    def _resolve_lang(cls, intent: IntentAnalysis, patient_context: Dict[str, Any]) -> str:
        raw_q = intent.raw_query or ""
        pref = patient_context.get("preferred_language", "en")
        if any("\u0b80" <= c <= "\u0bff" for c in raw_q):
            return "ta"
        if any("\u0600" <= c <= "\u06ff" for c in raw_q) or intent.detected_language == "ar" or pref == "ar":
            if any("\u0600" <= c <= "\u06ff" for c in raw_q) or pref == "ar":
                return "ar"
        if intent.detected_language == "es" or any(w in raw_q.lower() for w in ["hola", "cita", "médico", "biopsia", "gracias", "tengo", "informe", "cáncer", "por favor"]):
            return "es"
        if pref in ("es", "ar", "ta"):
            return pref
        return "en"

    @classmethod
    def formulate_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any],
        conversation_context: Dict[str, Any]
    ) -> CoordinationPlan:
        """Formulates an empathetic counselling communication plan with verified 5-step response."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = cls._resolve_patient_first_name(patient_context) or patient_context.get("full_name") or ""
        lang = cls._resolve_lang(intent, patient_context)
        finding_code = case_context.get("finding_code", "BI-RADS 4")
        screening_type = case_context.get("screening_type", "Mammogram")
        doc_name = cls._resolve_doctor_name(case_context)
        coord_name = cls._resolve_coordinator_name(case_context)

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="get_screening_result",
                arguments={"case_id": case_id},
                rationale="Retrieve factual screening finding context to ground counselling response.",
                autonomy_level=1
            ),
            ProposedAction(
                step_number=2,
                tool_name="update_case_notes",
                arguments={
                    "case_id": case_id,
                    "note": f"Patient inquired regarding {intent.inquiry_topic or 'screening finding'}. Provided 5-step empathetic counselling without diagnosing.",
                    "barrier_detected": "fear_anxiety" if any(b.barrier_type == "fear_anxiety" for b in intent.detected_barriers) else None
                },
                rationale="Document patient counselling touchpoint in persistent case memory.",
                autonomy_level=1
            )
        ]

        raw_q = intent.raw_query or intent.inquiry_topic or ""
        inquiry_reply = cls.answer_case_inquiry(raw_q, case_context, patient_context, lang)

        is_anxious = (
            any(b.barrier_type == "fear_anxiety" for b in intent.detected_barriers)
            or intent.emotional_state in ("anxious", "overwhelmed", "fearful")
            or any(w in raw_q.lower() for w in ["scared", "afraid", "nervous", "worried", "terrified", "fear", "anxious", "பயம்", "miedo", "temor", "خوف", "خائفة"])
        )

        if inquiry_reply:
            msg = inquiry_reply
        elif is_anxious and not any(term in raw_q.lower() for term in ["result mean", "what is my result", "what does my result", "bi-rads", "birads"]):
            msg = cls.provide_emotional_reassurance(patient_name, finding_code, screening_type, lang, case_context)
        elif intent.inquiry_topic == "biopsy" or "biopsy" in raw_q.lower():
            msg = cls.explain_procedure("biopsy", patient_name, lang, case_context)
        elif intent.inquiry_topic == "pain" or any(w in raw_q.lower() for w in ["pain", "hurt", "வலி", "dolor", "ألم"]):
            msg = cls.explain_procedure("pain", patient_name, lang, case_context)
        else:
            msg = cls.explain_finding(finding_code, screening_type, patient_name, lang, intent.inquiry_topic, case_context)

        return CoordinationPlan(
            goal="Provide empathetic 5-step counselling answering patient questions before scheduling.",
            situation_summary=f"Patient inquired regarding screening finding {finding_code} (topic: {intent.inquiry_topic or 'general'}).",
            actions=actions,
            patient_response_draft=msg,
            target_language=lang
        )

    @classmethod
    def formulate_referral_explanation_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any],
        conversation_context: Optional[Dict[str, Any]] = None
    ) -> CoordinationPlan:
        """Explains the clinical rationale behind the specialist referral in 5-step counselling tone."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = cls._resolve_patient_first_name(patient_context) or patient_context.get("full_name") or ""
        lang = cls._resolve_lang(intent, patient_context)
        finding_code = case_context.get("finding_code", "BI-RADS 4")
        screening_type = case_context.get("screening_type", "mammogram")
        cr = case_context.get("clinical_review") or {}
        doc_name = cls._resolve_doctor_name(case_context)
        coord_name = cls._resolve_coordinator_name(case_context)
        pathway = cr.get("approved_pathway") or "specialist diagnostic evaluation and ultrasound"

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="get_referral_status",
                arguments={"case_id": case_id},
                rationale="Audit referral details to provide accurate rationale to patient.",
                autonomy_level=1
            ),
            ProposedAction(
                step_number=2,
                tool_name="update_case_notes",
                arguments={
                    "case_id": case_id,
                    "note": f"Explained referral rationale for {finding_code} to patient in 5-step counselling style.",
                    "barrier_detected": None
                },
                rationale="Document educational explanation of referral rationale in case notes.",
                autonomy_level=1
            )
        ]

        if lang == "es":
            msg = (
                f"Comprendo que recibir una derivación especializada genera inquietud y preguntas sobre su salud, {patient_name}.\n\n"
                f"El {doc_name} recomendó esta derivación tras su {screening_type} ({finding_code}) para que un especialista realice una evaluación diagnóstica detallada ({pathway}).\n\n"
                "Una derivación permite obtener evaluaciones avanzadas pero no constituye un diagnóstico definitivo en sí misma.\n\n"
                f"El {doc_name} y su equipo le explicarán cada paso clínico durante su consulta especializada.\n\n"
                f"¿Le gustaría coordinar las opciones de citas para su consulta con el {doc_name}?"
            )
        elif lang == "ar":
            msg = (
                f"أتفهم تماماً التساؤلات والقلق الذي قد يسببه الحصول على إحالة لمركز تخصصي يا {patient_name}.\n\n"
                f"أوصى {doc_name} بهذه الإحالة بعد فحص {screening_type} ({finding_code}) لضمان خضوعكِ لتقييم تشخيصي متخصص وشامل ({pathway}).\n\n"
                "تعد الإحالة خطوة تشخيصية متقدمة ولا تعني تشخيصاً نهائياً بحد ذاتها.\n\n"
                f"سيقوم {doc_name} وفريق العيادة التخصصية بمتابعة كافة خطوات الرعاية معكِ بالتفصيل.\n\n"
                f"هل تودين المساعدة في ترتيب موعدكِ مع عيادة {doc_name}؟"
            )
        else:
            msg = (
                f"I understand that receiving a specialist referral can bring up uncertainty and worry, {patient_name}.\n\n"
                f"{doc_name} recommended this specialist referral following your {screening_type} ({finding_code}) to ensure you receive expert diagnostic evaluation ({pathway}).\n\n"
                "A referral is an investigative clinical step to gather more detailed information; it is not a final medical diagnosis.\n\n"
                f"{doc_name} and the specialist clinical team will guide you through the findings and next steps during your consultation.\n\n"
                f"Would you like me to help check available consultation options with {doc_name}'s clinic?"
            )

        return CoordinationPlan(
            goal="Explain clinical referral rationale empathetically with 5-step counselling structure.",
            situation_summary="Patient asked why doctor recommended a specialist referral.",
            actions=actions,
            patient_response_draft=msg,
            target_language=lang
        )
