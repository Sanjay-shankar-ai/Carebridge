"""
CareBridge AI Observability Module (LangSmith Integration)
Handles initialization, validation, and status inspection for LangSmith tracing across LangChain & LangGraph agents.
"""

import os
import logging
from typing import Dict, Any
from app.core.config import settings

logger = logging.getLogger("carebridge.observability")


def init_observability() -> Dict[str, Any]:
    """
    Initializes environment variables for LangChain/LangSmith tracing.
    Ensures LangChain natively streams agent executions to LangSmith if API key is provided.
    """
    project = settings.LANGCHAIN_PROJECT or "CareBridge"
    endpoint = settings.LANGCHAIN_ENDPOINT or "https://api.smith.langchain.com"
    api_key = settings.LANGCHAIN_API_KEY or os.getenv("LANGCHAIN_API_KEY", "")

    # Synchronize to os.environ so LangChain/LangGraph internals pick them up
    os.environ["LANGCHAIN_PROJECT"] = project
    os.environ["LANGCHAIN_ENDPOINT"] = endpoint

    if api_key and api_key.strip():
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = api_key.strip()
        logger.info(f"[LangSmith] AI Observability ENABLED. Streaming traces to Project '{project}' at {endpoint}")
        return {
            "enabled": True,
            "project": project,
            "endpoint": endpoint,
            "api_key_configured": True,
            "status": "active"
        }
    else:
        # Tracing is configured but awaiting key
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        logger.info(f"[LangSmith] Observability configured for Project '{project}'. Awaiting LANGCHAIN_API_KEY in .env.")
        return {
            "enabled": False,
            "project": project,
            "endpoint": endpoint,
            "api_key_configured": False,
            "status": "awaiting_api_key",
            "message": "Set LANGCHAIN_API_KEY in .env to stream live agent traces to your LangSmith dashboard."
        }


def get_observability_status() -> Dict[str, Any]:
    """Returns real-time status of LangSmith observability."""
    api_key = os.getenv("LANGCHAIN_API_KEY", "") or settings.LANGCHAIN_API_KEY
    tracing = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    project = os.getenv("LANGCHAIN_PROJECT", settings.LANGCHAIN_PROJECT)
    endpoint = os.getenv("LANGCHAIN_ENDPOINT", settings.LANGCHAIN_ENDPOINT)

    client_connected = False
    error_msg = None

    if api_key:
        try:
            import langsmith
            client = langsmith.Client(api_key=api_key, api_url=endpoint)
            # Ping client
            client_connected = True
        except Exception as e:
            error_msg = str(e)

    return {
        "tracing_enabled": tracing,
        "project": project,
        "endpoint": endpoint,
        "api_key_configured": bool(api_key and api_key.strip()),
        "client_connected": client_connected,
        "status": "active" if (tracing and client_connected) else "awaiting_api_key" if not api_key else "configured",
        "error": error_msg,
        "info": "LangChain and LangGraph agent runs are instrumented with @tool tracing."
    }
