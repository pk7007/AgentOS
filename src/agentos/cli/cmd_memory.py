"""memory add | search | inspect | correct | delete | export."""

import json
from pathlib import Path

from agentos import db, memory
from agentos.memory import Layer

LAYERS = [x.value for x in Layer]


def register(sub, common) -> None:
    from agentos.cli import add_project_arg

    p = sub.add_parser("memory", help="project-scoped memory with provenance")
    s = p.add_subparsers(dest="memory_cmd", metavar="ACTION")
    a = s.add_parser("add", parents=[common], help="record knowledge")
    add_project_arg(a)
    a.add_argument("layer", choices=LAYERS)
    a.add_argument("text")
    a.add_argument("--source", default="cli")
    a.add_argument("--confidence", type=float, default=0.5)
    a.add_argument("--validated", action="store_true", help="independently verified")
    a.add_argument("--org", action="store_true", help="share with all projects (validated only)")
    a.add_argument("--tag", action="append", default=[])
    a.set_defaults(func=cmd_add)
    q = s.add_parser("search", parents=[common], help="full-text search in this project (+ shared)")
    add_project_arg(q)
    q.add_argument("query")
    q.add_argument("--layer", action="append", choices=LAYERS, default=None)
    q.add_argument("--validated-only", action="store_true")
    q.add_argument("--no-org", action="store_true")
    q.add_argument("--limit", type=int, default=10)
    q.set_defaults(func=cmd_search)
    i = s.add_parser("inspect", parents=[common], help="show one record of this project (or a shared one)")
    add_project_arg(i)
    i.add_argument("id")
    i.set_defaults(func=cmd_inspect)
    c = s.add_parser("correct", parents=[common], help="replace a record with a new version")
    add_project_arg(c)
    c.add_argument("id")
    c.add_argument("text")
    c.set_defaults(func=cmd_correct)
    d = s.add_parser("delete", parents=[common], help="wipe a record's content (tombstone kept)")
    add_project_arg(d)
    d.add_argument("id")
    d.set_defaults(func=cmd_delete)
    e = s.add_parser("export", parents=[common], help="export this project's records")
    add_project_arg(e)
    e.add_argument("--out", type=Path, default=None)
    e.set_defaults(func=cmd_export)


def _short(r):
    return {"id": r.id, "layer": r.layer.value, "scope": r.scope, "validated": r.validated, "v": r.version,
            "content": r.content[:120]}


def _project(conn, args):
    from agentos.cli import resolve_project

    return resolve_project(conn, args.project)


def cmd_add(args, ctx):
    conn = db.require_initialized()
    try:
        r = memory.add(conn, _project(conn, args).id, Layer(args.layer), args.text, args.source, ctx.actor,
                       args.confidence, args.validated, "org" if args.org else "project", args.tag)
        return r.model_dump(mode="json")
    finally:
        conn.close()


def cmd_search(args, ctx):
    conn = db.require_initialized()
    try:
        hits = memory.search(conn, _project(conn, args).id, args.query, args.layer, not args.no_org,
                             args.validated_only, args.limit)
        return [_short(h) for h in hits]
    finally:
        conn.close()


def cmd_inspect(args, ctx):
    conn = db.require_initialized()
    try:
        return memory.read(conn, args.id, _project(conn, args).id).model_dump(mode="json")
    finally:
        conn.close()


def cmd_correct(args, ctx):
    conn = db.require_initialized()
    try:
        return memory.correct(conn, args.id, args.text, ctx.actor, _project(conn, args).id).model_dump(mode="json")
    finally:
        conn.close()


def cmd_delete(args, ctx):
    conn = db.require_initialized()
    try:
        return memory.delete(conn, args.id, ctx.actor, _project(conn, args).id).model_dump(mode="json")
    finally:
        conn.close()


def cmd_export(args, ctx):
    conn = db.require_initialized()
    try:
        records = memory.export(conn, _project(conn, args).id)
    finally:
        conn.close()
    if args.out:
        args.out.write_text(json.dumps(records, indent=2), encoding="utf-8")
        return {"written": str(args.out), "records": len(records)}
    return records
