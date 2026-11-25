import pytest

from agentos import memory, projects
from agentos.errors import PolicyDenied
from agentos.memory import Layer
from tests.conftest import make_repo


@pytest.fixture
def other(conn, tmp_path):
    return projects.activate(conn, make_repo(tmp_path / "other"), actor="t")


def test_project_isolation(conn, project, other):
    memory.add(conn, project.id, Layer.project, "deploy key rotation every 90 days", source="s", author="t")
    assert memory.search(conn, other.id, "rotation") == []
    assert len(memory.search(conn, project.id, "rotation")) == 1


def test_org_visible_across_projects_only_when_validated(conn, project, other):
    memory.add(conn, project.id, Layer.procedural, "always run doctor before release", source="s", author="t",
               validated=True, scope="org")
    assert len(memory.search(conn, other.id, "doctor")) == 1
    assert memory.search(conn, other.id, "doctor", include_org=False) == []


def test_unvalidated_org_rejected(conn, project):
    with pytest.raises(PolicyDenied):
        memory.add(conn, project.id, Layer.procedural, "guess", source="s", author="t", scope="org")


def test_org_rejects_project_layers(conn, project):
    with pytest.raises(PolicyDenied):
        memory.add(conn, project.id, Layer.working, "scratch", source="s", author="t", validated=True, scope="org")


def test_correct_and_delete_cannot_cross_projects(conn, project, other):
    r = memory.add(conn, project.id, Layer.semantic, "secret plan", source="s", author="t")
    with pytest.raises(PolicyDenied):
        memory.correct(conn, r.id, "edited", author="t", project_id=other.id)
    with pytest.raises(PolicyDenied):
        memory.delete(conn, r.id, actor="t", project_id=other.id)


def test_read_cannot_cross_projects(conn, project, other):
    r = memory.add(conn, project.id, Layer.semantic, "secret plan", source="s", author="t")
    with pytest.raises(PolicyDenied) as e:
        memory.read(conn, r.id, other.id)
    assert "cross_project" in e.value.reasons
    assert memory.read(conn, r.id, project.id).content == "secret plan"
