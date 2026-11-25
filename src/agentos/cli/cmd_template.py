"""template add | seed | list | inspect | suspend | quarantine | retire | reinstate."""

import tomllib
from pathlib import Path

from agentos import db, templates
from agentos.templates import AgentTemplate, TemplateStatus


def default_definitions_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "definitions" / "agents"


def register(sub, common) -> None:
    p = sub.add_parser("template", help="manage agent templates (stored configurations)")
    s = p.add_subparsers(dest="template_cmd", metavar="ACTION")
    a = s.add_parser("add", parents=[common], help="add a template (new version if the id exists)")
    a.add_argument("file", type=Path)
    a.set_defaults(func=cmd_add)
    sd = s.add_parser("seed", parents=[common], help="load the bundled definitions")
    sd.add_argument("--dir", type=Path, default=None)
    sd.set_defaults(func=cmd_seed)
    ls = s.add_parser("list", parents=[common], help="list templates (latest versions)")
    ls.add_argument("--status", choices=[x.value for x in TemplateStatus], default=None)
    ls.set_defaults(func=cmd_list)
    i = s.add_parser("inspect", parents=[common], help="show one template")
    i.add_argument("id")
    i.add_argument("--version", type=int, default=None)
    i.set_defaults(func=cmd_inspect)
    for verb, status, owner in [("suspend", "suspended", False), ("quarantine", "quarantined", False),
                                ("retire", "retired", True), ("reinstate", "active", None)]:
        m = s.add_parser(verb, parents=[common], help=f"set status to {status}")
        m.add_argument("id")
        m.add_argument("--reason", required=True)
        m.set_defaults(func=cmd_status, to=status, verb=verb)


def cmd_add(args, ctx):
    conn = db.require_initialized()
    try:
        with args.file.open("rb") as fh:
            t = AgentTemplate(**tomllib.load(fh))
        return templates.add_template(conn, t, ctx.actor).model_dump(mode="json")
    finally:
        conn.close()


def cmd_seed(args, ctx):
    conn = db.require_initialized()
    try:
        return templates.seed(conn, args.dir or default_definitions_dir(), ctx.actor)
    finally:
        conn.close()


def cmd_list(args, ctx):
    conn = db.require_initialized()
    try:
        return [{"id": t.id, "version": t.version, "status": t.status.value, "role": t.role,
                 "capabilities": t.capabilities} for t in templates.list_templates(conn, args.status)]
    finally:
        conn.close()


def cmd_inspect(args, ctx):
    conn = db.require_initialized()
    try:
        return templates.get_template(conn, args.id, args.version).model_dump(mode="json")
    finally:
        conn.close()


def cmd_status(args, ctx):
    from agentos.cli import owner_guard

    conn = db.require_initialized()
    try:
        to = TemplateStatus(args.to)
        current = templates.get_template(conn, args.id)
        needs_owner = templates._ALLOWED.get((current.status, to), False)
        owner = owner_guard(f"{args.verb} {args.id}", ctx) if needs_owner else None
        return templates.set_status(conn, args.id, to, ctx.actor, args.reason, owner=owner).model_dump(mode="json")
    finally:
        conn.close()
