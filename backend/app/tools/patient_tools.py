"""
CareBridge Modular Patient Tools
Implements patient profile, preferences, and conversation history retrieval tools.
"""

import uuid
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.models.communication import Communication, ConversationSession
from app.tools.base import ToolResult, validate_tool_permission, ToolExecutionError
from app.tools.schemas import (
    RetrievePatientProfileInput, PatientProfileOutput,
    RetrievePatientPreferencesInput, PatientPreferencesOutput,
    RetrieveConversationHistoryInput, ConversationHistoryOutput, MessageItem
)

logger = logging.getLogger("carebridge.tools.patient")


def retrieve_patient_profile(db: Session, input_data: RetrievePatientProfileInput) -> ToolResult[PatientProfileOutput]:
    """Retrieves full demographic, clinical context, and barrier profile for a patient."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=1)
        p_uuid = uuid.UUID(input_data.patient_id)
        patient = db.query(Patient).filter(Patient.id == p_uuid).first()
        if not patient:
            return ToolResult(
                success=False,
                error_code="PATIENT_NOT_FOUND",
                message=f"Patient {input_data.patient_id} not found."
            )

        ctx = patient.patient_context or {}
        barriers = list(ctx.get("known_barriers", []))

        output = PatientProfileOutput(
            patient_id=str(patient.id),
            mrn=patient.mrn,
            first_name=patient.first_name,
            last_name=patient.last_name,
            date_of_birth=patient.date_of_birth.isoformat() if patient.date_of_birth else None,
            gender=patient.gender,
            phone=patient.phone,
            email=patient.email,
            preferred_language=patient.preferred_language,
            communication_channel=patient.communication_channel,
            accessibility_requirements=patient.accessibility_requirements or {},
            known_barriers=barriers
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Retrieved profile for {patient.first_name} {patient.last_name} ({patient.mrn})",
            autonomy_level=1
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except ValueError as ve:
        return ToolResult(success=False, error_code="INVALID_UUID", message=f"Invalid patient_id: {ve}")
    except Exception as e:
        logger.error(f"Error in retrieve_patient_profile: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def retrieve_patient_preferences(db: Session, input_data: RetrievePatientPreferencesInput) -> ToolResult[PatientPreferencesOutput]:
    """Retrieves communication preferences, preferred language, accessibility needs, and consents."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=1)
        p_uuid = uuid.UUID(input_data.patient_id)
        patient = db.query(Patient).filter(Patient.id == p_uuid).first()
        if not patient:
            return ToolResult(
                success=False,
                error_code="PATIENT_NOT_FOUND",
                message=f"Patient {input_data.patient_id} not found."
            )

        ctx = patient.patient_context or {}
        active_consents = [c.scope for c in patient.consents if c.status == "active"]

        output = PatientPreferencesOutput(
            patient_id=str(patient.id),
            preferred_language=patient.preferred_language,
            communication_channel=patient.communication_channel,
            accessibility_requirements=patient.accessibility_requirements or {},
            caregiver_name=ctx.get("caregiver_name"),
            caregiver_phone=ctx.get("caregiver_phone"),
            active_consents=active_consents
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Retrieved preferences for patient {patient.mrn}",
            autonomy_level=1
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except ValueError as ve:
        return ToolResult(success=False, error_code="INVALID_UUID", message=f"Invalid patient_id: {ve}")
    except Exception as e:
        logger.error(f"Error in retrieve_patient_preferences: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))


def retrieve_conversation_history(db: Session, input_data: RetrieveConversationHistoryInput) -> ToolResult[ConversationHistoryOutput]:
    """Retrieves previous communications, messages, and conversation summaries for a patient."""
    try:
        validate_tool_permission(input_data.actor_role, autonomy_level=1)
        p_uuid = uuid.UUID(input_data.patient_id)

        query = db.query(Communication).filter(Communication.patient_id == p_uuid)
        if input_data.case_id:
            c_uuid = uuid.UUID(input_data.case_id)
            query = query.filter(Communication.case_id == c_uuid)

        communications = query.order_by(Communication.created_at.desc()).limit(input_data.limit).all()

        message_items = [
            MessageItem(
                id=str(c.id),
                sender=c.sender,
                channel=c.channel,
                content=c.content,
                translated_content=c.translated_content,
                language=c.language,
                sent_at=c.sent_at.isoformat() if c.sent_at else c.created_at.isoformat(),
                acknowledged=c.acknowledged
            )
            for c in communications
        ]

        # Retrieve active session summary if exists
        sess_query = db.query(ConversationSession).filter(ConversationSession.patient_id == p_uuid)
        if input_data.case_id:
            sess_query = sess_query.filter(ConversationSession.case_id == c_uuid)
        session = sess_query.order_by(ConversationSession.created_at.desc()).first()

        summary = session.summary if session else None
        unanswered = list(session.unanswered_questions or []) if session else []

        output = ConversationHistoryOutput(
            patient_id=str(p_uuid),
            messages=message_items,
            total_messages=len(message_items),
            session_summary=summary,
            unanswered_questions=unanswered
        )
        return ToolResult(
            success=True,
            data=output,
            message=f"Retrieved {len(message_items)} communications for patient {input_data.patient_id}",
            autonomy_level=1
        )
    except ToolExecutionError as tee:
        return ToolResult(success=False, error_code=tee.error_code, message=tee.message, autonomy_level=tee.autonomy_level)
    except ValueError as ve:
        return ToolResult(success=False, error_code="INVALID_UUID", message=f"Invalid UUID: {ve}")
    except Exception as e:
        logger.error(f"Error in retrieve_conversation_history: {e}", exc_info=True)
        return ToolResult(success=False, error_code="INTERNAL_ERROR", message=str(e))
