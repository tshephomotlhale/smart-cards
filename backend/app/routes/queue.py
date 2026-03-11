from fastapi import APIRouter, Depends

import redis.asyncio as aioredis

from app.db.redis import get_redis
from app.middleware.auth import require_receptionist_or_above
from app.services.queue import service as queue_svc

router = APIRouter(prefix="/queue", tags=["queue"])


@router.get("/{facility_id}")
async def get_queue(
    facility_id: int,
    service_class: str = "general",
    redis: aioredis.Redis = Depends(get_redis),
    _=Depends(require_receptionist_or_above),
):
    snapshot = await queue_svc.get_queue_snapshot(redis, facility_id, service_class)
    return {"facility_id": facility_id, "service_class": service_class, "queue": snapshot}


@router.get("/{facility_id}/wait/{visit_id}")
async def get_wait_time(
    facility_id: int,
    visit_id: int,
    service_class: str = "general",
    redis: aioredis.Redis = Depends(get_redis),
):
    position = await queue_svc.get_position(redis, facility_id, visit_id, service_class)
    wait = await queue_svc.estimate_wait(redis, facility_id, visit_id, service_class)
    return {"visit_id": visit_id, "queue_position": position, "estimated_wait_minutes": wait}
