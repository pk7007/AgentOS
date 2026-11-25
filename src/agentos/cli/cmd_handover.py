"""handover create | resume | list."""

from pathlib import Path

from agentos import db, handover


def register(sub, common) -> None:
    from agentos.cli import add_project_arg

    p = sub.add_parser("handover", help="hand work to another session or host")
    s = p.add_subparsers(dest="handover_cmd", metavar="ACTION")
    c = s.add_parser("create", parents=[common], help="write a sanitized handover for this project")
    add_project_arg(c)
    c.add_argument("--objective", required=True)
    c.add_argument("--next", dest="next_action", required=True)
    c.add_argument("--host", default="other")
    c.set_defaults(func=cmd_create)
    r = s.add_parser("resume", parents=[common], help="claim a handover (only once) and check the repo")
    add_project_arg(r)
    r.add_argument("id")
    r.add_argument("--host", default="other")
    r.set_defaults(func=cmd_resume)
    ls = s.add_parser("list", parents=[common], help="list handovers")
    add_project_arg(ls)
    ls.set_defaults(func=cmd_list)


def cmd_create(args, ctx):
    from agentos.cli import resolve_project

    conn = db.require_initialized()
    try:
        p = resolve_project(conn, args.project)
        h = handover.create(conn, p.id, Path(p.path), args.host, args.objective, args.next_action, ctx.actor)
        return {"id": h.id, "path": str(handover._file(h.id)), "tasks": len(h.tasks),
                "active_instances": len(h.active_instances), "git": h.git}
    finally:
        conn.close()


def cmd_resume(args, ctx):
    from agentos.cli import resolve_project

    conn = db.require_initialized()
    try:
        p = resolve_project(conn, args.project)
        r = handover.resume(conn, args.id, Path(p.path), args.host, ctx.actor)
        return r.model_dump()
    finally:
        conn.close()


def cmd_list(args, ctx):
    from agentos.cli import resolve_project

    conn = db.require_initialized()
    try:
        return handover.list_handovers(conn, resolve_project(conn, args.project).id)
    finally:
        conn.close()
