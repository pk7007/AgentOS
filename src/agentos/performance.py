"""Independent evaluations and per-template performance summaries. Recommendations never act on their own."""

import json
import sqlite3
import statistics
from typing import Literal

from pydantic import BaseModel

from agentos import audit, lifecycle, templates
from agentos.db import write_tx
from agentos.errors import PolicyDenied, UsageError
from agentos.lifecycle import AgentState
from agentos.templates import TemplateStatus
from agentos.util import new_id, now_iso

WEIGHTS = {
    "quality": 0.25, "accuracy": 0.20, "reliability": 0.15, "instruction_compliance": 0.10,
    "security_compliance": 0.10, "cost_efficiency": 0.08, "speed": 0.07, "collaboration": 0.05,
}
MIN_EVIDENCE_FOR_RETIREMENT = 5
CRITICAL_SUBSCORE = 30
Flag = Literal["security_violation", "integrity_violation"]


class Evaluation(BaseModel):
    id: str
    instance_id: str
    template_id: str
    evaluator_id: str
    category: str
    scores: dict[str, float]
    weighted: float
    evidence: list[str]
    flags: list[str]
    external_cause: bool
    created_at: str


class PerfSummary(BaseModel):
    template_id: str
    category: str | None
    n: int
    mean: float | None
    recent_mean: float | None
    stdev: float | None
    confidence: float
    band: str
    recommendation: str
    consecutive_failures: int
    critical_count: int
    excluded_external: int
    failure_rate: float | None


def weighted(scores: dict[str, float]) -> float:
    if not scores:
        raise UsageError("at least one score is required")
    for key, value in scores.items():
        if key not in WEIGHTS:
            raise UsageError(f"unknown score '{key}'; allowed: {', '.join(WEIGHTS)}")
        if not 0 <= value <= 100:
            raise UsageError(f"score {key}={value} is outside 0-100")
    total_w = sum(WEIGHTS[k] for k in scores)
    return sum(WEIGHTS[k] * v for k, v in scores.items()) / total_w


def _relatives(conn, instance_id: str) -> set[str]:
    """The instance's ancestors and descendants: none of them may grade it."""
    related, node = set(), instance_id
    while node:
        row = conn.execute("SELECT parent_id FROM agent_instances WHERE id=?", (node,)).fetchone()
        node = row[0] if row else None
        if node:
            related.add(node)
    stack = [instance_id]
    while stack:
        for (child,) in conn.execute("SELECT id FROM agent_instances WHERE parent_id=?", (stack.pop(),)):
            if child not in related:
                related.add(child)
                stack.append(child)
    return related


def record_eval(conn: sqlite3.Connection, instance_id: str, evaluator_id: str, category: str,
                scores: dict[str, float], evidence: list[str], flags: list[Flag] | None = None,
                external_cause: bool = False, actor: str = "host") -> Evaluation:
    flags = list(flags or [])
    inst = lifecycle.get_instance(conn, instance_id)
    if evaluator_id == instance_id or evaluator_id in _relatives(conn, instance_id):
        raise PolicyDenied("an agent cannot be graded by itself, its parent or its children",
                           reasons=["self_evaluation"])
    if not [e for e in evidence if e and e.strip()]:
        raise PolicyDenied("an evaluation needs at least one evidence reference", reasons=["no_evidence"])
    bad = [f for f in flags if f not in ("security_violation", "integrity_violation")]
    if bad:
        raise UsageError(f"unknown flag(s): {', '.join(bad)}")
    value = weighted(scores)
    eid = new_id("ev")
    with write_tx(conn):
        conn.execute(
            "INSERT INTO evaluations(id, instance_id, template_id, evaluator_id, category, scores, weighted, evidence,"
            " flags, external_cause, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (eid, instance_id, inst.template_id, evaluator_id, category, json.dumps(scores), value,
             json.dumps(evidence), json.dumps(flags), int(external_cause), now_iso()))
        audit.append_event(conn, "eval.recorded", actor, {
            "evaluation_id": eid, "instance_id": instance_id, "evaluator_id": evaluator_id,
            "weighted": round(value, 2), "flags": flags}, inst.project_id)
        if flags:
            tpl = templates.get_template(conn, inst.template_id)
            if tpl.status in (TemplateStatus.active, TemplateStatus.suspended):
                templates.set_status(conn, inst.template_id, TemplateStatus.quarantined, actor,
                                     reason=f"flagged: {', '.join(flags)} (evaluation {eid})")
            if lifecycle.can_transition(inst.state, AgentState.QUARANTINED):
                lifecycle.transition(conn, instance_id, AgentState.QUARANTINED, actor, reason="flagged evaluation")
    return get_eval(conn, eid)


def get_eval(conn: sqlite3.Connection, eval_id: str) -> Evaluation:
    row = conn.execute("SELECT * FROM evaluations WHERE id=?", (eval_id,)).fetchone()
    return Evaluation(**(dict(row) | {"scores": json.loads(row["scores"]), "evidence": json.loads(row["evidence"]),
                                      "flags": json.loads(row["flags"]),
                                      "external_cause": bool(row["external_cause"])}))


def _band(mean: float | None) -> str:
    if mean is None:
        return "unrated"
    for floor, name in ((95, "elite"), (85, "reliable"), (70, "monitor"), (50, "improve")):
        if mean >= floor:
            return name
    return "suspend_review"


def summary(conn: sqlite3.Connection, template_id: str, category: str | None = None) -> PerfSummary:
    sql, params = "SELECT * FROM evaluations WHERE template_id=?", [template_id]
    if category:
        sql += " AND category=?"
        params.append(category)
    rows = list(conn.execute(sql + " ORDER BY created_at, rowid", params))
    counted = [r for r in rows if not r["external_cause"]]
    values = [r["weighted"] for r in counted]
    n = len(values)
    mean = statistics.fmean(values) if values else None
    band = _band(mean)
    consecutive = 0
    for v in reversed(values):
        if v >= 50:
            break
        consecutive += 1
    failing_evaluators = {r["evaluator_id"] for r in counted if r["weighted"] < 50}
    if n < MIN_EVIDENCE_FOR_RETIREMENT:
        rec = "insufficient_evidence"
    elif band == "suspend_review" and len(failing_evaluators) >= 2:
        rec = "retire_review"
    elif band in ("improve", "suspend_review"):
        rec = "retrain"
    else:
        rec = "retain"
    critical = sum(1 for r in rows if any(v < CRITICAL_SUBSCORE for v in json.loads(r["scores"]).values()))
    return PerfSummary(
        template_id=template_id, category=category, n=n, mean=mean,
        recent_mean=statistics.fmean(values[-5:]) if values else None,
        stdev=statistics.pstdev(values) if n > 1 else None, confidence=min(n, 5) / 5, band=band,
        recommendation=rec, consecutive_failures=consecutive, critical_count=critical,
        excluded_external=len(rows) - n, failure_rate=(sum(1 for v in values if v < 50) / n) if n else None)
