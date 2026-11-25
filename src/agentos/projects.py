"""Projects: a git repository AgentOS has been explicitly activated for."""

import hashlib
import os
import sqlite3
import subprocess
from pathlib import Path

from pydantic import BaseModel

from agentos import audit
from agentos.db import write_tx
from agentos.errors import NotFound, PolicyDenied
from agentos.util import now_iso


class Project(BaseModel):
    id: str
    path: str
    name: str
    active: bool
    activated_at: str


def repo_root(path: Path) -> Path:
    path = Path(path)
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip()).resolve()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return path.resolve()


def _key(path: Path) -> str:
    return os.path.normcase(str(repo_root(path))).rstrip("\\/")


def project_id_for(path: Path) -> str:
    return "prj_" + hashlib.sha256(_key(path).encode("utf-8")).hexdigest()[:16]


def _row(row) -> Project:
    return Project(id=row["id"], path=row["path"], name=row["name"], active=bool(row["active"]),
                   activated_at=row["activated_at"])


def get_project(conn: sqlite3.Connection, project_id: str) -> Project:
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        raise NotFound(f"project not found: {project_id}")
    return _row(row)


def activate(conn: sqlite3.Connection, path: Path, actor: str) -> Project:
    root = repo_root(path)
    pid = project_id_for(path)
    with write_tx(conn):
        conn.execute(
            "INSERT INTO projects(id, path, name, active, activated_at) VALUES (?,?,?,1,?) "
            "ON CONFLICT(id) DO UPDATE SET active=1, path=excluded.path",
            (pid, str(root), root.name, now_iso()),
        )
        audit.append_event(conn, "project.activated", actor, {"path": str(root)}, project_id=pid)
    return get_project(conn, pid)


def deactivate(conn: sqlite3.Connection, project_id: str, actor: str) -> Project:
    get_project(conn, project_id)
    with write_tx(conn):
        conn.execute("UPDATE projects SET active=0 WHERE id=?", (project_id,))
        audit.append_event(conn, "project.deactivated", actor, {}, project_id=project_id)
    return get_project(conn, project_id)


def list_projects(conn: sqlite3.Connection) -> list[Project]:
    return [_row(r) for r in conn.execute("SELECT * FROM projects ORDER BY activated_at")]


def require_active(conn: sqlite3.Connection, project_id: str) -> Project:
    try:
        p = get_project(conn, project_id)
    except NotFound:
        raise PolicyDenied("project is not activated", reasons=["project_inactive"]) from None
    if not p.active:
        raise PolicyDenied("project is not activated", reasons=["project_inactive"])
    return p
