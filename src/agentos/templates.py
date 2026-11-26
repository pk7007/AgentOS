"""Versioned agent templates. A template is a stored configuration, never a running worker."""

import json
import sqlite3
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from agentos import audit
from agentos.db import write_tx
from agentos.errors import NotFound, PolicyDenied
from agentos.util import load_toml, now_iso


class TemplateStatus(str, Enum):
    active = "active"
    suspended = "suspended"
    quarantined = "quarantined"
    retired = "retired"
    # An experiment's challenger: never recruited, admitted only on that experiment's trial tasks.
    candidate = "candidate"


class AgentTemplate(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,40}$")
    version: int = 1
    name: str
    role: str
    department: str
    description: str
    capabilities: list[str]
    tools_allow: list[str] = []
    tools_deny: list[str] = []
    model_hint: str | None = None
    reasoning_hint: Literal["low", "medium", "high"] | None = None
    can_delegate: bool = False
    security_class: Literal["standard", "elevated"] = "standard"
    read_only: bool = False
    instructions: str
    status: TemplateStatus = TemplateStatus.active


A = TemplateStatus
# (from, to) -> owner confirmation required?
_ALLOWED: dict[tuple[TemplateStatus, TemplateStatus], bool] = {
    (A.active, A.suspended): False,
    (A.active, A.quarantined): False,
    (A.active, A.retired): True,
    (A.suspended, A.active): False,
    (A.suspended, A.quarantined): False,
    (A.suspended, A.retired): True,
    (A.quarantined, A.active): True,
    (A.quarantined, A.retired): True,
    (A.retired, A.active): True,
    # A challenger is promoted by copying its fields into the champion, never by activating it.
    (A.candidate, A.quarantined): False,
    (A.candidate, A.retired): False,
}

_BODY_EXCLUDE = {"id", "version", "status"}


def _from_row(row) -> AgentTemplate:
    return AgentTemplate(id=row["id"], version=row["version"], status=row["status"], **json.loads(row["body"]))


def get_template(conn: sqlite3.Connection, template_id: str, version: int | None = None) -> AgentTemplate:
    if version is None:
        row = conn.execute("SELECT * FROM agent_templates WHERE id=? ORDER BY version DESC LIMIT 1",
                           (template_id,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM agent_templates WHERE id=? AND version=?",
                           (template_id, version)).fetchone()
    if not row:
        raise NotFound(f"agent template not found: {template_id}" + (f" v{version}" if version else ""))
    return _from_row(row)


def list_templates(conn: sqlite3.Connection, status: TemplateStatus | None = None) -> list[AgentTemplate]:
    rows = conn.execute(
        "SELECT t.* FROM agent_templates t JOIN (SELECT id, max(version) v FROM agent_templates GROUP BY id) m "
        "ON t.id=m.id AND t.version=m.v ORDER BY t.id"
    )
    items = [_from_row(r) for r in rows]
    return [t for t in items if status is None or t.status == TemplateStatus(status)]


def add_template(conn: sqlite3.Connection, t: AgentTemplate, actor: str) -> AgentTemplate:
    with write_tx(conn):
        row = conn.execute("SELECT max(version), status FROM agent_templates WHERE id=?", (t.id,)).fetchone()
        version = (row[0] or 0) + 1
        status = row[1] if row[0] else t.status.value
        body = t.model_dump(mode="json", exclude=_BODY_EXCLUDE)
        conn.execute("INSERT INTO agent_templates(id, version, status, body, created_at) VALUES (?,?,?,?,?)",
                     (t.id, version, status, json.dumps(body), now_iso()))
        audit.append_event(conn, "template.added", actor, {"template_id": t.id, "version": version})
    return get_template(conn, t.id, version)


def set_status(conn: sqlite3.Connection, template_id: str, to: TemplateStatus, actor: str, reason: str,
               owner: object | None = None) -> AgentTemplate:
    to = TemplateStatus(to)
    current = get_template(conn, template_id)
    key = (current.status, to)
    if key not in _ALLOWED:
        raise PolicyDenied(f"cannot move template from {current.status.value} to {to.value}",
                           reasons=["illegal_transition"])
    from agentos.governance import is_owner

    if _ALLOWED[key] and not is_owner(owner):
        raise PolicyDenied(f"moving a template to {to.value} needs the owner", reasons=["owner_required"])
    with write_tx(conn):
        conn.execute("UPDATE agent_templates SET status=? WHERE id=?", (to.value, template_id))
        audit.append_event(conn, "template.status", actor, {
            "template_id": template_id, "from": current.status.value, "to": to.value,
            "reason": reason, "owner_confirmed": owner is not None})
    return get_template(conn, template_id)


def load_definitions(directory: Path) -> list[AgentTemplate]:
    out = []
    for path in sorted(Path(directory).glob("*.toml")):
        out.append(AgentTemplate(**load_toml(path)))
    return out


def seed(conn: sqlite3.Connection, directory: Path, actor: str) -> list[dict]:
    """Add definitions whose body differs from the latest stored version."""
    results = []
    for t in load_definitions(directory):
        try:
            latest = get_template(conn, t.id)
            same = latest.model_dump(exclude=_BODY_EXCLUDE) == t.model_dump(exclude=_BODY_EXCLUDE)
        except NotFound:
            same = False
        if same:
            results.append({"id": t.id, "action": "unchanged"})
        else:
            added = add_template(conn, t, actor)
            results.append({"id": t.id, "action": "added", "version": added.version})
    return results
