from pydantic import BaseModel


class PrescriptionItemCreate(BaseModel):
    medicine_id: int
    quantity: int
    dosage_instructions: str | None = None


class PrescriptionCreate(BaseModel):
    visit_id: int
    items: list[PrescriptionItemCreate]
    notes: str | None = None


class DispenseRequest(BaseModel):
    prescription_id: int
    pharmacist_id: int


class StockLevelResponse(BaseModel):
    medicine_id: int
    medicine_name: str
    quantity: int
    reorder_threshold: int
    is_low: bool

    model_config = {"from_attributes": True}
