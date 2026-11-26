"""Worker admission: the yes/no a host must get before spawning a native subagent.

`standing_reasons` is shared with lifecycle re-entry (FAILED/AVAILABLE -> ASSIGNED), so an agent can
never become active again without passing the same checks a new one would.
"""

import json
import sqlite3

from pydantic import BaseModel

from agentos import audit, governance, governor
from agentos.db import write_tx
from agentos.errors import NotFound, PolicyDenied
from agentos.lifecycle import ACTIVE_STATES, AgentState, get_instance, slot_count
from agentos.templates import TemplateStatus, get_template
from agentos.util import new_id, now_iso

HIGH_RISK_ACTION = "admit_high_risk"


class AdmitRequest(BaseModel):
    project_id: str
    task_id: str
    template_id: str
    parent_instance_id: str | None = None
    host: str


class AdmitDecision(BaseModel):
    allowed: bool
    reasons: list[str]
    instance_id: str | None = None
    depth: int | None = None


def chain_for(project_id: str, task_id: str) -> list[tuple[str, str]]:
    return [("global", "*"), ("project", project_id), ("task", task_id)]


def _risk(conn, risk: str, task_id: str, template_id: str):
    """High-risk work needs a template with a track record or a granted owner approval; critical work
    always needs the approval. Returns (reasons, approval-to-consume)."""
    if risk not in ("high", "critical"):
        return [], None
    from agentos import performance, recruit

    approval = governance.check(conn, HIGH_RISK_ACTION, {"task_id": task_id, "template_id": template_id})
    if approval:
        return [], approval
    if risk == "critical":
        return ["owner_approval_required"], None
    s = performance.summary(conn, template_id)
    if s.n >= recruit.HIGH_RISK_MIN_EVALS and (s.mean or 0) >= recruit.HIGH_RISK_MIN_MEAN:
        return [], None
    return ["high_risk_unproven"], None


def standing_reasons(conn: sqlite3.Connection, project_id: str, task_id: str, template_id: str):
    """Every reason a worker for (task, template) may not be active right now. Returns (reasons, template,
    approval). Must run inside the caller's write transaction."""
    reasons: list[str] = []
    if governance.is_stopped(conn):
        reasons.append("emergency_stop")
    proj = conn.execute("SELECT active FROM projects WHERE id=?", (project_id,)).fetchone()
    if not proj or not proj[0]:
        reasons.append("project_inactive")
    task = conn.execute("SELECT project_id, state, capabilities, risk FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task or task["project_id"] != project_id:
        reasons.append("task_not_found")
        task = None
    elif task["state"] not in ("pending", "running"):
        reasons.append("task_not_open")
    if task is not None:
        open_deps = conn.execute(
            "SELECT count(*) FROM task_deps d JOIN tasks o ON o.id=d.depends_on WHERE d.task_id=? AND o.state!='done'",
            (task_id,)).fetchone()[0]
        if open_deps:
            reasons.append("dependencies_incomplete")
    try:
        tpl = get_template(conn, template_id)
        if tpl.status != TemplateStatus.active:
            reasons.append("template_unavailable")
    except NotFound:
        tpl = None
        reasons.append("template_unavailable")
    approval = None
    if task is not None and tpl is not None:
        need = {c.strip().lower() for c in json.loads(task["capabilities"]) if c.strip()}
        if need - {c.lower() for c in tpl.capabilities}:
            reasons.append("capability_mismatch")
        risk_reasons, approval = _risk(conn, task["risk"], task_id, template_id)
        reasons.extend(risk_reasons)
    if slot_count(conn) >= governor.get_limits(conn).max_concurrent:
        reasons.append("max_concurrent")
    reasons.extend(governor.exhausted(conn, chain_for(project_id, task_id)))
    return reasons, tpl, approval


def admit(conn: sqlite3.Connection, req: AdmitRequest, actor: str) -> AdmitDecision:
    with write_tx(conn):
        limits = governor.get_limits(conn)
        reasons, tpl, approval = standing_reasons(conn, req.project_id, req.task_id, req.template_id)
        depth = 0
        if req.parent_instance_id:
            try:
                parent = get_instance(conn, req.parent_instance_id)
                if parent.project_id != req.project_id:
                    reasons.append("parent_cross_project")
                if parent.state not in ACTIVE_STATES:
                    reasons.append("parent_not_active")
                if not get_template(conn, parent.template_id, parent.template_version).can_delegate:
                    reasons.append("parent_cannot_delegate")
                depth = parent.depth + 1
            except NotFound:
                reasons.append("parent_not_active")
            if depth > limits.max_depth:
                reasons.append("max_depth")
        created = conn.execute("SELECT count(*) FROM agent_instances WHERE task_id=?", (req.task_id,)).fetchone()[0]
        if created >= limits.max_agents_per_task:
            reasons.append("max_agents_per_task")
        marks = ",".join("?" * len(ACTIVE_STATES))
        dup = conn.execute(
            f"SELECT 1 FROM agent_instances WHERE task_id=? AND template_id=? AND state IN ({marks})",
            [req.task_id, req.template_id, *[s.value for s in ACTIVE_STATES]]).fetchone()
        if dup:
            reasons.append("duplicate")

        iid = new_id("ag")
        if not reasons:
            try:
                governor.reserve(conn, chain_for(req.project_id, req.task_id), "agent_runs", 1, holder=iid)
            except PolicyDenied as exc:
                reasons.extend(exc.reasons)

        payload = req.model_dump() | {"reasons": reasons, "depth": depth}
        if reasons:
            audit.append_event(conn, "agent.admission_denied", actor, payload, req.project_id)
            return AdmitDecision(allowed=False, reasons=reasons)
        if approval:
            governance.consume(conn, approval.id, actor)
        ts = now_iso()
        conn.execute(
            "INSERT INTO agent_instances(id, template_id, template_version, project_id, task_id, parent_id, depth,"
            " host, state, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (iid, tpl.id, tpl.version, req.project_id, req.task_id, req.parent_instance_id, depth, req.host,
             AgentState.ASSIGNED.value, ts, ts))
        audit.append_event(conn, "agent.admitted", actor,
                           payload | {"instance_id": iid, "approval_id": approval.id if approval else None,
                                      "note": "admission moves an active template "
                                      "straight to ASSIGNED (PROPOSED..AVAILABLE compressed)"}, req.project_id)
        return AdmitDecision(allowed=True, reasons=[], instance_id=iid, depth=depth)
