"""Reusable workflows: a task graph saved under a name and applied to a new objective.

A workflow is the plan format `agentos boss plan` accepts (tasks with keys, capabilities, acceptance,
risk, effort and dependencies), stored with a version and a hash. Saving the same body again returns the
existing version; a changed body gets the next version, and older versions stay usable. A workflow taken
from an objective is only accepted once that objective was delivered, so only proven plans are reused."""

import json
import re
import sqlite3

from agentos import audit, boss
from agentos.db import write_tx
from agentos.errors import NotFound, PolicyDenied, UsageError
from agentos.util import now_iso, sha256_json

NAME = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
FIELDS = ("key", "title", "objective", "capabilities", "acceptance", "risk", "department", "priority", "effort",
          "depends_on")


def _clean(plan) -> dict:
    items = plan.get("tasks") if isinstance(plan, dict) else None
    if not isinstance(items, list) or not items:
        raise UsageError("a workflow needs a non-empty 'tasks' list")
    out, keys = [], set()
    for i, raw in enumerate(items):
        if not isinstance(raw, dict) or not str(raw.get("key") or "").strip() or not str(raw.get("title") or "").strip():
            raise UsageError(f"workflow task {i} needs a key and a title")
        if raw.get("parent"):
            raise UsageError(f"workflow task {raw['key']}: a workflow cannot name a parent task of another objective")
        key = str(raw["key"]).strip()
        if key in keys:
            raise UsageError(f"duplicate task key: {key}")
        keys.add(key)
        out.append({k: raw[k] for k in FIELDS if k in raw and raw[k] is not None} | {"key": key})
    for item in out:
        for d in item.get("depends_on") or []:
            if d not in keys:
                raise UsageError(f"workflow task {item['key']}: dependency {d} is not a task of the workflow")
    boss._topo([{"key": i["key"], "depends_on": list(i.get("depends_on") or [])} for i in out])
    return {"tasks": out}


def save(conn: sqlite3.Connection, name: str, plan: dict, actor: str, source: str | None = None) -> dict:
    if not NAME.match(name or ""):
        raise UsageError("a workflow name is 2-41 lowercase letters, digits or hyphens, starting with a letter")
    body = _clean(plan)
    digest = sha256_json(body)
    with write_tx(conn):
        row = conn.execute("SELECT version, body_hash FROM workflows WHERE name=? ORDER BY version DESC LIMIT 1",
                           (name,)).fetchone()
        if row and row["body_hash"] == digest:
            return {"name": name, "version": row["version"], "created": False, "tasks": len(body["tasks"])}
        version = (row["version"] + 1) if row else 1
        conn.execute("INSERT INTO workflows(name, version, body, body_hash, source, created_at, actor)"
                     " VALUES (?,?,?,?,?,?,?)", (name, version, json.dumps(body), digest, source, now_iso(), actor))
        audit.append_event(conn, "workflow.saved", actor, {"name": name, "version": version, "hash": digest,
                                                            "source": source, "tasks": len(body["tasks"])})
    return {"name": name, "version": version, "created": True, "tasks": len(body["tasks"])}


def from_objective(conn: sqlite3.Connection, objective_id: str, name: str, actor: str) -> dict:
    """Save a delivered objective's task graph. Cancelled tasks are left out."""
    obj = boss.get_objective(conn, objective_id)
    if obj.state != "delivered":
        raise PolicyDenied(f"objective is {obj.state}; only a delivered objective's plan is reused",
                           reasons=["not_delivered"])
    rows = conn.execute("SELECT * FROM tasks WHERE objective_id=? AND state<>'cancelled' ORDER BY rowid",
                        (objective_id,)).fetchall()
    keys = {r["id"]: f"t{i + 1}" for i, r in enumerate(rows)}
    items = []
    for r in rows:
        deps = [keys[d] for (d,) in conn.execute("SELECT depends_on FROM task_deps WHERE task_id=?", (r["id"],))
                if d in keys]
        items.append({"key": keys[r["id"]], "title": r["title"], "objective": r["objective"],
                      "capabilities": json.loads(r["capabilities"]), "acceptance": json.loads(r["acceptance"]),
                      "risk": r["risk"], "department": r["department"], "priority": r["priority"],
                      "effort": r["effort"], "depends_on": deps})
    return save(conn, name, {"tasks": items}, actor, source=objective_id)


def get(conn: sqlite3.Connection, name: str, version: int | None = None) -> dict:
    sql, params = "SELECT * FROM workflows WHERE name=?", [name]
    if version is not None:
        sql, params = sql + " AND version=?", [name, version]
    row = conn.execute(sql + " ORDER BY version DESC LIMIT 1", params).fetchone()
    if not row:
        raise NotFound(f"no workflow {name}" + (f" version {version}" if version is not None else ""))
    return dict(row) | {"body": json.loads(row["body"])}


def list_all(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT name, max(version) AS latest, count(*) AS versions, max(created_at) AS updated_at"
        " FROM workflows GROUP BY name ORDER BY name")]


def apply(conn: sqlite3.Connection, objective_id: str, name: str, actor: str, version: int | None = None) -> dict:
    wf = get(conn, name, version)
    if sha256_json(wf["body"]) != wf["body_hash"]:
        raise PolicyDenied(f"workflow {name} v{wf['version']} does not match its hash", reasons=["tampered"])
    result = boss.apply_plan(conn, objective_id, wf["body"], actor)
    obj = boss.get_objective(conn, objective_id)
    with write_tx(conn):
        audit.append_event(conn, "workflow.applied", actor, {"name": name, "version": wf["version"],
                                                              "objective_id": objective_id}, obj.project_id)
    return result | {"workflow": name, "version": wf["version"]}
