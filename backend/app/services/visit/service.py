from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import redis.asyncio as aioredis

from app.models.patient import Patient
from app.models.visit import SymptomEntry, TriageEntry, Visit, VisitState
from app.schemas.visit import ArriveRequest, SymptomSubmitRequest, TriageRequest
from app.services.patient.service import get_by_card_token
from app.services.queue import service as queue_svc
from app.services.notifications import events, sms


async def arrive_by_card(db: AsyncSession, redis: aioredis.Redis, payload: ArriveRequest) -> Visit:
    card = await get_by_card_token(db, payload.card_token)
    if not card:
        raise ValueError("Card not found or deactivated")

    visit = Visit(
        patient_id=card.patient_id,
        facility_id=payload.facility_id,
        service_class=payload.service_class,
        state=VisitState.ARRIVED,
    )
    db.add(visit)
    await db.flush()

    position = await queue_svc.enqueue(redis, payload.facility_id, visit.id, payload.service_class)
    wait = await queue_svc.estimate_wait(redis, payload.facility_id, visit.id, payload.service_class)
    visit.queue_position = position
    visit.estimated_wait_minutes = wait

    await db.commit()
    await db.refresh(visit)

    # Notify reception + nurse dashboards
    patient = card.patient
    await events.publish_to_roles(payload.facility_id, ["reception", "nurse", "queue"], "new_arrival", {
        "visit_id": visit.id,
        "patient_name": patient.full_name,
        "queue_position": position,
        "estimated_wait_minutes": wait,
        "service_class": payload.service_class,
    })
    # SMS confirmation to patient
    if patient.phone:
        await sms.notify_checkin(patient.phone, patient.full_name, position, wait)

    return visit


async def arrive_walkin(db: AsyncSession, redis: aioredis.Redis, patient_id: int, facility_id: int, service_class: str = "general") -> Visit:
    visit = Visit(
        patient_id=patient_id,
        facility_id=facility_id,
        service_class=service_class,
        state=VisitState.ARRIVED,
    )
    db.add(visit)
    await db.flush()

    position = await queue_svc.enqueue(redis, facility_id, visit.id, service_class)
    wait = await queue_svc.estimate_wait(redis, facility_id, visit.id, service_class)
    visit.queue_position = position
    visit.estimated_wait_minutes = wait

    await db.commit()
    await db.refresh(visit)

    # Load patient for notifications
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()

    await events.publish_to_roles(facility_id, ["reception", "nurse", "queue"], "new_arrival", {
        "visit_id": visit.id,
        "patient_name": patient.full_name if patient else "Walk-in",
        "queue_position": position,
        "estimated_wait_minutes": wait,
        "service_class": service_class,
    })
    if patient and patient.phone:
        await sms.notify_checkin(patient.phone, patient.full_name, position, wait)

    return visit


async def submit_symptoms(db: AsyncSession, payload: SymptomSubmitRequest) -> Visit:
    result = await db.execute(
        select(Visit).where(Visit.id == payload.visit_id).options(selectinload(Visit.patient))
    )
    visit = result.scalar_one_or_none()
    if not visit:
        raise ValueError("Visit not found")

    for question_key, answer in payload.answers.items():
        db.add(SymptomEntry(
            visit_id=visit.id,
            question_key=question_key,
            answer=answer,
            channel=payload.channel,
        ))

    visit.state = VisitState.SYMPTOMS_SUBMITTED
    await db.commit()
    await db.refresh(visit)

    # Alert nurse dashboard that symptoms are ready for review
    await events.publish(visit.facility_id, "nurse", "symptoms_submitted", {
        "visit_id": visit.id,
        "patient_id": visit.patient_id,
        "channel": payload.channel,
        "answer_count": len(payload.answers),
    })

    return visit


async def triage_visit(db: AsyncSession, redis: aioredis.Redis, payload: TriageRequest, nurse_id: int) -> Visit:
    result = await db.execute(
        select(Visit)
        .where(Visit.id == payload.visit_id)
        .options(selectinload(Visit.symptoms), selectinload(Visit.patient))
    )
    visit = result.scalar_one_or_none()
    if not visit:
        raise ValueError("Visit not found")

    summary = _build_symptom_summary(visit.symptoms)

    triage = TriageEntry(
        visit_id=visit.id,
        urgency_level=payload.urgency_level,
        nurse_id=nurse_id,
        notes=payload.notes,
        symptom_summary=summary,
    )
    db.add(triage)

    # Re-enqueue with urgency score
    await queue_svc.dequeue(redis, visit.facility_id, visit.id, visit.service_class)
    position = await queue_svc.enqueue(
        redis, visit.facility_id, visit.id, visit.service_class, payload.urgency_level.value
    )
    wait = await queue_svc.estimate_wait(redis, visit.facility_id, visit.id, visit.service_class)

    visit.state = VisitState.TRIAGED
    visit.queue_position = position
    visit.estimated_wait_minutes = wait

    await db.commit()
    await db.refresh(visit)

    patient = visit.patient
    # Alert doctor dashboard — patient is ready for consultation
    await events.publish_to_roles(visit.facility_id, ["doctor", "queue"], "patient_triaged", {
        "visit_id": visit.id,
        "patient_name": patient.full_name if patient else "",
        "urgency_level": payload.urgency_level.value,
        "symptom_summary": summary,
        "queue_position": position,
        "estimated_wait_minutes": wait,
    })
    # SMS patient: you've been called
    if patient and patient.phone:
        await sms.notify_called(patient.phone, patient.full_name)

    return visit


def _build_symptom_summary(symptoms: list[SymptomEntry]) -> str:
    if not symptoms:
        return "No symptoms submitted"
    return " | ".join(f"{s.question_key}: {s.answer}" for s in symptoms)
