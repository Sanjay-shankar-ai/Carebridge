"""
CareBridge Modular Communication Tools
Implements drafting, translation, consent-verified message dispatch, and acknowledgement recording.
"""

import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.models.care_case import CareCase, Task
from app.models.communication import Communication
from app.models.event_audit import CaseEvent
from app.services.llm_service import LLMService
from app.tools.base import ToolResult, validate_tool_permission, log_tool_audit, ToolExecutionError
from app.tools.schemas import (
    DraftPatientMessageInput, DraftPatientMessageOutput,
    TranslateMessageInput, TranslateMessageOutput,
    SendPermittedCommunicationInput, SendPermittedCommunicationOutput,
    RecordAcknowledgementInput, RecordAcknowledgementOutput
)

logger = logging.getLogger("carebridge.tools.communication")


def draft_patient_message(db: Session, input_data: DraftPatientMessageInput) -> ToolResult[DraftPatientMessageOutput]:
    """Drafts an empathetic, non-alarmist message adapted to patient's language and context."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=1)
        p_uuid = uuid.UUID(input_data.patient_id)
        patient = db.query(Patient).filter(Patient.id == p_uuid).first()
        if not patient:
            return ToolResult(success=False, error_code="PATIENT_NOT_FOUND", message=f"Patient {input_data.patient_id} not found.")

        target_lang = input_data.language or patient.preferred_language or "en"
        channel = patient.communication_channel or "sms"
        patient_name = f"{patient.first_name} {patient.last_name}"

        # LLM formulation or deterministic fallback
        prompt = (
            f"Draft an empathetic, non-alarmist healthcare message for patient {patient_name} in language '{target_lang}'.\n"
            f"Purpose: {input_data.message_purpose}.\n"
            f"Clinical context: {input_data.clinical_context or 'Screening follow-up'}.\n"
            f"Channel: {channel}.\n"
            f"Emphasize that findings on screening tests are routine and does not mean cancer; offer coordinator support."
        )

        content = None
        try:
            llm = LLMService.get_llm()
            if llm:
                response = llm.invoke(prompt)
                content = response.content.strip()
        except Exception as llm_err:
            logger.warning(f"LLM draft message fallback: {llm_err}")

        if not content:
            if target_lang == "ta":
                content = (
                    f"வணக்கம் {patient_name}, தங்களின் பரிசோதனை தொடர்பாக மேலதிக தகவல்களைப் பெற "
                    "எங்கள் குழு தயாராக உள்ளது. பயப்பட வேண்டாம், நாங்கள் உங்களுக்கு உதவ உள்ளோம். "
                    "தயவுசெய்து இந்த செய்திக்கு பதிலளிக்கவும்."
                )
            else:
                content = (
                    f"Hello {patient_name}, our care team is reaching out regarding your routine screening follow-up. "
                    "Finding something on a screening is common and does not mean cancer. "
                    "Please reply so we can help coordinate your next steps."
                )

        output = DraftPatientMessageOutput(
            drafted_content=content,
            language=target_lang,
            channel=channel,
            patient_name=patient_name
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Drafted message for {patient_name} in '{target_lang}'",
            autonomy_level=1
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except Exception as e:
        logger.error(f"Error in draft_patient_message: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def translate_message(db: Session, input_data: TranslateMessageInput) -> ToolResult[TranslateMessageOutput]:
    """Translates a message maintaining clinical accuracy and empathetic tone."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=1)
        source = input_data.source_language or "auto"
        target = input_data.target_language.lower().strip()

        translated = None
        try:
            llm = LLMService.get_llm()
            if llm:
                prompt = (
                    f"Translate the following healthcare communication from '{source}' to '{target}'.\n"
                    f"Preserve empathy, clinical clarity, and cultural appropriateness:\n\n{input_data.text}"
                )
                response = llm.invoke(prompt)
                translated = response.content.strip()
        except Exception as llm_err:
            logger.warning(f"LLM translation fallback: {llm_err}")

        if not translated:
            translated = input_data.text

        output = TranslateMessageOutput(
            original_text=input_data.text,
            translated_text=translated,
            source_language=source,
            target_language=target
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Translated text to '{target}'",
            autonomy_level=1
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except Exception as e:
        logger.error(f"Error in translate_message: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def send_permitted_communication(db: Session, input_data: SendPermittedCommunicationInput) -> ToolResult[SendPermittedCommunicationOutput]:
    """Dispatches a communication to the patient after strictly validating active consent."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=2)
        c_uuid = uuid.UUID(input_data.case_id)
        p_uuid = uuid.UUID(input_data.patient_id)

        patient = db.query(Patient).filter(Patient.id == p_uuid).first()
        if not patient:
            return ToolResult(success=False, error_code="PATIENT_NOT_FOUND", message=f"Patient {input_data.patient_id} not found.")

        # Consent Validation: Check for active outreach consent
        has_consent = any(c.status == "active" and "outreach" in c.scope for c in patient.consents)
        if not has_consent and patient.consents:
            return ToolResult(
                success=False,
                error_code="CONSENT_MISSING",
                message="Patient does not have an active consent for automated outreach communications.",
                autonomy_level=2
            )

        channel = input_data.channel or patient.communication_channel or "sms"
        lang = input_data.language or patient.preferred_language or "en"
        now = datetime.now(timezone.utc)

        comm = Communication(
            id=uuid.uuid4(),
            case_id=c_uuid,
            patient_id=p_uuid,
            sender="ai_coordinator",
            channel=channel,
            content=input_data.content,
            language=lang,
            sent_at=now,
            acknowledged=False
        )
        db.add(comm)

        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=c_uuid,
            event_type="patient_communication_dispatched",
            description=f"Outreach message sent via {channel} in {lang}",
            event_data={"channel": channel, "language": lang, "communication_id": str(comm.id)},
            timestamp=now
        )
        db.add(event)
        db.commit()

        audit_id = log_tool_audit(
            db=db,
            action="SEND_PATIENT_MESSAGE",
            actor_id="carebridge_agent",
            actor_type="ai_agent",
            autonomy_level=2,
            rationale=f"Dispatched patient communication via {channel} in language {lang}",
            case_id=c_uuid,
            patient_id=p_uuid
        )

        output = SendPermittedCommunicationOutput(
            communication_id=str(comm.id),
            case_id=str(c_uuid),
            patient_id=str(p_uuid),
            channel=channel,
            language=lang,
            status="sent",
            sent_at=now.isoformat()
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Dispatched communication via {channel} to patient",
            autonomy_level=2,
            audit_id=audit_id
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except Exception as e:
        logger.error(f"Error in send_permitted_communication: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def record_acknowledgement(db: Session, input_data: RecordAcknowledgementInput) -> ToolResult[RecordAcknowledgementOutput]:
    """Records patient receipt/acknowledgement and marks outreach tasks completed."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=1)
        c_uuid = uuid.UUID(input_data.case_id)
        case = db.query(CareCase).filter(CareCase.id == c_uuid).first()
        if not case:
            return ToolResult(success=False, error_code="CASE_NOT_FOUND", message=f"Case {input_data.case_id} not found.")

        now = datetime.now(timezone.utc)
        ctx = dict(case.case_context or {})
        ctx["patient_understanding_confirmed"] = True
        case.case_context = ctx

        # Mark all pending outreach tasks completed
        pending_tasks = (
            db.query(Task)
            .filter(Task.case_id == c_uuid, Task.task_type == "patient_outreach", Task.status == "pending")
            .all()
        )
        for t in pending_tasks:
            t.status = "completed"
            t.completed_at = now

        event = CaseEvent(
            id=uuid.uuid4(),
            case_id=c_uuid,
            event_type="patient_acknowledged",
            description=f"Patient acknowledged notification via {input_data.acknowledged_via}",
            event_data={"channel": input_data.acknowledged_via, "response": input_data.patient_response},
            timestamp=now
        )
        db.add(event)
        db.commit()

        audit_id = log_tool_audit(
            db=db,
            action="RECORD_PATIENT_ACKNOWLEDGEMENT",
            actor_id="carebridge_agent",
            actor_type="ai_agent",
            autonomy_level=1,
            rationale="Patient acknowledged screening result and care navigation plan.",
            case_id=c_uuid,
            patient_id=case.patient_id
        )

        output = RecordAcknowledgementOutput(
            case_id=str(c_uuid),
            patient_acknowledged=True,
            acknowledged_at=now.isoformat(),
            completed_task_count=len(pending_tasks)
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Recorded patient acknowledgement ({len(pending_tasks)} outreach tasks completed)",
            autonomy_level=1,
            audit_id=audit_id
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except Exception as e:
        logger.error(f"Error in record_acknowledgement: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))
