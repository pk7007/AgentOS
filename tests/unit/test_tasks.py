import pytest

from agentos import projects, tasks
from agentos.errors import PolicyDenied
from agentos.tasks import TaskState
from tests.conftest import make_repo


def _t(conn, project, title, **kw):
    return tasks.add_task(conn, project.id, title, actor="t", **kw)


def test_cycle_rejected(conn, project):
    a, b, c = (_t(conn, project, x) for x in "abc")
    tasks.add_dependency(conn, b.id, a.id, actor="t")
    tasks.add_dependency(conn, c.id, b.id, actor="t")
    with pytest.raises(PolicyDenied) as e:
        tasks.add_dependency(conn, a.id, c.id, actor="t")
    assert "cycle" in e.value.reasons


def test_self_dependency_rejected(conn, project):
    a = _t(conn, project, "a")
    with pytest.raises(PolicyDenied) as e:
        tasks.add_dependency(conn, a.id, a.id, actor="t")
    assert "cycle" in e.value.reasons


def test_start_requires_deps_done(conn, project):
    a, b = _t(conn, project, "a"), _t(conn, project, "b")
    tasks.add_dependency(conn, b.id, a.id, actor="t")
    with pytest.raises(PolicyDenied) as e:
        tasks.set_state(conn, b.id, TaskState.running, actor="t")
    assert "dependencies_incomplete" in e.value.reasons
    tasks.set_state(conn, a.id, TaskState.running, actor="t")
    tasks.set_state(conn, a.id, TaskState.done, actor="t")
    assert tasks.set_state(conn, b.id, TaskState.running, actor="t").state == TaskState.running


def test_ready_orders_by_priority(conn, project):
    _t(conn, project, "low", priority=10)
    _t(conn, project, "high", priority=90)
    blocked = _t(conn, project, "blocked", priority=99)
    dep = _t(conn, project, "dep", priority=1)
    tasks.add_dependency(conn, blocked.id, dep.id, actor="t")
    titles = [t.title for t in tasks.ready_tasks(conn, project.id)]
    assert titles == ["high", "low", "dep"]


def test_retry_limit(conn, project):
    a = _t(conn, project, "a")
    for _ in range(2):
        tasks.set_state(conn, a.id, TaskState.running, actor="t")
        tasks.set_state(conn, a.id, TaskState.failed, actor="t")
        tasks.set_state(conn, a.id, TaskState.pending, actor="t")
    tasks.set_state(conn, a.id, TaskState.running, actor="t")
    tasks.set_state(conn, a.id, TaskState.failed, actor="t")
    with pytest.raises(PolicyDenied) as e:
        tasks.set_state(conn, a.id, TaskState.pending, actor="t")
    assert "retry_limit" in e.value.reasons


def test_illegal_transition(conn, project):
    a = _t(conn, project, "a")
    with pytest.raises(PolicyDenied) as e:
        tasks.set_state(conn, a.id, TaskState.done, actor="t")
    assert "illegal_transition" in e.value.reasons


def test_depth_limit(conn, project):
    parent = _t(conn, project, "root")
    for i in range(tasks.MAX_TASK_DEPTH):
        parent = _t(conn, project, f"d{i}", parent_id=parent.id)
    assert parent.depth == tasks.MAX_TASK_DEPTH
    with pytest.raises(PolicyDenied) as e:
        _t(conn, project, "too deep", parent_id=parent.id)
    assert "max_task_depth" in e.value.reasons


def test_cross_project_dependency_denied(conn, project, tmp_path):
    other = projects.activate(conn, make_repo(tmp_path / "other"), actor="t")
    a = _t(conn, project, "a")
    b = tasks.add_task(conn, other.id, "b", actor="t")
    with pytest.raises(PolicyDenied) as e:
        tasks.add_dependency(conn, a.id, b.id, actor="t")
    assert "cross_project" in e.value.reasons


def test_inactive_project_cannot_add(conn, project):
    projects.deactivate(conn, project.id, actor="t")
    with pytest.raises(PolicyDenied):
        _t(conn, project, "a")
