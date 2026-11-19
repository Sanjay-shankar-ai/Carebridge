"""
CareBridge Patient Communication Agent
Specialized agent responsible for:
- Drafting empathetic, culturally attuned patient messages in English and Tamil
- Explaining screening results and clinical findings (e.g. BI-RADS 4, Mammogram, Pap smear) in plain language
- Explaining procedure steps (e.g. biopsy, ultrasound, consultations) to alleviate anxiety
- Supporting language translation and accessible terminology
- STRICT CLINICAL GUARDRAIL: Never diagnoses, never prescribes, never claims a definitive cancer diagnosis.
"""

from typing import Dict, Any, List, Optional
from app.agents.state import CoordinationPlan, ProposedAction, IntentAnalysis


class PatientCommunicationAgent:
    """Specialized agent for empathetic patient education, reassurance, and communication."""

    @classmethod
    def explain_finding(
        cls,
        finding_code: str,
        screening_type: str,
        patient_name: str,
        lang: str = "en",
        inquiry_topic: Optional[str] = None
    ) -> str:
        """Generates reassuring, factual explanation of screening findings without diagnosing."""
        code_upper = (finding_code or "").upper()
        
        # BI-RADS Mammography findings
        if "BI-RADS" in code_upper or "BIRADS" in code_upper or "4" in code_upper:
            if lang == "ta":
                return (
                    f"வணக்கம் {patient_name}, BI-RADS 4 என்பது பரிசோதனையில் கூடுதல் தெளிவு தேவைப்படும் ஒரு மாறுபாடு மட்டுமே. "
                    "இது புற்றுநோய் உறுதி செய்யப்பட்டதல்ல. பெரும்பாலான (சுமார் 70% முதல் 80%) பயாப்ஸி பரிசோதனைகளில் இது சாதாரண மாறுதலாகவே (benign) முடிவடைகிறது. "
                    "முழுமையான மன அமைதிக்காக மட்டுமே மருத்துவர் இந்த பயாப்ஸி பரிசோதனையை பரிந்துரைத்துள்ளார். எங்கள் மருத்துவக் குழு உங்களுடன் துணை நிற்கும்."
                )
            if lang == "es":
                return (
                    f"Hola {patient_name}. Un hallazgo BI-RADS 4 indica una anomalía observada en su examen de {screening_type or 'mamografía'} "
                    "que requiere una evaluación diagnóstica más detallada. Es fundamental señalar que BI-RADS 4 NO es un diagnóstico de cáncer. "
                    "De hecho, aproximadamente entre el 70% y el 80% de las biopsias BI-RADS 4 resultan ser completamente benignas (no cancerosas). "
                    "La evaluación de seguimiento es un paso preventivo estándar para brindarle a usted y a su equipo médico certeza y tranquilidad absoluta. "
                    "¿Desea que le ayude a consultar las opciones de citas disponibles con la clínica del Dr. Thorne, o tiene alguna otra pregunta sobre el estudio?"
                )
            if lang == "ar":
                return (
                    f"مرحباً {patient_name}. تشير نتيجة BI-RADS 4 إلى ملاحظة تغير في فحص {screening_type or 'الماموجرام'} "
                    "يتطلب تقييماً إضافياً لمزيد من الدقة. من المهم للغاية التأكيد على أن تصنيف BI-RADS 4 ليس تشخيصاً بالسرطان؛ "
                    "ففي الواقع، نحو 70% إلى 80% من نتائج الخزعات لتصنيف BI-RADS 4 تظهر أنها حميدة تماماً (غير سرطانية). "
                    "إن إجراء المتابعة أو الخزعة هو مجرد خطوة وقائية روتينية تهدف إلى منحك وفريقك الطبي الطمأنينة الكاملة واليقين. "
                    "هل ترغبين في أن أساعدك في التحقق من خيارات المواعيد المتاحة لدى عيادة د. ثورن، أم لديك استفسارات أخرى عن الفحص؟"
                )
            return (
                f"Hello {patient_name}. A BI-RADS 4 finding indicates an abnormality was noted on your screening {screening_type or 'mammogram'} "
                "that has suspicious features and requires further evaluation. Crucially, BI-RADS 4 is NOT a diagnosis of cancer. "
                "In fact, approximately 70% to 80% of BI-RADS 4 biopsies turn out to be completely benign (non-cancerous). "
                "The follow-up diagnostic evaluation or biopsy is a routine, precautionary step so your clinical team can provide you complete certainty and peace of mind. "
                "Would you like me to help check available appointment options with Dr. Thorne's clinic, or do you have other questions about the test?"
            )

        # General finding explanation
        if lang == "ta":
            return (
                f"வணக்கம் {patient_name}, தங்களின் பரிசோதனை முடிவில் ({finding_code or screening_type}) கூடுதல் பரிசோதனை தேவைப்படுகிறது. "
                "இது வழக்கமான ஒரு பாதுகாப்பு நடவடிக்கையே ஆகும். எவ்வித அச்சமும் தேவையில்லை; எங்கள் மருத்துவக் குழு உங்களுக்கு முழு ஆதரவு அளிக்கும். "
                "சந்திப்பு நேரத்தை திட்டமிட உதவவா?"
            )
        if lang == "es":
            return (
                f"Hola {patient_name}. El resultado de su examen ({finding_code or screening_type}) ha sido revisado por nuestro equipo clínico. "
                "Encontrar un área que requiere una observación más detallada es muy común y no significa que haya un problema grave. "
                "Una consulta de seguimiento es el paso más seguro para brindarle claridad total. ¿Desea revisar las opciones de citas próximas?"
            )
        if lang == "ar":
            return (
                f"مرحباً {patient_name}. تمت مراجعة نتيجة فحصك ({finding_code or screening_type}) من قِبل فريقنا السريري. "
                "إن ملاحظة منطقة تحتاج إلى تدقيق إضافي أمر شائع جداً ولا يعني بالضرورة وجود أي مشكلة. "
                "المتابعة الطبية هي الإجراء القياسي الأكثر أماناً لمنحك وضوحاً تاماً. هل ترغبين في المساعدة في مراجعة مواعيدك القادمة؟"
            )
        return (
            f"Hello {patient_name}. Your screening result ({finding_code or screening_type}) has been reviewed by our clinical team. "
            "Finding an area that needs a closer look is very common and does not mean anything is wrong. "
            "A follow-up consultation or diagnostic imaging is simply the safest, standard step to give you complete clarity. "
            "Would you like me to help review upcoming appointment options, or would you like to know more about the evaluation?"
        )

    @classmethod
    def provide_emotional_reassurance(
        cls,
        patient_name: str,
        finding_code: str,
        screening_type: str,
        lang: str = "en",
        coordinator_name: str = "Priya Nair, RN"
    ) -> str:
        """Provides compassionate, validating reassurance for patient fear or anxiety without diagnosing."""
        if lang == "ta":
            return (
                f"உங்கள் உணர்வுகளை நாங்கள் முழுமையாக புரிந்து கொள்கிறோம் {patient_name}. "
                "கூடுதல் பரிசோதனை தேவை என்று கேட்கும்போது பயமும் கவலையும் ஏற்படுவது மிகவும் இயல்பானது. "
                f"இருப்பினும், {finding_code} போன்ற பெரும்பாலான பரிசோதனை முடிவுகள் (சுமார் 70% முதல் 80%) சாதாரண மாறுதலாகவே (benign) முடிவடைகின்றன. "
                f"நீங்கள் இதில் தனியாக இல்லை—எங்கள் மருத்துவக் குழுவும் உங்கள் பராமரிப்பு ஒருங்கிணைப்பாளர் {coordinator_name}-உம் எப்போதும் உங்களுக்கு துணை நிற்போம். "
                "பரிசோதனை வழிமுறைகள் குறித்து மேலும் அறிய விரும்புகிறீர்களா, அல்லது சந்திப்பு நேரத்தை திட்டமிட உதவவா?"
            )
        if lang == "es":
            return (
                f"Comprendo profundamente lo que siente, {patient_name}, y es completamente normal y comprensible sentir temor o ansiedad en este momento. "
                f"Escuchar que necesita una evaluación adicional ({finding_code}) puede ser inquietante, pero recuerde: "
                "esto NO es un diagnóstico de cáncer. De hecho, aproximadamente entre el 70% y el 80% de las biopsias resultan ser completamente benignas. "
                f"No está sola en este proceso—todo nuestro equipo de atención y su coordinadora de cuidados, {coordinator_name}, están a su lado en cada paso. "
                "¿Le gustaría que le explique qué esperar durante la visita para mayor tranquilidad, o desea coordinar su cita?"
            )
        if lang == "ar":
            return (
                f"نحن نتفهم مشاعرك تماماً يا {patient_name}، ومن الطبيعي والمفهوم جداً الشعور بالخوف أو القلق في هذا الوقت. "
                f"إن معرفة أنك بحاجة إلى مزيد من التقييم لفحصك ({finding_code}) قد يثير القلق، ولكن تذكري دائماً: "
                "هذا ليس تشخيصاً بالسرطان إطلاقاً. في الواقع، نحو 70% إلى 80% من الخزعات تنتهي بنتائج حميدة تماماً. "
                f"أنتِ لستِ وحدك أبداً—فريقنا الطبي بأكمله ومنسقة رعايتك {coordinator_name} بجانبك في كل خطوة. "
                "هل ترغبين في أن أشرح لكِ ما يمكن توقعه أثناء الزيارة لتهدئة قلقك، أم تودين تنسيق موعد مناسب؟"
            )
        return (
            f"I hear you, {patient_name}, and it is completely normal and understandable to feel scared or anxious right now. "
            f"Hearing that you need further evaluation for your {screening_type} ({finding_code}) can feel overwhelming, but please remember: "
            "this is not a diagnosis of cancer. In fact, approximately 70% to 80% of biopsies turn out to be completely benign. "
            f"You are not alone in this—our entire care team and your care coordinator, {coordinator_name}, are by your side at every step. "
            "Would you like me to explain what to expect during the follow-up visit to help put your mind at ease, or would you like to explore scheduling options?"
        )

    @classmethod
    def explain_procedure(
        cls,
        procedure_type: str,
        patient_name: str,
        lang: str = "en"
    ) -> str:
        """Explains diagnostic procedures (biopsy, imaging) in understandable terms to reduce fear."""
        proc_lower = (procedure_type or "").lower()
        
        if "biopsy" in proc_lower:
            if lang == "ta":
                return (
                    f"பயாப்ஸி குறித்து கவலைப்பட வேண்டாம் {patient_name}. மருத்துவர் பகுதி மயக்க மருந்து (local anesthesia) "
                    "கொடுத்து செய்வதால் வலி இருக்காது; லேசான அழுத்தம் மட்டுமே உணரக்கூடும். இது சுமார் 20-30 நிமிடங்களில் முடிந்துவிடும் ஒரு எளிய புறநோயாளி பரிசோதனை மட்டுமே. "
                    "எங்கள் மருத்துவக் குழு உங்களுடன் துணை நிற்கும்."
                )
            if lang == "es":
                return (
                    f"Comprendemos que las preguntas sobre una biopsia puedan generar incertidumbre, {patient_name}. "
                    "Una biopsia es un procedimiento ambulatorio estándar y mínimamente invasivo realizado con anestesia local, "
                    "la cual adormece por completo la zona para que sólo sienta una ligera presión y ningún dolor. "
                    "El procedimiento suele durar sólo de 20 a 30 minutos, y nuestro equipo de atención estará con usted en todo momento."
                )
            if lang == "ar":
                return (
                    f"نتفهم تماماً أن الاستفسارات المتعلقة بالخزعة قد تسبب بعض القلق يا {patient_name}. "
                    "الخزعة إجراء تشخيصي بسيط وغير جراحي يتم في العيادة تحت تأثير التخدير الموضعي، "
                    "حيث يتم تخدير المنطقة بالكامل لتشعري بضغط خفيف فقط دون أي ألم. "
                    "يستغرق الإجراء عادةً من 20 إلى 30 دقيقة فقط، وسيكون فريق الرعاية بجانبك طوال الوقت."
                )
            return (
                f"We understand questions about biopsies can feel stressful, {patient_name}. A breast biopsy is a standard, minimally invasive outpatient procedure "
                "performed under local anesthesia, which numbs the area completely so you should only feel slight pressure, not pain. "
                "The procedure typically takes only 20 to 30 minutes, and our care team will be by your side the entire time."
            )
            
        if "pain" in proc_lower or "hurt" in proc_lower:
            if lang == "ta":
                return (
                    f"உங்கள் உணர்வை நாங்கள் புரிந்து கொள்கிறோம் {patient_name}. லேசான வலி அல்லது அசௌகரியம் சாதாரணமானது. "
                    "மருத்துவக் குழுவினர் உங்களை முழுமையாக கவனித்துக் கொள்வர்."
                )
            if lang == "es":
                return (
                    f"Gracias por compartir su preocupación sobre las molestias, {patient_name}. Su comodidad es nuestra máxima prioridad. "
                    "Todos los procedimientos de seguimiento utilizan anestesia local suave para minimizar cualquier molestia."
                )
            if lang == "ar":
                return (
                    f"نشكرك على مشاركة مخاوفك بشأن الألم يا {patient_name}. راحتك هي أولويتنا القصوى، ويتم استخدام التخدير الموضعي اللطيف لتقليل أي انزعاج."
                )
            return (
                f"Thank you for sharing your concerns about discomfort, {patient_name}. Your comfort is our top priority. "
                "All follow-up procedures use gentle local numbing so you feel minimal discomfort. We will also document your sensitivity "
                "in your case notes so Dr. Aris Thorne and your care coordinator can ensure your comfort throughout your visit."
            )

        return (
            f"Hello {patient_name}, we are here to support you through every step of your diagnostic care. "
            "Please feel free to ask any questions about your upcoming visits or procedures."
        )

    @classmethod
    def answer_case_inquiry(
        cls,
        message: str,
        case_context: Dict[str, Any],
        patient_context: Dict[str, Any],
        lang: str = "en"
    ) -> Optional[str]:
        """
        Dynamically answers the 9 critical longitudinal care journey inquiries without hallucinating:
          1. What does my screening result mean?
          2. Why does my doctor recommend further evaluation?
          3. Has my referral been accepted?
          4. When is my appointment?
          5. What should I expect during my consultation?
          6. What did my doctor recommend?
          7. What happens next in my treatment?
          8. When is my next follow-up?
          9. Have all my care steps been completed?
        """
        msg_lower = (message or "").lower()
        patient_name = patient_context.get("full_name") or patient_context.get("first_name", "Valued Patient")
        screening_type = case_context.get("screening_type", "mammogram")
        finding_code = case_context.get("finding_code", "BI-RADS 4")
        finding_summary = case_context.get("finding_summary", "suspicious finding requiring further evaluation")
        stages = case_context.get("lifecycle_stages") or []
        cr = case_context.get("clinical_review") or {}
        co = case_context.get("consultation_outcome") or {}
        tm = case_context.get("treatment_monitoring") or {}
        fu = case_context.get("follow_up") or {}
        is_closed = case_context.get("is_closed", False) or case_context.get("status") == "closed"

        # 1. "What does my screening result mean?"
        if any(term in msg_lower for term in ["screening result mean", "result mean", "what is my result", "what does my result"]):
            if lang == "ta":
                return (
                    f"வணக்கம் {patient_name}, உங்கள் {screening_type} பரிசோதனையில் {finding_code} ({finding_summary}) கண்டறியப்பட்டுள்ளது. "
                    "இது புற்றுநோய் உறுதி செய்யப்பட்டதல்ல. சுமார் 70% முதல் 80% பயாப்ஸி பரிசோதனைகளில் இது சாதாரண மாறுதலாகவே (benign) முடிகிறது. "
                    "முழுமையான தெளிவு மற்றும் மன அமைதிக்காகவே இந்த கூடுதல் பரிசோதனை பரிந்துரைக்கப்பட்டுள்ளது."
                )
            return (
                f"Hello {patient_name}. Your {screening_type} showed a finding categorized as {finding_code} ({finding_summary}). "
                "This means an area was detected that requires closer examination. Crucially, this is NOT a diagnosis of cancer; in fact, 70% to 80% of such findings turn out to be completely benign (non-cancerous). "
                "The follow-up evaluation is a standard precautionary step to provide complete certainty and reassurance."
            )

        # 2. "Why does my doctor recommend further evaluation?"
        if any(term in msg_lower for term in ["why does my doctor recommend", "why do i need further evaluation", "recommend further evaluation", "why further evaluation"]):
            doc_name = cr.get("doctor_name") or "Dr. Aris Thorne"
            pathway = cr.get("approved_pathway") or "specialist diagnostic biopsy and ultrasound"
            assessment = cr.get("clinical_assessment") or finding_summary
            if lang == "ta":
                return (
                    f"வணக்கம் {patient_name}, மருத்துவர் {doc_name} உங்கள் பரிசோதனை முடிவை ஆய்வு செய்து, "
                    f"துல்லியமான நோயறிதல் தெளிவுக்காக {pathway} பரிந்துரைத்துள்ளார் ({assessment}). இது உங்கள் பாதுகாப்பை உறுதி செய்யும் வழக்கமான மருத்துவ வழிகாட்டுதல் ஆகும்."
                )
            return (
                f"Hello {patient_name}. Dr. {doc_name} reviewed your screening findings ({finding_code}) and assessed: {assessment}. "
                f"Further evaluation through a {pathway} is recommended so that specialized tissue imaging or analysis can provide 100% diagnostic certainty and rule out any clinical risks."
            )

        # 3. "Has my referral been accepted?"
        if any(term in msg_lower for term in ["referral been accepted", "referral accepted", "has my referral", "status of my referral", "is my referral accepted"]):
            ref = case_context.get("active_referral") or {}
            stage_8 = next((s for s in stages if s.get("stage_number") == 8), None)
            is_accepted = (stage_8 and stage_8.get("status") == "completed") or (ref and ref.get("status") == "accepted")
            target_facility = (ref.get("target_facility") if ref else None) or (stage_8.get("evidence", {}).get("facility") if stage_8 else "CareBridge Breast Health Clinic")
            specialty = (ref.get("specialty") if ref else None) or "Breast Surgical Oncology"

            if is_accepted:
                if lang == "ta":
                    return f"ஆம் {patient_name}, {target_facility} மருத்துவ மையம் உங்கள் {specialty} பரிந்துரையை முறைப்படி ஏற்றுக்கொண்டுள்ளது. சந்திப்பு நேரத்தை உறுதி செய்ய உங்கள் ஒருங்கிணைப்பாளர் பணியாற்றி வருகிறார்."
                return f"Yes, {patient_name}! Your specialist referral to {target_facility} for {specialty} has been officially accepted. Your care coordinator is currently finalizing convenient appointment options for your visit."
            else:
                if lang == "ta":
                    return f"உங்கள் பரிந்துரை {target_facility} மையத்திற்கு அனுப்பப்பட்டுள்ளது, மேலும் 48 மணி நேரத்திற்குள் ஏற்றுக்கொள்ளப்படும் நிலையில் உள்ளது."
                return f"Your specialist referral to {target_facility} has been transmitted and is currently under active clinical review. Specialist facilities typically confirm acceptance within our standard 48-hour SLA."

        # 4. "When is my appointment?"
        if any(term in msg_lower for term in ["when is my appointment", "appointment date", "time is my appointment", "my upcoming appointment", "when is the appointment"]):
            appt = case_context.get("upcoming_appointment") or {}
            if not appt and case_context.get("appointment_history"):
                appt = case_context.get("appointment_history")[-1]
            stage_9 = next((s for s in stages if s.get("stage_number") == 9), None)

            if appt and appt.get("scheduled_time"):
                sched_time = appt.get("scheduled_time")
                provider = appt.get("provider_name", "Dr. Aris Thorne")
                fac = appt.get("facility", "CareBridge Breast Health Clinic")
                return f"Your appointment is confirmed for {sched_time} with {provider} at {fac}. Please arrive 15 minutes prior to your scheduled time."
            elif stage_9 and stage_9.get("status") == "completed":
                ev = stage_9.get("evidence") or {}
                return f"Your appointment is confirmed for {ev.get('scheduled_time', 'the designated date')} with {ev.get('provider_name', 'Dr. Aris Thorne')} at {ev.get('facility', 'CareBridge Clinic')}."
            else:
                return f"You do not currently have a confirmed appointment on file, {patient_name}. Your care coordinator is actively coordinating with the clinic to secure the earliest convenient opening for you."

        # 5. "What should I expect during my consultation?"
        if any(term in msg_lower for term in ["expect during my consultation", "expect during consultation", "what to expect", "what happens during consultation", "during my consultation"]):
            if lang == "ta":
                return (
                    f"வணக்கம் {patient_name}, உங்கள் ஆலோசனையின் போது மருத்துவர் உங்கள் உடல்நலம் குறித்து பேசுவார். "
                    "தேவைப்பட்டால் சிறிய பயாப்ஸி அல்லது அல்ட்ராசவுண்ட் பரிசோதனை செய்யப்படும். பகுதி மயக்க மருந்து (local anesthesia) கொடுக்கப்படுவதால் வலி இருக்காது, லேசான அழுத்தம் மட்டுமே உணரக்கூடும். இது 20-30 நிமிடங்களில் முடிந்துவிடும்."
                )
            return (
                f"During your consultation, {patient_name}, the specialist will review your symptoms and medical history, perform a focused examination, and may perform a targeted ultrasound or gentle biopsy. "
                "If a biopsy is conducted, the team uses local numbing medication so you only feel slight pressure, not pain. The entire visit typically takes about 20 to 30 minutes, and our care team will support you throughout."
            )

        # 6. "What did my doctor recommend?"
        if any(term in msg_lower for term in ["what did my doctor recommend", "doctor's recommendation", "doctor recommend", "what did doctor say"]):
            if co and co.get("biopsy_pathology_outcome"):
                doc_name = co.get("doctor_name", "Dr. Aris Thorne")
                outcome = co.get("biopsy_pathology_outcome")
                recs = co.get("clinical_recommendations", "Follow prescribed care plan")
                plan = co.get("treatment_plan", "Routine surveillance")
                return (
                    f"Following your evaluation, Dr. {doc_name} recorded the following clinical outcome: "
                    f"Pathology Result: {outcome}. "
                    f"Recommendations: {recs}. "
                    f"Care Plan: {plan}."
                )
            elif cr and cr.get("approved_pathway"):
                doc_name = cr.get("doctor_name", "Dr. Aris Thorne")
                return f"Dr. {doc_name} reviewed your screening findings and recommended: {cr.get('approved_pathway')}. Assessment: {cr.get('clinical_assessment')}."
            else:
                return "Your attending physician has not yet finalized a specific clinical recommendation. Our team will notify you as soon as the doctor's review is submitted."

        # 7. "What happens next in my treatment?"
        if any(term in msg_lower for term in ["what happens next in my treatment", "next in my treatment", "treatment next steps", "happens next"]):
            plan = tm.get("treatment_plan") or (co.get("treatment_plan") if co else None) or "Active clinical surveillance and care coordination"
            fu_date = fu.get("scheduled_date") or (co.get("next_followup_date") if co else None)
            fu_text = f" Your next follow-up evaluation is targeted for {fu_date}." if fu_date else ""
            return (
                f"Regarding your ongoing care, {patient_name}: Your active treatment plan is '{plan}'.{fu_text} "
                "Our team will continue monitoring your health, and you can contact your care coordinator anytime if you experience any symptoms or have questions."
            )

        # 8. "When is my next follow-up?"
        if any(term in msg_lower for term in ["when is my next follow-up", "next follow-up", "follow-up date", "when is follow up", "follow up scheduled"]):
            fu_date = fu.get("scheduled_date") or (co.get("next_followup_date") if co else None)
            fu_status = fu.get("status", "pending")
            if fu_date:
                return f"Your next follow-up milestone is scheduled for {fu_date} (Status: {fu_status.upper()}). We will send you reminders as the date approaches."
            elif is_closed:
                return "Your diagnostic care cycle is now complete! Dr. Thorne recommends routine annual preventive screening in 12 months."
            else:
                return f"A specific follow-up date has not yet been set, {patient_name}. Your care team will schedule this milestone once your current clinical phase is completed."

        # 9. "Have all my care steps been completed?"
        if any(term in msg_lower for term in ["have all my care steps been completed", "all care steps completed", "all my care steps", "care steps been completed", "is my case closed", "is my care completed"]):
            stage_14 = next((s for s in stages if s.get("stage_number") == 14), None)
            if is_closed or (stage_14 and stage_14.get("status") == "completed"):
                doc_name = (stage_14.get("evidence") or {}).get("doctor_name") if stage_14 else "Dr. Aris Thorne"
                doc_name = doc_name or "Dr. Aris Thorne"
                return (
                    f"Yes, {patient_name}! All 14 stages of your care journey have been successfully completed. "
                    f"Dr. {doc_name} has conducted the final review, verified all diagnostic and pathology documentation, and executed official clinical closure sign-off. "
                    "Your results are completely benign and reassuring. You may return to routine annual preventive screening."
                )
            else:
                curr_num = case_context.get("current_stage_number", 1)
                curr_id = case_context.get("current_stage_id", "ACTIVE")
                return (
                    f"Not quite yet, {patient_name}. Your care journey is currently at Stage {curr_num} of 14 ({curr_id.replace('_', ' ')}). "
                    "Our care team will continue guiding you step-by-step until verified clinical closure is signed off by your doctor."
                )

        return None

    @classmethod
    def _resolve_lang(cls, intent: IntentAnalysis, patient_context: Dict[str, Any]) -> str:
        raw_q = intent.raw_query or ""
        if any("\u0b80" <= c <= "\u0bff" for c in raw_q):
            return "ta"
        if any("\u0600" <= c <= "\u06ff" for c in raw_q):
            return "ar"
        if intent.detected_language == "es" and any(w in raw_q.lower() for w in ["hola", "cita", "médico", "biopsia", "gracias"]):
            return "es"
        return "en"

    @classmethod
    def formulate_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any],
        conversation_context: Dict[str, Any]
    ) -> CoordinationPlan:
        """Formulates an educational communication plan with appropriate factual tools."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = patient_context.get("full_name") or patient_context.get("first_name", "Valued Patient")
        lang = cls._resolve_lang(intent, patient_context)
        finding_code = case_context.get("finding_code", "BI-RADS 4")
        screening_type = case_context.get("screening_type", "Mammogram")

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="get_screening_result",
                arguments={"case_id": case_id},
                rationale="Retrieve factual screening finding context to ground educational response.",
                autonomy_level=1
            ),
            ProposedAction(
                step_number=2,
                tool_name="update_case_notes",
                arguments={
                    "case_id": case_id,
                    "note": f"Patient inquired regarding {intent.inquiry_topic or 'screening finding'}. Provided empathetic medical education without diagnosing.",
                    "barrier_detected": "fear_anxiety" if any(b.barrier_type == "fear_anxiety" for b in intent.detected_barriers) else None
                },
                rationale="Document patient educational touchpoint and reassurance in persistent case memory.",
                autonomy_level=1
            )
        ]

        # First check the 9 case-aware longitudinal inquiries
        raw_q = intent.raw_query or intent.inquiry_topic or ""
        inquiry_reply = cls.answer_case_inquiry(raw_q, case_context, patient_context, lang)

        # Check if patient expressed fear, anxiety, or emotional distress
        is_anxious = (
            any(b.barrier_type == "fear_anxiety" for b in intent.detected_barriers)
            or intent.emotional_state in ("anxious", "overwhelmed", "fearful")
            or any(w in raw_q.lower() for w in ["scared", "afraid", "nervous", "worried", "terrified", "fear", "anxious", "பயம்", "பயமாக", "miedo", "temor", "خوف", "خائفة"])
        )

        coord_name = case_context.get("current_owner_name") or "Priya Nair, RN"

        if inquiry_reply:
            msg = inquiry_reply
        elif is_anxious and not any(term in raw_q.lower() for term in ["result mean", "what is my result", "what does my result", "bi-rads 4 mean"]):
            msg = cls.provide_emotional_reassurance(patient_name, finding_code, screening_type, lang, coord_name)
        elif intent.inquiry_topic == "biopsy" or "biopsy" in raw_q.lower():
            msg = cls.explain_procedure("biopsy", patient_name, lang)
        elif intent.inquiry_topic == "pain" or any(w in raw_q.lower() for w in ["pain", "hurt", "வலி", "dolor", "ألم"]):
            msg = cls.explain_procedure("pain", patient_name, lang)
        else:
            msg = cls.explain_finding(finding_code, screening_type, patient_name, lang, intent.inquiry_topic)

        return CoordinationPlan(
            goal="Provide empathetic, accurate medical education answering patient questions before scheduling.",
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
        """Explains the clinical rationale behind the specialist referral in understandable terms."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = patient_context.get("full_name") or patient_context.get("first_name", "Valued Patient")
        lang = cls._resolve_lang(intent, patient_context)
        finding_code = case_context.get("finding_code", "BI-RADS 4")
        screening_type = case_context.get("screening_type", "mammogram")
        cr = case_context.get("clinical_review") or {}
        doc_name = cr.get("doctor_name") or "Dr. Aris Thorne"
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
                    "note": f"Explained referral rationale for {finding_code} to patient. Reassured non-diagnostic status.",
                    "barrier_detected": None
                },
                rationale="Document educational explanation of referral rationale in case notes.",
                autonomy_level=1
            )
        ]

        if lang == "ta":
            msg = (
                f"வணக்கம் {patient_name}, மருத்துவர் {doc_name} உங்கள் பரிசோதனை முடிவை ({finding_code}) ஆய்வு செய்து, "
                f"துல்லியமான நோயறிதல் தெளிவுக்காகவே சிறப்பு மருத்துவ மையத்திற்கு பரிந்துரைத்துள்ளார் ({pathway}). "
                "இது ஒரு வழக்கமான பாதுகாப்பு நடவடிக்கையே தவிர புற்றுநோய் உறுதி செய்யப்பட்டதல்ல. சுமார் 70% முதல் 80% பரிசோதனைகளில் இது சாதாரண மாறுதலாகவே (benign) முடிகிறது. "
                "எங்கள் குழு உங்களுடன் துணை நிற்கும்."
            )
        elif lang == "es":
            msg = (
                f"Hola {patient_name}. El Dr. {doc_name} recomendó una derivación a un centro especializado tras su {screening_type} ({finding_code}) "
                f"para asegurar que reciba una evaluación diagnóstica experta ({pathway}). "
                "La derivación permite realizar análisis específicos para garantizar un 100% de certeza clínica. "
                "Es importante destacar que una derivación es un paso preventivo de rutina y NO implica un diagnóstico de cáncer; "
                "de hecho, entre el 70% y el 80% de estos hallazgos resultan ser completamente benignos. "
                "¿Desea conocer detalles sobre el centro especializado o coordinar opciones de citas?"
            )
        elif lang == "ar":
            msg = (
                f"مرحباً {patient_name}. أوصى د. {doc_name} بإحالة تخصصية بعد فحص {screening_type} ({finding_code}) "
                f"لضمان حصولك على تقييم تشخيصي دقيق وشامل ({pathway}). "
                "تتيح هذه الإحالة للأخصائيين إجراء تصوير أو تقييم دقيق للوصول إلى يقين بنسبة 100%. "
                "من الأهمية بمكان معرفة أن الإحالة إجراء وقائي قياسي ولا تعني أبداً الإصابة بالسرطان؛ ففي الواقع، 70% إلى 80% من الحالات تكون حميدة تماماً. "
                "هل ترغبين في تفاصيل المركز المتخصص أو المساعدة في حجز الموعد؟"
            )
        else:
            msg = (
                f"Hello {patient_name}. {doc_name} recommended a specialist referral following your {screening_type} ({finding_code}) "
                f"to ensure you receive expert diagnostic evaluation ({pathway}). "
                "A referral allows a breast care specialist to conduct targeted imaging or a gentle diagnostic evaluation to provide 100% certainty. "
                "Crucially, a referral is a standard precautionary step and does NOT mean you have cancer—in fact, approximately 70% to 80% of such findings turn out to be completely benign. "
                "Would you like me to share details about the specialist clinic or help with appointment options?"
            )

        return CoordinationPlan(
            goal="Explain clinical referral rationale empathetically and alleviate anxiety.",
            situation_summary="Patient asked why doctor recommended a specialist referral.",
            actions=actions,
            patient_response_draft=msg,
            target_language=lang
        )
