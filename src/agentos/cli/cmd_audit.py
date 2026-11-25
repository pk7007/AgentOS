"""audit verify | log."""

from agentos import audit, db


def register(sub, common) -> None:
    p = sub.add_parser("audit", help="inspect the tamper-evident audit log")
    s = p.add_subparsers(dest="audit_cmd", metavar="ACTION")
    v = s.add_parser("verify", parents=[common], help="re-check every hash in the chain")
    v.set_defaults(func=cmd_verify)
    lg = s.add_parser("log", parents=[common], help="show recent events")
    lg.add_argument("--kind", default=None)
    lg.add_argument("--limit", type=int, default=50)
    lg.set_defaults(func=cmd_log)


def cmd_verify(args, ctx):
    conn = db.require_initialized()
    try:
        result = audit.verify_chain(conn)
    finally:
        conn.close()
    return result.model_dump(), (0 if result.ok else 5)


def cmd_log(args, ctx):
    conn = db.require_initialized()
    try:
        return audit.list_events(conn, limit=args.limit, kind=args.kind)
    finally:
        conn.close()
