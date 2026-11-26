"""End-to-end CLI flows: approvals, emergency stop, agent lifecycle, evaluations, recruit, memory, projects, templates."""

import json

import pytest

from agentos.performance import WEIGHTS


@pytest.fixture
def ready(cli, home, repo, monkeypatch):
    cli(["init"])
    cli(["template", "seed"])
    cli(["project", "activate", str(repo)])
    monkeypatch.chdir(repo)  # like a host: commands run from inside the repository
    return repo


def _j(result):
    code, out, err = result
    assert code == 0, err
    return json.loads(out)


def _task(cli, repo, title="t"):
    return _j(cli(["task", "add", title, "--project", str(repo), "--json"]))["id"]


def _admit(cli, repo, task, template="implementer"):
    d = _j(cli(["agent", "admit", "--project", str(repo), "--task", task, "--template", template, "--host", "cc",
                "--json"]))
    return d["instance_id"]


def test_approval_lifecycle(cli, ready, owner_tty):
    a = _j(cli(["approval", "request", "deploy", "--params", '{"env": "prod"}', "--json"]))
    assert cli(["approval", "check", "deploy", "--params", '{"env": "prod"}'])[0] == 3
    assert _j(cli(["approval", "grant", a["id"], "--json"]))["status"] == "granted"
    assert cli(["approval", "check", "deploy", "--params", '{"env": "prod"}'])[0] == 0
    assert cli(["approval", "check", "deploy", "--params", '{"env": "dev"}'])[0] == 3
    assert _j(cli(["approval", "consume", a["id"], "--json"]))["status"] == "consumed"
    assert cli(["approval", "consume", a["id"]])[0] == 3
    assert cli(["approval", "deny", a["id"]])[0] == 3
    assert [x["status"] for x in _j(cli(["approval", "list", "--json"]))] == ["consumed"]


def test_approval_grant_needs_owner(cli, ready):
    a = _j(cli(["approval", "request", "deploy", "--json"]))
    code, _, err = cli(["approval", "grant", a["id"]])
    assert code == 3 and "terminal" in err


def test_approval_deny_and_bad_params(cli, ready):
    a = _j(cli(["approval", "request", "x", "--json"]))
    assert _j(cli(["approval", "deny", a["id"], "--json"]))["status"] == "denied"
    assert _j(cli(["approval", "list", "--status", "pending", "--json"])) == []
    assert cli(["approval", "request", "x", "--params", "not json"])[0] == 2
    assert cli(["approval", "request", "x", "--params", "[1]"])[0] == 2
    assert cli(["approval", "grant", "apr_000000000000"])[0] == 4


def test_emergency_stop_blocks_admission_and_lift_needs_owner(cli, ready, monkeypatch):
    task = _task(cli, ready)
    assert _j(cli(["stop", "--reason", "drill", "--json"]))["emergency_stop"] is True
    code, out, _ = cli(["agent", "admit", "--project", str(ready), "--task", task, "--template", "researcher",
                        "--json"])
    assert code == 3 and "emergency_stop" in json.loads(out)["reasons"]
    assert cli(["stop", "--lift"])[0] == 3
    from agentos import governance

    monkeypatch.setattr(governance, "_default_isatty", lambda: True)
    monkeypatch.setattr(governance, "_default_prompt", lambda msg: "I APPROVE lift emergency stop")
    assert _j(cli(["stop", "--lift", "--json"]))["emergency_stop"] is False


def test_agent_lifecycle_via_cli(cli, ready):
    iid = _admit(cli, ready, _task(cli, ready))
    assert _j(cli(["agent", "transition", iid, "RUNNING", "--json"]))["state"] == "RUNNING"
    listed = _j(cli(["agent", "list", "--project", str(ready), "--active", "--json"]))
    assert [x["id"] for x in listed] == [iid]
    assert cli(["agent", "transition", iid, "ARCHIVED"])[0] == 3
    assert _j(cli(["agent", "transition", iid, "CANCELLED", "--json"]))["state"] == "CANCELLED"
    assert _j(cli(["agent", "transition", iid, "TERMINATED", "--reason", "stuck", "--json"]))["state"] == \
        "TERMINATED (unconfirmed)"
    assert _j(cli(["agent", "inspect", iid, "--json"]))["last_reason"] == "stuck"
    assert _j(cli(["agent", "list", "--project", str(ready), "--active", "--json"])) == []
    assert cli(["agent", "transition", iid, "ARCHIVED"])[0] == 3  # stop not confirmed yet
    assert _j(cli(["agent", "confirm-stop", iid, "--json"]))["state"] == "TERMINATED"
    assert cli(["agent", "confirm-stop", iid])[0] == 3
    assert _j(cli(["agent", "transition", iid, "ARCHIVED", "--json"]))["state"] == "ARCHIVED"
    assert cli(["agent", "inspect", "ag_000000000000"])[0] == 4


def test_eval_perf_and_recruit(cli, ready):
    iid = _admit(cli, ready, _task(cli, ready))
    reviewer = _admit(cli, ready, _task(cli, ready, "review"), "reviewer")
    proof = _j(cli(["evidence", "run", "--json", "--", "python", "-c", "print('3 passed')"]))
    assert proof["exit_code"] == 0 and "3 passed" in proof["output_tail"] and proof["id"].startswith("evd_")
    assert _j(cli(["evidence", "show", proof["id"], "--json"]))["command"] == ["python", "-c", "print('3 passed')"]
    scores = [x for k in WEIGHTS for x in ("--score", f"{k}=85")]
    e = _j(cli(["eval", "record", iid, "--evaluator", reviewer, "--category", "coding", *scores,
                "--evidence", proof["id"], "--json"]))
    assert e["instance_id"] == iid and e["evaluator_id"] == reviewer
    assert cli(["eval", "record", iid, "--evaluator", reviewer, "--category", "coding", *scores,
                "--evidence", proof["id"]])[0] == 3  # one grade per evaluator and category
    assert cli(["eval", "record", iid, "--evaluator", "r", "--category", "coding", "--score", "x"])[0] == 2
    assert cli(["eval", "record", iid, "--evaluator", "r", "--category", "coding", "--score", "x=abc"])[0] == 2
    assert cli(["eval", "record", iid, "--evaluator", "made-up", "--category", "review", *scores,
                "--evidence", proof["id"]])[0] == 3
    assert cli(["eval", "record", iid, "--evaluator", iid, "--category", "coding", *scores,
                "--evidence", "e"])[0] == 3
    p = _j(cli(["perf", "show", "implementer", "--json"]))
    assert p["n"] == 1 and p["recommendation"] == "insufficient_evidence"
    r = _j(cli(["recruit", "--cap", "review", "--json"]))
    assert r["candidates"][0]["template_id"] == "reviewer" and r["capability_gap"] == []
    gap = _j(cli(["recruit", "--cap", "quantum-chemistry", "--json"]))
    assert gap["candidates"] == [] and gap["capability_gap"] == ["quantum-chemistry"]


def test_memory_cli_round_trip(cli, ready, tmp_path):
    p = ["--project", str(ready)]
    r = _j(cli(["memory", "add", "project", "use sqlite wal mode", "--source", "docs/adr-1.md", *p, "--json"]))
    hits = _j(cli(["memory", "search", "sqlite", *p, "--json"]))
    assert [h["id"] for h in hits] == [r["id"]]
    c = _j(cli(["memory", "correct", r["id"], "use sqlite wal mode with busy timeout", *p, "--json"]))
    assert c["version"] == 2
    assert [h["id"] for h in _j(cli(["memory", "search", "busy", *p, "--json"]))] == [c["id"]]
    out = tmp_path / "mem.json"
    assert _j(cli(["memory", "export", *p, "--out", str(out), "--json"]))["records"] == 2
    assert len(json.loads(out.read_text())) == 2
    assert len(_j(cli(["memory", "export", *p, "--json"]))) == 2
    assert _j(cli(["memory", "delete", c["id"], *p, "--json"]))["deleted"] is True
    assert _j(cli(["memory", "search", "busy", *p, "--json"])) == []


def test_project_list_and_deactivate(cli, ready):
    listed = _j(cli(["project", "list", "--json"]))
    assert len(listed) == 1 and listed[0]["active"] is True
    _j(cli(["project", "deactivate", str(ready), "--json"]))
    assert _j(cli(["project", "list", "--json"]))[0]["active"] is False
    assert cli(["task", "add", "x", "--project", str(ready)])[0] == 3


def test_template_status_verbs(cli, ready, owner_tty):
    assert _j(cli(["template", "suspend", "planner", "--reason", "noisy", "--json"]))["status"] == "suspended"
    assert _j(cli(["template", "list", "--status", "suspended", "--json"]))[0]["id"] == "planner"
    assert _j(cli(["template", "reinstate", "planner", "--reason", "ok", "--json"]))["status"] == "active"
    assert _j(cli(["template", "quarantine", "planner", "--reason", "bad", "--json"]))["status"] == "quarantined"
    assert _j(cli(["template", "inspect", "planner", "--json"]))["status"] == "quarantined"
    assert _j(cli(["template", "retire", "planner", "--reason", "gone", "--json"]))["status"] == "retired"
    assert cli(["template", "inspect", "nope"])[0] == 4
