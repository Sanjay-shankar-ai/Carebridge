"""
CareBridge Configuration Module
Loads application configuration via Pydantic Settings from environment variables or .env file.
"""

import os
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Base application settings
    APP_NAME: str = "CareBridge AI Care Coordinator"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "carebridge-dev-secret-key-replace-in-production-32-bytes"

    # CORS settings
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        return ["*"]

    # Database & Supabase settings
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/carebridge"
    CHECKPOINTER_DB_URI: str = "postgresql://postgres:postgres@localhost:5432/carebridge"

    # LLM Settings (Gemini Primary, GroqCloud & OpenAI Fallback)
    LLM_PROVIDER: str = "gemini" # "gemini", "groq", "openai", "mock"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "" # Optional custom proxy/endpoint
    OPENAI_MODEL_NAME: str = "gpt-4o"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # LangSmith / LangChain AI Observability
    LANGCHAIN_TRACING_V2: bool = True
    LANGCHAIN_PROJECT: str = "CareBridge"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGCHAIN_API_KEY: str = ""

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        if len(v.strip()) < 16:
            raise ValueError("SECRET_KEY must be at least 16 characters long.")
        return v

    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() in ("production", "prod")

    def get_sanitized_config(self) -> dict:
        """Returns configuration with sensitive secrets masked for safe logging and audits."""
        raw = self.model_dump()
        for secret_field in ("SECRET_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "DATABASE_URL", "CHECKPOINTER_DB_URI"):
            if secret_field in raw and raw[secret_field]:
                val = str(raw[secret_field])
                if len(val) > 8:
                    raw[secret_field] = f"{val[:4]}...{val[-4:]}"
                else:
                    raw[secret_field] = "******"
        return raw

    # Care Coordination SLAs (Default hours/days)
    DEFAULT_ACK_SLA_HOURS: int = 24
    DEFAULT_REFERRAL_SLA_HOURS: int = 48
    DEFAULT_APPOINTMENT_SLA_DAYS: int = 14
    DEFAULT_CLOSURE_SLA_DAYS: int = 60

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
