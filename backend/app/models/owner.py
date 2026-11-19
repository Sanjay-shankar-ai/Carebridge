"""
Case Owner Relational Model
Represents named coordinators, clinicians, and providers responsible for care cases.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy import String, Boolean, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.session import Base, TimestampedUUIDMixin


class CaseOwner(Base, TimestampedUUIDMixin):
    __tablename__ = "case_owners"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False) # "care_coordinator", "primary_physician", "specialist", "nurse_navigator"
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    facility: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Doctor Directory & Allocation Extensions
    specialty: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    subspecialties: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    max_workload: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    working_hours: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    on_leave: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    eligibility_status: Mapped[str] = mapped_column(String(32), default="eligible", nullable=False, index=True) # "eligible", "on_leave", "over_capacity", "suspended"
    approved_case_categories: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    response_deadline_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)

    # Relationships
    owned_cases: Mapped[List["CareCase"]] = relationship("CareCase", back_populates="current_owner")
    assigned_tasks: Mapped[List["Task"]] = relationship("Task", back_populates="assigned_to")
    verified_closures: Mapped[List["ClosureEvidence"]] = relationship("ClosureEvidence", back_populates="verifying_clinician")
    doctor_assignments: Mapped[List["DoctorAssignment"]] = relationship("DoctorAssignment", back_populates="doctor")

    def __repr__(self) -> str:
        return f"<CaseOwner {self.name} ({self.role} - {self.specialty or 'General'}) at {self.facility}>"
