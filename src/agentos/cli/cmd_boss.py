"""boss start | plan | next | bottlenecks | review | accept | recover | deliver | list | show.

The Boss Agent's ledger for one objective. The host's lead agent thinks; these commands check its
plan, schedule it, find bottlenecks, gate quality and gate delivery."""

import json
import sys
from pathlib import Path

from agentos import boss, db
from agentos.cli import add_project_arg
from agentos.errors import UsageError

COMPLEXITY_FLAGS = [("--tasks", "task_count"), ("--depth", "dependency_depth"), ("--workstreams", "workstreams"),
                    ("--files", "files_touched"), ("--difficulty", "domain_difficulty"),
                    ("--uncertainty", "uncertainty"), ("--risk", "risk"), ("--verify", "verification_effort")]


def register(sub, common) -> None:
    p = sub.add_parser("boss", help="run one objective end to end: plan, schedule, quality and delivery")
    s = p.add_subparsers(dest="boss_cmd", metavar="ACTION")
    st = s.add_parser("start", parents=[common], help="record an objective with testable acceptance criteria")
    add_project_arg(st)
    st.add_argument("title")
    st.add_argument("--statement", default="", help="what done means, in a sentence or two")
    st.add_argument("--accept", action="append", default=[], help="an acceptance criterion (repeat)")
    for flag, dest in COMPLEXITY_FLAGS:
        st.add_argument(flag, dest=dest, type=int, default=None, help="complexity factor (give all 8 or none)")
    st.set_defaults(func=cmd_start)
    pl = s.add_parser("plan", parents=[common], help="apply a decomposition plan (JSON) to an objective")
    add_project_arg(pl)
    pl.add_argument("objective")
    pl.add_argument("--file", required=True, help="plan JSON file, or - for stdin")
    pl.set_defaults(func=cmd_plan)
    for name, helptext, func in (("next", "what to start now, by critical path", cmd_next),
                                 ("bottlenecks", "what is holding the objective up", cmd_bottlenecks),
                                 ("review", "the nine executive checks", cmd_review),
                                 ("show", "the objective, its tasks and delivery report", cmd_show)):
        x = s.add_parser(name, parents=[common], help=helptext)
        add_project_arg(x)
        x.add_argument("objective")
        x.set_defaults(func=func)
    ac = s.add_parser("accept", parents=[common], help="accept a done task on an independent, passing evaluation")
    add_project_arg(ac)
    ac.add_argument("task")
    ac.add_argument("--eval", dest="evaluation", required=True, help="evaluation id (ev_...)")
    ac.add_argument("--min-score", type=float, default=boss.DEFAULT_MIN_SCORE)
    ac.set_defaults(func=cmd_accept)
    rc = s.add_parser("recover", parents=[common], help="retry a failed task with another template, or escalate")
    add_project_arg(rc)
    rc.add_argument("task")
    rc.set_defaults(func=cmd_recover)
    dv = s.add_parser("deliver", parents=[common], help="close the objective once everything is accepted")
    add_project_arg(dv)
    dv.add_argument("objective")
    dv.add_argument("--criterion", action="append", default=[], metavar="N=EVD",
                    help="criterion index and the evd_ id proving it (repeat)")
    dv.set_defaults(func=cmd_deliver)
    ls = s.add_parser("list", parents=[common], help="objectives of this project")
    add_project_arg(ls)
    ls.set_defaults(func=cmd_list)


def _conn_project(args):
    from agentos.cli import resolve_project

    conn = db.require_initialized()
    return conn, resolve_project(conn, getattr(args, "project", None))


def _objective(conn, args):
    from agentos.cli import require_project

    obj = boss.get_objective(conn, args.objective)
    require_project(conn, args, obj.project_id, f"objective {obj.id}")
    return obj


def _task(conn, args):
    from agentos import tasks
    from agentos.cli import require_project

    t = tasks.get_task(conn, args.task)
    require_project(conn, args, t.project_id, f"task {t.id}")
    return t


def cmd_start(args, ctx):
    given = {dest: getattr(args, dest) for _, dest in COMPLEXITY_FLAGS}
    if any(v is not None for v in given.values()) and any(v is None for v in given.values()):
        raise UsageError("give all eight complexity factors or none: "
                         + " ".join(flag for flag, _ in COMPLEXITY_FLAGS))
    complexity = given if all(v is not None for v in given.values()) else None
    conn, proj = _conn_project(args)
    try:
        return boss.create_objective(conn, proj.id, args.title, args.statement, args.accept, complexity,
                                     ctx.actor).model_dump()
    finally:
        conn.close()


def _read_plan(path: str) -> dict:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8-sig")
        return json.loads(text)
    except (OSError, ValueError) as exc:
        raise UsageError(f"cannot read plan {path}: {exc}") from exc


def cmd_plan(args, ctx):
    plan = _read_plan(args.file)
    conn = db.require_initialized()
    try:
        return boss.apply_plan(conn, _objective(conn, args).id, plan, ctx.actor)
    finally:
        conn.close()


def _with_objective(fn):
    def run(args, ctx):
        conn = db.require_initialized()
        try:
            return fn(conn, _objective(conn, args).id)
        finally:
            conn.close()
    return run


cmd_next = _with_objective(boss.schedule)
cmd_bottlenecks = _with_objective(boss.bottlenecks)
cmd_review = _with_objective(boss.review)


def cmd_show(args, ctx):
    from agentos import tasks

    conn = db.require_initialized()
    try:
        obj = _objective(conn, args)
        rows = [tasks.get_task(conn, t).model_dump(mode="json", include={"id", "title", "state", "deps", "risk"})
                for t in boss.objective_tasks(conn, obj.id)]
        return {"objective": obj.model_dump(), "departments": boss.departments(conn, obj.id), "tasks": rows,
                "report": boss.delivery_report(conn, obj.id)}
    finally:
        conn.close()


def cmd_accept(args, ctx):
    conn = db.require_initialized()
    try:
        return boss.accept_task(conn, _task(conn, args).id, args.evaluation, ctx.actor, args.min_score)
    finally:
        conn.close()


def cmd_recover(args, ctx):
    conn = db.require_initialized()
    try:
        return boss.recover(conn, _task(conn, args).id, ctx.actor)
    finally:
        conn.close()


def cmd_deliver(args, ctx):
    mapping = {}
    for item in args.criterion:
        idx, sep, evd = item.partition("=")
        if not sep or not evd.strip():
            raise UsageError(f"--criterion takes N=EVD, got {item!r}")
        mapping[idx.strip()] = evd.strip()
    conn = db.require_initialized()
    try:
        return boss.deliver(conn, _objective(conn, args).id, mapping, ctx.actor)
    finally:
        conn.close()


def cmd_list(args, ctx):
    conn, proj = _conn_project(args)
    try:
        return [o.model_dump(include={"id", "title", "state", "complexity_band", "created_at"})
                for o in boss.list_objectives(conn, proj.id)]
    finally:
        conn.close()
