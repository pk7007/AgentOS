"""workforce review | rehab | probation | succession | split | contract | terminate | transfer | transfers.

Managing the workforce on its record: suspend, rehabilitate, plan successors, split heavy work,
contract, stop workers safely and hand unfinished work on."""

from agentos import db, workforce
from agentos.cli import add_project_arg
from agentos.util import load_toml


def register(sub, common) -> None:
    p = sub.add_parser("workforce", help="performance review, rehabilitation, succession, scaling and replacement")
    s = p.add_subparsers(dest="workforce_cmd", metavar="ACTION")
    rv = s.add_parser("review", parents=[common], help="suspend poor performers, flag weak ones, judge probation")
    rv.set_defaults(func=cmd_review)
    rh = s.add_parser("rehab", parents=[common], help="register an improved version and put it on probation")
    rh.add_argument("template")
    rh.add_argument("--file", required=True, help="TOML with the fields that change (instructions, ...)")
    rh.set_defaults(func=cmd_rehab)
    pb = s.add_parser("probation", parents=[common], help="judge a template on probation")
    pb.add_argument("template")
    pb.set_defaults(func=cmd_probation)
    sc = s.add_parser("succession", parents=[common], help="who could take over each template's work")
    add_project_arg(sc)
    sc.set_defaults(func=cmd_succession)
    sp = s.add_parser("split", parents=[common], help="split a heavy task into parallel parts")
    add_project_arg(sp)
    sp.add_argument("task")
    sp.add_argument("--parts", type=int, default=None, help="default: by effort and free slots")
    sp.set_defaults(func=cmd_split)
    ct = s.add_parser("contract", parents=[common], help="archive finished workers, expire specialists, "
                                                         "dissolve empty departments")
    add_project_arg(ct)
    ct.set_defaults(func=cmd_contract)
    tm = s.add_parser("terminate", parents=[common], help="stop a worker safely, keeping what it learned")
    add_project_arg(tm)
    tm.add_argument("instance")
    tm.add_argument("--reason", required=True)
    tm.add_argument("--note", default=None, help="what the next worker should know (saved to memory)")
    tm.set_defaults(func=cmd_terminate)
    tr = s.add_parser("transfer", parents=[common], help="hand a worker's unfinished task to a replacement")
    add_project_arg(tr)
    tr.add_argument("instance")
    tr.add_argument("--host", required=True)
    tr.add_argument("--to", dest="to_template", default=None, help="template (default: best other match)")
    tr.add_argument("--reason", default="transfer")
    tr.add_argument("--note", default=None)
    tr.set_defaults(func=cmd_transfer)
    ts = s.add_parser("transfers", parents=[common], help="transfer history of this project")
    add_project_arg(ts)
    ts.set_defaults(func=cmd_transfers)


def _project(conn, args):
    from agentos.cli import resolve_project

    return resolve_project(conn, getattr(args, "project", None))


def _instance(conn, args):
    from agentos import lifecycle
    from agentos.cli import require_project

    inst = lifecycle.get_instance(conn, args.instance)
    require_project(conn, args, inst.project_id, f"agent {inst.id}")
    return inst


def _run(fn):
    def handler(args, ctx):
        conn = db.require_initialized()
        try:
            return fn(conn, args, ctx)
        finally:
            conn.close()
    return handler


@_run
def cmd_review(conn, args, ctx):
    return workforce.review(conn, ctx.actor)


def cmd_rehab(args, ctx):
    changes = load_toml(args.file)
    conn = db.require_initialized()
    try:
        return workforce.start_rehab(conn, args.template, changes, ctx.actor)
    finally:
        conn.close()


@_run
def cmd_probation(conn, args, ctx):
    return workforce.probation(conn, args.template, ctx.actor)


@_run
def cmd_succession(conn, args, ctx):
    return workforce.succession(conn, _project(conn, args).id)


@_run
def cmd_split(conn, args, ctx):
    from agentos import tasks
    from agentos.cli import require_project

    t = tasks.get_task(conn, args.task)
    require_project(conn, args, t.project_id, f"task {t.id}")
    return workforce.split(conn, t.id, ctx.actor, args.parts)


@_run
def cmd_contract(conn, args, ctx):
    return workforce.contract(conn, _project(conn, args).id, ctx.actor)


@_run
def cmd_terminate(conn, args, ctx):
    return workforce.terminate(conn, _instance(conn, args).id, args.reason, ctx.actor, args.note)


@_run
def cmd_transfer(conn, args, ctx):
    r = workforce.transfer(conn, _instance(conn, args).id, args.host, ctx.actor, args.to_template, args.reason,
                           args.note)
    return (r, 3) if r["status"] != "admitted" else r


@_run
def cmd_transfers(conn, args, ctx):
    return workforce.transfers(conn, _project(conn, args).id)
