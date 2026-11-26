"""Runtime adapters: the host runtime calls AgentOS from its own hooks, so admission is enforced at
the point a subagent is spawned instead of relying on the host model to ask first.

Event flow (hook payload fields as the host runtime sends them on stdin):

- PreToolUse for the host's spawn tool: allowed only if an admitted ticket (an ASSIGNED instance of
  this project with no runtime binding yet) is waiting. The ticket is claimed atomically. A spawn
  message may name a ticket (`ag_...`); otherwise the oldest is used.
- PreToolUse for any other tool: if the payload identifies a bound subagent whose instance is no
  longer active (cancelled, terminated, ...) or the emergency stop is on, the call is denied.
- SubagentStart: the native agent id is bound to the claimed ticket and the instance moves to
  RUNNING. A subagent with no ticket cannot be blocked here (the runtime does not allow it); it is
  recorded as `runtime.unadmitted_subagent` and told so.
- SubagentStop: the binding is closed; a cancel or termination requested earlier is confirmed by the
  runtime itself, which frees the concurrency slot.

Directories that are not an activated project are left alone.
"""

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from agentos import audit, governance, lifecycle, projects
from agentos.db import write_tx
from agentos.errors import NotFound, UsageError
from agentos.lifecycle import ACTIVE_STATES, AgentState
from agentos.util import now_iso


@dataclass(frozen=True)
class HostProfile:
    name: str
    spawn_tools: frozenset[str]


HOSTS: dict[str, HostProfile] = {
    "codex": HostProfile("codex", frozenset({"spawn_agent", "Agent"})),
    "cc": HostProfile("cc", frozenset({"Task", "Agent"})),
}

TICKET_RE = re.compile(r"\bag_[0-9a-f]{12}\b")


@dataclass
class HookResult:
    output: dict | None = None
    reasons: list[str] = field(default_factory=list)
    instance_id: str | None = None


def profile(host: str) -> HostProfile:
    try:
        return HOSTS[host]
    except KeyError:
        raise UsageError(f"unknown runtime host: {host} (known: {', '.join(sorted(HOSTS))})") from None


def binding(conn: sqlite3.Connection, instance_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM runtime_bindings WHERE instance_id=?", (instance_id,)).fetchone()
    return dict(row) if row else None


def list_bindings(conn: sqlite3.Connection, project_id: str | None = None) -> list[dict]:
    sql = ("SELECT b.*, i.state, i.project_id, i.task_id FROM runtime_bindings b"
           " JOIN agent_instances i ON i.id=b.instance_id")
    params: list = []
    if project_id:
        sql += " WHERE i.project_id=?"
        params.append(project_id)
    return [dict(r) for r in conn.execute(sql + " ORDER BY b.claimed_at, b.rowid", params)]


def _project(conn, cwd):
    if not cwd:
        return None
    try:
        p = projects.get_project(conn, projects.project_id_for(Path(cwd)))
    except NotFound:
        return None
    return p if p.active else None


def _by_native(conn, host: str, agent_id: str):
    return conn.execute("SELECT * FROM runtime_bindings WHERE host=? AND native_agent_id=?",
                        (host, agent_id)).fetchone()


def _deny(message: str, reasons: list[str], instance_id: str | None = None) -> HookResult:
    return HookResult({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                              "permissionDecisionReason": message}}, reasons, instance_id)


def _context(event_name: str, text: str, reasons: list[str], instance_id: str | None = None) -> HookResult:
    return HookResult({"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text}},
                      reasons, instance_id)


def _open_tickets(conn, project_id: str, host: str) -> list[str]:
    rows = conn.execute(
        "SELECT i.id FROM agent_instances i LEFT JOIN runtime_bindings b ON b.instance_id=i.id"
        " WHERE i.project_id=? AND i.state=? AND i.host IN (?, 'other') AND b.instance_id IS NULL"
        " ORDER BY i.created_at, i.rowid", (project_id, AgentState.ASSIGNED.value, host))
    return [r[0] for r in rows]


def _gate_spawn(conn, prof: HostProfile, event: dict, actor: str) -> HookResult:
    proj = _project(conn, event.get("cwd"))
    if proj is None:
        return HookResult()
    named = TICKET_RE.findall(json.dumps(event.get("tool_input") or {}))
    with write_tx(conn):
        if event.get("tool_use_id"):  # the same call checked twice (e.g. plugin and user hooks): one claim
            same = conn.execute("SELECT instance_id FROM runtime_bindings WHERE host=? AND tool_use_id=?"
                                " AND session_id IS ?", (prof.name, event["tool_use_id"],
                                                         event.get("session_id"))).fetchone()
            if same:
                return HookResult(None, [], same[0])
        pick, reasons = None, []
        if governance.is_stopped(conn):
            reasons = ["emergency_stop"]
            message = "AgentOS emergency stop is active: no worker may start until the owner lifts it."
        else:
            tickets = _open_tickets(conn, proj.id, prof.name)
            if named:
                pick = next((t for t in named if t in tickets), None)
                reasons = [] if pick else ["ticket_not_available"]
                message = ("AgentOS: the instance named in the spawn message is not admitted and waiting"
                           f" in this project ({', '.join(named)}). Check `agentos agent list`.")
            else:
                pick = tickets[0] if tickets else None
                reasons = [] if pick else ["no_admitted_ticket"]
                message = ("AgentOS: no admitted worker is waiting for this spawn. Run `agentos agent admit"
                           f" --task <id> --template <id> --host {prof.name}` first and spawn only if it is"
                           " admitted; put the instance id in the spawn message to pick one.")
        if pick:
            conn.execute(
                "INSERT INTO runtime_bindings(instance_id, host, session_id, tool_use_id, claimed_at)"
                " VALUES (?,?,?,?,?)",
                (pick, prof.name, event.get("session_id"), event.get("tool_use_id"), now_iso()))
            conn.execute("UPDATE agent_instances SET host=? WHERE id=? AND host='other'", (prof.name, pick))
            audit.append_event(conn, "runtime.spawn_allowed", actor,
                               {"instance_id": pick, "tool": event.get("tool_name"),
                                "session_id": event.get("session_id")}, proj.id)
            return HookResult(None, [], pick)
        audit.append_event(conn, "runtime.spawn_denied", actor,
                           {"tool": event.get("tool_name"), "reasons": reasons, "named": named,
                            "session_id": event.get("session_id")}, proj.id)
    return _deny(message, reasons)


def _guard_tool(conn, prof: HostProfile, event: dict, actor: str) -> HookResult:
    agent_id = event.get("agent_id")
    if not agent_id:
        return HookResult()
    row = _by_native(conn, prof.name, agent_id)
    if not row:
        return HookResult()
    inst = lifecycle.get_instance(conn, row["instance_id"])
    if governance.is_stopped(conn):
        reasons, message = ["emergency_stop"], "AgentOS emergency stop is active: stop work now."
    elif inst.state not in ACTIVE_STATES:
        reasons = ["instance_not_active"]
        message = f"AgentOS: this worker ({inst.id}) is {inst.display_state()}; stop and report to the parent agent."
    else:
        return HookResult(None, [], inst.id)
    with write_tx(conn):
        audit.append_event(conn, "runtime.tool_denied", actor,
                           {"instance_id": inst.id, "tool": event.get("tool_name"), "reasons": reasons},
                           inst.project_id)
    return _deny(message, reasons, inst.id)


def _subagent_start(conn, prof: HostProfile, event: dict, actor: str) -> HookResult:
    agent_id = event.get("agent_id")
    if not agent_id:
        return HookResult()
    with write_tx(conn):
        row = _by_native(conn, prof.name, agent_id)
        if row:
            return HookResult(None, [], row["instance_id"])
        proj = _project(conn, event.get("cwd"))
        if proj is None:
            return HookResult()
        claim = conn.execute(
            "SELECT b.instance_id FROM runtime_bindings b JOIN agent_instances i ON i.id=b.instance_id"
            " WHERE b.host=? AND b.native_agent_id IS NULL AND b.stopped_at IS NULL AND i.project_id=?"
            " ORDER BY (b.session_id IS ?) DESC, b.claimed_at, b.rowid LIMIT 1",
            (prof.name, proj.id, event.get("session_id"))).fetchone()
        if not claim:
            audit.append_event(conn, "runtime.unadmitted_subagent", actor,
                               {"agent_id": agent_id, "agent_type": event.get("agent_type"),
                                "session_id": event.get("session_id")}, proj.id)
            return _context("SubagentStart",
                            "AgentOS: this subagent was not admitted (no `agentos agent admit` ticket). Do no"
                            " work; tell the parent agent to admit a worker first.", ["unadmitted_subagent"])
        iid = claim[0]
        conn.execute("UPDATE runtime_bindings SET native_agent_id=?, started_at=? WHERE instance_id=?",
                     (agent_id, now_iso(), iid))
        inst = lifecycle.get_instance(conn, iid)
        if inst.state == AgentState.ASSIGNED:
            inst = lifecycle.transition(conn, iid, AgentState.RUNNING, actor, reason="runtime subagent started")
        audit.append_event(conn, "runtime.subagent_started", actor,
                           {"instance_id": iid, "agent_id": agent_id, "agent_type": event.get("agent_type")},
                           proj.id)
    if inst.state not in ACTIVE_STATES:
        return _context("SubagentStart", f"AgentOS: your instance {iid} is {inst.display_state()}; do no work.",
                        ["instance_not_active"], iid)
    return _context("SubagentStart", f"AgentOS instance id for this worker: {iid}.", [], iid)


def _subagent_stop(conn, prof: HostProfile, event: dict, actor: str) -> HookResult:
    agent_id = event.get("agent_id")
    if not agent_id:
        return HookResult()
    with write_tx(conn):
        row = _by_native(conn, prof.name, agent_id)
        if not row:
            return HookResult()
        iid = row["instance_id"]
        conn.execute("UPDATE runtime_bindings SET stopped_at=coalesce(stopped_at, ?) WHERE instance_id=?",
                     (now_iso(), iid))
        inst = lifecycle.get_instance(conn, iid)
        confirmed = lifecycle._stop_unconfirmed(inst)
        if confirmed:
            inst = lifecycle.confirm_stopped(conn, iid, actor)
        audit.append_event(conn, "runtime.subagent_stopped", actor,
                           {"instance_id": iid, "agent_id": agent_id, "ledger_state": inst.display_state(),
                            "stop_confirmed": confirmed}, inst.project_id)
    return HookResult(None, [], iid)


def handle(conn: sqlite3.Connection, host: str, event: dict, actor: str | None = None) -> HookResult:
    prof = profile(host)
    actor = actor or f"runtime:{prof.name}"
    name = event.get("hook_event_name")
    if name == "PreToolUse":
        if (event.get("tool_name") or "") in prof.spawn_tools:
            return _gate_spawn(conn, prof, event, actor)
        return _guard_tool(conn, prof, event, actor)
    if name == "SubagentStart":
        return _subagent_start(conn, prof, event, actor)
    if name == "SubagentStop":
        return _subagent_stop(conn, prof, event, actor)
    return HookResult()


def hooks_config(host: str, guard_tools: bool = False, executable: str = "agentos") -> dict:
    """The hooks file a host runtime loads (`hooks/hooks.json` in a plugin, or the user's own).

    By default only the spawn tool is gated. `guard_tools` runs the hook for every tool call, so a
    cancelled subagent's calls can be denied; it costs one `agentos` start per tool call. A single
    PreToolUse entry is used either way, so the spawn gate never runs twice for one call."""
    prof = profile(host)
    command = {"type": "command", "command": f"{executable} hook run {prof.name}", "timeout": 30}
    matcher = "*" if guard_tools else "^(" + "|".join(sorted(prof.spawn_tools)) + ")$"
    return {"hooks": {
        "PreToolUse": [{"matcher": matcher, "hooks": [dict(command, statusMessage="AgentOS admission check")]}],
        "SubagentStart": [{"hooks": [dict(command)]}],
        "SubagentStop": [{"hooks": [dict(command)]}],
    }}


def failure_result(host: str, event: dict, error: str) -> HookResult:
    """What to answer when the hook itself fails: a spawn is refused (fail closed), anything else
    goes ahead, so a broken ledger never blocks ordinary tool calls."""
    prof = HOSTS.get(host)
    if (prof and event.get("hook_event_name") == "PreToolUse"
            and (event.get("tool_name") or "") in prof.spawn_tools):
        return _deny(f"AgentOS hook failed, so the spawn is refused: {error}", ["hook_error"])
    return HookResult(None, ["hook_error"])
