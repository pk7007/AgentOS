"""task add | dep | list | inspect | ready | start | done | fail | block | cancel | retry; plan score."""

from agentos import complexity, db, tasks
from agentos.tasks import TaskState

_MOVES = {
    "start": TaskState.running, "done": TaskState.done, "fail": TaskState.failed,
    "block": TaskState.blocked, "cancel": TaskState.cancelled, "retry": TaskState.pending,
    "unblock": TaskState.pending,
}


def register(sub, common) -> None:
    from agentos.cli import add_project_arg

    p = sub.add_parser("task", help="manage the task graph of a project")
    s = p.add_subparsers(dest="task_cmd", metavar="ACTION")
    a = s.add_parser("add", parents=[common], help="add a task")
    add_project_arg(a)
    a.add_argument("title")
    a.add_argument("--objective", default="")
    a.add_argument("--cap", action="append", default=[], help="required capability (repeatable)")
    a.add_argument("--accept", action="append", default=[], help="acceptance criterion (repeatable)")
    a.add_argument("--parent", default=None)
    a.add_argument("--priority", type=int, default=50)
    a.add_argument("--risk", choices=["low", "medium", "high", "critical"], default="low")
    a.set_defaults(func=cmd_add)
    d = s.add_parser("dep", parents=[common], help="TASK depends on --on OTHER")
    d.add_argument("task")
    d.add_argument("--on", required=True)
    d.set_defaults(func=cmd_dep)
    ls = s.add_parser("list", parents=[common], help="list tasks")
    add_project_arg(ls)
    ls.add_argument("--state", choices=[x.value for x in TaskState], default=None)
    ls.set_defaults(func=cmd_list)
    r = s.add_parser("ready", parents=[common], help="tasks whose dependencies are done")
    add_project_arg(r)
    r.set_defaults(func=cmd_ready)
    i = s.add_parser("inspect", parents=[common], help="show one task")
    i.add_argument("task")
    i.set_defaults(func=cmd_inspect)
    for verb in _MOVES:
        m = s.add_parser(verb, parents=[common], help=f"move a task ({_MOVES[verb].value})")
        m.add_argument("task")
        m.add_argument("--note", default=None)
        m.set_defaults(func=cmd_move, verb=verb)

    plan = sub.add_parser("plan", help="planning helpers")
    ps = plan.add_subparsers(dest="plan_cmd", metavar="ACTION")
    sc = ps.add_parser("score", parents=[common], help="complexity score and staffing band")
    for flag, dest in [("--tasks", "task_count"), ("--depth", "dependency_depth"),
                       ("--workstreams", "workstreams"), ("--files", "files_touched"),
                       ("--difficulty", "domain_difficulty"), ("--uncertainty", "uncertainty"),
                       ("--risk", "risk"), ("--verify", "verification_effort")]:
        sc.add_argument(flag, dest=dest, type=int, default=0)
    sc.set_defaults(func=cmd_score)


def _task_list(items):
    return [{"id": t.id, "title": t.title, "state": t.state.value, "priority": t.priority,
             "deps": t.deps} for t in items]


def cmd_add(args, ctx):
    from agentos.cli import resolve_project

    conn = db.require_initialized()
    try:
        p = resolve_project(conn, args.project)
        t = tasks.add_task(conn, p.id, args.title, objective=args.objective, capabilities=args.cap,
                           acceptance=args.accept, parent_id=args.parent, priority=args.priority,
                           risk=args.risk, actor=ctx.actor)
        return t.model_dump(mode="json")
    finally:
        conn.close()


def cmd_dep(args, ctx):
    conn = db.require_initialized()
    try:
        tasks.add_dependency(conn, args.task, args.on, ctx.actor)
        return tasks.get_task(conn, args.task).model_dump(mode="json")
    finally:
        conn.close()


def cmd_list(args, ctx):
    from agentos.cli import resolve_project

    conn = db.require_initialized()
    try:
        return _task_list(tasks.list_tasks(conn, resolve_project(conn, args.project).id, args.state))
    finally:
        conn.close()


def cmd_ready(args, ctx):
    from agentos.cli import resolve_project

    conn = db.require_initialized()
    try:
        return _task_list(tasks.ready_tasks(conn, resolve_project(conn, args.project).id))
    finally:
        conn.close()


def cmd_inspect(args, ctx):
    conn = db.require_initialized()
    try:
        return tasks.get_task(conn, args.task).model_dump(mode="json")
    finally:
        conn.close()


def cmd_move(args, ctx):
    conn = db.require_initialized()
    try:
        return tasks.set_state(conn, args.task, _MOVES[args.verb], ctx.actor, args.note).model_dump(mode="json")
    finally:
        conn.close()


def cmd_score(args, ctx):
    fields = complexity.ComplexityInput.model_fields
    inp = complexity.ComplexityInput(**{k: getattr(args, k) for k in fields})
    return complexity.score(inp).model_dump()
