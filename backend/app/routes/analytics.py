from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import require_receptionist_or_above
from app.services.analytics import service as analytics_svc

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard/{facility_id}")
async def dashboard(
    facility_id: int,
    target_date: date = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_receptionist_or_above),
):
    """All KPIs in one call — used by the admin dashboard summary cards."""
    return await analytics_svc.get_dashboard(db, facility_id, target_date or date.today())


@router.get("/throughput/{facility_id}")
async def throughput(
    facility_id: int,
    target_date: date = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_receptionist_or_above),
):
    return await analytics_svc.get_throughput(db, facility_id, target_date or date.today())


@router.get("/funnel/{facility_id}")
async def visit_funnel(
    facility_id: int,
    target_date: date = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_receptionist_or_above),
):
    """Visit funnel — shows patient drop-off at each stage."""
    return await analytics_svc.get_visit_funnel(db, facility_id, target_date or date.today())


@router.get("/wait-times/{facility_id}")
async def wait_times(
    facility_id: int,
    target_date: date = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_receptionist_or_above),
):
    """Avg / max / min time from arrival to triage (minutes)."""
    return await analytics_svc.get_wait_time_stats(db, facility_id, target_date or date.today())


@router.get("/adoption/{facility_id}")
async def digital_adoption(
    facility_id: int,
    target_date: date = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_receptionist_or_above),
):
    """Digital intake adoption rate — % of visits using app / USSD / kiosk."""
    return await analytics_svc.get_digital_adoption(db, facility_id, target_date or date.today())


@router.get("/stock/{facility_id}")
async def stock_health(
    facility_id: int,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_receptionist_or_above),
):
    """Stock health — healthy / low / stockout breakdown per medicine."""
    return await analytics_svc.get_stock_health(db, facility_id)
