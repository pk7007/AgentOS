"""hook run | bindings | config: the runtime side of admission (called by the host's own hooks)."""

import json
import sys

from agentos import db, paths, runtime
from agentos.cli import add_project_arg


def register(sub, common) -> None:
    p = sub.add_parser("hook", help="runtime hooks: gate subagent spawns at the host runtime")
    s = p.add_subparsers(dest="hook_cmd", metavar="ACTION")
    r = s.add_parser("run", parents=[common],
                     help="handle one hook event: JSON on stdin, the host's hook JSON on stdout")
    r.add_argument("host", help="codex or cc")
    r.set_defaults(func=cmd_run)
    b = s.add_parser("bindings", parents=[common], help="list which native subagent runs which instance")
    add_project_arg(b)
    b.add_argument("--all", action="store_true", help="every project")
    b.set_defaults(func=cmd_bindings)
    c = s.add_parser("config", parents=[common], help="print the hooks file for a host")
    c.add_argument("host", help="codex or cc")
    c.add_argument("--guard-tools", action="store_true",
                   help="also check every tool call (denies calls of cancelled workers; slower)")
    c.add_argument("--executable", default="agentos", help="command the runtime should run")
    c.set_defaults(func=cmd_config)


def cmd_run(args, ctx):
    """Always exits 0 (the host treats other codes as a hook failure); the decision is in the JSON."""
    runtime.profile(args.host)
    # Read bytes: on Windows a piped text stdin uses the locale code page, not the UTF-8 hosts send.
    buf = getattr(sys.stdin, "buffer", None)
    raw = buf.read().decode("utf-8", errors="replace") if buf else sys.stdin.read()
    try:
        event = json.loads(raw.lstrip("\ufeff"))
    except ValueError as exc:
        event, problem = None, str(exc)
    else:
        problem = None if isinstance(event, dict) else "expected a JSON object"
    if problem:
        print(f"agentos hook: not valid hook JSON: {problem}", file=sys.stderr)
        return None
    if not paths.db_path().exists():
        return None
    try:
        conn = db.require_initialized()
        try:
            result = runtime.handle(conn, args.host, event)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - any failure must still produce a safe answer
        print(f"agentos hook: {type(exc).__name__}: {exc}", file=sys.stderr)
        result = runtime.failure_result(args.host, event, f"{type(exc).__name__}: {exc}")
    return json.dumps(result.output) if result.output else None


def cmd_bindings(args, ctx):
    from agentos.cli import resolve_project

    conn = db.require_initialized()
    try:
        pid = None if args.all else resolve_project(conn, args.project).id
        return runtime.list_bindings(conn, pid)
    finally:
        conn.close()


def cmd_config(args, ctx):
    return json.dumps(runtime.hooks_config(args.host, args.guard_tools, args.executable), indent=2)
