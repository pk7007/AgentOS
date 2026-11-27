"""The Phase 9 command groups through the real CLI: msg, claim, workflow, health, policy, retention, bench, the
new intel and observe views, and the generators. Refusals use the usual exit codes."""

import json

import pytest

from agentos import mcp_server


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


def _admit(cli, task, template):
    return _j(cli(["agent", "admit", "--task", task, "--template", template, "--host", "codex", "--json"]))["instance_id"]


def test_messages_claims_and_escalations(cli, ready):
    task = _j(cli(["task", "add", "rate limiting", "--json"]))["id"]
    imp, rev = _admit(cli, task, "implementer"), _admit(cli, task, "reviewer")
    _j(cli(["msg", "send", "--from", imp, "--to", rev, "--kind", "request", "ready for review", "--json"]))
    assert [m["body"] for m in _j(cli(["msg", "inbox", rev, "--mark-read", "--json"]))] == ["ready for review"]
    assert _j(cli(["msg", "inbox", rev, "--json"])) == []
    assert len(_j(cli(["msg", "inbox", rev, "--all", "--json"]))) == 1
    assert cli(["msg", "send", "--from", imp, "--to", imp, "hello"])[0] == 2
    _j(cli(["msg", "escalate", "--from", imp, "--task", task, "please decide", "--json"]))
    assert _j(cli(["dashboard", "--json"]))["open_escalations"] == 1
    assert _j(cli(["claim", "take", imp, "src/api", "--json"]))["claimed"] == ["src/api"]
    code, _, err = cli(["claim", "take", rev, "src/api/limits.py", "--json"])
    assert code == 3 and "path_claimed" in err
    assert _j(cli(["claim", "list", "--json"]))[0]["instance_id"] == imp
    assert _j(cli(["claim", "release", imp, "--json"]))["released"] == ["src/api"]


def test_workflows_health_policy_and_data(cli, ready, tmp_path, owner_tty):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"tasks": [{"key": "a", "title": "first"},
                                          {"key": "b", "title": "second", "depends_on": ["a"]}]}))
    assert _j(cli(["workflow", "save", "two-step", "--file", str(plan), "--json"]))["version"] == 1
    assert cli(["workflow", "save", "two-step", "--file", str(tmp_path / "missing.json")])[0] == 2
    assert _j(cli(["workflow", "list", "--json"]))[0]["name"] == "two-step"
    assert len(_j(cli(["workflow", "show", "two-step", "--json"]))["body"]["tasks"]) == 2
    obj = _j(cli(["boss", "start", "reuse it", "--accept", "tests pass", "--json"]))["id"]
    assert set(_j(cli(["workflow", "apply", obj, "two-step", "--json"]))["created"]) == {"a", "b"}
    code, _, err = cli(["workflow", "from-objective", obj, "again", "--json"])
    assert code == 3 and "not_delivered" in err

    task = _j(cli(["task", "add", "watched", "--json"]))["id"]
    worker = _admit(cli, task, "implementer")
    _j(cli(["agent", "transition", worker, "RUNNING", "--json"]))
    assert _j(cli(["health", "heartbeat", worker, "--json"]))["instance_id"] == worker
    assert _j(cli(["health", "stale", "--json"])) == []
    assert _j(cli(["health", "reap", "--json"]))["reaped"] == []

    before = _j(cli(["policy", "show", "--json"]))["version"]
    eff = _j(cli(["policy", "project-limit", "max_concurrent", "1", "--json"]))["effective"]
    assert eff["max_concurrent"] == 1
    _j(cli(["policy", "project-limit", "max_concurrent", "3", "--json"]))  # loosening: the owner confirms
    assert _j(cli(["policy", "show", "--json"]))["version"] == before + 2
    assert _j(cli(["policy", "history", "--json"]))[-1]["change"]["owner_confirmed"] is True

    assert _j(cli(["retention", "plan", "--json"]))["would_remove"]["messages"] == 0
    assert cli(["retention", "plan", "--days", "1"])[0] == 2
    assert _j(cli(["retention", "apply", "--days", "30", "--json"]))["removed"] == {
        "messages": 0, "bench_runs": 0, "memory": 0, "claims": 0}


def test_bench_intel_views_and_generators(cli, ready, tmp_path):
    runs = _j(cli(["bench", "run", "--n", "5", "--json"]))
    assert len(runs) == 5 and _j(cli(["bench", "history", "--json"]))[0]["runs"] == 1
    assert len(_j(cli(["bench", "run", "--n", "5", "--no-record", "--json"]))) == 5
    assert _j(cli(["bench", "history", "--name", "admit_release", "--json"]))[0]["runs"] == 1
    task = _j(cli(["task", "add", "build", "--cap", "implementation", "--json"]))["id"]
    assert _j(cli(["intel", "options", task, "--json"]))["verdict"] == "insufficient_evidence"
    assert _j(cli(["intel", "route", task, "--json"]))["availability"].startswith("unknown")
    assert _j(cli(["intel", "context", task, "--record", "--json"]))["task_id"] == task
    assert _j(cli(["intel", "managers", "--json"]))["leads"] == []
    assert _j(cli(["intel", "calibration", "--json"]))["flagged"] == []
    assert _j(cli(["intel", "memory-quality", "--json"]))["records"] == 0
    assert _j(cli(["intel", "reuse", "--json"]))["reuse_rate"] is None
    assert len(_j(cli(["observe", "timeline", "--days", "2", "--json"]))["days"]) == 2
    assert _j(cli(["observe", "spans", "--json"])) == []
    written = _j(cli(["gen", "schemas", "--out", str(tmp_path / "s"), "--json"]))["written"]
    assert "plan.schema.json" in written and (tmp_path / "s" / "task.schema.json").exists()
    _j(cli(["gen", "docs", "--out", str(tmp_path / "CLI.md"), "--json"]))
    assert "agentos msg send" in (tmp_path / "CLI.md").read_text(encoding="utf-8")


def test_every_mcp_tool_answers(cli, ready):
    task = _j(cli(["task", "add", "build", "--json"]))["id"]
    _j(cli(["memory", "add", "project", "the parser accepts tabs", "--json"]))
    calls = {"agentos_status": {}, "agentos_dashboard": {}, "agentos_policy": {}, "agentos_governance_check": {},
             "agentos_route": {"task": task}, "agentos_memory_search": {"query": "parser"}}
    calls |= {f"view:{v}": {"view": v} for v in mcp_server.VIEWS}
    for name, args in calls.items():
        tool = "agentos_observe" if name.startswith("view:") else name
        r = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                               "params": {"name": tool, "arguments": args}})["result"]
        assert r["isError"] is False, (name, r["content"][0]["text"])
    empty = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                               "params": {"name": "agentos_memory_search", "arguments": {"query": " "}}})
    assert empty["result"]["isError"] is True
    assert mcp_server.handle({"jsonrpc": "2.0", "id": 3, "method": "ping"})["result"] == {}


def test_the_breaker_command_tightens_freely_and_asks_the_owner_to_loosen(cli, ready, owner_tty):
    assert _j(cli(["health", "breaker", "--json"])) == {"window": 3, "floor": 30.0}
    assert _j(cli(["health", "breaker", "--floor", "45", "--json"]))["new"]["floor"] == 45.0
    before = _j(cli(["policy", "show", "--json"]))["version"]
    assert _j(cli(["health", "breaker", "--window", "5", "--json"]))["new"]["window"] == 5  # owner confirms
    hist = _j(cli(["policy", "history", "--json"]))
    assert _j(cli(["policy", "show", "--json"]))["version"] == before + 1
    assert hist[-1]["kind"] == "health.breaker_set" and hist[-1]["change"]["owner_confirmed"] is True
    assert cli(["health", "breaker", "--window", "0"])[0] == 2


def test_the_breaker_command_refuses_to_loosen_without_the_owner(cli, ready):
    code, _, err = cli(["health", "breaker", "--floor", "10", "--json"])
    assert code == 3 and "owner" in err.lower()
    assert _j(cli(["health", "breaker", "--json"]))["floor"] == 30.0


def test_mcp_serve_does_not_migrate_the_ledger(cli, ready, home, monkeypatch):
    import io

    from agentos import db

    conn = db.connect()
    conn.execute("DELETE FROM schema_migrations WHERE version=?", (db.SCHEMA_VERSION,))
    conn.close()
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "agentos_status"}}) + "\n"))
    code, out, _ = cli(["mcp", "serve"])
    assert code == 0 and json.loads(out.splitlines()[0])["result"]["isError"] is True
    conn = db.connect()
    assert db.current_version(conn) == db.SCHEMA_VERSION - 1
    conn.close()
