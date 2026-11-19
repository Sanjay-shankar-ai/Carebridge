"""
Conversation Memory Layer
Maintains message history, dialog summaries, unanswered queries, and patient commitments.
"""

import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from app.models.communication import Communication, ConversationSession
from app.memory.schemas import ConversationMemoryContext, MessageItem


def _build_conversation_memory(
    patient_id: uuid.UUID,
    case_id: Optional[uuid.UUID],
    session: Optional[ConversationSession],
    communications: List[Communication]
) -> ConversationMemoryContext:
    messages = [
        MessageItem(
            id=c.id,
            sender=c.sender,
            language=c.language,
            channel=c.channel,
            content=c.content,
            translated_content=c.translated_content,
            acknowledged=c.acknowledged,
            sent_at=c.sent_at
        )
        for c in communications
    ]

    return ConversationMemoryContext(
        session_id=session.id if session else None,
        patient_id=patient_id,
        case_id=case_id,
        recent_messages=messages,
        summary=session.summary if session else None,
        unanswered_questions=session.unanswered_questions if session else [],
        patient_commitments=session.patient_commitments if session else []
    )


async def get_conversation_memory(
    patient_id: uuid.UUID,
    case_id: Optional[uuid.UUID],
    db: AsyncSession,
    limit: int = 15
) -> ConversationMemoryContext:
    """Asynchronously retrieves dialogue history and commitments for an active thread."""
    # Find active session
    session_stmt = (
        select(ConversationSession)
        .where(
            ConversationSession.patient_id == patient_id,
            ConversationSession.is_active.is_(True)
        )
        .order_by(desc(ConversationSession.last_interaction_at))
    )
    session_res = await db.execute(session_stmt)
    session = session_res.scalars().first()

    # Find recent communications
    comm_stmt = (
        select(Communication)
        .where(Communication.patient_id == patient_id)
        .order_by(desc(Communication.sent_at))
        .limit(limit)
    )
    if case_id:
        comm_stmt = comm_stmt.where(Communication.case_id == case_id)

    comm_res = await db.execute(comm_stmt)
    communications = list(reversed(comm_res.scalars().all()))

    return _build_conversation_memory(patient_id, case_id, session, communications)


def get_conversation_memory_sync(
    patient_id: uuid.UUID,
    case_id: Optional[uuid.UUID],
    db: Session,
    limit: int = 15
) -> ConversationMemoryContext:
    """Synchronous retrieval of conversation memory."""
    session = (
        db.query(ConversationSession)
        .filter(
            ConversationSession.patient_id == patient_id,
            ConversationSession.is_active.is_(True)
        )
        .order_by(desc(ConversationSession.last_interaction_at))
        .first()
    )

    query = db.query(Communication).filter(Communication.patient_id == patient_id)
    if case_id:
        query = query.filter(Communication.case_id == case_id)
    
    communications = list(reversed(query.order_by(desc(Communication.sent_at)).limit(limit).all()))

    return _build_conversation_memory(patient_id, case_id, session, communications)
