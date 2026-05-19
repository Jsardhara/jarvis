"""Multi-user contact graph — the people *around* Jyot.

Jarvis is single-operator, but mail, calendar, and conversation are
constantly populated by *other* humans — advisors, professors,
colleagues, family. Without a contact graph Jarvis can't resolve
"draft a reply to Pepper" because it has no idea who Pepper is.

This module is the minimal contact graph. Storage mirrors
``projects.py`` / ``drafted_replies.py``: JSONL append-on-create,
full-record rewrite on update, latest-ts wins per id on read.

Schema:
    Contact
      id            uuid hex prefix
      display_name  canonical name ("Pepper Potts")
      aliases       list of nicknames / shortforms
      email         primary email, optional
      relation      "advisor" | "professor" | "colleague" | "family" |
                    "friend" | "other"
      notes         operator-supplied or auto-learned
      created       ISO UTC
      updated       ISO UTC
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from jarvis.config import get_settings
from jarvis.state.rotate import rotate_if_large

log = logging.getLogger(__name__)

_PROMPT_CONTACT_CAP = 10


@dataclass(frozen=True)
class Contact:
    """One known person around the operator."""

    id: str
    display_name: str
    aliases: list[str] = field(default_factory=list)
    email: str | None = None
    relation: str = "other"
    notes: str = ""
    created: str = ""
    updated: str = ""


def _path() -> Path:
    return get_settings().state_dir / "contacts.jsonl"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _from_dict(raw: dict[str, Any]) -> Contact | None:
    """Hydrate a Contact from one JSONL line. None on schema mismatch."""
    try:
        aliases_raw = raw.get("aliases", []) or []
        aliases = [str(a) for a in aliases_raw if str(a).strip()]
        email = raw.get("email")
        email_value = str(email) if email else None
        return Contact(
            id=str(raw["id"]),
            display_name=str(raw["display_name"]),
            aliases=aliases,
            email=email_value,
            relation=str(raw.get("relation", "other")),
            notes=str(raw.get("notes", "")),
            created=str(raw.get("created", "")),
            updated=str(raw.get("updated", "")),
        )
    except (KeyError, TypeError) as exc:
        log.warning("contacts: skipping malformed record: %s", exc)
        return None


def _read_all_lines() -> list[Contact]:
    """Read every JSONL line; latest-updated wins per id."""
    target = _path()
    if not target.exists():
        return []
    by_id: dict[str, Contact] = {}
    try:
        for raw in target.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            contact = _from_dict(data)
            if contact is None:
                continue
            prior = by_id.get(contact.id)
            if prior is None or contact.updated >= prior.updated:
                by_id[contact.id] = contact
    except OSError as exc:
        log.warning("contacts read failed: %s", exc)
        return []
    return list(by_id.values())


def _append_record(contact: Contact) -> None:
    """Append one JSON line. Caller-supplied contact is the new truth."""
    target = _path()
    target.parent.mkdir(parents=True, exist_ok=True)
    rotate_if_large(target)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(contact), ensure_ascii=False) + "\n")


def create_contact(
    display_name: str,
    relation: str,
    *,
    aliases: list[str] | None = None,
    email: str | None = None,
    notes: str = "",
) -> Contact:
    """Create and persist a new contact. Returns the persisted record."""
    now = _now_iso()
    contact = Contact(
        id=uuid4().hex[:12],
        display_name=display_name,
        aliases=list(aliases) if aliases else [],
        email=email,
        relation=relation,
        notes=notes,
        created=now,
        updated=now,
    )
    _append_record(contact)
    return contact


def list_contacts(relation: str | None = None) -> list[Contact]:
    """All contacts, sorted by display_name. Optional relation filter."""
    items = _read_all_lines()
    if relation is not None:
        items = [c for c in items if c.relation == relation]
    return sorted(items, key=lambda c: c.display_name.lower())


def get_contact(contact_id: str) -> Contact | None:
    """Return one contact by id, or None if unknown."""
    return next((c for c in _read_all_lines() if c.id == contact_id), None)


def resolve_name(name: str) -> Contact | None:
    """Case-insensitive lookup against display_name OR any alias.

    First match wins. Returns None on no hit. Used by tempo to convert
    "Pepper" → the Contact record (and its email).
    """
    if not name:
        return None
    needle = name.strip().lower()
    if not needle:
        return None
    for contact in _read_all_lines():
        if contact.display_name.lower() == needle:
            return contact
        if any(alias.lower() == needle for alias in contact.aliases):
            return contact
    return None


def update_contact(contact_id: str, **patch: Any) -> Contact | None:
    """Patch display_name / aliases / email / relation / notes on a contact.

    Bumps ``updated``. Unknown patch keys are silently ignored so callers
    can't corrupt the schema.
    """
    cur = get_contact(contact_id)
    if cur is None:
        return None
    allowed = {"display_name", "aliases", "email", "relation", "notes"}
    clean: dict[str, Any] = {k: v for k, v in patch.items() if k in allowed}
    updated = Contact(
        id=cur.id,
        display_name=str(clean.get("display_name", cur.display_name)),
        aliases=(
            list(clean["aliases"]) if "aliases" in clean else list(cur.aliases)
        ),
        email=clean.get("email", cur.email),
        relation=str(clean.get("relation", cur.relation)),
        notes=str(clean.get("notes", cur.notes)),
        created=cur.created,
        updated=_now_iso(),
    )
    _append_record(updated)
    return updated


def render_contacts_for_prompt(limit: int = _PROMPT_CONTACT_CAP) -> str:
    """Compact "Known contacts:" block. Empty string when none known."""
    items = list_contacts()
    if not items:
        return ""
    if limit > 0:
        items = items[:limit]
    lines = ["Known contacts:"]
    for c in items:
        suffix = f" ({c.relation})" if c.relation else ""
        email_part = f" <{c.email}>" if c.email else ""
        lines.append(f"- {c.display_name}{suffix}{email_part}")
    return "\n".join(lines)


__all__ = [
    "Contact",
    "create_contact",
    "get_contact",
    "list_contacts",
    "render_contacts_for_prompt",
    "resolve_name",
    "update_contact",
]
