from pathlib import Path

import pytest
from pydantic import ValidationError

from agentos import templates
from agentos.errors import PolicyDenied
from agentos.templates import AgentTemplate, TemplateStatus

ROOT = Path(__file__).resolve().parents[2]


def _tpl(**kw):
    base = dict(id="coder", version=1, name="Coder", role="implementer", department="engineering",
                description="writes code", capabilities=["python"], instructions="Write code.")
    base.update(kw)
    return AgentTemplate(**base)


def test_versioning(conn):
    templates.add_template(conn, _tpl(), actor="t")
    templates.add_template(conn, _tpl(instructions="Write better code."), actor="t")
    assert templates.get_template(conn, "coder").version == 2
    assert templates.get_template(conn, "coder", version=1).instructions == "Write code."
    assert len(templates.list_templates(conn)) == 1


def test_retire_requires_owner(conn):
    templates.add_template(conn, _tpl(), actor="t")
    with pytest.raises(PolicyDenied) as e:
        templates.set_status(conn, "coder", TemplateStatus.retired, actor="t", reason="bad", owner=None)
    assert "owner_required" in e.value.reasons


def test_quarantine_no_owner_but_release_needs_owner(conn):
    templates.add_template(conn, _tpl(), actor="t")
    t = templates.set_status(conn, "coder", TemplateStatus.quarantined, actor="t", reason="leak")
    assert t.status == TemplateStatus.quarantined
    with pytest.raises(PolicyDenied):
        templates.set_status(conn, "coder", TemplateStatus.active, actor="t", reason="ok")


def test_suspend_and_reinstate_without_owner(conn):
    templates.add_template(conn, _tpl(), actor="t")
    templates.set_status(conn, "coder", TemplateStatus.suspended, actor="t", reason="slow")
    t = templates.set_status(conn, "coder", TemplateStatus.active, actor="t", reason="better")
    assert t.status == TemplateStatus.active


def test_status_applies_to_all_versions(conn):
    templates.add_template(conn, _tpl(), actor="t")
    templates.add_template(conn, _tpl(instructions="v2"), actor="t")
    templates.set_status(conn, "coder", TemplateStatus.suspended, actor="t", reason="x")
    assert templates.get_template(conn, "coder", version=1).status == TemplateStatus.suspended


def test_bad_slug_rejected():
    with pytest.raises(ValidationError):
        _tpl(id="Bad Slug!")


def test_seed_definitions_load():
    defs = templates.load_definitions(ROOT / "definitions" / "agents")
    assert sorted(t.id for t in defs) == ["implementer", "lead", "planner", "recovery", "researcher", "reviewer"]
    by_id = {t.id: t for t in defs}
    assert by_id["lead"].can_delegate and by_id["reviewer"].read_only
