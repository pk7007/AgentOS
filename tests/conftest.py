import pytest


@pytest.fixture
def cli(capsys):
    from agentos.cli import main

    def run(argv):
        code = main(argv)
        cap = capsys.readouterr()
        return code, cap.out, cap.err

    return run


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "agentos-home"
    monkeypatch.setenv("AGENTOS_HOME", str(h))
    monkeypatch.setenv("AGENTOS_ACTOR", "test")
    return h


@pytest.fixture
def conn(home):
    from agentos import db

    c = db.connect()
    db.migrate(c)
    yield c
    c.close()


def make_repo(path):
    import subprocess

    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path / "My Repo")


@pytest.fixture
def project(conn, repo):
    from agentos import projects

    return projects.activate(conn, repo, actor="test")


DEFINITIONS = __import__("pathlib").Path(__file__).resolve().parents[1] / "definitions" / "agents"


@pytest.fixture
def seeded(conn):
    from agentos import templates

    templates.seed(conn, DEFINITIONS, actor="test")
    return conn


@pytest.fixture
def task(conn, project):
    from agentos import tasks

    return tasks.add_task(conn, project.id, "fixture task", actor="test")


@pytest.fixture
def instance(seeded, project, task):
    """An agent instance inserted directly in RUNNING state (bypasses admission)."""
    from agentos.util import new_id, now_iso

    iid, ts = new_id("ag"), now_iso()
    seeded.execute(
        "INSERT INTO agent_instances(id, template_id, template_version, project_id, task_id, parent_id, depth,"
        " host, state, created_at, updated_at) VALUES (?, 'implementer', 1, ?, ?, NULL, 0, 'test', 'RUNNING', ?, ?)",
        (iid, project.id, task.id, ts, ts),
    )
    return iid
