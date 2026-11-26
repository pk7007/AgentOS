"""Host adapters through the CLI, and work moving between hosts: a task and what was learned start
under one host and continue under the other, in both directions, without any conversation history."""

import json

import pytest

from agentos import adapters


@pytest.fixture
def ready(cli, home, repo, monkeypatch, tmp_path):
    monkeypatch.setattr(adapters, "REPO", tmp_path / "no-repo")
    monkeypatch.setattr(adapters, "host_version", lambda a: "1.0.0")
    cli(["init"])
    cli(["template", "seed"])
    cli(["project", "activate", str(repo)])
    monkeypatch.chdir(repo)
    return repo


def _j(result):
    code, out, err = result
    assert code == 0, err
    return json.loads(out)


def test_install_drift_rollback_and_bootstrap(cli, ready, tmp_path):
    dest = tmp_path / "plug"
    r = _j(cli(["host", "install", "codex", "--dest", str(dest), "--json"]))
    assert r["register"] == f"codex plugin marketplace add {dest.resolve()}"
    assert _j(cli(["host", "drift", "codex", "--json"]))["status"] == "in_sync"
    (dest / "agents" / "lead.toml").write_text("edited", encoding="utf-8")
    code, out, _ = cli(["host", "drift", "codex", "--json"])
    assert code == 3 and json.loads(out)["modified"] == ["agents/lead.toml"]
    _j(cli(["host", "install", "codex", "--dest", str(dest), "--json"]))
    assert _j(cli(["host", "drift", "codex", "--json"]))["status"] == "in_sync"
    _j(cli(["host", "rollback", "codex", "--json"]))
    assert (dest / "agents" / "lead.toml").read_text(encoding="utf-8") == "edited"
    assert [h["status"] for h in _j(cli(["host", "history", "codex", "--json"]))] == ["active", "rolled_back"]
    hosts = {h["host"]: h for h in _j(cli(["host", "list", "--json"]))}
    assert hosts["codex"]["installed"] and hosts["cc"]["configured"] is False
    assert _j(cli(["host", "bootstrap", "codex", "--json"]))["action"] == "added"
    assert (ready / "AGENTS.md").exists()
    assert _j(cli(["host", "bootstrap", "codex", "--remove", "--json"]))["action"] == "removed"
    assert _j(cli(["host", "check", "codex", "--json"]))["verdict"] == "compatible"
    _j(cli(["host", "uninstall", "codex", "--json"]))
    assert cli(["host", "drift", "codex"])[0] == 4
    assert _j(cli(["audit", "verify", "--json"]))["ok"] is True


def test_an_unconfigured_host_is_a_usage_error(cli, ready):
    code, _, err = cli(["host", "install", "cc", "--json"])
    assert code == 2 and "profile" in err


@pytest.mark.parametrize(("first", "second"), [("codex", "cc"), ("cc", "codex")])
def test_work_and_learning_cross_hosts_both_ways(cli, ready, first, second):
    task = _j(cli(["task", "add", "export report", "--cap", "implementation", "--json"]))["id"]
    _j(cli(["task", "start", task, "--json"]))
    _j(cli(["memory", "add", "project", f"decided under {first}: write CSV, not XLSX", "--json"]))
    ho = _j(cli(["handover", "create", "--objective", "ship the export", "--next", "write the CSV writer",
                 "--host", first, "--json"]))
    assert ho["tasks"] == 1
    resumed = _j(cli(["handover", "resume", ho["id"], "--host", second, "--json"]))
    h = resumed["handover"]
    assert resumed["ok"] and h["host"] == first and h["next_action"] == "write the CSV writer"
    assert {t["id"] for t in h["tasks"]} == {task}
    assert not {"messages", "transcript", "conversation"} & set(h)  # structured state only
    found = _j(cli(["memory", "search", "CSV", "--json"]))
    assert any(f"decided under {first}" in m["content"] for m in found)
    worker = _j(cli(["agent", "admit", "--task", task, "--template", "implementer", "--host", second,
                     "--json"]))
    assert worker["allowed"] is True
    listed = {h["id"]: h for h in _j(cli(["handover", "list", "--json"]))}
    assert listed[ho["id"]]["host"] == first and listed[ho["id"]]["resumed_by"] == second
