"""audit verify | anchor | log."""

import json
from pathlib import Path

from agentos import audit, db
from agentos.errors import UsageError


def register(sub, common) -> None:
    p = sub.add_parser("audit", help="inspect the tamper-evident audit log")
    s = p.add_subparsers(dest="audit_cmd", metavar="ACTION")
    v = s.add_parser("verify", parents=[common], help="re-check every hash in the chain")
    v.add_argument("--anchor", type=Path, default=None,
                   help="a file written earlier by `audit anchor`: also prove the chain still contains it")
    v.set_defaults(func=cmd_verify)
    an = s.add_parser("anchor", parents=[common],
                      help="print the chain head (or --out FILE); keep it where agents cannot write")
    an.add_argument("--out", type=Path, default=None)
    an.set_defaults(func=cmd_anchor)
    lg = s.add_parser("log", parents=[common], help="show recent events")
    lg.add_argument("--kind", default=None)
    lg.add_argument("--limit", type=int, default=50)
    lg.set_defaults(func=cmd_log)


def _load_anchor(path: Path | None) -> dict | None:
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return {"seq": int(data["seq"]), "hash": str(data["hash"])}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise UsageError(f"cannot read anchor {path}: {exc}") from exc


def cmd_anchor(args, ctx):
    conn = db.require_initialized()
    try:
        head = audit.head(conn)
    finally:
        conn.close()
    if args.out:
        args.out.write_text(json.dumps(head) + "\n", encoding="utf-8")
    return head


def cmd_verify(args, ctx):
    anchor = _load_anchor(args.anchor)
    conn = db.require_initialized()
    try:
        result = audit.verify_chain(conn, anchor=anchor)
    finally:
        conn.close()
    return result.model_dump(), (0 if result.ok else 5)


def cmd_log(args, ctx):
    conn = db.require_initialized()
    try:
        return audit.list_events(conn, limit=args.limit, kind=args.kind)
    finally:
        conn.close()
