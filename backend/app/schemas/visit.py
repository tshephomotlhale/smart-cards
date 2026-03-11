from pydantic import BaseModel

from app.models.visit import UrgencyLevel, VisitState


class ArriveRequest(BaseModel):
    card_token: str
    facility_id: int
    service_class: str = "general"


class WalkInRequest(BaseModel):
    patient_id: int
    facility_id: int
    service_class: str = "general"


class VisitResponse(BaseModel):
    id: int
    patient_id: int
    facility_id: int
    state: VisitState
    queue_position: int | None
    estimated_wait_minutes: int | None
    service_class: str

    model_config = {"from_attributes": True}


class SymptomSubmitRequest(BaseModel):
    visit_id: int
    answers: dict[str, str]  # {question_key: answer}
    channel: str = "app"  # app, ussd, kiosk


class TriageRequest(BaseModel):
    visit_id: int
    urgency_level: UrgencyLevel
    notes: str | None = None
