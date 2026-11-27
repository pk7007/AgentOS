"""Heartbeats, stale-worker detection and recovery, and the automatic circuit breaker (agentos.health)."""

from datetime import UTC, datetime, timedelta

import pytest

from agentos import admission, audit, health, lifecycle, performance, tasks, templates
from agentos.errors import PolicyDenied
from tests.conftest import add_evidence, add_instance

ALL = list(performance.WEIGHTS)
LATER = datetime.now(UTC) + timedelta(hours=1)


def _admit(conn, project, task):
    d = admission.admit(conn, admission.AdmitRequest(project_id=project.id, task_id=task.id,
                                                      template_id="implementer", host="t"), "t")
    assert d.allowed, d.reasons
    lifecycle.transition(conn, d.instance_id, "RUNNING", "t")
    return d.instance_id


def test_a_heartbeat_keeps_a_worker_fresh_and_is_refused_once_it_stopped(seeded, project, task):
    iid = _admit(seeded, project, task)
    assert health.stale(seeded, project.id, 30, now=LATER)[0]["instance_id"] == iid
    seeded.execute("UPDATE agent_instances SET last_heartbeat=? WHERE id=?", (LATER.isoformat(), iid))
    assert health.stale(seeded, project.id, 30, now=LATER) == []
    lifecycle.transition(seeded, iid, "COMPLETED", "t")
    with pytest.raises(PolicyDenied) as exc:
        health.heartbeat(seeded, iid)
    assert exc.value.reasons == ["not_active"]
    with pytest.raises(PolicyDenied):
        health.stale(seeded, project.id, 0)


def test_heartbeat_records_the_time(seeded, project, task):
    iid = _admit(seeded, project, task)
    hb = health.heartbeat(seeded, iid)
    assert lifecycle.get_instance(seeded, iid) and hb["last_heartbeat"]
    assert health.stale(seeded, project.id, 5) == []


def test_reap_fails_a_silent_worker_frees_its_slot_and_retries_its_task(seeded, project, task):
    tasks.set_state(seeded, task.id, "running", "t")
    iid = _admit(seeded, project, task)
    held = lifecycle.slot_count(seeded)
    r = health.reap(seeded, project.id, "t", 30, now=LATER)
    step = r["reaped"][0]
    assert step["instance_id"] == iid and step["to"] == "FAILED"
    assert step["task_action"]["action"] == "retry" and "implementer" in step["task_action"]["avoid_templates"]
    assert lifecycle.slot_count(seeded) == held - 1
    assert tasks.get_task(seeded, task.id).state.value == "pending"
    assert seeded.execute("SELECT count(*) FROM events WHERE kind='health.reaped'").fetchone()[0] == 1
    assert audit.verify_chain(seeded).ok


def test_reap_escalates_when_the_retry_limit_is_reached(seeded, project, task):
    seeded.execute("UPDATE tasks SET max_retries=0 WHERE id=?", (task.id,))
    tasks.set_state(seeded, task.id, "running", "t")
    _admit(seeded, project, task)
    step = health.reap(seeded, project.id, "t", 30, now=LATER)["reaped"][0]
    assert step["task_action"]["action"] == "escalate_owner"


def test_reap_leaves_live_workers_alone(seeded, project, task):
    _admit(seeded, project, task)
    assert health.reap(seeded, project.id, "t", 30)["reaped"] == []


def _grade(conn, project, task, value, flags=None, external=False):
    worker = add_instance(conn, project, task, "implementer")
    judge = add_instance(conn, project, task, "reviewer")
    return performance.record_eval(conn, worker, judge, "coding", {k: value for k in ALL},
                                   [add_evidence(conn, project.id)], flags=flags, external_cause=external,
                                   actor="t")


def test_the_breaker_suspends_a_template_after_repeated_failures(seeded, project, task):
    _grade(seeded, project, task, 20)
    _grade(seeded, project, task, 25)
    assert templates.get_template(seeded, "implementer").status.value == "active"
    _grade(seeded, project, task, 10)
    assert templates.get_template(seeded, "implementer").status.value == "suspended"
    kinds = [r[0] for r in seeded.execute("SELECT kind FROM events WHERE kind='health.breaker_tripped'")]
    assert kinds == ["health.breaker_tripped"]
    t2 = tasks.add_task(seeded, project.id, "more", actor="t")
    d = admission.admit(seeded, admission.AdmitRequest(project_id=project.id, task_id=t2.id,
                                                       template_id="implementer", host="t"), "t")
    assert not d.allowed


def test_one_pass_or_an_outside_cause_does_not_trip_the_breaker(seeded, project, task):
    _grade(seeded, project, task, 20)
    _grade(seeded, project, task, 80)
    _grade(seeded, project, task, 20)
    _grade(seeded, project, task, 10, external=True)
    _grade(seeded, project, task, 30)  # failing, but not below the breaker's floor
    assert templates.get_template(seeded, "implementer").status.value == "active"


def test_the_breaker_window_is_a_setting(seeded, project, task):
    from agentos.db import put_setting

    put_setting(seeded, "breaker.window", 0)
    for _ in range(4):
        _grade(seeded, project, task, 10)
    assert templates.get_template(seeded, "implementer").status.value == "active"


def test_a_retry_limit_escalation_reaches_the_owner(seeded, project, task):
    from agentos import comms, observe

    seeded.execute("UPDATE tasks SET max_retries=0 WHERE id=?", (task.id,))
    tasks.set_state(seeded, task.id, "running", "t")
    _admit(seeded, project, task)
    action = health.reap(seeded, project.id, "t", 30, now=LATER)["reaped"][0]["task_action"]
    esc = comms.open_escalations(seeded, project.id)
    assert [e["id"] for e in esc] == [action["message_id"]] and esc[0]["task_id"] == task.id
    assert observe.dashboard(seeded, project.id)["open_escalations"] == 1
    assert any(i["kind"] == "comms.escalated" and i["severity"] == "high"
               for i in observe.incidents(seeded, project.id)["incidents"])
    assert audit.verify_chain(seeded).ok


def test_a_heartbeat_for_another_projects_worker_is_refused(seeded, project, task, tmp_path):
    from agentos import projects
    from tests.conftest import make_repo

    iid = _admit(seeded, project, task)
    other = projects.activate(seeded, make_repo(tmp_path / "other"), "t")
    with pytest.raises(PolicyDenied) as exc:
        health.heartbeat(seeded, iid, other.id)
    assert exc.value.reasons == ["cross_project"]
    assert seeded.execute("SELECT last_heartbeat FROM agent_instances WHERE id=?", (iid,)).fetchone()[0] is None
    assert health.heartbeat(seeded, iid, project.id)["instance_id"] == iid


def test_asking_again_at_the_retry_limit_does_not_pile_up_escalations(seeded, project, task):
    from agentos import boss, comms

    seeded.execute("UPDATE tasks SET max_retries=0 WHERE id=?", (task.id,))
    tasks.set_state(seeded, task.id, "running", "t")
    tasks.set_state(seeded, task.id, "failed", "t")
    first = boss.recover(seeded, task.id, "t")["message_id"]
    assert boss.recover(seeded, task.id, "t")["message_id"] == first
    assert len(comms.open_escalations(seeded, project.id)) == 1
    comms.inbox(seeded, project.id, comms.OWNER, mark_read=True, actor="owner")
    assert boss.recover(seeded, task.id, "t")["message_id"] != first  # read, then failed again: a new one


def test_the_breaker_settings_are_protected_from_the_generic_setter(seeded, owner):
    from agentos import governance

    with pytest.raises(PolicyDenied) as exc:
        governance.set_setting(seeded, "breaker.floor", 0, "t")
    assert exc.value.reasons == ["owner_required"]
    governance.set_setting(seeded, "breaker.floor", 20, "t", owner=owner)
    assert health.breaker_settings(seeded)["floor"] == 20
