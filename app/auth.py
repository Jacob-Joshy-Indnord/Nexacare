"""Caller identity for the API.

Defines Identity (user_id, tenant_id, role) and the FastAPI dependency
get_identity, which reads X-User-Id, X-Tenant-Id and X-Role headers and
answers 401 when any is missing. This is a placeholder for the platform's
real authentication and RBAC (multi-tenant foundation); it is assumed that a
trusted gateway validates credentials and sets these headers, so the service
must never be exposed directly. Handlers use the identity for role checks,
tenant isolation and audit attribution.
"""
from dataclasses import dataclass

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class Identity:
    user_id: str
    tenant_id: str
    role: str


def get_identity(
    x_user_id: str | None = Header(None),
    x_tenant_id: str | None = Header(None),
    x_role: str | None = Header(None),
) -> Identity:
    if not (x_user_id and x_tenant_id and x_role):
        raise HTTPException(status_code=401, detail="Authentication required")
    return Identity(x_user_id, x_tenant_id, x_role)
