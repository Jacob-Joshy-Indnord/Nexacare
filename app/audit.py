"""Audit trail helper.

Exposes record(session, identity, action, outcome, resource_id, patient_id,
detail), which adds an AuditLog row to the caller's session without
committing, so the audit entry is written in the same transaction as the
business change and both succeed or fail together. Denied attempts are
audited separately by the caller after rollback. Callers must pass
identifiers and short reason codes only; clinical content such as drug names
must never be placed in detail, to keep PHI out of the log.
"""
from sqlalchemy.orm import Session

from app.auth import Identity
from app.models import AuditLog


def record(session: Session, who: Identity, action: str, outcome: str,
           resource_id: str | None = None, patient_id: str | None = None,
           detail: str | None = None) -> AuditLog:
    entry = AuditLog(tenant_id=who.tenant_id, actor_id=who.user_id, actor_role=who.role,
                     action=action, outcome=outcome, resource_id=resource_id,
                     patient_id=patient_id, detail=detail)
    session.add(entry)
    return entry
