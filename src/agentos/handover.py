"""Sanitized handovers so another session or host can continue the work. Raw transcripts are never stored."""

import json
import re
import sqlite3
import subprocess
from pathlib import Path

from pydantic import BaseModel

from agentos import audit, governance, governor, lifecycle, memory, paths, tasks
from agentos.db import write_tx
from agentos.errors import IntegrityError, NotFound, PolicyDenied, UsageError
from agentos.memory import Layer
from agentos.projects import project_id_for, repo_root, require_active
from agentos.redact import redact_obj
from agentos.util import new_id, now_iso

HANDOVER_ID_RE = re.compile(r"^ho_[0-9a-f]{12}$")


class Handover(BaseModel):
    id: str
    schema_version: int = 1
    project_id: str
    host: str
    created_at: str
    objective: str
    next_action: str
    tasks: list[dict]
    active_instances: list[dict]
    pending_approvals: list[dict]
    decisions: list[dict]
    git: dict
    limits: dict
    budgets: list[dict]
    usage_note: str = "estimates only"


class ResumeReport(BaseModel):
    ok: bool
    warnings: list[str]
    handover: Handover


def _git(repo: Path, *args) -> tuple[int, str]:
    try:
        out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60, check=False)
        return out.returncode, out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def git_state(repo: Path) -> dict:
    code, head = _git(repo, "rev-parse", "--verify", "-q", "HEAD")
    _, branch = _git(repo, "symbolic-ref", "--short", "-q", "HEAD")
    _, status = _git(repo, "status", "--porcelain")
    dirty = [line[3:] for line in status.splitlines() if line.strip()]
    return {"branch": branch or None, "head": head if code == 0 and head else None, "dirty_files": dirty}


def _file(handover_id: str) -> Path:
    if not HANDOVER_ID_RE.match(handover_id or ""):
        raise UsageError(f"not a handover id: {handover_id!r}")
    base = paths.handovers_dir().resolve()
    path = (base / f"{handover_id}.json").resolve()
    if path.parent != base:
        raise IntegrityError("handover path escapes the handovers directory")
    return path


def create(conn: sqlite3.Connection, project_id: str, repo_path: Path, host: str, objective: str,
           next_action: str, actor: str) -> Handover:
    require_active(conn, project_id)
    if project_id_for(repo_path) != project_id:
        raise PolicyDenied("repo path is not this project's repository", reasons=["project_mismatch"])
    hid = new_id("ho")
    h = Handover(
        id=hid, project_id=project_id, host=host, created_at=now_iso(), objective=objective,
        next_action=next_action,
        tasks=[{"id": t.id, "title": t.title, "state": t.state.value, "deps": t.deps}
               for t in tasks.list_tasks(conn, project_id)],
        active_instances=[{"id": i.id, "template": i.template_id, "task": i.task_id, "state": i.state.value,
                           "host": i.host} for i in lifecycle.list_instances(conn, project_id, active_only=True)],
        pending_approvals=[{"id": a.id, "action": a.action, "params": a.params}
                           for a in governance.list_approvals(conn, "pending")],
        decisions=[{"id": m.id, "layer": m.layer.value, "content": m.content[:500], "validated": m.validated}
                   for m in memory.recent(conn, project_id, [Layer.project, Layer.governance], 10)],
        git=git_state(repo_root(repo_path)),
        limits=governor.get_limits(conn).model_dump(),
        budgets=governor.budget_report(conn),
    )
    data = redact_obj(h.model_dump())
    path = _file(hid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    with write_tx(conn):
        conn.execute("INSERT INTO handovers(id, project_id, host, created_at, path) VALUES (?,?,?,?,?)",
                     (hid, project_id, host, h.created_at, str(path)))
        audit.append_event(conn, "handover.created", actor, {"handover_id": hid, "host": host}, project_id)
    return Handover(**data)


def resume(conn: sqlite3.Connection, handover_id: str, repo_path: Path, host: str, actor: str) -> ResumeReport:
    path = _file(handover_id)
    row = conn.execute("SELECT * FROM handovers WHERE id=?", (handover_id,)).fetchone()
    if not row or not path.exists():
        raise NotFound(f"handover not found: {handover_id}")
    h = Handover(**json.loads(path.read_text(encoding="utf-8")))
    if h.id != handover_id or h.project_id != row["project_id"]:
        raise IntegrityError("handover file does not match its record")
    if project_id_for(repo_path) != h.project_id:
        raise PolicyDenied("this repository is not the handover's project", reasons=["project_mismatch"])
    with write_tx(conn):
        claimed = conn.execute("UPDATE handovers SET resumed_by=?, resumed_at=? WHERE id=? AND resumed_by IS NULL",
                               (host, now_iso(), handover_id)).rowcount
        if not claimed:
            raise PolicyDenied(f"handover was already resumed by {row['resumed_by']}", reasons=["already_resumed"])
        warnings: list[str] = []
        now = git_state(repo_root(repo_path))
        old_head = h.git.get("head")
        if old_head and now["head"] != old_head:
            code, _ = _git(repo_root(repo_path), "merge-base", "--is-ancestor", old_head, now["head"] or "HEAD")
            warnings.append("head_advanced" if code == 0 else "head_diverged")
        if now["dirty_files"]:
            warnings.append("dirty_tree")
        still_active = [i["id"] for i in h.active_instances
                        if lifecycle.get_instance(conn, i["id"]).state in lifecycle.ACTIVE_STATES]
        if still_active:
            warnings.append("orphaned_instances:" + ",".join(still_active))
        audit.append_event(conn, "handover.resumed", actor, {"handover_id": handover_id, "host": host,
                                                             "warnings": warnings}, h.project_id)
    return ResumeReport(ok=True, warnings=warnings, handover=h)


def list_handovers(conn: sqlite3.Connection, project_id: str | None = None) -> list[dict]:
    sql, params = "SELECT id, project_id, host, created_at, resumed_by, resumed_at FROM handovers", []
    if project_id:
        sql += " WHERE project_id=?"
        params.append(project_id)
    return [dict(r) for r in conn.execute(sql + " ORDER BY created_at DESC", params)]
