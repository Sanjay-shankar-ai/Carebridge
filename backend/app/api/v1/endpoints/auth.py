"""
CareBridge Authentication & Unified Role Detection API
Provides:
1. Patient and Doctor Registration with password hashing and duplicate prevention.
2. Login with password verification and cryptographic JWT issuance.
3. Authenticated session validation (/auth/me).
4. Strict database-derived role detection (Patient, Doctor, Coordinator, Admin).
"""

import uuid
from datetime import date, datetime, timezone, timedelta
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, EmailStr
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.database.session import get_async_db
from app.models.user import User
from app.models.owner import CaseOwner
from app.models.patient import Patient
from app.models.screening import ScreeningResult
from app.models.care_case import CareCase
from app.models.communication import ConversationSession, Communication
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    UserPrincipal,
)
from app.core.rate_limiter import rate_limit_login, login_rate_limiter, agent_rate_limiter
from app.schemas.common import ApiResponseEnvelope

router = APIRouter(prefix="/auth", tags=["Authentication & Role Detection"])


# ------------------------------------------------------------------------------
# Request / Response Schemas
# ------------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str = Field(description="Registered email address")
    password: str = Field(min_length=1, description="Password")


class RegisterPatientRequest(BaseModel):
    email: str = Field(description="Patient email address")
    password: str = Field(min_length=8, description="Password (min 8 chars)")
    first_name: str = Field(min_length=1, description="First name")
    last_name: str = Field(min_length=1, description="Last name")
    phone: str = Field(min_length=5, description="Phone number")
    date_of_birth: date = Field(default=date(1980, 1, 1), description="Date of birth")
    preferred_language: str = Field(default="en", description="Preferred language (en, ta, es)")


class RegisterDoctorRequest(BaseModel):
    email: str = Field(description="Doctor email address")
    password: str = Field(min_length=8, description="Password (min 8 chars)")
    full_name: str = Field(min_length=1, description="Full Name with credential")
    facility: str = Field(min_length=2, description="Hospital or Specialty Clinic")
    phone: Optional[str] = Field(default=None, description="Direct clinical line")
    specialty: str = Field(default="Breast Oncology", description="Clinical specialty")


class UserProfile(BaseModel):
    id: str
    name: str
    email: str
    role: str  # "patient", "clinician", "care_coordinator", "admin"
    facility: Optional[str] = None
    patient_id: Optional[str] = None
    case_id: Optional[str] = None
    phone: Optional[str] = None
    token: str


# ------------------------------------------------------------------------------
# 1. Registration Endpoints
# ------------------------------------------------------------------------------

@router.post(
    "/register/patient",
    response_model=ApiResponseEnvelope[UserProfile],
    status_code=status.HTTP_201_CREATED,
    summary="Register New Patient Account"
)
async def register_patient(
    req: RegisterPatientRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Registers a new Patient user account.
    Validates duplicate email, hashes password, creates Patient demographic record and User identity.
    """
    clean_email = req.email.strip().lower()

    # Check for duplicate email
    existing_stmt = select(User).where(User.email == clean_email)
    existing_res = await db.execute(existing_stmt)
    if existing_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An account with email '{clean_email}' already exists. Please log in."
        )

    # Generate Unique MRN
    year = datetime.now(timezone.utc).year
    rand_suffix = str(uuid.uuid4().hex[:6]).upper()
    mrn = f"MRN-{year}-{rand_suffix}"

    now = datetime.now(timezone.utc)

    # 1. Create Patient Profile
    new_patient = Patient(
        id=uuid.uuid4(),
        mrn=mrn,
        first_name=req.first_name.strip(),
        last_name=req.last_name.strip(),
        phone=req.phone.strip(),
        email=clean_email,
        date_of_birth=req.date_of_birth,
        preferred_language=req.preferred_language,
        communication_channel="in_app_chat",
    )
    db.add(new_patient)
    await db.flush()

    # 2. Look up Hospital Care Coordinator for Immediate Facility Ownership
    coord_stmt = select(CaseOwner).where(CaseOwner.role == "care_coordinator").limit(1)
    coord_res = await db.execute(coord_stmt)
    hospital_coordinator = coord_res.scalars().first()
    coord_name = hospital_coordinator.name if hospital_coordinator else "Priya Nair, RN"
    facility_name = hospital_coordinator.facility if hospital_coordinator else "Metropolitan Hospital Screening Center"

    # 3. Create Initial Diagnostic Screening Result for Intake
    init_screening = ScreeningResult(
        id=uuid.uuid4(),
        patient_id=new_patient.id,
        screening_type="General Healthcheck & Screening",
        test_date=now,
        finding_code="INTAKE-PENDING",
        finding_summary=f"Patient registered in CareBridge hospital portal. Awaiting intake statement to schedule screening at {facility_name}.",
        urgency_level="standard",
        performing_facility=facility_name,
        raw_report_data={"intake_stage": "initial_registration"}
    )
    db.add(init_screening)
    await db.flush()

    # 4. Create Distinct CareCase for Newly Registered Patient with Hospital Ownership
    new_case = CareCase(
        id=uuid.uuid4(),
        case_number=f"CASE-{year}-{rand_suffix}",
        patient_id=new_patient.id,
        screening_result_id=init_screening.id,
        current_owner_id=hospital_coordinator.id if hospital_coordinator else None,
        status="intake",
        priority="standard",
        sla_start_time=now,
        sla_deadline=now + timedelta(days=14),
        sla_status="normal",
        case_context={
            "onboarding_stage": "intake_ready",
            "is_new_registration": True,
            "intake_status": "awaiting_patient_request",
            "facility": facility_name,
            "hospital_name": facility_name,
            "coordinator_name": coord_name,
            "screening_request": "Pending Patient Intake Statement",
        }
    )
    db.add(new_case)
    await db.flush()

    # 5. Create Dedicated Conversation Session for Long-Term Memory
    new_session = ConversationSession(
        id=uuid.uuid4(),
        patient_id=new_patient.id,
        case_id=new_case.id,
        channel="in_app_chat",
        summary=f"Patient intake session for {new_patient.first_name}. Hospital coordinator {coord_name} assigned.",
        is_active=True,
        last_interaction_at=now
    )
    db.add(new_session)
    await db.flush()

    # 6. Insert Onboarding Greeting Message into Communication History
    first_name = req.first_name.strip()
    welcome_text = (
        f"Hi {first_name}! Welcome to CareBridge. I am your AI Care Companion working directly with your hospital Care Coordinator ({coord_name}). "
        "How can we assist you with your health check, screening, or medical concerns today? "
        "Please describe what you need, and our care coordination team will prepare and schedule your screening."
    )
    welcome_comm = Communication(
        id=uuid.uuid4(),
        case_id=new_case.id,
        patient_id=new_patient.id,
        session_id=new_session.id,
        sender="ai_coordinator",
        channel="in_app_chat",
        language="en",
        content=welcome_text,
        translated_content=welcome_text,
        acknowledged=False,
        sent_at=now
    )
    db.add(welcome_comm)

    # 5. Create User Account
    new_user = User(
        id=uuid.uuid4(),
        email=clean_email,
        password_hash=hash_password(req.password),
        role="patient",
        full_name=f"{req.first_name.strip()} {req.last_name.strip()}",
        is_active=True,
        is_verified=True,
        patient_id=new_patient.id,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # 6. Generate Cryptographic JWT with Verified Case ID
    token = create_access_token({
        "sub": str(new_user.id),
        "role": new_user.role,
        "email": new_user.email,
        "name": new_user.full_name,
        "case_id": str(new_case.id),
    })

    return ApiResponseEnvelope.success_response(
        data=UserProfile(
            id=str(new_user.id),
            name=new_user.full_name,
            email=new_user.email,
            role=new_user.role,
            facility="CareBridge Patient Network",
            patient_id=str(new_patient.id),
            case_id=str(new_case.id),
            phone=new_patient.phone,
            token=token,
        ),
        message="Patient account registered successfully."
    )


@router.post(
    "/register/doctor",
    response_model=ApiResponseEnvelope[UserProfile],
    status_code=status.HTTP_201_CREATED,
    summary="Register New Doctor / Specialist Account"
)
async def register_doctor(
    req: RegisterDoctorRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Registers a new Clinician user account.
    Validates duplicate email, hashes password, creates CaseOwner profile and User identity.
    """
    clean_email = req.email.strip().lower()

    existing_stmt = select(User).where(User.email == clean_email)
    existing_res = await db.execute(existing_stmt)
    if existing_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An account with email '{clean_email}' already exists. Please log in."
        )

    # 1. Create CaseOwner Profile
    new_owner = CaseOwner(
        id=uuid.uuid4(),
        name=req.full_name.strip(),
        role="specialist",
        email=clean_email,
        phone=req.phone.strip() if req.phone else None,
        facility=req.facility.strip(),
        is_active=True,
    )
    db.add(new_owner)
    await db.flush()

    # 2. Create User Account
    new_user = User(
        id=uuid.uuid4(),
        email=clean_email,
        password_hash=hash_password(req.password),
        role="doctor",
        full_name=req.full_name.strip(),
        is_active=True,
        is_verified=True,
        owner_id=new_owner.id,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # 3. Generate Cryptographic JWT
    token = create_access_token({
        "sub": str(new_user.id),
        "role": new_user.role,
        "email": new_user.email,
        "name": new_user.full_name,
    })

    return ApiResponseEnvelope.success_response(
        data=UserProfile(
            id=str(new_user.id),
            name=new_user.full_name,
            email=new_user.email,
            role=new_user.role,
            facility=new_owner.facility,
            phone=new_owner.phone,
            token=token,
        ),
        message="Doctor account registered successfully."
    )


# ------------------------------------------------------------------------------
# 2. Login Endpoint
# ------------------------------------------------------------------------------

@router.post(
    "/login",
    response_model=ApiResponseEnvelope[UserProfile],
    dependencies=[Depends(rate_limit_login)],
    summary="Unified Login & Cryptographic JWT Issuance"
)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Authenticates registered user using email and password.
    Retrieves trusted role strictly from the database.
    Issues cryptographic JWT containing user_id, verified_role, and expiration.
    """
    clean_identifier = req.email.strip().lower()

    # Search User table
    stmt = select(User).where(User.email == clean_identifier)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        # Check alias shortcuts for convenience
        alias_map = {
            "doctor": "doctor@carebridge.com",
            "doc": "doctor@carebridge.com",
            "coordinator": "coordinator@carebridge.com",
            "coord": "coordinator@carebridge.com",
            "patient": "patient@carebridge.com",
        }
        if clean_identifier in alias_map:
            alias_email = alias_map[clean_identifier]
            alias_res = await db.execute(select(User).where(User.email == alias_email))
            user = alias_res.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid credentials. No registered user found for '{req.email}'."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Please contact your care coordinator or administrator."
        )

    # Mandatory Cryptographic Password Verification
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Incorrect password provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Resolve linked patient or case context
    patient_id = None
    case_id = None
    facility = None
    phone = None

    if user.patient_id:
        patient_id = str(user.patient_id)
        # Find active care case (most recent first)
        case_stmt = select(CareCase).where(CareCase.patient_id == user.patient_id).order_by(CareCase.created_at.desc())
        case_res = await db.execute(case_stmt)
        c = case_res.scalars().first()
        if c:
            case_id = str(c.id)

    if user.owner_id:
        owner_res = await db.execute(select(CaseOwner).where(CaseOwner.id == user.owner_id))
        owner = owner_res.scalar_one_or_none()
        if owner:
            facility = owner.facility
            phone = owner.phone

    # Issue verified cryptographic JWT
    token_claims = {
        "sub": str(user.id),
        "role": user.role,
        "email": user.email,
        "name": user.full_name,
    }
    if case_id:
        token_claims["case_id"] = case_id
    if patient_id:
        token_claims["patient_id"] = patient_id

    token = create_access_token(token_claims)

    return ApiResponseEnvelope.success_response(
        data=UserProfile(
            id=str(user.id),
            name=user.full_name,
            email=user.email,
            role=user.role,
            facility=facility or "CareBridge Health System",
            patient_id=patient_id,
            case_id=case_id,
            phone=phone,
            token=token,
        ),
        message=f"Welcome back, {user.full_name}"
    )


# ------------------------------------------------------------------------------
# 3. Session & Me Endpoint
# ------------------------------------------------------------------------------

@router.get(
    "/me",
    response_model=ApiResponseEnvelope[UserPrincipal],
    summary="Get Authenticated User Profile"
)
async def get_current_user_profile(
    current_user: UserPrincipal = Depends(get_current_user)
):
    """Returns the validated database profile of the active Bearer token."""
    return ApiResponseEnvelope.success_response(
        data=current_user,
        message="Session authenticated"
    )


class TokenRefreshResponse(BaseModel):
    token: str = Field(description="Newly signed cryptographic JWT access token")
    token_type: str = Field(default="Bearer")
    expires_in_minutes: int = Field(default=1440)


@router.post(
    "/refresh",
    response_model=ApiResponseEnvelope[TokenRefreshResponse],
    summary="Refresh Active JWT Session"
)
async def refresh_access_token(
    current_user: UserPrincipal = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Validates current active JWT session against database, confirms active account status,
    and issues a fresh cryptographic JWT access token.
    """
    u_uuid = uuid.UUID(current_user.user_id)
    stmt = select(User).where(User.id == u_uuid)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or not found. Cannot refresh session.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    fresh_token = create_access_token({
        "sub": str(user.id),
        "role": user.role,
        "email": user.email,
        "name": user.full_name,
    })

    return ApiResponseEnvelope.success_response(
        data=TokenRefreshResponse(token=fresh_token),
        message="Access token refreshed successfully."
    )


@router.post(
    "/rate-limit-reset",
    summary="Reset In-Memory Rate Limit Counters (Development/Testing Only)"
)
async def reset_rate_limit():
    """Resets sliding window rate limiter state for testing."""
    login_rate_limiter.reset()
    agent_rate_limiter.reset()
    return {"status": "success", "message": "Rate limits reset"}
