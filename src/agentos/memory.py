"""Layered memory with provenance, project isolation, versioned corrections and full-text search."""

import json
import sqlite3
from enum import Enum
from typing import Literal

from pydantic import BaseModel

from agentos import audit
from agentos.db import write_tx
from agentos.errors import NotFound, PolicyDenied, UsageError
from agentos.projects import require_active
from agentos.redact import redact
from agentos.util import new_id, now_iso, sha256_text

MAX_CONTENT = 20_000


class Layer(str, Enum):
    working = "working"
    episodic = "episodic"
    semantic = "semantic"
    procedural = "procedural"
    performance = "performance"
    failure = "failure"
    project = "project"
    organizational = "organizational"
    governance = "governance"


ORG_LAYERS = {Layer.semantic, Layer.procedural, Layer.failure, Layer.organizational}
Scope = Literal["project", "org"]


class MemoryRecord(BaseModel):
    id: str
    project_id: str | None
    scope: Scope
    layer: Layer
    content: str
    content_hash: str
    source: str
    author: str
    confidence: float
    validated: bool
    version: int
    supersedes: str | None
    superseded: bool
    deleted: bool
    tags: list[str]
    created_at: str


def _row(row) -> MemoryRecord:
    d = dict(row)
    d.update(tags=json.loads(d["tags"]), validated=bool(d["validated"]), superseded=bool(d["superseded"]),
             deleted=bool(d["deleted"]))
    return MemoryRecord(**d)


def inspect(conn: sqlite3.Connection, record_id: str) -> MemoryRecord:
    row = conn.execute("SELECT * FROM memory WHERE id=?", (record_id,)).fetchone()
    if not row:
        raise NotFound(f"memory record not found: {record_id}")
    return _row(row)


def read(conn: sqlite3.Connection, record_id: str, project_id: str) -> MemoryRecord:
    """Inspect for callers: the record must belong to `project_id` or be shared (org scope)."""
    rec = inspect(conn, record_id)
    if rec.project_id != project_id and rec.scope != "org":
        raise PolicyDenied("memory record belongs to another project", reasons=["cross_project"])
    return rec


def _insert(conn, *, project_id, scope, layer, content, source, author, confidence, validated, tags,
            version=1, supersedes=None) -> str:
    rid = new_id("mem")
    digest = sha256_text(f"{scope}|{project_id}|{layer.value}|{content}")
    conn.execute(
        "INSERT INTO memory(id, project_id, scope, layer, content, content_hash, source, author, confidence, validated,"
        " version, supersedes, tags, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rid, project_id, scope, layer.value, content, digest, source, author, float(confidence), int(validated),
         version, supersedes, json.dumps(tags), now_iso()))
    return rid


def add(conn: sqlite3.Connection, project_id: str | None, layer: Layer, content: str, source: str, author: str,
        confidence: float = 0.5, validated: bool = False, scope: Scope = "project",
        tags: list[str] | None = None) -> MemoryRecord:
    layer = Layer(layer)
    if len(content) > MAX_CONTENT:
        raise UsageError(f"memory content is limited to {MAX_CONTENT} characters")
    if not 0 <= confidence <= 1:
        raise UsageError("confidence must be between 0 and 1")
    if scope == "org":
        if not validated:
            raise PolicyDenied("only validated knowledge can be shared across projects",
                               reasons=["org_requires_validated"])
        if layer not in ORG_LAYERS:
            raise PolicyDenied(f"layer {layer.value} cannot be shared across projects", reasons=["org_layer"])
    if project_id is None:
        raise UsageError("a project is required (it is recorded as the source of the knowledge)")
    require_active(conn, project_id)
    content, _ = redact(content)
    digest = sha256_text(f"{scope}|{project_id}|{layer.value}|{content}")
    with write_tx(conn):
        dup = conn.execute("SELECT id FROM memory WHERE content_hash=? AND deleted=0 AND superseded=0",
                           (digest,)).fetchone()
        if dup:
            return inspect(conn, dup[0])
        rid = _insert(conn, project_id=project_id, scope=scope, layer=layer, content=content, source=source,
                      author=author, confidence=confidence, validated=validated, tags=list(tags or []))
        audit.append_event(conn, "memory.added", author, {"memory_id": rid, "layer": layer.value, "scope": scope,
                                                          "validated": validated}, project_id)
    return inspect(conn, rid)


def _fts_query(query: str, any_term: bool = False) -> str:
    tokens = dict.fromkeys(t for t in query.split() if any(ch.isalnum() for ch in t))
    return (" OR " if any_term else " ").join('"' + t.replace('"', '""') + '"' for t in tokens)


def search(conn: sqlite3.Connection, project_id: str, query: str, layers: list[Layer] | None = None,
           include_org: bool = True, validated_only: bool = False, limit: int = 10,
           any_term: bool = False) -> list[MemoryRecord]:
    """Records matching every word of `query` (or any word, with `any_term`), best match first."""
    fts = _fts_query(query, any_term)
    if not fts:
        return []
    sql = ("SELECT m.* FROM memory_fts f JOIN memory m ON m.rowid = f.rowid WHERE memory_fts MATCH ? "
           "AND m.deleted = 0 AND m.superseded = 0 AND (m.project_id = ? OR (m.scope = 'org' AND ?))")
    params: list = [fts, project_id, int(include_org)]
    if layers:
        sql += f" AND m.layer IN ({','.join('?' * len(layers))})"
        params.extend(Layer(x).value for x in layers)
    if validated_only:
        sql += " AND m.validated = 1"
    sql += " ORDER BY f.rank LIMIT ?"
    params.append(limit)
    return [_row(r) for r in conn.execute(sql, params)]


def _owned(conn, record_id: str, project_id: str | None) -> MemoryRecord:
    rec = inspect(conn, record_id)
    if project_id is not None and rec.project_id != project_id:
        raise PolicyDenied("memory record belongs to another project", reasons=["cross_project"])
    if rec.deleted:
        raise PolicyDenied("memory record was deleted", reasons=["deleted"])
    return rec


def correct(conn: sqlite3.Connection, record_id: str, new_content: str, author: str,
            project_id: str | None = None) -> MemoryRecord:
    rec = _owned(conn, record_id, project_id)
    if len(new_content) > MAX_CONTENT:
        raise UsageError(f"memory content is limited to {MAX_CONTENT} characters")
    content, _ = redact(new_content)
    with write_tx(conn):
        conn.execute("UPDATE memory SET superseded=1 WHERE id=?", (record_id,))
        rid = _insert(conn, project_id=rec.project_id, scope=rec.scope, layer=rec.layer, content=content,
                      source=rec.source, author=author, confidence=rec.confidence, validated=rec.validated,
                      tags=rec.tags, version=rec.version + 1, supersedes=record_id)
        audit.append_event(conn, "memory.corrected", author, {"memory_id": rid, "supersedes": record_id},
                           rec.project_id)
    return inspect(conn, rid)


def delete(conn: sqlite3.Connection, record_id: str, actor: str, project_id: str | None = None) -> MemoryRecord:
    rec = _owned(conn, record_id, project_id)
    with write_tx(conn):
        conn.execute("UPDATE memory SET deleted=1, content='' WHERE id=?", (record_id,))
        audit.append_event(conn, "memory.deleted", actor, {"memory_id": record_id}, rec.project_id)
    return inspect(conn, record_id)


def export(conn: sqlite3.Connection, project_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM memory WHERE project_id=? AND deleted=0 ORDER BY created_at, rowid",
                        (project_id,))
    return [_row(r).model_dump(mode="json") for r in rows]


def recent(conn: sqlite3.Connection, project_id: str, layers: list[Layer], limit: int = 10) -> list[MemoryRecord]:
    marks = ",".join("?" * len(layers))
    rows = conn.execute(
        f"SELECT * FROM memory WHERE project_id=? AND deleted=0 AND superseded=0 AND layer IN ({marks}) "
        "ORDER BY created_at DESC, rowid DESC LIMIT ?", [project_id, *[Layer(x).value for x in layers], limit])
    return [_row(r) for r in rows]
