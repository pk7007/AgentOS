"""Append-only, hash-chained audit log."""

import hashlib
import json
import sqlite3

from pydantic import BaseModel

from agentos.redact import redact_obj
from agentos.util import canonical_json, new_id, now_iso, sha256_json

GENESIS = "0" * 64


class VerifyResult(BaseModel):
    ok: bool
    checked: int
    first_bad_seq: int | None = None


def _hash(prev_hash: str, record: dict) -> str:
    return hashlib.sha256((prev_hash + sha256_json(record)).encode("utf-8")).hexdigest()


def append_event(
    conn: sqlite3.Connection, kind: str, actor: str, payload: dict, project_id: str | None = None
) -> str:
    assert conn.in_transaction, "append_event must run inside write_tx"
    payload = redact_obj(payload)
    row = conn.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
    prev = row[0] if row else GENESIS
    record = {"id": new_id("ev"), "ts": now_iso(), "kind": kind, "actor": actor,
              "project_id": project_id, "payload": payload}
    conn.execute(
        "INSERT INTO events(id, ts, kind, actor, project_id, payload, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?)",
        (record["id"], record["ts"], kind, actor, project_id, canonical_json(payload), prev,
         _hash(prev, record)),
    )
    return record["id"]


def verify_chain(conn: sqlite3.Connection) -> VerifyResult:
    prev, checked = GENESIS, 0
    for row in conn.execute("SELECT * FROM events ORDER BY seq"):
        record = {"id": row["id"], "ts": row["ts"], "kind": row["kind"], "actor": row["actor"],
                  "project_id": row["project_id"], "payload": json.loads(row["payload"])}
        if row["prev_hash"] != prev or _hash(prev, record) != row["hash"]:
            return VerifyResult(ok=False, checked=checked, first_bad_seq=row["seq"])
        prev = row["hash"]
        checked += 1
    return VerifyResult(ok=True, checked=checked)


def list_events(conn: sqlite3.Connection, limit: int = 50, kind: str | None = None,
                project_id: str | None = None) -> list[dict]:
    sql, params = "SELECT seq, id, ts, kind, actor, project_id, payload FROM events WHERE 1=1", []
    if kind:
        sql += " AND kind=?"
        params.append(kind)
    if project_id:
        sql += " AND project_id=?"
        params.append(project_id)
    sql += " ORDER BY seq DESC LIMIT ?"
    params.append(limit)
    return [dict(r) | {"payload": json.loads(r["payload"])} for r in conn.execute(sql, params)]
