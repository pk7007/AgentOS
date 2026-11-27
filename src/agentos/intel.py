"""Organisational intelligence from the ledger: staffing and resource forecasts, model-tier routing advice,
context packing, reusable skills from proven commands, organisation and failure analysis, competitive
evaluation of solutions, independent governance checks, project profiles and validated cross-project
lessons. Simple counting and ranking only: nothing here calls a model, spends money or admits a worker."""

import json
import math
import re
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime

from agentos import audit, governor, lifecycle, memory, performance, recruit, tasks, templates
from agentos.db import write_tx
from agentos.errors import NotFound, PolicyDenied, UsageError
from agentos.memory import ORG_LAYERS, Layer
from agentos.paths import agentos_home
from agentos.templates import TemplateStatus

OPEN = ("pending", "running", "blocked")
TIERS = ("small", "medium", "large")
RELATIVE_COST = {"small": 1, "medium": 3, "large": 10}  # relative units, not prices
REASONING = {"small": "low", "medium": "medium", "large": "high"}
CHARS_PER_TOKEN = 4  # a rough estimate, labelled as such wherever it is shown
MIN_HISTORY = 3


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _open_tasks(conn, project_id: str, objective_id: str | None = None) -> list:
    sql = f"SELECT id FROM tasks WHERE project_id=? AND state IN ({','.join('?' * len(OPEN))})"
    params: list = [project_id, *OPEN]
    if objective_id:
        sql += " AND objective_id=?"
        params.append(objective_id)
    return [tasks.get_task(conn, r[0]) for r in conn.execute(sql + " ORDER BY created_at, rowid", params)]


def _layers(open_tasks: list) -> list[list]:
    """Open tasks grouped into waves: a task's wave is one more than the latest wave of its open dependencies."""
    by_id = {t.id: t for t in open_tasks}
    waiting = {t.id: {d for d in t.deps if d in by_id} for t in open_tasks}
    out: list[list] = []
    while waiting:  # iterative, so a long chain cannot exhaust the stack
        ready = [t for t in open_tasks if t.id in waiting and not waiting[t.id]]
        if not ready:  # a cycle: `task dep` refuses them, but a hand-edited ledger could hold one
            out.append([t for t in open_tasks if t.id in waiting])
            break
        out.append(ready)
        done = {t.id for t in ready}
        waiting = {k: v - done for k, v in waiting.items() if k not in done}
    return out


def _effort(conn, task_id: str) -> int:
    return conn.execute("SELECT effort FROM tasks WHERE id=?", (task_id,)).fetchone()[0] or 1


def _done_history(conn, project_id: str) -> tuple[list[str], str]:
    """Done tasks of this project, or of every project when this one has too little history."""
    own = [r[0] for r in conn.execute("SELECT id FROM tasks WHERE project_id=? AND state='done'", (project_id,))]
    if len(own) >= MIN_HISTORY:
        return own, "project"
    return [r[0] for r in conn.execute("SELECT id FROM tasks WHERE state='done'")], "all_projects"


def _workers_per_task(conn, done: list[str]) -> float:
    if not done:
        return 1.0
    marks = ",".join("?" * len(done))
    counts = dict(conn.execute(
        f"SELECT task_id, count(*) FROM agent_instances WHERE task_id IN ({marks}) GROUP BY task_id", done).fetchall())
    return statistics.fmean(max(1, counts.get(t, 0)) for t in done)


# --- predictive staffing ---

def staffing(conn: sqlite3.Connection, project_id: str, objective_id: str | None = None) -> dict:
    open_tasks = _open_tasks(conn, project_id, objective_id)
    waves = _layers(open_tasks)
    limit = governor.get_limits(conn).max_concurrent
    done, basis = _done_history(conn, project_id)
    per_task = _workers_per_task(conn, done)
    caps: dict[str, Counter] = defaultdict(Counter)
    for i, wave in enumerate(waves):
        for t in wave:
            for c in {x.strip().lower() for x in t.capabilities if x.strip()} or {"general"}:
                caps[c][i] += 1
    rows, gaps = [], []
    for c, by_wave in sorted(caps.items()):
        peak = max(by_wave.values())
        ranked = [x for x in recruit.rank(conn, [c]) if x.match == 1.0] if c != "general" else []
        row = {"capability": c, "open_tasks": sum(by_wave.values()), "peak_parallel": peak,
               "recommended_workers": min(limit, math.ceil(peak * per_task)),
               "template_id": ranked[0].template_id if ranked else None,
               "alternatives": [x.template_id for x in ranked[1:3]]}
        if c != "general" and not ranked:
            row["action"] = f"agentos factory propose --cap {c}"
            gaps.append(c)
        rows.append(row)
    peak = max((len(w) for w in waves), default=0)
    need = math.ceil(peak * per_task)
    ids = [t.id for t in open_tasks]
    running = conn.execute(
        f"SELECT count(*) FROM agent_instances WHERE task_id IN ({','.join('?' * len(ids))}) AND state IN "
        f"({','.join('?' * len(lifecycle.ACTIVE_STATES))})",
        [*ids, *(s.value for s in lifecycle.ACTIVE_STATES)]).fetchone()[0] if ids else 0
    return {"project_id": project_id, "objective_id": objective_id, "open_tasks": len(open_tasks),
            "waves": len(waves), "peak_parallel": peak, "workers_per_task": round(per_task, 2),
            "history_basis": basis, "history_tasks": len(done), "recommended_workers": min(limit, need),
            "already_working": running, "to_recruit": max(0, min(limit, need) - running),
            "limited_by_max_concurrent": need > limit, "max_concurrent": limit, "by_capability": rows,
            "capability_gaps": gaps}


# --- cost-aware model routing ---

def _project_perf(conn, project_id: str, template_id: str) -> tuple[int, float | None, float | None]:
    vals = [r[0] for r in conn.execute(
        "SELECT e.weighted FROM evaluations e JOIN agent_instances a ON a.id=e.instance_id "
        "WHERE e.template_id=? AND a.project_id=? AND e.external_cause=0", (template_id, project_id))]
    if not vals:
        return 0, None, None
    return len(vals), statistics.fmean(vals), sum(1 for v in vals if v < 50) / len(vals)


def route(conn: sqlite3.Connection, task_id: str, template_id: str | None = None) -> dict:
    """The cheapest model tier the task's risk and the worker's record justify. Critical and high-risk work
    never drops below the large tier; a strong record only lowers low- and medium-risk work."""
    t = tasks.get_task(conn, task_id)
    effort = _effort(conn, t.id)
    tier = {"low": 0, "medium": 1, "high": 2, "critical": 2}[t.risk]
    reasons = [f"risk {t.risk}: start at {TIERS[tier]}"]
    if effort >= 5 and tier < 2:
        tier += 1
        reasons.append(f"effort {effort}: one tier up")
    if template_id is None:
        ranked = recruit.rank(conn, t.capabilities, high_risk=t.risk in ("high", "critical"))
        template_id = ranked[0].template_id if ranked else None
    if template_id:
        n, mean, fail = _project_perf(conn, t.project_id, template_id)
        scope = "this project"
        if n < MIN_HISTORY:
            s = performance.summary(conn, template_id)
            n, mean, fail, scope = s.n, s.mean, s.failure_rate, "all projects"
        if n < MIN_HISTORY:
            reasons.append(f"{template_id} has {n} evaluations: not enough history to adjust")
        elif fail is not None and fail >= 0.3 and tier < 2:
            tier += 1
            reasons.append(f"{template_id} fails {fail:.0%} of graded work in {scope}: one tier up")
        elif mean is not None and mean >= 85 and tier > 0 and t.risk in ("low", "medium"):
            tier -= 1
            reasons.append(f"{template_id} averages {mean:.0f} over {n} evaluations in {scope}: one tier down")
    cap = governor.get_limits(conn).max_paid_spend_usd
    chosen = TIERS[tier]
    note = "advice only: the host chooses the model."
    if cap <= 0:
        note += " Paid spend is blocked (cap 0): use the models included with the host."
    return {"task_id": t.id, "template_id": template_id, "tier": chosen, "reasoning_hint": REASONING[chosen],
            "relative_cost": RELATIVE_COST[chosen], "reasons": reasons, "paid_spend_allowed": cap > 0, "note": note}


# --- context optimisation ---

def _tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / CHARS_PER_TOKEN))


def context_pack(conn: sqlite3.Connection, task_id: str, budget_tokens: int = 800) -> dict:
    """The most useful memory for a task within a token budget: validated knowledge and past failures
    first, duplicates dropped, then by confidence and relevance."""
    if budget_tokens < 50:
        raise UsageError("the context budget must be at least 50 tokens")
    t = tasks.get_task(conn, task_id)
    found = memory.search(conn, t.project_id, " ".join([t.title, t.objective, *t.capabilities]), limit=50,
                          any_term=True)
    order = {r.id: i for i, r in enumerate(found)}
    ranked = sorted(found, key=lambda r: (-int(r.validated), r.layer != Layer.failure, -r.confidence, order[r.id]))
    used, seen, included, excluded = 0, set(), [], []
    for r in ranked:
        key, n = _norm(r.content), _tokens(r.content)
        if key in seen:
            excluded.append({"id": r.id, "reason": "duplicate", "tokens_est": n})
        elif used + n > budget_tokens:
            excluded.append({"id": r.id, "reason": "over_budget", "tokens_est": n})
        else:
            seen.add(key)
            used += n
            included.append({"id": r.id, "layer": r.layer.value, "scope": r.scope, "validated": r.validated,
                             "tokens_est": n, "content": r.content})
    return {"task_id": t.id, "budget_tokens": budget_tokens, "used_tokens_est": used, "included": included,
            "excluded": excluded,
            "duplicate_tokens_est": sum(x["tokens_est"] for x in excluded if x["reason"] == "duplicate"),
            "left_out_tokens_est": sum(x["tokens_est"] for x in excluded if x["reason"] == "over_budget"),
            "measurement": f"estimate ({CHARS_PER_TOKEN} characters per token)"}


# --- reusable skills from proven commands ---

def _command(row) -> str:
    try:
        argv = json.loads(row["command"])
    except (TypeError, ValueError):
        return str(row["command"])
    return " ".join(argv) if isinstance(argv, list) else str(argv)


def skill_candidates(conn: sqlite3.Connection, project_id: str, min_uses: int = 3) -> list[dict]:
    """Commands that passed in at least `min_uses` different tasks graded 70 or more, unflagged, by an
    independent evaluator, and that pass at least two times in three wherever they were run."""
    uses: dict[str, dict] = {}
    for ev in conn.execute(
            "SELECT e.evidence, a.task_id FROM evaluations e JOIN agent_instances a ON a.id=e.instance_id "
            "WHERE a.project_id=? AND e.weighted >= 70 AND e.flags='[]'", (project_id,)):
        for eid in json.loads(ev["evidence"]):
            row = conn.execute("SELECT * FROM evidence WHERE id=? AND project_id=? AND exit_code=0 AND timed_out=0",
                               (eid, project_id)).fetchone()
            if row:
                u = uses.setdefault(_command(row), {"tasks": set(), "evidence": set()})
                u["tasks"].add(ev["task_id"])
                u["evidence"].add(eid)
    runs: dict[str, list[int]] = defaultdict(list)
    for row in conn.execute("SELECT command, exit_code, timed_out FROM evidence WHERE project_id=?", (project_id,)):
        runs[_command(row)].append(int(row["exit_code"] == 0 and not row["timed_out"]))
    out = []
    for cmd, u in uses.items():
        rate = statistics.fmean(runs[cmd])
        if len(u["tasks"]) >= min_uses and rate >= 2 / 3:
            out.append({"command": cmd, "tasks": len(u["tasks"]), "runs": len(runs[cmd]),
                        "pass_rate": round(rate, 3), "evidence": sorted(u["evidence"])})
    return sorted(out, key=lambda x: (-x["tasks"], x["command"]))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-") or "skill"


def create_skill(conn: sqlite3.Connection, project_id: str, evidence_id: str, actor: str, name: str | None = None,
                 min_uses: int = 3) -> dict:
    """Write a native SKILL.md for a proven command, and a validated procedural memory pointing to it."""
    row = conn.execute("SELECT * FROM evidence WHERE id=? AND project_id=?", (evidence_id, project_id)).fetchone()
    if not row:
        raise NotFound(f"evidence not found in this project: {evidence_id}")
    cmd = _command(row)
    if any(ch in cmd for ch in "`\r\n"):
        raise PolicyDenied("the command cannot be written safely into a skill file", reasons=["unsafe_command"])
    match = next((c for c in skill_candidates(conn, project_id, min_uses) if c["command"] == cmd), None)
    if not match:
        raise PolicyDenied(f"`{cmd}` has not passed in {min_uses} independently graded tasks yet",
                           reasons=["not_enough_evidence"])
    slug = _slug(name or cmd)
    body = "\n".join([
        "---", f"name: {slug}", f"description: {json.dumps('Run and check: ' + cmd)}", "---", "",
        f"# {slug}", "",
        f"This project checks this kind of work with `{cmd}`. It passed in {match['tasks']} tasks that",
        f"independent evaluators graded 70 or more, and in {match['pass_rate']:.0%} of the {match['runs']} runs here.",
        "",
        f"1. Run it through AgentOS so the result is recorded: `agentos evidence run -- {cmd}`.",
        "2. Cite the evidence id when the work is evaluated. A failing run is a finding, not noise.", "",
        "Evidence: " + ", ".join(match["evidence"][:10]), ""])
    path = agentos_home() / "skills" / project_id / slug / "SKILL.md"
    if path.exists() and f"`{cmd}`" not in path.read_text(encoding="utf-8"):
        raise PolicyDenied(f"a different skill named {slug} exists; choose another --name", reasons=["skill_exists"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(body, encoding="utf-8")  # the file is in place before the ledger says so
    try:
        with write_tx(conn):
            rec = memory.add(conn, project_id, Layer.procedural, f"Skill {slug}: check the work with `{cmd}`.",
                             source=f"evidence:{','.join(match['evidence'][:10])}", author=actor, confidence=0.8,
                             validated=True, tags=["skill", slug])
            audit.append_event(conn, "intel.skill_created", actor, {"skill": slug, "command": cmd,
                                                                   "path": str(path), "memory_id": rec.id,
                                                                   "tasks": match["tasks"]}, project_id)
        try:
            tmp.replace(path)  # after the commit: a failed commit leaves no file behind
        except OSError:
            memory.delete(conn, rec.id, actor, project_id)  # and a failed move leaves no record pointing nowhere
            raise
    finally:
        tmp.unlink(missing_ok=True)
    return {"skill": slug, "path": str(path), "memory_id": rec.id, "command": cmd, "tasks": match["tasks"],
            "pass_rate": match["pass_rate"]}


# --- organisational optimisation ---

def org_review(conn: sqlite3.Connection, project_id: str, idle_days: int = 30) -> dict:
    findings = []
    active = templates.list_templates(conn, TemplateStatus.active)
    now = datetime.now(UTC)
    for t in active:
        last = conn.execute("SELECT max(created_at) FROM agent_instances WHERE template_id=?", (t.id,)).fetchone()[0]
        if last is None or (now - _ts(last)).days >= idle_days:
            findings.append({"kind": "idle_template", "subject": t.id,
                             "detail": "never recruited" if last is None else f"last recruited {last}",
                             "action": "keep it if it covers a rare capability; otherwise consider retiring it"})
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            ca, cb = set(a.capabilities), set(b.capabilities)
            overlap = len(ca & cb) / len(ca | cb)
            if overlap >= 2 / 3:
                findings.append({"kind": "overlapping_templates", "subject": f"{a.id}+{b.id}",
                                 "detail": f"{overlap:.0%} of capabilities shared",
                                 "action": "compare their records (agentos perf show) and keep the stronger"})
    providers = Counter(c for t in active for c in set(t.capabilities))
    demand = Counter(c for t in _open_tasks(conn, project_id) for c in set(t.capabilities))
    for c, n in sorted(demand.items()):
        if providers[c] == 1 and n >= 3:
            findings.append({"kind": "single_point_of_failure", "subject": c,
                             "detail": f"{n} open tasks, one template provides it",
                             "action": f"agentos factory propose --cap {c}"})
        elif providers[c] and n / providers[c] >= 5:
            findings.append({"kind": "overloaded_capability", "subject": c,
                             "detail": f"{n} open tasks for {providers[c]} templates",
                             "action": "split heavy tasks (agentos workforce split) or add a specialist"})
    for d in conn.execute(
            "SELECT d.function, d.objective_id FROM departments d JOIN objectives o ON o.id=d.objective_id "
            "WHERE o.project_id=? AND d.dissolved_at IS NULL", (project_id,)):
        still = conn.execute(f"SELECT 1 FROM tasks WHERE objective_id=? AND department=? AND state IN "
                             f"({','.join('?' * len(OPEN))})", (d["objective_id"], d["function"], *OPEN)).fetchone()
        if not still:
            findings.append({"kind": "idle_department", "subject": f"{d['objective_id']}/{d['function']}",
                             "detail": "no open tasks", "action": "agentos workforce contract"})
    return {"project_id": project_id, "findings": findings, "counts": dict(Counter(f["kind"] for f in findings))}


# --- failure pattern detection ---

_NOISE = [(re.compile(r"[A-Za-z]:[\\/][^\s'\"]+|/[^\s'\"]+/[^\s'\"]+"), "<path>"),
          # a quoted value starts after a non-letter, so the apostrophe in "can't" is not a quote
          (re.compile(r"(?<![A-Za-z])(['\"])[^'\"\n]*\1"), "<str>"),
          (re.compile(r"\b[0-9a-f]{7,}\b"), "<hex>"), (re.compile(r"\d+(\.\d+)?"), "<n>")]


def signature(output_tail: str, timed_out: bool = False) -> str:
    """A failure's normalised last error line: paths, quoted values, hashes and numbers removed."""
    if timed_out:
        return "timed out"
    lines = [x.strip() for x in output_tail.splitlines() if x.strip()]
    errs = [x for x in lines if re.search(r"error|exception|failed|fatal|traceback", x, re.IGNORECASE)]
    line = (errs or lines or ["(no output)"])[-1]
    for pat, rep in _NOISE:
        line = pat.sub(rep, line)
    return _norm(line)[:200]


def _pattern_text(p: dict) -> str:
    if p["kind"] == "error":
        return f"Recurring failure ({p['count']}x): {p['signature']} from {', '.join(p['commands'])}"
    if p["kind"] == "weak_dimension":
        return f"{p['template_id']} is repeatedly weakest on {p['dimension']} ({p['count']} failing evaluations)"
    return f"Tasks needing {p['capability']} failed or were retried {p['count']} times"


def failure_patterns(conn: sqlite3.Connection, project_id: str, min_count: int = 2, actor: str | None = None,
                     record: bool = False) -> dict:
    groups: dict[str, dict] = {}
    for row in conn.execute("SELECT * FROM evidence WHERE project_id=? AND (exit_code<>0 OR timed_out=1) "
                            "ORDER BY started_at, rowid", (project_id,)):
        sig = signature(row["output_tail"], bool(row["timed_out"]))
        g = groups.setdefault(sig, {"kind": "error", "signature": sig, "count": 0, "evidence": [], "commands": set()})
        g["count"] += 1
        g["evidence"].append(row["id"])
        g["commands"].add(_command(row))
    patterns = [dict(g, commands=sorted(g["commands"])) for g in groups.values() if g["count"] >= min_count]
    weak: Counter = Counter()
    for r in conn.execute("SELECT e.template_id, e.scores FROM evaluations e JOIN agent_instances a "
                          "ON a.id=e.instance_id WHERE a.project_id=? AND e.weighted < 50 AND e.external_cause=0",
                          (project_id,)):
        scores = json.loads(r["scores"])
        if scores:
            weak[(r["template_id"], min(scores, key=lambda k: (scores[k], k)))] += 1
    patterns += [{"kind": "weak_dimension", "template_id": tid, "dimension": dim, "count": n}
                 for (tid, dim), n in sorted(weak.items()) if n >= min_count]
    failed: Counter = Counter()
    for t in tasks.list_tasks(conn, project_id):
        if t.state == "failed" or t.retries:
            failed.update(t.capabilities or ["general"])
    patterns += [{"kind": "failing_capability", "capability": c, "count": n}
                 for c, n in sorted(failed.items()) if n >= min_count]
    patterns.sort(key=lambda p: (-p["count"], p["kind"]))
    recorded = [memory.add(conn, project_id, Layer.failure, _pattern_text(p), source="intel.failures",
                           author=actor or "agentos", confidence=0.7, tags=["pattern", p["kind"]]).id
                for p in patterns] if record else []
    return {"project_id": project_id, "patterns": patterns, "recorded": recorded}


# --- competitive solution evaluation ---

def compete(conn: sqlite3.Connection, task_id: str, min_margin: float = 2.0) -> dict:
    """Rank competing solutions to one task by their independent evaluations. A grade from another
    competitor is discarded, a flag or failing evidence disqualifies, and a lead under `min_margin`
    is no clear winner."""
    t = tasks.get_task(conn, task_id)
    rows = list(conn.execute("SELECT e.* FROM evaluations e JOIN agent_instances a ON a.id=e.instance_id "
                             "WHERE a.task_id=? ORDER BY e.created_at, e.rowid", (t.id,)))
    competitors = {r["instance_id"] for r in rows}
    entries: dict[str, dict] = {}
    for a in conn.execute("SELECT id, template_id, template_version FROM agent_instances WHERE task_id=? "
                          "ORDER BY created_at, rowid", (t.id,)):
        # Every worker on the task that could write a solution competes, graded or not; only read-only
        # workers (reviewers, researchers) that nobody graded can act as judges.
        try:
            judge_only = templates.get_template(conn, a["template_id"], a["template_version"]).read_only
        except NotFound:
            judge_only = False
        if a["id"] not in competitors and not judge_only:
            competitors.add(a["id"])
            entries[a["id"]] = {"instance_id": a["id"], "template_id": a["template_id"], "scores": [],
                                "evaluators": set(), "discarded": [], "disqualified": set()}
    for r in rows:
        e = entries.setdefault(r["instance_id"], {"instance_id": r["instance_id"], "template_id": r["template_id"],
                                                  "scores": [], "evaluators": set(), "discarded": [],
                                                  "disqualified": set()})
        if r["evaluator_id"] in competitors:
            e["discarded"].append({"evaluation_id": r["id"], "reason": "evaluator_is_competitor"})
            continue
        e["scores"].append(r["weighted"])
        e["evaluators"].add(r["evaluator_id"])
        e["disqualified"].update(f"flagged:{f}" for f in json.loads(r["flags"]))
        for eid in json.loads(r["evidence"]):
            ev = conn.execute("SELECT exit_code, timed_out FROM evidence WHERE id=?", (eid,)).fetchone()
            if not ev or ev["exit_code"] != 0 or ev["timed_out"]:
                e["disqualified"].add(f"failing_evidence:{eid}")
    ranked = []
    for e in entries.values():
        if not e["scores"]:
            e["disqualified"].add("no_independent_evaluation")
        ranked.append({"instance_id": e["instance_id"], "template_id": e["template_id"],
                       "mean": round(statistics.fmean(e["scores"]), 2) if e["scores"] else None,
                       "evaluations": len(e["scores"]), "evaluators": sorted(e["evaluators"]),
                       "discarded": e["discarded"], "disqualified": sorted(e["disqualified"])})
    ranked.sort(key=lambda x: (x["mean"] is None, -(x["mean"] or 0), x["instance_id"]))
    eligible = [x for x in ranked if not x["disqualified"]]
    margin = None
    if not eligible:
        verdict, winner = "no_eligible_solution", None
    elif len(eligible) == 1:
        verdict, winner = "only_one_eligible", eligible[0]["instance_id"]
    else:
        margin = round(eligible[0]["mean"] - eligible[1]["mean"], 2)
        verdict, winner = ("winner", eligible[0]["instance_id"]) if margin >= min_margin else ("no_clear_winner", None)
    return {"task_id": t.id, "verdict": verdict, "winner": winner, "margin": margin, "min_margin": min_margin,
            "solutions": ranked}


# --- independent governance ---

def governance_check(conn: sqlite3.Connection) -> dict:
    """Re-derive the core invariants from the raw tables, independently of the code that enforces them."""
    checks = []

    def add(name: str, violations: list, what: str) -> None:
        checks.append({"name": name, "ok": not violations, "count": len(violations), "violations": violations[:20],
                       "checks": what})

    v = audit.verify_chain(conn)
    add("audit_chain", [] if v.ok else [f"{v.reason} at seq {v.first_bad_seq}"], "the audit log hash chain")
    add("evaluator_independence",
        [r["id"] for r in conn.execute("SELECT id, instance_id, evaluator_id FROM evaluations")
         if r["evaluator_id"] == r["instance_id"] or r["evaluator_id"] in performance._relatives(conn,
                                                                                                 r["instance_id"])],
        "no evaluation by the worker itself, its parents or its children")
    bad = []
    for r in conn.execute("SELECT a.task_id, a.evidence_id, e.instance_id FROM task_acceptances a "
                          "LEFT JOIN evaluations e ON e.id=a.evaluation_id"):
        ev = conn.execute("SELECT exit_code, timed_out FROM evidence WHERE id=?", (r["evidence_id"],)).fetchone()
        inst = conn.execute("SELECT task_id FROM agent_instances WHERE id=?", (r["instance_id"],)).fetchone()
        if not ev or ev[0] != 0 or ev[1] or not inst or inst[0] != r["task_id"]:
            bad.append(r["task_id"])
    add("evidence_backed_acceptance", bad, "every accepted task has passing evidence and its own evaluation")
    bad = []
    for r in conn.execute("SELECT id, gate_evidence, result FROM experiments WHERE status IN "
                          "('promoted', 'rolled_back')"):
        gate = json.loads(r["gate_evidence"])
        rows_ = [conn.execute("SELECT exit_code, timed_out FROM evidence WHERE id=?", (g,)).fetchone() for g in gate]
        passed = [x is not None and x[0] == 0 and not x[1] for x in rows_]
        if not gate or not all(passed) or not r["result"]:
            bad.append(r["id"])
    add("gated_promotions", bad, "every promoted change passed its regression and security gate")
    lim = governor.get_limits(conn)
    spent = governor._used(conn, "global", "*", "usd")
    add("paid_spend_cap", [f"spent {spent} over cap {lim.max_paid_spend_usd}"] if spent > lim.max_paid_spend_usd
        else [], "paid spend never above the owner's cap")
    slots = lifecycle.slot_count(conn)
    add("concurrency", [f"{slots} slots held, limit {lim.max_concurrent}"] if slots > lim.max_concurrent else [],
        "workers holding a slot never exceed max_concurrent")
    add("candidates_isolated", [r[0] for r in conn.execute(
        "SELECT a.id FROM agent_instances a JOIN agent_templates t ON t.id=a.template_id AND "
        "t.version=a.template_version WHERE t.status='candidate' AND NOT EXISTS (SELECT 1 FROM trials tr "
        "WHERE tr.task_id=a.task_id AND tr.template_id=a.template_id)")],
        "experiment challengers ran only on their own trial tasks")
    add("org_memory_validated",
        [r[0] for r in conn.execute("SELECT id FROM memory WHERE scope='org' AND validated=0 AND deleted=0")],
        "knowledge shared across projects is validated")
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


# --- resource forecasting ---

def _work_hours(conn, task_id: str) -> float:
    """Hours from the task's first start to its completion, from the audit log (queue time excluded)."""
    row = conn.execute(
        "SELECT min(CASE WHEN json_extract(payload, '$.to')='running' THEN ts END), "
        "max(CASE WHEN json_extract(payload, '$.to')='done' THEN ts END) FROM events "
        "WHERE kind='task.state' AND json_extract(payload, '$.task_id')=?", (task_id,)).fetchone()
    if not (row[0] and row[1]):  # pragma: no cover - set_state always logs both
        row = conn.execute("SELECT created_at, updated_at FROM tasks WHERE id=?", (task_id,)).fetchone()
    return max(0.0, (_ts(row[1]) - _ts(row[0])).total_seconds() / 3600)


def forecast(conn: sqlite3.Connection, project_id: str, objective_id: str | None = None) -> dict:
    """Remaining effort times what finished work cost per unit of effort, against the budgets left."""
    open_tasks = _open_tasks(conn, project_id, objective_id)
    remaining = sum(_effort(conn, t.id) for t in open_tasks)
    done, basis = _done_history(conn, project_id)
    out = {"project_id": project_id, "objective_id": objective_id, "open_tasks": len(open_tasks),
           "remaining_effort": remaining, "history_basis": basis, "history_tasks": len(done),
           "history_weight": round(min(len(done), 10) / 10, 2)}  # finished tasks counted, capped at 10
    if not done:
        return out | {"projected": None, "warnings": [], "note": "no finished tasks yet: nothing to forecast from"}
    marks = ",".join("?" * len(done))
    effort_done = sum(_effort(conn, t) for t in done)
    runs = conn.execute(f"SELECT count(*) FROM agent_instances WHERE task_id IN ({marks})", done).fetchone()[0]
    toks = conn.execute(f"SELECT coalesce(sum(coalesce(actual, amount)), 0) FROM reservations WHERE scope='task' "
                        f"AND kind='tokens_est' AND scope_id IN ({marks})", done).fetchone()[0]
    hours = [_work_hours(conn, t) for t in done]
    waves = len(_layers(open_tasks))
    projected = {"agent_runs": math.ceil(remaining * runs / effort_done),
                 "tokens_est": math.ceil(remaining * toks / effort_done),
                 "hours_est": round(waves * statistics.median(hours), 2), "usd": 0.0}
    warnings = []
    for scope, sid in (("project", project_id), ("global", "*")):
        for kind in ("agent_runs", "tokens_est"):
            row = conn.execute("SELECT limit_value FROM budgets WHERE scope=? AND scope_id=? AND kind=?",
                               (scope, sid, kind)).fetchone()
            if row and projected[kind] > row[0] - governor._used(conn, scope, sid, kind):
                warnings.append({"scope": scope, "kind": kind, "projected": projected[kind],
                                 "remaining": row[0] - governor._used(conn, scope, sid, kind),
                                 "action": "re-plan the work, or ask the owner to raise the budget"})
    return out | {"per_effort_unit": {"agent_runs": round(runs / effort_done, 3),
                                      "tokens_est": round(toks / effort_done, 1)},
                  "projected": projected, "waves": waves, "warnings": warnings,
                  "note": "estimates from finished work; usd stays 0 unless the owner authorises paid spend"}


# --- project-specific intelligence ---

def project_profile(conn: sqlite3.Connection, project_id: str) -> dict:
    states = Counter(t.state.value for t in tasks.list_tasks(conn, project_id))
    finished = states["done"] + states["failed"]
    grades: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for r in conn.execute("SELECT e.template_id, e.weighted, t.capabilities FROM evaluations e "
                          "JOIN agent_instances a ON a.id=e.instance_id JOIN tasks t ON t.id=a.task_id "
                          "WHERE a.project_id=? AND e.external_cause=0", (project_id,)):
        for c in json.loads(r["capabilities"]) or ["general"]:
            grades[c][r["template_id"]].append(r["weighted"])
    leaders = {}
    for c, by_t in sorted(grades.items()):
        tid, ws = max(by_t.items(), key=lambda kv: (statistics.fmean(kv[1]), len(kv[1]), kv[0]))
        leaders[c] = {"template_id": tid, "mean": round(statistics.fmean(ws), 1), "evaluations": len(ws)}
    return {"project_id": project_id, "tasks": dict(states),
            "success_rate": round(states["done"] / finished, 3) if finished else None,
            "best_by_capability": leaders, "top_failures": failure_patterns(conn, project_id)["patterns"][:3],
            "proven_commands": [c["command"] for c in skill_candidates(conn, project_id)][:3]}


# --- validated cross-project learning ---

def lessons(conn: sqlite3.Connection, min_projects: int = 2) -> list[dict]:
    """Validated project lessons that at least `min_projects` projects reached on their own, not shared yet."""
    shared = {_norm(r[0]) for r in conn.execute(
        "SELECT content FROM memory WHERE scope='org' AND deleted=0 AND superseded=0")}
    layers = [x.value for x in ORG_LAYERS]
    groups: dict[str, dict] = {}
    for r in conn.execute(f"SELECT * FROM memory WHERE scope='project' AND validated=1 AND deleted=0 AND "
                          f"superseded=0 AND layer IN ({','.join('?' * len(layers))}) ORDER BY created_at, rowid",
                          layers):
        key = _norm(r["content"])
        if key not in shared:
            g = groups.setdefault(key, {"content": r["content"], "layer": r["layer"], "projects": set(),
                                        "records": []})
            g["projects"].add(r["project_id"])
            g["records"].append(r["id"])
    return [dict(g, projects=sorted(g["projects"])) for g in groups.values() if len(g["projects"]) >= min_projects]


def share_lesson(conn: sqlite3.Connection, record_id: str, actor: str, min_projects: int = 2) -> dict:
    rec = memory.inspect(conn, record_id)
    if rec.scope != "project" or rec.deleted or rec.superseded:
        raise PolicyDenied("only a current project record can be shared", reasons=["not_a_project_record"])
    if not rec.validated:
        raise PolicyDenied("the lesson is not validated", reasons=["not_validated"])
    if rec.layer not in ORG_LAYERS:
        raise PolicyDenied(f"layer {rec.layer.value} cannot be shared across projects", reasons=["org_layer"])
    group = next((g for g in lessons(conn, min_projects) if record_id in g["records"]), None)
    if not group:
        raise PolicyDenied(f"the lesson has not been validated independently in {min_projects} projects",
                           reasons=["not_confirmed_elsewhere"])
    with write_tx(conn):
        org = memory.add(conn, rec.project_id, rec.layer, rec.content, source="lesson:" + ",".join(group["records"]),
                         author=actor, confidence=0.9, validated=True, scope="org", tags=["cross_project"])
        audit.append_event(conn, "intel.lesson_shared", actor, {"memory_id": org.id, "records": group["records"],
                                                               "projects": group["projects"]}, rec.project_id)
    return {"memory_id": org.id, "projects": group["projects"], "records": group["records"]}
