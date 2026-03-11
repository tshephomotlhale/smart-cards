from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_token
from app.models.user import UserRole

bearer_scheme = HTTPBearer()


class TokenData:
    def __init__(self, user_id: int, role: UserRole, facility_id: int | None):
        self.user_id = user_id
        self.role = role
        self.facility_id = facility_id


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> TokenData:
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise ValueError("Not an access token")
        return TokenData(
            user_id=int(payload["sub"]),
            role=UserRole(payload["role"]),
            facility_id=payload.get("facility_id"),
        )
    except (ValueError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_roles(*roles: UserRole):
    async def _check(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not permitted for this action",
            )
        return current_user
    return _check


# Convenience role guards
require_admin = require_roles(UserRole.ADMIN)
require_nurse_or_above = require_roles(UserRole.NURSE, UserRole.DOCTOR, UserRole.ADMIN)
require_doctor = require_roles(UserRole.DOCTOR, UserRole.ADMIN)
require_pharmacist = require_roles(UserRole.PHARMACIST, UserRole.ADMIN)
require_receptionist_or_above = require_roles(
    UserRole.RECEPTIONIST, UserRole.NURSE, UserRole.DOCTOR, UserRole.PHARMACIST, UserRole.ADMIN
)
