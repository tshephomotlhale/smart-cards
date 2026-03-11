"""
SMS notifications via Africa's Talking.
Falls back to a log-only mode if AT_API_KEY is not configured (dev/sandbox).
"""

import logging

import africastalking

from app.core.config import settings

logger = logging.getLogger(__name__)

_initialized = False


def _init_at() -> bool:
    global _initialized
    if _initialized:
        return True
    if not settings.AT_API_KEY or settings.AT_API_KEY == "your_africastalking_api_key":
        logger.warning("Africa's Talking API key not set — SMS will be logged only")
        return False
    try:
        africastalking.initialize(settings.AT_USERNAME, settings.AT_API_KEY)
        _initialized = True
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Africa's Talking: {e}")
        return False


async def send_sms(phone: str, message: str) -> bool:
    """Send an SMS. Returns True on success, False on failure."""
    if not phone:
        return False

    # Normalise Botswana numbers to international format
    if phone.startswith("0"):
        phone = "+267" + phone[1:]
    elif not phone.startswith("+"):
        phone = "+267" + phone

    if not _init_at():
        logger.info(f"[SMS LOG] To: {phone} | Message: {message}")
        return True  # Don't fail the request just because SMS is in log mode

    try:
        sms = africastalking.SMS
        response = sms.send(message, [phone], sender_id=settings.AT_SENDER_ID)
        logger.info(f"SMS sent to {phone}: {response}")
        return True
    except Exception as e:
        logger.error(f"SMS failed to {phone}: {e}")
        return False


# ── Pre-built message templates ────────────────────────────────────────────

async def notify_checkin(phone: str, patient_name: str, queue_position: int, wait_minutes: int) -> bool:
    name = patient_name.split()[0]
    msg = (
        f"Hi {name}, you have checked in at the clinic. "
        f"You are #{queue_position} in the queue. "
        f"Estimated wait: {wait_minutes} mins. "
        f"Please stay nearby."
    )
    return await send_sms(phone, msg)


async def notify_called(phone: str, patient_name: str, room: str = "") -> bool:
    name = patient_name.split()[0]
    room_text = f" Please proceed to {room}." if room else " Please proceed to the consultation room."
    msg = f"Hi {name}, the nurse is ready to see you.{room_text}"
    return await send_sms(phone, msg)


async def notify_prescription_ready(phone: str, patient_name: str) -> bool:
    name = patient_name.split()[0]
    msg = f"Hi {name}, your prescription is ready. Please proceed to the pharmacy counter."
    return await send_sms(phone, msg)


async def notify_low_stock(phone: str, medicine_name: str, current_qty: int, facility_name: str) -> bool:
    msg = (
        f"STOCK ALERT [{facility_name}]: {medicine_name} is low. "
        f"Current stock: {current_qty} units. Please reorder."
    )
    return await send_sms(phone, msg)
