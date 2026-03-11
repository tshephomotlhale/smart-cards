from datetime import date

from pydantic import BaseModel


class PatientCreate(BaseModel):
    full_name: str
    national_id: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    phone: str | None = None
    address: str | None = None
    emergency_contact: str | None = None
    known_allergies: str | None = None
    consent_given: bool = False


class PatientResponse(BaseModel):
    id: int
    full_name: str
    national_id: str | None
    phone: str | None
    gender: str | None

    model_config = {"from_attributes": True}


class CardResponse(BaseModel):
    card_token: str
    status: str
    patient: PatientResponse

    model_config = {"from_attributes": True}
