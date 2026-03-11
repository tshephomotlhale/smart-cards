"""
Server-Sent Events (SSE) broadcast system.

How it works:
- Each connected dashboard client subscribes to a channel (e.g. "facility:1:nurse")
- When something happens (new arrival, triage, low stock), we publish an event
- All subscribed clients receive it instantly via their open SSE connection

Channels:
  facility:{id}:reception  → new arrivals, walk-ins
  facility:{id}:nurse      → new patients to triage, symptom submissions
  facility:{id}:doctor     → triaged patients ready for consultation
  facility:{id}:pharmacy   → prescriptions ready, low-stock alerts
  facility:{id}:queue      → any queue position change (for queue board display)
"""

import asyncio
import json
from collections import defaultdict
from typing import AsyncGenerator

# channel_name → set of asyncio.Queue instances (one per connected client)
_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)


def _channel(facility_id: int, role: str) -> str:
    return f"facility:{facility_id}:{role}"


async def subscribe(facility_id: int, role: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=50)
    _subscribers[_channel(facility_id, role)].add(q)
    return q


def unsubscribe(facility_id: int, role: str, q: asyncio.Queue) -> None:
    channel = _channel(facility_id, role)
    _subscribers[channel].discard(q)
    if not _subscribers[channel]:
        del _subscribers[channel]


async def publish(facility_id: int, role: str, event_type: str, data: dict) -> None:
    """Publish an event to all clients subscribed to this facility+role channel."""
    channel = _channel(facility_id, role)
    if channel not in _subscribers:
        return
    message = json.dumps({"type": event_type, "data": data})
    dead = set()
    for q in _subscribers[channel]:
        try:
            q.put_nowait(message)
        except asyncio.QueueFull:
            dead.add(q)
    for q in dead:
        _subscribers[channel].discard(q)


async def publish_to_roles(facility_id: int, roles: list[str], event_type: str, data: dict) -> None:
    """Publish the same event to multiple role channels at once."""
    for role in roles:
        await publish(facility_id, role, event_type, data)


async def event_stream(facility_id: int, role: str) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE-formatted strings.
    Yields a heartbeat every 15s to keep the connection alive.
    """
    q = await subscribe(facility_id, role)
    try:
        yield "data: {\"type\": \"connected\"}\n\n"
        while True:
            try:
                message = await asyncio.wait_for(q.get(), timeout=15.0)
                yield f"data: {message}\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
    finally:
        unsubscribe(facility_id, role, q)
