import itertools

import pytest

from agentos import lifecycle
from agentos.errors import PolicyDenied
from agentos.lifecycle import TRANSITIONS, AgentState


@pytest.mark.parametrize("a,b", [(a, b) for a in AgentState for b in TRANSITIONS[a]])
def test_all_legal_transitions_allowed(a, b):
    assert lifecycle.can_transition(a, b)


def test_every_other_pair_rejected():
    legal = {(a, b) for a in AgentState for b in TRANSITIONS[a]}
    rejected = [(a, b) for a, b in itertools.product(AgentState, AgentState) if (a, b) not in legal]
    assert len(AgentState) == 17
    assert len(rejected) == 17 * 17 - len(legal)
    assert not any(lifecycle.can_transition(a, b) for a, b in rejected)


def test_archived_is_terminal():
    assert TRANSITIONS[AgentState.ARCHIVED] == frozenset()


def test_transition_and_active_count(conn, instance):
    assert lifecycle.active_count(conn) == 1
    inst = lifecycle.transition(conn, instance, AgentState.COMPLETED, actor="t", reason="done")
    assert inst.state == AgentState.COMPLETED and lifecycle.active_count(conn) == 0


def test_terminate_unconfirmed_is_recorded(conn, instance):
    lifecycle.transition(conn, instance, AgentState.CANCELLED, actor="t")
    inst = lifecycle.transition(conn, instance, AgentState.TERMINATED, actor="t", runtime_confirmed=False)
    assert inst.termination_confirmed is False


def test_terminate_confirmed(conn, instance):
    lifecycle.transition(conn, instance, AgentState.CANCELLED, actor="t")
    inst = lifecycle.transition(conn, instance, AgentState.TERMINATED, actor="t", runtime_confirmed=True)
    assert inst.termination_confirmed is True


def test_illegal_transition_audited(conn, instance):
    with pytest.raises(PolicyDenied) as e:
        lifecycle.transition(conn, instance, AgentState.RECRUITED, actor="t")
    assert "illegal_transition" in e.value.reasons
    n = conn.execute("SELECT count(*) FROM events WHERE kind='agent.transition_denied'").fetchone()[0]
    assert n == 1
