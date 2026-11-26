"""Runtime hooks: the host runtime asks AgentOS before a subagent is spawned (PreToolUse), reports
when one starts (SubagentStart) and when it stops (SubagentStop)."""

import json

import pytest

from agentos import governance, lifecycle, runtime
from tests.conftest import add_instance


def _spawn(cwd, tool="spawn_agent", tool_input=None, session="s1", call="call_1", **extra):
    return {"hook_event_name": "PreToolUse", "session_id": session, "cwd": str(cwd), "turn_id": "t1",
            "tool_name": tool, "tool_use_id": call, "tool_input": tool_input or {"message": "go"}, **extra}


def _start(cwd, agent_id="agt_1", session="s1"):
    return {"hook_event_name": "SubagentStart", "session_id": session, "cwd": str(cwd), "turn_id": "t1",
            "agent_id": agent_id, "agent_type": "worker"}


def _stop(cwd, agent_id="agt_1", session="s1"):
    return {"hook_event_name": "SubagentStop", "session_id": session, "cwd": str(cwd), "turn_id": "t1",
            "agent_id": agent_id, "agent_type": "worker", "stop_hook_active": False}


def _denied(result):
    out = result.output or {}
    spec = out.get("hookSpecificOutput", {})
    return spec.get("permissionDecision") == "deny"


def _ticket(conn, project, task, host="codex"):
    iid = add_instance(conn, project, task, template="implementer", state="ASSIGNED")
    conn.execute("UPDATE agent_instances SET host=? WHERE id=?", (host, iid))
    return iid


def _kinds(conn):
    return [r[0] for r in conn.execute("SELECT kind FROM events ORDER BY seq")]


def test_spawn_without_a_ticket_is_denied(seeded, project, repo):
    r = runtime.handle(seeded, "codex", _spawn(repo))
    assert _denied(r)
    assert "agentos agent admit" in r.output["hookSpecificOutput"]["permissionDecisionReason"]
    assert r.reasons == ["no_admitted_ticket"]
    assert "runtime.spawn_denied" in _kinds(seeded)


def test_spawn_with_a_ticket_is_allowed_once(seeded, project, repo, task):
    iid = _ticket(seeded, project, task)
    first = runtime.handle(seeded, "codex", _spawn(repo))
    assert first.output is None and first.instance_id == iid
    assert runtime.binding(seeded, iid)["tool_use_id"] == "call_1"
    second = runtime.handle(seeded, "codex", _spawn(repo, call="call_2"))
    assert _denied(second) and second.reasons == ["no_admitted_ticket"]


def test_the_same_spawn_call_checked_twice_claims_one_ticket(seeded, project, repo, task):
    iid = _ticket(seeded, project, task)
    other = _ticket(seeded, project, task)
    assert runtime.handle(seeded, "codex", _spawn(repo)).instance_id == iid
    again = runtime.handle(seeded, "codex", _spawn(repo))
    assert again.output is None and again.instance_id == iid
    assert runtime.binding(seeded, other) is None


def test_named_ticket_is_claimed_and_unavailable_names_are_denied(seeded, project, repo, task):
    a = _ticket(seeded, project, task)
    b = _ticket(seeded, project, task)
    r = runtime.handle(seeded, "codex", _spawn(repo, tool_input={"message": f"agentos instance {b}: do it"}))
    assert r.instance_id == b
    assert runtime.binding(seeded, a) is None
    again = runtime.handle(seeded, "codex", _spawn(repo, tool_input={"message": f"use {b}"}, call="call_2"))
    assert _denied(again) and again.reasons == ["ticket_not_available"]


def test_ticket_from_another_project_cannot_be_named(seeded, project, repo, task, tmp_path):
    from agentos import projects, tasks
    from tests.conftest import make_repo

    other_repo = make_repo(tmp_path / "other")
    other = projects.activate(seeded, other_repo, actor="test")
    foreign = _ticket(seeded, other, tasks.add_task(seeded, other.id, "t", actor="test"))
    r = runtime.handle(seeded, "codex", _spawn(repo, tool_input={"message": foreign}))
    assert _denied(r) and r.reasons == ["ticket_not_available"]


def test_host_other_tickets_are_accepted_and_relabelled(seeded, project, repo, task):
    iid = _ticket(seeded, project, task, host="other")
    assert runtime.handle(seeded, "codex", _spawn(repo)).instance_id == iid
    assert lifecycle.get_instance(seeded, iid).host == "codex"


def test_tickets_of_another_host_are_not_used(seeded, project, repo, task):
    _ticket(seeded, project, task, host="cc")
    assert _denied(runtime.handle(seeded, "codex", _spawn(repo)))


def test_emergency_stop_denies_spawn_even_with_a_ticket(seeded, project, repo, task):
    _ticket(seeded, project, task)
    governance.emergency_stop(seeded, "test", "drill")
    r = runtime.handle(seeded, "codex", _spawn(repo))
    assert _denied(r) and r.reasons == ["emergency_stop"]


def test_ungoverned_directories_are_left_alone(seeded, tmp_path):
    from tests.conftest import make_repo

    loose = make_repo(tmp_path / "not-activated")
    before = _kinds(seeded)
    r = runtime.handle(seeded, "codex", _spawn(loose))
    assert r.output is None and r.reasons == []
    assert _kinds(seeded) == before


def test_other_tools_are_not_gated_for_the_main_agent(seeded, project, repo):
    r = runtime.handle(seeded, "codex", _spawn(repo, tool="Bash", tool_input={"command": "ls"}))
    assert r.output is None


def test_subagent_start_binds_and_starts_running(seeded, project, repo, task):
    iid = _ticket(seeded, project, task)
    runtime.handle(seeded, "codex", _spawn(repo))
    r = runtime.handle(seeded, "codex", _start(repo, "agt_9"))
    assert r.instance_id == iid
    assert runtime.binding(seeded, iid)["native_agent_id"] == "agt_9"
    assert lifecycle.get_instance(seeded, iid).state == lifecycle.AgentState.RUNNING
    again = runtime.handle(seeded, "codex", _start(repo, "agt_9"))
    assert again.instance_id == iid
    assert lifecycle.get_instance(seeded, iid).state == lifecycle.AgentState.RUNNING


def test_unadmitted_subagent_is_recorded_and_told(seeded, project, repo):
    r = runtime.handle(seeded, "codex", _start(repo, "agt_rogue"))
    assert r.instance_id is None
    assert "not admitted" in r.output["hookSpecificOutput"]["additionalContext"]
    row = seeded.execute("SELECT payload FROM events WHERE kind='runtime.unadmitted_subagent'").fetchone()
    assert json.loads(row[0])["agent_id"] == "agt_rogue"


def test_subagent_stop_confirms_a_requested_cancel(seeded, project, repo, task):
    iid = _ticket(seeded, project, task)
    runtime.handle(seeded, "codex", _spawn(repo))
    runtime.handle(seeded, "codex", _start(repo, "agt_2"))
    lifecycle.transition(seeded, iid, lifecycle.AgentState.CANCELLED, "owner")
    slots = lifecycle.slot_count(seeded)
    r = runtime.handle(seeded, "codex", _stop(repo, "agt_2"))
    assert r.output is None
    inst = lifecycle.get_instance(seeded, iid)
    assert inst.state == lifecycle.AgentState.TERMINATED and inst.termination_confirmed is True
    assert lifecycle.slot_count(seeded) == slots - 1
    assert runtime.binding(seeded, iid)["stopped_at"]


def test_subagent_stop_of_running_work_only_records_it(seeded, project, repo, task):
    iid = _ticket(seeded, project, task)
    runtime.handle(seeded, "codex", _spawn(repo))
    runtime.handle(seeded, "codex", _start(repo, "agt_3"))
    runtime.handle(seeded, "codex", _stop(repo, "agt_3"))
    assert lifecycle.get_instance(seeded, iid).state == lifecycle.AgentState.RUNNING
    assert runtime.binding(seeded, iid)["stopped_at"]
    assert "runtime.subagent_stopped" in _kinds(seeded)


def test_unknown_subagent_stop_is_harmless(seeded, project, repo):
    assert runtime.handle(seeded, "codex", _stop(repo, "agt_never")).output is None


def test_tool_calls_of_a_cancelled_subagent_are_denied(seeded, project, repo, task):
    iid = _ticket(seeded, project, task)
    runtime.handle(seeded, "codex", _spawn(repo))
    runtime.handle(seeded, "codex", _start(repo, "agt_4"))
    call = _spawn(repo, tool="Bash", tool_input={"command": "rm -rf build"}, agent_id="agt_4")
    assert runtime.handle(seeded, "codex", call).output is None
    lifecycle.transition(seeded, iid, lifecycle.AgentState.CANCELLED, "owner")
    r = runtime.handle(seeded, "codex", call)
    assert _denied(r) and r.reasons == ["instance_not_active"]


def test_emergency_stop_denies_tool_calls_of_bound_subagents(seeded, project, repo, task):
    _ticket(seeded, project, task)
    runtime.handle(seeded, "codex", _spawn(repo))
    runtime.handle(seeded, "codex", _start(repo, "agt_5"))
    governance.emergency_stop(seeded, "test", "drill")
    r = runtime.handle(seeded, "codex", _spawn(repo, tool="Bash", agent_id="agt_5"))
    assert _denied(r) and r.reasons == ["emergency_stop"]


@pytest.mark.parametrize("tool", ["Task", "Agent"])
def test_cc_host_spawn_tools(seeded, project, repo, tool):
    assert _denied(runtime.handle(seeded, "cc", _spawn(repo, tool=tool)))


def test_unknown_host_is_a_usage_error(seeded, repo):
    from agentos.errors import UsageError

    with pytest.raises(UsageError):
        runtime.handle(seeded, "nope", _spawn(repo))


def test_events_without_a_cwd_are_ignored(seeded, project):
    r = runtime.handle(seeded, "codex", {"hook_event_name": "PreToolUse", "tool_name": "spawn_agent"})
    assert r.output is None
