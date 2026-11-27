"""A Model Context Protocol server over stdio: `agentos mcp serve`.

It speaks JSON-RPC 2.0, one message per line, and offers read-only tools: status, the dashboard, any
`observe` view, memory search, routing advice, the policy snapshot and the governance self-check. Nothing
that admits a worker, records a grade or changes a limit is offered here: those stay CLI commands, so the
host's hooks and the owner's confirmations still gate them. Standard library only."""

import json
import sys
from pathlib import Path

from agentos import __version__, db, intel, memory, observe, paths, policy_log, projects, tasks

PROTOCOL = "2025-06-18"
SUPPORTED = ("2025-06-18", "2025-03-26", "2024-11-05")  # offered back only when asked for
VIEWS = ("agents", "tree", "progress", "recruitment", "terminations", "performance", "resources",
         "experiments", "changes", "incidents", "controls", "timeline", "spans")
_PROJECT = {"project": {"type": "string", "description": "project id or repository path (default: server cwd)"}}

TOOLS = [
    {"name": "agentos_status", "description": "Emergency stop, active projects, task and agent counts.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "agentos_dashboard", "description": "One-screen summary of a project: controls, workers, "
     "progress, incidents, changes.", "inputSchema": {"type": "object", "properties": _PROJECT}},
    {"name": "agentos_observe", "description": "One read-only view of a project.",
     "inputSchema": {"type": "object", "required": ["view"],
                     "properties": _PROJECT | {"view": {"type": "string", "enum": list(VIEWS)}}}},
    {"name": "agentos_memory_search", "description": "Search a project's memory (with provenance).",
     "inputSchema": {"type": "object", "required": ["query"],
                     "properties": _PROJECT | {"query": {"type": "string"}, "limit": {"type": "integer"}}}},
    {"name": "agentos_route", "description": "Model-tier advice for a task (advice only).",
     "inputSchema": {"type": "object", "required": ["task"],
                     "properties": _PROJECT | {"task": {"type": "string"}}}},
    {"name": "agentos_policy", "description": "The policy in force: version, hash and values.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "agentos_governance_check", "description": "Re-check the core invariants from the raw ledger.",
     "inputSchema": {"type": "object", "properties": {}}},
]


class ToolError(Exception):
    pass


def _project_id(conn, target: str | None) -> str:
    if target and target.startswith("prj_"):
        return projects.get_project(conn, target).id
    return projects.get_project(conn, projects.project_id_for(Path(target) if target else Path.cwd())).id


def _view(conn, pid: str, view: str):
    calls = {"agents": lambda: observe.active_agents(conn, pid), "tree": lambda: observe.hierarchy(conn, pid),
             "progress": lambda: observe.progress(conn, pid), "recruitment": lambda: observe.recruitment(conn, pid),
             "terminations": lambda: observe.terminations(conn, pid),
             "performance": lambda: observe.performance_records(conn), "resources": lambda: observe.resources(conn, pid),
             "experiments": lambda: observe.experiments(conn, pid), "changes": lambda: observe.changes(conn, pid),
             "incidents": lambda: observe.incidents(conn, pid), "controls": lambda: observe.controls(conn),
             "timeline": lambda: observe.timeline(conn, pid), "spans": lambda: observe.spans(conn, pid)}
    if view not in calls:
        raise ToolError(f"unknown view {view!r}; one of: {', '.join(VIEWS)}")
    return calls[view]()


def _open_read_only():
    """The ledger opened for reading only: a pending migration is refused rather than applied, and
    `query_only` makes SQLite itself refuse any write a tool might attempt."""
    if not paths.db_path().exists():
        raise ToolError("AgentOS is not initialized. Run: agentos init")
    conn = db.connect()
    have = db.current_version(conn)
    if have != db.SCHEMA_VERSION:
        conn.close()
        raise ToolError(f"the ledger is at schema v{have}, this AgentOS needs v{db.SCHEMA_VERSION}; "
                        "run `agentos backup`, then `agentos init` to migrate (this server never writes)")
    conn.execute("PRAGMA query_only=ON")
    return conn


def call_tool(name: str, args: dict):
    conn = _open_read_only()
    try:
        if name == "agentos_status":
            return {"emergency_stop": observe.governance.is_stopped(conn),
                    "active_projects": conn.execute("SELECT count(*) FROM projects WHERE active=1").fetchone()[0],
                    "tasks": dict(conn.execute("SELECT state, count(*) FROM tasks GROUP BY state").fetchall()),
                    "agents": dict(conn.execute("SELECT state, count(*) FROM agent_instances GROUP BY state").fetchall())}
        if name == "agentos_dashboard":
            return observe.dashboard(conn, _project_id(conn, args.get("project")))
        if name == "agentos_observe":
            return _view(conn, _project_id(conn, args.get("project")), str(args.get("view")))
        if name == "agentos_memory_search":
            query = str(args.get("query") or "").strip()
            if not query:
                raise ToolError("query is required")
            found = memory.search(conn, _project_id(conn, args.get("project")), query,
                                  limit=max(1, min(int(args.get("limit") or 10), 50)))
            return [r.model_dump(mode="json") for r in found]
        if name == "agentos_route":
            task = tasks.get_task(conn, str(args.get("task") or ""))
            if task.project_id != _project_id(conn, args.get("project")):
                raise ToolError(f"task {task.id} belongs to another project (cross_project)")
            return intel.route(conn, task.id)
        if name == "agentos_policy":
            return policy_log.snapshot(conn)
        if name == "agentos_governance_check":
            return intel.governance_check(conn)
        raise ToolError(f"unknown tool {name!r}")
    finally:
        conn.close()


def handle(msg: dict) -> dict | None:
    """One JSON-RPC message in, one response out (None for a notification)."""
    mid, method = msg.get("id"), msg.get("method")
    if msg.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32600, "message": "invalid request"}}
    if mid is None:  # a notification, such as notifications/initialized
        return None
    if method == "initialize":
        asked = (msg.get("params") or {}).get("protocolVersion")
        result = {"protocolVersion": asked if asked in SUPPORTED else PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
                  "serverInfo": {"name": "agentos", "version": __version__},
                  "instructions": "Read-only AgentOS ledger views. Admission, grading and limits stay CLI commands."}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = msg.get("params") or {}
        try:
            data = call_tool(str(params.get("name")), params.get("arguments") or {})
            result = {"content": [{"type": "text", "text": json.dumps(data, default=str)}], "isError": False}
        except Exception as exc:  # noqa: BLE001 - every failure goes back to the client as a tool error
            result = {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(stdin=None, stdout=None) -> int:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            reply = handle(msg) if isinstance(msg, dict) else {
                "jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
    return 0
