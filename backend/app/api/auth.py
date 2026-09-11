from datetime import datetime, timedelta, timezone
import os

from dotenv import load_dotenv
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2PasswordBearer,
    OAuth2PasswordRequestForm,
)
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.config import settings, ENV_FILE
from app.db.database import get_db
from app.models.doctor import Doctor


load_dotenv(ENV_FILE)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

password_hash = PasswordHash.recommended()

# Physician authentication scheme.
physician_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)

# Admin authentication scheme.
admin_bearer_scheme = HTTPBearer()

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


# -------------------------------------------------------------------
# TOKEN CREATION
# -------------------------------------------------------------------

def create_access_token(subject: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": subject,
        "role": role,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=JWT_ALGORITHM,
    )


# -------------------------------------------------------------------
# PHYSICIAN LOGIN
# -------------------------------------------------------------------

@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Authenticate a physician using doctor ID and password.
    """

    try:
        doctor_id = int(form_data.username)

    except (ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid doctor ID or password",
        )

    doctor = (
        db.query(Doctor)
        .filter(Doctor.id == doctor_id)
        .first()
    )

    if doctor is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid doctor ID or password",
        )

    if not doctor.is_active:
        raise HTTPException(
            status_code=403,
            detail="Doctor account is inactive",
        )

    if not doctor.password_hash:
        raise HTTPException(
            status_code=401,
            detail="Invalid doctor ID or password",
        )

    if not password_hash.verify(
        form_data.password,
        doctor.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid doctor ID or password",
        )

    access_token = create_access_token(
        subject=str(doctor.id),
        role=doctor.role,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": doctor.role,
    }


# -------------------------------------------------------------------
# ADMIN LOGIN
# -------------------------------------------------------------------

@router.post("/admin/login")
def admin_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """
    Authenticate the MediKiosk admin.

    Admin credentials are stored in backend/.env.
    """

    admin_username = os.getenv("ADMIN_USERNAME")
    admin_password = os.getenv("ADMIN_PASSWORD")

    if not admin_username or not admin_password:
        raise HTTPException(
            status_code=500,
            detail="Admin credentials are not configured",
        )

    if (
        form_data.username != admin_username
        or form_data.password != admin_password
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid admin credentials",
        )

    access_token = create_access_token(
        subject=admin_username,
        role="admin",
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": "admin",
    }


# -------------------------------------------------------------------
# JWT DECODING
# -------------------------------------------------------------------

def decode_token(token: str):
    """
    Decode and validate a MediKiosk JWT.
    """

    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate authentication credentials",
        headers={
            "WWW-Authenticate": "Bearer"
        },
    )

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[JWT_ALGORITHM],
        )

        subject = payload.get("sub")
        role = payload.get("role")

        if not subject or not role:
            raise credentials_exception

        return subject, role

    except (
        jwt.InvalidTokenError,
        ValueError,
        TypeError,
    ):
        raise credentials_exception


# -------------------------------------------------------------------
# CURRENT PHYSICIAN
# -------------------------------------------------------------------

def get_current_user(
    token: str = Depends(physician_oauth2_scheme),
    db: Session = Depends(get_db),
):
    """
    Validate a physician JWT and return the physician.
    """

    subject, role = decode_token(token)

    if role != "physician":
        raise HTTPException(
            status_code=403,
            detail="Physician access required",
        )

    try:
        doctor_id = int(subject)

    except (ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid physician credentials",
        )

    doctor = (
        db.query(Doctor)
        .filter(Doctor.id == doctor_id)
        .first()
    )

    if doctor is None:
        raise HTTPException(
            status_code=401,
            detail="Doctor not found",
        )

    if not doctor.is_active:
        raise HTTPException(
            status_code=403,
            detail="Doctor account is inactive",
        )

    return doctor


def get_current_doctor(
    current_doctor: Doctor = Depends(get_current_user),
) -> Doctor:
    return current_doctor


def require_physician(
    current_doctor: Doctor = Depends(get_current_doctor),
) -> Doctor:
    return current_doctor


# -------------------------------------------------------------------
# CURRENT ADMIN
# -------------------------------------------------------------------

def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(
        admin_bearer_scheme
    ),
):
    """
    Validate an Admin JWT.

    Swagger will show this as a separate Bearer authentication
    scheme, allowing the admin token to be entered directly.
    """

    subject, role = decode_token(credentials.credentials)

    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )

    return {
        "role": "admin",
        "username": subject,
    }