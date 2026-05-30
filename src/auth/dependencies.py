"""
FastAPI dependency functions for authentication and RBAC.

Usage
-----
    @router.get("/events")
    def list_events(current_user: User = Depends(require_auth)):
        ...

    @router.delete("/incidents/{id}")
    def close_incident(current_user: User = Depends(require_role(Role.site_manager))):
        ...
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from src.auth.models import Role, User
from src.auth.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)

_ROLE_HIERARCHY: dict[Role, int] = {
    Role.auditor:        0,
    Role.executive:      1,
    Role.site_manager:   2,
    Role.safety_officer: 3,
}


def _get_auth_db():
    """Yields the AuthDB singleton. Overridden in tests via app.dependency_overrides."""
    from src.api.main import auth_db
    return auth_db


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db=Depends(_get_auth_db),
) -> User:
    """Extract and validate the Bearer JWT. Returns the User row."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user = db.get_user_by_id(payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def require_role(*roles: Role):
    """Return a dependency that enforces at least one of the given roles."""
    def _dep(current_user: User = Depends(require_auth)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role.value}' is not permitted for this action",
            )
        return current_user
    return _dep


def require_min_role(min_role: Role):
    """Return a dependency that enforces a minimum role level by hierarchy."""
    min_level = _ROLE_HIERARCHY[min_role]
    def _dep(current_user: User = Depends(require_auth)) -> User:
        if _ROLE_HIERARCHY.get(current_user.role, -1) < min_level:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions",
            )
        return current_user
    return _dep
