"""stop [--lift]; approval request | grant | deny | check | consume | list."""

import json

from agentos import db, governance


def register(sub, common) -> None:
    st = sub.add_parser("stop", parents=[common], help="emergency stop: admit no new workers (anyone may engage)")
    st.add_argument("--reason", default="manual stop")
    st.add_argument("--lift", action="store_true", help="lift the stop (owner only)")
    st.set_defaults(func=cmd_stop)

    ap = sub.add_parser("approval", help="approvals bound to one action and its exact parameters")
    s = ap.add_subparsers(dest="approval_cmd", metavar="ACTION")
    rq = s.add_parser("request", parents=[common], help="ask the owner to approve an action")
    rq.add_argument("action")
    rq.add_argument("--params", default="{}", help="JSON object")
    rq.add_argument("--ttl", type=int, default=60, help="minutes until it expires")
    rq.set_defaults(func=cmd_request)
    for verb in ("grant", "deny", "consume"):
        p = s.add_parser(verb, parents=[common], help=f"{verb} an approval")
        p.add_argument("id")
        p.set_defaults(func=cmd_decide, verb=verb)
    ck = s.add_parser("check", parents=[common], help="exit 0 if a valid approval exists, else 3")
    ck.add_argument("action")
    ck.add_argument("--params", default="{}")
    ck.set_defaults(func=cmd_check)
    ls = s.add_parser("list", parents=[common], help="list approvals")
    ls.add_argument("--status", default=None)
    ls.set_defaults(func=cmd_list)


def cmd_stop(args, ctx):
    from agentos.cli import owner_guard

    conn = db.require_initialized()
    try:
        if args.lift:
            governance.lift_stop(conn, ctx.actor, owner_guard("lift emergency stop", ctx))
        else:
            governance.emergency_stop(conn, ctx.actor, args.reason)
        return {"emergency_stop": governance.is_stopped(conn)}
    finally:
        conn.close()


def _params(raw: str) -> dict:
    from agentos.errors import UsageError

    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise UsageError(f"--params is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise UsageError("--params must be a JSON object")
    return value


def cmd_request(args, ctx):
    conn = db.require_initialized()
    try:
        return governance.request_approval(conn, args.action, _params(args.params), ctx.actor,
                                           args.ttl).model_dump()
    finally:
        conn.close()


def cmd_decide(args, ctx):
    from agentos.cli import owner_guard

    conn = db.require_initialized()
    try:
        if args.verb == "grant":
            a = governance.get_approval(conn, args.id)
            owner = owner_guard(f"grant {a.action} {json.dumps(a.params, sort_keys=True)}", ctx)
            return governance.grant(conn, args.id, owner, ctx.actor).model_dump()
        if args.verb == "deny":
            return governance.deny(conn, args.id, ctx.actor).model_dump()
        return governance.consume(conn, args.id, ctx.actor).model_dump()
    finally:
        conn.close()


def cmd_check(args, ctx):
    conn = db.require_initialized()
    try:
        a = governance.check(conn, args.action, _params(args.params))
        return ({"approved": a is not None, "approval": a.model_dump() if a else None}, 0 if a else 3)
    finally:
        conn.close()


def cmd_list(args, ctx):
    conn = db.require_initialized()
    try:
        return [a.model_dump() for a in governance.list_approvals(conn, args.status)]
    finally:
        conn.close()
