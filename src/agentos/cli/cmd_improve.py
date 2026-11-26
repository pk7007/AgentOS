"""improve retro | case | cases | propose | trial | check | score | gate | status | decide | abandon |
monitor | experiments | show | policies.

The self-improvement loop: learn from finished work, then test a change against the current
champion on fixed benchmark cases before it can replace anything."""

from agentos import db, evidence, improve
from agentos.cli import add_project_arg
from agentos.errors import UsageError
from agentos.util import load_toml


def register(sub, common) -> None:
    p = sub.add_parser("improve", help="retrospectives and champion-versus-challenger experiments")
    s = p.add_subparsers(dest="improve_cmd", metavar="ACTION")

    r = s.add_parser("retro", parents=[common], help="collect outcomes, diagnose weaknesses, propose hypotheses")
    add_project_arg(r)
    g = r.add_mutually_exclusive_group()
    g.add_argument("--task", default=None, help="one task (and its subtasks)")
    g.add_argument("--objective", default=None, help="one objective")
    g.add_argument("--show", default=None, metavar="RETRO", help="show a stored retrospective")
    r.set_defaults(func=cmd_retro)

    c = s.add_parser("case", parents=[common], help="add a benchmark case (fixed before experiments use it)")
    add_project_arg(c)
    c.add_argument("--suite", required=True)
    c.add_argument("--title", required=True)
    c.add_argument("--split", required=True, choices=improve.SPLITS)
    c.add_argument("--cap", action="append", default=[], help="required capability (repeatable)")
    c.add_argument("--accept", action="append", default=[], help="acceptance criterion (repeatable)")
    c.add_argument("argv", nargs="+", metavar="-- COMMAND", help="the check command AgentOS runs, after --")
    c.set_defaults(func=cmd_case)

    cs = s.add_parser("cases", parents=[common], help="list cases (held-out cases by id and hash only)")
    add_project_arg(cs)
    cs.add_argument("--suite", default=None)
    cs.set_defaults(func=cmd_cases)

    pr = s.add_parser("propose", parents=[common], help="start an experiment with an isolated challenger")
    add_project_arg(pr)
    pr.add_argument("--suite", required=True)
    pr.add_argument("--hypothesis", default="", help="what should improve, and why")
    what = pr.add_mutually_exclusive_group(required=True)
    what.add_argument("--template", default=None, help="champion template (with --file)")
    what.add_argument("--policy", default=None, help="tunable policy name (with --value)")
    what.add_argument("--from-retro", dest="retro", default=None, metavar="RETRO", help="use a retro hypothesis")
    pr.add_argument("--file", default=None, help="TOML: instructions, description, reasoning_hint, model_hint")
    pr.add_argument("--value", type=float, default=None)
    pr.add_argument("--index", type=int, default=0, help="hypothesis number in the retro (default 0)")
    pr.set_defaults(func=cmd_propose)

    t = s.add_parser("trial", parents=[common], help="run one arm on one case: creates and admits the trial")
    add_project_arg(t)
    t.add_argument("experiment")
    t.add_argument("case")
    t.add_argument("--arm", required=True, choices=("champion", "challenger"))
    t.add_argument("--host", required=True)
    t.set_defaults(func=cmd_trial)

    ck = s.add_parser("check", parents=[common], help="run the case's check command for a trial")
    add_project_arg(ck)
    ck.add_argument("trial")
    ck.add_argument("--timeout", type=int, default=evidence.DEFAULT_TIMEOUT_S)
    ck.set_defaults(func=cmd_check)

    sc = s.add_parser("score", parents=[common], help="attach an independent evaluation to a trial")
    add_project_arg(sc)
    sc.add_argument("trial")
    sc.add_argument("evaluation")
    sc.set_defaults(func=cmd_score)

    gt = s.add_parser("gate", parents=[common], help="run the regression and security checks")
    add_project_arg(gt)
    gt.add_argument("experiment")
    gt.add_argument("--timeout", type=int, default=evidence.DEFAULT_TIMEOUT_S)
    gt.add_argument("argv", nargs="+", metavar="-- COMMAND", help="the check command, after --")
    gt.set_defaults(func=cmd_gate)

    for name, fn, text in (("status", cmd_status, "the comparison so far, without deciding"),
                           ("decide", cmd_decide, "promote or reject on the evidence"),
                           ("show", cmd_show, "an experiment and its (blind) trials")):
        x = s.add_parser(name, parents=[common], help=text)
        add_project_arg(x)
        x.add_argument("experiment")
        x.set_defaults(func=fn)

    ab = s.add_parser("abandon", parents=[common], help="stop an experiment without a decision")
    add_project_arg(ab)
    ab.add_argument("experiment")
    ab.add_argument("--reason", required=True)
    ab.set_defaults(func=cmd_abandon)

    mo = s.add_parser("monitor", parents=[common], help="check promoted changes; roll back regressions")
    add_project_arg(mo)
    mo.set_defaults(func=cmd_monitor)

    ex = s.add_parser("experiments", parents=[common], help="experiments of this project")
    add_project_arg(ex)
    ex.add_argument("--status", default=None)
    ex.set_defaults(func=cmd_experiments)

    po = s.add_parser("policies", parents=[common], help="the tunable policies, their bounds and values")
    po.set_defaults(func=cmd_policies)


def _argv(args) -> list[str]:
    return args.argv[1:] if args.argv[:1] == ["--"] else args.argv


def _project(conn, args):
    from agentos.cli import resolve_project

    return resolve_project(conn, getattr(args, "project", None))


def _experiment(conn, args, experiment_id=None):
    from agentos.cli import require_project

    exp = improve.get_experiment(conn, experiment_id or args.experiment)
    require_project(conn, args, exp.project_id, f"experiment {exp.id}")
    return exp


def _trial_experiment(conn, args):
    return _experiment(conn, args, improve._trial(conn, args.trial)["experiment_id"])


def _run(fn):
    def handler(args, ctx):
        conn = db.require_initialized()
        try:
            return fn(conn, args, ctx)
        finally:
            conn.close()
    return handler


@_run
def cmd_retro(conn, args, ctx):
    if args.show:
        from agentos.cli import require_project

        r = improve.get_retro(conn, args.show)
        require_project(conn, args, r["project_id"], f"retrospective {r['id']}")
        return r
    return improve.retro(conn, _project(conn, args).id, ctx.actor, task_id=args.task, objective_id=args.objective)


@_run
def cmd_case(conn, args, ctx):
    return improve.add_case(conn, _project(conn, args).id, args.suite, args.title, _argv(args), args.split,
                            ctx.actor, capabilities=args.cap, acceptance=args.accept)


@_run
def cmd_cases(conn, args, ctx):
    return improve.list_cases(conn, _project(conn, args).id, args.suite)


@_run
def cmd_propose(conn, args, ctx):
    pid = _project(conn, args).id
    if args.retro:
        from agentos.cli import require_project

        require_project(conn, args, improve.get_retro(conn, args.retro)["project_id"], f"retrospective {args.retro}")
        exp = improve.propose_from_retro(conn, args.retro, args.index, args.suite, ctx.actor)
    elif args.template:
        if not args.file:
            raise UsageError("--template needs --file with the fields that change")
        exp = improve.propose_template(conn, pid, args.template, load_toml(args.file), args.hypothesis, args.suite,
                                       ctx.actor)
    else:
        if args.value is None:
            raise UsageError("--policy needs --value")
        exp = improve.propose_policy(conn, pid, args.policy, args.value, args.hypothesis, args.suite, ctx.actor)
    return exp.model_dump()


@_run
def cmd_trial(conn, args, ctx):
    exp = _experiment(conn, args)
    r = improve.start_trial(conn, exp.id, args.case, args.arm, args.host, ctx.actor)
    return (r, 3) if r["status"] != "admitted" else r


@_run
def cmd_check(conn, args, ctx):
    _trial_experiment(conn, args)
    return improve.check_trial(conn, args.trial, ctx.actor, args.timeout).model_dump()


@_run
def cmd_score(conn, args, ctx):
    _trial_experiment(conn, args)
    return improve.score_trial(conn, args.trial, args.evaluation, ctx.actor)


@_run
def cmd_gate(conn, args, ctx):
    exp = _experiment(conn, args)
    ev = improve.gate(conn, exp.id, _argv(args), ctx.actor, args.timeout)
    out = ev.model_dump()
    return (out, 3) if ev.exit_code != 0 or ev.timed_out else out


@_run
def cmd_status(conn, args, ctx):
    return improve.evaluate(conn, _experiment(conn, args).id)


@_run
def cmd_decide(conn, args, ctx):
    return improve.decide(conn, _experiment(conn, args).id, ctx.actor)


@_run
def cmd_show(conn, args, ctx):
    exp = _experiment(conn, args)
    return exp.model_dump() | {"trials": improve.trials_of(conn, exp.id)}


@_run
def cmd_abandon(conn, args, ctx):
    return improve.abandon(conn, _experiment(conn, args).id, ctx.actor, args.reason).model_dump()


@_run
def cmd_monitor(conn, args, ctx):
    return improve.monitor(conn, ctx.actor, _project(conn, args).id)


@_run
def cmd_experiments(conn, args, ctx):
    return [{"id": e.id, "kind": e.kind, "target": e.target, "suite": e.suite, "status": e.status,
             "hypothesis": e.hypothesis, "created_at": e.created_at}
            for e in improve.list_experiments(conn, _project(conn, args).id, args.status)]


@_run
def cmd_policies(conn, args, ctx):
    return improve.policies(conn)
