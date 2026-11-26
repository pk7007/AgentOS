"""host list | install | drift | rollback | uninstall | bootstrap | check | history.

Native host adapters: install the generated plugin, keep it in sync with the definitions, undo an
update, write the project bootstrap block and check coexistence with other plugins."""

from pathlib import Path

from agentos import adapters, db
from agentos.cli import add_project_arg


def register(sub, common) -> None:
    p = sub.add_parser("host", help="install, update, check and roll back host plugins")
    s = p.add_subparsers(dest="host_cmd", metavar="ACTION")

    def host_parser(name, help_text, func, profile=True):
        x = s.add_parser(name, parents=[common], help=help_text)
        x.add_argument("host", help="codex or cc")
        if profile:
            x.add_argument("--profile", type=Path, default=None,
                           help="host profile (default: ~/.agentos/hosts/HOST.toml)")
        x.set_defaults(func=func)
        return x

    ls = s.add_parser("list", parents=[common], help="known hosts, capabilities, versions and installs")
    ls.set_defaults(func=cmd_list)
    i = host_parser("install", "generate the plugin and install it (the previous install is backed up)", cmd_install)
    i.add_argument("--dest", type=Path, default=None, help="folder (default: ~/.agentos/plugins/HOST)")
    host_parser("drift", "hand edits, stale files and host CLI changes since the install", cmd_drift)
    host_parser("rollback", "restore the previous install", cmd_rollback, profile=False)
    u = host_parser("uninstall", "remove the installed files (hand-edited files are kept)", cmd_uninstall,
                    profile=False)
    u.add_argument("--force", action="store_true", help="also remove files you edited")
    b = host_parser("bootstrap", "add a short AgentOS block to this project's instructions file", cmd_bootstrap)
    add_project_arg(b)
    b.add_argument("--remove", action="store_true", help="remove the block again")
    host_parser("check", "coexistence with other plugins: shared hooks, same names, duplicate installs", cmd_check)
    h = s.add_parser("history", parents=[common], help="every install, update and rollback")
    h.add_argument("host", nargs="?", default=None)
    h.set_defaults(func=cmd_history)


def _run(fn):
    def handler(args, ctx):
        conn = db.require_initialized()
        try:
            return fn(conn, args, ctx)
        finally:
            conn.close()
    return handler


@_run
def cmd_list(conn, args, ctx):
    return adapters.status(conn)


@_run
def cmd_install(conn, args, ctx):
    return adapters.install(conn, args.host, ctx.actor, args.dest, args.profile)


@_run
def cmd_drift(conn, args, ctx):
    r = adapters.drift(conn, args.host, args.profile)
    return (r, 3) if r["status"] != "in_sync" else r


@_run
def cmd_rollback(conn, args, ctx):
    return adapters.rollback(conn, args.host, ctx.actor)


@_run
def cmd_uninstall(conn, args, ctx):
    return adapters.uninstall(conn, args.host, ctx.actor, args.force)


@_run
def cmd_bootstrap(conn, args, ctx):
    from agentos.cli import resolve_project

    project = resolve_project(conn, args.project)
    return adapters.bootstrap(conn, Path(project.path), args.host, ctx.actor, args.remove, args.profile)


def cmd_check(args, ctx):
    r = adapters.check(args.host, args.profile)
    return (r, 3) if r["verdict"] == "conflict" else r


@_run
def cmd_history(conn, args, ctx):
    return adapters.history(conn, args.host)
