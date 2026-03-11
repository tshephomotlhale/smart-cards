from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import require_doctor, require_pharmacist, require_receptionist_or_above
from app.schemas.pharmacy import DispenseRequest, PrescriptionCreate
from app.services.pharmacy import service as pharmacy_svc

router = APIRouter(prefix="/pharmacy", tags=["pharmacy"])


@router.post("/prescriptions", status_code=status.HTTP_201_CREATED)
async def create_prescription(
    payload: PrescriptionCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_doctor),
):
    try:
        rx = await pharmacy_svc.create_prescription(db, payload, current_user.user_id)
        return {"prescription_id": rx.id, "visit_id": rx.visit_id, "status": rx.status}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/dispense")
async def dispense(
    payload: DispenseRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_pharmacist),
):
    try:
        rx = await pharmacy_svc.dispense(db, payload)
        return {"prescription_id": rx.id, "status": rx.status}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/stock/{facility_id}")
async def get_stock(
    facility_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_receptionist_or_above),
):
    levels = await pharmacy_svc.get_stock_levels(db, facility_id)
    return {"facility_id": facility_id, "stock": [l.model_dump() for l in levels]}


@router.get("/demand/{facility_id}")
async def get_demand(
    facility_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_pharmacist),
):
    signals = await pharmacy_svc.get_demand_signals(db, facility_id)
    return {"facility_id": facility_id, "demand_signals": signals}
