"""Domain logic for physician review, editing and e-signing of AI visit notes.

Holds the in-memory NoteSigningService plus its data classes. Functions and
methods: create_draft stores the AI-generated text as an immutable original;
edit_draft appends an attributed, time-stamped revision without overwriting
history; sign verifies two components (active IdP session plus a fresh MFA
step-up claim), links the signature to the note by a SHA-256 digest of note id,
version and text, and locks the note; verify_integrity detects any change after
signing; manifestation returns printed name, UTC date/time and meaning;
signature_identity_for issues one never-reassigned identity per individual.
Signatures cannot be removed or moved to another record. Storage is in-memory
and should be swapped for PostgreSQL with append-only tables in production.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

STEP_UP_MAX_AGE = timedelta(minutes=5)
MFA_AMR_VALUES = {"mfa", "otp", "hwk", "swk"}
MFA_ACR_VALUES = {"mfa", "urn:mace:incommon:iap:silver"}
MEANINGS = {"authored": "Authored and approved", "reviewed": "Reviewed", "approved": "Approved"}


class SigningError(Exception):
    """Raised for rule violations; `status` maps to an HTTP status code."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Principal:
    """Identity claims taken from the validated IdP session/token."""
    user_id: str
    printed_name: str
    role: str
    session_active: bool
    auth_time: datetime  # time of the most recent (step-up) authentication
    amr: tuple[str, ...] = ()
    acr: str = ""


@dataclass(frozen=True)
class Revision:
    version: int
    text: str
    editor_id: str  # "ai" for the generated original
    at: datetime
    reason: str = ""


@dataclass(frozen=True)
class Signature:
    signature_id: str  # unique identity, belongs to one individual
    signer_id: str
    printed_name: str
    signed_at: datetime
    meaning: str
    note_id: str
    signed_version: int
    digest: str
    components: tuple[str, ...] = ("idp_session", "mfa_step_up")


@dataclass
class Note:
    note_id: str
    revisions: list[Revision] = field(default_factory=list)
    signature: Signature | None = None

    @property
    def current(self) -> Revision:
        return self.revisions[-1]


def _digest(note_id: str, version: int, text: str) -> str:
    canonical = json.dumps({"note_id": note_id, "version": version, "text": text},
                           sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


class NoteSigningService:
    def __init__(self, clock=lambda: datetime.now(timezone.utc)):
        self._clock = clock
        self._notes: dict[str, Note] = {}
        self._identities: dict[str, str] = {}   # user_id -> signature_id
        self._issued: set[str] = set()          # signature_ids ever issued

    def create_draft(self, text: str, note_id: str | None = None) -> Note:
        note = Note(note_id or str(uuid.uuid4()))
        note.revisions.append(Revision(1, text, "ai", self._clock(), "AI generated"))
        self._notes[note.note_id] = note
        return note

    def get(self, note_id: str) -> Note:
        if note_id not in self._notes:
            raise SigningError("note not found", 404)
        return self._notes[note_id]

    def edit_draft(self, note_id: str, principal: Principal, text: str, reason: str = "") -> Note:
        note = self.get(note_id)
        if principal.role != "physician":
            raise SigningError("only physicians may edit notes", 403)
        if note.signature:
            raise SigningError("note is signed; add an addendum instead", 409)
        note.revisions.append(
            Revision(note.current.version + 1, text, principal.user_id, self._clock(), reason))
        return note

    def signature_identity_for(self, user_id: str) -> str:
        if user_id not in self._identities:
            sid = str(uuid.uuid4())
            self._identities[user_id] = sid
            self._issued.add(sid)
        return self._identities[user_id]

    def _check_two_components(self, p: Principal) -> None:
        if not p.session_active:
            raise SigningError("active IdP session required", 401)
        now = self._clock()
        mfa = set(p.amr) & MFA_AMR_VALUES or p.acr in MFA_ACR_VALUES
        if not mfa:
            raise SigningError("MFA step-up required before signing", 401)
        if p.auth_time > now or now - p.auth_time > STEP_UP_MAX_AGE:
            raise SigningError("step-up authentication is stale; re-authenticate", 401)

    def sign(self, note_id: str, principal: Principal, meaning: str = "authored") -> Note:
        note = self.get(note_id)
        if principal.role != "physician":
            raise SigningError("only physicians may sign notes", 403)
        if note.signature:
            raise SigningError("note already signed; signature cannot be replaced", 409)
        if meaning not in MEANINGS:
            raise SigningError("unknown signature meaning", 422)
        self._check_two_components(principal)
        rev = note.current
        note.signature = Signature(
            signature_id=self.signature_identity_for(principal.user_id),
            signer_id=principal.user_id, printed_name=principal.printed_name,
            signed_at=self._clock(), meaning=MEANINGS[meaning], note_id=note_id,
            signed_version=rev.version, digest=_digest(note_id, rev.version, rev.text))
        return note

    def verify_integrity(self, note_id: str) -> bool:
        note = self.get(note_id)
        sig = note.signature
        if sig is None:
            return False
        signed = next((r for r in note.revisions if r.version == sig.signed_version), None)
        return (signed is not None and sig.note_id == note.note_id
                and note.current.version == sig.signed_version
                and _digest(note.note_id, signed.version, signed.text) == sig.digest)

    def manifestation(self, note_id: str) -> dict:
        note = self.get(note_id)
        sig = note.signature
        if sig is None:
            raise SigningError("note is not signed", 409)
        return {"printed_name": sig.printed_name,
                "signed_at": sig.signed_at.astimezone(timezone.utc).isoformat(),
                "meaning": sig.meaning, "signature_id": sig.signature_id,
                "intact": self.verify_integrity(note_id)}
