import uuid
from datetime import datetime
from pydantic import BaseModel


class CompanyCreate(BaseModel):
    name: str
    industry: str = ""
    contact_name: str = ""
    contact_email: str = ""
    tier: str = "Standard"


class CompanyOut(BaseModel):
    id: uuid.UUID
    name: str
    industry: str
    contact_name: str
    contact_email: str
    tier: str
    onboarded_on: datetime

    class Config:
        from_attributes = True
