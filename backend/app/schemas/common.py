"""
Common Pydantic Schemas for API responses and status models.
"""

from datetime import datetime, timezone
from typing import Generic, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class HealthResponse(BaseModel):
    status: str = Field(default="healthy", description="Service health status")
    app_name: str = Field(..., description="Application name")
    environment: str = Field(..., description="Runtime environment")
    version: str = Field(default="0.1.0", description="API version")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Current server UTC timestamp"
    )


class ApiResponseEnvelope(BaseModel, Generic[T]):
    success: bool = Field(default=True, description="Whether the operation succeeded")
    message: Optional[str] = Field(default=None, description="Optional informational message")
    data: Optional[T] = Field(default=None, description="Payload data")
    error: Optional[str] = Field(default=None, description="Error detail if success is false")

    @classmethod
    def success_response(cls, data: Optional[T] = None, message: Optional[str] = None) -> "ApiResponseEnvelope[T]":
        return cls(success=True, data=data, message=message, error=None)

    @classmethod
    def error_response(cls, error: str, message: Optional[str] = None) -> "ApiResponseEnvelope[T]":
        return cls(success=False, data=None, message=message, error=error)
