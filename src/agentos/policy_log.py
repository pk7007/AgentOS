"""Policy versions: the policy in force as one hashed snapshot, and every change to it in order.

The policy is the limits (local, host-reported and per project), the budgets, the tunable values, the
circuit breaker and the emergency stop; the snapshot hash covers exactly these. A change made through the
generic setting command (`settings.set`) also raises the version, and its key and value are in `history`,
but its value is not part of the hashed snapshot. Its version is the number of policy changes the audit log records, so it only ever goes up,
and each change names who made it and whether the owner confirmed it. The snapshot hash lets two
machines, or a before-and-after report, show that they ran under the same policy. Nothing here writes."""

import json
import sqlite3

from agentos import governance, governor, health, policy
from agentos.util import sha256_json

CHANGE_KINDS = ("limits.set", "limits.host", "limits.project", "budget.set", "governance.stop",
                "governance.stop_lifted", "governance.owner_pin_set", "governance.owner_pin_cleared",
                "improve.promoted", "improve.rolled_back", "health.breaker_set", "settings.set")


def _marks() -> str:
    return ",".join("?" * len(CHANGE_KINDS))


def snapshot(conn: sqlite3.Connection) -> dict:
    host = {r[0]: json.loads(r[1]) for r in conn.execute("SELECT key, value FROM settings WHERE key LIKE 'host.%'")}
    projects = {}
    for (pid,) in conn.execute("SELECT id FROM projects ORDER BY id"):
        if own := governor.project_limits(conn, pid):
            projects[pid] = own
    budgets = [dict(r) for r in conn.execute(
        "SELECT scope, scope_id, kind, limit_value FROM budgets ORDER BY scope, scope_id, kind")]
    body = {"limits": governor._local(conn).model_dump(), "host_limits": host, "project_limits": projects,
            "budgets": budgets, "tunables": policy.current(conn), "breaker": health.breaker_settings(conn),
            "emergency_stop": governance.is_stopped(conn)}
    version = conn.execute(f"SELECT count(*) FROM events WHERE kind IN ({_marks()})", CHANGE_KINDS).fetchone()[0]
    return {"version": version, "hash": sha256_json(body), "policy": body}


def history(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(f"SELECT seq, ts, kind, actor, project_id, payload FROM events WHERE kind IN ({_marks()})"
                        " ORDER BY seq", CHANGE_KINDS).fetchall()
    out = [{"version": i + 1, "seq": r["seq"], "ts": r["ts"], "kind": r["kind"], "actor": r["actor"],
            "project_id": r["project_id"], "change": json.loads(r["payload"])} for i, r in enumerate(rows)]
    return out[-limit:]
