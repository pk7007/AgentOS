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
