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


def transition(conn: sqlite3.Connection, instance_id: str, to: AgentState, actor: str,
               reason: str | None = None, runtime_confirmed: bool | None = None) -> AgentInstance:
    from agentos import governor

    to = AgentState(to)
    with write_tx(conn):
        inst = get_instance(conn, instance_id)
        if not can_transition(inst.state, to):
            audit.append_event(conn, "agent.transition_denied", actor,
                               {"instance_id": instance_id, "from": inst.state.value, "to": to.value},
                               inst.project_id)
            denied = PolicyDenied(f"cannot move agent from {inst.state.value} to {to.value}",
                                  reasons=["illegal_transition"])
        else:
            denied = None
            confirmed = inst.termination_confirmed
            if to == S.TERMINATED:
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
