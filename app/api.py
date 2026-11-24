"""FastAPI REST layer for physician note review, editing and signing.

Endpoints: POST /notes (create AI draft), GET /notes/{id} (note, history and
signature manifestation), PUT /notes/{id}/draft (physician edit, original kept),
POST /notes/{id}/sign (two-component e-signature), GET /notes/{id}/verify
(integrity check after signing). No endpoint removes or reassigns a signature.
get_principal is the dependency that must return the claims of the validated
IdP session (provided by the user-authentication task); by default it rejects
every request with 401, so it fails closed. SigningError maps to HTTP errors.
"""
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from app.note_signing import NoteSigningService, Principal, SigningError

app = FastAPI(title="Nexa Care note signing")
service = NoteSigningService()


def get_principal() -> Principal:
    raise HTTPException(401, "authentication required")


class DraftIn(BaseModel):
    text: str


class EditIn(BaseModel):
    text: str
    reason: str = ""


class SignIn(BaseModel):
    meaning: str = "authored"


def _view(note):
    sig = note.signature
    return {"note_id": note.note_id, "text": note.current.text, "version": note.current.version,
            "signed": sig is not None,
            "history": [{"version": r.version, "text": r.text, "editor_id": r.editor_id,
                         "at": r.at.isoformat(), "reason": r.reason} for r in note.revisions],
            "signature": service.manifestation(note.note_id) if sig else None}


def _call(fn, *a, **k):
    try:
        return fn(*a, **k)
    except SigningError as e:
        raise HTTPException(e.status, str(e))


@app.post("/notes", status_code=201)
def create_note(body: DraftIn, p: Principal = Depends(get_principal)):
    return _view(service.create_draft(body.text))


@app.get("/notes/{note_id}")
def read_note(note_id: str, p: Principal = Depends(get_principal)):
    return _view(_call(service.get, note_id))


@app.put("/notes/{note_id}/draft")
def edit_note(note_id: str, body: EditIn, p: Principal = Depends(get_principal)):
    return _view(_call(service.edit_draft, note_id, p, body.text, body.reason))


@app.post("/notes/{note_id}/sign")
def sign_note(note_id: str, body: SignIn, p: Principal = Depends(get_principal)):
    return _view(_call(service.sign, note_id, p, body.meaning))


@app.get("/notes/{note_id}/verify")
def verify_note(note_id: str, p: Principal = Depends(get_principal)):
    _call(service.get, note_id)
    return {"intact": service.verify_integrity(note_id)}
