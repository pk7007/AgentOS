import json
import subprocess

import pytest

from agentos import admission, handover, paths, projects
from agentos.admission import AdmitRequest
from agentos.errors import PolicyDenied, UsageError
from tests.conftest import make_repo


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   check=True, capture_output=True)


def commit(repo, name="a.txt", text="x"):
    (repo / name).write_text(text)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", f"add {name}")


@pytest.fixture
def ready(conn, repo, project):
    commit(repo)
    return conn, repo, project


def _create(conn, repo, project, **kw):
    return handover.create(conn, project.id, repo, host="codex", objective=kw.get("objective", "build parser"),
                           next_action="write tests", actor="t")


def test_create_and_resume_cross_host(ready):
    conn, repo, project = ready
    h = _create(conn, repo, project)
    assert h.git["head"] and h.usage_note == "estimates only"
    assert (paths.handovers_dir() / f"{h.id}.json").exists()
    r = handover.resume(conn, h.id, repo, host="cc", actor="t")
    assert r.ok and r.warnings == [] and r.handover.objective == "build parser"


def test_second_resume_denied(ready):
    conn, repo, project = ready
    h = _create(conn, repo, project)
    handover.resume(conn, h.id, repo, host="cc", actor="t")
    with pytest.raises(PolicyDenied) as e:
        handover.resume(conn, h.id, repo, host="codex", actor="t")
    assert "already_resumed" in e.value.reasons


@pytest.mark.parametrize("bad", ["../../etc/passwd", "ho_123", "ho_ZZZZZZZZZZZZ", "x/ho_0123456789ab"])
def test_bad_id_rejected(ready, bad):
    conn, repo, _ = ready
    with pytest.raises(UsageError):
        handover.resume(conn, bad, repo, host="cc", actor="t")


def test_wrong_repo_denied(ready, tmp_path):
    conn, repo, project = ready
    other = make_repo(tmp_path / "other")
    projects.activate(conn, other, actor="t")
    h = _create(conn, repo, project)
    with pytest.raises(PolicyDenied) as e:
        handover.resume(conn, h.id, other, host="cc", actor="t")
    assert "project_mismatch" in e.value.reasons


def test_head_advanced_and_diverged(ready):
    conn, repo, project = ready
    h1 = _create(conn, repo, project)
    commit(repo, "b.txt")
    assert "head_advanced" in handover.resume(conn, h1.id, repo, host="cc", actor="t").warnings
    h2 = _create(conn, repo, project)
    git(repo, "checkout", "-q", "--orphan", "elsewhere")
    commit(repo, "c.txt")
    assert "head_diverged" in handover.resume(conn, h2.id, repo, host="cc", actor="t").warnings


def test_dirty_tree_warning(ready):
    conn, repo, project = ready
    h = _create(conn, repo, project)
    (repo / "a.txt").write_text("changed")
    assert "dirty_tree" in handover.resume(conn, h.id, repo, host="cc", actor="t").warnings


def test_orphaned_instances_warning(ready, seeded):
    conn, repo, project = ready
    from agentos import tasks

    t = tasks.add_task(conn, project.id, "t", actor="t")
    d = admission.admit(conn, AdmitRequest(project_id=project.id, task_id=t.id, template_id="researcher",
                                           host="codex"), actor="t")
    h = _create(conn, repo, project)
    warnings = handover.resume(conn, h.id, repo, host="cc", actor="t").warnings
    assert f"orphaned_instances:{d.instance_id}" in warnings


def test_secrets_not_in_handover_file(ready):
    conn, repo, project = ready
    h = _create(conn, repo, project, objective="deploy with password=hunter2 now")
    text = (paths.handovers_dir() / f"{h.id}.json").read_text()
    assert "hunter2" not in text and json.loads(text)["id"] == h.id


def test_repo_without_commits(conn, repo, project):
    h = _create(conn, repo, project)
    assert h.git["head"] is None
    assert handover.resume(conn, h.id, repo, host="cc", actor="t").ok
