"""Tunable policies: only registered names, only within bounds, and recruitment reads them."""

import pytest

from agentos import policy, recruit
from agentos.db import put_setting
from agentos.errors import PolicyDenied


def test_defaults_match_the_documented_weights(conn):
    assert policy.current(conn) == {"recruit.w_match": 0.45, "recruit.w_history": 0.25,
                                    "recruit.w_reliability": 0.15, "recruit.w_confidence": 0.15}


@pytest.mark.parametrize("name", ["governor.max_concurrent", "approval.ttl", "owner", "recruit.w_unknown"])
def test_sensitive_or_unknown_names_are_not_tunable(conn, name):
    with pytest.raises(PolicyDenied) as e:
        policy.check_value(name, 0.3)
    assert e.value.reasons == ["not_tunable"]


def test_values_must_stay_within_bounds(conn):
    assert policy.check_value("recruit.w_match", 0.7) == 0.7
    with pytest.raises(PolicyDenied) as e:
        policy.check_value("recruit.w_match", 0.71)
    assert e.value.reasons == ["out_of_bounds"]
    with pytest.raises(PolicyDenied):
        policy.get(conn, "recruit.w_history", {"recruit.w_history": -0.1})


def test_a_stored_value_out_of_bounds_falls_back_to_the_default(conn):
    put_setting(conn, "policy.recruit.w_match", 5)
    assert policy.get(conn, "recruit.w_match") == 0.45
    put_setting(conn, "policy.recruit.w_match", 0.6)
    assert policy.get(conn, "recruit.w_match") == 0.6


def test_recruitment_ranks_with_the_stored_and_overridden_weights(seeded):
    base = {c.template_id: c.score for c in recruit.rank(seeded, ["python", "research"])}
    put_setting(seeded, "policy.recruit.w_match", 0.2)
    lowered = {c.template_id: c.score for c in recruit.rank(seeded, ["python", "research"])}
    assert lowered["implementer"] < base["implementer"]
    override = {c.template_id: c.score for c in recruit.rank(seeded, ["python", "research"],
                                                                 weights={"recruit.w_match": 0.45})}
    assert override == base
