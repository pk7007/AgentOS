"""Worker health: heartbeats, stale-worker detection and recovery, and an automatic circuit breaker.

A host reports `agentos health heartbeat ID` while a worker runs. A worker that is active but has not been
heard from (no heartbeat, start or state change) for longer than the threshold is stale. `reap` marks a
stale worker FAILED (or CANCELLED before it started), frees its slot, and hands its task to the boss
recovery rule: retry with a template that has not failed it, or escalate to the owner at the retry limit.

The circuit breaker suspends a template automatically when its last `breaker.window` evaluations all
scored below `breaker.floor` (default: three in a row below 30), so a template whose work fails badly stops
being admitted at once, without waiting for anyone to run `agentos workforce review`. The review's own,
milder rule (three failing evaluations in a row, below 50) still applies when the review runs.
Re-activating a suspended template is a normal template status change."""

import sqlite3
from datetime import UTC, datetime, timedelta

from agentos import audit, lifecycle, tasks
from agentos.db import get_setting, put_setting, write_tx
from agentos.errors import PolicyDenied, UsageError
from agentos.lifecycle import ACTIVE_STATES, AgentState
from agentos.tasks import TaskState
from agentos.util import now_iso

DEFAULT_STALE_MINUTES = 15
BREAKER_WINDOW = 3
BREAKER_FLOOR = 30.0  # below the review's failing line (50): this catches work that failed badly


def heartbeat(conn: sqlite3.Connection, instance_id: str, project_id: str | None = None) -> dict:
    """Record that the worker is alive. Refused for a worker that is not active, or that belongs to another
    project than the one named. Heartbeats update one column and write no audit event, so frequent
    reporting does not grow the audit log."""
    inst = lifecycle.get_instance(conn, instance_id)
    if project_id is not None and inst.project_id != project_id:
        raise PolicyDenied(f"{instance_id} belongs to another project", reasons=["cross_project"])
    if inst.state not in ACTIVE_STATES:
        raise PolicyDenied(f"{instance_id} is {inst.state.value}, not active", reasons=["not_active"])
    ts = now_iso()
    with write_tx(conn):
        conn.execute("UPDATE agent_instances SET last_heartbeat=? WHERE id=?", (ts, instance_id))
    return {"instance_id": instance_id, "last_heartbeat": ts}


def _last_seen(row) -> str:
    seen = [row["updated_at"], row["created_at"]]
    seen += [x for x in (row["last_heartbeat"], row["started_at"]) if x]
    return max(seen)


def stale(conn: sqlite3.Connection, project_id: str | None = None,
          after_minutes: float = DEFAULT_STALE_MINUTES, now: datetime | None = None) -> list[dict]:
    if after_minutes <= 0:
        raise PolicyDenied("the stale threshold must be positive", reasons=["bad_threshold"])
    cutoff = (now or datetime.now(UTC)) - timedelta(minutes=after_minutes)
    marks = ",".join("?" * len(ACTIVE_STATES))
    sql = (f"SELECT i.*, b.started_at FROM agent_instances i LEFT JOIN runtime_bindings b ON b.instance_id=i.id"
           f" WHERE i.state IN ({marks})")
    params: list = [s.value for s in ACTIVE_STATES]
    if project_id:
        sql += " AND i.project_id=?"
        params.append(project_id)
    out = []
    for row in conn.execute(sql + " ORDER BY i.created_at", params):
        seen = _last_seen(row)
        if datetime.fromisoformat(seen) < cutoff:
            out.append({"instance_id": row["id"], "template_id": row["template_id"], "task_id": row["task_id"],
                        "state": row["state"], "last_seen": seen, "heartbeat": row["last_heartbeat"] is not None})
    return out


def reap(conn: sqlite3.Connection, project_id: str, actor: str, after_minutes: float = DEFAULT_STALE_MINUTES,
         now: datetime | None = None) -> dict:
    """Fail every stale worker of the project and recover its task. Returns what was done to each."""
    from agentos import boss

    actions = []
    for s in stale(conn, project_id, after_minutes, now):
        to = AgentState.CANCELLED if s["state"] == AgentState.ASSIGNED.value else AgentState.FAILED
        lifecycle.transition(conn, s["instance_id"], to, actor,
                             reason=f"no sign of life since {s['last_seen']}")
        step = {"instance_id": s["instance_id"], "to": to.value, "task_id": s["task_id"], "task_action": None}
        task = tasks.get_task(conn, s["task_id"])
        others = conn.execute(
            f"SELECT count(*) FROM agent_instances WHERE task_id=? AND state IN ({','.join('?' * len(ACTIVE_STATES))})",
            [task.id, *[x.value for x in ACTIVE_STATES]]).fetchone()[0]
        if task.state == TaskState.running and not others:
            tasks.set_state(conn, task.id, TaskState.failed, actor, note="worker went silent")
            step["task_action"] = boss.recover(conn, task.id, actor)
        actions.append(step)
    with write_tx(conn):
        audit.append_event(conn, "health.reaped", actor, {
            "after_minutes": after_minutes, "instances": [a["instance_id"] for a in actions]}, project_id)
    return {"after_minutes": after_minutes, "reaped": actions}


def breaker_settings(conn: sqlite3.Connection) -> dict:
    return {"window": int(get_setting(conn, "breaker.window", BREAKER_WINDOW)),
            "floor": float(get_setting(conn, "breaker.floor", BREAKER_FLOOR))}


def is_milder(old: dict, new: dict) -> bool:
    """A longer window or a lower floor lets a failing template keep working for longer."""
    return new["window"] > old["window"] or new["floor"] < old["floor"]


def proposed_breaker(conn: sqlite3.Connection, window: int | None, floor: float | None) -> tuple[dict, dict]:
    old = breaker_settings(conn)
    return old, {"window": old["window"] if window is None else int(window),
                 "floor": old["floor"] if floor is None else float(floor)}


def set_breaker(conn: sqlite3.Connection, actor: str, window: int | None = None, floor: float | None = None,
                owner=None) -> dict:
    """Change the circuit breaker. Making it stricter (a shorter window, a higher floor) needs nobody;
    making it milder needs the owner, because a milder breaker lets failing templates keep working.
    Every change is a policy change: it raises the policy version (`agentos policy history`)."""
    from agentos.governance import require_owner

    old, new = proposed_breaker(conn, window, floor)
    milder = is_milder(old, new)
    if not 1 <= new["window"] <= 20:
        raise UsageError("the breaker window is 1 to 20 evaluations")
    if not 0 <= new["floor"] <= 100:
        raise UsageError("the breaker floor is a score from 0 to 100")
    if milder:
        require_owner(owner, "making the circuit breaker milder")
    with write_tx(conn):
        put_setting(conn, "breaker.window", new["window"])
        put_setting(conn, "breaker.floor", new["floor"])
        audit.append_event(conn, "health.breaker_set", actor, {"old": old, "new": new,
                                                               "owner_confirmed": owner is not None})
    return {"old": old, "new": new}


def check_breaker(conn: sqlite3.Connection, template_id: str, actor: str) -> dict | None:
    """Called inside the evaluation transaction. Suspends the template when its last `window` unflagged
    evaluations all fell below the floor. Returns what it did, or None."""
    from agentos import templates
    from agentos.templates import TemplateStatus

    window, floor = breaker_settings(conn).values()
    if window < 1:
        return None
    recent = [r[0] for r in conn.execute(
        "SELECT weighted FROM evaluations WHERE template_id=? AND flags='[]' AND external_cause=0"
        " ORDER BY created_at DESC, rowid DESC LIMIT ?", (template_id, window))]
    if len(recent) < window or max(recent) >= floor:
        return None
    tpl = templates.get_template(conn, template_id)
    if tpl.status != TemplateStatus.active:
        return None
    reason = f"circuit breaker: last {window} evaluations below {floor:g} ({', '.join(f'{x:.0f}' for x in recent)})"
    templates.set_status(conn, template_id, TemplateStatus.suspended, actor, reason=reason)
    audit.append_event(conn, "health.breaker_tripped", actor, {
        "template_id": template_id, "window": window, "floor": floor, "scores": [round(x, 2) for x in recent]})
    return {"template_id": template_id, "status": "suspended", "reason": reason}
