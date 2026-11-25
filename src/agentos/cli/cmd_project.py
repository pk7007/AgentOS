"""project activate | deactivate | list."""

from pathlib import Path

from agentos import db, projects


def register(sub, common) -> None:
    p = sub.add_parser("project", help="turn AgentOS on or off for a repository")
    s = p.add_subparsers(dest="project_cmd", metavar="ACTION")
    a = s.add_parser("activate", parents=[common], help="activate the repo at PATH (default: cwd)")
    a.add_argument("path", nargs="?", type=Path, default=Path.cwd())
    a.set_defaults(func=cmd_activate)
    d = s.add_parser("deactivate", parents=[common], help="deactivate the repo at PATH or by id")
    d.add_argument("target", nargs="?", default=None)
    d.set_defaults(func=cmd_deactivate)
    ls = s.add_parser("list", parents=[common], help="list known projects")
    ls.set_defaults(func=cmd_list)


def cmd_activate(args, ctx):
    conn = db.require_initialized()
    try:
        return projects.activate(conn, args.path, ctx.actor).model_dump()
    finally:
        conn.close()


def cmd_deactivate(args, ctx):
    from agentos.cli import resolve_project

    conn = db.require_initialized()
    try:
        p = resolve_project(conn, args.target)
        return projects.deactivate(conn, p.id, ctx.actor).model_dump()
    finally:
        conn.close()


def cmd_list(args, ctx):
    conn = db.require_initialized()
    try:
        return [p.model_dump() for p in projects.list_projects(conn)]
    finally:
        conn.close()
