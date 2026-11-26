"""`agentos` command-line entry point.

Each command group lives in a `cmd_*.py` module exposing `register(subparsers, common)`.
Handlers have the signature `func(args, ctx) -> data | (data, exit_code)`.
"""

import argparse
import importlib
import json
import os
import sys
from dataclasses import dataclass

from agentos import __version__
from agentos.errors import AgentOSError, PolicyDenied

COMMAND_MODULES: tuple[str, ...] = ("cmd_system", "cmd_audit", "cmd_project", "cmd_task", "cmd_template", "cmd_agent", "cmd_budget", "cmd_governance", "cmd_perf", "cmd_memory", "cmd_handover", "cmd_gen", "cmd_evidence", "cmd_hook")


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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
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
            print(json.dumps(body), file=sys.stderr)
        else:
            print(f"error: {exc.message}", file=sys.stderr)
            if isinstance(exc, PolicyDenied) and exc.reasons:
                print("reasons: " + ", ".join(exc.reasons), file=sys.stderr)
        return exc.exit_code
    code = 0
    if isinstance(result, tuple):
        result, code = result
    out = json.dumps(result, indent=2, default=str) if ctx.json else _render(result)
    if out:
        print(out)
    return code
