"""Worker admission: the yes/no a host must get before spawning a native subagent."""

import sqlite3

from pydantic import BaseModel

from agentos import audit, governance, governor
from agentos.db import write_tx
from agentos.errors import NotFound, PolicyDenied
from agentos.lifecycle import ACTIVE_STATES, AgentState, active_count, get_instance
from agentos.templates import TemplateStatus, get_template
from agentos.util import new_id, now_iso


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


def admit(conn: sqlite3.Connection, req: AdmitRequest, actor: str) -> AdmitDecision:
    with write_tx(conn):
        reasons: list[str] = []
        limits = governor.get_limits(conn)
        if governance.is_stopped(conn):
            reasons.append("emergency_stop")
        proj = conn.execute("SELECT active FROM projects WHERE id=?", (req.project_id,)).fetchone()
        if not proj or not proj[0]:
            reasons.append("project_inactive")
        task = conn.execute("SELECT project_id, state FROM tasks WHERE id=?", (req.task_id,)).fetchone()
        if not task or task["project_id"] != req.project_id:
            reasons.append("task_not_found")
        elif task["state"] not in ("pending", "running"):
            reasons.append("task_not_open")
        try:
            tpl = get_template(conn, req.template_id)
            if tpl.status != TemplateStatus.active:
                reasons.append("template_unavailable")
        except NotFound:
            tpl = None
            reasons.append("template_unavailable")
        depth = 0
        if req.parent_instance_id:
            try:
                parent = get_instance(conn, req.parent_instance_id)
                if parent.state not in ACTIVE_STATES:
                    reasons.append("parent_not_active")
                if not get_template(conn, parent.template_id, parent.template_version).can_delegate:
                    reasons.append("parent_cannot_delegate")
                depth = parent.depth + 1
            except NotFound:
                reasons.append("parent_not_active")
            if depth > limits.max_depth:
                reasons.append("max_depth")
        if active_count(conn) >= limits.max_concurrent:
            reasons.append("max_concurrent")
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
                governor.reserve(conn, [("global", "*"), ("project", req.project_id), ("task", req.task_id)],
                                 "agent_runs", 1, holder=iid)
            except PolicyDenied as exc:
                reasons.extend(exc.reasons)

        payload = req.model_dump() | {"reasons": reasons, "depth": depth}
        if reasons:
            audit.append_event(conn, "agent.admission_denied", actor, payload, req.project_id)
            return AdmitDecision(allowed=False, reasons=reasons)
        ts = now_iso()
        conn.execute(
            "INSERT INTO agent_instances(id, template_id, template_version, project_id, task_id, parent_id, depth,"
            " host, state, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (iid, tpl.id, tpl.version, req.project_id, req.task_id, req.parent_instance_id, depth, req.host,
             AgentState.ASSIGNED.value, ts, ts))
        audit.append_event(conn, "agent.admitted", actor,
                           payload | {"instance_id": iid, "note": "admission moves an active template "
                                      "straight to ASSIGNED (PROPOSED..AVAILABLE compressed)"}, req.project_id)
        return AdmitDecision(allowed=True, reasons=[], instance_id=iid, depth=depth)
