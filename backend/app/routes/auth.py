from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import get_current_user, require_admin
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.auth import service as auth_svc

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await auth_svc.login(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_staff(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    try:
        user = await auth_svc.register_staff(db, payload, current_user.role)
        return {"id": user.id, "email": user.email, "role": user.role}
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
