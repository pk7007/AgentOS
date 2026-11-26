"""agent admit | transition | confirm-stop | list | inspect (live instances, not templates)."""

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
    add_project_arg(t)
    t.set_defaults(func=cmd_transition)
    cs = s.add_parser("confirm-stop", parents=[common],
                      help="the runtime worker is really gone: free the slot a CANCELLED/unconfirmed agent holds")
    cs.add_argument("id")
    add_project_arg(cs)
    cs.set_defaults(func=cmd_confirm_stop)
    ls = s.add_parser("list", parents=[common], help="list instances")
    add_project_arg(ls)
    ls.add_argument("--all-projects", action="store_true")
    ls.add_argument("--active", action="store_true")
    ls.set_defaults(func=cmd_list)
    i = s.add_parser("inspect", parents=[common], help="show one instance")
    i.add_argument("id")
    add_project_arg(i)
    i.set_defaults(func=cmd_inspect)
    _register_admit(s, common)


def _register_admit(s, common) -> None:
    from agentos.cli import add_project_arg

    a = s.add_parser("admit", parents=[common],
                     help="ask permission before spawning a worker (exit 3 = denied: do not spawn)")
    add_project_arg(a)
    a.add_argument("--task", required=True)
    a.add_argument("--template", required=True)
    a.add_argument("--parent", default=None, help="instance id of the delegating agent")
    a.add_argument("--host", default="other", help="codex, cc or other")
    a.set_defaults(func=cmd_admit)


def cmd_admit(args, ctx):
    from agentos import admission
    from agentos.cli import resolve_project

    conn = db.require_initialized()
    try:
        p = resolve_project(conn, args.project)
        d = admission.admit(conn, admission.AdmitRequest(project_id=p.id, task_id=args.task,
                                                         template_id=args.template,
                                                         parent_instance_id=args.parent, host=args.host),
                            ctx.actor)
        return d.model_dump(), (0 if d.allowed else 3)
    finally:
        conn.close()


def _view(inst):
    d = inst.model_dump(mode="json")
    d["state"] = inst.display_state()
    return d


def _owned(conn, args):
    from agentos.cli import require_project

    inst = lifecycle.get_instance(conn, args.id)
    require_project(conn, args, inst.project_id, f"agent {inst.id}")
    return inst


def cmd_transition(args, ctx):
    conn = db.require_initialized()
    try:
        _owned(conn, args)
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


def cmd_confirm_stop(args, ctx):
    conn = db.require_initialized()
    try:
        _owned(conn, args)
        return _view(lifecycle.confirm_stopped(conn, args.id, ctx.actor))
    finally:
        conn.close()


def cmd_inspect(args, ctx):
    conn = db.require_initialized()
    try:
        return _view(_owned(conn, args))
    finally:
        conn.close()
