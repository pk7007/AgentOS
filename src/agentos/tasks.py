"""Task graph: a DAG of work units with guarded state changes."""

import json
import sqlite3
from enum import Enum
from typing import Literal

from pydantic import BaseModel

from agentos import audit
from agentos.db import write_tx
from agentos.errors import NotFound, PolicyDenied
from agentos.projects import require_active
from agentos.util import new_id, now_iso

MAX_TASK_DEPTH = 5


class TaskState(str, Enum):
    pending = "pending"
    running = "running"
    blocked = "blocked"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


S = TaskState
TASK_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    S.pending: {S.running, S.blocked, S.cancelled},
    S.running: {S.done, S.failed, S.blocked, S.cancelled},
    S.blocked: {S.pending, S.cancelled},
    S.failed: {S.pending, S.cancelled},
    S.done: set(),
    S.cancelled: set(),
}

Risk = Literal["low", "medium", "high", "critical"]


class Task(BaseModel):
    id: str
    project_id: str
    parent_id: str | None
    title: str
    objective: str
    capabilities: list[str]
    acceptance: list[str]
    priority: int
    risk: Risk
    state: TaskState
    retries: int
    max_retries: int
    depth: int
    created_at: str
    updated_at: str
    deps: list[str] = []


def _row(conn, row) -> Task:
    deps = [r[0] for r in conn.execute("SELECT depends_on FROM task_deps WHERE task_id=?", (row["id"],))]
    return Task(
        id=row["id"], project_id=row["project_id"], parent_id=row["parent_id"], title=row["title"],
        objective=row["objective"], capabilities=json.loads(row["capabilities"]),
        acceptance=json.loads(row["acceptance"]), priority=row["priority"], risk=row["risk"],
        state=row["state"], retries=row["retries"], max_retries=row["max_retries"], depth=row["depth"],
        created_at=row["created_at"], updated_at=row["updated_at"], deps=deps,
    )


def get_task(conn: sqlite3.Connection, task_id: str) -> Task:
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        raise NotFound(f"task not found: {task_id}")
    return _row(conn, row)


def list_tasks(conn: sqlite3.Connection, project_id: str, state: TaskState | None = None) -> list[Task]:
    sql, params = "SELECT * FROM tasks WHERE project_id=?", [project_id]
    if state:
        sql += " AND state=?"
        params.append(TaskState(state).value)
    sql += " ORDER BY created_at, rowid"
    return [_row(conn, r) for r in conn.execute(sql, params)]


def add_task(
    conn: sqlite3.Connection, project_id: str, title: str, objective: str = "",
    capabilities: list[str] | None = None, acceptance: list[str] | None = None,
    parent_id: str | None = None, priority: int = 50, risk: Risk = "low", actor: str = "host",
) -> Task:
    require_active(conn, project_id)
    depth = 0
    if parent_id:
        parent = get_task(conn, parent_id)
        if parent.project_id != project_id:
            raise PolicyDenied("parent task is in another project", reasons=["cross_project"])
        depth = parent.depth + 1
        if depth > MAX_TASK_DEPTH:
            raise PolicyDenied(f"task depth {depth} exceeds {MAX_TASK_DEPTH}", reasons=["max_task_depth"])
    from agentos.governor import get_limits

    max_retries = get_limits(conn).max_retries
    tid, ts = new_id("task"), now_iso()
    with write_tx(conn):
        conn.execute(
            "INSERT INTO tasks(id, project_id, parent_id, title, objective, capabilities, acceptance, "
            "priority, risk, state, retries, max_retries, depth, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,'pending',0,?,?,?,?)",
            (tid, project_id, parent_id, title, objective, json.dumps(capabilities or []),
             json.dumps(acceptance or []), priority, risk, max_retries, depth, ts, ts),
        )
        audit.append_event(conn, "task.added", actor, {"task_id": tid, "title": title}, project_id)
    return get_task(conn, tid)


def _reaches(conn, start: str, target: str) -> bool:
    seen, stack = set(), [start]
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(r[0] for r in conn.execute("SELECT depends_on FROM task_deps WHERE task_id=?", (node,)))
    return False


def add_dependency(conn: sqlite3.Connection, task_id: str, depends_on: str, actor: str) -> None:
    # The cycle check and the insert share one immediate transaction, so two sessions adding A->B and
    # B->A at the same time cannot both pass the check.
    with write_tx(conn):
        task, dep = get_task(conn, task_id), get_task(conn, depends_on)
        if task.project_id != dep.project_id:
            raise PolicyDenied("tasks are in different projects", reasons=["cross_project"])
        if task_id == depends_on or _reaches(conn, depends_on, task_id):
            raise PolicyDenied("dependency would create a cycle", reasons=["cycle"])
        conn.execute("INSERT OR IGNORE INTO task_deps VALUES (?, ?)", (task_id, depends_on))
        audit.append_event(conn, "task.dep_added", actor, {"task_id": task_id, "depends_on": depends_on},
                           task.project_id)


def ready_tasks(conn: sqlite3.Connection, project_id: str) -> list[Task]:
    rows = conn.execute(
        "SELECT * FROM tasks t WHERE project_id=? AND state='pending' AND NOT EXISTS ("
        "  SELECT 1 FROM task_deps d JOIN tasks o ON o.id=d.depends_on"
        "  WHERE d.task_id=t.id AND o.state!='done') "
        "ORDER BY priority DESC, created_at, rowid",
        (project_id,),
    )
    return [_row(conn, r) for r in rows]


def set_state(conn: sqlite3.Connection, task_id: str, to: TaskState, actor: str,
              note: str | None = None) -> Task:
    to = TaskState(to)
    with write_tx(conn):
        task = get_task(conn, task_id)
        if to not in TASK_TRANSITIONS[task.state]:
            raise PolicyDenied(f"cannot move task from {task.state.value} to {to.value}",
                               reasons=["illegal_transition"])
        retries = task.retries
        if task.state == S.pending and to == S.running:
            open_deps = conn.execute(
                "SELECT count(*) FROM task_deps d JOIN tasks o ON o.id=d.depends_on "
                "WHERE d.task_id=? AND o.state!='done'", (task_id,)).fetchone()[0]
            if open_deps:
                raise PolicyDenied(f"{open_deps} dependencies are not done",
                                   reasons=["dependencies_incomplete"])
        if task.state == S.failed and to == S.pending:
            if retries >= task.max_retries:
                raise PolicyDenied(f"retry limit {task.max_retries} reached", reasons=["retry_limit"])
            retries += 1
        conn.execute("UPDATE tasks SET state=?, retries=?, updated_at=? WHERE id=?",
                     (to.value, retries, now_iso(), task_id))
        audit.append_event(conn, "task.state", actor,
                           {"task_id": task_id, "from": task.state.value, "to": to.value, "note": note},
                           task.project_id)
    return get_task(conn, task_id)
