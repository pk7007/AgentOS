"""Workforce management over the ledger.

Review templates on their evaluations and suspend poor performers, rehabilitate a template on
probation with a new version, plan successors, split heavy tasks across several workers, contract
idle capacity, terminate workers safely and hand unfinished work to a replacement. AgentOS cannot
stop a host's native worker: it records the intent, refuses that worker's further admission and
tells the host what to stop. Nothing here retires a template or lifts a hard limit; those stay
with the owner."""

import json
import sqlite3
import statistics

from agentos import audit, factory, governor, lifecycle, memory, performance, recruit, tasks, templates
from agentos.db import write_tx
from agentos.errors import PolicyDenied, UsageError
from agentos.lifecycle import ACTIVE_STATES, AgentState
from agentos.tasks import TaskState
from agentos.templates import AgentTemplate, TemplateStatus
from agentos.util import new_id, now_iso

SUSPEND_CONSECUTIVE = 3     # this many failing evaluations in a row suspends a template
PROBATION_EVALS = 3         # evaluations of a new version before rehabilitation is judged
REHAB_PASS = 70.0
REHAB_FAIL = 50.0
MAX_PARTS = 8
OPEN_TASK = (TaskState.pending, TaskState.running)


def _suspend(conn, template_id: str, actor: str, reason: str) -> None:
    templates.set_status(conn, template_id, TemplateStatus.suspended, actor, reason)


def _active_on(conn, template_id: str) -> list[str]:
    marks = ",".join("?" * len(ACTIVE_STATES))
    return [r[0] for r in conn.execute(
        f"SELECT id FROM agent_instances WHERE template_id=? AND state IN ({marks}) ORDER BY created_at",
        [template_id, *[s.value for s in ACTIVE_STATES]])]


# --- performance review, suspension and rehabilitation -------------------------------------------

def _open_rehab(conn, template_id: str):
    return conn.execute("SELECT * FROM rehabilitations WHERE template_id=? AND status='probation'",
                        (template_id,)).fetchone()


def review(conn: sqlite3.Connection, actor: str) -> list[dict]:
    """Act on every active template's record. Suspends on a retire-review recommendation or a run of
    failing evaluations; recommends rehabilitation for weak ones; judges templates on probation."""
    actions = []
    for t in templates.list_templates(conn, TemplateStatus.active):
        if _open_rehab(conn, t.id):
            actions.append(probation(conn, t.id, actor))
            continue
        s = performance.summary(conn, t.id)
        workers = _active_on(conn, t.id)
        if s.recommendation == "retire_review":
            _suspend(conn, t.id, actor, "performance review: retire review")
            actions.append({"template_id": t.id, "action": "suspended", "reason": "retire_review",
                            "active_workers": workers,
                            "next": f"the owner decides on retirement: agentos template retire {t.id} --reason ..."})
        elif s.n >= SUSPEND_CONSECUTIVE and s.consecutive_failures >= SUSPEND_CONSECUTIVE:
            _suspend(conn, t.id, actor, f"performance review: {s.consecutive_failures} failing evaluations in a row")
            actions.append({"template_id": t.id, "action": "suspended", "reason": "consecutive_failures",
                            "active_workers": workers,
                            "next": "rehabilitate it with a new version, and transfer its active workers' tasks"})
        elif s.recommendation == "retrain":
            actions.append({"template_id": t.id, "action": "rehabilitate",
                            "reason": f"band {s.band}, mean {s.mean:.1f} over {s.n} evaluations"})
    if actions:
        with write_tx(conn):
            audit.append_event(conn, "workforce.reviewed", actor,
                               {"actions": [{k: a[k] for k in ("template_id", "action")} for a in actions]})
    return actions


def start_rehab(conn: sqlite3.Connection, template_id: str, changes: dict, actor: str) -> dict:
    """Register an improved version of an underperforming template and put it on probation. The new
    version may not widen the template's permissions; that is the owner's call (`template add`)."""
    t = templates.get_template(conn, template_id)
    if t.status in (TemplateStatus.quarantined, TemplateStatus.retired):
        raise PolicyDenied(f"a {t.status.value} template comes back only through the owner",
                           reasons=["owner_required"])
    if _open_rehab(conn, template_id):
        raise PolicyDenied("this template is already on probation", reasons=["already_in_rehabilitation"])
    s = performance.summary(conn, template_id)
    weak = s.recommendation in ("retrain", "retire_review") or s.band in ("improve", "suspend_review")
    if t.status == TemplateStatus.active and not weak:
        raise PolicyDenied(f"template is performing ({s.band}); nothing to rehabilitate",
                           reasons=["not_underperforming"])
    unknown = set(changes) - (factory.OVERRIDABLE - {"id"})
    if unknown:
        raise UsageError(f"these fields cannot change in a rehabilitation: {', '.join(sorted(unknown))}")
    body = t.model_dump(exclude={"version", "status"}) | changes
    body["instructions"] = factory.with_safety(str(body.get("instructions") or ""))
    new = AgentTemplate(**body)
    if new.model_dump(exclude={"version", "status"}) == t.model_dump(exclude={"version", "status"}):
        raise UsageError("the new version changes nothing")
    problems = factory.config_problems(new)
    wider = factory.widening(new, t)
    if t.security_class == "elevated" and "elevated_security" in wider:
        wider.remove("elevated_security")
    if t.can_delegate and "delegation" in wider:
        wider.remove("delegation")
    if not t.read_only and "write_access" in wider:
        wider.remove("write_access")
    if problems or wider:
        raise PolicyDenied(f"rehabilitation refused: {', '.join(problems + wider)}", reasons=problems + wider)
    with write_tx(conn):
        added = templates.add_template(conn, new, actor)
        if t.status == TemplateStatus.suspended:
            templates.set_status(conn, template_id, TemplateStatus.active, actor, "rehabilitation: on probation")
        rid = new_id("rhb")
        conn.execute("INSERT INTO rehabilitations(id, template_id, from_version, to_version, baseline_mean, status,"
                     " started_at) VALUES (?,?,?,?,?,'probation',?)",
                     (rid, template_id, t.version, added.version, s.mean, now_iso()))
        audit.append_event(conn, "workforce.rehab_started", actor,
                           {"rehabilitation_id": rid, "template_id": template_id, "from_version": t.version,
                            "to_version": added.version, "baseline_mean": s.mean})
    return {"rehabilitation_id": rid, "template_id": template_id, "from_version": t.version,
            "to_version": added.version, "baseline_mean": s.mean, "status": "probation",
            "rule": f"after {PROBATION_EVALS} evaluations of the new version: mean >= {REHAB_PASS:g} passes, "
                    f"< {REHAB_FAIL:g} fails and suspends; otherwise probation continues to "
                    f"{2 * PROBATION_EVALS} evaluations"}


def probation(conn: sqlite3.Connection, template_id: str, actor: str) -> dict:
    r = _open_rehab(conn, template_id)
    if not r:
        raise PolicyDenied("this template is not on probation", reasons=["not_in_rehabilitation"])
    values = [row[0] for row in conn.execute(
        "SELECT e.weighted FROM evaluations e JOIN agent_instances i ON i.id=e.instance_id"
        " WHERE e.template_id=? AND i.template_version>=? AND e.external_cause=0", (template_id, r["to_version"]))]
    n, mean = len(values), (statistics.fmean(values) if values else None)
    status = "probation"
    if n >= PROBATION_EVALS and mean >= REHAB_PASS:
        status = "rehabilitated"
    elif (n >= PROBATION_EVALS and mean < REHAB_FAIL) or (n >= 2 * PROBATION_EVALS and mean < REHAB_PASS):
        status = "failed"
    if status != "probation":
        with write_tx(conn):
            conn.execute("UPDATE rehabilitations SET status=?, closed_at=? WHERE id=?", (status, now_iso(), r["id"]))
            if status == "failed" and templates.get_template(conn, template_id).status == TemplateStatus.active:
                _suspend(conn, template_id, actor, "rehabilitation failed")
            audit.append_event(conn, f"workforce.rehab_{status}", actor,
                               {"rehabilitation_id": r["id"], "template_id": template_id, "evaluations": n,
                                "mean": mean})
    return {"template_id": template_id, "rehabilitation_id": r["id"], "action": f"probation:{status}",
            "status": status, "evaluations": n, "mean": mean, "baseline_mean": r["baseline_mean"],
            "version": r["to_version"]}


# --- succession -----------------------------------------------------------------------------------

def succession(conn: sqlite3.Connection, project_id: str | None = None) -> list[dict]:
    """For every active template: who could take over its work, ranked on evaluated performance."""
    open_caps = []
    if project_id:
        for (caps,) in conn.execute("SELECT capabilities FROM tasks WHERE project_id=? AND state IN ('pending',"
                                    "'running')", (project_id,)):
            open_caps.append({c.strip().lower() for c in json.loads(caps) if c.strip()})
    active = templates.list_templates(conn, TemplateStatus.active)
    plans = []
    for t in active:
        successors = [c.template_id for c in recruit.rank(conn, t.capabilities)
                      if c.match == 1.0 and c.template_id != t.id][:3]
        mine = {c.lower() for c in t.capabilities}
        only_it = 0
        for need in open_caps:
            if need and need <= mine and not any(need <= {c.lower() for c in o.capabilities}
                                                 for o in active if o.id != t.id):
                only_it += 1
        plans.append({"template_id": t.id, "successors": successors,
                      "status": "covered" if successors else "single_point_of_failure",
                      "active_workers": len(_active_on(conn, t.id)), "open_tasks_only_it_covers": only_it})
    return plans


# --- workload-based multiplication ----------------------------------------------------------------

def _meta(conn, task_id: str):
    return conn.execute("SELECT objective_id, department, effort FROM tasks WHERE id=?", (task_id,)).fetchone()


def suggest_parts(conn: sqlite3.Connection, task_id: str) -> int:
    lim = governor.get_limits(conn)
    free = max(1, lim.max_concurrent - lifecycle.slot_count(conn))
    return max(1, min(_meta(conn, task_id)["effort"], MAX_PARTS, lim.max_agents_per_task, free))


def split(conn: sqlite3.Connection, task_id: str, actor: str, parts: int | None = None) -> dict:
    """Split a heavy task into parallel parts, one worker each. The parent then depends on every part,
    so it becomes the integration step. Each part is still admitted on its own."""
    task = tasks.get_task(conn, task_id)
    if task.state not in OPEN_TASK:
        raise PolicyDenied(f"task is {task.state.value}", reasons=["task_not_open"])
    if conn.execute("SELECT 1 FROM tasks WHERE parent_id=?", (task_id,)).fetchone():
        raise PolicyDenied("task is already split", reasons=["already_split"])
    meta = _meta(conn, task_id)
    effort = meta["effort"]
    cap = min(MAX_PARTS, governor.get_limits(conn).max_agents_per_task)
    parts = parts if parts is not None else suggest_parts(conn, task_id)
    if parts < 2:
        raise PolicyDenied(f"the workload (effort {effort}) does not need more than one worker",
                           reasons=["workload_too_small"])
    if parts > effort:
        raise PolicyDenied(f"{parts} parts for effort {effort}: more workers than work",
                           reasons=["parts_exceed_workload"])
    if parts > cap:
        raise PolicyDenied(f"at most {cap} parts", reasons=["parts_exceed_limit"])
    created = []
    with write_tx(conn):
        for i in range(1, parts + 1):
            child = tasks.add_task(conn, task.project_id, f"{task.title} (part {i}/{parts})", objective=task.objective,
                                   capabilities=task.capabilities, acceptance=task.acceptance, parent_id=task.id,
                                   priority=task.priority, risk=task.risk, actor=actor)
            conn.execute("UPDATE tasks SET objective_id=?, department=?, effort=1 WHERE id=?",
                         (meta["objective_id"], meta["department"], child.id))
            tasks.add_dependency(conn, task.id, child.id, actor)
            created.append(child.id)
        audit.append_event(conn, "workforce.split", actor, {"task_id": task.id, "parts": created, "effort": effort},
                           task.project_id)
    return {"task_id": task.id, "parts": created,
            "note": "admit one worker per part; the parent integrates them once every part is done"}


# --- contraction ----------------------------------------------------------------------------------

def contract(conn: sqlite3.Connection, project_id: str, actor: str) -> dict:
    """Shrink the workforce to the work left: archive finished workers of closed tasks, expire temporary
    specialists, dissolve departments with nothing open. Running or idle workers are reported, not
    stopped: stopping one is a decision (`workforce terminate`)."""
    from agentos import boss

    archived = []
    for r in conn.execute("SELECT i.id FROM agent_instances i JOIN tasks t ON t.id=i.task_id WHERE i.project_id=?"
                          " AND i.state='COMPLETED' AND t.state IN ('done','cancelled')", (project_id,)).fetchall():
        lifecycle.transition(conn, r[0], AgentState.ARCHIVED, actor, reason="contraction: task closed")
        archived.append(r[0])
    expired = factory.expire(conn, actor, project_id=project_id)
    dissolved = []
    for (oid,) in conn.execute("SELECT id FROM objectives WHERE project_id=?", (project_id,)).fetchall():
        dissolved += [{"objective_id": oid, "department": d} for d in boss.dissolve_departments(conn, oid, actor)]
    stale = [f for (oid,) in conn.execute("SELECT id FROM objectives WHERE project_id=? AND state='open'",
                                          (project_id,)).fetchall()
             for f in boss.bottlenecks(conn, oid) if f["kind"] in ("stale_worker", "orphan_worker")]
    return {"archived_workers": archived, "expired_specialists": expired, "dissolved_departments": dissolved,
            "workers_to_check": stale}


# --- termination, replacement and transfer ---------------------------------------------------------

def _evals_of(conn, instance_id: str) -> tuple[list[str], list[str]]:
    ev_ids, evd = [], []
    for row in conn.execute("SELECT id, evidence FROM evaluations WHERE instance_id=? ORDER BY created_at, rowid",
                            (instance_id,)):
        ev_ids.append(row[0])
        evd += [e for e in json.loads(row[1]) if e not in evd]
    return ev_ids, evd


def _keep(conn, inst, note: str | None, actor: str) -> str | None:
    if not note:
        return None
    layer = memory.Layer.failure if inst.state == AgentState.FAILED else memory.Layer.episodic
    return memory.add(conn, inst.project_id, layer, note, source=f"agent {inst.id} ({inst.template_id})",
                      author=actor).id


def terminate(conn: sqlite3.Connection, instance_id: str, reason: str, actor: str, note: str | None = None) -> dict:
    """Stop a worker the safe way. An active worker is CANCELLED and keeps its slot until the host confirms
    the native stop; a finished or idle one is TERMINATED. Its evaluations, evidence and audit history
    stay; `note` is saved to project memory."""
    from agentos.runtime import binding

    inst = lifecycle.get_instance(conn, instance_id)
    if inst.state in (AgentState.TERMINATED, AgentState.ARCHIVED, AgentState.CANCELLED):
        raise PolicyDenied(f"agent is already {inst.display_state()}", reasons=["already_stopping"])
    if inst.state not in ACTIVE_STATES and not lifecycle.can_transition(inst.state, AgentState.TERMINATED):
        raise PolicyDenied(f"agent in {inst.state.value} cannot be terminated", reasons=["illegal_transition"])
    with write_tx(conn):
        memory_id = _keep(conn, inst, note, actor)
        if inst.state in ACTIVE_STATES:
            after = lifecycle.transition(conn, instance_id, AgentState.CANCELLED, actor, reason=reason)
            step = (f"stop it in the runtime, then run: agentos agent confirm-stop {instance_id}"
                    " (with the runtime hooks on, its stop is confirmed for you)")
        else:
            b = binding(conn, instance_id)
            confirmed = inst.state == AgentState.COMPLETED or bool(b and b["stopped_at"])
            after = lifecycle.transition(conn, instance_id, AgentState.TERMINATED, actor, reason=reason,
                                         runtime_confirmed=confirmed)
            step = None if confirmed else f"confirm the runtime stopped it: agentos agent confirm-stop {instance_id}"
        ev_ids, evd = _evals_of(conn, instance_id)
        audit.append_event(conn, "workforce.terminated", actor,
                           {"instance_id": instance_id, "reason": reason, "memory_id": memory_id,
                            "evaluations": ev_ids, "knowledge_kept": memory_id is not None}, inst.project_id)
    task = tasks.get_task(conn, inst.task_id)
    return {"instance_id": instance_id, "state": after.display_state(), "memory_id": memory_id,
            "evaluations": ev_ids, "evidence": evd, "task_id": task.id, "task_open": task.state in OPEN_TASK,
            "next": step, "knowledge_kept": memory_id is not None,
            "warnings": [] if memory_id else [("no_handover_note: what this worker learned was not saved; "
                                               "pass --note next time")]}


def transfer(conn: sqlite3.Connection, instance_id: str, host: str, actor: str, to_template: str | None = None,
             reason: str = "transfer", note: str | None = None) -> dict:
    """Hand a worker's unfinished task to a replacement. Without `to_template` the best-ranked other
    template that covers the task is chosen (performance-based). The replacement is checked first; only
    if it could be admitted is the old worker stopped and the new one admitted."""
    from agentos.admission import AdmitRequest, admit, standing_reasons

    inst = lifecycle.get_instance(conn, instance_id)
    task = tasks.get_task(conn, inst.task_id)
    if task.state not in OPEN_TASK:
        raise PolicyDenied(f"task is {task.state.value}; nothing to transfer", reasons=["task_not_open"])
    caps = factory.norm_caps(task.capabilities)
    if to_template is None:
        high = task.risk in ("high", "critical")
        options = [t for t in (factory.covering(conn, caps, high_risk=high) or factory.covering(conn, caps))
                   if t != inst.template_id] if caps else []
        if not options:
            raise PolicyDenied("no other active template covers this task; staff one with "
                               f"`agentos factory recruit --task {task.id} --host {host}`",
                               reasons=["no_replacement"])
        to_template = options[0]
    reasons = list(standing_reasons(conn, task.project_id, task.id, to_template)[0])
    if reasons:
        with write_tx(conn):
            audit.append_event(conn, "workforce.transfer_denied", actor,
                               {"instance_id": instance_id, "to_template": to_template, "reasons": reasons},
                               task.project_id)
        return {"status": "denied", "from_instance": instance_id, "template_id": to_template, "instance_id": None,
                "reasons": reasons}
    stopped = None
    if inst.state not in (AgentState.TERMINATED, AgentState.ARCHIVED, AgentState.CANCELLED):
        stopped = terminate(conn, instance_id, f"replaced: {reason}", actor, note)
        memory_id = stopped["memory_id"]
    else:
        with write_tx(conn):
            memory_id = _keep(conn, inst, note, actor)
    parent = inst.parent_id
    if parent and lifecycle.get_instance(conn, parent).state not in ACTIVE_STATES:
        parent = None
    decision = admit(conn, AdmitRequest(project_id=task.project_id, task_id=task.id, template_id=to_template,
                                        parent_instance_id=parent, host=host), actor)
    ev_ids, evd = _evals_of(conn, instance_id)
    tid = new_id("trf")
    with write_tx(conn):
        conn.execute("INSERT INTO transfers(id, project_id, task_id, from_instance, to_instance, to_template, memory_id,"
                     " created_at, actor) VALUES (?,?,?,?,?,?,?,?,?)",
                     (tid, task.project_id, task.id, instance_id, decision.instance_id, to_template, memory_id,
                      now_iso(), actor))
        audit.append_event(conn, "workforce.transferred", actor,
                           {"transfer_id": tid, "task_id": task.id, "from_instance": instance_id,
                            "to_instance": decision.instance_id, "to_template": to_template,
                            "allowed": decision.allowed, "reasons": decision.reasons}, task.project_id)
    briefing = {"task": {"id": task.id, "title": task.title, "objective": task.objective,
                         "acceptance": task.acceptance},
                "previous": {"instance_id": inst.id, "template_id": inst.template_id,
                             "last_reason": inst.last_reason, "evaluations": ev_ids, "evidence": evd},
                "memory_id": memory_id}
    return {"status": "admitted" if decision.allowed else "denied", "transfer_id": tid,
            "from_instance": instance_id, "stopped": stopped, "template_id": to_template,
            "instance_id": decision.instance_id, "reasons": decision.reasons, "briefing": briefing}


def transfers(conn: sqlite3.Connection, project_id: str) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM transfers WHERE project_id=? ORDER BY created_at, rowid",
                                          (project_id,))]
