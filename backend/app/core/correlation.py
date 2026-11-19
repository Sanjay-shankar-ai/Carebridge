"""
CareBridge Correlation ID Context Variables (Phase 6)
Provides async-safe propagation of correlation_id and workflow_id
across request boundaries using Python contextvars.
"""

from contextvars import ContextVar
import uuid

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
workflow_id_var: ContextVar[str] = ContextVar("workflow_id", default="")


def get_correlation_id() -> str:
    """Return the current request correlation ID, or empty string if not set."""
    return correlation_id_var.get()


def get_workflow_id() -> str:
    """Return the current workflow ID, or empty string if not set."""
    return workflow_id_var.get()


def set_correlation_ids(correlation_id: str = None, workflow_id: str = None) -> None:
    """Set both context variables. Generates new IDs for any None argument."""
    correlation_id_var.set(correlation_id if correlation_id else new_correlation_id())
    workflow_id_var.set(workflow_id if workflow_id else new_workflow_id())


def new_correlation_id() -> str:
    """Generate a fresh correlation ID."""
    return str(uuid.uuid4())


def new_workflow_id() -> str:
    """Generate a fresh workflow ID."""
    return str(uuid.uuid4())
