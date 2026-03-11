from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.middleware.auth import get_current_user
from app.services.notifications.events import event_stream

router = APIRouter(prefix="/events", tags=["events"])

VALID_ROLES = {"reception", "nurse", "doctor", "pharmacy", "queue"}


@router.get("/{facility_id}/{role}")
async def sse_stream(
    facility_id: int,
    role: str,
    current_user=Depends(get_current_user),
):
    """
    SSE endpoint. Connect once and receive real-time events.

    Usage (JavaScript):
      const es = new EventSource('/events/1/nurse', {headers: {Authorization: 'Bearer <token>'}})
      es.onmessage = (e) => console.log(JSON.parse(e.data))

    Roles: reception | nurse | doctor | pharmacy | queue
    """
    if role not in VALID_ROLES:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Invalid role channel. Must be one of: {', '.join(VALID_ROLES)}")

    return StreamingResponse(
        event_stream(facility_id, role),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )
