from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.db.redis import get_redis
from app.db.session import get_db
from app.middleware.auth import get_current_user, require_nurse_or_above, require_receptionist_or_above
from app.schemas.visit import ArriveRequest, SymptomSubmitRequest, TriageRequest, VisitResponse, WalkInRequest
from app.services.visit import service as visit_svc

router = APIRouter(prefix="/visits", tags=["visits"])


@router.post("/arrive", response_model=VisitResponse)
async def arrive_by_card(
    payload: ArriveRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Card tap endpoint — authenticated via card token, not JWT."""
    try:
        visit = await visit_svc.arrive_by_card(db, redis, payload)
        return visit
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/walkin", response_model=VisitResponse)
async def walkin(
    payload: WalkInRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    _=Depends(require_receptionist_or_above),
):
    visit = await visit_svc.arrive_walkin(db, redis, payload.patient_id, payload.facility_id, payload.service_class)
    return visit


@router.post("/symptoms")
async def submit_symptoms(
    payload: SymptomSubmitRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        visit = await visit_svc.submit_symptoms(db, payload)
        return {"visit_id": visit.id, "state": visit.state}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/triage", response_model=VisitResponse)
async def triage(
    payload: TriageRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    current_user=Depends(require_nurse_or_above),
):
    try:
        visit = await visit_svc.triage_visit(db, redis, payload, current_user.user_id)
        return visit
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
