import pytest

from agentos import admission, governance, lifecycle, util
from agentos.admission import AdmitRequest
from agentos.errors import PolicyDenied
from agentos.governance import OwnerConfirmation
from agentos.lifecycle import AgentState


def test_non_tty_cannot_confirm():
    with pytest.raises(PolicyDenied) as e:
        governance.confirm_owner("x", isatty=lambda: False, prompt=lambda m: "I APPROVE x")
    assert "owner_confirmation_requires_terminal" in e.value.reasons


def test_wrong_phrase():
    with pytest.raises(PolicyDenied) as e:
        governance.confirm_owner("x", isatty=lambda: True, prompt=lambda m: "yes")
    assert "owner_phrase_mismatch" in e.value.reasons


def test_right_phrase():
    c = governance.confirm_owner("retire x", isatty=lambda: True, prompt=lambda m: "I APPROVE retire x")
    assert isinstance(c, OwnerConfirmation) and c.action == "retire x"


def test_cannot_forge_confirmation():
    with pytest.raises(TypeError):
        OwnerConfirmation("x", "t")
    with pytest.raises(TypeError):
        OwnerConfirmation("x", "t", object())


def test_lift_needs_owner(conn, owner):
    governance.emergency_stop(conn, actor="t", reason="r")
    with pytest.raises(PolicyDenied):
        governance.lift_stop(conn, actor="t", owner=None)
    governance.lift_stop(conn, actor="t", owner=owner)
    assert not governance.is_stopped(conn)


def test_stop_blocks_admission_but_allows_winddown(seeded, project, task):
    d = admission.admit(seeded, AdmitRequest(project_id=project.id, task_id=task.id, template_id="researcher",
                                             host="t"), actor="t")
    governance.emergency_stop(seeded, actor="t", reason="r")
    lifecycle.transition(seeded, d.instance_id, AgentState.RUNNING, actor="t")
    lifecycle.transition(seeded, d.instance_id, AgentState.COMPLETED, actor="t")
    again = admission.admit(seeded, AdmitRequest(project_id=project.id, task_id=task.id,
                                                 template_id="reviewer", host="t"), actor="t")
    assert "emergency_stop" in again.reasons


def test_approval_bound_to_params(conn, owner):
    a = governance.request_approval(conn, "push", {"branch": "main"}, requested_by="lead")
    governance.grant(conn, a.id, owner=owner, actor="owner")
    assert governance.check(conn, "push", {"branch": "dev"}) is None
    assert governance.check(conn, "push", {"branch": "main"}).id == a.id


def test_pending_approval_does_not_pass(conn):
    governance.request_approval(conn, "push", {"b": 1}, requested_by="lead")
    assert governance.check(conn, "push", {"b": 1}) is None


def test_approval_expires(conn, owner, monkeypatch):
    a = governance.request_approval(conn, "push", {}, requested_by="lead", ttl_minutes=1)
    governance.grant(conn, a.id, owner=owner, actor="owner")
    monkeypatch.setattr(util, "now_iso", lambda: "2999-01-01T00:00:00Z")
    assert governance.check(conn, "push", {}) is None


def test_approval_single_use(conn, owner):
    a = governance.request_approval(conn, "deploy", {"env": "prod"}, requested_by="lead")
    governance.grant(conn, a.id, owner=owner, actor="owner")
    governance.consume(conn, a.id, actor="lead")
    assert governance.check(conn, "deploy", {"env": "prod"}) is None
    with pytest.raises(PolicyDenied) as e:
        governance.consume(conn, a.id, actor="lead")
    assert "approval_consumed" in e.value.reasons


def test_grant_needs_owner(conn):
    a = governance.request_approval(conn, "x", {}, requested_by="lead")
    with pytest.raises(PolicyDenied):
        governance.grant(conn, a.id, owner=None, actor="lead")


def test_protected_setting_needs_owner(conn, owner):
    with pytest.raises(PolicyDenied):
        governance.set_setting(conn, "governance.anything", 1, actor="t")
    governance.set_setting(conn, "governance.anything", 1, actor="t", owner=owner)
    governance.set_setting(conn, "ui.color", "blue", actor="t")
