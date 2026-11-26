"""Direct tests for what the Phase 1 fixes added: the evidence runner, audit anchors, the owner PIN,
usage charging, stop confirmation and the high-risk approval path."""

import json
import sys

import pytest

from agentos import admission, audit, db, evidence, governance, governor, lifecycle, tasks
from agentos.admission import AdmitRequest
from agentos.errors import NotFound, PolicyDenied, UsageError
from agentos.lifecycle import AgentState as S
from agentos.redact import redact


def _admit(conn, project, task_id, template="implementer"):
    return admission.admit(conn, AdmitRequest(project_id=project.id, task_id=task_id, template_id=template,
                                              host="test"), actor="t")


# evidence runner

def test_evidence_records_what_really_happened(conn, project):
    ok = evidence.run(conn, project.id, [sys.executable, "-c", "print('41 passed')"], actor="t")
    assert ok.exit_code == 0 and "41 passed" in ok.output_tail and not ok.timed_out
    assert ok.cwd == project.path and len(ok.stdout_sha256) == 64
    bad = evidence.run(conn, project.id, [sys.executable, "-c", "import sys; print('boom'); sys.exit(3)"], actor="t")
    assert bad.exit_code == 3 and "boom" in bad.output_tail
    assert len(audit.list_events(conn, kind="evidence.recorded")) == 2


def test_evidence_redacts_secrets_in_output(conn, project):
    ev = evidence.run(conn, project.id, [sys.executable, "-c", "print('password=hunter2-long')"], actor="t")
    assert "hunter2-long" not in ev.output_tail


def test_evidence_timeout_and_missing_command(conn, project):
    slow = evidence.run(conn, project.id, [sys.executable, "-c", "import time; time.sleep(5)"], actor="t",
                        timeout_s=1)
    assert slow.timed_out and slow.exit_code == -1
    missing = evidence.run(conn, project.id, ["no-such-command-xyz"], actor="t")
    assert missing.exit_code == 127
    with pytest.raises(UsageError):
        evidence.run(conn, project.id, [], actor="t")


def test_evidence_read_is_project_scoped(conn, project, tmp_path):
    from agentos import projects
    from tests.conftest import make_repo

    other = projects.activate(conn, make_repo(tmp_path / "Other"), actor="t")
    ev = evidence.run(conn, project.id, [sys.executable, "-c", "pass"], actor="t")
    assert evidence.read(conn, ev.id, project.id).id == ev.id
    with pytest.raises(PolicyDenied):
        evidence.read(conn, ev.id, other.id)
    with pytest.raises(NotFound):
        evidence.get(conn, "evd_000000000000")


# audit anchors

def test_anchor_detects_whole_chain_rewrite(conn):
    with db.write_tx(conn):
        audit.append_event(conn, "a", "t", {"i": 1})
        audit.append_event(conn, "b", "t", {"i": 2})
    anchor = audit.head(conn)
    assert audit.verify_chain(conn, anchor=anchor).ok
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM sqlite_sequence WHERE name='events'")  # a careful attacker resets the counter
    with db.write_tx(conn):
        audit.append_event(conn, "forged", "t", {"i": 1})
        audit.append_event(conn, "forged", "t", {"i": 2})
    assert audit.verify_chain(conn).ok  # locally consistent...
    r = audit.verify_chain(conn, anchor=anchor)
    assert not r.ok and r.reason == "anchor_mismatch"  # ...but not the chain the owner anchored


def test_anchor_ahead_of_chain_is_detected(conn):
    with db.write_tx(conn):
        audit.append_event(conn, "a", "t", {})
    r = audit.verify_chain(conn, anchor={"seq": 99, "hash": "x"})
    assert not r.ok and r.reason == "behind_anchor"


def test_truncation_reason_reported(conn):
    with db.write_tx(conn):
        audit.append_event(conn, "a", "t", {})
        audit.append_event(conn, "b", "t", {})
    conn.execute("DELETE FROM events WHERE seq=2")
    r = audit.verify_chain(conn)
    assert not r.ok and r.reason == "truncated_tail" and r.first_bad_seq == 2


def test_audit_anchor_cli_round_trip(cli, home, tmp_path):
    cli(["init"])
    out = tmp_path / "anchor.json"
    code, body, _ = cli(["audit", "anchor", "--out", str(out), "--json"])
    assert code == 0 and json.loads(out.read_text())["seq"] == json.loads(body)["seq"]
    assert cli(["audit", "verify", "--anchor", str(out)])[0] == 0
    out.write_text('{"seq": 1, "hash": "nope"}')
    assert cli(["audit", "verify", "--anchor", str(out)])[0] == 5
    out.write_text("not json")
    assert cli(["audit", "verify", "--anchor", str(out)])[0] == 2


# owner PIN

def test_pin_must_be_long_enough_and_needs_owner(conn, owner):
    with pytest.raises(PolicyDenied):
        governance.set_owner_pin(conn, "123456", None, actor="t")
    with pytest.raises(PolicyDenied) as e:
        governance.set_owner_pin(conn, "123", owner, actor="t")
    assert "weak_pin" in e.value.reasons
    governance.set_owner_pin(conn, "123456", owner, actor="t")
    stored = json.dumps(db.get_setting(conn, governance.PIN_KEY))
    assert "123456" not in stored and governance.has_owner_pin(conn)
    assert "123456" not in json.dumps(audit.list_events(conn, kind="governance.owner_pin_set"))
    governance.clear_owner_pin(conn, owner, actor="t")
    assert not governance.has_owner_pin(conn)


def test_owner_pin_cli(cli, home, monkeypatch):
    cli(["init"])
    monkeypatch.setattr(governance, "_default_isatty", lambda: True)
    monkeypatch.setattr(governance, "_default_prompt", lambda msg: "I APPROVE " + msg.split("'")[1])
    answers = iter(["river-4821", "river-4821"])
    monkeypatch.setattr(governance, "_default_secret", lambda msg: next(answers))
    code, out, _ = cli(["owner", "pin", "set", "--json"])
    assert code == 0 and json.loads(out)["owner_pin"] is True
    monkeypatch.setattr(governance, "_default_secret", lambda msg: "wrong-pin")
    assert cli(["stop", "--reason", "x"])[0] == 0
    assert cli(["stop", "--lift"])[0] == 3  # the phrase alone no longer works
    monkeypatch.setattr(governance, "_default_secret", lambda msg: "river-4821")
    assert cli(["stop", "--lift"])[0] == 0
    mismatch = iter(["river-4821", "aaaaaaa", "bbbbbbb"])
    monkeypatch.setattr(governance, "_default_secret", lambda msg: next(mismatch))
    assert cli(["owner", "pin", "set"])[0] == 2
    monkeypatch.setattr(governance, "_default_secret", lambda msg: "river-4821")
    assert json.loads(cli(["owner", "pin", "clear", "--json"])[1])["owner_pin"] is False
    assert json.loads(cli(["owner", "pin", "status", "--json"])[1])["owner_pin"] is False


# usage charging

def test_usage_validation_and_usd_cap(seeded, project, task):
    a = _admit(seeded, project, task.id).instance_id
    with pytest.raises(UsageError):
        governor.record_usage(seeded, a, "agent_runs", 1, actor="t")
    with pytest.raises(UsageError):
        governor.record_usage(seeded, a, "tokens_est", -10, actor="t")
    with pytest.raises(PolicyDenied) as e:
        governor.record_usage(seeded, a, "usd", 0.5, actor="t")  # paid spend cap is 0
    assert "paid_spend_blocked" in e.value.reasons
    rid = governor.record_usage(seeded, a, "tokens_est", 500, actor="t")
    charged = "SELECT count(*) FROM reservations WHERE id LIKE ? AND state='charged'"
    assert seeded.execute(charged, (f"{rid}:%",)).fetchone()[0] == 3
    lifecycle.transition(seeded, a, S.RUNNING, "t")
    lifecycle.transition(seeded, a, S.COMPLETED, "t")
    assert seeded.execute(charged, (f"{rid}:%",)).fetchone()[0] == 3  # finishing does not refund usage


def test_set_budget_validation(conn):
    for scope, kind, limit in (("galaxy", "agent_runs", 1), ("global", "bananas", 1), ("global", "agent_runs", -1),
                               ("global", "agent_runs", float("nan"))):
        with pytest.raises(UsageError):
            governor.set_budget(conn, scope, "*", kind, limit, actor="t")


def test_budget_use_cli(cli, home, repo, monkeypatch):
    monkeypatch.chdir(repo)
    cli(["init"])
    cli(["template", "seed"])
    cli(["project", "activate", str(repo)])
    tid = json.loads(cli(["task", "add", "t", "--json"])[1])["id"]
    iid = json.loads(cli(["agent", "admit", "--task", tid, "--template", "implementer", "--json"])[1])["instance_id"]
    assert cli(["budget", "set", "global", "tokens_est", "1000"])[0] == 0
    assert cli(["budget", "use", iid])[0] == 2
    code, out, _ = cli(["budget", "use", iid, "--tokens", "600", "--json"])
    assert code == 0 and "tokens_est" in json.loads(out)["charged"]
    assert cli(["budget", "use", iid, "--tokens", "600"])[0] == 3


# stop confirmation

def test_confirm_stopped_paths(seeded, project, task):
    a = _admit(seeded, project, task.id).instance_id
    with pytest.raises(PolicyDenied) as e:
        lifecycle.confirm_stopped(seeded, a, "t")
    assert "not_stopping" in e.value.reasons
    lifecycle.transition(seeded, a, S.CANCELLED, "t")
    assert lifecycle.slot_count(seeded) == 1 and lifecycle.active_count(seeded) == 0
    inst = lifecycle.confirm_stopped(seeded, a, "t")
    assert inst.state == S.TERMINATED and inst.termination_confirmed and lifecycle.slot_count(seeded) == 0


def test_unconfirmed_termination_can_be_confirmed_later(seeded, project, task):
    a = _admit(seeded, project, task.id).instance_id
    lifecycle.transition(seeded, a, S.CANCELLED, "t")
    lifecycle.transition(seeded, a, S.TERMINATED, "t", runtime_confirmed=False)
    with pytest.raises(PolicyDenied) as e:
        lifecycle.transition(seeded, a, S.ARCHIVED, "t")
    assert "termination_unconfirmed" in e.value.reasons
    assert lifecycle.confirm_stopped(seeded, a, "t").termination_confirmed
    assert lifecycle.transition(seeded, a, S.ARCHIVED, "t").state == S.ARCHIVED


def test_cancelled_can_be_archived_with_confirmation(seeded, project, task):
    a = _admit(seeded, project, task.id).instance_id
    lifecycle.transition(seeded, a, S.CANCELLED, "t")
    inst = lifecycle.transition(seeded, a, S.ARCHIVED, "t", runtime_confirmed=True)
    assert inst.state == S.ARCHIVED and inst.termination_confirmed and lifecycle.slot_count(seeded) == 0


def test_reentry_reserves_a_run_and_respects_budget(seeded, project, task):
    governor.set_budget(seeded, "task", task.id, "agent_runs", 1, actor="t")
    a = _admit(seeded, project, task.id).instance_id
    lifecycle.transition(seeded, a, S.RUNNING, "t")
    lifecycle.transition(seeded, a, S.FAILED, "t")
    with pytest.raises(PolicyDenied) as e:
        lifecycle.transition(seeded, a, S.ASSIGNED, "t")
    assert "budget_exceeded:task:agent_runs" in e.value.reasons


# high-risk and critical admission

def test_high_risk_admitted_with_owner_approval_once(seeded, project, owner):
    t = tasks.add_task(seeded, project.id, "risky", capabilities=["python"], risk="high", actor="t")
    params = {"task_id": t.id, "template_id": "implementer"}
    a = governance.request_approval(seeded, admission.HIGH_RISK_ACTION, params, "host")
    governance.grant(seeded, a.id, owner, "owner")
    d = _admit(seeded, project, t.id)
    assert d.allowed
    assert governance.get_approval(seeded, a.id).status == "consumed"
    lifecycle.transition(seeded, d.instance_id, S.CANCELLED, "t")
    lifecycle.confirm_stopped(seeded, d.instance_id, "t")
    assert "high_risk_unproven" in _admit(seeded, project, t.id).reasons


def test_critical_risk_always_needs_approval(seeded, project):
    t = tasks.add_task(seeded, project.id, "critical", risk="critical", actor="t")
    assert "owner_approval_required" in _admit(seeded, project, t.id).reasons


def test_denied_admission_does_not_consume_the_approval(seeded, project, owner):
    t = tasks.add_task(seeded, project.id, "risky", risk="high", actor="t")
    a = governance.request_approval(seeded, admission.HIGH_RISK_ACTION,
                                    {"task_id": t.id, "template_id": "implementer"}, "host")
    governance.grant(seeded, a.id, owner, "owner")
    governance.emergency_stop(seeded, actor="t", reason="x")
    assert not _admit(seeded, project, t.id).allowed
    assert governance.get_approval(seeded, a.id).status == "granted"


# redaction does not eat ordinary words

@pytest.mark.parametrize("text", ["tokens_est=100", "the secretary said hi", "max tokens: 500",
                                  "passwords are hashed", "https://example.com/path@v2"])
def test_redaction_leaves_ordinary_text(text):
    assert redact(text) == (text, 0)
