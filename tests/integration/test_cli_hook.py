"""`agentos hook run HOST` is what the host runtime executes: hook JSON on stdin, hook JSON on stdout."""

import io
import json

import pytest


@pytest.fixture
def stdin(monkeypatch):
    def feed(obj):
        text = obj if isinstance(obj, str) else json.dumps(obj)
        monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(text.encode("utf-8")), encoding="utf-8"))

    return feed


def _spawn(cwd, tool="spawn_agent"):
    return {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": str(cwd), "tool_name": tool,
            "tool_use_id": "c1", "tool_input": {"message": "go"}}


@pytest.fixture
def ready(cli, home, repo, monkeypatch):
    monkeypatch.chdir(repo)
    for argv in (["init"], ["template", "seed"], ["project", "activate", str(repo)]):
        assert cli(argv)[0] == 0
    return repo


def test_no_agentos_state_means_no_opinion(cli, home, repo, stdin):
    stdin(_spawn(repo))
    code, out, _ = cli(["hook", "run", "codex"])
    assert (code, out) == (0, "")


def test_spawn_without_admission_prints_a_deny(cli, ready, stdin):
    stdin(_spawn(ready))
    code, out, _ = cli(["hook", "run", "codex"])
    assert code == 0
    spec = json.loads(out)["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse" and spec["permissionDecision"] == "deny"


def test_admitted_spawn_prints_nothing_and_binds(cli, ready, stdin):
    code, out, _ = cli(["task", "add", "work", "--json"])
    task_id = json.loads(out)["id"]
    code, out, err = cli(["agent", "admit", "--task", task_id, "--template", "researcher", "--host", "codex",
                          "--json"])
    assert code == 0, err
    iid = json.loads(out)["instance_id"]
    stdin(_spawn(ready))
    assert cli(["hook", "run", "codex"])[:2] == (0, "")
    code, out, _ = cli(["hook", "bindings", "--json"])
    assert [b["instance_id"] for b in json.loads(out)] == [iid]


def test_hook_failure_refuses_spawn_but_not_other_tools(cli, ready, stdin, monkeypatch):
    from agentos import runtime

    def boom(*a, **k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(runtime, "handle", boom)
    stdin(_spawn(ready))
    code, out, err = cli(["hook", "run", "codex"])
    assert code == 0 and "disk on fire" in json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
    stdin(_spawn(ready, tool="Bash"))
    code, out, err = cli(["hook", "run", "codex"])
    assert (code, out) == (0, "") and "disk on fire" in err


def test_garbage_input_is_reported_not_fatal(cli, ready, stdin):
    stdin("not json")
    code, out, err = cli(["hook", "run", "codex"])
    assert (code, out) == (0, "") and "not valid hook JSON" in err


def test_unknown_host_is_a_usage_error(cli, ready, stdin):
    stdin(_spawn(ready))
    assert cli(["hook", "run", "nope"])[0] == 2


@pytest.mark.parametrize("host,matcher", [("codex", "^(Agent|spawn_agent)$"), ("cc", "^(Agent|Task)$")])
def test_hook_config(cli, host, matcher):
    code, out, _ = cli(["hook", "config", host])
    cfg = json.loads(out)["hooks"]
    assert code == 0 and set(cfg) == {"PreToolUse", "SubagentStart", "SubagentStop"}
    assert cfg["PreToolUse"][0]["matcher"] == matcher
    assert cfg["SubagentStop"][0]["hooks"][0]["command"] == f"agentos hook run {host}"


def test_hook_config_guarding_every_tool_uses_one_matcher(cli):
    cfg = json.loads(cli(["hook", "config", "codex", "--guard-tools"])[1])["hooks"]
    assert [e["matcher"] for e in cfg["PreToolUse"]] == ["*"]


def test_real_process_with_a_non_ascii_path(tmp_path):
    """The runtime starts a separate process and pipes UTF-8 bytes; check that path end to end."""
    import os
    import subprocess
    import sys

    from tests.conftest import make_repo

    exe = [sys.executable, "-c", "import sys; from agentos.cli import main; sys.exit(main())"]
    repo = make_repo(tmp_path / "Répo 中")
    env = dict(os.environ, AGENTOS_HOME=str(tmp_path / "home"), AGENTOS_ACTOR="test")
    for argv in (["init"], ["template", "seed"], ["project", "activate", str(repo)]):
        assert subprocess.run([*exe, *argv], env=env, capture_output=True, check=False).returncode == 0
    event = json.dumps(_spawn(repo), ensure_ascii=False).encode("utf-8")
    r = subprocess.run([*exe, "hook", "run", "codex"], input=event, env=env, capture_output=True,
                       timeout=120, check=False)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
