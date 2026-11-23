"""Pydantic request/response schemas for the prescription API.

PrescriptionIn is the body a physician submits: drug_name, dose, route,
frequency (non-empty, length-bounded strings) plus duration_days and
quantity (positive integers, bounded) with extra fields forbidden so unknown
input is rejected. PrescriptionOut is the response returned after signing or
reading: id, patient_id, physician_id, the clinical fields, status,
signed_at and signature. Validation here keeps malformed or oversized data
out of the database before any storage or audit logic runs.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PrescriptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    drug_name: str = Field(min_length=1, max_length=200)
    dose: str = Field(min_length=1, max_length=100)
    route: str = Field(min_length=1, max_length=50)
    frequency: str = Field(min_length=1, max_length=100)
    duration_days: int = Field(gt=0, le=365)
    quantity: int = Field(gt=0, le=10000)


class PrescriptionOut(PrescriptionIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    patient_id: str
    physician_id: str
    status: str
    signed_at: datetime
    signature: str
