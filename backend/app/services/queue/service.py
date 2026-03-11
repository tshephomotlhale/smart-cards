import json

import redis.asyncio as aioredis

URGENCY_SCORE = {
    "emergency": 1,
    "urgent": 10,
    "semi_urgent": 100,
    "non_urgent": 1000,
}

AVG_CONSULT_MINUTES = 12  # baseline estimate, can be tuned per facility


def _queue_key(facility_id: int, service_class: str) -> str:
    return f"queue:{facility_id}:{service_class}"


async def enqueue(
    redis: aioredis.Redis,
    facility_id: int,
    visit_id: int,
    service_class: str = "general",
    urgency: str = "non_urgent",
) -> int:
    key = _queue_key(facility_id, service_class)
    score = URGENCY_SCORE.get(urgency, 1000)
    await redis.zadd(key, {str(visit_id): score}, nx=True)
    position = await redis.zrank(key, str(visit_id))
    return (position or 0) + 1


async def get_position(redis: aioredis.Redis, facility_id: int, visit_id: int, service_class: str = "general") -> int | None:
    key = _queue_key(facility_id, service_class)
    rank = await redis.zrank(key, str(visit_id))
    return (rank + 1) if rank is not None else None


async def estimate_wait(redis: aioredis.Redis, facility_id: int, visit_id: int, service_class: str = "general") -> int:
    position = await get_position(redis, facility_id, visit_id, service_class)
    if position is None:
        return 0
    # Simple model: position × avg consult time, assuming 2 doctors on average
    doctors_available = 2
    return max(0, (position - 1) * AVG_CONSULT_MINUTES // doctors_available)


async def dequeue(redis: aioredis.Redis, facility_id: int, visit_id: int, service_class: str = "general") -> None:
    key = _queue_key(facility_id, service_class)
    await redis.zrem(key, str(visit_id))


async def get_queue_snapshot(redis: aioredis.Redis, facility_id: int, service_class: str = "general") -> list[dict]:
    key = _queue_key(facility_id, service_class)
    members = await redis.zrange(key, 0, -1, withscores=True)
    return [{"visit_id": int(m), "score": s, "position": i + 1} for i, (m, s) in enumerate(members)]
