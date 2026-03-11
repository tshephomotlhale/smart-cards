import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.patient import CardStatus, Patient, PatientCard
from app.schemas.patient import PatientCreate


async def register_patient(db: AsyncSession, payload: PatientCreate) -> tuple[Patient, PatientCard]:
    if payload.national_id:
        existing = await db.execute(select(Patient).where(Patient.national_id == payload.national_id))
        if existing.scalar_one_or_none():
            raise ValueError("A patient with this national ID is already registered")

    patient = Patient(**payload.model_dump())
    db.add(patient)
    await db.flush()

    card = PatientCard(
        patient_id=patient.id,
        card_token=str(uuid.uuid4()),
        status=CardStatus.ACTIVE,
    )
    db.add(card)
    await db.commit()
    await db.refresh(patient)
    await db.refresh(card)
    return patient, card


async def get_by_card_token(db: AsyncSession, token: str) -> PatientCard | None:
    result = await db.execute(
        select(PatientCard)
        .where(PatientCard.card_token == token, PatientCard.status == CardStatus.ACTIVE)
        .options(selectinload(PatientCard.patient))
    )
    return result.scalar_one_or_none()


async def deactivate_card(db: AsyncSession, card_token: str, reason: str = "lost") -> PatientCard:
    card = await get_by_card_token(db, card_token)
    if not card:
        raise ValueError("Active card not found")

    card.status = CardStatus.LOST if reason == "lost" else CardStatus.DEACTIVATED

    new_card = PatientCard(
        patient_id=card.patient_id,
        card_token=str(uuid.uuid4()),
        status=CardStatus.ACTIVE,
        notes=f"Replacement for {card_token}",
    )
    db.add(new_card)
    await db.commit()
    await db.refresh(new_card)
    return new_card
