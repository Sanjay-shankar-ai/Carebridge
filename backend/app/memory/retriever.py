"""
Unified Memory Retriever
Facade combining Patient Memory, Conversation Memory, and Case Memory into a single context.
"""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from app.memory.patient_memory import get_patient_memory, get_patient_memory_sync
from app.memory.conversation_memory import get_conversation_memory, get_conversation_memory_sync
from app.memory.case_memory import get_case_memory, get_case_memory_sync
from app.memory.schemas import UnifiedCareContext


async def get_unified_memory(
    case_id: uuid.UUID,
    patient_id: uuid.UUID,
    db: AsyncSession
) -> Optional[UnifiedCareContext]:
    """Retrieves full unified context for a care case."""
    patient_mem = await get_patient_memory(patient_id, db)
    if not patient_mem:
        return None

    case_mem = await get_case_memory(case_id, db)
    if not case_mem:
        return None

    if case_mem.patient_id != patient_id:
        raise PermissionError(
            f"Cross-patient access violation: Case {case_id} does not belong to patient {patient_id}"
        )

    conv_mem = await get_conversation_memory(patient_id, case_id, db)

    return UnifiedCareContext(
        patient=patient_mem,
        case=case_mem,
        conversation=conv_mem,
        retrieved_at=datetime.now()
    )


def get_unified_memory_sync(
    case_id: uuid.UUID,
    patient_id: uuid.UUID,
    db: Session
) -> Optional[UnifiedCareContext]:
    """Synchronous unified context retrieval."""
    patient_mem = get_patient_memory_sync(patient_id, db)
    if not patient_mem:
        return None

    case_mem = get_case_memory_sync(case_id, db)
    if not case_mem:
        return None

    if case_mem.patient_id != patient_id:
        raise PermissionError(
            f"Cross-patient access violation: Case {case_id} does not belong to patient {patient_id}"
        )

    conv_mem = get_conversation_memory_sync(patient_id, case_id, db)

    return UnifiedCareContext(
        patient=patient_mem,
        case=case_mem,
        conversation=conv_mem,
        retrieved_at=datetime.now()
    )
