"""init, doctor, status, backup, restore."""

import shutil
import sqlite3
import sys
from pathlib import Path

from agentos import db, paths
from agentos.errors import IntegrityError


def register(sub, common) -> None:
    p = sub.add_parser("init", parents=[common], help="create AgentOS state (safe to re-run)")
    p.set_defaults(func=cmd_init)
    p = sub.add_parser("doctor", parents=[common], help="check installation and capabilities")
    p.set_defaults(func=cmd_doctor)
    p = sub.add_parser("status", parents=[common], help="show counts and the emergency-stop flag")
    p.set_defaults(func=cmd_status)
    p = sub.add_parser("backup", parents=[common], help="write a consistent copy of the database")
    p.add_argument("--dest", type=Path, default=None)
    p.set_defaults(func=cmd_backup)
    p = sub.add_parser("restore", parents=[common], help="replace the database from a backup (owner only)")
    p.add_argument("file", type=Path)
    p.set_defaults(func=cmd_restore)


def cmd_init(args, ctx):
    for d in paths.all_dirs():
        d.mkdir(parents=True, exist_ok=True)
    conn = db.connect()
    try:
        version = db.migrate(conn)
        _after_init(conn, ctx)
    finally:
        conn.close()
    return {"home": str(paths.agentos_home()), "db": str(paths.db_path()), "schema_version": version}


def _after_init(conn, ctx) -> None:
    """Hook for later modules (audit event on init)."""


def _check(name, status, detail=""):
    return {"name": name, "status": status, "detail": detail}


def doctor_checks() -> tuple[list[dict], bool]:
    checks, integrity_ok = [], True
    ok_py = sys.version_info >= (3, 11)
    checks.append(_check("python", "VERIFIED" if ok_py else "UNSUPPORTED", sys.version.split()[0]))
    dbp = paths.db_path()
    if not dbp.exists():
        checks.append(_check("database", "UNKNOWN", "not initialized; run: agentos init"))
    else:
        conn = db.connect()
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            integrity_ok = result == "ok"
            checks.append(_check("database", "VERIFIED" if integrity_ok else "UNSUPPORTED", result))
            checks.append(_check("schema_version", "VERIFIED", str(db.current_version(conn))))
            checks.extend(_extra_checks(conn))
        finally:
            conn.close()
    try:
        probe = sqlite3.connect(":memory:")
        probe.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        probe.close()
        checks.append(_check("sqlite_fts5", "VERIFIED", sqlite3.sqlite_version))
    except sqlite3.Error as exc:
        checks.append(_check("sqlite_fts5", "UNSUPPORTED", str(exc)))
    codex = shutil.which("codex")
    checks.append(_check("codex_cli", "VERIFIED" if codex else "UNSUPPORTED", codex or "not on PATH"))
    return checks, integrity_ok


def _extra_checks(conn) -> list[dict]:
    """Hook for later modules (audit chain check)."""
    return []


def cmd_doctor(args, ctx):
    checks, integrity_ok = doctor_checks()
    result = {"home": str(paths.agentos_home()), "checks": checks}
    if not ctx.json:
        lines = [f"AgentOS home: {result['home']}"]
        lines += [f"  [{c['status']}] {c['name']}: {c['detail']}" for c in checks]
        result = "\n".join(lines)
    return result, (0 if integrity_ok else 5)


def cmd_status(args, ctx):
    conn = db.require_initialized()
    try:
        tasks = {r[0]: r[1] for r in conn.execute("SELECT state, count(*) FROM tasks GROUP BY state")}
        agents = {
            r[0]: r[1] for r in conn.execute("SELECT state, count(*) FROM agent_instances GROUP BY state")
        }
        projects = conn.execute("SELECT count(*) FROM projects WHERE active=1").fetchone()[0]
        stop = bool(db.get_setting(conn, "governance.emergency_stop", False))
    finally:
        conn.close()
    return {"emergency_stop": stop, "active_projects": projects, "tasks": tasks, "agents": agents}


def cmd_backup(args, ctx):
    conn = db.require_initialized()
    try:
        path = db.backup(conn, args.dest)
    finally:
        conn.close()
    return {"path": str(path)}


def owner_guard(action: str, ctx) -> object | None:
    """Replaced in the governance task with a real owner confirmation."""
    return None


def cmd_restore(args, ctx):
    db.require_initialized().close()
    db.validate_backup(args.file)
    owner_guard(f"restore {args.file.name}", ctx)
    safety = db.restore(args.file)
    conn = db.connect()
    try:
        if db.current_version(conn) < db.SCHEMA_VERSION:
            db.migrate(conn)
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise IntegrityError("restored database failed integrity check")
    finally:
        conn.close()
    return {"restored_from": str(args.file), "previous_saved_to": str(safety) if safety else None}
