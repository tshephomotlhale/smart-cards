"""
USSD State Machine
------------------
Africa's Talking sends a POST with:
  sessionId, phoneNumber, serviceCode, text (all inputs joined by *)

We respond with:
  CON <message>   → session continues
  END <message>   → session ends
"""

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ussd.session import clear_session, get_session, set_session
from app.services.visit import service as visit_svc
from app.services.queue import service as queue_svc
from app.schemas.visit import ArriveRequest, SymptomSubmitRequest

# Symptom questions shown over USSD (keep short — USSD has ~182 char limit)
SYMPTOM_QUESTIONS = [
    ("chief_complaint", "1. Main problem?\n1.Fever 2.Cough 3.Pain 4.Vomiting 5.Other"),
    ("duration", "2. How long?\n1.<1 day 2.1-3 days 3.4-7 days 4.>1 week"),
    ("severity", "3. Severity?\n1.Mild 2.Moderate 3.Severe"),
]

SYMPTOM_ANSWERS = {
    "chief_complaint": {"1": "Fever", "2": "Cough", "3": "Pain", "4": "Vomiting", "5": "Other"},
    "duration": {"1": "Less than 1 day", "2": "1-3 days", "3": "4-7 days", "4": "More than 1 week"},
    "severity": {"1": "Mild", "2": "Moderate", "3": "Severe"},
}

DEFAULT_FACILITY_ID = None  # Set at startup via set_default_facility()


def set_default_facility(facility_id: int) -> None:
    global DEFAULT_FACILITY_ID
    DEFAULT_FACILITY_ID = facility_id


async def handle(
    db: AsyncSession,
    redis: aioredis.Redis,
    session_id: str,
    phone: str,
    text: str,
) -> str:
    inputs = [t.strip() for t in text.split("*")] if text else []
    session = await get_session(redis, session_id)

    # ── Main menu ──────────────────────────────────────────────
    if not inputs or inputs == [""]:
        await set_session(redis, session_id, {"step": "main_menu", "phone": phone})
        return "CON Welcome to Smart Patient Card\n1. Check in with card\n2. Check my wait time\n3. Submit symptoms\n4. Register"

    step = session.get("step", "main_menu")

    # ── Menu selection ─────────────────────────────────────────
    if step == "main_menu":
        choice = inputs[-1]
        if choice == "1":
            await set_session(redis, session_id, {**session, "step": "checkin_token"})
            return "CON Enter your card number (printed on card):"
        elif choice == "2":
            return await _wait_time_check(db, redis, session_id, session, inputs)
        elif choice == "3":
            await set_session(redis, session_id, {**session, "step": "symptoms_visit_id"})
            return "CON Enter your visit number (from receipt):"
        elif choice == "4":
            await set_session(redis, session_id, {**session, "step": "register_name"})
            return "CON Enter your full name:"
        else:
            return "END Invalid option. Please try again."

    # ── Check in flow ──────────────────────────────────────────
    if step == "checkin_token":
        card_token = inputs[-1]
        try:
            visit = await visit_svc.arrive_by_card(
                db, redis,
                ArriveRequest(card_token=card_token, facility_id=DEFAULT_FACILITY_ID),
            )
            await set_session(redis, session_id, {**session, "step": "symptoms_q0", "visit_id": visit.id})
            q_key, q_text = SYMPTOM_QUESTIONS[0]
            return f"CON Checked in! Queue #{visit.queue_position}. Est wait: {visit.estimated_wait_minutes} mins\n\n{q_text}"
        except ValueError as e:
            await clear_session(redis, session_id)
            return f"END Error: {e}. Please see reception."

    # ── Symptom questions ──────────────────────────────────────
    if step.startswith("symptoms_q"):
        q_index = int(step.split("_q")[1])
        q_key, _ = SYMPTOM_QUESTIONS[q_index]
        answer_map = SYMPTOM_ANSWERS[q_key]
        answer = answer_map.get(inputs[-1], inputs[-1])

        answers = session.get("answers", {})
        answers[q_key] = answer
        session["answers"] = answers

        next_index = q_index + 1
        if next_index < len(SYMPTOM_QUESTIONS):
            await set_session(redis, session_id, {**session, "step": f"symptoms_q{next_index}"})
            _, next_text = SYMPTOM_QUESTIONS[next_index]
            return f"CON {next_text}"
        else:
            visit_id = session.get("visit_id")
            if visit_id:
                await visit_svc.submit_symptoms(
                    db,
                    SymptomSubmitRequest(visit_id=visit_id, answers=answers, channel="ussd"),
                )
            await clear_session(redis, session_id)
            return "END Symptoms submitted. A nurse will review shortly. Thank you."

    # ── Symptom submit by visit ID ─────────────────────────────
    if step == "symptoms_visit_id":
        try:
            visit_id = int(inputs[-1])
            await set_session(redis, session_id, {**session, "step": "symptoms_q0", "visit_id": visit_id, "answers": {}})
            _, q_text = SYMPTOM_QUESTIONS[0]
            return f"CON {q_text}"
        except ValueError:
            return "END Invalid visit number."

    # ── Wait time check ────────────────────────────────────────
    if step == "wait_time_visit_id":
        return await _wait_time_check(db, redis, session_id, session, inputs)

    await clear_session(redis, session_id)
    return "END Session expired. Please dial again."


async def _wait_time_check(db, redis, session_id, session, inputs):
    if session.get("step") == "main_menu":
        await set_session(redis, session_id, {**session, "step": "wait_time_visit_id"})
        return "CON Enter your visit number:"

    try:
        visit_id = int(inputs[-1])
        wait = await queue_svc.estimate_wait(redis, DEFAULT_FACILITY_ID, visit_id)
        pos = await queue_svc.get_position(redis, DEFAULT_FACILITY_ID, visit_id)
        await clear_session(redis, session_id)
        if pos:
            return f"END You are #{pos} in queue. Estimated wait: {wait} minutes."
        return "END You are not currently in a queue."
    except (ValueError, TypeError):
        return "END Invalid visit number."
