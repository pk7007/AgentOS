"""Retention: remove data that is no longer needed, after the owner confirms.

What can be removed, once older than the retention period (deleted or superseded memory counts from when it
was deleted or superseded, as the audit log records): messages that were read, benchmark runs, released
file claims, and memory records that were deleted or superseded (deleting a memory record only hides it; this removes its
text for good, together with its search index entry). The audit log is never pruned: it is a hash chain,
and removing an event would break verification. Audit payloads are redacted when they are written, so
secrets do not reach it in the first place.

`plan` only counts. `apply` needs owner confirmation and records what it removed."""

import sqlite3
from datetime import UTC, datetime, timedelta

from agentos import audit
from agentos.db import write_tx
from agentos.errors import PolicyDenied, UsageError

MIN_DAYS = 7
_RULES = {
    "messages": "DELETE FROM messages WHERE read_at IS NOT NULL AND created_at < ?",
    "bench_runs": "DELETE FROM bench_runs WHERE created_at < ?",
    "memory": "DELETE FROM memory WHERE (deleted=1 OR superseded=1) AND COALESCE((SELECT max(e.ts) FROM events e"
              " WHERE (e.kind='memory.deleted' AND json_extract(e.payload, '$.memory_id')=memory.id)"
              " OR (e.kind='memory.corrected' AND json_extract(e.payload, '$.supersedes')=memory.id)),"
              " created_at) < ?",
    "claims": "DELETE FROM claims WHERE released_at IS NOT NULL AND released_at < ?",
}


def _cutoff(days: int, now: datetime | None = None) -> str:
    if days < MIN_DAYS:
        raise UsageError(f"the retention period is at least {MIN_DAYS} days")
    return ((now or datetime.now(UTC)) - timedelta(days=days)).isoformat()


def plan(conn: sqlite3.Connection, days: int = 90, now: datetime | None = None) -> dict:
    cutoff = _cutoff(days, now)
    counts = {name: conn.execute(sql.replace("DELETE", "SELECT count(*)", 1), (cutoff,)).fetchone()[0]
              for name, sql in _RULES.items()}
    return {"older_than": cutoff, "days": days, "would_remove": counts, "audit_events": "kept (hash chain)"}


def apply(conn: sqlite3.Connection, days: int, actor: str, owner=None, now: datetime | None = None) -> dict:
    from agentos.governance import is_owner

    if not is_owner(owner):
        raise PolicyDenied("removing data for good needs the owner", reasons=["owner_required"])
    cutoff = _cutoff(days, now)
    removed = {}
    with write_tx(conn):
        for name, sql in _RULES.items():
            removed[name] = conn.execute(sql, (cutoff,)).rowcount
        audit.append_event(conn, "retention.applied", actor, {"older_than": cutoff, "removed": removed})
    return {"older_than": cutoff, "days": days, "removed": removed}
