"""`agentos intel` through the real CLI: every command answers in JSON, refusals use the usual exit codes."""

import json

import pytest


@pytest.fixture
def ready(cli, home, repo, monkeypatch):
    cli(["init"])
    cli(["template", "seed"])
    cli(["project", "activate", str(repo)])
    monkeypatch.chdir(repo)
    return repo


def _j(result):
    code, out, err = result
    assert code == 0, err
    return json.loads(out)


def test_every_intel_command_answers(cli, ready):
    a = _j(cli(["task", "add", "build parser", "--cap", "implementation", "--json"]))["id"]
    b = _j(cli(["task", "add", "review parser", "--cap", "review", "--json"]))["id"]
    _j(cli(["task", "dep", b, "--on", a, "--json"]))
    staffing = _j(cli(["intel", "staffing", "--json"]))
    assert staffing["waves"] == 2 and staffing["peak_parallel"] == 1
    assert _j(cli(["intel", "route", a, "--json"]))["tier"] == "small"
    _j(cli(["memory", "add", "project", "the parser must accept tabs", "--json"]))
    ctx = _j(cli(["intel", "context", a, "--budget", "100", "--json"]))
    assert ctx["included"] and ctx["used_tokens_est"] <= 100
    assert _j(cli(["intel", "skills", "--json"])) == []
    assert "findings" in _j(cli(["intel", "org", "--json"]))
    assert _j(cli(["intel", "failures", "--json"]))["patterns"] == []
    assert _j(cli(["intel", "compete", a, "--json"]))["verdict"] == "no_eligible_solution"
    assert _j(cli(["intel", "forecast", "--json"]))["projected"] is None
    assert _j(cli(["intel", "profile", "--json"]))["tasks"] == {"pending": 2}
    assert _j(cli(["intel", "lessons", "--json"])) == []
    assert _j(cli(["intel", "governance", "--json"]))["ok"] is True


def test_refusals_use_the_usual_exit_codes(cli, ready, home):
    assert cli(["intel", "skill-create", "evd_missing", "--json"])[0] == 4
    assert cli(["intel", "share", "mem_missing", "--json"])[0] == 4
    code, _, err = cli(["intel", "context", "task_missing", "--json"])
    assert code == 4
    mem = _j(cli(["memory", "add", "semantic", "a lesson from one project", "--json"]))["id"]
    code, _, err = cli(["intel", "share", mem, "--json"])
    assert code == 3 and "not_validated" in err
    import sqlite3

    conn = sqlite3.connect(home / "state" / "agentos.db")
    conn.execute("UPDATE events SET payload='{}' WHERE seq=1")
    conn.commit()
    conn.close()
    code, out, _ = cli(["intel", "governance", "--json"])
    assert code == 5 and json.loads(out)["ok"] is False
