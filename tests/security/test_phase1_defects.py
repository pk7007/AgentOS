"""Reproductions for the suspected defects listed in the V4.0 recovery brief.

Each test asserts the *correct* behaviour. A failing test on the unfixed code confirms the defect;
a passing one means the suspicion did not hold. D01 (cooperative-only admission) and D02 (no runtime
cancellation) are architectural: nothing in the ledger can stop or kill a host's worker, so they are
covered by the runtime-adapter work, not by a test here.
"""

import json
import math
import sqlite3

import pytest

from agentos import admission, audit, db, governance, governor, lifecycle, performance, tasks
from agentos.admission import AdmitRequest
from agentos.errors import PolicyDenied, UsageError
from agentos.lifecycle import AgentState as S
from tests.conftest import make_repo

ALL_SCORES = {k: 80 for k in performance.WEIGHTS}


def _admit(conn, project_id, task_id, template="implementer", parent=None):
    return admission.admit(conn, AdmitRequest(project_id=project_id, task_id=task_id, template_id=template,
                                              parent_instance_id=parent, host="test"), actor="t")


def _task(conn, project, title="t", **kw):
    return tasks.add_task(conn, project.id, title, actor="t", **kw)


@pytest.fixture
def other(seeded, tmp_path):
    from agentos import projects

    return projects.activate(seeded, make_repo(tmp_path / "Other Repo"), actor="t")


def _evidence(conn, project_id):
    from agentos import evidence

    return evidence.run(conn, project_id, ["python", "-c", "print('ok')"], actor="t").id


def _evaluator(conn, project):
    d = _admit(conn, project.id, _task(conn, project, "review").id, "reviewer")
    assert d.allowed, d.reasons
    return d.instance_id


# D03 premature release of active-worker slots

def test_d03_cancel_keeps_slot_until_runtime_confirms_stop(seeded, project):
    governor.set_limit(seeded, "max_concurrent", 1, actor="t")
    a = _admit(seeded, project.id, _task(seeded, project).id).instance_id
    lifecycle.transition(seeded, a, S.RUNNING, "t")
    lifecycle.transition(seeded, a, S.CANCELLED, "t")
    d = _admit(seeded, project.id, _task(seeded, project).id)
    assert not d.allowed and "max_concurrent" in d.reasons
    lifecycle.transition(seeded, a, S.TERMINATED, "t", runtime_confirmed=True)
    assert _admit(seeded, project.id, _task(seeded, project).id).allowed


def test_d03_unconfirmed_termination_keeps_slot(seeded, project):
    governor.set_limit(seeded, "max_concurrent", 1, actor="t")
    a = _admit(seeded, project.id, _task(seeded, project).id).instance_id
    lifecycle.transition(seeded, a, S.CANCELLED, "t")
    lifecycle.transition(seeded, a, S.TERMINATED, "t", runtime_confirmed=False)
    assert "max_concurrent" in _admit(seeded, project.id, _task(seeded, project).id).reasons


# D04 lifecycle transitions bypassing admission

def test_d04_reassigning_a_failed_agent_rechecks_concurrency(seeded, project):
    governor.set_limit(seeded, "max_concurrent", 1, actor="t")
    a = _admit(seeded, project.id, _task(seeded, project).id).instance_id
    lifecycle.transition(seeded, a, S.RUNNING, "t")
    lifecycle.transition(seeded, a, S.FAILED, "t")
    assert _admit(seeded, project.id, _task(seeded, project).id).allowed
    with pytest.raises(PolicyDenied) as exc:
        lifecycle.transition(seeded, a, S.ASSIGNED, "t")
    assert "max_concurrent" in exc.value.reasons
    assert lifecycle.active_count(seeded) == 1


def test_d04_reassigning_under_emergency_stop_is_denied(seeded, project):
    a = _admit(seeded, project.id, _task(seeded, project).id).instance_id
    lifecycle.transition(seeded, a, S.RUNNING, "t")
    lifecycle.transition(seeded, a, S.FAILED, "t")
    governance.emergency_stop(seeded, actor="t", reason="x")
    with pytest.raises(PolicyDenied) as exc:
        lifecycle.transition(seeded, a, S.ASSIGNED, "t")
    assert "emergency_stop" in exc.value.reasons


# D05 unauthenticated evaluator identities

def test_d05_made_up_evaluator_is_rejected(seeded, project, task):
    a = _admit(seeded, project.id, task.id).instance_id
    with pytest.raises(PolicyDenied) as exc:
        performance.record_eval(seeded, a, "anyone-at-all", "coding", ALL_SCORES, [_evidence(seeded, project.id)])
    assert "unknown_evaluator" in exc.value.reasons


def test_d05_evaluator_from_another_project_is_rejected(seeded, project, task, other):
    a = _admit(seeded, project.id, task.id).instance_id
    foreign = _evaluator(seeded, other)
    with pytest.raises(PolicyDenied) as exc:
        performance.record_eval(seeded, a, foreign, "coding", ALL_SCORES, [_evidence(seeded, project.id)])
    assert "cross_project" in exc.value.reasons


# D06 fabricated or unverifiable evidence

def test_d06_free_text_evidence_alone_is_rejected(seeded, project, task):
    a = _admit(seeded, project.id, task.id).instance_id
    ev = _evaluator(seeded, project)
    with pytest.raises(PolicyDenied) as exc:
        performance.record_eval(seeded, a, ev, "coding", ALL_SCORES, ["pytest -q: 999 passed (trust me)"])
    assert "unverified_evidence" in exc.value.reasons


# D07 duplicate or selectively incomplete evaluations

def test_d07_second_evaluation_by_same_evaluator_is_rejected(seeded, project, task):
    a = _admit(seeded, project.id, task.id).instance_id
    ev, proof = _evaluator(seeded, project), _evidence(seeded, project.id)
    performance.record_eval(seeded, a, ev, "coding", ALL_SCORES, [proof])
    with pytest.raises(PolicyDenied) as exc:
        performance.record_eval(seeded, a, ev, "coding", ALL_SCORES, [proof])
    assert "duplicate_evaluation" in exc.value.reasons


def test_d07_cherry_picked_scores_are_rejected(seeded, project, task):
    a = _admit(seeded, project.id, task.id).instance_id
    ev = _evaluator(seeded, project)
    with pytest.raises(UsageError):
        performance.record_eval(seeded, a, ev, "coding", {"speed": 100}, [_evidence(seeded, project.id)])


# D08 cross-project parent delegation

def test_d08_parent_from_another_project_is_rejected(seeded, project, task, other):
    lead = _admit(seeded, other.id, _task(seeded, other).id, "lead").instance_id
    d = _admit(seeded, project.id, task.id, parent=lead)
    assert not d.allowed and "parent_cross_project" in d.reasons


# D09 missing dependency checks in admission

def test_d09_admission_waits_for_dependencies(seeded, project):
    first, second = _task(seeded, project, "first"), _task(seeded, project, "second")
    tasks.add_dependency(seeded, second.id, first.id, "t")
    d = _admit(seeded, project.id, second.id)
    assert not d.allowed and "dependencies_incomplete" in d.reasons


# D10 missing capability and risk validation in admission

def test_d10_template_without_required_capability_is_rejected(seeded, project):
    t = _task(seeded, project, capabilities=["python"])
    d = _admit(seeded, project.id, t.id, "researcher")
    assert not d.allowed and "capability_mismatch" in d.reasons
    assert _admit(seeded, project.id, t.id, "implementer").allowed


def test_d10_high_risk_task_needs_proven_template_or_owner_approval(seeded, project):
    t = _task(seeded, project, capabilities=["python"], risk="high")
    d = _admit(seeded, project.id, t.id, "implementer")
    assert not d.allowed and "high_risk_unproven" in d.reasons


# D11 race in task dependency creation

def test_d11_concurrent_reverse_dependencies_cannot_form_a_cycle(conn, project, home, monkeypatch):
    a, b = _task(conn, project, "a"), _task(conn, project, "b")
    rival = db.connect()
    rival.execute("PRAGMA busy_timeout=200")
    real = tasks._reaches
    raced = {}

    def racing_reaches(c, start, goal):
        found = real(c, start, goal)
        if not raced:
            raced["done"] = True
            try:
                tasks.add_dependency(rival, b.id, a.id, "rival")
            except sqlite3.OperationalError:
                raced["blocked"] = True
        return found

    monkeypatch.setattr(tasks, "_reaches", racing_reaches)
    try:
        try:
            tasks.add_dependency(conn, a.id, b.id, "t")
        except PolicyDenied:
            pass
    finally:
        rival.close()
    edges = {tuple(e) for e in conn.execute("SELECT task_id, depends_on FROM task_deps").fetchall()}
    assert not ((a.id, b.id) in edges and (b.id, a.id) in edges), "dependency cycle created"


# D12 insufficient reservation validation

@pytest.mark.parametrize("amount", [-5, 0, math.nan, math.inf])
def test_d12_reserve_rejects_non_positive_or_non_finite(conn, amount):
    with pytest.raises((PolicyDenied, UsageError)):
        governor.reserve(conn, [("global", "*")], "agent_runs", amount, holder="x")


def test_d12_negative_reservation_cannot_refund_a_budget(conn):
    governor.set_budget(conn, "global", "*", "agent_runs", 1, actor="t")
    governor.reserve(conn, [("global", "*")], "agent_runs", 1, holder="a")
    with pytest.raises((PolicyDenied, UsageError)):
        governor.reserve(conn, [("global", "*")], "agent_runs", -1, holder="b")
    with pytest.raises(PolicyDenied):
        governor.reserve(conn, [("global", "*")], "agent_runs", 1, holder="c")


def test_d12_unknown_kind_is_rejected(conn):
    with pytest.raises((PolicyDenied, UsageError)):
        governor.reserve(conn, [("global", "*")], "bananas", 1, holder="x")


# D13 budget enforcement gaps

def test_d13_token_usage_is_charged_and_enforced(seeded, project):
    governor.set_budget(seeded, "project", project.id, "tokens_est", 100, actor="t")
    a = _admit(seeded, project.id, _task(seeded, project).id).instance_id
    with pytest.raises(PolicyDenied):
        governor.record_usage(seeded, a, "tokens_est", 150, actor="t")
    governor.record_usage(seeded, a, "tokens_est", 100, actor="t")
    d = _admit(seeded, project.id, _task(seeded, project).id)
    assert not d.allowed and "budget_exhausted:project:tokens_est" in d.reasons


# D14 audit-chain truncation

def test_d14_deleting_the_newest_events_is_detected(conn):
    with db.write_tx(conn):
        for i in range(3):
            audit.append_event(conn, "test.event", "t", {"i": i})
    conn.execute("DELETE FROM events WHERE seq=(SELECT max(seq) FROM events)")
    assert not audit.verify_chain(conn).ok


# D15 weak owner identity

def test_d15_owner_pin_is_required_once_set(conn):
    owner = governance.confirm_owner("set owner pin", isatty=lambda: True,
                                     prompt=lambda m: "I APPROVE set owner pin")
    governance.set_owner_pin(conn, "4821-river", owner, actor="t")
    with pytest.raises(PolicyDenied) as exc:
        governance.confirm_owner("lift stop", isatty=lambda: True, prompt=lambda m: "I APPROVE lift stop",
                                 secret=lambda m: "0000", conn=conn)
    assert "owner_pin_mismatch" in exc.value.reasons
    ok = governance.confirm_owner("lift stop", isatty=lambda: True, prompt=lambda m: "I APPROVE lift stop",
                                  secret=lambda m: "4821-river", conn=conn)
    assert governance.is_owner(ok)


# D16 secret-redaction limits

# Fake credentials are assembled at runtime so no secret-shaped literal sits in the source
# (secret scanners on the hosting side would otherwise flag these test fixtures).
_FILL = "Q7xTfake" * 4
JWT = ".".join(["ey" + "J" + "hbGciOiJIUzI1NiJ9", "ey" + "J" + "zdWIiOiJ0ZXN0In0", _FILL])


@pytest.mark.parametrize("text,secret", [
    (f"token {JWT}", _FILL[-20:]),
    ("Authorization: Bearer " + _FILL, _FILL[:16]),
    ("key " + "AI" + "za" + _FILL, _FILL[:14]),
    ("stripe " + "sk" + "_live_" + _FILL, _FILL[:14]),
    ("restricted " + "rk" + "_live_" + _FILL, _FILL[:14]),
    ("clone https://deploy:" + "Sup3r" + "S3cret@git.example.com/repo.git", "Sup3rS3cret"),
    ('{"password": "hunter2-long"}', "hunter2-long"),
    ("client_secret=zz9plural-zalpha", "zz9plural-zalpha"),
    ("AWS_SECRET_" + "ACCESS_KEY=" + _FILL, _FILL[:14]),
])
def test_d16_more_secret_shapes_are_redacted(text, secret):
    from agentos.redact import redact

    out, n = redact(text)
    assert secret not in out and n >= 1, out


# D17 incomplete project isolation (instance- and task-level commands)

@pytest.fixture
def two_projects(cli, home, tmp_path, monkeypatch):
    a, b = make_repo(tmp_path / "Repo A"), make_repo(tmp_path / "Repo B")
    cli(["init"])
    cli(["template", "seed"])
    for r in (a, b):
        cli(["project", "activate", str(r)])
    task_b = json.loads(cli(["task", "add", "b work", "--project", str(b), "--json"])[1])["id"]
    inst_b = json.loads(cli(["agent", "admit", "--task", task_b, "--template", "implementer",
                             "--project", str(b), "--json"])[1])["instance_id"]
    monkeypatch.chdir(a)
    return task_b, inst_b


@pytest.mark.parametrize("argv", [
    ["agent", "transition", "{inst}", "RUNNING"],
    ["agent", "inspect", "{inst}"],
    ["task", "start", "{task}"],
    ["task", "inspect", "{task}"],
])
def test_d17_commands_cannot_reach_into_another_project(cli, two_projects, argv):
    task_b, inst_b = two_projects
    code, out, err = cli([x.format(inst=inst_b, task=task_b) for x in argv])
    assert code == 3, (code, out, err)
