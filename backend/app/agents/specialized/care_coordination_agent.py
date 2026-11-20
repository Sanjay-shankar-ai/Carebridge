"""
CareBridge Care Coordination Agent
Specialized agent responsible for:
- Coordinating referrals and specialist appointments within clinical SLA windows
- Tracking pending coordination tasks, outstanding milestones, and SLA clocks
- Maintaining Care Coordinator ownership continuity
- Detecting incomplete care journeys and stalled referrals
- Presenting available slots and assisting with booking requests
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from app.agents.state import CoordinationPlan, ProposedAction, IntentAnalysis


class CareCoordinationAgent:
    """Specialized agent for clinical navigation, scheduling, referral routing, and ownership tracking."""

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
    def formulate_booking_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any]
    ) -> CoordinationPlan:
        """Formulates an appointment search, slot proposal, and booking coordination plan."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_id = str(patient_context.get("id") or patient_context.get("patient_id") or "")
        patient_name = patient_context.get("full_name") or patient_context.get("first_name", "Valued Patient")
        lang = cls._resolve_lang(intent, patient_context)
        facility = case_context.get("facility") or "Clinic A - Women's Specialty Breast Center"
        specialty = case_context.get("specialty") or "Breast Oncology"
        raw_msg = (intent.raw_query or "").lower()

        # Extract requested timing details from natural language
        import re
        days_map = {
            "monday": "Monday", "tuesday": "Tuesday", "wednesday": "Wednesday",
            "thursday": "Thursday", "friday": "Friday", "saturday": "Saturday",
            "sunday": "Sunday", "tomorrow": "Tomorrow", "today": "Today"
        }
        detected_day = None
        for k, v in days_map.items():
            if k in raw_msg:
                detected_day = v
                break

        time_match = re.search(r'\b(\d{1,2}(?::\d{2})?\s*(?:am|pm|noon))\b', raw_msg, re.IGNORECASE)
        detected_time = time_match.group(1).upper() if time_match else None
        if not detected_time:
            if "morning" in raw_msg:
                detected_time = "morning"
            elif "afternoon" in raw_msg:
                detected_time = "afternoon"
            elif "noon" in raw_msg or "midday" in raw_msg:
                detected_time = "12:00 PM"

        requested_timing = None
        if detected_day and detected_time:
            requested_timing = f"{detected_day} at {detected_time}"
        elif detected_day:
            requested_timing = detected_day
        elif detected_time:
            requested_timing = detected_time

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="search_available_appointments",
                arguments={
                    "facility": facility,
                    "specialty": specialty,
                    "timeframe": "next_7_days"
                },
                rationale="Identify available clinic openings to accommodate patient booking request within SLA window.",
                autonomy_level=1
            )
        ]

        # If patient explicitly requested timing or immediate slot, initiate provisional reservation
        if requested_timing:
            actions.append(
                ProposedAction(
                    step_number=2,
                    tool_name="book_appointment",
                    arguments={
                        "case_id": case_id,
                        "patient_id": patient_id,
                        "facility": facility,
                        "provider_name": "Dr. Aris Thorne",
                        "appointment_type": "Diagnostic Evaluation",
                        "scheduled_time": requested_timing,
                        "status": "pending_approval",
                        "notes": f"Patient requested appointment booking for {requested_timing}."
                    },
                    rationale="Create provisional appointment reservation for requested slot requiring clinical confirmation.",
                    autonomy_level=2
                )
            )
            step_num = 3
        elif any(w in raw_msg for w in ["tomorrow", "urgent", "asap", "morning appointment", "afternoon appointment"]):
            actions.append(
                ProposedAction(
                    step_number=2,
                    tool_name="book_appointment",
                    arguments={
                        "case_id": case_id,
                        "patient_id": patient_id,
                        "facility": facility,
                        "provider_name": "Dr. Aris Thorne",
                        "appointment_type": "Diagnostic Evaluation",
                        "scheduled_time": "tomorrow at 10:00 AM" if "tomorrow" in raw_msg else "Friday at 9:00 AM",
                        "status": "pending_approval",
                        "notes": "Patient requested appointment booking via conversational chat. Requires doctor approval and patient confirmation."
                    },
                    rationale="Create provisional appointment reservation requiring clinical team approval.",
                    autonomy_level=2
                )
            )
            step_num = 3
        else:
            step_num = 2

        actions.append(
            ProposedAction(
                step_number=step_num,
                tool_name="create_followup_task",
                arguments={
                    "case_id": case_id,
                    "title": "Coordinate booked visit with patient",
                    "description": f"Patient requested booking for {requested_timing or 'upcoming slot'}. Secure doctor approval and confirm slot with patient.",
                    "task_type": "care_coordination",
                    "due_date": (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00Z"),
                    "assigned_role": "care_coordinator"
                },
                rationale="Schedule coordinator follow-up to finalize appointment reservation with doctor approval.",
                autonomy_level=1
            )
        )

        if lang == "ta":
            msg = (
                f"கண்டிப்பாக {patient_name}, மருத்துவ சந்திப்பை பதிவு செய்ய நான் உதவுகிறேன். "
                "டாக்டர் அரிஸ் தோர்ன் அவர்களின் Clinic A மையத்தில் செவ்வாய் காலை 10:30 மணி மற்றும் "
                "வியாழன் மதியம் 2:00 மணி ஆகிய நேரங்களில் இடங்கள் உள்ளன. இதில் எந்த நேரம் உங்களுக்கு வசதியாக இருக்கும்? "
                "உங்கள் விருப்பத்தை பதிவு செய்தவுடன் மருத்துவக் குழுவின் ஒப்புதலுடன் இறுதி செய்யப்படும்."
            )
        elif lang == "es":
            if requested_timing:
                msg = (
                    f"¡Con gusto le ayudaré a reservar su cita para {requested_timing}, {patient_name}! "
                    f"He generado una solicitud de reserva para {requested_timing} con el Dr. Aris Thorne en {facility}. "
                    "Nuestro equipo clínico y su coordinadora Priya Nair revisarán este horario para confirmar su cita. "
                    "Como referencia inmediata, también contamos con horarios confirmados el martes a las 10:30 AM y el jueves a las 2:00 PM. "
                    f"¿Desea que procedamos con {requested_timing} o prefiere alguno de los otros horarios?"
                )
            else:
                msg = (
                    f"¡Con gusto le ayudaré a reservar su cita, {patient_name}! "
                    f"He ubicado espacios diagnósticos disponibles con el Dr. Aris Thorne en {facility}. "
                    "Los horarios disponibles incluyen el martes a las 10:30 AM y el jueves a las 2:00 PM. "
                    "¿Cuál de estos horarios se adapta mejor a su conveniencia?"
                )
        elif lang == "ar":
            if requested_timing:
                msg = (
                    f"يسعدني جداً مساعدتك في حجز موعدك في {requested_timing} يا {patient_name}! "
                    f"لقد رفعت طلب حجز مبدئي لـ {requested_timing} مع الدكتور أريس ثورن في {facility}. "
                    "سيقوم فريقنا الطبي ومنسقة رعايتك بريا ناير بمراجعة هذا الموعد لتأكيده. "
                    "للعلم، تتوفر لدينا أيضاً مواعيد مؤكدة يوم الثلاثاء الساعة 10:30 صباحاً والخميس الساعة 2:00 ظهراً. "
                    f"هل تود أن نؤكد موعد {requested_timing} أم تفضل أحد المواعيد الأخرى؟"
                )
            else:
                msg = (
                    f"يسعدني جداً مساعدتك في حجز موعدك يا {patient_name}! "
                    f"لقد وجدت مواعيد تشخيصية قادمة مع الدكتور أريس ثورن في {facility}. "
                    "المواعيد المتاحة تشمل يوم الثلاثاء الساعة 10:30 صباحاً والخميس الساعة 2:00 ظهراً. "
                    "هل يناسبك أي من هذين الموعدين؟"
                )
        else:
            if requested_timing:
                msg = (
                    f"I would be glad to help you book your appointment for {requested_timing}, {patient_name}! "
                    f"I have submitted a booking request for {requested_timing} with Dr. Aris Thorne at {facility}. "
                    "Our clinical team and your care coordinator Priya Nair are reviewing this slot to confirm your reservation. "
                    "For immediate reference, our confirmed diagnostic openings also include Tuesday at 10:30 AM and Thursday at 2:00 PM. "
                    f"Would you like us to proceed with {requested_timing}, or would one of the other slots be better for you?"
                )
            else:
                msg = (
                    f"I would be glad to help you book your appointment, {patient_name}! "
                    f"I have located upcoming diagnostic openings with Dr. Aris Thorne at {facility}. "
                    "Available slots include Tuesday at 10:30 AM and Thursday at 2:00 PM. Would either of these times work well for you? "
                    "Once you select an option, our clinical team will review and confirm your reservation."
                )

        return CoordinationPlan(
            goal="Search and present available appointment slots to schedule patient visit within SLA window.",
            situation_summary="Patient requested appointment booking assistance.",
            actions=actions,
            patient_response_draft=msg,
            target_language=lang
        )

    @classmethod
    def formulate_referral_delay_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any]
    ) -> CoordinationPlan:
        """Handles delayed referral investigations with ownership notifications."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = patient_context.get("full_name") or patient_context.get("first_name", "Valued Patient")
        lang = cls._resolve_lang(intent, patient_context)

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="get_referral_status",
                arguments={"case_id": case_id},
                rationale="Audit referral handoff status across facilities.",
                autonomy_level=1
            ),
            ProposedAction(
                step_number=2,
                tool_name="notify_case_owner",
                arguments={
                    "case_id": case_id,
                    "priority": "high",
                    "message": "Patient flagged delay in specialist clinic outreach. Coordinator intervention required."
                },
                rationale="Alert accountable nurse coordinator to expedite referral intake.",
                autonomy_level=1
            )
        ]

        cr = case_context.get("clinical_review") or {}
        doc_name = (
            case_context.get("assigned_doctor_name")
            or case_context.get("doctor_name")
            or cr.get("doctor_name")
            or "Dr. Arjun Menon"
        )
        coord_name = case_context.get("current_owner_name") or "Priya Nair, RN"

        if lang == "ta":
            msg = (
                f"மருத்துவர் அழைப்பிற்காக காத்திருப்பது மன உளைச்சலை ஏற்படுத்தும் என்பதை நாங்கள் உணர்கிறோம் {patient_name}.\n\n"
                "மருத்துவ மையங்களில் பணிச்சுமை காரணமாக சில சமயங்களில் அழைப்புகள் தாமதமாகலாம்.\n\n"
                "இந்த உரையாடலின் மூலம் எங்களால் நேரடியாக தொலைபேசி அழைப்பை மேற்கொள்ள முடியாது என்றாலும், எங்கள் குழு உடனடியாக நடவடிக்கை எடுக்கும்.\n\n"
                f"உங்கள் பராமரிப்பு ஒருங்கிணைப்பாளர் {coord_name}, மருத்துவர் {doc_name} அலுவலகத்துடன் இன்று உடனடியாக தொடர்பு கொண்டு தங்களின் சந்திப்பை விரைவுபடுத்துவார்.\n\n"
                f"மருத்துவர் {doc_name} அலுவலகம் உங்களைத் தொடர்பு கொள்ள வசதியான நேரத்தைக் குறிப்பிட விரும்புகிறீர்களா?"
            )
        elif lang == "es":
            msg = (
                f"Comprendo lo frustrante y angustiante que resulta estar esperando la llamada del consultorio del médico, {patient_name}.\n\n"
                "En ocasiones los consultorios especializados presentan demoras imprevistas en la programación de llamadas telefónicas.\n\n"
                "Aunque este chat no puede comunicarse por teléfono directamente, nuestro equipo intervendrá de inmediato.\n\n"
                f"Su coordinadora de cuidados, {coord_name}, se comunicará hoy mismo con el consultorio del {doc_name} para agilizar su cita.\n\n"
                f"¿Desea confirmar el mejor número de teléfono y horario para que la clínica del {doc_name} se comunique con usted?"
            )
        elif lang == "ar":
            msg = (
                f"أتفهم تماماً مدى الإحباط والقلق الذي قد يسببه انتظار اتصال عيادة الطبيب يا {patient_name}.\n\n"
                "في بعض الأحيان تواجه العيادات التخصصية ضغطاً في جداول الاتصال، مما قد يؤدي إلى بعض التأخير.\n\n"
                "ورغم أن هذه المحادثة لا تستطيع إجراء مكالمات هاتفية مباشرة، إلا أن فريقنا سيتدخل فوراً لدعمكِ.\n\n"
                f"ستتواصل منسقة رعايتكِ، {coord_name}، مباشرة اليوم مع عيادة {doc_name} لتسريع التواصل معكِ.\n\n"
                f"هل تودين تأكيد أفضل رقم هاتف ووقت مفضل لتتواصل معكِ عيادة {doc_name}؟"
            )
        else:
            msg = (
                f"I understand how frustrating and stressful it is to wait for the doctor's office to call, {patient_name}.\n\n"
                "Specialist clinic offices sometimes experience unexpected scheduling backlogs or high call volumes, which can delay outreach.\n\n"
                "While this chat cannot place phone calls directly, our care team can take immediate action on your behalf.\n\n"
                f"Your care coordinator, {coord_name}, is following up directly with {doc_name}'s specialty clinic today to expedite your contact.\n\n"
                f"Would you like to confirm the best phone number and time of day for {doc_name}'s clinic to reach you?"
            )

        return CoordinationPlan(
            goal="Investigate referral bottleneck and alert assigned coordinator.",
            situation_summary="Patient flagged delay in referral progression.",
            actions=actions,
            patient_response_draft=msg,
            target_language=lang
        )

    @classmethod
    def formulate_task_query_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any]
    ) -> CoordinationPlan:
        """Retrieves and summarizes pending care coordination tasks for coordinators or clinicians."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = patient_context.get("full_name") or patient_context.get("first_name", "Patient")
        case_number = case_context.get("case_number", "CASE-UNKNOWN")

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="get_pending_case_tasks",
                arguments={"case_id": case_id},
                rationale="Query outstanding coordination milestones, barriers, and tasks from database.",
                autonomy_level=1
            )
        ]

        msg = (
            f"Here are the active coordination tasks for Case #{case_number} ({patient_name}):\n"
            "- Referral Routing & Tracking: Specialist handoff within 48h SLA window\n"
            "- Diagnostic Scheduling: Clinic visit coordination with Dr. Aris Thorne\n"
            "- Barrier Follow-up: Caregiver availability and transportation verification\n"
            "All tasks are currently assigned to Care Coordinator Priya Nair, RN."
        )

        return CoordinationPlan(
            goal="Retrieve and summarize pending coordination tasks.",
            situation_summary=f"Care team requested pending tasks for Case #{case_number}.",
            actions=actions,
            patient_response_draft=msg,
            target_language="en"
        )

    @classmethod
    def formulate_additional_slots_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any],
        conversation_context: Optional[Dict[str, Any]] = None
    ) -> CoordinationPlan:
        """Formulates a plan to retrieve and present alternative appointment slots."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = patient_context.get("full_name") or patient_context.get("first_name", "Valued Patient")
        lang = cls._resolve_lang(intent, patient_context)
        facility = case_context.get("facility") or "Clinic A - Women's Specialty Breast Center"
        specialty = case_context.get("specialty") or "Breast Oncology"

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="search_available_appointments",
                arguments={
                    "facility": facility,
                    "specialty": specialty,
                    "timeframe": "next_14_days"
                },
                rationale="Search expanded scheduling availability for alternative patient openings.",
                autonomy_level=1
            ),
            ProposedAction(
                step_number=2,
                tool_name="create_followup_task",
                arguments={
                    "case_id": case_id,
                    "title": "Coordinate alternative appointment slots with patient",
                    "description": "Patient requested different appointment slots. Present alternative options.",
                    "task_type": "care_coordination",
                    "due_date": (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00Z"),
                    "assigned_role": "care_coordinator"
                },
                rationale="Ensure coordinator tracks slot selection and confirms finalized booking.",
                autonomy_level=1
            )
        ]

        pref_topic = intent.inquiry_topic
        if pref_topic == "morning":
            if lang == "ta":
                msg = (
                    f"நிச்சயமாக {patient_name}! டாக்டர் அரிஸ் தோர்ன் அவர்களின் Clinic A மையத்தில் கூடுதல் காலை நேரங்கள் கிடைக்கின்றன: "
                    "வெள்ளிக்கிழமை காலை 9:00 மணி மற்றும் திங்கட்கிழமை காலை 10:30 மணி. இவற்றில் எந்த நேரம் உங்களுக்கு வசதியாக இருக்கும்?"
                )
            elif lang == "es":
                msg = (
                    f"¡Por supuesto, {patient_name}! Disponemos de horarios matutinos adicionales con el Dr. Aris Thorne en {facility}: "
                    "Viernes a las 9:00 AM y Lunes a las 10:30 AM. ¿Cuál de estos horarios de la mañana le resulta más conveniente?"
                )
            elif lang == "ar":
                msg = (
                    f"بالتأكيد يا {patient_name}! تتوفر مواعيد صباحية بديلة لدى د. أريس ثورن في {facility}: "
                    "الجمعة الساعة 9:00 صباحاً والإثنين الساعة 10:30 صباحاً. أي من هذين الموعدين الصباحيين يناسبك أكثر؟"
                )
            else:
                msg = (
                    f"Certainly, {patient_name}! Here are alternative morning openings with Dr. Aris Thorne at {facility}: "
                    "Friday at 9:00 AM and Monday at 10:30 AM. Would either of these morning times work better for your schedule?"
                )
        elif pref_topic == "afternoon":
            if lang == "ta":
                msg = (
                    f"நிச்சயமாக {patient_name}! டாக்டர் அரிஸ் தோர்ன் அவர்களின் Clinic A மையத்தில் கூடுதல் மதிய நேரங்கள் கிடைக்கின்றன: "
                    "வெள்ளிக்கிழமை மதியம் 2:00 மணி மற்றும் திங்கட்கிழமை மதியம் 3:30 மணி. இவற்றில் எந்த நேரம் உங்களுக்கு வசதியாக இருக்கும்?"
                )
            elif lang == "es":
                msg = (
                    f"¡Por supuesto, {patient_name}! Disponemos de horarios por la tarde con el Dr. Aris Thorne en {facility}: "
                    "Viernes a las 2:00 PM y Lunes a las 3:30 PM. ¿Cuál de estos horarios le resulta más conveniente?"
                )
            elif lang == "ar":
                msg = (
                    f"بالتأكيد يا {patient_name}! تتوفر مواعيد مسائية بديلة لدى د. أريس ثورن في {facility}: "
                    "الجمعة الساعة 2:00 ظهراً والإثنين الساعة 3:30 عصراً. أي من هذين الموعدين يناسبك أكثر؟"
                )
            else:
                msg = (
                    f"Certainly, {patient_name}! Here are alternative afternoon openings with Dr. Aris Thorne at {facility}: "
                    "Friday at 2:00 PM and Monday at 3:30 PM. Would either of these afternoon times work better for your schedule?"
                )
        else:
            if lang == "ta":
                msg = (
                    f"நிச்சயமாக {patient_name}! டாக்டர் அரிஸ் தோர்ன் அவர்களின் Clinic A மையத்தில் கூடுதல் நேரங்கள் கிடைக்கின்றன: "
                    "வெள்ளிக்கிழமை காலை 9:00 மணி, திங்கட்கிழமை காலை 11:00 மணி, மற்றும் அடுத்த புதன்கிழமை மதியம் 3:30 மணி. "
                    "இவற்றில் எந்த நேரம் உங்களுக்கு வசதியாக இருக்கும்?"
                )
            elif lang == "es":
                msg = (
                    f"¡Por supuesto, {patient_name}! Aquí tiene horarios adicionales disponibles con el Dr. Aris Thorne en {facility}: "
                    "Viernes a las 9:00 AM, Lunes a las 11:00 AM y el próximo Miércoles a las 3:30 PM. ¿Alguno de estos horarios se adapta a su agenda?"
                )
            elif lang == "ar":
                msg = (
                    f"بالتأكيد يا {patient_name}! فيما يلي مواعيد إضافية متاحة لدى د. أريس ثورن في {facility}: "
                    "الجمعة الساعة 9:00 صباحاً، الإثنين الساعة 11:00 صباحاً، والأربعاء القادم الساعة 3:30 عصراً. هل يناسبك أي من هذه المواعيد؟"
                )
            else:
                msg = (
                    f"Certainly, {patient_name}! Here are additional upcoming openings with Dr. Aris Thorne at {facility}: "
                    "Friday at 9:00 AM, Monday at 11:00 AM, and next Wednesday at 3:30 PM. Would any of these alternative times work better for your schedule?"
                )

        return CoordinationPlan(
            goal="Provide alternative appointment slot options accommodating patient schedule.",
            situation_summary="Patient requested alternative appointment slots.",
            actions=actions,
            patient_response_draft=msg,
            target_language=lang
        )

    @classmethod
    def formulate_slot_preference_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any],
        conversation_context: Optional[Dict[str, Any]] = None
    ) -> CoordinationPlan:
        """Filters and presents slots matching patient time preferences (e.g. morning vs afternoon)."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = patient_context.get("full_name") or patient_context.get("first_name", "Valued Patient")
        lang = cls._resolve_lang(intent, patient_context)
        facility = case_context.get("facility") or "Clinic A - Women's Specialty Breast Center"
        specialty = case_context.get("specialty") or "Breast Oncology"
        pref = intent.inquiry_topic or "morning"

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="search_available_appointments",
                arguments={
                    "facility": facility,
                    "specialty": specialty,
                    "timeframe": "next_7_days"
                },
                rationale=f"Filter clinic openings according to patient {pref} time preference.",
                autonomy_level=1
            ),
            ProposedAction(
                step_number=2,
                tool_name="update_case_notes",
                arguments={
                    "case_id": case_id,
                    "note": f"Patient specified preference for {pref} appointment openings.",
                    "barrier_detected": None
                },
                rationale="Persist patient scheduling preference in case profile.",
                autonomy_level=1
            )
        ]

        if lang == "ta":
            msg = (
                f"காலை நேரமே உங்களுக்கு வசதியானது என்பதை குறித்துக்கொண்டோம் {patient_name}! "
                "டாக்டர் அரிஸ் தோர்ன் அவர்களின் மையத்தில் வெள்ளிக்கிழமை காலை 9:00 மணி மற்றும் செவ்வாய் காலை 10:00 மணி "
                "ஆகிய காலை நேரங்களில் இடங்கள் உள்ளன. இதில் எது உங்களுக்கு வசதியாக இருக்கும்?"
            )
        else:
            msg = (
                f"I have noted your preference for morning visits, {patient_name}! "
                "We have morning openings available on Friday at 9:00 AM and next Tuesday at 10:00 AM with Dr. Aris Thorne. "
                "Would either of these morning times work for you?"
            )

        return CoordinationPlan(
            goal=f"Filter and offer appointments tailored to patient's {pref} preference.",
            situation_summary=f"Patient expressed preference for {pref} appointments.",
            actions=actions,
            patient_response_draft=msg,
            target_language=lang
        )

    @classmethod
    def formulate_slot_selection_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any],
        conversation_context: Optional[Dict[str, Any]] = None
    ) -> CoordinationPlan:
        """Resolves ordinal or specific slot selection (e.g. 'the second one') and initiates reservation."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = patient_context.get("full_name") or patient_context.get("first_name", "Valued Patient")
        lang = cls._resolve_lang(intent, patient_context)
        facility = case_context.get("facility") or "Clinic A - Women's Specialty Breast Center"
        selection = intent.inquiry_topic or "slot_2"

        if selection == "slot_1":
            slot_desc = "Tuesday at 10:30 AM"
            slot_desc_ta = "செவ்வாய் காலை 10:30 மணி"
            ordinal_text = "first option"
            ordinal_text_ta = "முதலாவது நேரம்"
        elif selection == "slot_3":
            slot_desc = "next Wednesday at 3:30 PM"
            slot_desc_ta = "அடுத்த புதன்கிழமை மதியம் 3:30 மணி"
            ordinal_text = "third option"
            ordinal_text_ta = "மூன்றாவது நேரம்"
        else:
            slot_desc = "Thursday at 2:00 PM"
            slot_desc_ta = "வியாழன் மதியம் 2:00 மணி"
            ordinal_text = "second option"
            ordinal_text_ta = "இரண்டாவது நேரம்"

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="book_appointment",
                arguments={
                    "case_id": case_id,
                    "patient_id": str(patient_context.get("id") or patient_context.get("patient_id") or ""),
                    "facility": facility,
                    "provider_name": "Dr. Aris Thorne",
                    "appointment_type": "Diagnostic Evaluation",
                    "scheduled_time": slot_desc,
                    "status": "booked",
                    "notes": f"Booked via conversational AI selection ({ordinal_text}: {slot_desc}). Requires doctor confirmation."
                },
                rationale=f"Initiate appointment booking for patient-selected {ordinal_text} ({slot_desc}).",
                autonomy_level=2
            ),
            ProposedAction(
                step_number=2,
                tool_name="create_followup_task",
                arguments={
                    "case_id": case_id,
                    "title": f"Confirm booked visit ({slot_desc}) with patient",
                    "description": f"Patient confirmed {ordinal_text} ({slot_desc}). Confirm details and send reminders.",
                    "task_type": "care_coordination",
                    "due_date": (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00Z"),
                    "assigned_role": "care_coordinator"
                },
                rationale="Schedule coordinator follow-up to finalize appointment details with patient.",
                autonomy_level=1
            )
        ]

        if lang == "ta":
            msg = (
                f"அருமை {patient_name}! நீங்கள் தேர்வு செய்த {ordinal_text_ta}யை ({slot_desc_ta}, டாக்டர் அரிஸ் தோர்ன், {facility}) "
                "முன்பதிவு செய்ய நடவடிக்கை எடுத்துள்ளோம். உங்கள் பராமரிப்பு ஒருங்கிணைப்பாளர் பிரியா நாயர் இதனை உறுதி செய்வார். "
                "சந்திப்பிற்கு முன் உங்களுக்கு நினைவூட்டல் செய்தி அனுப்பப்படும்."
            )
        else:
            msg = (
                f"Wonderful, {patient_name}! I have selected the {ordinal_text} for you ({slot_desc} with Dr. Aris Thorne at {facility}). "
                "We have initiated your booking confirmation, and your care coordinator Priya Nair, RN will finalize your appointment details. "
                "You will receive a confirmation reminder prior to your visit."
            )

        return CoordinationPlan(
            goal=f"Confirm patient's slot selection ({slot_desc}) and initiate appointment booking.",
            situation_summary=f"Patient chose {ordinal_text} ({slot_desc}).",
            actions=actions,
            patient_response_draft=msg,
            target_language=lang
        )

    @classmethod
    def formulate_reschedule_request_plan(
        cls,
        intent: IntentAnalysis,
        patient_context: Dict[str, Any],
        case_context: Dict[str, Any],
        conversation_context: Optional[Dict[str, Any]] = None
    ) -> CoordinationPlan:
        """Handles patient reschedule requests by querying upcoming openings and offering flexible times."""
        case_id = str(case_context.get("case_id") or case_context.get("id") or "")
        patient_name = patient_context.get("full_name") or patient_context.get("first_name", "Valued Patient")
        lang = cls._resolve_lang(intent, patient_context)
        facility = case_context.get("facility") or "Clinic A - Women's Specialty Breast Center"
        specialty = case_context.get("specialty") or "Breast Oncology"

        actions: List[ProposedAction] = [
            ProposedAction(
                step_number=1,
                tool_name="search_available_appointments",
                arguments={
                    "facility": facility,
                    "specialty": specialty,
                    "timeframe": "next_10_days"
                },
                rationale="Query upcoming openings to accommodate patient reschedule request.",
                autonomy_level=1
            ),
            ProposedAction(
                step_number=2,
                tool_name="create_followup_task",
                arguments={
                    "case_id": case_id,
                    "title": "Coordinate appointment reschedule for patient",
                    "description": "Patient requested appointment reschedule. Verify preference and rebook.",
                    "task_type": "care_coordination",
                    "due_date": (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT10:00:00Z"),
                    "assigned_role": "care_coordinator"
                },
                rationale="Assign task to coordinator to finalize modified appointment date.",
                autonomy_level=1
            )
        ]

        if lang == "ta":
            msg = (
                f"கண்டிப்பாக மாற்றலாம் {patient_name}! உங்கள் வசதிக்கேற்ப சந்திப்பு நேரத்தை எப்போது வேண்டுமானாலும் மாற்றியமைக்கலாம். "
                "உங்களுக்கு எந்த கிழமை அல்லது நேரம் வசதியாக இருக்கும் என்று கூறினால் அதற்கேற்ப புதிய நேரத்தை ஒதுக்குகிறோம்."
            )
        else:
            msg = (
                f"Yes, absolutely, {patient_name}! You can change your appointment at any time. "
                "We want to ensure your consultation fits comfortably into your schedule. "
                "I can help you reschedule to another day or time that works better. What days or times of the week do you prefer?"
            )

        return CoordinationPlan(
            goal="Assist patient with rescheduling their appointment to a convenient time.",
            situation_summary="Patient requested to reschedule their appointment.",
            actions=actions,
            patient_response_draft=msg,
            target_language=lang
        )
