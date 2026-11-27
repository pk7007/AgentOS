"""Read-only views of what AgentOS knows: active workers and their hierarchy, task progress, recruitment and
termination history, performance, resource use, experiments, accepted and rejected changes, security
incidents and emergency controls. Every figure comes from a ledger row or an audit event; nothing is
inferred, and nothing here writes."""

import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime

from agentos import audit, comms, governance, governor, lifecycle, performance
from agentos.db import get_setting
from agentos.governance import PIN_KEY

SEVERITY = {
    "runtime.unadmitted_subagent": "high", "audit.chain_broken": "high", "eval.flagged": "high",
    "template.quarantined": "high", "governance.stop": "high", "comms.escalated": "high",
    "health.breaker_tripped": "medium", "comms.claim_denied": "low",
    "runtime.spawn_denied": "medium", "evidence.refused": "medium", "runtime.tool_denied": "medium", "budget.usage_denied": "medium",
    "factory.register_denied": "medium", "agent.transition_denied": "low", "agent.admission_denied": "low",
    "workforce.transfer_denied": "low", "boss.acceptance_denied": "low", "boss.delivery_denied": "low",
}
RECRUITMENT = ("agent.admitted", "agent.admission_denied", "factory.proposed", "factory.registered",
               "factory.rejected", "factory.expired", "workforce.transferred")
TERMINATION = ("workforce.terminated", "agent.stop_confirmed", "runtime.subagent_stopped")


def _events(conn, kinds, project_id: str | None, limit: int, include_global: bool = False) -> list[dict]:
    sql = f"SELECT seq, ts, kind, actor, project_id, payload FROM events WHERE kind IN ({','.join('?' * len(kinds))})"
    params: list = list(kinds)
    if project_id:
        sql += " AND (project_id=?" + (" OR project_id IS NULL)" if include_global else ")")
        params.append(project_id)
    rows = conn.execute(sql + " ORDER BY seq DESC LIMIT ?", [*params, limit]).fetchall()
    return [{"seq": r["seq"], "ts": r["ts"], "kind": r["kind"], "actor": r["actor"], "project_id": r["project_id"],
             **json.loads(r["payload"])} for r in rows]


def _minutes(since: str) -> int:
    return int((datetime.now(UTC) - datetime.fromisoformat(since)).total_seconds() // 60)


def _titles(conn, task_ids) -> dict[str, str]:
    ids = list(set(task_ids))
    if not ids:
        return {}
    return dict(conn.execute(f"SELECT id, title FROM tasks WHERE id IN ({','.join('?' * len(ids))})", ids))


# --- actual active agents and hierarchy ---

def active_agents(conn: sqlite3.Connection, project_id: str | None = None) -> list[dict]:
    """Every worker holding a concurrency slot: active, cancel pending, or terminated without the host's
    confirmation. `runtime` is what the host's hooks reported, when they did."""
    sql = f"SELECT * FROM agent_instances WHERE ({lifecycle._SLOT_SQL})"
    params: list = []
    if project_id:
        sql += " AND project_id=?"
        params.append(project_id)
    rows = [lifecycle._row(r) for r in conn.execute(sql + " ORDER BY created_at, rowid", params)]
    titles = _titles(conn, [r.task_id for r in rows])
    out = []
    for i in rows:
        b = conn.execute("SELECT * FROM runtime_bindings WHERE instance_id=?", (i.id,)).fetchone()
        state = i.display_state()
        if i.state == lifecycle.AgentState.TERMINATED and not i.termination_confirmed:
            state = "TERMINATED (unconfirmed)"
        elif i.state == lifecycle.AgentState.CANCELLED:
            state = "CANCELLED (stop pending)"
        out.append({"id": i.id, "template_id": i.template_id, "state": state, "host": i.host,
                    "task_id": i.task_id, "task": titles.get(i.task_id), "parent_id": i.parent_id,
                    "depth": i.depth, "age_minutes": _minutes(i.created_at),
                    "runtime": None if b is None else {"native_agent_id": b["native_agent_id"],
                                                       "started_at": b["started_at"],
                                                       "stopped_at": b["stopped_at"]}})
    return out


def hierarchy(conn: sqlite3.Connection, project_id: str, include_finished: bool = False) -> list[dict]:
    insts = lifecycle.list_instances(conn, project_id)
    if not include_finished:
        keep = {i.id for i in insts if i.state not in (lifecycle.AgentState.ARCHIVED,)}
        insts = [i for i in insts if i.id in keep]
    titles = _titles(conn, [i.task_id for i in insts])
    nodes = {i.id: {"id": i.id, "template_id": i.template_id, "state": i.display_state(), "task": titles.get(
        i.task_id), "children": []} for i in insts}
    roots = []
    for i in insts:
        parent = nodes.get(i.parent_id) if i.parent_id else None
        (parent["children"] if parent else roots).append(nodes[i.id])
    return roots


def render_tree(roots: list[dict]) -> str:
    lines: list[str] = []

    def walk(n, prefix, last):
        lines.append(f"{prefix}{'`-- ' if last else '|-- '}{n['template_id']} {n['id']} [{n['state']}] "
                     f"{n['task'] or ''}".rstrip())
        for k, c in enumerate(n["children"]):
            walk(c, prefix + ("    " if last else "|   "), k == len(n["children"]) - 1)

    for k, r in enumerate(roots):
        walk(r, "", k == len(roots) - 1)
    return "\n".join(lines) or "(no workers)"


# --- task progress ---

def progress(conn: sqlite3.Connection, project_id: str) -> dict:
    groups: dict[str | None, Counter] = {}
    for oid, state, n in conn.execute("SELECT objective_id, state, count(*) FROM tasks WHERE project_id=? "
                                      "GROUP BY objective_id, state", (project_id,)):
        groups.setdefault(oid, Counter())[state] += n
    accepted = Counter(oid for (oid,) in conn.execute(
        "SELECT t.objective_id FROM task_acceptances a JOIN tasks t ON t.id=a.task_id WHERE t.project_id=?",
        (project_id,)))
    titles = dict(conn.execute("SELECT id, title FROM objectives WHERE project_id=?", (project_id,)))
    states = dict(conn.execute("SELECT id, state FROM objectives WHERE project_id=?", (project_id,)))
    out = []
    for oid, c in sorted(groups.items(), key=lambda kv: (kv[0] is None, kv[0] or "")):
        counted = sum(c.values()) - c["cancelled"]
        out.append({"objective_id": oid, "title": titles.get(oid, "(no objective)"), "state": states.get(oid),
                    "tasks": dict(c), "accepted": accepted[oid],
                    "percent_done": round(100 * c["done"] / counted) if counted else None})
    blocked = [{"id": r[0], "title": r[1]} for r in conn.execute(
        "SELECT id, title FROM tasks WHERE project_id=? AND state='blocked' ORDER BY created_at", (project_id,))]
    return {"project_id": project_id, "objectives": out, "blocked": blocked}


# --- recruitment and termination history ---

def recruitment(conn: sqlite3.Connection, project_id: str, limit: int = 50) -> dict:
    ev = _events(conn, RECRUITMENT, project_id, limit)
    return {"events": ev, "counts": dict(Counter(e["kind"] for e in ev))}


def terminations(conn: sqlite3.Connection, project_id: str, limit: int = 50) -> dict:
    ev = _events(conn, TERMINATION, project_id, limit)
    unconfirmed = [{"id": r["id"], "template_id": r["template_id"], "state": r["state"], "since": r["updated_at"]}
                   for r in conn.execute(
        "SELECT id, template_id, state, updated_at FROM agent_instances WHERE project_id=? AND (state='CANCELLED' "
        "OR (state='TERMINATED' AND coalesce(termination_confirmed, 0)=0)) ORDER BY updated_at, rowid",
        (project_id,))]
    return {"events": ev, "unconfirmed_stops": unconfirmed}


# --- performance, resources, experiments, changes ---

def performance_records(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for (tid,) in conn.execute("SELECT DISTINCT template_id FROM evaluations ORDER BY template_id"):
        s = performance.summary(conn, tid)
        out.append({"template_id": tid, "evaluations": s.n, "mean": None if s.mean is None else round(s.mean, 1),
                    "recent_mean": None if s.recent_mean is None else round(s.recent_mean, 1), "band": s.band,
                    "recommendation": s.recommendation, "failure_rate": s.failure_rate,
                    "critical_scores": s.critical_count})
    return out


def resources(conn: sqlite3.Connection, project_id: str) -> dict:
    lim = governor.get_limits(conn)
    used = {}
    for scope, sid in (("global", "*"), ("project", project_id)):
        used[scope] = {k: governor._used(conn, scope, sid, k) for k in ("agent_runs", "tokens_est", "usd")}
    return {"slots_held": lifecycle.slot_count(conn), "max_concurrent": lim.max_concurrent,
            "workers_admitted": conn.execute("SELECT count(*) FROM agent_instances WHERE project_id=?",
                                             (project_id,)).fetchone()[0],
            "used": used, "budgets": governor.budget_report(conn), "paid_spend_cap_usd": lim.max_paid_spend_usd,
            "measurement": "agent runs and usd are counted; tokens are the host's or the worker's estimates"}


def experiments(conn: sqlite3.Connection, project_id: str) -> dict:
    rows = [dict(r) for r in conn.execute(
        "SELECT id, kind, target, status, hypothesis, created_at, decided_at FROM experiments WHERE project_id=? "
        "ORDER BY created_at DESC, rowid DESC", (project_id,))]
    return {"experiments": rows, "counts": dict(Counter(r["status"] for r in rows))}


def changes(conn: sqlite3.Connection, project_id: str) -> dict:
    """Changes to how the organisation works, split into accepted and rejected."""
    accepted, rejected = [], []
    for r in conn.execute("SELECT id, kind, target, status, decided_at FROM experiments WHERE project_id=? AND "
                          "status IN ('promoted', 'abandoned', 'rolled_back') ORDER BY rowid", (project_id,)):
        (accepted if r["status"] == "promoted" else rejected).append(
            {"what": f"experiment {r['kind']} on {r['target']}", "id": r["id"], "outcome": r["status"],
             "at": r["decided_at"]})
    for r in conn.execute("SELECT id, template_id, status, updated_at FROM factory_proposals WHERE project_id=? "
                          "AND status IN ('registered', 'rejected', 'expired') ORDER BY rowid", (project_id,)):
        (accepted if r["status"] == "registered" else rejected).append(
            {"what": f"new template {r['template_id']}", "id": r["id"], "outcome": r["status"],
             "at": r["updated_at"]})
    for r in conn.execute("SELECT id, template_id, status, closed_at FROM rehabilitations WHERE status<>'probation' "
                          "ORDER BY rowid"):
        (accepted if r["status"] == "rehabilitated" else rejected).append(
            {"what": f"rehabilitation of {r['template_id']}", "id": r["id"], "outcome": r["status"],
             "at": r["closed_at"]})
    for r in conn.execute("SELECT id, action, status, granted_at, created_at FROM approvals WHERE status IN "
                          "('granted', 'consumed', 'denied') ORDER BY rowid"):
        (rejected if r["status"] == "denied" else accepted).append(
            {"what": f"approval for {r['action']}", "id": r["id"], "outcome": r["status"],
             "at": r["granted_at"] or r["created_at"]})
    return {"accepted": accepted, "rejected": rejected}


# --- security incidents and emergency controls ---

def incidents(conn: sqlite3.Connection, project_id: str | None = None, limit: int = 100) -> dict:
    kinds = [k for k in SEVERITY if "." in k and k not in ("audit.chain_broken", "eval.flagged",
                                                            "template.quarantined")]
    out = []
    for e in _events(conn, kinds, project_id, limit, include_global=True):
        out.append({"severity": SEVERITY[e["kind"]], **e})
    for e in _events(conn, ["eval.recorded"], project_id, limit):
        if e.get("flags"):
            out.append({"severity": "high", **e, "kind": "eval.flagged"})
    for e in _events(conn, ["template.status"], None, limit):
        if e.get("to") == "quarantined":
            out.append({"severity": "high", **e, "kind": "template.quarantined"})
    v = audit.verify_chain(conn)
    if not v.ok:
        out.append({"severity": "high", "kind": "audit.chain_broken", "seq": v.first_bad_seq, "reason": v.reason})
    order = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda e: (order[e["severity"]], -(e.get("seq") or 0)))
    return {"incidents": out[:limit], "counts": dict(Counter(e["severity"] for e in out)),
            "audit_chain_ok": v.ok}


def controls(conn: sqlite3.Connection) -> dict:
    stopped = governance.is_stopped(conn)
    lim = governor.get_limits(conn)
    return {"emergency_stop": stopped, "owner_pin_set": get_setting(conn, PIN_KEY) is not None,
            "limits": lim.model_dump(),
            "pending_approvals": conn.execute("SELECT count(*) FROM approvals WHERE status='pending'").fetchone()[0],
            "commands": {"stop": "agentos stop --reason TEXT", "lift": "agentos stop --lift (owner)",
                         "cancel_worker": "agentos agent transition ID CANCELLED",
                         "terminate_worker": "agentos workforce terminate ID --reason TEXT",
                         "quarantine_template": "agentos template quarantine ID --reason TEXT"}}


def dashboard(conn: sqlite3.Connection, project_id: str) -> dict:
    act = active_agents(conn, project_id)
    prog = progress(conn, project_id)
    inc = incidents(conn, project_id)
    ch = changes(conn, project_id)
    res = resources(conn, project_id)
    return {"project_id": project_id, "controls": controls(conn),
            "active_agents": len(act), "active_by_state": dict(Counter(a["state"] for a in act)),
            "objectives": prog["objectives"], "blocked_tasks": len(prog["blocked"]),
            "incidents": inc["counts"], "audit_chain_ok": inc["audit_chain_ok"],
            "changes": {"accepted": len(ch["accepted"]), "rejected": len(ch["rejected"])},
            "experiments": experiments(conn, project_id)["counts"], "slots": f"{res['slots_held']}/"
            f"{res['max_concurrent']}", "used": res["used"]["project"],
            "open_escalations": len(comms.open_escalations(conn, project_id))}


def render_dashboard(d: dict) -> str:
    c = d["controls"]
    lines = [f"AgentOS: project {d['project_id']}",
             (f"  emergency stop: {'ON' if c['emergency_stop'] else 'off'}   owner pin: "
             f"{'set' if c['owner_pin_set'] else 'not set'}   pending approvals: {c['pending_approvals']}"),
             f"  audit chain: {'ok' if d['audit_chain_ok'] else 'BROKEN'}   slots: {d['slots']}   "
             f"active workers: {d['active_agents']} {d['active_by_state'] or ''}".rstrip(),
             (f"  incidents: {d['incidents'] or 'none'}   changes accepted/rejected: "
             f"{d['changes']['accepted']}/{d['changes']['rejected']}   experiments: {d['experiments'] or 'none'}"),
             f"  used in this project: {d['used']}", "  objectives:"]
    for o in d["objectives"] or [{"title": "(none)", "tasks": {}, "percent_done": None, "accepted": 0}]:
        pct = "-" if o["percent_done"] is None else f"{o['percent_done']}%"
        lines.append(f"    {o['title']}: {pct} done, {o['accepted']} accepted, {o['tasks']}")
    if d["blocked_tasks"]:
        lines.append(f"  blocked tasks: {d['blocked_tasks']}")
    if d.get("open_escalations"):
        lines.append(f"  ESCALATIONS waiting for the owner: {d['open_escalations']} (agentos msg inbox owner)")
    return "\n".join(lines)


# --- time series and spans ---

SERIES = {"admitted": ("agent.admitted",), "refused": ("agent.admission_denied",),
          "evaluations": ("eval.recorded",), "incidents": tuple(k for k, v in SEVERITY.items() if v == "high"),
          "usage": ("budget.usage",), "accepted": ("boss.task_accepted",)}


def timeline(conn: sqlite3.Connection, project_id: str, days: int = 14) -> dict:
    """Counts per UTC day for the last `days` days, one series per kind of activity. Days with nothing
    are present with 0, so the series can be plotted as they are."""
    if not 1 <= days <= 366:
        from agentos.errors import UsageError

        raise UsageError("days must be between 1 and 366")
    today = datetime.now(UTC).date()
    labels = [(today.fromordinal(today.toordinal() - i)).isoformat() for i in range(days - 1, -1, -1)]
    series = {}
    for name, kinds in SERIES.items():
        counts = Counter()
        marks = ",".join("?" * len(kinds))
        for (ts,) in conn.execute(f"SELECT ts FROM events WHERE kind IN ({marks}) AND project_id=? AND ts>=?",
                                  [*kinds, project_id, labels[0]]):
            counts[ts[:10]] += 1
        series[name] = [counts.get(d, 0) for d in labels]
    return {"project_id": project_id, "days": labels, "series": series, "bucket": "UTC day"}


def spans(conn: sqlite3.Connection, project_id: str) -> list[dict]:
    """One span per worker, from admission to the moment it left the active states (open spans have no
    end). Spans share a trace id, the id of the root worker of their delegation tree."""
    active = {s.value for s in lifecycle.ACTIVE_STATES}
    ends: dict[str, str] = {}
    for e in _events(conn, ["agent.transition"], project_id, 100000):
        if e.get("from") in active and e.get("to") not in active:
            ends.setdefault(e["instance_id"], e["ts"])  # newest first: keep the last exit
    rows = conn.execute("SELECT id, parent_id, template_id, task_id, state, created_at FROM agent_instances"
                        " WHERE project_id=? ORDER BY created_at", (project_id,)).fetchall()
    parent = {r["id"]: r["parent_id"] for r in rows}

    def root(i: str) -> str:
        seen = set()
        while parent.get(i) and i not in seen:
            seen.add(i)
            i = parent[i]
        return i

    out = []
    for r in rows:
        end = ends.get(r["id"])
        dur = (datetime.fromisoformat(end) - datetime.fromisoformat(r["created_at"])).total_seconds() if end else None
        out.append({"span_id": r["id"], "trace_id": root(r["id"]), "parent_span_id": r["parent_id"],
                    "name": f"{r['template_id']}:{r['task_id']}", "start": r["created_at"], "end": end,
                    "duration_s": None if dur is None else round(dur, 3), "state": r["state"]})
    return out
