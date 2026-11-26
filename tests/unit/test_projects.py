from pathlib import Path

import pytest

from agentos import projects
from agentos.errors import NotFound, PolicyDenied
from tests.conftest import make_repo


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows paths are case-insensitive")
def test_same_repo_different_spelling_same_id(repo):
    assert projects.project_id_for(repo) == projects.project_id_for(Path(str(repo).upper() + "\\"))


def test_trailing_separator_same_id(repo):
    import os

    assert projects.project_id_for(repo) == projects.project_id_for(Path(str(repo) + os.sep))


def test_subdir_maps_to_repo_root(repo):
    sub = repo / "a" / "b"
    sub.mkdir(parents=True)
    assert projects.project_id_for(sub) == projects.project_id_for(repo)


def test_non_git_dir_uses_itself(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    assert projects.project_id_for(d).startswith("prj_")


def test_require_active_denies_inactive(conn, repo):
    p = projects.activate(conn, repo, actor="t")
    projects.deactivate(conn, p.id, actor="t")
    with pytest.raises(PolicyDenied) as e:
        projects.require_active(conn, p.id)
    assert "project_inactive" in e.value.reasons


def test_activate_twice_is_idempotent_and_audited(conn, repo):
    projects.activate(conn, repo, actor="t")
    projects.activate(conn, repo, actor="t")
    assert len(projects.list_projects(conn)) == 1
    n = conn.execute("SELECT count(*) FROM events WHERE kind='project.activated'").fetchone()[0]
    assert n == 2


def test_get_unknown_project(conn):
    with pytest.raises(NotFound):
        projects.get_project(conn, "prj_nope")


def test_two_repos_two_projects(conn, tmp_path):
    a = projects.activate(conn, make_repo(tmp_path / "a"), actor="t")
    b = projects.activate(conn, make_repo(tmp_path / "b"), actor="t")
    assert a.id != b.id
