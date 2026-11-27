"""Messages between workers and the owner, escalations, and file claims that stop two workers editing the
same path at once.

A message is a ledger row, not a delivery: the host reads a worker's inbox and passes it on. Message bodies
are redacted before they are stored. A claim is exclusive: a second worker asking for the same path, a path
inside it, or a folder that contains it is refused and told who holds it. A claim whose holder is no longer
active is released automatically when someone else asks for the path, so a crashed worker cannot block
others for ever."""

import posixpath
import sqlite3

from agentos import audit
from agentos.db import write_tx
from agentos.errors import NotFound, PolicyDenied, UsageError
from agentos.lifecycle import ACTIVE_STATES
from agentos.redact import redact
from agentos.util import new_id, now_iso

KINDS = ("note", "request", "reply", "escalation")
OWNER = "owner"
BROADCAST = "all"
MAX_BODY = 4000


def _instance(conn, project_id: str, instance_id: str, role: str):
    row = conn.execute("SELECT id, project_id, state FROM agent_instances WHERE id=?", (instance_id,)).fetchone()
    if not row:
        raise NotFound(f"{role} {instance_id} is not a registered agent instance")
    if row["project_id"] != project_id:
        raise PolicyDenied(f"{role} {instance_id} belongs to another project", reasons=["cross_project"])
    return row


def _party(conn, project_id: str, who: str, role: str) -> str:
    who = (who or "").strip()
    if who in (OWNER, BROADCAST) and not (role == "sender" and who == BROADCAST):
        return who
    if not who.startswith("ag_"):
        raise UsageError(f"{role} must be an agent instance id or '{OWNER}'"
                         + ("" if role == "sender" else f" or '{BROADCAST}'"))
    _instance(conn, project_id, who, role)
    return who


def send(conn: sqlite3.Connection, project_id: str, sender: str, recipient: str, body: str, actor: str,
         kind: str = "note", task_id: str | None = None) -> dict:
    if kind not in KINDS:
        raise UsageError(f"unknown kind {kind!r}; allowed: {', '.join(KINDS)}")
    body = (body or "").strip()
    if not body:
        raise UsageError("a message needs a body")
    if len(body) > MAX_BODY:
        raise UsageError(f"a message body is at most {MAX_BODY} characters")
    sender, recipient = _party(conn, project_id, sender, "sender"), _party(conn, project_id, recipient, "recipient")
    if sender == recipient:
        raise UsageError("a worker cannot message itself")
    if task_id:
        row = conn.execute("SELECT project_id FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row or row[0] != project_id:
            raise NotFound(f"task {task_id} is not in this project")
    clean, hits = redact(body)
    mid = new_id("msg")
    with write_tx(conn):
        conn.execute("INSERT INTO messages(id, project_id, sender, recipient, kind, task_id, body, created_at)"
                     " VALUES (?,?,?,?,?,?,?,?)", (mid, project_id, sender, recipient, kind, task_id, clean, now_iso()))
        audit.append_event(conn, "comms.escalated" if kind == "escalation" else "comms.sent", actor, {
            "message_id": mid, "sender": sender, "recipient": recipient, "message_kind": kind, "task_id": task_id,
            "redactions": hits}, project_id)
    return {"id": mid, "sender": sender, "recipient": recipient, "kind": kind, "task_id": task_id,
            "body": clean, "redactions": hits}


def escalate(conn: sqlite3.Connection, project_id: str, sender: str, body: str, actor: str,
             task_id: str | None = None) -> dict:
    """A message to the owner that the dashboard and `observe incidents` show until it is read."""
    return send(conn, project_id, sender, OWNER, body, actor, kind="escalation", task_id=task_id)


SYSTEM = "agentos"


def escalate_from_agentos(conn: sqlite3.Connection, project_id: str, body: str, actor: str,
                          task_id: str | None = None) -> str:
    """An escalation raised by AgentOS itself (the retry limit, a reaped worker), not by a worker. It joins
    the caller's transaction, so it is recorded together with the decision that raised it, and it shows on
    the dashboard and in `observe incidents` until the owner reads it (`agentos msg inbox owner --mark-read`)."""
    clean, hits = redact(body.strip()[:MAX_BODY])
    mid = new_id("msg")
    with write_tx(conn):
        conn.execute("INSERT INTO messages(id, project_id, sender, recipient, kind, task_id, body, created_at)"
                     " VALUES (?,?,?,?,?,?,?,?)", (mid, project_id, SYSTEM, OWNER, "escalation", task_id, clean,
                                                   now_iso()))
        audit.append_event(conn, "comms.escalated", actor, {
            "message_id": mid, "sender": SYSTEM, "recipient": OWNER, "message_kind": "escalation",
            "task_id": task_id, "redactions": hits}, project_id)
    return mid


def inbox(conn: sqlite3.Connection, project_id: str, recipient: str, unread_only: bool = True,
          mark_read: bool = False, actor: str = "host", limit: int = 50) -> list[dict]:
    recipient = _party(conn, project_id, recipient, "recipient")
    sql = ("SELECT * FROM messages WHERE project_id=? AND (recipient=? OR (recipient=? AND sender<>?))"
           + (" AND read_at IS NULL" if unread_only else "") + " ORDER BY created_at, id LIMIT ?")
    rows = [dict(r) for r in conn.execute(sql, (project_id, recipient, BROADCAST, recipient, limit))]
    if mark_read:
        mine = [r["id"] for r in rows if r["recipient"] == recipient and r["read_at"] is None]
        if mine:
            ts = now_iso()
            with write_tx(conn):
                conn.executemany("UPDATE messages SET read_at=? WHERE id=?", [(ts, m) for m in mine])
                audit.append_event(conn, "comms.read", actor, {"recipient": recipient, "messages": mine}, project_id)
            for r in rows:
                if r["id"] in mine:
                    r["read_at"] = ts
    return rows


def open_escalations(conn: sqlite3.Connection, project_id: str | None = None) -> list[dict]:
    sql = "SELECT * FROM messages WHERE kind='escalation' AND read_at IS NULL"
    params: tuple = ()
    if project_id:
        sql, params = sql + " AND project_id=?", (project_id,)
    return [dict(r) for r in conn.execute(sql + " ORDER BY created_at", params)]


def normalise_path(path: str) -> str:
    p = (path or "").strip().replace("\\", "/")
    if not p or p.startswith("/") or (len(p) > 1 and p[1] == ":"):
        raise UsageError(f"claim a path relative to the repository, not {path!r}")
    p = posixpath.normpath(p)
    if p == "." or p.startswith("../") or p == "..":
        raise UsageError(f"path {path!r} is outside the repository")
    return p


def _overlaps(a: str, b: str) -> bool:
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _active(conn, instance_id: str) -> bool:
    row = conn.execute("SELECT state FROM agent_instances WHERE id=?", (instance_id,)).fetchone()
    return bool(row) and row[0] in {s.value for s in ACTIVE_STATES}


def claim(conn: sqlite3.Connection, project_id: str, instance_id: str, paths: list[str], actor: str) -> dict:
    """Claim every path or none. Refused with the holder's id when another active worker holds an
    overlapping path; a claim held by a worker that is no longer active is released first."""
    inst = _instance(conn, project_id, instance_id, "claimant")
    if inst["state"] not in {s.value for s in ACTIVE_STATES}:
        raise PolicyDenied(f"{instance_id} is {inst['state']}, not active", reasons=["not_active"])
    wanted = sorted({normalise_path(p) for p in paths})
    if not wanted:
        raise UsageError("name at least one path")
    with write_tx(conn):
        held = conn.execute("SELECT id, path, instance_id FROM claims WHERE project_id=? AND released_at IS NULL",
                            (project_id,)).fetchall()
        conflicts, stale = [], []
        for row in held:
            if not any(_overlaps(row["path"], w) for w in wanted) or row["instance_id"] == instance_id:
                continue
            if _active(conn, row["instance_id"]):
                conflicts.append({"path": row["path"], "holder": row["instance_id"]})
            else:
                stale.append(row)
        if conflicts:
            # recorded and committed before the refusal is raised, so the denial stays in the audit log
            audit.append_event(conn, "comms.claim_denied", actor, {
                "instance_id": instance_id, "paths": wanted, "conflicts": conflicts}, project_id)
        else:
            ts = now_iso()
            for row in stale:
                conn.execute("UPDATE claims SET released_at=? WHERE id=?", (ts, row["id"]))
                audit.append_event(conn, "comms.claim_released", actor, {
                    "claim_id": row["id"], "path": row["path"], "instance_id": row["instance_id"],
                    "reason": "holder no longer active"}, project_id)
            mine = {r["path"] for r in held if r["instance_id"] == instance_id}
            new = [w for w in wanted if w not in mine]
            for w in new:
                conn.execute("INSERT INTO claims(id, project_id, path, instance_id, claimed_at) VALUES (?,?,?,?,?)",
                             (new_id("clm"), project_id, w, instance_id, ts))
            audit.append_event(conn, "comms.claimed", actor, {"instance_id": instance_id, "paths": new,
                                                               "freed": [r["path"] for r in stale]}, project_id)
    if conflicts:
        raise PolicyDenied("another active worker holds " + ", ".join(
            f"{c['path']} ({c['holder']})" for c in conflicts), reasons=["path_claimed"])
    return {"instance_id": instance_id, "claimed": new, "already_held": sorted(mine & set(wanted)),
            "freed_stale": [r["path"] for r in stale]}


def release(conn: sqlite3.Connection, project_id: str, instance_id: str, actor: str,
            paths: list[str] | None = None) -> dict:
    _instance(conn, project_id, instance_id, "claimant")
    sql = "SELECT id, path FROM claims WHERE project_id=? AND instance_id=? AND released_at IS NULL"
    rows = conn.execute(sql, (project_id, instance_id)).fetchall()
    if paths:
        want = {normalise_path(p) for p in paths}
        rows = [r for r in rows if r["path"] in want]
    with write_tx(conn):
        ts = now_iso()
        for r in rows:
            conn.execute("UPDATE claims SET released_at=? WHERE id=?", (ts, r["id"]))
        if rows:
            audit.append_event(conn, "comms.claim_released", actor, {
                "instance_id": instance_id, "paths": [r["path"] for r in rows], "reason": "released"}, project_id)
    return {"instance_id": instance_id, "released": sorted(r["path"] for r in rows)}


def claims(conn: sqlite3.Connection, project_id: str) -> list[dict]:
    rows = conn.execute("SELECT path, instance_id, claimed_at FROM claims WHERE project_id=? AND released_at IS NULL"
                        " ORDER BY path", (project_id,)).fetchall()
    return [dict(r) | {"holder_active": _active(conn, r["instance_id"])} for r in rows]
