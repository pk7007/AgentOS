"""Rank active templates for a set of required capabilities. Weights are uncalibrated heuristics."""

import sqlite3

from pydantic import BaseModel

from agentos import performance, templates
from agentos.templates import TemplateStatus

HIGH_RISK_MIN_EVALS = 3
HIGH_RISK_MIN_MEAN = 85


class Candidate(BaseModel):
    template_id: str
    version: int
    score: float
    match: float
    reasons: list[str]


def _weights(conn: sqlite3.Connection, overrides: dict | None = None) -> dict[str, float]:
    """The ranking weights: the defaults, unless a validated experiment promoted other values."""
    from agentos import policy

    return {k: policy.get(conn, f"recruit.w_{k}", overrides)
            for k in ("match", "history", "reliability", "confidence")}


def rank(conn: sqlite3.Connection, required: list[str], category: str | None = None,
         high_risk: bool = False, weights: dict | None = None) -> list[Candidate]:
    req = {c.strip().lower() for c in required if c.strip()}
    if not req:
        return []
    w = _weights(conn, weights)
    out = []
    for t in templates.list_templates(conn, TemplateStatus.active):
        caps = {c.lower() for c in t.capabilities}
        match = len(caps & req) / len(req)
        if match == 0:
            continue
        s = performance.summary(conn, t.id, category)
        if high_risk and (s.n < HIGH_RISK_MIN_EVALS or (s.mean or 0) < HIGH_RISK_MIN_MEAN):
            continue
        history = (s.mean / 100) if s.n else 0.5
        reliability = (1 - s.failure_rate) if s.n else 0.5
        score = (w["match"] * match + w["history"] * history + w["reliability"] * reliability
                 + w["confidence"] * s.confidence)
        reasons = [f"match {match:.0%}", f"evaluations {s.n}"]
        if s.n:
            reasons.append(f"mean {s.mean:.1f}")
        if s.critical_count:
            reasons.append(f"critical scores {s.critical_count}")
        out.append(Candidate(template_id=t.id, version=t.version, score=round(score, 4), match=match,
                             reasons=reasons))
    return sorted(out, key=lambda c: (-c.score, c.template_id))


def missing_capabilities(conn: sqlite3.Connection, required: list[str]) -> list[str]:
    have = {c.lower() for t in templates.list_templates(conn, TemplateStatus.active) for c in t.capabilities}
    return [c for c in required if c.strip().lower() not in have]
