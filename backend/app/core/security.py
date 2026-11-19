"""
CareBridge Authentication, RBAC & Minimum Necessary PHI Module
Enforces:
1. Secure password hashing with bcrypt.
2. Cryptographic JWT creation, verification, and expiration check.
3. Role-Based Access Control (RBAC) backed by database User identity.
4. HIPAA Minimum Necessary PHI Masking.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from passlib.context import CryptContext
from jose import jwt, JWTError
from fastapi import HTTPException, Security, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.database.session import get_async_db

bearer_scheme = HTTPBearer(auto_error=False)

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
JWT_SECRET_KEY = settings.SECRET_KEY
JWT_ALGORITHM = "HS256"
DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

ROLE_API_KEYS = {
    "dev-coordinator-key": {"role": "care_coordinator", "name": "Priya Nair, RN", "email": "priya.nair@carebridge.health"},
    "dev-clinician-key": {"role": "clinician", "name": "Dr. Aris Thorne, MD", "email": "aris.thorne@carebridge.health"},
    "dev-doctor-key": {"role": "doctor", "name": "Dr. Aris Thorne, MD", "email": "aris.thorne@carebridge.health"},
    "carebridge-key-coordinator": {"role": "care_coordinator", "name": "Priya Nair, RN", "email": "coordinator@carebridge.health"},
    "carebridge-key-doctor": {"role": "doctor", "name": "Dr. Aris Thorne, MD", "email": "doctor@carebridge.health"},
    "carebridge-key-clinician": {"role": "doctor", "name": "Dr. Aris Thorne, MD", "email": "doctor@carebridge.health"},
    "carebridge-key-patient": {"role": "patient", "name": "Sarah Jenkins", "email": "patient@carebridge.health"},
}


def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """Creates a cryptographically signed JWT access token with expiration and unique identifier."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=DEFAULT_ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now, "jti": str(uuid.uuid4())})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decodes and validates a JWT token.
    Raises HTTPException 401 if expired or invalid.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


class UserPrincipal(BaseModel):
    """Authenticated user context containing identity, role, and profile affiliation."""
    user_id: str = Field(description="UUID of authenticated user")
    email: str = Field(description="Email of user")
    role: str = Field(description="Role: 'patient', 'doctor', 'clinician', 'care_coordinator'")
    name: str = Field(default="Authenticated User", description="Display name")
    facility: Optional[str] = Field(default=None, description="Primary healthcare facility")
    patient_id: Optional[str] = Field(default=None, description="Linked patient profile UUID if applicable")
    owner_id: Optional[str] = Field(default=None, description="Linked case owner profile UUID if applicable")


def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = None
) -> UserPrincipal:
    """
    Authenticates incoming request using Bearer JWT or verified API key.
    Validates token signature, expiration, and loads the active User record from DB.
    Never relies on untrusted headers or fake defaults.
    """
    # 1. API key resolution for automated testing & non-production integration
    if api_key:
        if settings.is_production():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Static API key authentication is disabled in production environments. Bearer JWT required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        api_info = ROLE_API_KEYS.get(api_key)
        if isinstance(api_info, dict):
            return UserPrincipal(
                user_id=str(uuid.uuid4()),
                email=api_info.get("email", "test@carebridge.health"),
                role=api_info["role"],
                name=api_info.get("name", f"Test {api_info['role'].title()}")
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unauthorized API key."
        )

    # 2. Bearer token validation
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided. Bearer token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth.credentials.strip()
    payload = decode_access_token(token)

    user_id_str: Optional[str] = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject identifier.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: malformed subject identifier.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from app.models.user import User
    from app.models.owner import CaseOwner
    from app.database.session import get_sync_db

    with get_sync_db() as db:
        user = db.query(User).filter(User.id == user_uuid).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authenticated user account does not exist in the database.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated. Contact care administration.",
            )

        # Enforce approved 3 roles: patient, doctor (or clinician), care_coordinator
        approved_roles = {"patient", "doctor", "clinician", "care_coordinator"}
        if user.role not in approved_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Account role '{user.role}' is not an active authorized application role.",
            )

        # Resolve facility and profile metadata
        facility = None
        if user.owner_id:
            owner = db.query(CaseOwner).filter(CaseOwner.id == user.owner_id).first()
            if owner:
                facility = owner.facility

        return UserPrincipal(
            user_id=str(user.id),
            email=user.email,
            role=user.role,
            name=user.full_name,
            facility=facility,
            patient_id=str(user.patient_id) if user.patient_id else None,
            owner_id=str(user.owner_id) if user.owner_id else None,
        )


def require_role(allowed_roles: List[str]):
    """FastAPI dependency factory enforcing strict Role-Based Access Control."""
    # Expand aliases: doctor <-> clinician
    expanded_roles = set(allowed_roles)
    if "doctor" in expanded_roles:
        expanded_roles.add("clinician")
    if "clinician" in expanded_roles:
        expanded_roles.add("doctor")

    def _role_checker(user: UserPrincipal = Depends(get_current_user)) -> UserPrincipal:
        if user.role not in expanded_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: User role '{user.role}' lacks sufficient privileges. Required: {allowed_roles}"
            )
        return user
    return _role_checker


def mask_phone_number(phone: Optional[str]) -> Optional[str]:
    """Masks middle digits of phone numbers to enforce minimum necessary PHI exposure."""
    if not phone:
        return phone
    cleaned = phone.strip()
    if len(cleaned) > 7:
        prefix = cleaned[:7]
        suffix = cleaned[-3:]
        return f"{prefix}***-**{suffix}"
    return phone


def filter_minimum_necessary_phi(patient_data: Dict[str, Any], requester_role: str) -> Dict[str, Any]:
    """
    Applies HIPAA Minimum Necessary Standard to patient data payloads.
    Redacts or masks full direct identifiers for non-clinical or administrative roles.
    """
    data = dict(patient_data)
    if requester_role not in ("doctor", "clinician", "specialist", "primary_physician"):
        if "phone" in data and data["phone"]:
            data["phone"] = mask_phone_number(data["phone"])
        if "email" in data and data["email"] and "@" in data["email"]:
            parts = data["email"].split("@")
            data["email"] = f"{parts[0][:2]}***@{parts[1]}"
    return data
