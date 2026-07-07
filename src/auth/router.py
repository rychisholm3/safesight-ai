"""
Auth endpoints: register, login, refresh, me, guest.

POST /auth/register  – create org + first Safety Officer user
POST /auth/login     – returns access + refresh tokens
POST /auth/refresh   – exchange refresh token for new access token
POST /auth/guest      – returns tokens for the shared read-only demo account
GET  /auth/me        – return current user info
"""
import logging
import secrets
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from pydantic import BaseModel, EmailStr, field_validator

from src.auth.db import AuthDB
from src.auth.dependencies import require_auth
from src.auth.models import Role, User
from src.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    verify_password,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

GUEST_ORG_NAME = "Demo Organization"
GUEST_EMAIL    = "guest@safesight.demo"


# ── Request / response schemas ────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    org_name:  str
    email:     EmailStr
    password:  str

    @field_validator("password")
    @classmethod
    def _password_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"


class UserResponse(BaseModel):
    user_id:    str
    org_id:     str
    email:      str
    role:       str
    is_active:  bool
    created_at: str


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        user_id=user.user_id,
        org_id=user.org_id,
        email=user.email,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def _get_auth_db() -> AuthDB:
    from src.api.main import auth_db
    return auth_db


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest, db: AuthDB = Depends(_get_auth_db)):
    """
    Create a new organisation and its first Safety Officer account.
    Subsequent users are added by an admin (future endpoint).
    """
    if db.get_user_by_email(body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already registered")

    org = db.create_org(body.org_name)
    user = db.create_user(
        org_id=org.org_id,
        email=body.email,
        plain_password=body.password,
        role=Role.safety_officer,
    )
    logger.info("New org registered: org=%s user=%s", org.name, user.email)
    return TokenResponse(
        access_token=create_access_token(user.user_id, user.role.value, user.org_id),
        refresh_token=create_refresh_token(user.user_id),
    )


@router.post("/guest", response_model=TokenResponse)
def guest_login(db: AuthDB = Depends(_get_auth_db)):
    """
    Issue real tokens for the shared read-only demo account, creating it on
    first use. Lets "Continue as Guest" reuse the normal auth flow instead of
    faking a signed-in user the backend has never heard of.
    """
    user = db.get_user_by_email(GUEST_EMAIL)
    if user is None:
        try:
            org = db.create_org(GUEST_ORG_NAME)
            user = db.create_user(
                org_id=org.org_id,
                email=GUEST_EMAIL,
                plain_password=secrets.token_hex(32),
                role=Role.auditor,
            )
            logger.info("Guest demo account created: org=%s user=%s", org.name, user.email)
        except sqlite3.IntegrityError:
            # Lost a race with a concurrent guest login that created it first.
            user = db.get_user_by_email(GUEST_EMAIL)
            if user is None:
                raise
    return TokenResponse(
        access_token=create_access_token(user.user_id, user.role.value, user.org_id),
        refresh_token=create_refresh_token(user.user_id),
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: AuthDB = Depends(_get_auth_db)):
    user = db.get_user_by_email(body.email)
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Account inactive")
    logger.info("User logged in: %s", user.email)
    return TokenResponse(
        access_token=create_access_token(user.user_id, user.role.value, user.org_id),
        refresh_token=create_refresh_token(user.user_id),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshRequest, db: AuthDB = Depends(_get_auth_db)):
    try:
        user_id = decode_refresh_token(body.refresh_token)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")
    user = db.get_user_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return TokenResponse(
        access_token=create_access_token(user.user_id, user.role.value, user.org_id),
        refresh_token=create_refresh_token(user.user_id),
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(require_auth)):
    return _user_response(current_user)
