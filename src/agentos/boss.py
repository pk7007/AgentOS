"""The Boss Agent's ledger: one objective from understanding to delivery.

AgentOS never calls a model. The host's lead agent understands the objective, decomposes it and does
or delegates the work; this module holds it to account. It
- records the objective with testable acceptance criteria and a complexity band;
- applies a decomposition plan atomically (unique keys, known dependencies, no cycles);
- forms a department only when enough of the work shares one function;
- schedules ready work by critical path, picks a template that covers every capability, dry-runs
  admission, and respects free concurrency slots;
- finds bottlenecks (blockers, failures, gaps, saturation, stale or orphaned workers, budgets);
- accepts a task only on an independent evaluation backed by passing evidence;
- recovers a failed task with a different template, or escalates when retries are spent;
- reviews the objective through nine executive functions, which are checks, not workers;
- delivers only when every task is done and accepted and every criterion has passing evidence.
"""

import json
import sqlite3
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from agentos import audit, governance, governor, lifecycle, recruit, tasks, templates
from agentos.complexity import ComplexityInput
from agentos.complexity import score as complexity_score
from agentos.db import write_tx
from agentos.errors import NotFound, PolicyDenied, UsageError
from agentos.lifecycle import ACTIVE_STATES, AgentState
from agentos.projects import require_active
from agentos.tasks import TaskState
from agentos.templates import TemplateStatus
from agentos.util import new_id, now_iso

FUNCTIONS = ("operations", "engineering", "hr", "finance", "intelligence", "security", "data", "risk", "quality")
CAP_FUNCTION = {
    "review": "quality", "testing": "quality", "qa": "quality", "verification": "quality",
    "security": "security", "research": "intelligence", "analysis": "intelligence",
    "data": "data", "database": "data", "migration": "data",
    "planning": "operations", "decomposition": "operations", "debugging": "operations",
    "recovery": "operations", "budget": "finance", "cost": "finance",
    "risk": "risk", "compliance": "risk", "recruitment": "hr", "staffing": "hr",
}
RISKS = ("low", "medium", "high", "critical")
DEPT_MIN_TASKS = 3          # a department forms only when this many tasks share a function
LARGE_BANDS = ("department", "hierarchical")
LEAD_MIN_READY = 3          # ...and a department lead worker is suggested only for large objectives
LEAD_TEMPLATE = "lead"
DEFAULT_MIN_SCORE = 70.0
STALE_MINUTES = 60
BUDGET_WARN = 0.8
CLOSED = (TaskState.done, TaskState.cancelled)


class Objective(BaseModel):
    id: str
    project_id: str
    title: str
    statement: str
    acceptance: list[str]
    complexity_score: int | None
    complexity_band: str | None
    state: str
    created_at: str
    updated_at: str
    delivered_at: str | None


def _obj_row(row) -> Objective:
    d = dict(row)
    d["acceptance"] = json.loads(d["acceptance"])
    d.pop("report", None)
    return Objective(**d)


def get_objective(conn: sqlite3.Connection, objective_id: str) -> Objective:
    row = conn.execute("SELECT * FROM objectives WHERE id=?", (objective_id,)).fetchone()
    if not row:
        raise NotFound(f"objective not found: {objective_id}")
    return _obj_row(row)


def list_objectives(conn: sqlite3.Connection, project_id: str) -> list[Objective]:
    return [_obj_row(r) for r in conn.execute(
        "SELECT * FROM objectives WHERE project_id=? ORDER BY created_at, rowid", (project_id,))]


def create_objective(conn: sqlite3.Connection, project_id: str, title: str, statement: str = "",
                     acceptance: list[str] | None = None, complexity: dict | None = None,
                     actor: str = "host") -> Objective:
    require_active(conn, project_id)
    title = (title or "").strip()
    if not title:
        raise UsageError("an objective needs a title")
    criteria = [c.strip() for c in (acceptance or []) if c and c.strip()]
    if not criteria:
        raise PolicyDenied("an objective needs at least one testable acceptance criterion",
                           reasons=["no_acceptance_criteria"])
    cscore = band = None
    if complexity is not None:
        result = complexity_score(ComplexityInput(**complexity))
        cscore, band = result.score, result.band
    oid, ts = new_id("obj"), now_iso()
    with write_tx(conn):
        conn.execute(
            "INSERT INTO objectives(id, project_id, title, statement, acceptance, complexity_score,"
            " complexity_band, state, created_at, updated_at) VALUES (?,?,?,?,?,?,?,'open',?,?)",
            (oid, project_id, title, statement or "", json.dumps(criteria), cscore, band, ts, ts))
        audit.append_event(conn, "boss.objective_created", actor,
                           {"objective_id": oid, "title": title, "criteria": len(criteria), "band": band},
                           project_id)
    return get_objective(conn, oid)


def objective_tasks(conn: sqlite3.Connection, objective_id: str) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT id FROM tasks WHERE objective_id=? ORDER BY created_at, rowid", (objective_id,))]


def _tasks(conn, objective_id: str) -> list[tuple]:
    """(Task, department, effort) for every task of the objective."""
    out = []
    for r in conn.execute("SELECT id, department, effort FROM tasks WHERE objective_id=? ORDER BY created_at, rowid",
                          (objective_id,)):
        out.append((tasks.get_task(conn, r[0]), r[1], r[2]))
    return out


def departments(conn: sqlite3.Connection, objective_id: str) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT function FROM departments WHERE objective_id=? AND dissolved_at IS NULL ORDER BY function",
        (objective_id,))]


def dissolve_departments(conn: sqlite3.Connection, objective_id: str, actor: str) -> list[str]:
    """Dissolve every department of the objective that has no open task left. The record stays."""
    obj = get_objective(conn, objective_id)
    closed = tuple(s.value for s in CLOSED)
    out = []
    with write_tx(conn):
        for fn in departments(conn, obj.id):
            open_n = conn.execute(f"SELECT count(*) FROM tasks WHERE objective_id=? AND department=?"
                                  f" AND state NOT IN ({','.join('?' * len(closed))})",
                                  (obj.id, fn, *closed)).fetchone()[0]
            if open_n == 0:
                conn.execute("UPDATE departments SET dissolved_at=? WHERE objective_id=? AND function=?",
                             (now_iso(), obj.id, fn))
                audit.append_event(conn, "boss.department_dissolved", actor,
                                   {"objective_id": obj.id, "function": fn}, obj.project_id)
                out.append(fn)
    return out


def function_for(capabilities: list[str], explicit: str | None = None) -> str:
    if explicit:
        return explicit
    for cap in capabilities:
        fn = CAP_FUNCTION.get(cap.strip().lower())
        if fn:
            return fn
    return "engineering"


def _require_open(obj: Objective) -> None:
    if obj.state != "open":
        raise PolicyDenied(f"objective is {obj.state}", reasons=["objective_not_open"])


def _validate_plan(conn, obj: Objective, plan) -> list[dict]:
    items = plan.get("tasks") if isinstance(plan, dict) else None
    if not isinstance(items, list) or not items:
        raise UsageError("the plan has no tasks")
    existing = set(objective_tasks(conn, obj.id))
    keys: set[str] = set()
    out = []
    for i, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise UsageError(f"task {i} is not an object")
        key = str(raw.get("key") or "").strip()
        if not key:
            raise UsageError(f"task {i} needs a key")
        if key in keys:
            raise UsageError(f"duplicate task key: {key}")
        keys.add(key)
        title = str(raw.get("title") or "").strip()
        if not title:
            raise UsageError(f"task {key} needs a title")
        caps = raw.get("capabilities") or []
        accept = raw.get("acceptance") or []
        if not isinstance(caps, list) or not isinstance(accept, list):
            raise UsageError(f"task {key}: capabilities and acceptance must be lists")
        risk = raw.get("risk", "low")
        if risk not in RISKS:
            raise UsageError(f"task {key}: unknown risk {risk!r} (allowed: {', '.join(RISKS)})")
        dept = raw.get("department")
        if dept is not None and dept not in FUNCTIONS:
            raise UsageError(f"task {key}: unknown department {dept!r} (allowed: {', '.join(FUNCTIONS)})")
        try:
            priority, effort = int(raw.get("priority", 50)), int(raw.get("effort", 1))
        except (TypeError, ValueError) as exc:
            raise UsageError(f"task {key}: priority and effort must be integers") from exc
        if not 0 <= priority <= 100 or effort < 1:
            raise UsageError(f"task {key}: priority must be 0-100 and effort at least 1")
        parent = raw.get("parent")
        if parent is not None and parent not in existing:
            raise PolicyDenied(f"task {key}: parent {parent} is not a task of this objective",
                               reasons=["cross_objective"])
        deps = [str(d) for d in raw.get("depends_on") or []]
        out.append({"key": key, "title": title, "objective": str(raw.get("objective") or ""),
                    "capabilities": [str(c) for c in caps], "acceptance": [str(a) for a in accept],
                    "risk": risk, "department": function_for([str(c) for c in caps], dept),
                    "priority": priority, "effort": effort, "parent": parent, "depends_on": deps})
    for item in out:
        for d in item["depends_on"]:
            if d in keys or d in existing:
                continue
            if d.startswith("task_") and conn.execute("SELECT 1 FROM tasks WHERE id=?", (d,)).fetchone():
                raise PolicyDenied(f"task {item['key']}: {d} is not a task of this objective",
                                   reasons=["cross_objective"])
            raise UsageError(f"task {item['key']}: unknown dependency {d}")
    return out


def _topo(items: list[dict]) -> list[dict]:
    by_key = {i["key"]: i for i in items}
    waiting = {i["key"]: {d for d in i["depends_on"] if d in by_key} for i in items}
    order: list[dict] = []
    while waiting:
        ready = [k for k in by_key if k in waiting and not waiting[k]]
        if not ready:
            raise PolicyDenied("the plan's dependencies form a cycle: " + ", ".join(sorted(waiting)),
                               reasons=["cycle"])
        for k in ready:
            order.append(by_key[k])
            del waiting[k]
        for rest in waiting.values():
            rest.difference_update(ready)
    return order


def _form_departments(conn, obj: Objective, actor: str) -> None:
    need = 2 if obj.complexity_band in LARGE_BANDS else DEPT_MIN_TASKS
    have = set(departments(conn, obj.id))
    for fn, n in conn.execute("SELECT department, count(*) FROM tasks WHERE objective_id=? GROUP BY department",
                              (obj.id,)):
        if fn and n >= need and fn not in have:
            conn.execute("INSERT INTO departments(id, objective_id, function, created_at) VALUES (?,?,?,?)"
                         " ON CONFLICT(objective_id, function) DO UPDATE SET dissolved_at=NULL",
                         (new_id("dep"), obj.id, fn, now_iso()))
            audit.append_event(conn, "boss.department_created", actor,
                               {"objective_id": obj.id, "function": fn, "tasks": n}, obj.project_id)


def apply_plan(conn: sqlite3.Connection, objective_id: str, plan: dict, actor: str) -> dict:
    """Create the plan's tasks and dependencies in one transaction; nothing is created if any part fails."""
    obj = get_objective(conn, objective_id)
    _require_open(obj)
    order = _topo(_validate_plan(conn, obj, plan))
    created: dict[str, str] = {}
    with write_tx(conn):
        for item in order:
            t = tasks.add_task(conn, obj.project_id, item["title"], objective=item["objective"],
                               capabilities=item["capabilities"], acceptance=item["acceptance"],
                               parent_id=item["parent"], priority=item["priority"], risk=item["risk"],
                               actor=actor)
            conn.execute("UPDATE tasks SET objective_id=?, department=?, effort=? WHERE id=?",
                         (obj.id, item["department"], item["effort"], t.id))
            created[item["key"]] = t.id
            for d in item["depends_on"]:
                tasks.add_dependency(conn, t.id, created.get(d, d), actor)
        _form_departments(conn, obj, actor)
        conn.execute("UPDATE objectives SET updated_at=? WHERE id=?", (now_iso(), obj.id))
        audit.append_event(conn, "boss.plan_applied", actor,
                           {"objective_id": obj.id, "created": len(created)}, obj.project_id)
    gaps = {i["key"]: g for i in order if (g := recruit.missing_capabilities(conn, i["capabilities"]))}
    return {"objective_id": obj.id, "created": created, "departments": departments(conn, obj.id),
            "capability_gaps": gaps}


def _critical_paths(items: list[tuple]) -> dict[str, int]:
    """Longest chain of open work (by effort) that starts at each open task."""
    open_ids = {t.id for t, _, _ in items if t.state not in CLOSED}
    effort = {t.id: e for t, _, e in items}
    dependents: dict[str, list[str]] = {i: [] for i in open_ids}
    for t, _, _ in items:
        if t.id in open_ids:
            for d in t.deps:
                if d in open_ids:
                    dependents[d].append(t.id)
    memo: dict[str, int] = {}

    def walk(tid: str) -> int:
        if tid not in memo:
            memo[tid] = effort[tid] + max((walk(n) for n in dependents[tid]), default=0)
        return memo[tid]

    return {tid: walk(tid) for tid in open_ids}


def _open_dependents(items: list[tuple]) -> dict[str, int]:
    open_ids = {t.id for t, _, _ in items if t.state not in CLOSED}
    direct: dict[str, set[str]] = {i: set() for i in open_ids}
    for t, _, _ in items:
        if t.id in open_ids:
            for d in t.deps:
                if d in open_ids:
                    direct[d].add(t.id)
    out = {}
    for tid in open_ids:
        seen, stack = set(), list(direct[tid])
        while stack:
            n = stack.pop()
            if n not in seen:
                seen.add(n)
                stack.extend(direct[n])
        out[tid] = len(seen)
    return out


def _full_match(conn, caps: list[str], avoid: set[str] = frozenset()) -> list[str]:
    need = {c.strip().lower() for c in caps if c.strip()}
    return [c.template_id for c in recruit.rank(conn, caps) if c.match == 1.0 and c.template_id not in avoid
            and need]


def schedule(conn: sqlite3.Connection, objective_id: str) -> dict:
    from agentos.admission import standing_reasons

    obj = get_objective(conn, objective_id)
    items = _tasks(conn, obj.id)
    cp = _critical_paths(items)
    dept = {t.id: d for t, d, _ in items}
    ready_ids = {t.id for t in tasks.ready_tasks(conn, obj.project_id)}
    ready = [t for t, _, _ in items if t.id in ready_ids]
    ready.sort(key=lambda t: (-cp.get(t.id, 0), -t.priority, t.created_at))
    free = max(0, governor.get_limits(conn).max_concurrent - lifecycle.slot_count(conn))
    slots = free
    dispatch = []
    for t in ready:
        candidates = _full_match(conn, t.capabilities)
        template = candidates[0] if candidates else None
        reasons = standing_reasons(conn, obj.project_id, t.id, template)[0] if template else []
        policy = [r for r in reasons if r != "max_concurrent"]
        if template is None:
            status = "capability_gap"
        elif policy:
            status = "blocked_by_policy"
        elif slots > 0:
            status, slots = "dispatch", slots - 1
        else:
            status = "queued_capacity"
        dispatch.append({"task_id": t.id, "title": t.title, "department": dept[t.id], "risk": t.risk,
                         "priority": t.priority, "critical_path": cp.get(t.id, 0), "template_id": template,
                         "candidates": candidates[:3], "would_admit": template is not None and not reasons,
                         "reasons": policy, "status": status})
    leads = []
    if obj.complexity_band in LARGE_BANDS:
        try:
            lead = templates.get_template(conn, LEAD_TEMPLATE)
            lead_ok = lead.status == TemplateStatus.active and lead.can_delegate
        except NotFound:
            lead_ok = False
        for fn in departments(conn, obj.id):
            n = sum(1 for t in ready if dept[t.id] == fn)
            if lead_ok and n >= LEAD_MIN_READY:
                leads.append({"department": fn, "template_id": LEAD_TEMPLATE, "ready_tasks": n})
    return {"objective_id": obj.id, "free_slots": free, "dispatch": dispatch, "executive_workers": leads}


def _ago(minutes: int) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _accepted(conn, task_id: str):
    return conn.execute("SELECT * FROM task_acceptances WHERE task_id=?", (task_id,)).fetchone()


def bottlenecks(conn: sqlite3.Connection, objective_id: str) -> list[dict]:
    obj = get_objective(conn, objective_id)
    items = _tasks(conn, obj.id)
    waiting_on = _open_dependents(items)
    found: list[dict] = []
    for t, _, _ in items:
        if t.state == TaskState.blocked:
            found.append({"kind": "blocked_task", "task_id": t.id, "detail": t.title})
        if t.state == TaskState.failed:
            left = t.max_retries - t.retries
            found.append({"kind": "failed_task", "task_id": t.id,
                          "detail": f"{left} retries left" if left > 0 else "retries exhausted"})
        if t.state != TaskState.running and t.state not in CLOSED and waiting_on.get(t.id, 0) >= 2:
            found.append({"kind": "critical_blocker", "task_id": t.id,
                          "detail": f"{waiting_on[t.id]} tasks wait on it and it is {t.state.value}"})
        if t.state not in CLOSED:
            gaps = recruit.missing_capabilities(conn, t.capabilities)
            if gaps:
                found.append({"kind": "capability_gap", "task_id": t.id, "detail": ", ".join(gaps)})
        if t.state == TaskState.done and not _accepted(conn, t.id):
            found.append({"kind": "unaccepted_done", "task_id": t.id, "detail": "done but not accepted"})
    task_ids = [t.id for t, _, _ in items]
    if task_ids:
        marks = ",".join("?" * len(task_ids))
        active = ",".join(f"'{s.value}'" for s in ACTIVE_STATES)
        stale = _ago(STALE_MINUTES)
        for r in conn.execute(
                f"SELECT i.id, i.task_id, i.updated_at, b.stopped_at FROM agent_instances i"
                f" LEFT JOIN runtime_bindings b ON b.instance_id=i.id"
                f" WHERE i.task_id IN ({marks}) AND i.state IN ({active})", task_ids):
            if r["stopped_at"]:
                found.append({"kind": "orphan_worker", "task_id": r["task_id"], "instance_id": r["id"],
                              "detail": "the runtime reports this worker stopped; the ledger still shows it active"})
            elif r["updated_at"] < stale:
                found.append({"kind": "stale_worker", "task_id": r["task_id"], "instance_id": r["id"],
                              "detail": f"no update since {r['updated_at']}"})
    ready = [t for t in tasks.ready_tasks(conn, obj.project_id) if t.id in set(task_ids)]
    if ready and lifecycle.slot_count(conn) >= governor.get_limits(conn).max_concurrent:
        found.append({"kind": "capacity_saturated", "detail": f"{len(ready)} ready tasks, no free slot"})
    scopes = {("global", "*"), ("project", obj.project_id)} | {("task", t) for t in task_ids}
    for b in governor.budget_report(conn):
        if (b["scope"], b["scope_id"]) in scopes and b["limit"] > 0 and b["used"] >= BUDGET_WARN * b["limit"]:
            found.append({"kind": "budget_low", "detail": f"{b['scope']}:{b['scope_id']}:{b['kind']} "
                                                          f"{b['used']:g} of {b['limit']:g} used"})
    return found


def accept_task(conn: sqlite3.Connection, task_id: str, evaluation_id: str, actor: str,
                min_score: float = DEFAULT_MIN_SCORE) -> dict:
    """Quality gate: a task counts as delivered only on an independent evaluation of a worker on that
    task, at or above `min_score`, unflagged, citing evidence whose command passed."""
    from agentos import performance

    task = tasks.get_task(conn, task_id)
    if not conn.execute("SELECT 1 FROM evaluations WHERE id=?", (evaluation_id,)).fetchone():
        raise NotFound(f"evaluation not found: {evaluation_id}")
    ev = performance.get_eval(conn, evaluation_id)
    with write_tx(conn):
        if _accepted(conn, task_id):
            raise PolicyDenied("task is already accepted", reasons=["already_accepted"])
        reasons = []
        if task.state != TaskState.done:
            reasons.append("task_not_done")
        if lifecycle.get_instance(conn, ev.instance_id).task_id != task_id:
            reasons.append("evaluation_not_for_task")
        if ev.weighted < min_score:
            reasons.append("score_below_threshold")
        if ev.flags:
            reasons.append("evaluation_flagged")
        passing = None
        for ref in ev.evidence:
            row = conn.execute("SELECT exit_code, timed_out FROM evidence WHERE id=?", (ref,)).fetchone()
            if row and row["exit_code"] == 0 and not row["timed_out"]:
                passing = ref
                break
        if passing is None:
            reasons.append("no_passing_evidence")
        if reasons:
            audit.append_event(conn, "boss.acceptance_denied", actor,
                               {"task_id": task_id, "evaluation_id": evaluation_id, "reasons": reasons},
                               task.project_id)
            denied = PolicyDenied(f"task cannot be accepted: {', '.join(reasons)}", reasons=reasons)
        else:
            denied = None
            conn.execute("INSERT INTO task_acceptances VALUES (?,?,?,?,?)",
                         (task_id, evaluation_id, passing, now_iso(), actor))
            audit.append_event(conn, "boss.task_accepted", actor,
                               {"task_id": task_id, "evaluation_id": evaluation_id, "evidence_id": passing,
                                "weighted": round(ev.weighted, 2)}, task.project_id)
    if denied:
        raise denied
    from agentos import improve

    retro = improve.retro(conn, task.project_id, actor, task_id=task_id)
    return {"task_id": task_id, "accepted": True, "evaluation_id": evaluation_id, "evidence_id": passing,
            "retrospective": _retro_brief(retro)}


def _retro_brief(retro: dict) -> dict:
    return {"id": retro["id"], "weaknesses": len(retro["weaknesses"]), "hypotheses": len(retro["hypotheses"]),
            "next": f"agentos improve retro --show {retro['id']}" if retro["hypotheses"] else None}


def recover(conn: sqlite3.Connection, task_id: str, actor: str) -> dict:
    """A failed task is retried with a template that has not failed it, or escalated to the owner."""
    task = tasks.get_task(conn, task_id)
    if task.state != TaskState.failed:
        raise PolicyDenied(f"task is {task.state.value}, not failed", reasons=["task_not_failed"])
    failed = {r[0] for r in conn.execute(
        "SELECT DISTINCT template_id FROM agent_instances WHERE task_id=? AND state IN (?, ?)",
        (task_id, AgentState.FAILED.value, AgentState.QUARANTINED.value))}
    if task.retries >= task.max_retries:
        with write_tx(conn):
            audit.append_event(conn, "boss.escalated", actor,
                               {"task_id": task_id, "retries": task.retries, "failed_templates": sorted(failed)},
                               task.project_id)
        return {"action": "escalate_owner", "task_id": task_id, "avoid_templates": sorted(failed),
                "detail": f"retry limit {task.max_retries} reached; the owner decides: raise the limit, "
                          "re-plan the task or cancel it"}
    retried = tasks.set_state(conn, task_id, TaskState.pending, actor, note="boss recovery")
    options = _full_match(conn, task.capabilities, avoid=failed)
    with write_tx(conn):
        audit.append_event(conn, "boss.recovery", actor,
                           {"task_id": task_id, "avoid": sorted(failed), "suggested": options[:1]},
                           task.project_id)
    return {"action": "retry", "task_id": task_id, "retries": retried.retries,
            "avoid_templates": sorted(failed), "suggested_template": options[0] if options else None}


def _related_memory(conn, obj: Objective) -> list[str]:
    from agentos import memory

    words = sorted({w.strip(".,:;!?()").lower() for w in obj.title.split() if len(w) > 3})[:4]
    ids: list[str] = []
    for w in words:
        for rec in memory.search(conn, obj.project_id, w, limit=3):
            if rec.id not in ids:
                ids.append(rec.id)
    return ids[:5]


def review(conn: sqlite3.Connection, objective_id: str) -> dict:
    """The nine executive functions, as checks over the ledger. None of them starts a worker."""
    obj = get_objective(conn, objective_id)
    items = _tasks(conn, obj.id)
    found = bottlenecks(conn, obj.id)
    kinds = {}
    for f in found:
        kinds.setdefault(f["kind"], []).append(f)
    counts: dict[str, int] = {}
    for t, _, _ in items:
        counts[t.state.value] = counts.get(t.state.value, 0) + 1
    ids = [t.id for t, _, _ in items]
    marks = ",".join("?" * len(ids)) or "''"
    instances = conn.execute(f"SELECT template_id, state FROM agent_instances WHERE task_id IN ({marks})",
                             ids).fetchall()
    flagged = conn.execute(
        f"SELECT count(*) FROM evaluations e JOIN agent_instances i ON i.id=e.instance_id"
        f" WHERE i.task_id IN ({marks}) AND e.flags != '[]'", ids).fetchone()[0]

    def fn(attention: bool, *notes: str) -> dict:
        return {"status": "attention" if attention else "ok", "findings": [n for n in notes if n]}

    ops = [k for k in ("blocked_task", "critical_blocker", "capacity_saturated", "stale_worker", "orphan_worker")
           if k in kinds]
    no_accept = [t.id for t, _, _ in items if not t.acceptance and t.state not in CLOSED]
    staffing: dict[str, int] = {}
    for r in instances:
        if AgentState(r["state"]) in ACTIVE_STATES:
            staffing[r["template_id"]] = staffing.get(r["template_id"], 0) + 1
    risky = [t.id for t, _, _ in items if t.risk in ("high", "critical") and t.state not in CLOSED]
    exhausted = [f["task_id"] for f in kinds.get("failed_task", []) if f["detail"] == "retries exhausted"]
    done_no_evidence = [t.id for t, _, _ in items if t.state == TaskState.done and not conn.execute(
        "SELECT 1 FROM evaluations e JOIN agent_instances i ON i.id=e.instance_id WHERE i.task_id=?",
        (t.id,)).fetchone()]
    unaccepted = [f["task_id"] for f in kinds.get("unaccepted_done", [])]
    memories = _related_memory(conn, obj)
    functions = {
        "operations": fn(bool(ops), f"progress: {counts}", ", ".join(ops) and "bottlenecks: " + ", ".join(ops)),
        "engineering": fn(bool(no_accept), f"{len(items)} tasks, departments: {departments(conn, obj.id) or 'none'}",
                          no_accept and f"tasks without acceptance criteria: {', '.join(no_accept)}"),
        "hr": fn("capability_gap" in kinds, f"active workers by template: {staffing or 'none'}",
                 "capability_gap" in kinds and "capability gaps: "
                 + ", ".join(f["task_id"] for f in kinds["capability_gap"])),
        "finance": fn("budget_low" in kinds, "paid spend cap is enforced by `limits`",
                      *(f["detail"] for f in kinds.get("budget_low", []))),
        "intelligence": fn(False, f"related project memories: {', '.join(memories) or 'none'}"),
        "security": fn(bool(flagged) or governance.is_stopped(conn),
                       flagged and f"{flagged} flagged evaluations",
                       governance.is_stopped(conn) and "emergency stop is active"),
        "data": fn(bool(done_no_evidence),
                   done_no_evidence and f"done without any graded evidence: {', '.join(done_no_evidence)}"),
        "risk": fn(bool(risky or exhausted), risky and f"open high/critical tasks: {', '.join(risky)}",
                   exhausted and f"retries exhausted: {', '.join(exhausted)}"),
        "quality": fn(bool(unaccepted), unaccepted and f"done but not accepted: {', '.join(unaccepted)}"),
    }
    return {"objective": obj.model_dump(), "functions": functions, "bottlenecks": found,
            "note": "executive functions are checks run by AgentOS; none starts a worker"}


def deliver(conn: sqlite3.Connection, objective_id: str, criteria_evidence: dict, actor: str) -> dict:
    """Final delivery: every task done (or cancelled) and accepted, every acceptance criterion backed by
    passing evidence from this project. Writes a delivery report and closes the objective."""
    from agentos import evidence as evidence_mod

    obj = get_objective(conn, objective_id)
    _require_open(obj)
    mapping = {}
    for k, v in (criteria_evidence or {}).items():
        try:
            idx = int(k)
        except (TypeError, ValueError) as exc:
            raise UsageError(f"criterion index must be a number, got {k!r}") from exc
        if not 0 <= idx < len(obj.acceptance):
            raise UsageError(f"criterion {idx} does not exist (0-{len(obj.acceptance) - 1})")
        mapping[idx] = str(v)
    items = _tasks(conn, obj.id)
    reasons: list[str] = []
    if any(t.state not in CLOSED for t, _, _ in items):
        reasons.append("tasks_open")
    done = [t for t, _, _ in items if t.state == TaskState.done]
    if not done:
        reasons.append("nothing_delivered")
    if any(not _accepted(conn, t.id) for t in done):
        reasons.append("tasks_unaccepted")
    criteria = []
    for i, text in enumerate(obj.acceptance):
        if i not in mapping:
            if "criteria_without_evidence" not in reasons:
                reasons.append("criteria_without_evidence")
            continue
        ev = evidence_mod.read(conn, mapping[i], obj.project_id)
        if (ev.exit_code != 0 or ev.timed_out) and "criterion_evidence_failed" not in reasons:
            reasons.append("criterion_evidence_failed")
        criteria.append({"index": i, "criterion": text, "evidence_id": ev.id, "exit_code": ev.exit_code})
    with write_tx(conn):
        if reasons:
            audit.append_event(conn, "boss.delivery_denied", actor,
                               {"objective_id": obj.id, "reasons": reasons}, obj.project_id)
            denied = PolicyDenied(f"objective cannot be delivered: {', '.join(reasons)}", reasons=reasons)
        else:
            denied = None
            rows = []
            for t, dept, _ in items:
                acc = _accepted(conn, t.id)
                rows.append({"task_id": t.id, "title": t.title, "state": t.state.value, "department": dept,
                             "evaluation_id": acc["evaluation_id"] if acc else None,
                             "evidence_id": acc["evidence_id"] if acc else None,
                             "accepted_at": acc["accepted_at"] if acc else None})
            ts = now_iso()
            report = {"tasks": rows, "criteria": criteria, "departments": departments(conn, obj.id),
                      "delivered_at": ts}
            conn.execute("UPDATE objectives SET state='delivered', report=?, delivered_at=?, updated_at=? WHERE id=?",
                         (json.dumps(report), ts, ts, obj.id))
            audit.append_event(conn, "boss.delivered", actor,
                               {"objective_id": obj.id, "tasks": len(rows), "criteria": len(criteria)},
                               obj.project_id)
            dissolve_departments(conn, obj.id, actor)
    if denied:
        raise denied
    from agentos import improve

    retro = improve.retro(conn, obj.project_id, actor, objective_id=obj.id)
    return {"objective": get_objective(conn, obj.id).model_dump(), **report, "retrospective": _retro_brief(retro)}


def delivery_report(conn: sqlite3.Connection, objective_id: str) -> dict | None:
    row = conn.execute("SELECT report FROM objectives WHERE id=?", (objective_id,)).fetchone()
    if not row:
        raise NotFound(f"objective not found: {objective_id}")
    return json.loads(row[0]) if row[0] else None
