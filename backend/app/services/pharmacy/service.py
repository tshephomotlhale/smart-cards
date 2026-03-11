from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.patient import Patient
from app.models.pharmacy import Medicine, Prescription, PrescriptionItem, StockEvent, StockEventType, StockLedger
from app.models.visit import Visit, VisitState
from app.schemas.pharmacy import DispenseRequest, PrescriptionCreate, StockLevelResponse
from app.services.notifications import events, sms


async def create_prescription(db: AsyncSession, payload: PrescriptionCreate, doctor_id: int) -> Prescription:
    result = await db.execute(select(Visit).where(Visit.id == payload.visit_id))
    visit = result.scalar_one_or_none()
    if not visit:
        raise ValueError("Visit not found")

    prescription = Prescription(
        visit_id=visit.id,
        doctor_id=doctor_id,
        notes=payload.notes,
    )
    db.add(prescription)
    await db.flush()

    for item in payload.items:
        db.add(PrescriptionItem(
            prescription_id=prescription.id,
            medicine_id=item.medicine_id,
            quantity=item.quantity,
            dosage_instructions=item.dosage_instructions,
        ))

    visit.state = VisitState.PRESCRIBED
    await db.commit()
    await db.refresh(prescription)

    # Alert pharmacy dashboard — new prescription pending
    await events.publish(visit.facility_id, "pharmacy", "prescription_pending", {
        "prescription_id": prescription.id,
        "visit_id": visit.id,
        "item_count": len(payload.items),
    })

    return prescription


async def dispense(db: AsyncSession, payload: DispenseRequest) -> Prescription:
    result = await db.execute(
        select(Prescription)
        .where(Prescription.id == payload.prescription_id, Prescription.status == "pending")
        .options(selectinload(Prescription.items))
    )
    prescription = result.scalar_one_or_none()
    if not prescription:
        raise ValueError("Prescription not found or already dispensed")

    visit_result = await db.execute(
        select(Visit).where(Visit.id == prescription.visit_id)
    )
    visit = visit_result.scalar_one()

    low_stock_alerts = []

    for item in prescription.items:
        ledger_result = await db.execute(
            select(StockLedger, Medicine)
            .join(Medicine, StockLedger.medicine_id == Medicine.id)
            .where(
                StockLedger.facility_id == visit.facility_id,
                StockLedger.medicine_id == item.medicine_id,
            )
        )
        row = ledger_result.first()
        if not row:
            raise ValueError(f"No stock record found for medicine_id={item.medicine_id} at this facility")
        ledger, medicine = row
        if ledger.quantity < item.quantity:
            raise ValueError(f"Insufficient stock for {medicine.name} (have {ledger.quantity}, need {item.quantity})")

        ledger.quantity -= item.quantity
        db.add(StockEvent(
            ledger_id=ledger.id,
            event_type=StockEventType.DISPENSED,
            quantity_delta=-item.quantity,
            reference_id=prescription.id,
            recorded_by=payload.pharmacist_id,
        ))

        # Check if stock dropped below threshold
        if ledger.quantity <= medicine.reorder_threshold:
            low_stock_alerts.append((medicine.name, ledger.quantity, medicine.reorder_threshold))

    prescription.status = "dispensed"
    visit.state = VisitState.AT_PHARMACY
    await db.commit()
    await db.refresh(prescription)

    # Notify pharmacy dashboard of low stock items
    for med_name, qty, threshold in low_stock_alerts:
        await events.publish(visit.facility_id, "pharmacy", "low_stock", {
            "medicine_name": med_name,
            "current_quantity": qty,
            "reorder_threshold": threshold,
        })

    # SMS patient — prescription ready
    patient_result = await db.execute(select(Patient).where(Patient.id == visit.patient_id))
    patient = patient_result.scalar_one_or_none()
    if patient and patient.phone:
        await sms.notify_prescription_ready(patient.phone, patient.full_name)

    return prescription


async def get_stock_levels(db: AsyncSession, facility_id: int) -> list[StockLevelResponse]:
    result = await db.execute(
        select(StockLedger, Medicine)
        .join(Medicine, StockLedger.medicine_id == Medicine.id)
        .where(StockLedger.facility_id == facility_id)
    )
    rows = result.all()
    return [
        StockLevelResponse(
            medicine_id=medicine.id,
            medicine_name=medicine.name,
            quantity=ledger.quantity,
            reorder_threshold=medicine.reorder_threshold,
            is_low=ledger.quantity <= medicine.reorder_threshold,
        )
        for ledger, medicine in rows
    ]


async def get_demand_signals(db: AsyncSession, facility_id: int) -> list[dict]:
    """Return medicines likely to be needed based on pending prescriptions."""
    result = await db.execute(
        select(PrescriptionItem, Medicine)
        .join(Prescription, PrescriptionItem.prescription_id == Prescription.id)
        .join(Visit, Prescription.visit_id == Visit.id)
        .join(Medicine, PrescriptionItem.medicine_id == Medicine.id)
        .where(Visit.facility_id == facility_id, Prescription.status == "pending")
    )
    rows = result.all()
    demand: dict[int, dict] = {}
    for item, medicine in rows:
        if medicine.id not in demand:
            demand[medicine.id] = {"medicine_id": medicine.id, "name": medicine.name, "total_needed": 0}
        demand[medicine.id]["total_needed"] += item.quantity
    return list(demand.values())
