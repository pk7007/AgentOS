"""intel staffing | route | context | skills | skill-create | org | failures | compete | governance | forecast |
profile | lessons | share | options | managers | calibration | memory-quality | reuse.

Advice from the ledger: who to staff, which model tier, what context, which proven commands become
skills, where the organisation and its failures cluster, which competing solution won, whether the
core invariants hold, what the remaining work will cost, and which lessons are ready to share."""

from agentos import db, intel


def register(sub, common) -> None:
    p = sub.add_parser("intel", help="staffing, routing, context, skills, failures, governance and forecasts")
    s = p.add_subparsers(dest="intel_cmd", metavar="ACTION")
    from agentos.cli import add_project_arg

    def cmd(name, func, help_, project=True):
        c = s.add_parser(name, parents=[common], help=help_)
        if project:
            add_project_arg(c)
        c.set_defaults(func=func)
        return c

    cmd("staffing", cmd_staffing, "how many workers of which kind the open work needs").add_argument(
        "--objective", default=None)
    r = cmd("route", cmd_route, "the cheapest model tier a task's risk and record justify")
    r.add_argument("task")
    r.add_argument("--template", default=None)
    r.add_argument("--host", default=None, help="check the tiers this host's profile lists and give a fallback")
    c = cmd("context", cmd_context, "the most useful memory for a task within a token budget")
    c.add_argument("task")
    c.add_argument("--budget", type=int, default=800, help="estimated tokens (default 800)")
    c.add_argument("--record", action="store_true", help="count the included records as used")
    cmd("skills", cmd_skills, "commands proven often enough to become a skill").add_argument(
        "--min-uses", type=int, default=3)
    sc = cmd("skill-create", cmd_skill_create, "write a SKILL.md for a proven command")
    sc.add_argument("evidence", help="an evidence id of the command, from `intel skills`")
    sc.add_argument("--name", default=None)
    sc.add_argument("--min-uses", type=int, default=3)
    cmd("org", cmd_org, "idle and overlapping templates, single points of failure, idle departments").add_argument(
        "--idle-days", type=int, default=30)
    f = cmd("failures", cmd_failures, "recurring failures: error signatures, weak dimensions, failing capabilities")
    f.add_argument("--min-count", type=int, default=2)
    f.add_argument("--record", action="store_true", help="save each pattern as failure memory")
    cp = cmd("compete", cmd_compete, "rank competing solutions to one task by independent evaluations")
    cp.add_argument("task")
    cp.add_argument("--min-margin", type=float, default=2.0)
    cmd("governance", cmd_governance, "re-check the core invariants from the raw ledger (exit 5 on a violation)",
        project=False)
    cmd("forecast", cmd_forecast, "agent runs, tokens and time the open work will need").add_argument(
        "--objective", default=None)
    cmd("profile", cmd_profile, "what this project's history says")
    cmd("lessons", cmd_lessons, "validated lessons several projects reached, ready to share", project=False
        ).add_argument("--min-projects", type=int, default=2)
    sh = cmd("share", cmd_share, "share a lesson across projects once enough projects validated it", project=False)
    sh.add_argument("memory")
    sh.add_argument("--min-projects", type=int, default=2)
    cmd("options", cmd_options, "candidate templates for a task: expected score, interval, cost, risks").add_argument(
        "task")
    cmd("managers", cmd_managers, "how well each lead's team did, from independent evaluations")
    cal = cmd("calibration", cmd_calibration, "evaluators that grade far from the others on the same work")
    cal.add_argument("--min-shared", type=int, default=2)
    cal.add_argument("--max-bias", type=float, default=15.0)
    cmd("memory-quality", cmd_memory_quality, "score memory records and list the weakest")
    cmd("reuse", cmd_reuse, "how much learned memory is used again")


def _run(fn):
    def handler(args, ctx):
        conn = db.require_initialized()
        try:
            return fn(conn, args, ctx)
        finally:
            conn.close()
    return handler


def _pid(conn, args) -> str:
    from agentos.cli import resolve_project

    return resolve_project(conn, getattr(args, "project", None)).id


def _task(conn, args):
    from agentos import tasks
    from agentos.cli import require_project

    t = tasks.get_task(conn, args.task)
    require_project(conn, args, t.project_id, f"task {t.id}")
    return t


@_run
def cmd_staffing(conn, args, ctx):
    return intel.staffing(conn, _pid(conn, args), args.objective)


@_run
def cmd_route(conn, args, ctx):
    return intel.route(conn, _task(conn, args).id, args.template, intel.host_tiers(args.host))


@_run
def cmd_context(conn, args, ctx):
    return intel.context_pack(conn, _task(conn, args).id, args.budget, ctx.actor if args.record else None)


@_run
def cmd_skills(conn, args, ctx):
    return intel.skill_candidates(conn, _pid(conn, args), args.min_uses)


@_run
def cmd_skill_create(conn, args, ctx):
    return intel.create_skill(conn, _pid(conn, args), args.evidence, ctx.actor, args.name, args.min_uses)


@_run
def cmd_org(conn, args, ctx):
    return intel.org_review(conn, _pid(conn, args), args.idle_days)


@_run
def cmd_failures(conn, args, ctx):
    return intel.failure_patterns(conn, _pid(conn, args), args.min_count, ctx.actor, args.record)


@_run
def cmd_compete(conn, args, ctx):
    return intel.compete(conn, _task(conn, args).id, args.min_margin)


@_run
def cmd_governance(conn, args, ctx):
    r = intel.governance_check(conn)
    return r if r["ok"] else (r, 5)


@_run
def cmd_forecast(conn, args, ctx):
    return intel.forecast(conn, _pid(conn, args), args.objective)


@_run
def cmd_profile(conn, args, ctx):
    return intel.project_profile(conn, _pid(conn, args))


@_run
def cmd_lessons(conn, args, ctx):
    return intel.lessons(conn, args.min_projects)


@_run
def cmd_share(conn, args, ctx):
    return intel.share_lesson(conn, args.memory, ctx.actor, args.min_projects)


@_run
def cmd_managers(conn, args, ctx):
    return intel.managers(conn, _pid(conn, args))


@_run
def cmd_calibration(conn, args, ctx):
    return intel.calibration(conn, _pid(conn, args), args.min_shared, args.max_bias)


@_run
def cmd_memory_quality(conn, args, ctx):
    return intel.memory_quality(conn, _pid(conn, args))


@_run
def cmd_reuse(conn, args, ctx):
    return intel.reuse(conn, _pid(conn, args))


@_run
def cmd_options(conn, args, ctx):
    return intel.options(conn, _task(conn, args).id)
