"""ORM data models for e-prescribing.

Defines three tables. Patient: minimal patient reference scoped to a tenant
(id, tenant_id) so prescriptions can be stored against a patient with tenant
isolation. Prescription: a signed medication order holding tenant, patient,
physician, drug, dose, route, frequency, duration, quantity, status,
signed_at and a SHA-256 signature over the content. AuditLog: append-only
record of who did what and when (actor, role, action, resource, patient,
outcome, timestamp, detail). The audit detail column must hold identifiers
only, never clinical content, to keep PHI out of logs.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)


class Prescription(Base):
    __tablename__ = "prescriptions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    patient_id: Mapped[str] = mapped_column(String, index=True)
    physician_id: Mapped[str] = mapped_column(String)
    drug_name: Mapped[str] = mapped_column(String)
    dose: Mapped[str] = mapped_column(String)
    route: Mapped[str] = mapped_column(String)
    frequency: Mapped[str] = mapped_column(String)
    duration_days: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="signed")
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    signature: Mapped[str] = mapped_column(String(64))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_id)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    actor_id: Mapped[str] = mapped_column(String)
    actor_role: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    resource_id: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_id: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[str] = mapped_column(String)
    detail: Mapped[str | None] = mapped_column(String, nullable=True)
