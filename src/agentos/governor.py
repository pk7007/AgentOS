"""Limits, budgets and atomic reservations."""

import sqlite3
from typing import Literal

from pydantic import BaseModel

from agentos import audit
from agentos.db import get_setting, put_setting, write_tx
from agentos.errors import PolicyDenied
from agentos.util import new_id, now_iso

BudgetKind = Literal["agent_runs", "tokens_est", "usd"]
Scope = Literal["global", "project", "task"]


class Limits(BaseModel):
    max_concurrent: int = 4
    max_depth: int = 2
    max_retries: int = 2
    max_agents_per_task: int = 12
    max_paid_spend_usd: float = 0.0
    max_remediation_rounds: int = 5


FIELDS = tuple(Limits.model_fields)


def _local(conn) -> Limits:
    defaults = Limits()
    return Limits(**{f: get_setting(conn, f"limits.{f}", getattr(defaults, f)) for f in FIELDS})


def get_limits(conn: sqlite3.Connection) -> Limits:
    lim = _local(conn).model_dump()
    for key, value in conn.execute("SELECT key, value FROM settings WHERE key LIKE 'host.%'"):
        parts = key.split(".")
        if len(parts) == 3 and parts[2] in lim:
            lim[parts[2]] = min(lim[parts[2]], type(lim[parts[2]])(get_setting(conn, key)))
    return Limits(**lim)


def _check_field(field: str) -> None:
    if field not in FIELDS:
        raise PolicyDenied(f"unknown limit: {field}", reasons=["unknown_limit"])


def set_limit(conn: sqlite3.Connection, field: str, value: float, actor: str, owner: object | None = None) -> Limits:
    _check_field(field)
    current = getattr(_local(conn), field)
    value = type(current)(value)
    if value > current and owner is None:
        raise PolicyDenied(f"raising {field} from {current} to {value} needs the owner", reasons=["owner_required"])
    with write_tx(conn):
        put_setting(conn, f"limits.{field}", value)
        audit.append_event(conn, "limits.set", actor, {"field": field, "from": current, "to": value,
                                                       "owner_confirmed": owner is not None})
    return get_limits(conn)


def set_host_limit(conn: sqlite3.Connection, host: str, field: str, value: float, actor: str) -> Limits:
    """Record a limit reported by a host. It can only ever tighten the effective limit."""
    _check_field(field)
    with write_tx(conn):
        put_setting(conn, f"host.{host}.{field}", value)
        audit.append_event(conn, "limits.host", actor, {"host": host, "field": field, "value": value})
    return get_limits(conn)


def set_budget(conn: sqlite3.Connection, scope: Scope, scope_id: str, kind: BudgetKind, limit: float,
               actor: str, owner: object | None = None) -> None:
    if kind == "usd" and limit > get_limits(conn).max_paid_spend_usd and owner is None:
        raise PolicyDenied("a paid-spend budget above the cap needs the owner", reasons=["owner_required"])
    with write_tx(conn):
        conn.execute(
            "INSERT INTO budgets VALUES (?,?,?,?) ON CONFLICT(scope, scope_id, kind) "
            "DO UPDATE SET limit_value=excluded.limit_value", (scope, scope_id, kind, float(limit)))
        audit.append_event(conn, "budget.set", actor, {"scope": scope, "scope_id": scope_id, "kind": kind,
                                                       "limit": limit, "owner_confirmed": owner is not None})


def _used(conn, scope, scope_id, kind) -> float:
    row = conn.execute(
        "SELECT coalesce(sum(coalesce(actual, amount)), 0) FROM reservations "
        "WHERE scope=? AND scope_id=? AND kind=?", (scope, scope_id, kind)).fetchone()
    return float(row[0])


def reserve(conn: sqlite3.Connection, chain: list[tuple[str, str]], kind: BudgetKind, amount: float,
            holder: str) -> str:
    """Reserve `amount` on every scope in `chain`. Call inside the caller's write_tx."""
    with write_tx(conn):
        if kind == "usd" and amount > get_limits(conn).max_paid_spend_usd:
            raise PolicyDenied("paid spend is blocked by the owner's cap", reasons=["paid_spend_blocked"])
        reasons = []
        for scope, scope_id in chain:
            row = conn.execute("SELECT limit_value FROM budgets WHERE scope=? AND scope_id=? AND kind=?",
                               (scope, scope_id, kind)).fetchone()
            if row and _used(conn, scope, scope_id, kind) + amount > row[0]:
                reasons.append(f"budget_exceeded:{scope}:{kind}")
        if reasons:
            raise PolicyDenied("budget exceeded", reasons=reasons)
        rid = new_id("rsv")
        for scope, scope_id in chain:
            conn.execute(
                "INSERT INTO reservations(id, scope, scope_id, kind, amount, holder, state, created_at) "
                "VALUES (?,?,?,?,?,?,'open',?)", (f"{rid}:{scope}", scope, scope_id, kind, amount, holder, now_iso()))
    return rid


def release(conn: sqlite3.Connection, reservation_id: str, actual: float | None = None) -> None:
    with write_tx(conn):
        conn.execute("UPDATE reservations SET state='released', actual=coalesce(?, actual) "
                     "WHERE id LIKE ? AND state='open'", (actual, f"{reservation_id}:%"))


def release_for_instance(conn: sqlite3.Connection, instance_id: str) -> None:
    with write_tx(conn):
        conn.execute("UPDATE reservations SET state='released' WHERE holder=? AND state='open'", (instance_id,))


def budget_report(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for r in conn.execute("SELECT * FROM budgets ORDER BY scope, scope_id, kind"):
        used = _used(conn, r["scope"], r["scope_id"], r["kind"])
        out.append({"scope": r["scope"], "scope_id": r["scope_id"], "kind": r["kind"],
                    "limit": r["limit_value"], "used": used, "remaining": r["limit_value"] - used,
                    "measurement": "estimate" if r["kind"] == "tokens_est" else "counted"})
    return out
