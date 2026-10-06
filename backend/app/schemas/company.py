import uuid
from datetime import datetime
from pydantic import BaseModel


class CompanyOut(BaseModel):
    id: uuid.UUID
    name: str
    industry: str
    contact_name: str
    contact_email: str
    gst_number: str
    tier: str
    document_path: str | None
    is_active: bool = True
    onboarded_on: datetime

    class Config:
        from_attributes = True


class CompanyStatusUpdate(BaseModel):
    is_active: bool
