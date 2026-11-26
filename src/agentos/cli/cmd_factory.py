"""factory propose | register | reject | recruit | expire | list | show.

The Agent Factory: a capability gap becomes a validated specialist configuration, registered within
the owner's permissions and recruited through admission."""

from agentos import db, factory
from agentos.cli import add_project_arg
from agentos.util import load_toml


def register(sub, common) -> None:
    p = sub.add_parser("factory", help="propose, validate, register and recruit specialists for capability gaps")
    s = p.add_subparsers(dest="factory_cmd", metavar="ACTION")
    pr = s.add_parser("propose", parents=[common], help="draft a specialist for capabilities no template covers")
    add_project_arg(pr)
    pr.add_argument("--cap", action="append", default=[], help="capability needed (repeat)")
    pr.add_argument("--task", default=None, help="the task the gap came from (its capabilities by default)")
    pr.add_argument("--file", default=None, help="TOML with fields to set (instructions, tools, ...)")
    pr.add_argument("--permanent", action="store_true", help="do not expire (default: temporary)")
    pr.add_argument("--ttl-hours", type=float, default=factory.DEFAULT_TTL_HOURS)
    pr.set_defaults(func=cmd_propose)
    for name, helptext, func in (("register", "validate again and register (owner approval if wider)", cmd_register),
                                 ("show", "one proposal", cmd_show)):
        x = s.add_parser(name, parents=[common], help=helptext)
        add_project_arg(x)
        x.add_argument("proposal")
        x.set_defaults(func=func)
    rj = s.add_parser("reject", parents=[common], help="close a proposal without registering it")
    add_project_arg(rj)
    rj.add_argument("proposal")
    rj.add_argument("--reason", required=True)
    rj.set_defaults(func=cmd_reject)
    rc = s.add_parser("recruit", parents=[common], help="staff a task: existing template or a new specialist, "
                                                        "then admission")
    add_project_arg(rc)
    rc.add_argument("--task", required=True)
    rc.add_argument("--host", required=True)
    rc.add_argument("--parent", default=None, help="your instance id, if you delegate")
    rc.add_argument("--permanent", action="store_true")
    rc.set_defaults(func=cmd_recruit)
    ex = s.add_parser("expire", parents=[common], help="suspend temporary specialists past their expiry")
    add_project_arg(ex)
    ex.set_defaults(func=cmd_expire)
    ls = s.add_parser("list", parents=[common], help="proposals of this project")
    add_project_arg(ls)
    ls.add_argument("--status", choices=["proposed", "registered", "rejected", "expired"], default=None)
    ls.set_defaults(func=cmd_list)


def _project(conn, args):
    from agentos.cli import resolve_project

    return resolve_project(conn, getattr(args, "project", None))


def _proposal(conn, args):
    from agentos.cli import require_project

    p = factory.get_proposal(conn, args.proposal)
    require_project(conn, args, p.project_id, f"proposal {p.id}")
    return p


def _task(conn, args):
    from agentos import tasks
    from agentos.cli import require_project

    t = tasks.get_task(conn, args.task)
    require_project(conn, args, t.project_id, f"task {t.id}")
    return t


def cmd_propose(args, ctx):
    overrides = load_toml(args.file) if args.file else None
    conn = db.require_initialized()
    try:
        proj = _project(conn, args)
        task_id = _task(conn, args).id if args.task else None
        return factory.propose(conn, proj.id, args.cap, ctx.actor, task_id=task_id, temporary=not args.permanent,
                               ttl_hours=args.ttl_hours, overrides=overrides).model_dump()
    finally:
        conn.close()


def cmd_register(args, ctx):
    conn = db.require_initialized()
    try:
        r = factory.register(conn, _proposal(conn, args).id, ctx.actor)
        return (r, 3) if r["status"] != "registered" else r
    finally:
        conn.close()


def cmd_show(args, ctx):
    conn = db.require_initialized()
    try:
        return _proposal(conn, args).model_dump()
    finally:
        conn.close()


def cmd_reject(args, ctx):
    conn = db.require_initialized()
    try:
        return factory.reject(conn, _proposal(conn, args).id, ctx.actor, args.reason).model_dump()
    finally:
        conn.close()


def cmd_recruit(args, ctx):
    conn = db.require_initialized()
    try:
        r = factory.recruit_for(conn, _task(conn, args).id, args.host, ctx.actor, parent=args.parent,
                                temporary=not args.permanent)
        return (r, 3) if r["status"] != "admitted" else r
    finally:
        conn.close()


def cmd_expire(args, ctx):
    conn = db.require_initialized()
    try:
        return factory.expire(conn, ctx.actor, project_id=_project(conn, args).id)
    finally:
        conn.close()


def cmd_list(args, ctx):
    conn = db.require_initialized()
    try:
        return [p.model_dump(include={"id", "template_id", "status", "temporary", "expires_at", "owner_reasons",
                                      "problems", "task_id"})
                for p in factory.list_proposals(conn, _project(conn, args).id, args.status)]
    finally:
        conn.close()
