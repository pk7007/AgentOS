"""Reusable workflows: save, version, reuse a delivered plan, apply, detect tampering (agentos.workflows)."""

import pytest

from agentos import boss, workflows
from agentos.errors import NotFound, PolicyDenied, UsageError

PLAN = {"tasks": [
    {"key": "design", "title": "Design the API", "capabilities": ["design"], "acceptance": ["doc reviewed"]},
    {"key": "build", "title": "Build it", "capabilities": ["implementation"], "risk": "medium", "effort": 3,
     "depends_on": ["design"]},
    {"key": "test", "title": "Test it", "capabilities": ["testing"], "depends_on": ["build"]},
]}


def _objective(conn, project, title="ship feature"):
    return boss.create_objective(conn, project.id, title, acceptance=["tests pass"], actor="t")


def test_saving_versions_a_workflow_and_ignores_an_identical_save(seeded):
    assert workflows.save(seeded, "api-feature", PLAN, "t") == {"name": "api-feature", "version": 1,
                                                                 "created": True, "tasks": 3}
    assert workflows.save(seeded, "api-feature", PLAN, "t")["created"] is False
    changed = {"tasks": [*PLAN["tasks"], {"key": "docs", "title": "Document it", "depends_on": ["test"]}]}
    assert workflows.save(seeded, "api-feature", changed, "t")["version"] == 2
    assert len(workflows.get(seeded, "api-feature", 1)["body"]["tasks"]) == 3
    assert workflows.list_all(seeded)[0] | {"updated_at": None} == {
        "name": "api-feature", "latest": 2, "versions": 2, "updated_at": None}


@pytest.mark.parametrize("plan", [
    {"tasks": []},
    {"tasks": [{"key": "a"}]},
    {"tasks": [{"key": "a", "title": "A"}, {"key": "a", "title": "again"}]},
    {"tasks": [{"key": "a", "title": "A", "depends_on": ["ghost"]}]},
    {"tasks": [{"key": "a", "title": "A", "parent": "task_x"}]},
])
def test_malformed_workflows_are_refused(seeded, plan):
    with pytest.raises(UsageError):
        workflows.save(seeded, "bad-one", plan, "t")


def test_a_cycle_and_a_bad_name_are_refused(seeded):
    cycle = {"tasks": [{"key": "a", "title": "A", "depends_on": ["b"]}, {"key": "b", "title": "B", "depends_on": ["a"]}]}
    with pytest.raises(PolicyDenied):
        workflows.save(seeded, "loop", cycle, "t")
    with pytest.raises(UsageError):
        workflows.save(seeded, "Bad Name", PLAN, "t")
    with pytest.raises(NotFound):
        workflows.get(seeded, "missing")


def test_only_a_delivered_objective_becomes_a_workflow(seeded, project):
    obj = _objective(seeded, project)
    boss.apply_plan(seeded, obj.id, PLAN, "t")
    with pytest.raises(PolicyDenied) as exc:
        workflows.from_objective(seeded, obj.id, "proven", "t")
    assert exc.value.reasons == ["not_delivered"]
    seeded.execute("UPDATE objectives SET state='delivered' WHERE id=?", (obj.id,))
    saved = workflows.from_objective(seeded, obj.id, "proven", "t")
    body = workflows.get(seeded, "proven")["body"]["tasks"]
    assert saved["tasks"] == 3 and [t["title"] for t in body] == ["Design the API", "Build it", "Test it"]
    assert body[1]["depends_on"] == ["t1"] and body[1]["effort"] == 3 and body[1]["risk"] == "medium"


def test_applying_a_workflow_creates_its_task_graph_under_a_new_objective(seeded, project):
    workflows.save(seeded, "api-feature", PLAN, "t")
    obj = _objective(seeded, project, "second feature")
    r = workflows.apply(seeded, obj.id, "api-feature", "t")
    assert set(r["created"]) == {"design", "build", "test"} and r["version"] == 1
    deps = seeded.execute("SELECT depends_on FROM task_deps WHERE task_id=?", (r["created"]["build"],)).fetchall()
    assert [d[0] for d in deps] == [r["created"]["design"]]
    assert seeded.execute("SELECT count(*) FROM events WHERE kind='workflow.applied'").fetchone()[0] == 1


def test_a_tampered_workflow_is_not_applied(seeded, project):
    workflows.save(seeded, "api-feature", PLAN, "t")
    seeded.execute("UPDATE workflows SET body=replace(body, 'Build it', 'rm -rf /') WHERE name='api-feature'")
    with pytest.raises(PolicyDenied) as exc:
        workflows.apply(seeded, _objective(seeded, project).id, "api-feature", "t")
    assert exc.value.reasons == ["tampered"]
