"""Tests for physician note signing, one group per spec scenario.

Covers: two-component signing (IdP session plus fresh MFA step-up; stale,
missing or inactive credentials rejected); signature manifestation (printed
name, UTC date/time, meaning) shown through the API; signature linked to the
record (cannot be re-signed, removed, edited after signing; tampering detected
by digest mismatch); unique signature identity (one per person, never shared or
reassigned); and corrections preserving history (attributed, time-stamped
edits with the AI original retained). Helper functions build principals and a
service with a controllable clock; the API tests override get_principal.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import api
from app.note_signing import NoteSigningService, Principal, SigningError

NOW = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)


def doc(uid="u1", name="Dr. Ada Lovelace", **kw):
    base = dict(user_id=uid, printed_name=name, role="physician", session_active=True,
                auth_time=NOW - timedelta(minutes=1), amr=("pwd", "mfa"))
    base.update(kw)
    return Principal(**base)


@pytest.fixture
def svc():
    return NoteSigningService(clock=lambda: NOW)


def test_sign_requires_two_components(svc):
    n = svc.create_draft("text")
    with pytest.raises(SigningError):
        svc.sign(n.note_id, doc(session_active=False))
    with pytest.raises(SigningError):
        svc.sign(n.note_id, doc(amr=("pwd",)))
    with pytest.raises(SigningError):
        svc.sign(n.note_id, doc(auth_time=NOW - timedelta(minutes=30)))
    assert svc.sign(n.note_id, doc()).signature.components == ("idp_session", "mfa_step_up")


def test_non_physician_cannot_sign(svc):
    n = svc.create_draft("t")
    with pytest.raises(SigningError) as e:
        svc.sign(n.note_id, doc(role="nurse"))
    assert e.value.status == 403


def test_manifestation(svc):
    n = svc.create_draft("t")
    svc.sign(n.note_id, doc(), "reviewed")
    m = svc.manifestation(n.note_id)
    assert m["printed_name"] == "Dr. Ada Lovelace"
    assert m["signed_at"].startswith("2026-01-05T10:00:00")
    assert m["meaning"] == "Reviewed"


def test_signature_linked_to_record(svc):
    a, b = svc.create_draft("a"), svc.create_draft("b")
    svc.sign(a.note_id, doc())
    assert svc.verify_integrity(a.note_id)
    with pytest.raises(SigningError):
        svc.sign(a.note_id, doc("u2"))          # cannot replace
    with pytest.raises(SigningError):
        svc.edit_draft(a.note_id, doc(), "changed")
    assert b.signature is None                   # not transferred
    a.revisions[-1] = replace(a.revisions[-1], text="tampered")
    assert not svc.verify_integrity(a.note_id)


def test_signature_identity_unique(svc):
    ids = {svc.signature_identity_for(u) for u in ("u1", "u2", "u3")}
    assert len(ids) == 3
    assert svc.signature_identity_for("u1") == svc.signature_identity_for("u1")
    a, b = svc.create_draft("a"), svc.create_draft("b")
    svc.sign(a.note_id, doc("u1")); svc.sign(b.note_id, doc("u2"))
    assert a.signature.signature_id != b.signature.signature_id


def test_corrections_preserve_history(svc):
    n = svc.create_draft("ai text")
    svc.edit_draft(n.note_id, doc(), "edited", "fix dose")
    assert [r.text for r in n.revisions] == ["ai text", "edited"]
    assert n.revisions[0].editor_id == "ai"
    assert n.revisions[1].editor_id == "u1" and n.revisions[1].at == NOW


def test_api_flow_and_fail_closed():
    api.service = NoteSigningService()
    c = TestClient(api.app)
    assert c.post("/notes", json={"text": "x"}).status_code == 401
    p = replace(doc(), auth_time=datetime.now(timezone.utc))
    api.app.dependency_overrides[api.get_principal] = lambda: p
    try:
        nid = c.post("/notes", json={"text": "x"}).json()["note_id"]
        assert c.put(f"/notes/{nid}/draft", json={"text": "y"}).json()["version"] == 2
        r = c.post(f"/notes/{nid}/sign", json={"meaning": "approved"})
        assert r.json()["signature"]["printed_name"] == "Dr. Ada Lovelace"
        assert c.put(f"/notes/{nid}/draft", json={"text": "z"}).status_code == 409
        assert c.get(f"/notes/{nid}/verify").json() == {"intact": True}
    finally:
        api.app.dependency_overrides.clear()
