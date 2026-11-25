import pytest

from agentos import admission, governance, governor, lifecycle, tasks, templates
from agentos.admission import AdmitRequest
from agentos.lifecycle import AgentState
from agentos.templates import TemplateStatus


def _admit(conn, project, task_id, template="implementer", parent=None):
    return admission.admit(conn, AdmitRequest(project_id=project.id, task_id=task_id, template_id=template,
                                              parent_instance_id=parent, host="test"), actor="t")


def _tasks(conn, project, n):
    return [tasks.add_task(conn, project.id, f"t{i}", actor="t") for i in range(n)]


def test_admit_happy_path(seeded, project, task):
    d = _admit(seeded, project, task.id)
    assert d.allowed and d.reasons == []
    assert lifecycle.get_instance(seeded, d.instance_id).state == AgentState.ASSIGNED
    assert lifecycle.active_count(seeded) == 1


def test_max_concurrent(seeded, project):
    ts = _tasks(seeded, project, 5)
    assert all(_admit(seeded, project, t.id).allowed for t in ts[:4])
    d = _admit(seeded, project, ts[4].id)
    assert not d.allowed and "max_concurrent" in d.reasons and d.instance_id is None


def test_depth_and_delegation(seeded, project):
    ts = _tasks(seeded, project, 4)
    lead = _admit(seeded, project, ts[0].id, "lead")
    child = _admit(seeded, project, ts[1].id, "lead", parent=lead.instance_id)
    grandchild = _admit(seeded, project, ts[2].id, "implementer", parent=child.instance_id)
    assert lead.allowed and child.allowed and grandchild.allowed
    assert lifecycle.get_instance(seeded, grandchild.instance_id).depth == 2
    governor.set_limit(seeded, "max_concurrent", 4, actor="t")
    too_deep = _admit(seeded, project, ts[3].id, "lead", parent=grandchild.instance_id)
    assert "max_depth" in too_deep.reasons and "parent_cannot_delegate" in too_deep.reasons


def test_duplicate(seeded, project, task):
    assert _admit(seeded, project, task.id).allowed
    assert "duplicate" in _admit(seeded, project, task.id).reasons


def test_all_reasons_collected(seeded, project, task):
    governance.emergency_stop(seeded, actor="t", reason="test")
    templates.set_status(seeded, "implementer", TemplateStatus.suspended, actor="t", reason="x")
    d = _admit(seeded, project, task.id)
    assert {"emergency_stop", "template_unavailable"} <= set(d.reasons)


def test_unknown_task_and_template(seeded, project):
    d = _admit(seeded, project, "task_nope", template="nobody")
    assert {"task_not_found", "template_unavailable"} <= set(d.reasons)


def test_closed_task_not_open(seeded, project, task):
    tasks.set_state(seeded, task.id, tasks.TaskState.cancelled, actor="t")
    assert "task_not_open" in _admit(seeded, project, task.id).reasons


def test_release_on_completion(seeded, project):
    ts = _tasks(seeded, project, 5)
    ids = [_admit(seeded, project, t.id).instance_id for t in ts[:4]]
    lifecycle.transition(seeded, ids[0], AgentState.RUNNING, actor="t")
    lifecycle.transition(seeded, ids[0], AgentState.COMPLETED, actor="t")
    assert _admit(seeded, project, ts[4].id).allowed


def test_max_agents_per_task(seeded, project, task):
    governor.set_limit(seeded, "max_agents_per_task", 1, actor="t")
    first = _admit(seeded, project, task.id)
    lifecycle.transition(seeded, first.instance_id, AgentState.CANCELLED, actor="t")
    assert "max_agents_per_task" in _admit(seeded, project, task.id, "reviewer").reasons


def test_agent_run_budget(seeded, project):
    governor.set_budget(seeded, "project", project.id, "agent_runs", 1, actor="t")
    ts = _tasks(seeded, project, 2)
    assert _admit(seeded, project, ts[0].id).allowed
    d = _admit(seeded, project, ts[1].id)
    assert "budget_exceeded:project:agent_runs" in d.reasons


def test_denial_is_audited(seeded, project):
    _admit(seeded, project, "task_nope")
    n = seeded.execute("SELECT count(*) FROM events WHERE kind='agent.admission_denied'").fetchone()[0]
    assert n == 1


@pytest.mark.parametrize("state", ["COMPLETED", "FAILED", "CANCELLED"])
def test_parent_must_be_active(seeded, project, state):
    ts = _tasks(seeded, project, 2)
    lead = _admit(seeded, project, ts[0].id, "lead").instance_id
    lifecycle.transition(seeded, lead, AgentState.RUNNING, actor="t")
    lifecycle.transition(seeded, lead, AgentState(state), actor="t")
    assert "parent_not_active" in _admit(seeded, project, ts[1].id, parent=lead).reasons
