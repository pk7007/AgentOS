"""Agent-instance lifecycle: a validated 17-state machine."""

import sqlite3
from enum import Enum

from pydantic import BaseModel

from agentos import audit
from agentos.db import write_tx
from agentos.errors import NotFound, PolicyDenied
from agentos.util import now_iso


class AgentState(str, Enum):
    PROPOSED = "PROPOSED"
    RECRUITED = "RECRUITED"
    VALIDATING = "VALIDATING"
    AVAILABLE = "AVAILABLE"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    BLOCKED = "BLOCKED"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRAINING = "RETRAINING"
    QUARANTINED = "QUARANTINED"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"
    TERMINATED = "TERMINATED"
    ARCHIVED = "ARCHIVED"


S = AgentState
TRANSITIONS: dict[AgentState, frozenset[AgentState]] = {
    S.PROPOSED: frozenset({S.RECRUITED, S.CANCELLED}),
    S.RECRUITED: frozenset({S.VALIDATING, S.CANCELLED}),
    S.VALIDATING: frozenset({S.AVAILABLE, S.FAILED, S.QUARANTINED}),
    S.AVAILABLE: frozenset({S.ASSIGNED, S.SUSPENDED, S.TERMINATED}),
    S.ASSIGNED: frozenset({S.RUNNING, S.CANCELLED, S.AVAILABLE}),
    S.RUNNING: frozenset({S.WAITING, S.BLOCKED, S.REVIEWING, S.COMPLETED, S.FAILED, S.CANCELLED, S.QUARANTINED}),
    S.WAITING: frozenset({S.RUNNING, S.CANCELLED, S.FAILED}),
    S.BLOCKED: frozenset({S.RUNNING, S.CANCELLED, S.FAILED}),
    S.REVIEWING: frozenset({S.COMPLETED, S.RUNNING, S.FAILED}),
    S.COMPLETED: frozenset({S.AVAILABLE, S.TERMINATED, S.ARCHIVED}),
    S.FAILED: frozenset({S.RETRAINING, S.TERMINATED, S.ASSIGNED}),
    S.RETRAINING: frozenset({S.VALIDATING, S.TERMINATED}),
    S.QUARANTINED: frozenset({S.SUSPENDED, S.TERMINATED}),
    S.SUSPENDED: frozenset({S.AVAILABLE, S.TERMINATED}),
    S.CANCELLED: frozenset({S.TERMINATED, S.ARCHIVED}),
    S.TERMINATED: frozenset({S.ARCHIVED}),
    S.ARCHIVED: frozenset(),
}

ACTIVE_STATES = frozenset({S.ASSIGNED, S.RUNNING, S.WAITING, S.BLOCKED, S.REVIEWING})


class AgentInstance(BaseModel):
    id: str
    template_id: str
    template_version: int
    project_id: str
    task_id: str
    parent_id: str | None
    depth: int
    host: str
    state: AgentState
    termination_confirmed: bool | None
    created_at: str
    updated_at: str
    last_reason: str | None

    def display_state(self) -> str:
        if self.state == S.TERMINATED and self.termination_confirmed is False:
            return "TERMINATED (unconfirmed)"
        return self.state.value


def can_transition(a: AgentState, b: AgentState) -> bool:
    return AgentState(b) in TRANSITIONS[AgentState(a)]


def _row(row) -> AgentInstance:
    data = dict(row)
    tc = data["termination_confirmed"]
    data["termination_confirmed"] = None if tc is None else bool(tc)
    return AgentInstance(**data)


def get_instance(conn: sqlite3.Connection, instance_id: str) -> AgentInstance:
    row = conn.execute("SELECT * FROM agent_instances WHERE id=?", (instance_id,)).fetchone()
    if not row:
        raise NotFound(f"agent instance not found: {instance_id}")
    return _row(row)


def list_instances(conn: sqlite3.Connection, project_id: str | None = None, state: AgentState | None = None,
                   active_only: bool = False) -> list[AgentInstance]:
    sql, params = "SELECT * FROM agent_instances WHERE 1=1", []
    if project_id:
        sql += " AND project_id=?"
        params.append(project_id)
    if state:
        sql += " AND state=?"
        params.append(AgentState(state).value)
    if active_only:
        sql += f" AND state IN ({','.join('?' * len(ACTIVE_STATES))})"
        params.extend(s.value for s in ACTIVE_STATES)
    return [_row(r) for r in conn.execute(sql + " ORDER BY created_at, rowid", params)]


def active_count(conn: sqlite3.Connection) -> int:
    marks = ",".join("?" * len(ACTIVE_STATES))
    return conn.execute(f"SELECT count(*) FROM agent_instances WHERE state IN ({marks})",
                        [s.value for s in ACTIVE_STATES]).fetchone()[0]


# A worker holds a concurrency slot while it may still be running: in an active state, after a
# cancel request, or after a termination the host has not confirmed at the runtime.
_SLOT_SQL = (f"state IN ({','.join(repr(s.value) for s in sorted(ACTIVE_STATES))}) OR state='CANCELLED' "
             "OR (state='TERMINATED' AND coalesce(termination_confirmed, 0)=0)")


def slot_count(conn: sqlite3.Connection) -> int:
    return conn.execute(f"SELECT count(*) FROM agent_instances WHERE {_SLOT_SQL}").fetchone()[0]


def _stop_unconfirmed(inst: "AgentInstance") -> bool:
    return inst.state == S.CANCELLED or (inst.state == S.TERMINATED and not inst.termination_confirmed)


def confirm_stopped(conn: sqlite3.Connection, instance_id: str, actor: str) -> AgentInstance:
    """The host confirms the runtime worker is gone. CANCELLED becomes TERMINATED; either way the slot frees."""
    inst = get_instance(conn, instance_id)
    if inst.state == S.CANCELLED:
        return transition(conn, instance_id, S.TERMINATED, actor, reason="runtime stop confirmed",
                          runtime_confirmed=True)
    if inst.state != S.TERMINATED or inst.termination_confirmed:
        raise PolicyDenied(f"nothing to confirm: agent is {inst.display_state()}", reasons=["not_stopping"])
    with write_tx(conn):
        conn.execute("UPDATE agent_instances SET termination_confirmed=1, updated_at=? WHERE id=?",
                     (now_iso(), instance_id))
        audit.append_event(conn, "agent.stop_confirmed", actor, {"instance_id": instance_id}, inst.project_id)
    return get_instance(conn, instance_id)


def _entry_reasons(conn, inst: "AgentInstance", to: AgentState, runtime_confirmed) -> list[str]:
    """Checks beyond the state graph: re-entering active work goes through admission's checks, and a
    worker whose stop is unconfirmed can only be archived once the host confirms it."""
    if to in ACTIVE_STATES and inst.state not in ACTIVE_STATES:
        from agentos.admission import standing_reasons

        return standing_reasons(conn, inst.project_id, inst.task_id, inst.template_id)[0]
    if to == S.ARCHIVED and _stop_unconfirmed(inst) and not runtime_confirmed:
        return ["termination_unconfirmed"]
    return []


def transition(conn: sqlite3.Connection, instance_id: str, to: AgentState, actor: str,
               reason: str | None = None, runtime_confirmed: bool | None = None) -> AgentInstance:
    from agentos import governor

    to = AgentState(to)
    with write_tx(conn):
        inst = get_instance(conn, instance_id)
        if not can_transition(inst.state, to):
            reasons, message = ["illegal_transition"], f"cannot move agent from {inst.state.value} to {to.value}"
        else:
            reasons = _entry_reasons(conn, inst, to, runtime_confirmed)
            message = f"agent cannot move from {inst.state.value} to {to.value}: {', '.join(reasons)}"
            if not reasons and to in ACTIVE_STATES and inst.state not in ACTIVE_STATES:
                from agentos.admission import chain_for

                try:
                    governor.reserve(conn, chain_for(inst.project_id, inst.task_id), "agent_runs", 1,
                                     holder=instance_id)
                except PolicyDenied as exc:
                    reasons, message = exc.reasons, exc.message
        if reasons:
            audit.append_event(conn, "agent.transition_denied", actor,
                               {"instance_id": instance_id, "from": inst.state.value, "to": to.value,
                                "reasons": reasons}, inst.project_id)
            denied = PolicyDenied(message, reasons=reasons)
        else:
            denied = None
            confirmed = inst.termination_confirmed
            if to == S.TERMINATED or (to == S.ARCHIVED and _stop_unconfirmed(inst)):
                confirmed = bool(runtime_confirmed)
            conn.execute(
                "UPDATE agent_instances SET state=?, termination_confirmed=?, last_reason=?, updated_at=? WHERE id=?",
                (to.value, None if confirmed is None else int(confirmed), reason, now_iso(), instance_id),
            )
            if inst.state in ACTIVE_STATES and to not in ACTIVE_STATES:
                governor.release_for_instance(conn, instance_id)
            audit.append_event(conn, "agent.transition", actor, {
                "instance_id": instance_id, "from": inst.state.value, "to": to.value, "reason": reason,
                "runtime_confirmed": runtime_confirmed}, inst.project_id)
    if denied:
        raise denied
    return get_instance(conn, instance_id)
