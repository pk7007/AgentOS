"""Agent Factory and workforce management through the CLI."""

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


def _task(cli, title, *caps):
    return _j(cli(["task", "add", title, *[x for c in caps for x in ("--cap", c)], "--json"]))["id"]


def _admit(cli, task, template="implementer"):
    return _j(cli(["agent", "admit", "--task", task, "--template", template, "--host", "cc",
                   "--json"]))["instance_id"]


def test_factory_fills_a_gap_and_recruits(cli, ready):
    task = _task(cli, "deploy", "kubernetes")
    r = _j(cli(["factory", "recruit", "--task", task, "--host", "cc", "--json"]))
    assert r["status"] == "admitted" and r["template_id"] == "x-kubernetes"
    assert _j(cli(["template", "inspect", "x-kubernetes", "--json"]))["status"] == "active"
    listed = _j(cli(["factory", "list", "--json"]))
    assert [p["status"] for p in listed] == ["registered"]
    assert _j(cli(["factory", "show", listed[0]["id"], "--json"]))["base_template"] is None
    assert _j(cli(["factory", "expire", "--json"])) == []
    assert cli(["audit", "verify"])[0] == 0


def test_wider_specialist_needs_the_owner(cli, ready, tmp_path, owner_tty):
    extra = tmp_path / "extra.toml"
    extra.write_text('can_delegate = true\ninstructions = "Plan the rollout."\n', encoding="utf-8")
    p = _j(cli(["factory", "propose", "--cap", "terraform", "--file", str(extra), "--json"]))
    assert p["owner_reasons"] == ["delegation"]
    code, out, _ = cli(["factory", "register", p["id"], "--json"])
    pending = json.loads(out)
    assert code == 3 and pending["status"] == "awaiting_owner"
    _j(cli(["approval", "grant", pending["approval_id"], "--json"]))
    assert _j(cli(["factory", "register", p["id"], "--json"]))["status"] == "registered"


def test_factory_refusals(cli, ready):
    assert cli(["factory", "propose", "--cap", "review"])[0] == 3  # already covered
    p = _j(cli(["factory", "propose", "--cap", "helm", "--json"]))
    assert _j(cli(["factory", "reject", p["id"], "--reason", "later", "--json"]))["status"] == "rejected"
    assert cli(["factory", "register", p["id"]])[0] == 3
    assert cli(["factory", "show", "fp_000000000000"])[0] == 4
    task = _task(cli, "deploy", "kubernetes")
    _j(cli(["stop", "--reason", "drill", "--json"]))
    code, out, _ = cli(["factory", "recruit", "--task", task, "--host", "cc", "--json"])
    assert code == 3 and "emergency_stop" in json.loads(out)["reasons"]


def test_split_then_terminate_and_transfer(cli, ready, tmp_path):
    from agentos import db

    task = _task(cli, "big change", "python")
    conn = db.connect()
    conn.execute("UPDATE tasks SET effort=2 WHERE id=?", (task,))
    conn.commit()
    conn.close()
    parts = _j(cli(["workforce", "split", task, "--json"]))["parts"]
    assert len(parts) == 2
    first, second = _admit(cli, parts[0]), _admit(cli, parts[1])

    code, _, err = cli(["workforce", "transfer", first, "--host", "cc", "--json"])
    assert code == 3 and "no_replacement" in json.loads(err)["reasons"]  # only implementer covers python
    spec = tmp_path / "py.toml"
    spec.write_text('id = "py-only"\nname = "Py"\nrole = "implementer"\ndepartment = "engineering"\n'
                    'description = "python only"\ncapabilities = ["python"]\ninstructions = "x"\n', encoding="utf-8")
    _j(cli(["template", "add", str(spec), "--json"]))
    moved = _j(cli(["workforce", "transfer", first, "--host", "cc", "--note", "parser half done", "--json"]))
    assert moved["status"] == "admitted" and moved["template_id"] == "py-only"
    assert moved["stopped"]["state"] == "CANCELLED" and moved["briefing"]["memory_id"]
    assert [t["from_instance"] for t in _j(cli(["workforce", "transfers", "--json"]))] == [first]

    stopped = _j(cli(["workforce", "terminate", second, "--reason", "stuck", "--note", "look at io.py", "--json"]))
    assert stopped["state"] == "CANCELLED" and stopped["memory_id"] and "confirm-stop" in stopped["next"]
    assert cli(["workforce", "terminate", second, "--reason", "again"])[0] == 3


def test_review_succession_contract_and_rehab_checks(cli, ready, tmp_path):
    assert _j(cli(["workforce", "review", "--json"])) == []
    plans = {p["template_id"]: p for p in _j(cli(["workforce", "succession", "--json"]))}
    assert plans["implementer"]["status"] == "single_point_of_failure"
    r = _j(cli(["workforce", "contract", "--json"]))
    assert r["archived_workers"] == [] and r["dissolved_departments"] == []
    assert cli(["workforce", "probation", "planner"])[0] == 3
    change = tmp_path / "v2.toml"
    change.write_text('description = "better"\n', encoding="utf-8")
    code, _, err = cli(["workforce", "rehab", "planner", "--file", str(change), "--json"])
    assert code == 3 and "not_underperforming" in json.loads(err)["reasons"]


def test_workforce_records_are_project_scoped(cli, ready, tmp_path, monkeypatch):
    task = _task(cli, "t", "python")
    worker = _admit(cli, task)
    other = tmp_path / "other"
    other.mkdir()
    (other / ".git").mkdir()
    cli(["project", "activate", str(other)])
    monkeypatch.chdir(other)
    code, _, err = cli(["workforce", "terminate", worker, "--reason", "x", "--json"])
    assert code == 3 and "cross_project" in json.loads(err)["reasons"]
