import pytest

from agentos import lifecycle, performance, templates
from agentos.errors import PolicyDenied, UsageError
from agentos.lifecycle import AgentState
from agentos.performance import WEIGHTS
from agentos.templates import TemplateStatus
from agentos.util import new_id, now_iso
from tests.conftest import add_evidence, add_instance

GOOD = {k: 90 for k in WEIGHTS}
BAD = {k: 40 for k in WEIGHTS}


def _child(conn, parent_id, project, task):
    iid, ts = new_id("ag"), now_iso()
    conn.execute(
        "INSERT INTO agent_instances(id, template_id, template_version, project_id, task_id, parent_id, depth,"
        " host, state, created_at, updated_at) VALUES (?, 'reviewer', 1, ?, ?, ?, 1, 'test', 'RUNNING', ?, ?)",
        (iid, project.id, task.id, parent_id, ts, ts))
    return iid


_PEERS: dict = {}


def _rec(conn, inst, evaluator="rev1", scores=GOOD, **kw):
    """Grade `inst` as a named peer: each name is a registered reviewer instance of the same project."""
    row = conn.execute("SELECT project_id, task_id FROM agent_instances WHERE id=?", (inst,)).fetchone()
    project = type("P", (), {"id": row[0]})
    task = type("T", (), {"id": row[1]})
    key = (id(conn), row[0], evaluator)
    if not evaluator.startswith("ag_") and key not in _PEERS:
        _PEERS[key] = add_instance(conn, project, task)
    ev = _PEERS.get(key, evaluator)
    return performance.record_eval(conn, inst, ev, "coding", scores, evidence=[add_evidence(conn, row[0])],
                                   actor="t", **kw)


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1) < 1e-9


def test_weighted_renormalizes_missing_keys():
    assert performance.weighted({"quality": 80}) == pytest.approx(80)
    assert performance.weighted(GOOD) == pytest.approx(90)


def test_score_out_of_range_rejected(conn, instance):
    with pytest.raises(UsageError):
        _rec(conn, instance, scores=GOOD | {"quality": 120})
    with pytest.raises(UsageError):
        _rec(conn, instance, scores=GOOD | {"vibes": 50})


def test_every_score_is_required(conn, instance):
    with pytest.raises(UsageError) as e:
        _rec(conn, instance, scores={"quality": 100, "speed": 100})
    assert "accuracy" in e.value.message


def test_same_evaluator_grades_once_per_category(conn, instance):
    _rec(conn, instance, evaluator="dup")
    with pytest.raises(PolicyDenied) as e:
        _rec(conn, instance, evaluator="dup")
    assert "duplicate_evaluation" in e.value.reasons


def test_evidence_must_exist_and_belong_to_the_project(conn, instance, project, task):
    peer = add_instance(conn, project, task)
    with pytest.raises(PolicyDenied) as e:
        performance.record_eval(conn, instance, peer, "coding", GOOD, ["evd_000000000000"], actor="t")
    assert "unknown_evidence" in e.value.reasons
    old = add_evidence(conn, project.id)
    conn.execute("UPDATE evidence SET finished_at='2000-01-01T00:00:00Z' WHERE id=?", (old,))
    with pytest.raises(PolicyDenied) as e:
        performance.record_eval(conn, instance, peer, "coding", GOOD, [old], actor="t")
    assert "stale_evidence" in e.value.reasons


def test_owner_may_grade_only_with_confirmation(conn, instance, project, owner):
    proof = add_evidence(conn, project.id)
    with pytest.raises(PolicyDenied) as e:
        performance.record_eval(conn, instance, "owner", "coding", GOOD, [proof], actor="t")
    assert "owner_required" in e.value.reasons
    ev = performance.record_eval(conn, instance, "owner", "coding", GOOD, [proof, "looked at the diff"],
                                 actor="t", owner=owner)
    assert ev.evaluator_id == "owner" and ev.evidence == [proof, "looked at the diff"]


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


def test_no_evidence_rejected(conn, instance, project, task):
    with pytest.raises(PolicyDenied) as e:
        performance.record_eval(conn, instance, add_instance(conn, project, task), "coding", GOOD, evidence=[],
                                actor="t")
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


def test_retire_review_needs_two_evaluators(conn, instance, project, task):
    graded = [instance] + [add_instance(conn, project, task, template="implementer") for _ in range(4)]
    for inst in graded:
        _rec(conn, inst, evaluator="only-one", scores=BAD)
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
    _rec(conn, instance, evaluator="ext", scores=BAD, external_cause=True)
    _rec(conn, instance, evaluator="int", scores=GOOD)
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
