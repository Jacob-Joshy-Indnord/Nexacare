"""HTTP routes for e-prescription entry.

create_router(session_factory) builds the APIRouter. POST
/patients/{patient_id}/prescriptions (sign_prescription): only the physician
role may call it; the patient must belong to the caller's tenant (else 404);
the prescription is stored with status signed, a signed_at time and a SHA-256
signature over its content, and a prescription.sign audit row is written in
the same transaction. Non-physician attempts are audited as denied and get
403. GET /prescriptions/{id} (read_prescription) returns a tenant-scoped
prescription and audits the read. _signature computes the content hash.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import audit
from app.auth import Identity, get_identity
from app.models import Patient, Prescription
from app.schemas import PrescriptionIn, PrescriptionOut


def _signature(rx: Prescription) -> str:
    payload = json.dumps(
        [rx.id, rx.tenant_id, rx.patient_id, rx.physician_id, rx.drug_name, rx.dose,
         rx.route, rx.frequency, rx.duration_days, rx.quantity, rx.signed_at.isoformat()])
    return hashlib.sha256(payload.encode()).hexdigest()


def create_router(session_factory) -> APIRouter:
    router = APIRouter()

    def get_session():
        with session_factory() as s:
            yield s

    @router.post("/patients/{patient_id}/prescriptions", response_model=PrescriptionOut,
                 status_code=201)
    def sign_prescription(patient_id: str, body: PrescriptionIn,
                          who: Identity = Depends(get_identity),
                          s: Session = Depends(get_session)):
        if who.role != "physician":
            audit.record(s, who, "prescription.sign", "denied", patient_id=patient_id,
                         detail="role_not_permitted")
            s.commit()
            raise HTTPException(403, "Only physicians may sign prescriptions")
        patient = s.get(Patient, patient_id)
        if patient is None or patient.tenant_id != who.tenant_id:
            audit.record(s, who, "prescription.sign", "denied", patient_id=patient_id,
                         detail="patient_not_found")
            s.commit()
            raise HTTPException(404, "Patient not found")
        rx = Prescription(tenant_id=who.tenant_id, patient_id=patient_id,
                          physician_id=who.user_id, status="signed",
                          signed_at=datetime.now(timezone.utc), **body.model_dump())
        rx.id = str(uuid.uuid4())
        rx.signature = _signature(rx)
        s.add(rx)
        audit.record(s, who, "prescription.sign", "success", resource_id=rx.id,
                     patient_id=patient_id)
        s.commit()
        return rx

    @router.get("/prescriptions/{rx_id}", response_model=PrescriptionOut)
    def read_prescription(rx_id: str, who: Identity = Depends(get_identity),
                          s: Session = Depends(get_session)):
        rx = s.get(Prescription, rx_id)
        if rx is None or rx.tenant_id != who.tenant_id:
            raise HTTPException(404, "Prescription not found")
        audit.record(s, who, "prescription.read", "success", resource_id=rx.id,
                     patient_id=rx.patient_id)
        s.commit()
        return rx

    return router
