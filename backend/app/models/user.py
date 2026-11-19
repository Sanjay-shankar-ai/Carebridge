"""
CareBridge User & Identity Account Model
Stores authenticated identities, hashed passwords, verified roles, and links to clinical/patient profiles.
"""

import uuid
from typing import Optional
from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid
from app.database.session import Base, TimestampedUUIDMixin


class User(Base, TimestampedUUIDMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # Supported roles: "patient", "doctor", "care_coordinator"
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Optional profile links
    patient_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("case_owners.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Relationships
    patient_profile: Mapped[Optional["Patient"]] = relationship("Patient", foreign_keys=[patient_id])
    owner_profile: Mapped[Optional["CaseOwner"]] = relationship("CaseOwner", foreign_keys=[owner_id])

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role}) active={self.is_active}>"
