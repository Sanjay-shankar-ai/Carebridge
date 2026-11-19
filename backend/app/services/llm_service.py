"""
CareBridge Centralized LLM Service
Provides singleton/cached LLM client instances supporting Google Gemini, GroqCloud (openai/gpt-oss-120b),
OpenAI, and deterministic mock providers with tool-calling capabilities.
"""

from typing import Optional, List, Type, Any
from functools import lru_cache
from pydantic import BaseModel
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from app.core.config import settings

try:
    from google import genai
    from google.genai import types as genai_types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


class GeminiChatModel(BaseChatModel):
    """LangChain BaseChatModel wrapper for the Google GenAI SDK (gemini-3.5-flash-lite / gemini-3.8-flash)."""

    client: Any = None
    model_name: str = "gemini-3.5-flash-lite"
    temperature: float = 0.1

    def __init__(self, api_key: str, model_name: str = "gemini-3.5-flash-lite", temperature: float = 0.1, **kwargs):
        super().__init__(**kwargs)
        if not GENAI_AVAILABLE:
            raise ImportError("google-genai package is not installed.")
        http_opts = genai_types.HttpOptions(timeout=25000) if hasattr(genai_types, "HttpOptions") else None
        self.client = genai.Client(api_key=api_key, http_options=http_opts)
        self.model_name = model_name
        self.temperature = temperature

    @property
    def _llm_type(self) -> str:
        return "gemini"

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs) -> ChatResult:
        contents = []
        system_instruction = None
        for m in messages:
            if isinstance(m, SystemMessage):
                system_instruction = str(m.content)
            elif isinstance(m, HumanMessage):
                contents.append(str(m.content))
            elif isinstance(m, AIMessage):
                contents.append(str(m.content))
            else:
                contents.append(str(m.content))
        prompt = "\n\n".join(contents)
        config = genai_types.GenerateContentConfig(
            temperature=self.temperature,
            system_instruction=system_instruction
        )
        # Try configured model, with resilient fallback to supported Gemini models
        models_to_try = [self.model_name]
        for candidate in ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]:
            if candidate not in models_to_try:
                models_to_try.append(candidate)

        last_err = None
        for mod in models_to_try:
            try:
                resp = self.client.models.generate_content(
                    model=mod,
                    contents=prompt,
                    config=config
                )
                text = resp.text or ""
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])
            except Exception as e:
                last_err = e
                continue

        # Resilient failover to Groq if Google Gemini free tier experiences 503/504 spikes
        groq_client = LLMService._get_groq_client()
        if groq_client:
            res = groq_client.invoke(messages)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=str(res.content)))])

        raise last_err or RuntimeError("Gemini content generation failed across all models.")


class LLMService:
    """Singleton factory for managing LLM clients across the platform."""

    _gemini_instance: Optional[BaseChatModel] = None
    _groq_instance: Optional[Any] = None
    _openai_instance: Optional[ChatOpenAI] = None

    @classmethod
    def get_llm(cls, provider: Optional[str] = None) -> Optional[BaseChatModel]:
        """Returns the primary configured LLM client using singleton reuse with resilient failover."""
        selected_provider = provider or settings.LLM_PROVIDER.lower()

        if selected_provider == "gemini":
            return cls._get_gemini_client()
        elif selected_provider == "groq":
            return cls._get_groq_client()
        elif selected_provider == "openai":
            return cls._get_openai_client()
        elif selected_provider == "mock":
            return None
        else:
            # Default to Gemini if key exists, else Groq, else OpenAI
            if settings.GEMINI_API_KEY and not settings.GEMINI_API_KEY.startswith("dummy"):
                return cls._get_gemini_client()
            if settings.GROQ_API_KEY and not settings.GROQ_API_KEY.startswith("dummy"):
                return cls._get_groq_client()
            return cls._get_openai_client()

    @classmethod
    def _get_gemini_client(cls) -> Optional[BaseChatModel]:
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.startswith("dummy"):
            return None

        if cls._gemini_instance is None:
            try:
                cls._gemini_instance = GeminiChatModel(
                    api_key=settings.GEMINI_API_KEY,
                    model_name=settings.GEMINI_MODEL,
                    temperature=0.1
                )
            except Exception as e:
                return None
        return cls._gemini_instance

    @classmethod
    def _get_groq_client(cls) -> Optional[Any]:
        if not settings.GROQ_API_KEY or settings.GROQ_API_KEY.startswith("dummy"):
            return None

        if cls._groq_instance is None:
            primary = ChatGroq(
                model=settings.GROQ_MODEL,
                api_key=settings.GROQ_API_KEY,
                temperature=0.1,
                timeout=12.0,
                max_retries=1,
            )
            # Resilient fallback Groq model to absorb rate limits and ensure continuous availability
            fallback_model = "openai/gpt-oss-20b"
            if settings.GROQ_MODEL != fallback_model:
                fallback = ChatGroq(
                    model=fallback_model,
                    api_key=settings.GROQ_API_KEY,
                    temperature=0.1,
                    timeout=10.0,
                    max_retries=1,
                )
                cls._groq_instance = primary.with_fallbacks([fallback])
            else:
                cls._groq_instance = primary
        return cls._groq_instance

    @classmethod
    def _get_openai_client(cls) -> Optional[ChatOpenAI]:
        if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY.startswith("dummy"):
            return None

        if cls._openai_instance is None:
            kwargs = {
                "model": settings.OPENAI_MODEL_NAME,
                "api_key": settings.OPENAI_API_KEY,
                "temperature": 0.1,
                "timeout": 10.0,
                "max_retries": 1,
            }
            if settings.OPENAI_BASE_URL:
                kwargs["base_url"] = settings.OPENAI_BASE_URL
            cls._openai_instance = ChatOpenAI(**kwargs)
        return cls._openai_instance

    @classmethod
    def reset_clients(cls):
        """Resets cached client instances (primarily for test environments)."""
        cls._gemini_instance = None
        cls._groq_instance = None
        cls._openai_instance = None


llm_service = LLMService()
