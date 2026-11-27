"""msg send | inbox | escalate; claim take | release | list; workflow save | from-objective | list | show | apply.

Coordination between workers: messages (and escalations to the owner), exclusive claims on repository paths,
and reusable task graphs."""

import json
from pathlib import Path

from agentos import comms, db, workflows
from agentos.errors import UsageError


def register(sub, common) -> None:
    from agentos.cli import add_project_arg

    def group(name, help_):
        p = sub.add_parser(name, help=help_)
        return p.add_subparsers(dest=f"{name}_cmd", metavar="ACTION")

    def cmd(s, name, func, help_, project=True):
        c = s.add_parser(name, parents=[common], help=help_)
        if project:
            add_project_arg(c)
        c.set_defaults(func=func)
        return c

    m = group("msg", "messages between workers and the owner, and escalations")
    c = cmd(m, "send", cmd_send, "send a message (recorded in the ledger; the host delivers it)")
    c.add_argument("--from", dest="sender", required=True, help="an agent instance id, or 'owner'")
    c.add_argument("--to", dest="recipient", required=True, help="an agent instance id, 'owner' or 'all'")
    c.add_argument("--kind", default="note", choices=comms.KINDS)
    c.add_argument("--task", default=None)
    c.add_argument("body")
    c = cmd(m, "inbox", cmd_inbox, "messages for a worker, the owner or everyone")
    c.add_argument("recipient", help="an agent instance id, or 'owner'")
    c.add_argument("--all", action="store_true", help="include messages already read")
    c.add_argument("--mark-read", action="store_true")
    c = cmd(m, "escalate", cmd_escalate, "tell the owner something needs a decision (shown on the dashboard)")
    c.add_argument("--from", dest="sender", required=True)
    c.add_argument("--task", default=None)
    c.add_argument("body")

    cl = group("claim", "exclusive claims on repository paths, so two workers never edit the same file")
    c = cmd(cl, "take", cmd_claim, "claim paths for a worker (all or none; refused if another active worker holds one)")
    c.add_argument("instance")
    c.add_argument("paths", nargs="+")
    c = cmd(cl, "release", cmd_release, "release a worker's claims (all of them unless paths are given)")
    c.add_argument("instance")
    c.add_argument("paths", nargs="*")
    cmd(cl, "list", cmd_claims, "open claims and whether their holder is still active")

    w = group("workflow", "reusable task graphs: save a proven plan, apply it to a new objective")
    c = cmd(w, "save", cmd_wf_save, "save a plan file (the `boss plan` format) as a named workflow", project=False)
    c.add_argument("name")
    c.add_argument("--file", type=Path, required=True)
    c = cmd(w, "from-objective", cmd_wf_from, "save a delivered objective's task graph as a workflow")
    c.add_argument("objective")
    c.add_argument("name")
    cmd(w, "list", cmd_wf_list, "saved workflows", project=False)
    c = cmd(w, "show", cmd_wf_show, "one workflow version", project=False)
    c.add_argument("name")
    c.add_argument("--version", type=int, default=None)
    c = cmd(w, "apply", cmd_wf_apply, "create a workflow's tasks under an open objective")
    c.add_argument("objective")
    c.add_argument("name")
    c.add_argument("--version", type=int, default=None)


def _run(fn):
    def handler(args, ctx):
        conn = db.require_initialized()
        try:
            return fn(conn, args, ctx)
        finally:
            conn.close()
    return handler


def _pid(conn, args) -> str:
    from agentos.cli import resolve_project

    return resolve_project(conn, getattr(args, "project", None)).id


@_run
def cmd_send(conn, args, ctx):
    return comms.send(conn, _pid(conn, args), args.sender, args.recipient, args.body, ctx.actor, args.kind, args.task)


@_run
def cmd_inbox(conn, args, ctx):
    return comms.inbox(conn, _pid(conn, args), args.recipient, unread_only=not args.all, mark_read=args.mark_read,
                       actor=ctx.actor)


@_run
def cmd_escalate(conn, args, ctx):
    return comms.escalate(conn, _pid(conn, args), args.sender, args.body, ctx.actor, args.task)


@_run
def cmd_claim(conn, args, ctx):
    return comms.claim(conn, _pid(conn, args), args.instance, args.paths, ctx.actor)


@_run
def cmd_release(conn, args, ctx):
    return comms.release(conn, _pid(conn, args), args.instance, ctx.actor, args.paths or None)


@_run
def cmd_claims(conn, args, ctx):
    return comms.claims(conn, _pid(conn, args))


@_run
def cmd_wf_save(conn, args, ctx):
    try:
        plan = json.loads(args.file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UsageError(f"cannot read plan file {args.file}: {exc}") from exc
    return workflows.save(conn, args.name, plan, ctx.actor, source=str(args.file))


@_run
def cmd_wf_from(conn, args, ctx):
    from agentos import boss
    from agentos.cli import require_project

    obj = boss.get_objective(conn, args.objective)
    require_project(conn, args, obj.project_id, f"objective {obj.id}")
    return workflows.from_objective(conn, obj.id, args.name, ctx.actor)


@_run
def cmd_wf_list(conn, args, ctx):
    return workflows.list_all(conn)


@_run
def cmd_wf_show(conn, args, ctx):
    return workflows.get(conn, args.name, args.version)


@_run
def cmd_wf_apply(conn, args, ctx):
    from agentos import boss
    from agentos.cli import require_project

    obj = boss.get_objective(conn, args.objective)
    require_project(conn, args, obj.project_id, f"objective {obj.id}")
    return workflows.apply(conn, obj.id, args.name, ctx.actor, args.version)
