"""agent admit | transition | list | inspect (live instances, not templates)."""

from agentos import db, lifecycle
from agentos.lifecycle import AgentState


def register(sub, common) -> None:
    from agentos.cli import add_project_arg

    p = sub.add_parser("agent", help="live agent instances")
    s = p.add_subparsers(dest="agent_cmd", metavar="ACTION")
    t = s.add_parser("transition", parents=[common], help="move an instance to another lifecycle state")
    t.add_argument("id")
    t.add_argument("state", type=str.upper, choices=[x.value for x in AgentState])
    t.add_argument("--reason", default=None)
    t.add_argument("--confirmed", action="store_true", help="the host confirmed the runtime worker stopped")
    t.set_defaults(func=cmd_transition)
    ls = s.add_parser("list", parents=[common], help="list instances")
    add_project_arg(ls)
    ls.add_argument("--all-projects", action="store_true")
    ls.add_argument("--active", action="store_true")
    ls.set_defaults(func=cmd_list)
    i = s.add_parser("inspect", parents=[common], help="show one instance")
    i.add_argument("id")
    i.set_defaults(func=cmd_inspect)
    _register_admit(s, common)


def _register_admit(s, common) -> None:
    """Admission is added by the admission task."""


def _view(inst):
    d = inst.model_dump(mode="json")
    d["state"] = inst.display_state()
    return d


def cmd_transition(args, ctx):
    conn = db.require_initialized()
    try:
        confirmed = True if args.confirmed else (False if args.state == "TERMINATED" else None)
        return _view(lifecycle.transition(conn, args.id, AgentState(args.state), ctx.actor, args.reason,
                                          runtime_confirmed=confirmed))
    finally:
        conn.close()


def cmd_list(args, ctx):
    from agentos.cli import resolve_project

    conn = db.require_initialized()
    try:
        pid = None if args.all_projects else resolve_project(conn, args.project).id
        return [{"id": i.id, "template": f"{i.template_id}@v{i.template_version}", "task": i.task_id,
                 "state": i.display_state(), "depth": i.depth, "host": i.host}
                for i in lifecycle.list_instances(conn, project_id=pid, active_only=args.active)]
    finally:
        conn.close()


def cmd_inspect(args, ctx):
    conn = db.require_initialized()
    try:
        return _view(lifecycle.get_instance(conn, args.id))
    finally:
        conn.close()
