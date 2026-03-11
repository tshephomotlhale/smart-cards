from fastapi import APIRouter, Depends, Form
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.db.redis import get_redis
from app.db.session import get_db
from app.services.ussd.handler import handle

router = APIRouter(prefix="/ussd", tags=["ussd"])


@router.post("/webhook")
async def ussd_webhook(
    sessionId: str = Form(...),
    phoneNumber: str = Form(...),
    serviceCode: str = Form(...),
    text: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """Africa's Talking USSD callback endpoint."""
    response = await handle(db, redis, sessionId, phoneNumber, text)
    # Africa's Talking expects plain text response
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content=response)
