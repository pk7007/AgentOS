"""budget set | show; limits show | set | host."""

from agentos import db, governor


def register(sub, common) -> None:
    b = sub.add_parser("budget", help="budgets for agent runs, estimated tokens and paid spend")
    bs = b.add_subparsers(dest="budget_cmd", metavar="ACTION")
    st = bs.add_parser("set", parents=[common], help="set a budget limit")
    st.add_argument("scope", choices=["global", "project", "task"])
    st.add_argument("kind", choices=["agent_runs", "tokens_est", "usd"])
    st.add_argument("limit", type=float)
    st.add_argument("--id", default="*", help="project or task id (default * for global)")
    st.set_defaults(func=cmd_budget_set)
    sh = bs.add_parser("show", parents=[common], help="limits, use and what remains")
    sh.set_defaults(func=cmd_budget_show)

    lm = sub.add_parser("limits", help="hard limits on workers, depth, retries and paid spend")
    ls = lm.add_subparsers(dest="limits_cmd", metavar="ACTION")
    show = ls.add_parser("show", parents=[common], help="effective limits (strictest of local and host)")
    show.set_defaults(func=cmd_limits_show)
    lset = ls.add_parser("set", parents=[common], help="lower freely; raising needs the owner")
    lset.add_argument("field", choices=governor.FIELDS)
    lset.add_argument("value", type=float)
    lset.set_defaults(func=cmd_limits_set)
    host = ls.add_parser("host", parents=[common], help="record a limit a host enforces (only tightens)")
    host.add_argument("host")
    host.add_argument("field", choices=governor.FIELDS)
    host.add_argument("value", type=float)
    host.set_defaults(func=cmd_limits_host)


def cmd_budget_set(args, ctx):
    from agentos.cli import owner_guard

    conn = db.require_initialized()
    try:
        owner = None
        if args.kind == "usd" and args.limit > governor.get_limits(conn).max_paid_spend_usd:
            owner = owner_guard(f"budget usd {args.limit}", ctx)
        governor.set_budget(conn, args.scope, args.id, args.kind, args.limit, ctx.actor, owner=owner)
        return governor.budget_report(conn)
    finally:
        conn.close()


def cmd_budget_show(args, ctx):
    conn = db.require_initialized()
    try:
        return governor.budget_report(conn)
    finally:
        conn.close()


def cmd_limits_show(args, ctx):
    conn = db.require_initialized()
    try:
        return governor.get_limits(conn).model_dump()
    finally:
        conn.close()


def cmd_limits_set(args, ctx):
    from agentos.cli import owner_guard

    conn = db.require_initialized()
    try:
        current = getattr(governor._local(conn), args.field)
        owner = owner_guard(f"raise {args.field} to {args.value:g}", ctx) if args.value > current else None
        return governor.set_limit(conn, args.field, args.value, ctx.actor, owner=owner).model_dump()
    finally:
        conn.close()


def cmd_limits_host(args, ctx):
    conn = db.require_initialized()
    try:
        return governor.set_host_limit(conn, args.host, args.field, args.value, ctx.actor).model_dump()
    finally:
        conn.close()
