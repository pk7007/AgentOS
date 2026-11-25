"""eval record; perf show; recruit."""

from agentos import db, performance, recruit
from agentos.errors import UsageError


def register(sub, common) -> None:
    ev = sub.add_parser("eval", help="independent evaluations")
    es = ev.add_subparsers(dest="eval_cmd", metavar="ACTION")
    rec = es.add_parser("record", parents=[common], help="record an evaluation by a different agent")
    rec.add_argument("instance")
    rec.add_argument("--evaluator", required=True, help="who evaluated (not the agent itself, its parent or child)")
    rec.add_argument("--category", required=True)
    rec.add_argument("--score", action="append", default=[], help="key=value, 0-100 (repeatable)")
    rec.add_argument("--evidence", action="append", default=[], help="test command, file or log (repeatable)")
    rec.add_argument("--flag", action="append", default=[], choices=["security_violation", "integrity_violation"])
    rec.add_argument("--external", action="store_true", help="failure caused outside the agent's control")
    rec.set_defaults(func=cmd_record)

    pf = sub.add_parser("perf", help="performance summaries")
    ps = pf.add_subparsers(dest="perf_cmd", metavar="ACTION")
    show = ps.add_parser("show", parents=[common], help="summary for one template")
    show.add_argument("template")
    show.add_argument("--category", default=None)
    show.set_defaults(func=cmd_show)

    rc = sub.add_parser("recruit", parents=[common], help="rank templates for required capabilities")
    rc.add_argument("--cap", action="append", required=True)
    rc.add_argument("--category", default=None)
    rc.add_argument("--high-risk", action="store_true")
    rc.set_defaults(func=cmd_recruit)


def _scores(items: list[str]) -> dict[str, float]:
    out = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep:
            raise UsageError(f"--score must be key=value, got '{item}'")
        try:
            out[key.strip()] = float(value)
        except ValueError as exc:
            raise UsageError(f"--score value is not a number: '{item}'") from exc
    return out


def cmd_record(args, ctx):
    conn = db.require_initialized()
    try:
        e = performance.record_eval(conn, args.instance, args.evaluator, args.category, _scores(args.score),
                                    args.evidence, args.flag, args.external, ctx.actor)
        return e.model_dump()
    finally:
        conn.close()


def cmd_show(args, ctx):
    conn = db.require_initialized()
    try:
        return performance.summary(conn, args.template, args.category).model_dump()
    finally:
        conn.close()


def cmd_recruit(args, ctx):
    conn = db.require_initialized()
    try:
        ranked = recruit.rank(conn, args.cap, args.category, args.high_risk)
        if not ranked:
            missing = recruit.missing_capabilities(conn, args.cap) or args.cap
            return {"candidates": [], "capability_gap": missing,
                    "note": "no active template fits; add one with `agentos template add`"}
        return {"candidates": [c.model_dump() for c in ranked], "capability_gap": []}
    finally:
        conn.close()
