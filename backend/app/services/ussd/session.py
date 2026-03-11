import json

import redis.asyncio as aioredis

SESSION_TTL_SECONDS = 300  # 5 min USSD session


def _session_key(session_id: str) -> str:
    return f"ussd:session:{session_id}"


async def get_session(redis: aioredis.Redis, session_id: str) -> dict:
    raw = await redis.get(_session_key(session_id))
    return json.loads(raw) if raw else {}


async def set_session(redis: aioredis.Redis, session_id: str, data: dict) -> None:
    await redis.setex(_session_key(session_id), SESSION_TTL_SECONDS, json.dumps(data))


async def clear_session(redis: aioredis.Redis, session_id: str) -> None:
    await redis.delete(_session_key(session_id))
