"""`agentos dashboard` and `agentos observe` through the real CLI, after real admissions and a stop."""

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


def test_views_after_real_work(cli, ready):
    task = _j(cli(["task", "add", "build", "--json"]))["id"]
    lead = _j(cli(["agent", "admit", "--task", task, "--template", "lead", "--host", "codex", "--json"]))
    worker = _j(cli(["agent", "admit", "--task", task, "--template", "implementer", "--host", "codex",
                     "--parent", lead["instance_id"], "--json"]))
    assert worker["allowed"]
    agents = _j(cli(["observe", "agents", "--json"]))
    assert {a["id"] for a in agents} == {lead["instance_id"], worker["instance_id"]}
    tree = _j(cli(["observe", "tree", "--json"]))
    assert tree[0]["id"] == lead["instance_id"] and tree[0]["children"][0]["id"] == worker["instance_id"]
    code, out, _ = cli(["observe", "tree"])
    assert code == 0 and out.startswith("`-- lead")
    assert _j(cli(["observe", "recruitment", "--json"]))["counts"] == {"agent.admitted": 2}
    assert _j(cli(["observe", "progress", "--json"]))["objectives"][0]["tasks"] == {"pending": 1}
    _j(cli(["workforce", "terminate", worker["instance_id"], "--reason", "drill", "--json"]))
    assert _j(cli(["observe", "terminations", "--json"]))["unconfirmed_stops"][0]["state"] == "CANCELLED"
    assert _j(cli(["observe", "resources", "--json"]))["slots_held"] == 2
    assert _j(cli(["observe", "performance", "--json"])) == []
    assert _j(cli(["observe", "experiments", "--json"]))["counts"] == {}
    assert _j(cli(["observe", "changes", "--json"])) == {"accepted": [], "rejected": []}
    _j(cli(["stop", "--reason", "drill", "--json"]))
    denied = cli(["agent", "admit", "--task", task, "--template", "implementer", "--host", "codex", "--json"])
    assert denied[0] == 3
    assert _j(cli(["observe", "controls", "--json"]))["emergency_stop"] is True
    inc = _j(cli(["observe", "incidents", "--json"]))
    assert inc["audit_chain_ok"] and "governance.stop" in {i["kind"] for i in inc["incidents"]}
    code, out, _ = cli(["dashboard"])
    assert code == 0 and "emergency stop: ON" in out and "build" not in out  # objectives, not task titles
    assert _j(cli(["dashboard", "--json"]))["active_agents"] == 2
    assert len(_j(cli(["observe", "agents", "--all-projects", "--json"]))) == 2
