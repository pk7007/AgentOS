"""`agentos` command-line entry point.

Each command group lives in a `cmd_*.py` module exposing `register(subparsers, common)`.
Handlers have the signature `func(args, ctx) -> data | (data, exit_code)`.
"""

import argparse
import difflib
import importlib
import json
import os
import sqlite3
import sys
from dataclasses import dataclass

from agentos import __version__
from agentos.errors import AgentOSError, PolicyDenied
from agentos.gen.reason_guide import REMEDY

COMMAND_MODULES: tuple[str, ...] = ("cmd_system", "cmd_audit", "cmd_project", "cmd_task", "cmd_template", "cmd_agent", "cmd_budget", "cmd_governance", "cmd_perf", "cmd_memory", "cmd_handover", "cmd_gen", "cmd_evidence", "cmd_hook", "cmd_boss", "cmd_factory", "cmd_workforce", "cmd_improve", "cmd_host", "cmd_intel", "cmd_observe", "cmd_coord", "cmd_ops")


def owner_guard(action: str, ctx):
    """Ask the human owner at a real terminal to confirm `action`. Raises PolicyDenied otherwise."""
    from agentos import db, governance, paths

    conn = db.connect() if paths.db_path().exists() else None
    try:
        return governance.confirm_owner(action, conn=conn)
    finally:
        if conn is not None:
            conn.close()


def add_project_arg(parser) -> None:
    parser.add_argument("--project", default=None, help="project id or repo path (default: cwd)")


def resolve_project(conn, target: str | None):
    """Resolve --project / positional target: a project id, a path, or the current directory."""
    from pathlib import Path

    from agentos import projects

    if target and target.startswith("prj_"):
        return projects.get_project(conn, target)
    return projects.get_project(conn, projects.project_id_for(Path(target) if target else Path.cwd()))


def require_project(conn, args, owner_project_id: str, what: str):
    """Commands that act on one record by id may only touch records of the current project
    (cwd or --project). Returns the current project."""
    from agentos.errors import PolicyDenied

    current = resolve_project(conn, getattr(args, "project", None))
    if current.id != owner_project_id:
        raise PolicyDenied(f"{what} belongs to another project; run from its repository or pass --project",
                           reasons=["cross_project"])
    return current


@dataclass
class Context:
    actor: str
    json: bool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentos", description="Local ledger and policy engine for multi-agent coding hosts."
    )
    parser.add_argument("--version", action="version", version=f"agentos {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable output")
    common.add_argument("--actor", default=None, help="who is acting (default: $AGENTOS_ACTOR or 'host')")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    for name in COMMAND_MODULES:
        importlib.import_module(f"agentos.cli.{name}").register(sub, common)
    return parser


def _render(data) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        lines = []
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                v = json.dumps(v, default=str)
            lines.append(f"{k}: {v}")
        return "\n".join(lines)
    if isinstance(data, list):
        if not data:
            return "(none)"
        return "\n".join(
            "  ".join(f"{k}={v}" for k, v in item.items()) if isinstance(item, dict) else str(item)
            for item in data
        )
    return str(data)


def _suggest(parser: argparse.ArgumentParser, argv: list[str]) -> None:
    """After argparse refuses an unknown command, name the closest real ones."""
    level = parser
    for word in [a for a in argv if not a.startswith("-")]:
        subs = [a for a in level._actions if isinstance(a, argparse._SubParsersAction)]
        if not subs:
            return
        choices = subs[0].choices
        if word not in choices:
            close = difflib.get_close_matches(word, list(choices), n=3, cutoff=0.6)
            if close:
                print("did you mean: " + ", ".join(close) + "?", file=sys.stderr)
            return
        level = choices[word]


def _database_error(exc: sqlite3.DatabaseError) -> int:
    """A busy database (exit 2: try again) is told apart from one that cannot be read (exit 5: doctor and
    restore) and from any other database error (exit 5, reported as it is)."""
    text = str(exc).lower()
    if isinstance(exc, sqlite3.OperationalError) and ("locked" in text or "busy" in text):
        print("error: the AgentOS database is busy (another agentos command is writing); try again in a"
              " moment", file=sys.stderr)
        return 2
    if type(exc) is sqlite3.DatabaseError or "malformed" in text or "not a database" in text:
        print(f"error: the AgentOS database cannot be read ({exc}); run `agentos doctor`, and restore a"
              " backup with `agentos restore` if it is damaged", file=sys.stderr)
        return 5
    print(f"error: database error: {exc}", file=sys.stderr)
    return 5


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code:
            _suggest(parser, sys.argv[1:] if argv is None else argv)
        return exc.code if isinstance(exc.code, int) else 2
    if not getattr(args, "func", None):
        parser.print_help(sys.stderr)
        return 2
    ctx = Context(actor=args.actor or os.environ.get("AGENTOS_ACTOR") or "host", json=args.json)
    try:
        result = args.func(args, ctx)
    except AgentOSError as exc:
        if ctx.json:
            body = {"error": exc.message, "exit_code": exc.exit_code}
            if isinstance(exc, PolicyDenied):
                body["reasons"] = exc.reasons
                body["remedies"] = {r: REMEDY[r] for r in exc.reasons if r in REMEDY}
            print(json.dumps(body), file=sys.stderr)
        else:
            print(f"error: {exc.message}", file=sys.stderr)
            if isinstance(exc, PolicyDenied) and exc.reasons:
                print("reasons: " + ", ".join(exc.reasons), file=sys.stderr)
                for reason in exc.reasons:
                    if remedy := REMEDY.get(reason):
                        print(f"  {reason}: {remedy}", file=sys.stderr)
        return exc.exit_code
    except sqlite3.DatabaseError as exc:
        return _database_error(exc)
    except OSError as exc:
        print(f"error: {exc.strerror or exc} ({exc.filename or 'file'})", file=sys.stderr)
        return 2
    code = 0
    if isinstance(result, tuple):
        result, code = result
    out = json.dumps(result, indent=2, default=str) if ctx.json else _render(result)
    if out:
        print(out)
    return code
