"""Tunable, non-sensitive policy values that the self-improvement engine may change.

Only what is registered here can be tuned, and only within its hard-coded bounds. Ownership,
security boundaries, approval requirements and hard resource limits are deliberately absent, so
no experiment can reach them. Values live in settings under `policy.`; only a promoted (or
rolled-back) experiment writes them."""

import sqlite3

from pydantic import BaseModel

from agentos.db import get_setting
from agentos.errors import PolicyDenied


class Policy(BaseModel):
    name: str
    default: float
    low: float
    high: float
    area: str
    description: str


REGISTRY: dict[str, Policy] = {p.name: p for p in [
    Policy(name="recruit.w_match", default=0.45, low=0.2, high=0.7, area="recruitment",
           description="weight of capability match when ranking templates"),
    Policy(name="recruit.w_history", default=0.25, low=0.0, high=0.5, area="recruitment",
           description="weight of the evaluated mean"),
    Policy(name="recruit.w_reliability", default=0.15, low=0.0, high=0.4, area="recruitment",
           description="weight of the non-failure rate"),
    Policy(name="recruit.w_confidence", default=0.15, low=0.0, high=0.4, area="recruitment",
           description="weight of how many evaluations back the record"),
]}


def spec(name: str) -> Policy:
    if name not in REGISTRY:
        raise PolicyDenied(f"{name} is not a tunable policy (tunable: {', '.join(sorted(REGISTRY))})",
                           reasons=["not_tunable"])
    return REGISTRY[name]


def check_value(name: str, value: float) -> float:
    p = spec(name)
    value = float(value)
    if not p.low <= value <= p.high:
        raise PolicyDenied(f"{name} must stay within {p.low:g}..{p.high:g}", reasons=["out_of_bounds"])
    return value


def get(conn: sqlite3.Connection, name: str, overrides: dict | None = None) -> float:
    p = spec(name)
    if overrides and name in overrides:
        return check_value(name, overrides[name])
    value = float(get_setting(conn, f"policy.{name}", p.default))
    return value if p.low <= value <= p.high else p.default


def current(conn: sqlite3.Connection) -> dict[str, float]:
    return {name: get(conn, name) for name in REGISTRY}
