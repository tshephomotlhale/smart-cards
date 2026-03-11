from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import require_receptionist_or_above
from app.schemas.patient import CardResponse, PatientCreate, PatientResponse
from app.services.patient import service as patient_svc

router = APIRouter(prefix="/patients", tags=["patients"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_patient(
    payload: PatientCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_receptionist_or_above),
):
    try:
        patient, card = await patient_svc.register_patient(db, payload)
        return {
            "patient_id": patient.id,
            "full_name": patient.full_name,
            "card_token": card.card_token,
            "message": "Patient registered. Show card token as QR code.",
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/card/{token}", response_model=dict)
async def lookup_by_card(
    token: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_receptionist_or_above),
):
    card = await patient_svc.get_by_card_token(db, token)
    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found or deactivated")
    return {
        "patient_id": card.patient.id,
        "full_name": card.patient.full_name,
        "phone": card.patient.phone,
        "card_status": card.status,
    }


@router.post("/card/{token}/deactivate")
async def deactivate_card(
    token: str,
    reason: str = "lost",
    db: AsyncSession = Depends(get_db),
    _=Depends(require_receptionist_or_above),
):
    try:
        new_card = await patient_svc.deactivate_card(db, token, reason)
        return {"new_card_token": new_card.card_token, "message": "Card replaced. Issue new card to patient."}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
