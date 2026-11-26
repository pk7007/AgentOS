"""Self-improvement engine: retrospectives, diagnoses, hypotheses and champion-versus-challenger
experiments with promotion, monitoring and rollback.

AgentOS never calls a model, so it cannot invent a better prompt by itself. It proposes concrete,
rule-based challengers from what the record shows (the host may write its own), and it is strict
about how a challenger earns promotion:

- the challenger is an isolated candidate: a separate template admission accepts only on that
  experiment's own trial tasks, or a bounded policy value used only to staff those trials;
- benchmark cases are fixed before the experiment starts; held-out cases are hidden from
  listings, a challenger whose text copies one is refused, and a held-out case already used by an
  earlier experiment no longer counts as held out;
- every trial is graded by an evaluator of neither arm's template, citing the evidence AgentOS
  recorded by running that case's own check command; abandoned trials count as failures;
- promotion needs enough paired cases, a passing regression/security gate, a margin on the
  representative cases, no loss on the held-out cases, no lower pass rate and no flags;
- after promotion the new champion is monitored and rolled back if it falls below its baseline.

Only instructions, description and model or reasoning hints of a template, and the policies in
`agentos.policy`, can change. Permissions, security class, delegation, ownership, approvals and
hard limits cannot be reached by an experiment at all."""

import hashlib
import json
import re
import sqlite3
import statistics

from pydantic import BaseModel

from agentos import (
    audit,
    evidence,
    factory,
    lifecycle,
    memory,
    performance,
    policy,
    recruit,
    tasks,
    templates,
)
from agentos.db import get_setting, put_setting, write_tx
from agentos.errors import NotFound, PolicyDenied, UsageError
from agentos.lifecycle import AgentState
from agentos.templates import AgentTemplate, TemplateStatus
from agentos.util import new_id, now_iso, sha256_json

GUIDANCE = {
    "quality": "Before you report, re-read your change as a reviewer would and fix what you would flag.",
    "accuracy": "Check every claim against the code or a command's output before you report it.",
    "reliability": "Run the task's check command yourself before you say the task is done, and say what it printed.",
    "instruction_compliance": "Re-read the task's acceptance criteria before you finish and confirm each one.",
    "security_compliance": "Never weaken a check, widen a permission or print a secret; if the task seems to need "
                           "that, stop and report.",
    "cost_efficiency": "Use the smallest change and the fewest steps that meet the acceptance criteria.",
    "speed": "Start with the most direct approach and report blockers early instead of searching widely.",
    "collaboration": "Leave a short note of what you did and what is left, so the next worker can continue.",
}
TEMPLATE_FIELDS = {"instructions", "description", "reasoning_hint", "model_hint"}
SPLITS = ("representative", "heldout")
WEAK_SUBSCORE = 70.0
WEAK_MIN_EVALS = 3
RECURRING = 3
MIN_REPRESENTATIVE = 3
MIN_HELDOUT = 2
MARGIN = 2.0
MONITOR_N = 5
ROLLBACK_MARGIN = 5.0
LEAK_NGRAM = 6
TERMINAL = {AgentState.FAILED, AgentState.CANCELLED, AgentState.TERMINATED, AgentState.ARCHIVED,
            AgentState.QUARANTINED, AgentState.SUSPENDED}


# --- benchmark cases ----------------------------------------------------------------------------

def add_case(conn: sqlite3.Connection, project_id: str, suite: str, title: str, check_command: list[str],
             split: str, actor: str, capabilities: list[str] | None = None,
             acceptance: list[str] | None = None) -> dict:
    from agentos.projects import require_active

    require_active(conn, project_id)
    if split not in SPLITS:
        raise UsageError(f"split must be one of {', '.join(SPLITS)}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,40}", suite or ""):
        raise UsageError("suite must be a short lowercase name")
    if not title.strip() or not check_command or not check_command[0].strip():
        raise UsageError("a case needs a title and a check command (the command AgentOS runs to check it)")
    caps, accept = factory.norm_caps(capabilities), [str(a) for a in (acceptance or [])]
    digest = sha256_json({"title": title, "capabilities": caps, "acceptance": accept, "command": check_command})
    if conn.execute("SELECT 1 FROM benchmark_cases WHERE project_id=? AND suite=? AND content_hash=?",
                    (project_id, suite, digest)).fetchone():
        raise PolicyDenied("this case is already in the suite", reasons=["duplicate_case"])
    cid = new_id("case")
    with write_tx(conn):
        conn.execute("INSERT INTO benchmark_cases(id, project_id, suite, title, capabilities, acceptance, check_command,"
                     " split, content_hash, created_at, actor) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (cid, project_id, suite, title, json.dumps(caps), json.dumps(accept), json.dumps(check_command),
                      split, digest, now_iso(), actor))
        # The audit records the hash, never the content, so held-out cases stay hidden there too.
        audit.append_event(conn, "improve.case_added", actor,
                           {"case_id": cid, "suite": suite, "split": split, "content_hash": digest}, project_id)
    return _case_view(_case(conn, cid))


def _case(conn, case_id: str):
    row = conn.execute("SELECT * FROM benchmark_cases WHERE id=?", (case_id,)).fetchone()
    if not row:
        raise NotFound(f"benchmark case not found: {case_id}")
    return row


def _case_view(row) -> dict:
    view = {"id": row["id"], "suite": row["suite"], "split": row["split"], "content_hash": row["content_hash"],
            "created_at": row["created_at"]}
    if row["split"] == "representative":
        view |= {"title": row["title"], "capabilities": json.loads(row["capabilities"]),
                 "acceptance": json.loads(row["acceptance"]), "check_command": json.loads(row["check_command"])}
    return view


def list_cases(conn: sqlite3.Connection, project_id: str, suite: str | None = None) -> list[dict]:
    """Held-out cases are listed by id and hash only."""
    sql, params = "SELECT * FROM benchmark_cases WHERE project_id=?", [project_id]
    if suite:
        sql += " AND suite=?"
        params.append(suite)
    return [_case_view(r) for r in conn.execute(sql + " ORDER BY created_at, rowid", params)]


def _exposed(conn, case_id: str, experiment_id: str | None) -> bool:
    """A held-out case seen in another experiment's trials is no longer held out."""
    return conn.execute("SELECT 1 FROM trials WHERE case_id=? AND experiment_id IS NOT ?",
                        (case_id, experiment_id)).fetchone() is not None


def _suite(conn, project_id: str, suite: str) -> list:
    return list(conn.execute("SELECT * FROM benchmark_cases WHERE project_id=? AND suite=?"
                             " ORDER BY created_at, rowid", (project_id, suite)))


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def _ngrams(text: str) -> set[str]:
    w = _words(text)
    return {" ".join(w[i:i + LEAK_NGRAM]) for i in range(len(w) - LEAK_NGRAM + 1)}


def _leaks(conn, project_id: str, suite: str, text: str) -> list[str]:
    grams, flat = _ngrams(text), " ".join(_words(text))
    out = []
    for c in _suite(conn, project_id, suite):
        if c["split"] != "heldout":
            continue
        case_text = " ".join([c["title"], *json.loads(c["acceptance"]), *json.loads(c["check_command"])])
        title = " ".join(_words(c["title"]))
        if _ngrams(case_text) & grams or (len(title) >= 12 and title in flat):
            out.append(c["id"])
    return out


# --- experiments --------------------------------------------------------------------------------

class Experiment(BaseModel):
    id: str
    project_id: str
    kind: str
    target: str
    suite: str
    hypothesis: str
    champion: dict
    challenger: dict
    challenger_template: str | None
    status: str
    gate_evidence: list[str]
    result: dict | None
    monitor: dict | None
    created_at: str
    decided_at: str | None
    actor: str


def _exp_row(row) -> Experiment:
    d = dict(row)
    for k in ("champion", "challenger", "gate_evidence"):
        d[k] = json.loads(d[k])
    for k in ("result", "monitor"):
        d[k] = json.loads(d[k]) if d[k] else None
    return Experiment(**d)


def get_experiment(conn: sqlite3.Connection, experiment_id: str) -> Experiment:
    row = conn.execute("SELECT * FROM experiments WHERE id=?", (experiment_id,)).fetchone()
    if not row:
        raise NotFound(f"experiment not found: {experiment_id}")
    return _exp_row(row)


def list_experiments(conn: sqlite3.Connection, project_id: str | None = None,
                     status: str | None = None) -> list[Experiment]:
    sql, params = "SELECT * FROM experiments WHERE 1=1", []
    if project_id:
        sql += " AND project_id=?"
        params.append(project_id)
    if status:
        sql += " AND status=?"
        params.append(status)
    return [_exp_row(r) for r in conn.execute(sql + " ORDER BY created_at, rowid", params)]


def _ready_suite(conn, project_id: str, suite: str) -> None:
    rows = _suite(conn, project_id, suite)
    rep = sum(1 for r in rows if r["split"] == "representative")
    held = sum(1 for r in rows if r["split"] == "heldout" and not _exposed(conn, r["id"], None))
    if rep < MIN_REPRESENTATIVE or held < MIN_HELDOUT:
        raise PolicyDenied(f"suite {suite!r} needs {MIN_REPRESENTATIVE} representative and {MIN_HELDOUT} unused "
                           f"held-out cases (has {rep} and {held})", reasons=["not_enough_cases"])


def _no_open(conn, kind: str, target: str) -> None:
    if conn.execute("SELECT 1 FROM experiments WHERE kind=? AND target=? AND status='trialing'",
                    (kind, target)).fetchone():
        raise PolicyDenied(f"an experiment on {target} is already running", reasons=["experiment_open"])


def _insert(conn, project_id, kind, target, suite, hypothesis, champion, challenger, cand, actor) -> str:
    eid = new_id("exp")
    conn.execute("INSERT INTO experiments(id, project_id, kind, target, suite, hypothesis, champion, challenger,"
                 " challenger_template, status, created_at, actor) VALUES (?,?,?,?,?,?,?,?,?,'trialing',?,?)",
                 (eid, project_id, kind, target, suite, hypothesis, json.dumps(champion), json.dumps(challenger),
                  cand, now_iso(), actor))
    audit.append_event(conn, "improve.experiment_created", actor,
                       {"experiment_id": eid, "kind": kind, "target": target, "suite": suite,
                        "hypothesis": hypothesis, "challenger_template": cand}, project_id)
    return eid


def _challenger_body(champion: AgentTemplate, changes: dict) -> AgentTemplate:
    unknown = set(changes) - TEMPLATE_FIELDS
    if unknown:
        raise PolicyDenied(f"an experiment may change only {', '.join(sorted(TEMPLATE_FIELDS))}; "
                           f"{', '.join(sorted(unknown))} are security or ownership settings",
                           reasons=["not_tunable"])
    body = champion.model_dump(exclude={"version", "status"}) | changes
    body["instructions"] = factory.with_safety(str(body.get("instructions") or ""))
    return AgentTemplate(**body)


def propose_template(conn: sqlite3.Connection, project_id: str, target: str, changes: dict, hypothesis: str,
                     suite: str, actor: str) -> Experiment:
    champion = templates.get_template(conn, target)
    if champion.status != TemplateStatus.active:
        raise PolicyDenied(f"template {target} is {champion.status.value}", reasons=["champion_not_active"])
    if not hypothesis.strip():
        raise UsageError("state the hypothesis: what should improve, and why")
    challenger = _challenger_body(champion, changes)
    if challenger.model_dump(exclude={"version", "status"}) == champion.model_dump(exclude={"version", "status"}):
        raise UsageError("the challenger is the same as the champion")
    problems = factory.config_problems(challenger) + factory.widening(challenger, champion)
    if _leaks(conn, project_id, suite, f"{challenger.instructions} {challenger.description}"):
        problems.append("benchmark_leakage")
    if problems:
        raise PolicyDenied(f"challenger refused: {', '.join(problems)}", reasons=problems)
    _no_open(conn, "template", target)
    _ready_suite(conn, project_id, suite)
    n = conn.execute("SELECT count(*) FROM experiments WHERE target=?", (target,)).fetchone()[0] + 1
    cand = f"{target[:34]}-c{n}"
    while conn.execute("SELECT 1 FROM agent_templates WHERE id=?", (cand,)).fetchone():
        n += 1
        cand = f"{target[:34]}-c{n}"
    with write_tx(conn):
        templates.add_template(conn, challenger.model_copy(update={"id": cand, "status": TemplateStatus.candidate}),
                               actor)
        eid = _insert(conn, project_id, "template", target, suite, hypothesis,
                      {"template_id": target, "version": champion.version},
                      {"template_id": cand, "changes": changes}, cand, actor)
    return get_experiment(conn, eid)


def propose_policy(conn: sqlite3.Connection, project_id: str, name: str, value: float, hypothesis: str,
                   suite: str, actor: str) -> Experiment:
    value = policy.check_value(name, value)
    current = policy.get(conn, name)
    if value == current:
        raise UsageError(f"{name} is already {current:g}")
    if not hypothesis.strip():
        raise UsageError("state the hypothesis: what should improve, and why")
    _no_open(conn, "policy", name)
    _ready_suite(conn, project_id, suite)
    with write_tx(conn):
        eid = _insert(conn, project_id, "policy", name, suite, hypothesis, {"value": current}, {"value": value},
                      None, actor)
    return get_experiment(conn, eid)


def _trialing(exp: Experiment) -> None:
    if exp.status != "trialing":
        raise PolicyDenied(f"experiment is {exp.status}", reasons=["experiment_closed"])


def trial_template(conn: sqlite3.Connection, exp: Experiment, arm: str, caps: list[str]) -> str:
    if exp.kind == "template":
        if arm == "challenger":
            return exp.challenger_template
        if templates.get_template(conn, exp.target).version != exp.champion["version"]:
            raise PolicyDenied("the champion changed during the experiment; start a new one",
                               reasons=["champion_changed"])
        return exp.target
    weights = {exp.target: getattr(exp, arm)["value"]}
    ranked = [c.template_id for c in recruit.rank(conn, caps, weights=weights) if c.match == 1.0]
    if not ranked:
        raise PolicyDenied("no active template covers this case", reasons=["no_template"])
    return ranked[0]


def _label(exp_id: str, case_id: str, arm: str) -> str:
    first = "A" if int(hashlib.sha256(f"{exp_id}|{case_id}".encode()).hexdigest()[:2], 16) % 2 == 0 else "B"
    return first if arm == "champion" else ("B" if first == "A" else "A")


def start_trial(conn: sqlite3.Connection, experiment_id: str, case_id: str, arm: str, host: str,
                actor: str) -> dict:
    """Create the trial task for one arm on one case and admit that arm's worker."""
    from agentos.admission import AdmitRequest, admit

    exp = get_experiment(conn, experiment_id)
    _trialing(exp)
    if arm not in ("champion", "challenger"):
        raise UsageError("arm must be champion or challenger")
    case = _case(conn, case_id)
    if case["project_id"] != exp.project_id or case["suite"] != exp.suite:
        raise PolicyDenied("the case is not in this experiment's suite", reasons=["case_not_in_suite"])
    if case["created_at"] > exp.created_at:
        raise PolicyDenied("cases added after the experiment started don't count", reasons=["case_after_experiment"])
    if conn.execute("SELECT 1 FROM trials WHERE experiment_id=? AND case_id=? AND arm=?",
                    (exp.id, case_id, arm)).fetchone():
        raise PolicyDenied("this arm already ran this case", reasons=["trial_exists"])
    caps = json.loads(case["capabilities"])
    template = trial_template(conn, exp, arm, caps)
    label = _label(exp.id, case_id, arm)
    task = tasks.add_task(conn, exp.project_id, f"[trial {exp.id} {label}] {case['title']}",
                          objective=f"benchmark case {case_id}", capabilities=caps,
                          acceptance=json.loads(case["acceptance"]), risk="low", actor=actor)
    tid = new_id("trl")
    with write_tx(conn):
        conn.execute("INSERT INTO trials(id, experiment_id, case_id, arm, label, task_id, template_id, created_at)"
                     " VALUES (?,?,?,?,?,?,?,?)", (tid, exp.id, case_id, arm, label, task.id, template, now_iso()))
    decision = admit(conn, AdmitRequest(project_id=exp.project_id, task_id=task.id, template_id=template,
                                        host=host), actor)
    with write_tx(conn):
        if decision.allowed:
            conn.execute("UPDATE trials SET instance_id=? WHERE id=?", (decision.instance_id, tid))
            audit.append_event(conn, "improve.trial_started", actor,
                               {"trial_id": tid, "experiment_id": exp.id, "case_id": case_id, "label": label,
                                "instance_id": decision.instance_id}, exp.project_id)
        else:
            conn.execute("DELETE FROM trials WHERE id=?", (tid,))
            tasks.set_state(conn, task.id, tasks.TaskState.cancelled, actor, note="trial not admitted")
    return {"status": "admitted" if decision.allowed else "denied", "trial_id": tid if decision.allowed else None,
            "label": label, "task_id": task.id, "template_id": template, "instance_id": decision.instance_id,
            "reasons": decision.reasons}


def _trial(conn, trial_id: str):
    row = conn.execute("SELECT * FROM trials WHERE id=?", (trial_id,)).fetchone()
    if not row:
        raise NotFound(f"trial not found: {trial_id}")
    return row


def check_trial(conn: sqlite3.Connection, trial_id: str, actor: str, timeout_s: int = evidence.DEFAULT_TIMEOUT_S):
    """AgentOS runs the case's own check command; the grade must cite this evidence."""
    t = _trial(conn, trial_id)
    exp = get_experiment(conn, t["experiment_id"])
    _trialing(exp)
    if t["evidence_id"]:
        raise PolicyDenied("this trial was already checked", reasons=["already_checked"])
    case = _case(conn, t["case_id"])
    ev = evidence.run(conn, exp.project_id, json.loads(case["check_command"]), actor, timeout_s)
    with write_tx(conn):
        conn.execute("UPDATE trials SET evidence_id=? WHERE id=?", (ev.id, trial_id))
    return ev


def score_trial(conn: sqlite3.Connection, trial_id: str, evaluation_id: str, actor: str) -> dict:
    t = _trial(conn, trial_id)
    exp = get_experiment(conn, t["experiment_id"])
    _trialing(exp)
    if t["evaluation_id"]:
        raise PolicyDenied("this trial is already scored", reasons=["already_scored"])
    if not conn.execute("SELECT 1 FROM evaluations WHERE id=?", (evaluation_id,)).fetchone():
        raise NotFound(f"evaluation not found: {evaluation_id}")
    ev = performance.get_eval(conn, evaluation_id)
    reasons = []
    if ev.instance_id != t["instance_id"]:
        reasons.append("evaluation_not_for_trial")
    if not t["evidence_id"] or t["evidence_id"] not in ev.evidence:
        reasons.append("evidence_not_from_case")
    # Neither side may grade: for a policy experiment, any template either arm's staffing picked.
    arms = {r[0] for r in conn.execute("SELECT template_id FROM trials WHERE experiment_id=?", (exp.id,))}
    if exp.kind == "template":
        arms |= {exp.target, exp.challenger_template}
    if ev.evaluator_id != performance.OWNER_EVALUATOR:
        evaluator = lifecycle.get_instance(conn, ev.evaluator_id)
        if evaluator.template_id in arms:
            reasons.append("evaluator_not_independent")
    if reasons:
        raise PolicyDenied(f"trial cannot be scored: {', '.join(reasons)}", reasons=reasons)
    with write_tx(conn):
        conn.execute("UPDATE trials SET evaluation_id=? WHERE id=?", (evaluation_id, trial_id))
        audit.append_event(conn, "improve.trial_scored", actor,
                           {"trial_id": trial_id, "evaluation_id": evaluation_id, "weighted": round(ev.weighted, 2)},
                           exp.project_id)
    return {"trial_id": trial_id, "label": t["label"], "evaluation_id": evaluation_id,
            "weighted": round(ev.weighted, 2)}


def gate(conn: sqlite3.Connection, experiment_id: str, argv: list[str], actor: str,
         timeout_s: int = evidence.DEFAULT_TIMEOUT_S):
    """Run the regression and security checks; the latest gate run must pass before promotion."""
    exp = get_experiment(conn, experiment_id)
    _trialing(exp)
    ev = evidence.run(conn, exp.project_id, argv, actor, timeout_s)
    with write_tx(conn):
        conn.execute("UPDATE experiments SET gate_evidence=? WHERE id=?",
                     (json.dumps([*exp.gate_evidence, ev.id]), exp.id))
    return ev


def trials_of(conn: sqlite3.Connection, experiment_id: str) -> list[dict]:
    out = []
    for t in conn.execute("SELECT * FROM trials WHERE experiment_id=? ORDER BY created_at, rowid", (experiment_id,)):
        d = dict(t)
        d.pop("arm")  # listings stay blind: label only
        out.append(d)
    return out


def _outcome(conn, t) -> dict | None:
    """Score and pass of one trial; None while it is still in progress. An abandoned trial is a failure."""
    passed = None
    if t["evidence_id"]:
        row = conn.execute("SELECT exit_code, timed_out FROM evidence WHERE id=?", (t["evidence_id"],)).fetchone()
        passed = row["exit_code"] == 0 and not row["timed_out"]
    if t["evaluation_id"]:
        ev = performance.get_eval(conn, t["evaluation_id"])
        return {"score": ev.weighted, "passed": bool(passed), "flags": ev.flags, "evaluator": ev.evaluator_id}
    if t["instance_id"] and lifecycle.get_instance(conn, t["instance_id"]).state in TERMINAL:
        return {"score": 0.0, "passed": False, "flags": [], "evaluator": None, "abandoned": True}
    return None


def _mean(values):
    return statistics.fmean(values) if values else None


def evaluate(conn: sqlite3.Connection, experiment_id: str) -> dict:
    """The comparison as it stands, without deciding."""
    exp = get_experiment(conn, experiment_id)
    by_case: dict[str, dict] = {}
    in_progress = []
    for t in conn.execute("SELECT * FROM trials WHERE experiment_id=?", (exp.id,)):
        o = _outcome(conn, t)
        if o is None:
            in_progress.append(t["id"])
            continue
        by_case.setdefault(t["case_id"], {})[t["arm"]] = o
    split = {}
    for case_id in by_case:
        c = _case(conn, case_id)
        split[case_id] = "heldout" if c["split"] == "heldout" and not _exposed_before(conn, case_id, exp) \
            else "representative"
    paired = {cid: arms for cid, arms in by_case.items() if {"champion", "challenger"} <= set(arms)}

    def side(kind):
        cases = [cid for cid in paired if split[cid] == kind]
        cp = [paired[c]["champion"]["score"] for c in cases]
        ch = [paired[c]["challenger"]["score"] for c in cases]
        wins = sum(1 for c in cases if paired[c]["challenger"]["score"] > paired[c]["champion"]["score"])
        losses = sum(1 for c in cases if paired[c]["challenger"]["score"] < paired[c]["champion"]["score"])
        return {"cases": len(cases), "champion_mean": _mean(cp), "challenger_mean": _mean(ch),
                "delta": (_mean(ch) - _mean(cp)) if cases else None, "wins": wins, "losses": losses,
                "champion_pass": sum(paired[c]["champion"]["passed"] for c in cases),
                "challenger_pass": sum(paired[c]["challenger"]["passed"] for c in cases)}

    outcomes = [o for arms in paired.values() for o in arms.values()]
    gate_ok = False
    if exp.gate_evidence:
        row = conn.execute("SELECT exit_code, timed_out FROM evidence WHERE id=?", (exp.gate_evidence[-1],)).fetchone()
        gate_ok = row["exit_code"] == 0 and not row["timed_out"]
    return {"experiment_id": exp.id, "representative": side("representative"), "heldout": side("heldout"),
            "in_progress": in_progress, "evaluators": len({o["evaluator"] for o in outcomes if o["evaluator"]}),
            "flags": sorted({f for o in outcomes for f in o["flags"]}), "gate_passed": gate_ok,
            "champion_mean_all": _mean([a["champion"]["score"] for a in paired.values()]),
            "challenger_mean_all": _mean([a["challenger"]["score"] for a in paired.values()])}


def _exposed_before(conn, case_id: str, exp: Experiment) -> bool:
    return conn.execute("SELECT 1 FROM trials t JOIN experiments e ON e.id=t.experiment_id WHERE t.case_id=?"
                        " AND e.rowid < (SELECT rowid FROM experiments WHERE id=?)",
                        (case_id, exp.id)).fetchone() is not None


def decide(conn: sqlite3.Connection, experiment_id: str, actor: str) -> dict:
    """Promote or reject on the evidence. Refuses (without deciding) while the evidence is incomplete."""
    exp = get_experiment(conn, experiment_id)
    _trialing(exp)
    r = evaluate(conn, exp.id)
    rep, held = r["representative"], r["heldout"]
    incomplete = []
    if r["in_progress"]:
        incomplete.append("trials_in_progress")
    if rep["cases"] < MIN_REPRESENTATIVE:
        incomplete.append("not_enough_trials")
    if held["cases"] < MIN_HELDOUT:
        incomplete.append("not_enough_heldout_trials")
    if not r["gate_passed"]:
        incomplete.append("gate_not_passed")
    if r["evaluators"] < 2:
        incomplete.append("not_enough_evaluators")
    if exp.kind == "template" and templates.get_template(conn, exp.target).version != exp.champion["version"]:
        incomplete.append("champion_changed")
    if incomplete:
        raise PolicyDenied(f"not ready to decide: {', '.join(incomplete)}", reasons=incomplete)
    why = []
    if rep["delta"] < MARGIN:
        why.append(f"representative gain {rep['delta']:.1f} is below the {MARGIN:g}-point margin")
    if rep["wins"] <= rep["losses"]:
        why.append(f"wins {rep['wins']} do not exceed losses {rep['losses']}")
    if held["delta"] < 0:
        why.append(f"worse on held-out cases ({held['delta']:.1f})")
    if rep["challenger_pass"] + held["challenger_pass"] < rep["champion_pass"] + held["champion_pass"]:
        why.append("fewer cases pass their check command")
    if r["flags"]:
        why.append(f"flagged: {', '.join(r['flags'])}")
    if exp.kind == "template":
        cand = templates.get_template(conn, exp.challenger_template)
        champ = templates.get_template(conn, exp.target, exp.champion["version"])
        if factory.config_problems(cand) or factory.widening(cand, champ):
            why.append("challenger failed the security check")
    promote = not why
    result = r | {"decision": "promote" if promote else "reject", "why": why or ["beat the champion on every test"]}
    ts = now_iso()
    with write_tx(conn):
        if promote:
            monitor = _promote(conn, exp, r, actor)
            status = "promoted"
        else:
            monitor, status = None, "rejected"
        conn.execute("UPDATE experiments SET status=?, result=?, monitor=?, decided_at=? WHERE id=?",
                     (status, json.dumps(result), json.dumps(monitor) if monitor else None, ts, exp.id))
        audit.append_event(conn, f"improve.{status}", actor,
                           {"experiment_id": exp.id, "target": exp.target, "why": result["why"],
                            "representative_delta": rep["delta"], "heldout_delta": held["delta"]}, exp.project_id)
        _remember(conn, exp, status, result, actor)
    return {"experiment_id": exp.id, "status": status, "result": result, "monitor": monitor}


def _promote(conn, exp: Experiment, r: dict, actor: str) -> dict:
    if exp.kind == "template":
        champ = templates.get_template(conn, exp.target)
        body = champ.model_dump(exclude={"version", "status"}) | exp.challenger["changes"]
        body["instructions"] = factory.with_safety(str(body.get("instructions") or ""))
        new = templates.add_template(conn, AgentTemplate(**body), actor)
        return {"template_id": exp.target, "version": new.version, "previous_version": champ.version,
                "baseline_mean": r["champion_mean_all"], "challenger_mean": r["challenger_mean_all"],
                "needed": MONITOR_N}
    before = [row[0] for row in conn.execute(
        "SELECT e.weighted FROM evaluations e JOIN agent_instances i ON i.id=e.instance_id"
        " WHERE i.project_id=? AND e.external_cause=0 ORDER BY e.created_at DESC, e.rowid DESC LIMIT 20",
        (exp.project_id,))]
    put_setting(conn, f"policy.{exp.target}", exp.challenger["value"])
    return {"policy": exp.target, "value": exp.challenger["value"], "previous_value": exp.champion["value"],
            "baseline_mean": _mean(before), "needed": MONITOR_N, "since": now_iso()}


def _remember(conn, exp: Experiment, status: str, result: dict, actor: str) -> None:
    rep, held = result["representative"], result["heldout"]
    numbers = (f"representative {rep['challenger_mean']:.1f} vs {rep['champion_mean']:.1f} over {rep['cases']} cases, "
               f"held-out {held['challenger_mean']:.1f} vs {held['champion_mean']:.1f} over {held['cases']}")
    if status == "promoted":
        memory.add(conn, exp.project_id, memory.Layer.procedural,
                   f"Validated improvement to {exp.target}: {exp.hypothesis} ({numbers}).",
                   source=f"experiment {exp.id}", author=actor, confidence=0.8, validated=True, scope="org",
                   tags=["improvement", exp.kind])
    else:
        memory.add(conn, exp.project_id, memory.Layer.failure,
                   f"Rejected change to {exp.target}: {exp.hypothesis} ({numbers}; {'; '.join(result['why'])}).",
                   source=f"experiment {exp.id}", author=actor, confidence=0.7, tags=["improvement", exp.kind])


def abandon(conn: sqlite3.Connection, experiment_id: str, actor: str, reason: str) -> Experiment:
    exp = get_experiment(conn, experiment_id)
    _trialing(exp)
    with write_tx(conn):
        conn.execute("UPDATE experiments SET status='abandoned', decided_at=? WHERE id=?", (now_iso(), exp.id))
        audit.append_event(conn, "improve.abandoned", actor, {"experiment_id": exp.id, "reason": reason},
                           exp.project_id)
    return get_experiment(conn, exp.id)


# --- monitoring and rollback --------------------------------------------------------------------

def monitor(conn: sqlite3.Connection, actor: str, project_id: str | None = None) -> list[dict]:
    out = []
    for exp in list_experiments(conn, project_id, "promoted"):
        m = exp.monitor or {}
        if exp.kind == "template":
            latest = templates.get_template(conn, exp.target).version
            if latest != m["version"]:
                _close(conn, exp, "superseded", actor, {"latest_version": latest})
                out.append({"experiment_id": exp.id, "status": "superseded"})
                continue
            values = [row[0] for row in conn.execute(
                "SELECT e.weighted FROM evaluations e JOIN agent_instances i ON i.id=e.instance_id"
                " WHERE i.template_id=? AND i.template_version=? AND e.external_cause=0", (exp.target, m["version"]))]
        else:
            values = [row[0] for row in conn.execute(
                "SELECT e.weighted FROM evaluations e JOIN agent_instances i ON i.id=e.instance_id"
                " WHERE i.project_id=? AND e.external_cause=0 AND e.created_at>=?", (exp.project_id, m["since"]))]
        n, mean = len(values), _mean(values)
        base = m.get("baseline_mean")
        if n < MONITOR_N:
            out.append({"experiment_id": exp.id, "status": "monitoring", "evaluations": n, "mean": mean})
        elif base is not None and mean < base - ROLLBACK_MARGIN:
            _rollback(conn, exp, mean, n, actor)
            out.append({"experiment_id": exp.id, "status": "rolled_back", "evaluations": n, "mean": mean,
                        "baseline_mean": base})
        else:
            _close(conn, exp, "adopted", actor, {"evaluations": n, "mean": mean})
            out.append({"experiment_id": exp.id, "status": "adopted", "evaluations": n, "mean": mean})
    return out


def _close(conn, exp: Experiment, status: str, actor: str, detail: dict) -> None:
    with write_tx(conn):
        conn.execute("UPDATE experiments SET status=? WHERE id=?", (status, exp.id))
        audit.append_event(conn, f"improve.{status}", actor, {"experiment_id": exp.id, **detail}, exp.project_id)


def _rollback(conn, exp: Experiment, mean: float, n: int, actor: str) -> None:
    m = exp.monitor
    with write_tx(conn):
        if exp.kind == "template":
            prev = templates.get_template(conn, exp.target, m["previous_version"])
            restored = templates.add_template(conn, AgentTemplate(**prev.model_dump(exclude={"version", "status"})),
                                              actor)
            detail = {"restored_from_version": prev.version, "version": restored.version}
        else:
            put_setting(conn, f"policy.{exp.target}", m["previous_value"])
            detail = {"restored_value": m["previous_value"]}
        conn.execute("UPDATE experiments SET status='rolled_back' WHERE id=?", (exp.id,))
        audit.append_event(conn, "improve.rolled_back", actor,
                           {"experiment_id": exp.id, "mean": mean, "evaluations": n, **detail}, exp.project_id)
        memory.add(conn, exp.project_id, memory.Layer.failure,
                   f"Rolled back {exp.target}: after promotion it averaged {mean:.1f} over {n} evaluations, below "
                   f"its baseline {m['baseline_mean']:.1f}. Hypothesis was: {exp.hypothesis}",
                   source=f"experiment {exp.id}", author=actor, confidence=0.8, tags=["improvement", "rollback"])


# --- retrospective, diagnosis and hypotheses ------------------------------------------------------

def diagnose(conn: sqlite3.Connection, project_id: str) -> list[dict]:
    """Recurring weaknesses in this project's record."""
    found = []
    per_template: dict[str, list] = {}
    for row in conn.execute("SELECT e.template_id, e.scores, e.evidence FROM evaluations e JOIN agent_instances i"
                            " ON i.id=e.instance_id WHERE i.project_id=? AND e.external_cause=0", (project_id,)):
        per_template.setdefault(row[0], []).append((json.loads(row[1]), json.loads(row[2])))
    for tid, evals in sorted(per_template.items()):
        if len(evals) < WEAK_MIN_EVALS:
            continue
        for key in performance.WEIGHTS:
            mean = statistics.fmean(s.get(key, 0) for s, _ in evals)
            if mean < WEAK_SUBSCORE:
                found.append({"kind": "template_subscore", "template_id": tid, "subscore": key,
                              "mean": round(mean, 1), "evaluations": len(evals)})
        failed = 0
        for _, refs in evals:
            rows = [conn.execute("SELECT exit_code FROM evidence WHERE id=?", (r,)).fetchone() for r in refs]
            if rows and all(x is not None and x[0] != 0 for x in rows):
                failed += 1
        if failed * 2 >= len(evals):
            found.append({"kind": "evidence_failures", "template_id": tid, "failed": failed,
                          "evaluations": len(evals)})
    reasons: dict[str, int] = {}
    for (payload,) in conn.execute("SELECT payload FROM events WHERE kind='agent.admission_denied' AND project_id=?",
                                   (project_id,)):
        for r in json.loads(payload).get("reasons", []):
            reasons[r] = reasons.get(r, 0) + 1
    for r, n in sorted(reasons.items()):
        if n >= RECURRING:
            found.append({"kind": "admission_reason", "reason": r, "count": n})
    caps: dict[str, int] = {}
    for (c,) in conn.execute("SELECT capabilities FROM tasks WHERE project_id=? AND state='failed'", (project_id,)):
        for cap in json.loads(c):
            caps[cap] = caps.get(cap, 0) + 1
    for cap, n in sorted(caps.items()):
        if n >= 2:
            found.append({"kind": "task_failures", "capability": cap, "count": n})
    return found


def _tried(conn, target: str, changes: dict) -> bool:
    digest = sha256_json(changes)
    return any(sha256_json(e.challenger.get("changes", e.challenger)) == digest
               for e in list_experiments(conn) if e.target == target)


def hypotheses(conn: sqlite3.Connection, weaknesses: list[dict]) -> list[dict]:
    out = []
    for w in weaknesses:
        if w["kind"] in ("template_subscore", "evidence_failures"):
            key = w.get("subscore", "reliability")
            try:
                t = templates.get_template(conn, w["template_id"])
            except NotFound:
                continue
            if t.status != TemplateStatus.active or GUIDANCE[key] in t.instructions:
                continue
            changes = {"instructions": t.instructions.rstrip() + "\n" + GUIDANCE[key]}
            busy = conn.execute("SELECT 1 FROM experiments WHERE target=? AND status='trialing'", (t.id,)).fetchone()
            if busy or _tried(conn, t.id, changes) or any(h.get("target") == t.id for h in out):
                continue
            out.append({"kind": "template", "target": t.id, "changes": changes,
                        "hypothesis": f"explicit guidance on {key} raises {t.id}'s {key} score "
                                      f"(now {w.get('mean', 'failing evidence')})"})
        elif w["kind"] == "admission_reason" and w["reason"] == "capability_mismatch":
            p = policy.spec("recruit.w_match")
            value = round(min(p.high, policy.get(conn, p.name) + 0.1), 2)
            if value != policy.get(conn, p.name) and not _tried(conn, p.name, {"value": value}):
                out.append({"kind": "policy", "target": p.name, "value": value,
                            "hypothesis": "weighing capability match more stops recruiting templates that "
                                          f"don't fit ({w['count']} capability_mismatch refusals)"})
    return out


def retro(conn: sqlite3.Connection, project_id: str, actor: str, task_id: str | None = None,
          objective_id: str | None = None) -> dict:
    """After meaningful work: collect outcomes and evidence, separate what worked from what didn't,
    diagnose recurring weaknesses, propose hypotheses and check promoted changes."""
    if task_id:
        scope, scope_id = "task", task_id
        ids = [task_id] + [r[0] for r in conn.execute("SELECT id FROM tasks WHERE parent_id=?", (task_id,))]
    elif objective_id:
        scope, scope_id = "objective", objective_id
        ids = [r[0] for r in conn.execute("SELECT id FROM tasks WHERE objective_id=?", (objective_id,))]
    else:
        scope, scope_id = "project", None
        ids = [r[0] for r in conn.execute("SELECT id FROM tasks WHERE project_id=? AND state IN ('done','failed')",
                                          (project_id,))]
    outcomes, good, bad = [], [], []
    for tid in ids:
        t = tasks.get_task(conn, tid)
        if t.project_id != project_id:
            raise PolicyDenied("the task belongs to another project", reasons=["cross_project"])
        outcomes.append({"task_id": t.id, "state": t.state.value, "retries": t.retries})
        for inst in conn.execute("SELECT id, template_id FROM agent_instances WHERE task_id=?", (tid,)).fetchall():
            evals = [performance.get_eval(conn, r[0]) for r in
                     conn.execute("SELECT id FROM evaluations WHERE instance_id=?", (inst[0],))]
            if not evals:
                continue
            mean = statistics.fmean(e.weighted for e in evals)
            refs = [r for e in evals for r in e.evidence]
            passed = any((row := conn.execute("SELECT exit_code FROM evidence WHERE id=?", (r,)).fetchone())
                         and row[0] == 0 for r in refs)
            entry = {"task_id": tid, "template_id": inst[1], "capabilities": t.capabilities,
                     "mean": round(mean, 1), "evidence_passed": passed}
            if mean >= 85 and passed and t.state.value == "done":
                good.append(entry)
            elif mean < 70 or not passed or t.state.value == "failed":
                bad.append(entry)
    weaknesses = diagnose(conn, project_id)
    hyps = hypotheses(conn, weaknesses)
    monitored = monitor(conn, actor, project_id)
    report = {"scope": scope, "scope_id": scope_id, "outcomes": outcomes, "successful": good,
              "unsuccessful": bad, "weaknesses": weaknesses, "hypotheses": hyps, "monitoring": monitored}
    rid = new_id("retro")
    with write_tx(conn):
        conn.execute("INSERT INTO retrospectives(id, project_id, scope, scope_id, report, created_at, actor)"
                     " VALUES (?,?,?,?,?,?,?)", (rid, project_id, scope, scope_id, json.dumps(report), now_iso(), actor))
        audit.append_event(conn, "improve.retro", actor,
                           {"retro_id": rid, "scope": scope, "scope_id": scope_id, "weaknesses": len(weaknesses),
                            "hypotheses": len(hyps)}, project_id)
    return {"id": rid, **report}


def get_retro(conn: sqlite3.Connection, retro_id: str) -> dict:
    row = conn.execute("SELECT * FROM retrospectives WHERE id=?", (retro_id,)).fetchone()
    if not row:
        raise NotFound(f"retrospective not found: {retro_id}")
    return {"id": row["id"], "project_id": row["project_id"], "created_at": row["created_at"],
            **json.loads(row["report"])}


def propose_from_retro(conn: sqlite3.Connection, retro_id: str, index: int, suite: str, actor: str) -> Experiment:
    r = get_retro(conn, retro_id)
    hyps = r["hypotheses"]
    if not 0 <= index < len(hyps):
        raise UsageError(f"hypothesis {index} does not exist (0-{len(hyps) - 1})" if hyps else "no hypotheses")
    h = hyps[index]
    if h["kind"] == "template":
        return propose_template(conn, r["project_id"], h["target"], h["changes"], h["hypothesis"], suite, actor)
    return propose_policy(conn, r["project_id"], h["target"], h["value"], h["hypothesis"], suite, actor)


def policies(conn: sqlite3.Connection) -> list[dict]:
    return [p.model_dump() | {"value": policy.get(conn, p.name),
                              "set": get_setting(conn, f"policy.{p.name}", None) is not None}
            for p in policy.REGISTRY.values()]
