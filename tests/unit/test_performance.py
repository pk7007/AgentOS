import pytest

from agentos import lifecycle, performance, templates
from agentos.errors import PolicyDenied, UsageError
from agentos.lifecycle import AgentState
from agentos.performance import WEIGHTS
from agentos.templates import TemplateStatus
from agentos.util import new_id, now_iso

GOOD = {k: 90 for k in WEIGHTS}
BAD = {k: 40 for k in WEIGHTS}


def _child(conn, parent_id, project, task):
    iid, ts = new_id("ag"), now_iso()
    conn.execute(
        "INSERT INTO agent_instances(id, template_id, template_version, project_id, task_id, parent_id, depth,"
        " host, state, created_at, updated_at) VALUES (?, 'reviewer', 1, ?, ?, ?, 1, 'test', 'RUNNING', ?, ?)",
        (iid, project.id, task.id, parent_id, ts, ts))
    return iid


def _rec(conn, inst, evaluator="rev1", scores=GOOD, **kw):
    return performance.record_eval(conn, inst, evaluator, "coding", scores, evidence=["pytest -q"],
                                   actor="t", **kw)


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1) < 1e-9


def test_weighted_renormalizes_missing_keys():
    assert performance.weighted({"quality": 80}) == pytest.approx(80)
    assert performance.weighted(GOOD) == pytest.approx(90)


def test_score_out_of_range_rejected(conn, instance):
    with pytest.raises(UsageError):
        _rec(conn, instance, scores={"quality": 120})
    with pytest.raises(UsageError):
        _rec(conn, instance, scores={"vibes": 50})


def test_self_eval_rejected(conn, instance):
    with pytest.raises(PolicyDenied) as e:
        _rec(conn, instance, evaluator=instance)
    assert "self_evaluation" in e.value.reasons


def test_parent_and_child_eval_rejected(conn, instance, project, task):
    child = _child(conn, instance, project, task)
    with pytest.raises(PolicyDenied):
        _rec(conn, child, evaluator=instance)
    with pytest.raises(PolicyDenied):
        _rec(conn, instance, evaluator=child)


def test_no_evidence_rejected(conn, instance):
    with pytest.raises(PolicyDenied) as e:
        performance.record_eval(conn, instance, "rev1", "coding", GOOD, evidence=[], actor="t")
    assert "no_evidence" in e.value.reasons


def test_security_flag_quarantines(conn, instance):
    _rec(conn, instance, flags=["security_violation"])
    assert templates.get_template(conn, "implementer").status == TemplateStatus.quarantined
    assert lifecycle.get_instance(conn, instance).state == AgentState.QUARANTINED


def test_insufficient_evidence_under_5(conn, instance):
    for i in range(4):
        _rec(conn, instance, evaluator=f"r{i}", scores=BAD)
    s = performance.summary(conn, "implementer")
    assert s.n == 4 and s.recommendation == "insufficient_evidence" and s.confidence == pytest.approx(0.8)


def test_retire_review_needs_two_evaluators(conn, instance):
    for _ in range(5):
        _rec(conn, instance, evaluator="only-one", scores=BAD)
    s = performance.summary(conn, "implementer")
    assert s.band == "suspend_review" and s.recommendation != "retire_review"
    _rec(conn, instance, evaluator="second", scores=BAD)
    assert performance.summary(conn, "implementer").recommendation == "retire_review"


def test_bands_and_retain(conn, instance):
    for i in range(5):
        _rec(conn, instance, evaluator=f"r{i}")
    s = performance.summary(conn, "implementer")
    assert s.band == "reliable" and s.recommendation == "retain" and s.consecutive_failures == 0


def test_external_cause_excluded(conn, instance):
    _rec(conn, instance, scores=BAD, external_cause=True)
    _rec(conn, instance, scores=GOOD)
    s = performance.summary(conn, "implementer")
    assert s.n == 1 and s.mean == pytest.approx(90) and s.excluded_external == 1


def test_critical_visible_despite_high_mean(conn, instance):
    for i in range(4):
        _rec(conn, instance, evaluator=f"r{i}")
    _rec(conn, instance, evaluator="r9", scores=GOOD | {"security_compliance": 10})
    s = performance.summary(conn, "implementer")
    assert s.mean > 80 and s.critical_count == 1


def test_empty_summary(conn, seeded):
    s = performance.summary(conn, "reviewer")
    assert s.n == 0 and s.band == "unrated" and s.recommendation == "insufficient_evidence"
