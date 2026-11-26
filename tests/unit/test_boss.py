"""Boss Agent: the executive ledger behind one objective. The host's model does the thinking;
AgentOS checks the plan, schedules it, finds bottlenecks, enforces quality and gates delivery."""

import pytest

from agentos import boss, governor, lifecycle, performance, tasks
from agentos.errors import PolicyDenied, UsageError
from tests.conftest import add_evidence, add_instance

SCORES = {k: 90 for k in performance.WEIGHTS}


@pytest.fixture
def obj(seeded, project):
    return boss.create_objective(seeded, project.id, "Ship the export feature",
                                 statement="Users can export reports as CSV",
                                 acceptance=["CSV export works", "tests pass"], actor="test")


def _plan(*items):
    return {"tasks": list(items)}


def _t(key, caps=("implementation",), deps=(), **kw):
    return {"key": key, "title": f"task {key}", "capabilities": list(caps), "depends_on": list(deps), **kw}


def test_objective_needs_acceptance_criteria(seeded, project):
    with pytest.raises(PolicyDenied) as e:
        boss.create_objective(seeded, project.id, "vague", acceptance=[], actor="test")
    assert e.value.reasons == ["no_acceptance_criteria"]


def test_objective_records_complexity(seeded, project):
    o = boss.create_objective(seeded, project.id, "big", acceptance=["done"], actor="test",
                              complexity={"task_count": 20, "dependency_depth": 6, "workstreams": 6,
                                          "files_touched": 50, "domain_difficulty": 5, "uncertainty": 5,
                                          "risk": 5, "verification_effort": 5})
    assert o.complexity_band == "hierarchical" and o.complexity_score == 100


def test_plan_creates_linked_tasks_and_dependencies(seeded, obj):
    r = boss.apply_plan(seeded, obj.id, _plan(_t("a"), _t("b", deps=["a"]), _t("c", deps=["a", "b"])), "test")
    ids = r["created"]
    assert set(ids) == {"a", "b", "c"}
    c = tasks.get_task(seeded, ids["c"])
    assert set(c.deps) == {ids["a"], ids["b"]}
    assert boss.objective_tasks(seeded, obj.id) == [ids["a"], ids["b"], ids["c"]]


def test_plan_is_all_or_nothing(seeded, obj):
    with pytest.raises(PolicyDenied) as e:
        boss.apply_plan(seeded, obj.id, _plan(_t("a", deps=["b"]), _t("b", deps=["a"])), "test")
    assert e.value.reasons == ["cycle"]
    assert boss.objective_tasks(seeded, obj.id) == []


@pytest.mark.parametrize("plan,msg", [
    (_plan(_t("a"), _t("a")), "duplicate"),
    (_plan(_t("a", deps=["nope"])), "unknown"),
    ({"tasks": []}, "no tasks"),
    (_plan({"key": "a"}), "title"),
    (_plan(_t("a", department="marketing")), "department"),
    (_plan(_t("a", risk="extreme")), "risk"),
])
def test_plan_validation(seeded, obj, plan, msg):
    with pytest.raises(UsageError) as e:
        boss.apply_plan(seeded, obj.id, plan, "test")
    assert msg in str(e.value)


def test_departments_only_when_the_work_justifies_one(seeded, obj):
    r = boss.apply_plan(seeded, obj.id, _plan(
        _t("t1", caps=["testing"]), _t("t2", caps=["review"]), _t("t3", caps=["testing"]),
        _t("s1", caps=["security"])), "test")
    assert r["departments"] == ["quality"]
    assert boss.departments(seeded, obj.id) == ["quality"]


def test_plan_reports_capability_gaps(seeded, obj):
    r = boss.apply_plan(seeded, obj.id, _plan(_t("x", caps=["kubernetes"])), "test")
    assert r["capability_gaps"] == {"x": ["kubernetes"]}


def test_replan_can_build_on_existing_tasks_of_the_objective(seeded, obj, project):
    first = boss.apply_plan(seeded, obj.id, _plan(_t("a")), "test")["created"]["a"]
    more = boss.apply_plan(seeded, obj.id, _plan(_t("b", deps=[first]), _t("sub", parent=first)), "test")
    b = tasks.get_task(seeded, more["created"]["b"])
    assert b.deps == [first]
    assert tasks.get_task(seeded, more["created"]["sub"]).parent_id == first
    loose = tasks.add_task(seeded, project.id, "not in the objective", actor="test")
    with pytest.raises(PolicyDenied) as e:
        boss.apply_plan(seeded, obj.id, _plan(_t("c", deps=[loose.id])), "test")
    assert e.value.reasons == ["cross_objective"]


def test_schedule_puts_the_critical_path_first(seeded, obj):
    ids = boss.apply_plan(seeded, obj.id, _plan(
        _t("a"), _t("b", deps=["a"]), _t("c", deps=["b"]), _t("solo", priority=90)), "test")["created"]
    plan = boss.schedule(seeded, obj.id)
    order = [d["task_id"] for d in plan["dispatch"]]
    assert order == [ids["a"], ids["solo"]]
    first = plan["dispatch"][0]
    assert first["critical_path"] == 3 and first["template_id"] == "implementer"
    assert first["would_admit"] is True and first["reasons"] == []


def test_schedule_respects_capacity(seeded, obj, project):
    ids = boss.apply_plan(seeded, obj.id, _plan(_t("a"), _t("b")), "test")["created"]
    filler = tasks.add_task(seeded, project.id, "other work", actor="test")
    limit = governor.get_limits(seeded).max_concurrent
    for _ in range(limit - 1):
        add_instance(seeded, project, filler)
    plan = boss.schedule(seeded, obj.id)
    assert plan["free_slots"] == 1
    assert [d["status"] for d in plan["dispatch"]] == ["dispatch", "queued_capacity"]
    assert {d["task_id"] for d in plan["dispatch"]} == set(ids.values())


def test_schedule_flags_tasks_no_template_can_do(seeded, obj):
    boss.apply_plan(seeded, obj.id, _plan(_t("x", caps=["kubernetes"])), "test")
    d = boss.schedule(seeded, obj.id)["dispatch"][0]
    assert d["status"] == "capability_gap" and d["template_id"] is None


def test_no_executive_worker_for_routine_work(seeded, obj):
    boss.apply_plan(seeded, obj.id, _plan(_t("t1", caps=["testing"]), _t("t2", caps=["testing"]),
                                          _t("t3", caps=["testing"])), "test")
    assert boss.schedule(seeded, obj.id)["executive_workers"] == []


def test_large_objectives_may_get_a_department_lead(seeded, project):
    big = boss.create_objective(seeded, project.id, "big", acceptance=["done"], actor="test",
                                complexity={"task_count": 20, "dependency_depth": 6, "workstreams": 6,
                                            "files_touched": 50, "domain_difficulty": 5, "uncertainty": 5,
                                            "risk": 5, "verification_effort": 5})
    boss.apply_plan(seeded, big.id, _plan(_t("t1", caps=["testing"]), _t("t2", caps=["testing"]),
                                          _t("t3", caps=["testing"])), "test")
    leads = boss.schedule(seeded, big.id)["executive_workers"]
    assert leads == [{"department": "quality", "template_id": "lead", "ready_tasks": 3}]


def _run(conn, task_id, project, template="implementer"):
    tasks.set_state(conn, task_id, tasks.TaskState.running, "test")
    return add_instance(conn, project, tasks.get_task(conn, task_id), template=template)


def test_bottlenecks(seeded, obj, project):
    ids = boss.apply_plan(seeded, obj.id, _plan(
        _t("root"), _t("x", deps=["root"]), _t("y", deps=["root"]), _t("blk"), _t("bad"),
        _t("gap", caps=["kubernetes"])), "test")["created"]
    tasks.set_state(seeded, ids["blk"], tasks.TaskState.blocked, "test")
    _run(seeded, ids["bad"], project)
    tasks.set_state(seeded, ids["bad"], tasks.TaskState.failed, "test")
    kinds = {(f["kind"], f.get("task_id")) for f in boss.bottlenecks(seeded, obj.id)}
    assert ("critical_blocker", ids["root"]) in kinds
    assert ("blocked_task", ids["blk"]) in kinds
    assert ("failed_task", ids["bad"]) in kinds
    assert ("capability_gap", ids["gap"]) in kinds


def test_orphan_worker_is_a_bottleneck(seeded, obj, project):
    tid = boss.apply_plan(seeded, obj.id, _plan(_t("a")), "test")["created"]["a"]
    iid = _run(seeded, tid, project)
    seeded.execute("INSERT INTO runtime_bindings(instance_id, host, native_agent_id, claimed_at, stopped_at)"
                   " VALUES (?, 'codex', 'n1', '2026-01-01T00:00:00Z', '2026-01-01T00:01:00Z')", (iid,))
    found = [f for f in boss.bottlenecks(seeded, obj.id) if f["kind"] == "orphan_worker"]
    assert found and found[0]["instance_id"] == iid


def _done_with_eval(conn, task_id, project, exit_code=0, scores=SCORES):
    iid = _run(conn, task_id, project)
    task = tasks.get_task(conn, task_id)
    reviewer = add_instance(conn, project, task, template="reviewer")
    evd = add_evidence(conn, project.id, exit_code=exit_code)
    ev = performance.record_eval(conn, iid, reviewer, "coding", scores, [evd], actor="test")
    tasks.set_state(conn, task_id, tasks.TaskState.done, "test")
    return ev, evd


def test_accept_needs_independent_passing_evidence(seeded, obj, project):
    ids = boss.apply_plan(seeded, obj.id, _plan(_t("a"), _t("b"), _t("c")), "test")["created"]
    ev, _ = _done_with_eval(seeded, ids["a"], project)
    assert boss.accept_task(seeded, ids["a"], ev.id, "test")["accepted"] is True
    with pytest.raises(PolicyDenied) as e:
        boss.accept_task(seeded, ids["a"], ev.id, "test")
    assert e.value.reasons == ["already_accepted"]
    with pytest.raises(PolicyDenied) as e:
        boss.accept_task(seeded, ids["b"], ev.id, "test")
    assert "task_not_done" in e.value.reasons and "evaluation_not_for_task" in e.value.reasons
    failing, _ = _done_with_eval(seeded, ids["c"], project, exit_code=1, scores={k: 40 for k in SCORES})
    with pytest.raises(PolicyDenied) as e:
        boss.accept_task(seeded, ids["c"], failing.id, "test")
    assert set(e.value.reasons) == {"score_below_threshold", "no_passing_evidence"}


def test_recover_retries_with_another_template(seeded, obj, project):
    tid = boss.apply_plan(seeded, obj.id, _plan(_t("a", caps=["testing"])), "test")["created"]["a"]
    iid = _run(seeded, tid, project, template="implementer")
    lifecycle.transition(seeded, iid, lifecycle.AgentState.FAILED, "test")
    tasks.set_state(seeded, tid, tasks.TaskState.failed, "test")
    r = boss.recover(seeded, tid, "test")
    assert r["action"] == "retry" and r["avoid_templates"] == ["implementer"]
    assert r["suggested_template"] == "reviewer"
    assert tasks.get_task(seeded, tid).state == tasks.TaskState.pending


def test_recover_escalates_when_retries_run_out(seeded, obj, project):
    tid = boss.apply_plan(seeded, obj.id, _plan(_t("a")), "test")["created"]["a"]
    seeded.execute("UPDATE tasks SET state='failed', retries=max_retries WHERE id=?", (tid,))
    r = boss.recover(seeded, tid, "test")
    assert r["action"] == "escalate_owner"
    assert tasks.get_task(seeded, tid).state == tasks.TaskState.failed


def test_recover_only_failed_tasks(seeded, obj):
    tid = boss.apply_plan(seeded, obj.id, _plan(_t("a")), "test")["created"]["a"]
    with pytest.raises(PolicyDenied) as e:
        boss.recover(seeded, tid, "test")
    assert e.value.reasons == ["task_not_failed"]


def test_review_covers_every_executive_function(seeded, obj):
    boss.apply_plan(seeded, obj.id, _plan(_t("a"), _t("s", caps=["security"], risk="high")), "test")
    rev = boss.review(seeded, obj.id)
    assert set(rev["functions"]) == set(boss.FUNCTIONS)
    assert all(f["status"] in ("ok", "attention") for f in rev["functions"].values())
    assert rev["functions"]["risk"]["status"] == "attention"


def test_delivery_is_gated(seeded, obj, project):
    tid = boss.apply_plan(seeded, obj.id, _plan(_t("a")), "test")["created"]["a"]
    with pytest.raises(PolicyDenied) as e:
        boss.deliver(seeded, obj.id, {}, "test")
    assert {"tasks_open", "criteria_without_evidence"} <= set(e.value.reasons)
    ev, evd = _done_with_eval(seeded, tid, project)
    with pytest.raises(PolicyDenied) as e:
        boss.deliver(seeded, obj.id, {0: evd, 1: evd}, "test")
    assert e.value.reasons == ["tasks_unaccepted"]
    boss.accept_task(seeded, tid, ev.id, "test")
    bad = add_evidence(seeded, project.id, exit_code=2)
    with pytest.raises(PolicyDenied) as e:
        boss.deliver(seeded, obj.id, {0: evd, 1: bad}, "test")
    assert e.value.reasons == ["criterion_evidence_failed"]
    report = boss.deliver(seeded, obj.id, {0: evd, 1: evd}, "test")
    assert report["objective"]["state"] == "delivered"
    assert report["tasks"][0]["evaluation_id"] == ev.id
    assert [c["evidence_id"] for c in report["criteria"]] == [evd, evd]
    with pytest.raises(PolicyDenied) as e:
        boss.deliver(seeded, obj.id, {0: evd, 1: evd}, "test")
    assert e.value.reasons == ["objective_not_open"]


def test_cancelled_tasks_do_not_block_delivery(seeded, obj, project):
    ids = boss.apply_plan(seeded, obj.id, _plan(_t("a"), _t("drop")), "test")["created"]
    tasks.set_state(seeded, ids["drop"], tasks.TaskState.cancelled, "test")
    ev, evd = _done_with_eval(seeded, ids["a"], project)
    boss.accept_task(seeded, ids["a"], ev.id, "test")
    assert boss.deliver(seeded, obj.id, {0: evd, 1: evd}, "test")["objective"]["state"] == "delivered"


def test_plans_cannot_change_a_delivered_objective(seeded, obj, project):
    tid = boss.apply_plan(seeded, obj.id, _plan(_t("a")), "test")["created"]["a"]
    ev, evd = _done_with_eval(seeded, tid, project)
    boss.accept_task(seeded, tid, ev.id, "test")
    boss.deliver(seeded, obj.id, {0: evd, 1: evd}, "test")
    with pytest.raises(PolicyDenied) as e:
        boss.apply_plan(seeded, obj.id, _plan(_t("late")), "test")
    assert e.value.reasons == ["objective_not_open"]
