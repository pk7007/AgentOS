"""health heartbeat | stale | reap; policy show | history | project-limit; bench run | history;
retention plan | apply; mcp serve.

Running AgentOS itself: worker liveness and recovery, the versioned policy, benchmarks of AgentOS's own speed,
data retention, and a read-only Model Context Protocol server."""

from agentos import bench, db, health, policy_log, retention


def register(sub, common) -> None:
    from agentos.cli import add_project_arg

    def group(name, help_):
        p = sub.add_parser(name, help=help_)
        return p.add_subparsers(dest=f"{name}_cmd", metavar="ACTION")

    def cmd(s, name, func, help_, project=False):
        c = s.add_parser(name, parents=[common], help=help_)
        if project:
            add_project_arg(c)
        c.set_defaults(func=func)
        return c

    h = group("health", "worker heartbeats, stale workers and their recovery")
    cmd(h, "heartbeat", cmd_heartbeat, "report that a worker is alive", project=True).add_argument("instance")
    c = cmd(h, "breaker", cmd_breaker, "show the circuit breaker, or change it (milder needs the owner)")
    c.add_argument("--window", type=int, default=None, help="evaluations in a row (1-20)")
    c.add_argument("--floor", type=float, default=None, help="score every one of them is below (0-100)")
    c = cmd(h, "stale", cmd_stale, "active workers not heard from for longer than the threshold", project=True)
    c.add_argument("--after-minutes", type=float, default=health.DEFAULT_STALE_MINUTES)
    c = cmd(h, "reap", cmd_reap, "fail stale workers, free their slots and retry or escalate their tasks",
            project=True)
    c.add_argument("--after-minutes", type=float, default=health.DEFAULT_STALE_MINUTES)

    p = group("policy", "the policy in force, its version and every change to it")
    cmd(p, "show", cmd_policy_show, "version, hash and values of the policy in force")
    cmd(p, "history", cmd_policy_history, "every policy change, oldest first").add_argument(
        "--limit", type=int, default=50)
    c = cmd(p, "project-limit", cmd_project_limit, "a limit for this project only (tightening needs nobody)",
            project=True)
    c.add_argument("field")
    c.add_argument("value", type=float)

    b = group("bench", "benchmarks of AgentOS's own operations, on a throwaway database")
    c = cmd(b, "run", cmd_bench_run, "measure admission, audit, memory search and chain verification")
    c.add_argument("--n", type=int, default=100)
    c.add_argument("--no-record", action="store_true", help="do not store the result")
    cmd(b, "history", cmd_bench_history, "the trend of each benchmark and whether the latest run regressed"
        ).add_argument("--name", default=None)

    r = group("retention", "remove read messages, old benchmark runs, released claims and deleted memory for good")
    cmd(r, "plan", cmd_ret_plan, "count what would be removed").add_argument("--days", type=int, default=90)
    cmd(r, "apply", cmd_ret_apply, "remove it (owner only)").add_argument("--days", type=int, default=90)

    m = group("mcp", "Model Context Protocol server (read-only tools)")
    cmd(m, "serve", cmd_mcp_serve, "serve over stdio until the client disconnects")


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
def cmd_heartbeat(conn, args, ctx):
    return health.heartbeat(conn, args.instance, _pid(conn, args))


@_run
def cmd_breaker(conn, args, ctx):
    from agentos.cli import owner_guard

    if args.window is None and args.floor is None:
        return health.breaker_settings(conn)
    old, new = health.proposed_breaker(conn, args.window, args.floor)
    owner = owner_guard("make the circuit breaker milder", ctx) if health.is_milder(old, new) else None
    return health.set_breaker(conn, ctx.actor, args.window, args.floor, owner=owner)


@_run
def cmd_stale(conn, args, ctx):
    return health.stale(conn, _pid(conn, args), args.after_minutes)


@_run
def cmd_reap(conn, args, ctx):
    return health.reap(conn, _pid(conn, args), ctx.actor, args.after_minutes)


@_run
def cmd_policy_show(conn, args, ctx):
    return policy_log.snapshot(conn)


@_run
def cmd_policy_history(conn, args, ctx):
    return policy_log.history(conn, args.limit)


@_run
def cmd_project_limit(conn, args, ctx):
    from agentos import governor
    from agentos.cli import owner_guard

    pid = _pid(conn, args)
    current = governor.project_limits(conn, pid).get(args.field)
    owner = (owner_guard(f"raise the project {args.field} to {args.value:g}", ctx)
             if current is not None and args.value > float(current) else None)
    return governor.set_project_limit(conn, pid, args.field, args.value, ctx.actor, owner=owner)


def cmd_bench_run(args, ctx):
    results = bench.run(args.n)
    if not args.no_record:
        conn = db.require_initialized()
        try:
            bench.record(conn, results)
        finally:
            conn.close()
    return results


@_run
def cmd_bench_history(conn, args, ctx):
    return bench.history(conn, args.name)


@_run
def cmd_ret_plan(conn, args, ctx):
    return retention.plan(conn, args.days)


@_run
def cmd_ret_apply(conn, args, ctx):
    from agentos.cli import owner_guard

    retention.plan(conn, args.days)  # validates the period before asking the owner
    owner = owner_guard(f"remove data older than {args.days} days", ctx)
    return retention.apply(conn, args.days, ctx.actor, owner=owner)


def cmd_mcp_serve(args, ctx):
    from agentos import mcp_server

    mcp_server.serve()  # opens the ledger read-only per call; never migrates
