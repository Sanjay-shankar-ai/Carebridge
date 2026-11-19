"""
CareBridge Long-Running Workflow Checkpointer Management (Phase 8)
Provides persistent PostgreSQL checkpointing with case-isolated thread IDs,
checkpoint history inspection, state retrieval, and thread rollback capabilities.
Safely falls back to MemorySaver in unit tests and offline development.
"""

import logging
from typing import Optional, Dict, Any, List
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from app.core.config import settings

logger = logging.getLogger("carebridge.workflows.checkpointer")

_IN_MEMORY_CHECKPOINTER: Optional[MemorySaver] = None


def get_in_memory_checkpointer() -> MemorySaver:
    """Returns singleton in-memory checkpointer for testing and development."""
    global _IN_MEMORY_CHECKPOINTER
    if _IN_MEMORY_CHECKPOINTER is None:
        _IN_MEMORY_CHECKPOINTER = MemorySaver()
    return _IN_MEMORY_CHECKPOINTER


def get_workflow_checkpointer(db_uri: Optional[str] = None) -> BaseCheckpointSaver:
    """
    Creates and returns a persistent PostgreSQL checkpointer when available.
    If PostgreSQL is unreachable or during unit tests, safely falls back to MemorySaver.
    """
    uri = db_uri or getattr(settings, "CHECKPOINTER_DB_URI", None)

    if uri and "postgres" in uri:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            import psycopg

            # Probe connection with short timeout to prevent blocking
            conn = psycopg.connect(uri, autocommit=True, connect_timeout=2)
            saver = PostgresSaver(conn)
            saver.setup()  # Initialize checkpoint tables if they do not exist
            logger.info("Successfully connected PostgreSQL checkpointer.")
            return saver
        except Exception as e:
            logger.warning(
                f"PostgreSQL checkpointer unavailable ({e}). Falling back to MemorySaver for safe state persistence."
            )

    return get_in_memory_checkpointer()


def get_thread_config(case_id: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Constructs the LangGraph execution config using case_id as the primary thread identifier.
    Guarantees thread-level isolation so state resumes precisely for that specific patient case.
    """
    thread_id = f"care-thread-{case_id}" if not str(case_id).startswith("care-thread-") else str(case_id)
    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }
    if run_id:
        config["configurable"]["run_id"] = str(run_id)
    return config


def inspect_checkpoint_history(
    checkpointer: BaseCheckpointSaver,
    thread_id: str
) -> List[Dict[str, Any]]:
    """
    Retrieves chronological checkpoint timeline for a given thread ID.
    Enables coordinators and supervisors to inspect previous execution states.
    """
    formatted_thread = f"care-thread-{thread_id}" if not str(thread_id).startswith("care-thread-") else str(thread_id)
    config = {"configurable": {"thread_id": formatted_thread}}

    history = []
    try:
        # LangGraph BaseCheckpointSaver exposes .list(config)
        tuples = list(checkpointer.list(config))
        for item in tuples:
            checkpoint = item.checkpoint
            metadata = item.metadata or {}
            history.append({
                "checkpoint_id": checkpoint.get("id"),
                "node": metadata.get("node") or metadata.get("step"),
                "step": metadata.get("step"),
                "timestamp": checkpoint.get("ts"),
                "writes": item.pending_writes,
                "values_summary": {k: type(v).__name__ for k, v in (checkpoint.get("channel_values") or {}).items()}
            })
    except Exception as e:
        logger.error(f"Error inspecting checkpoint history for thread {thread_id}: {e}", exc_info=True)

    return history


def get_latest_checkpoint_state(
    checkpointer: BaseCheckpointSaver,
    thread_id: str
) -> Optional[Dict[str, Any]]:
    """
    Retrieves the latest persisted state dictionary for a specific thread.
    """
    formatted_thread = f"care-thread-{thread_id}" if not str(thread_id).startswith("care-thread-") else str(thread_id)
    config = {"configurable": {"thread_id": formatted_thread}}

    try:
        tuple_item = checkpointer.get_tuple(config)
        if tuple_item and tuple_item.checkpoint:
            return tuple_item.checkpoint.get("channel_values")
    except Exception as e:
        logger.error(f"Error getting latest checkpoint state for thread {thread_id}: {e}", exc_info=True)

    return None
