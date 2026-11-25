import pytest

from agentos import db, governor
from agentos.errors import PolicyDenied


def test_defaults(conn):
    lim = governor.get_limits(conn)
    assert (lim.max_concurrent, lim.max_depth, lim.max_retries, lim.max_agents_per_task) == (4, 2, 2, 12)
    assert lim.max_paid_spend_usd == 0.0 and lim.max_remediation_rounds == 5


def test_lower_limit_ok(conn):
    governor.set_limit(conn, "max_concurrent", 2, actor="t")
    assert governor.get_limits(conn).max_concurrent == 2


def test_raise_limit_needs_owner(conn, owner):
    with pytest.raises(PolicyDenied) as e:
        governor.set_limit(conn, "max_concurrent", 8, actor="t")
    assert "owner_required" in e.value.reasons
    with pytest.raises(PolicyDenied):
        governor.set_limit(conn, "max_concurrent", 8, actor="t", owner=object())
    governor.set_limit(conn, "max_concurrent", 8, actor="t", owner=owner)
    assert governor.get_limits(conn).max_concurrent == 8


def test_unknown_limit_rejected(conn):
    with pytest.raises(PolicyDenied):
        governor.set_limit(conn, "max_power", 1, actor="t")


def test_host_limit_tightens(conn):
    governor.set_host_limit(conn, "codex", "max_concurrent", 2, actor="t")
    assert governor.get_limits(conn).max_concurrent == 2
    governor.set_host_limit(conn, "codex", "max_concurrent", 9, actor="t")
    assert governor.get_limits(conn).max_concurrent == 4


def test_paid_spend_blocked(conn):
    with pytest.raises(PolicyDenied) as e:
        with db.write_tx(conn):
            governor.reserve(conn, [("global", "*")], "usd", 0.01, holder="x")
    assert "paid_spend_blocked" in e.value.reasons


def test_usd_budget_above_cap_needs_owner(conn):
    with pytest.raises(PolicyDenied) as e:
        governor.set_budget(conn, "global", "*", "usd", 5.0, actor="t")
    assert "owner_required" in e.value.reasons


def test_budget_exceeded_and_release(conn):
    governor.set_budget(conn, "project", "p1", "tokens_est", 100, actor="t")
    chain = [("global", "*"), ("project", "p1")]
    with db.write_tx(conn):
        rid = governor.reserve(conn, chain, "tokens_est", 80, holder="a")
    with pytest.raises(PolicyDenied) as e:
        with db.write_tx(conn):
            governor.reserve(conn, chain, "tokens_est", 30, holder="b")
    assert "budget_exceeded:project:tokens_est" in e.value.reasons
    with db.write_tx(conn):
        governor.release(conn, rid, actual=40)
        governor.reserve(conn, chain, "tokens_est", 30, holder="b")
    assert governor.budget_report(conn)[0]["used"] == 70
