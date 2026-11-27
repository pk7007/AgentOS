"""dashboard; observe agents | tree | progress | recruitment | terminations | performance | resources |
experiments | changes | incidents | controls.

What is happening, from the ledger and the audit log only. Read-only."""

from agentos import db, observe


def register(sub, common) -> None:
    from agentos.cli import add_project_arg

    d = sub.add_parser("dashboard", parents=[common], help="one screen: controls, workers, progress, incidents")
    add_project_arg(d)
    d.set_defaults(func=cmd_dashboard)
    p = sub.add_parser("observe", help="active workers, hierarchy, progress, history, incidents and controls")
    s = p.add_subparsers(dest="observe_cmd", metavar="VIEW")

    def view(name, func, help_, project=True, limit=False):
        c = s.add_parser(name, parents=[common], help=help_)
        if project:
            add_project_arg(c)
        if limit:
            c.add_argument("--limit", type=int, default=50)
        c.set_defaults(func=func)
        return c

    view("agents", cmd_agents, "workers holding a slot now, with what the host reported").add_argument(
        "--all-projects", action="store_true")
    view("tree", cmd_tree, "the worker hierarchy (parents and children)").add_argument(
        "--all", action="store_true", help="include archived workers")
    view("progress", cmd_progress, "task progress per objective")
    view("recruitment", cmd_recruitment, "admissions, refusals and new templates", limit=True)
    view("terminations", cmd_terminations, "terminations and stops still unconfirmed by the host", limit=True)
    view("performance", cmd_performance, "per-template performance records", project=False)
    view("resources", cmd_resources, "slots, agent runs, tokens and paid spend against budgets")
    view("experiments", cmd_experiments, "improvement experiments and their status")
    view("changes", cmd_changes, "accepted and rejected changes to the organisation")
    view("incidents", cmd_incidents, "security incidents, most severe first", limit=True)
    view("controls", cmd_controls, "emergency stop, owner pin, limits and the commands to act", project=False)


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
def cmd_dashboard(conn, args, ctx):
    d = observe.dashboard(conn, _pid(conn, args))
    return d if ctx.json else observe.render_dashboard(d)


@_run
def cmd_agents(conn, args, ctx):
    return observe.active_agents(conn, None if args.all_projects else _pid(conn, args))


@_run
def cmd_tree(conn, args, ctx):
    roots = observe.hierarchy(conn, _pid(conn, args), include_finished=args.all)
    return roots if ctx.json else observe.render_tree(roots)


@_run
def cmd_progress(conn, args, ctx):
    return observe.progress(conn, _pid(conn, args))


@_run
def cmd_recruitment(conn, args, ctx):
    return observe.recruitment(conn, _pid(conn, args), args.limit)


@_run
def cmd_terminations(conn, args, ctx):
    return observe.terminations(conn, _pid(conn, args), args.limit)


@_run
def cmd_performance(conn, args, ctx):
    return observe.performance_records(conn)


@_run
def cmd_resources(conn, args, ctx):
    return observe.resources(conn, _pid(conn, args))


@_run
def cmd_experiments(conn, args, ctx):
    return observe.experiments(conn, _pid(conn, args))


@_run
def cmd_changes(conn, args, ctx):
    return observe.changes(conn, _pid(conn, args))


@_run
def cmd_incidents(conn, args, ctx):
    return observe.incidents(conn, _pid(conn, args), args.limit)


@_run
def cmd_controls(conn, args, ctx):
    return observe.controls(conn)
