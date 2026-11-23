"""Tests for the e-prescription entry endpoint (task-K3981co9sUk).

This module verifies the scenario "Prescription stored and audited": when a
physician signs a prescription it is stored against the patient and an audit
record is written. Fixtures: client (FastAPI TestClient on an in-memory
database with one seeded patient). Tests: test_sign_stores_and_audits checks
persistence, signature and audit; test_audit_has_no_phi checks the audit holds
identifiers only; test_non_physician_rejected and test_cross_tenant_patient_404
check access control; test_validation_rejects_bad_input checks input rules;
test_get_prescription_is_audited checks reads are audited too.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import make_engine, make_session_factory, Base
from app.main import create_app
from app.models import AuditLog, Patient, Prescription

PHYS = {"X-User-Id": "doc-1", "X-Tenant-Id": "t1", "X-Role": "physician"}
BODY = {"drug_name": "Amoxicillin", "dose": "500 mg", "route": "oral",
        "frequency": "3x daily", "duration_days": 7, "quantity": 21}


@pytest.fixture
def ctx():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    sf = make_session_factory(engine)
    with sf() as s:
        s.add(Patient(id="p1", tenant_id="t1"))
        s.add(Patient(id="p2", tenant_id="t2"))
        s.commit()
    return TestClient(create_app(sf)), sf


def test_sign_stores_and_audits(ctx):
    client, sf = ctx
    r = client.post("/patients/p1/prescriptions", json=BODY, headers=PHYS)
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "signed" and data["patient_id"] == "p1"
    assert len(data["signature"]) == 64
    with sf() as s:
        rx = s.get(Prescription, data["id"])
        assert rx.patient_id == "p1" and rx.physician_id == "doc-1" and rx.tenant_id == "t1"
        logs = s.scalars(select(AuditLog).where(AuditLog.action == "prescription.sign")).all()
        assert len(logs) == 1
        assert logs[0].actor_id == "doc-1" and logs[0].resource_id == rx.id
        assert logs[0].patient_id == "p1" and logs[0].outcome == "success"


def test_audit_has_no_phi(ctx):
    client, sf = ctx
    client.post("/patients/p1/prescriptions", json=BODY, headers=PHYS)
    with sf() as s:
        for log in s.scalars(select(AuditLog)):
            assert "Amoxicillin" not in (log.detail or "")


def test_non_physician_rejected(ctx):
    client, sf = ctx
    h = {**PHYS, "X-Role": "nurse"}
    assert client.post("/patients/p1/prescriptions", json=BODY, headers=h).status_code == 403
    with sf() as s:
        assert s.scalars(select(Prescription)).all() == []
        assert s.scalars(select(AuditLog).where(AuditLog.outcome == "denied")).all()


def test_missing_identity_401(ctx):
    client, _ = ctx
    assert client.post("/patients/p1/prescriptions", json=BODY).status_code == 401


def test_cross_tenant_patient_404(ctx):
    client, _ = ctx
    assert client.post("/patients/p2/prescriptions", json=BODY, headers=PHYS).status_code == 404


def test_validation_rejects_bad_input(ctx):
    client, _ = ctx
    bad = {**BODY, "quantity": 0}
    assert client.post("/patients/p1/prescriptions", json=bad, headers=PHYS).status_code == 422


def test_get_prescription_is_audited(ctx):
    client, sf = ctx
    rid = client.post("/patients/p1/prescriptions", json=BODY, headers=PHYS).json()["id"]
    assert client.get(f"/prescriptions/{rid}", headers=PHYS).status_code == 200
    with sf() as s:
        assert s.scalars(select(AuditLog).where(AuditLog.action == "prescription.read")).all()
