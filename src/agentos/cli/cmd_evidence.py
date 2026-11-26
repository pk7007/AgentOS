"""evidence run | show: command results AgentOS observed itself, for grading."""

from agentos import db, evidence


def register(sub, common) -> None:
    from agentos.cli import add_project_arg

    p = sub.add_parser("evidence", help="run a check and record what really happened (for eval record)")
    s = p.add_subparsers(dest="evidence_cmd", metavar="ACTION")
    r = s.add_parser("run", parents=[common],
                     help="run a command (no shell) in the project repo and record exit code and output hashes")
    add_project_arg(r)
    r.add_argument("--timeout", type=int, default=evidence.DEFAULT_TIMEOUT_S, help="seconds (default 900)")
    r.add_argument("argv", nargs="+", metavar="-- COMMAND", help="the command and its arguments, after --")
    r.set_defaults(func=cmd_run)
    sh = s.add_parser("show", parents=[common], help="show one evidence record")
    sh.add_argument("id")
    add_project_arg(sh)
    sh.set_defaults(func=cmd_show)


def cmd_run(args, ctx):
    from agentos.cli import resolve_project

    argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
    conn = db.require_initialized()
    try:
        p = resolve_project(conn, args.project)
        return evidence.run(conn, p.id, argv, ctx.actor, timeout_s=args.timeout).model_dump()
    finally:
        conn.close()


def cmd_show(args, ctx):
    from agentos.cli import resolve_project

    conn = db.require_initialized()
    try:
        return evidence.read(conn, args.id, resolve_project(conn, args.project).id).model_dump()
    finally:
        conn.close()
