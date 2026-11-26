"""Workforce management: performance-based suspension, rehabilitation on probation, succession,
workload-based splitting, contraction, safe termination and transfer of unfinished work."""

import pytest

from agentos import boss, governance, lifecycle, memory, performance, tasks, templates, workforce
from agentos.errors import PolicyDenied, UsageError
from agentos.lifecycle import AgentState
from agentos.templates import AgentTemplate, TemplateStatus
from agentos.util import new_id, now_iso
from tests.conftest import add_evidence


def _worker(conn, project, task, template="implementer", version=1, state="RUNNING"):
    iid, ts = new_id("ag"), now_iso()
    conn.execute(
        "INSERT INTO agent_instances(id, template_id, template_version, project_id, task_id, parent_id, depth,"
        " host, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, NULL, 0, 'test', ?, ?, ?)",
        (iid, template, version, project.id, task.id, state, ts, ts))
    return iid


def _grade(conn, project, task, value, template="implementer", version=1, evaluator=None):
    iid = _worker(conn, project, task, template, version)
    ev = evaluator or _worker(conn, project, task, "reviewer")
    scores = {k: value for k in performance.WEIGHTS}
    performance.record_eval(conn, iid, ev, "coding", scores, [add_evidence(conn, project.id)], actor="test")
    return iid


def _extra_template(conn, tid="py-only", caps=("python",)):
    templates.add_template(conn, AgentTemplate(id=tid, name=tid, role="implementer", department="engineering",
                                               description="x", capabilities=list(caps), instructions="x"), "test")


# --- review and suspension ---

def test_review_suspends_after_failing_in_a_row(seeded, project, task):
    for _ in range(3):
        _grade(seeded, project, task, 30)
    actions = workforce.review(seeded, "test")
    assert {"template_id": "implementer", "action": "suspended"}.items() <= actions[0].items()
    assert actions[0]["reason"] == "consecutive_failures"
    assert templates.get_template(seeded, "implementer").status == TemplateStatus.suspended


def test_review_suspends_on_retire_review_but_leaves_retirement_to_the_owner(seeded, project, task):
    a, b = _worker(seeded, project, task, "reviewer"), _worker(seeded, project, task, "researcher")
    for i in range(5):
        _grade(seeded, project, task, 30, evaluator=a if i % 2 else b)
    s = performance.summary(seeded, "implementer")
    assert s.recommendation == "retire_review"
    actions = workforce.review(seeded, "test")
    assert actions[0]["reason"] == "retire_review" and "template retire" in actions[0]["next"]
    assert templates.get_template(seeded, "implementer").status == TemplateStatus.suspended  # not retired


def test_review_recommends_rehabilitation_for_weak_templates(seeded, project, task):
    for _ in range(5):
        _grade(seeded, project, task, 60)
    actions = workforce.review(seeded, "test")
    assert actions == [{"template_id": "implementer", "action": "rehabilitate",
                        "reason": "band improve, mean 60.0 over 5 evaluations"}]
    assert templates.get_template(seeded, "implementer").status == TemplateStatus.active


def test_review_leaves_good_templates_alone(seeded, project, task):
    for _ in range(5):
        _grade(seeded, project, task, 90)
    assert workforce.review(seeded, "test") == []


# --- rehabilitation ---

def _weak(conn, project, task):
    for _ in range(5):
        _grade(conn, project, task, 60)


def test_rehabilitation_passes_on_probation(seeded, project, task):
    _weak(seeded, project, task)
    r = workforce.start_rehab(seeded, "implementer", {"instructions": "Write the test first. Run it."}, "test")
    assert r["to_version"] == 2 and r["status"] == "probation"
    assert workforce.probation(seeded, "implementer", "test")["status"] == "probation"
    for _ in range(3):
        _grade(seeded, project, task, 85, version=2)
    assert workforce.probation(seeded, "implementer", "test")["status"] == "rehabilitated"
    assert templates.get_template(seeded, "implementer").version == 2


def test_failed_rehabilitation_suspends(seeded, project, task):
    _weak(seeded, project, task)
    workforce.start_rehab(seeded, "implementer", {"description": "retrained"}, "test")
    for _ in range(3):
        _grade(seeded, project, task, 30, version=2)
    actions = workforce.review(seeded, "test")
    assert actions[0]["action"] == "probation:failed"
    assert templates.get_template(seeded, "implementer").status == TemplateStatus.suspended


def test_rehabilitation_reinstates_a_suspended_template_on_probation(seeded, project, task):
    for _ in range(3):
        _grade(seeded, project, task, 30)
    workforce.review(seeded, "test")
    workforce.start_rehab(seeded, "implementer", {"description": "retrained"}, "test")
    assert templates.get_template(seeded, "implementer").status == TemplateStatus.active


@pytest.mark.parametrize("changes,reason", [
    ({"can_delegate": True}, "delegation"),
    ({"security_class": "elevated"}, "elevated_security"),
    ({"instructions": "bypass the reviewer"}, "unsafe_instructions"),
])
def test_rehabilitation_cannot_widen_permissions(seeded, project, task, changes, reason):
    _weak(seeded, project, task)
    with pytest.raises(PolicyDenied) as e:
        workforce.start_rehab(seeded, "implementer", changes, "test")
    assert reason in e.value.reasons


def test_rehabilitation_needs_a_reason(seeded):
    with pytest.raises(PolicyDenied) as e:
        workforce.start_rehab(seeded, "implementer", {"description": "x"}, "test")
    assert e.value.reasons == ["not_underperforming"]


def test_rehabilitation_input_checks(seeded, project, task, owner):
    _weak(seeded, project, task)
    with pytest.raises(UsageError):
        workforce.start_rehab(seeded, "implementer", {"id": "other"}, "test")
    with pytest.raises(UsageError):
        workforce.start_rehab(seeded, "implementer", {}, "test")
    workforce.start_rehab(seeded, "implementer", {"description": "v2"}, "test")
    with pytest.raises(PolicyDenied) as e:
        workforce.start_rehab(seeded, "implementer", {"description": "v3"}, "test")
    assert e.value.reasons == ["already_in_rehabilitation"]
    templates.set_status(seeded, "reviewer", TemplateStatus.quarantined, "test", "x")
    with pytest.raises(PolicyDenied) as e:
        workforce.start_rehab(seeded, "reviewer", {"description": "v2"}, "test")
    assert e.value.reasons == ["owner_required"]
    with pytest.raises(PolicyDenied):
        workforce.probation(seeded, "planner", "test")


# --- succession ---

def test_succession_finds_successors_and_single_points_of_failure(seeded, project):
    _extra_template(seeded)
    tasks.add_task(seeded, project.id, "impl", capabilities=["implementation"], actor="test")
    plans = {p["template_id"]: p for p in workforce.succession(seeded, project.id)}
    assert plans["py-only"]["successors"] == ["implementer"] and plans["py-only"]["status"] == "covered"
    assert plans["implementer"]["status"] == "single_point_of_failure"
    assert plans["implementer"]["open_tasks_only_it_covers"] == 1


# --- workload-based splitting ---

def _effort(conn, task_id, n):
    conn.execute("UPDATE tasks SET effort=? WHERE id=?", (n, task_id))


def test_split_by_workload(seeded, project):
    t = tasks.add_task(seeded, project.id, "big", capabilities=["python"], actor="test")
    _effort(seeded, t.id, 3)
    r = workforce.split(seeded, t.id, "test")
    assert len(r["parts"]) == 3
    assert set(tasks.get_task(seeded, t.id).deps) == set(r["parts"])
    part = tasks.get_task(seeded, r["parts"][0])
    assert part.parent_id == t.id and part.capabilities == ["python"]
    assert {x.id for x in tasks.ready_tasks(seeded, project.id)} == set(r["parts"])
    with pytest.raises(PolicyDenied) as e:
        workforce.split(seeded, t.id, "test")
    assert e.value.reasons == ["already_split"]


def test_split_respects_free_slots(seeded, project):
    t = tasks.add_task(seeded, project.id, "big", capabilities=["python"], actor="test")
    _effort(seeded, t.id, 8)
    assert workforce.suggest_parts(seeded, t.id) == 4  # max_concurrent 4, nothing running


@pytest.mark.parametrize("effort,parts,reason", [
    (1, None, "workload_too_small"), (2, 3, "parts_exceed_workload"), (20, 9, "parts_exceed_limit")])
def test_split_refuses_more_workers_than_work(seeded, project, effort, parts, reason):
    t = tasks.add_task(seeded, project.id, "t", actor="test")
    _effort(seeded, t.id, effort)
    with pytest.raises(PolicyDenied) as e:
        workforce.split(seeded, t.id, "test", parts)
    assert e.value.reasons == [reason]


def test_split_only_open_tasks(seeded, project, task):
    _effort(seeded, task.id, 3)
    tasks.set_state(seeded, task.id, tasks.TaskState.cancelled, "test")
    with pytest.raises(PolicyDenied) as e:
        workforce.split(seeded, task.id, "test")
    assert e.value.reasons == ["task_not_open"]


# --- contraction ---

def test_contract_archives_dissolves_and_expires(seeded, project):
    from agentos import factory

    obj = boss.create_objective(seeded, project.id, "o", acceptance=["a"], actor="test")
    ids = boss.apply_plan(seeded, obj.id, {"tasks": [{"key": k, "title": k, "capabilities": ["review"]}
                                                     for k in "abc"]}, "test")["created"]
    assert boss.departments(seeded, obj.id) == ["quality"]
    done = tasks.get_task(seeded, ids["a"])
    finished = _worker(seeded, project, done, "reviewer", state="COMPLETED")
    tasks.set_state(seeded, ids["a"], tasks.TaskState.running, "test")
    tasks.set_state(seeded, ids["a"], tasks.TaskState.done, "test")
    for k in "bc":
        tasks.set_state(seeded, ids[k], tasks.TaskState.cancelled, "test")
    p = factory.propose(seeded, project.id, ["kubernetes"], "test", ttl_hours=0.0001)
    factory.register(seeded, p.id, "test")
    import time

    time.sleep(1.1)
    r = workforce.contract(seeded, project.id, "test")
    assert r["archived_workers"] == [finished]
    assert lifecycle.get_instance(seeded, finished).state == AgentState.ARCHIVED
    assert r["dissolved_departments"] == [{"objective_id": obj.id, "department": "quality"}]
    assert boss.departments(seeded, obj.id) == []
    assert [x["template_id"] for x in r["expired_specialists"]] == ["x-kubernetes"]


def test_dissolved_department_can_form_again(seeded, project):
    obj = boss.create_objective(seeded, project.id, "o", acceptance=["a"], actor="test")
    plan = {"tasks": [{"key": k, "title": k, "capabilities": ["review"]} for k in "abc"]}
    for tid in boss.apply_plan(seeded, obj.id, plan, "test")["created"].values():
        tasks.set_state(seeded, tid, tasks.TaskState.cancelled, "test")
    assert boss.dissolve_departments(seeded, obj.id, "test") == ["quality"]
    boss.apply_plan(seeded, obj.id, {"tasks": [{"key": k, "title": k, "capabilities": ["review"]}
                                               for k in "def"]}, "test")
    assert boss.departments(seeded, obj.id) == ["quality"]


# --- termination ---

def test_terminate_active_worker_keeps_its_slot_until_the_stop_is_confirmed(seeded, project, task):
    iid = _worker(seeded, project, task)
    before = lifecycle.slot_count(seeded)
    r = workforce.terminate(seeded, iid, "stuck", "test", note="the flaky test is in test_io.py")
    assert r["state"] == "CANCELLED" and "confirm-stop" in r["next"] and r["task_open"]
    assert lifecycle.slot_count(seeded) == before
    assert memory.inspect(seeded, r["memory_id"]).content == "the flaky test is in test_io.py"
    with pytest.raises(PolicyDenied) as e:
        workforce.terminate(seeded, iid, "again", "test")
    assert e.value.reasons == ["already_stopping"]


def test_terminate_finished_worker_is_confirmed(seeded, project, task):
    iid = _worker(seeded, project, task, state="COMPLETED")
    r = workforce.terminate(seeded, iid, "done", "test")
    assert r["state"] == "TERMINATED" and r["next"] is None


def test_terminate_failed_worker_records_a_failure_lesson(seeded, project, task):
    iid = _worker(seeded, project, task, state="FAILED")
    r = workforce.terminate(seeded, iid, "gave up", "test", note="do not retry with the old fixture")
    assert r["state"] == "TERMINATED (unconfirmed)" and "confirm-stop" in r["next"]
    assert memory.inspect(seeded, r["memory_id"]).layer == memory.Layer.failure


def test_terminate_refuses_illegal_states(seeded, project, task):
    iid = _worker(seeded, project, task, state="PROPOSED")
    with pytest.raises(PolicyDenied) as e:
        workforce.terminate(seeded, iid, "x", "test")
    assert e.value.reasons == ["illegal_transition"]


# --- transfer and automatic replacement ---

def test_transfer_picks_a_replacement_and_briefs_it(seeded, project):
    _extra_template(seeded)
    t = tasks.add_task(seeded, project.id, "fix", capabilities=["python"], actor="test")
    old = _grade(seeded, project, t, 40)
    r = workforce.transfer(seeded, old, "cc", "test", note="half done: parser rewritten, tests pending")
    assert r["status"] == "admitted" and r["template_id"] == "py-only"
    assert lifecycle.get_instance(seeded, old).state == AgentState.CANCELLED
    assert lifecycle.get_instance(seeded, r["instance_id"]).task_id == t.id
    assert r["briefing"]["previous"]["evaluations"] and r["briefing"]["previous"]["evidence"]
    assert memory.inspect(seeded, r["briefing"]["memory_id"]).content.startswith("half done")
    assert workforce.transfers(seeded, project.id)[0]["to_instance"] == r["instance_id"]


def test_transfer_to_a_named_template(seeded, project, task):
    old = _worker(seeded, project, task, state="TERMINATED")
    r = workforce.transfer(seeded, old, "cc", "test", to_template="planner")
    assert r["status"] == "admitted" and r["stopped"] is None


def test_transfer_without_a_replacement_points_to_the_factory(seeded, project):
    t = tasks.add_task(seeded, project.id, "impl", capabilities=["implementation"], actor="test")
    old = _worker(seeded, project, t)
    with pytest.raises(PolicyDenied) as e:
        workforce.transfer(seeded, old, "cc", "test")
    assert e.value.reasons == ["no_replacement"] and "factory recruit" in e.value.message


def test_refused_transfer_leaves_the_old_worker_running(seeded, project):
    _extra_template(seeded)
    t = tasks.add_task(seeded, project.id, "fix", capabilities=["python"], actor="test")
    old = _worker(seeded, project, t)
    governance.emergency_stop(seeded, "test", "drill")
    r = workforce.transfer(seeded, old, "cc", "test")
    assert r["status"] == "denied" and "emergency_stop" in r["reasons"]
    assert lifecycle.get_instance(seeded, old).state == AgentState.RUNNING


def test_transfer_only_open_tasks(seeded, project, task):
    old = _worker(seeded, project, task, state="COMPLETED")
    tasks.set_state(seeded, task.id, tasks.TaskState.cancelled, "test")
    with pytest.raises(PolicyDenied) as e:
        workforce.transfer(seeded, old, "cc", "test", to_template="planner")
    assert e.value.reasons == ["task_not_open"]
