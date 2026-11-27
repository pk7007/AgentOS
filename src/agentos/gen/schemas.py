"""JSON Schema files for the records AgentOS exchanges with hosts and other tools, generated from the same
pydantic models the code validates with, so the published schema and the enforced one cannot drift."""

import json
from pathlib import Path

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


def _models() -> dict:
    from agentos.admission import AdmitDecision, AdmitRequest
    from agentos.evidence import Evidence
    from agentos.governor import Limits
    from agentos.lifecycle import AgentInstance
    from agentos.memory import MemoryRecord
    from agentos.performance import Evaluation
    from agentos.tasks import Task
    from agentos.templates import AgentTemplate

    return {"agent-template": AgentTemplate, "agent-instance": AgentInstance, "admit-request": AdmitRequest,
            "admit-decision": AdmitDecision, "task": Task, "evaluation": Evaluation, "evidence": Evidence,
            "memory-record": MemoryRecord, "limits": Limits}


def _plan_schema() -> dict:
    item = {"type": "object", "required": ["key", "title"], "additionalProperties": False, "properties": {
        "key": {"type": "string", "minLength": 1}, "title": {"type": "string", "minLength": 1},
        "objective": {"type": "string"}, "capabilities": {"type": "array", "items": {"type": "string"}},
        "acceptance": {"type": "array", "items": {"type": "string"}},
        "risk": {"enum": ["low", "medium", "high", "critical"]}, "department": {"type": ["string", "null"]},
        "priority": {"type": "integer", "minimum": 0, "maximum": 100}, "effort": {"type": "integer", "minimum": 1},
        "parent": {"type": ["string", "null"]}, "depends_on": {"type": "array", "items": {"type": "string"}}}}
    return {"title": "Plan", "description": "A task graph for `agentos boss plan` and `agentos workflow save`.",
            "type": "object", "required": ["tasks"],
            "properties": {"tasks": {"type": "array", "minItems": 1, "items": item}}}


def expected() -> dict[str, str]:
    out = {}
    for name, model in _models().items():
        schema = {"$schema": SCHEMA_DIALECT, "$id": f"agentos/{name}.schema.json"} | model.model_json_schema()
        out[f"{name}.schema.json"] = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    plan = {"$schema": SCHEMA_DIALECT, "$id": "agentos/plan.schema.json"} | _plan_schema()
    out["plan.schema.json"] = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    return out


def generate(out: Path) -> list[str]:
    out.mkdir(parents=True, exist_ok=True)
    files = expected()
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8", newline="\n")
    for stale in out.glob("*.schema.json"):
        if stale.name not in files:
            stale.unlink()
    return sorted(files)
