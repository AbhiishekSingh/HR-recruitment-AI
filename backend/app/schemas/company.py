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
    onboarded_on: datetime

    class Config:
        from_attributes = True