"""
Run once to seed reference data: facilities + medicine catalog + stock ledger.
Usage: python -m app.db.seed
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, engine
from app.models.base import Base
from app.models import audit, patient, visit  # noqa: F401 — registers all models with Base
from app.models.facility import Facility
from app.models.pharmacy import Medicine, StockLedger
from app.models.user import User, UserRole
from app.core.security import hash_password

FACILITIES = [
    {"name": "Princess Marina Hospital", "facility_type": "hospital", "district": "South East", "address": "Gaborone"},
    {"name": "Scottish Livingstone Hospital", "facility_type": "hospital", "district": "South East", "address": "Molepolole"},
    {"name": "Nyangabgwe Referral Hospital", "facility_type": "hospital", "district": "North East", "address": "Francistown"},
    {"name": "Maun General Hospital", "facility_type": "hospital", "district": "North West", "address": "Maun"},
    {"name": "Athlone Clinic", "facility_type": "clinic", "district": "South East", "address": "Gaborone"},
    {"name": "Bontleng Clinic", "facility_type": "clinic", "district": "South East", "address": "Gaborone"},
    {"name": "Broadhurst Clinic", "facility_type": "clinic", "district": "South East", "address": "Gaborone"},
    {"name": "Naledi Clinic", "facility_type": "clinic", "district": "South East", "address": "Gaborone"},
]

MEDICINES = [
    {"name": "Paracetamol 500mg", "generic_name": "Paracetamol", "unit": "tablets", "reorder_threshold": 500, "category": "analgesic"},
    {"name": "Amoxicillin 250mg", "generic_name": "Amoxicillin", "unit": "capsules", "reorder_threshold": 200, "category": "antibiotic"},
    {"name": "Metformin 500mg", "generic_name": "Metformin", "unit": "tablets", "reorder_threshold": 300, "category": "antidiabetic"},
    {"name": "Atenolol 50mg", "generic_name": "Atenolol", "unit": "tablets", "reorder_threshold": 200, "category": "antihypertensive"},
    {"name": "Oral Rehydration Salts", "generic_name": "ORS", "unit": "sachets", "reorder_threshold": 100, "category": "rehydration"},
    {"name": "Artemether/Lumefantrine 20/120mg", "generic_name": "AL", "unit": "tablets", "reorder_threshold": 150, "category": "antimalarial"},
    {"name": "Cotrimoxazole 480mg", "generic_name": "Cotrimoxazole", "unit": "tablets", "reorder_threshold": 200, "category": "antibiotic"},
    {"name": "Ibuprofen 400mg", "generic_name": "Ibuprofen", "unit": "tablets", "reorder_threshold": 300, "category": "analgesic"},
]


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # Seed facilities (skip if already seeded)
        existing_facilities = (await db.execute(select(Facility))).scalars().all()
        if not existing_facilities:
            for f in FACILITIES:
                db.add(Facility(**f))
            await db.flush()
            print("  Facilities seeded.")
        else:
            print("  Facilities already present — skipping.")

        # Seed medicines (skip if already seeded)
        existing_medicines = (await db.execute(select(Medicine))).scalars().all()
        if not existing_medicines:
            for m in MEDICINES:
                db.add(Medicine(**m, lead_time_days=7))
            await db.flush()
            print("  Medicines seeded.")
        else:
            print("  Medicines already present — skipping.")

        # Seed stock ledger — one record per (facility, medicine)
        # Quantities varied to make analytics interesting for the demo:
        #   - Most medicines healthy (above threshold)
        #   - A few deliberately low/stockout to trigger alerts
        existing_stock = (await db.execute(select(StockLedger))).scalars().first()
        if existing_stock:
            print("  Stock ledger already present — skipping.")
        else:
            facilities_result = await db.execute(select(Facility))
            facilities = facilities_result.scalars().all()

            medicines_result = await db.execute(select(Medicine))
            medicines = medicines_result.scalars().all()

            # [qty_hospital, qty_clinic] per medicine (matches MEDICINES list order)
            STOCK_TEMPLATE = [
                [2500, 1200],  # Paracetamol — healthy everywhere
                [800, 180],    # Amoxicillin — clinics at 180, threshold=200 → LOW
                [1500, 600],   # Metformin — healthy
                [900, 400],    # Atenolol — stockout overridden below
                [500, 250],    # ORS — healthy
                [160, 80],     # Artemether/Lumefantrine — hospitals 160 > threshold 150 (borderline), clinics 80 → LOW
                [1000, 450],   # Cotrimoxazole — healthy
                [1200, 350],   # Ibuprofen — stockout overridden below
            ]

            for f_idx, facility in enumerate(facilities):
                is_clinic = facility.facility_type == "clinic"
                for m_idx, medicine in enumerate(medicines):
                    qty_hosp, qty_clinic = STOCK_TEMPLATE[m_idx]
                    qty = qty_clinic if is_clinic else qty_hosp

                    # Atenolol: stockout at Athlone Clinic (index 4)
                    if m_idx == 3 and f_idx == 4:
                        qty = 0
                    # Ibuprofen: stockout at Naledi Clinic (index 7)
                    if m_idx == 7 and f_idx == 7:
                        qty = 0

                    db.add(StockLedger(
                        facility_id=facility.id,
                        medicine_id=medicine.id,
                        quantity=qty,
                    ))
            print(f"  Stock ledger seeded ({len(facilities) * len(medicines)} records).")

        # Create default admin user (skip if exists)
        existing_admin = (await db.execute(select(User).where(User.email == "admin@smartcards.bw"))).scalar_one_or_none()
        if not existing_admin:
            admin = User(
                email="admin@smartcards.bw",
                full_name="System Administrator",
                hashed_password=hash_password("Admin1234!"),
                role=UserRole.ADMIN,
            )
            db.add(admin)
            print("  Admin user created.")
        else:
            print("  Admin user already present — skipping.")

        await db.commit()
        print("Seed complete.")
        print("Admin login: admin@smartcards.bw / Admin1234!")
        print("IMPORTANT: Change the admin password immediately in production.")


if __name__ == "__main__":
    asyncio.run(seed())
