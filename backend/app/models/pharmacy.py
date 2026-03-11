import enum

from sqlalchemy import Date, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class StockEventType(str, enum.Enum):
    RECEIVED = "received"
    DISPENSED = "dispensed"
    ADJUSTED = "adjusted"
    EXPIRED = "expired"
    WASTAGE = "wastage"


class Medicine(Base, TimestampMixin):
    __tablename__ = "medicine_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    generic_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)  # tablets, ml, vials
    reorder_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    stock: Mapped[list["StockLedger"]] = relationship(back_populates="medicine")


class StockLedger(Base, TimestampMixin):
    __tablename__ = "stock_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False)
    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicine_catalog.id"), nullable=False)
    batch_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    expiry_date: Mapped[str | None] = mapped_column(Date, nullable=True)

    facility: Mapped["Facility"] = relationship(back_populates="stock_ledger")  # noqa: F821
    medicine: Mapped["Medicine"] = relationship(back_populates="stock")
    events: Mapped[list["StockEvent"]] = relationship(back_populates="ledger")


class StockEvent(Base, TimestampMixin):
    __tablename__ = "stock_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ledger_id: Mapped[int] = mapped_column(ForeignKey("stock_ledger.id"), nullable=False)
    event_type: Mapped[StockEventType] = mapped_column(Enum(StockEventType), nullable=False)
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # prescription_id or transfer_id
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    ledger: Mapped["StockLedger"] = relationship(back_populates="events")


class Prescription(Base, TimestampMixin):
    __tablename__ = "prescriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visits.id"), unique=True, nullable=False)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)  # pending, dispensed
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    visit: Mapped["Visit"] = relationship(back_populates="prescription")  # noqa: F821
    items: Mapped[list["PrescriptionItem"]] = relationship(back_populates="prescription")


class PrescriptionItem(Base, TimestampMixin):
    __tablename__ = "prescription_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    prescription_id: Mapped[int] = mapped_column(ForeignKey("prescriptions.id"), nullable=False)
    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicine_catalog.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    dosage_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    prescription: Mapped["Prescription"] = relationship(back_populates="items")
