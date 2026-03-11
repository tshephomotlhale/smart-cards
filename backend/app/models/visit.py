import enum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class VisitState(str, enum.Enum):
    ARRIVED = "arrived"
    SYMPTOMS_SUBMITTED = "symptoms_submitted"
    TRIAGED = "triaged"
    IN_CONSULTATION = "in_consultation"
    PRESCRIBED = "prescribed"
    AT_PHARMACY = "at_pharmacy"
    DISCHARGED = "discharged"


class UrgencyLevel(str, enum.Enum):
    EMERGENCY = "emergency"
    URGENT = "urgent"
    SEMI_URGENT = "semi_urgent"
    NON_URGENT = "non_urgent"


class Visit(Base, TimestampMixin):
    __tablename__ = "visits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), nullable=False)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False)
    arrived_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    state: Mapped[VisitState] = mapped_column(Enum(VisitState), default=VisitState.ARRIVED, nullable=False)
    service_class: Mapped[str] = mapped_column(String(50), default="general", nullable=False)
    queue_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_wait_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discharged_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    patient: Mapped["Patient"] = relationship(back_populates="visits")  # noqa: F821
    facility: Mapped["Facility"] = relationship(back_populates="visits")  # noqa: F821
    symptoms: Mapped[list["SymptomEntry"]] = relationship(back_populates="visit")
    triage: Mapped["TriageEntry | None"] = relationship(back_populates="visit", uselist=False)
    prescription: Mapped["Prescription | None"] = relationship(back_populates="visit", uselist=False)  # noqa: F821


class SymptomEntry(Base, TimestampMixin):
    __tablename__ = "symptoms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visits.id"), nullable=False)
    question_key: Mapped[str] = mapped_column(String(100), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), default="app", nullable=False)  # app, ussd, kiosk

    visit: Mapped["Visit"] = relationship(back_populates="symptoms")


class TriageEntry(Base, TimestampMixin):
    __tablename__ = "triage_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    visit_id: Mapped[int] = mapped_column(ForeignKey("visits.id"), unique=True, nullable=False)
    urgency_level: Mapped[UrgencyLevel] = mapped_column(Enum(UrgencyLevel), nullable=False)
    nurse_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    symptom_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    visit: Mapped["Visit"] = relationship(back_populates="triage")
