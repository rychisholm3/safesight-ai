"""
Password hashing and JWT token creation/verification.

Tokens are signed HS256 JWTs.  The secret key is read from the
SAFESIGHT_SECRET_KEY environment variable; if it is not set a random
key is generated at startup (fine for development, breaks on restart).
"""
import os
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_SECRET_KEY: str = os.environ.get(
    "SAFESIGHT_SECRET_KEY", secrets.token_hex(32)
)
_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8   # 8 hours
_REFRESH_TOKEN_EXPIRE_DAYS   = 30


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, role: str, org_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "role": role, "org_id": org_id,
         "type": "access", "exp": expire},
        _SECRET_KEY, algorithm=_ALGORITHM,
    )


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=_REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "type": "refresh", "exp": expire},
        _SECRET_KEY, algorithm=_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    """Return payload dict, or raise JWTError on invalid/expired token."""
    payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
    if payload.get("type") != "access":
        raise JWTError("not an access token")
    return payload


def decode_refresh_token(token: str) -> str:
    """Return user_id, or raise JWTError on invalid/expired token."""
    payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
    if payload.get("type") != "refresh":
        raise JWTError("not a refresh token")
    return payload["sub"]
