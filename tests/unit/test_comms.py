"""Messages, escalations and path claims between workers (agentos.comms)."""

import pytest

from agentos import comms, observe, projects, tasks
from agentos.errors import NotFound, PolicyDenied, UsageError
from tests.conftest import add_instance, make_repo


@pytest.fixture
def two(seeded, project, task):
    return add_instance(seeded, project, task, "implementer"), add_instance(seeded, project, task, "reviewer")


def test_messages_reach_the_recipient_and_broadcasts_reach_everyone_else(seeded, project, two):
    a, b = two
    comms.send(seeded, project.id, a, b, "please review src/x.py", "t", kind="request")
    comms.send(seeded, project.id, b, comms.BROADCAST, "the build is green", "t")
    got = comms.inbox(seeded, project.id, b, mark_read=True, actor="t")
    assert [m["body"] for m in got] == ["please review src/x.py"]  # its own broadcast is not echoed back
    assert comms.inbox(seeded, project.id, b) == []
    assert [m["body"] for m in comms.inbox(seeded, project.id, a)] == ["the build is green"]
    assert len(comms.inbox(seeded, project.id, b, unread_only=False)) == 1


def test_secrets_in_a_message_are_redacted_before_storage(seeded, project, two):
    a, b = two
    m = comms.send(seeded, project.id, a, b, "use api_key=abcd1234efgh5678 for now", "t")
    assert "abcd1234" not in m["body"] and m["redactions"] == 1
    stored = seeded.execute("SELECT body FROM messages WHERE id=?", (m["id"],)).fetchone()[0]
    assert "abcd1234" not in stored


def test_bad_messages_are_refused(seeded, project, two, tmp_path):
    a, b = two
    with pytest.raises(UsageError):
        comms.send(seeded, project.id, a, b, "x", "t", kind="gossip")
    with pytest.raises(UsageError):
        comms.send(seeded, project.id, a, b, "   ", "t")
    with pytest.raises(UsageError):
        comms.send(seeded, project.id, a, a, "talking to myself", "t")
    with pytest.raises(UsageError):
        comms.send(seeded, project.id, comms.BROADCAST, b, "from everyone", "t")
    with pytest.raises(UsageError):
        comms.send(seeded, project.id, a, b, "x" * (comms.MAX_BODY + 1), "t")
    with pytest.raises(NotFound):
        comms.send(seeded, project.id, a, "ag_missing", "hello", "t")
    other = projects.activate(seeded, make_repo(tmp_path / "other"), "t")
    stranger = add_instance(seeded, other, tasks.add_task(seeded, other.id, "theirs", actor="t"))
    with pytest.raises(PolicyDenied) as exc:
        comms.send(seeded, project.id, a, stranger, "hello", "t")
    assert exc.value.reasons == ["cross_project"]


def test_an_escalation_waits_on_the_dashboard_until_the_owner_reads_it(seeded, project, two):
    a, _ = two
    comms.escalate(seeded, project.id, a, "two reviewers disagree; please decide", "t")
    assert observe.dashboard(seeded, project.id)["open_escalations"] == 1
    assert "ESCALATIONS" in observe.render_dashboard(observe.dashboard(seeded, project.id))
    inc = observe.incidents(seeded, project.id)["incidents"]
    assert inc[0]["kind"] == "comms.escalated" and inc[0]["severity"] == "high"
    comms.inbox(seeded, project.id, comms.OWNER, mark_read=True, actor="owner")
    assert comms.open_escalations(seeded, project.id) == []


def test_a_claim_is_exclusive_across_overlapping_paths(seeded, project, two):
    a, b = two
    assert comms.claim(seeded, project.id, a, ["src/app/", "./README.md"], "t")["claimed"] == ["README.md", "src/app"]
    with pytest.raises(PolicyDenied) as exc:
        comms.claim(seeded, project.id, b, ["src/app/models.py"], "t")
    assert exc.value.reasons == ["path_claimed"] and a in exc.value.message
    with pytest.raises(PolicyDenied):
        comms.claim(seeded, project.id, b, ["src"], "t")  # a folder holding a claimed path
    assert comms.claim(seeded, project.id, b, ["src/lib.py"], "t")["claimed"] == ["src/lib.py"]
    assert comms.claim(seeded, project.id, a, ["README.md"], "t")["already_held"] == ["README.md"]
    assert comms.release(seeded, project.id, a, "t", ["README.md"])["released"] == ["README.md"]
    assert comms.claim(seeded, project.id, b, ["README.md"], "t")["claimed"] == ["README.md"]


def test_a_dead_holder_does_not_block_others(seeded, project, two):
    a, b = two
    comms.claim(seeded, project.id, a, ["src/x.py"], "t")
    seeded.execute("UPDATE agent_instances SET state='FAILED' WHERE id=?", (a,))
    assert comms.claims(seeded, project.id)[0]["holder_active"] is False
    r = comms.claim(seeded, project.id, b, ["src/x.py"], "t")
    assert r["claimed"] == ["src/x.py"] and r["freed_stale"] == ["src/x.py"]
    with pytest.raises(PolicyDenied) as exc:
        comms.claim(seeded, project.id, a, ["other.py"], "t")
    assert exc.value.reasons == ["not_active"]


@pytest.mark.parametrize("bad", ["/etc/passwd", "C:/Windows", "../outside.py", ".", ""])
def test_paths_outside_the_repository_cannot_be_claimed(seeded, project, two, bad):
    with pytest.raises(UsageError):
        comms.claim(seeded, project.id, two[0], [bad], "t")


def test_a_refused_claim_stays_in_the_audit_log(seeded, project, two):
    a, b = two
    comms.claim(seeded, project.id, a, ["src/x.py"], "t")
    with pytest.raises(PolicyDenied):
        comms.claim(seeded, project.id, b, ["src/x.py"], "t")
    row = seeded.execute("SELECT payload FROM events WHERE kind='comms.claim_denied'").fetchone()
    assert row is not None and b in row[0] and a in row[0]
    assert [c["instance_id"] for c in comms.claims(seeded, project.id)] == [a]  # b claimed nothing
    assert observe.incidents(seeded, project.id)["incidents"][0]["kind"] == "comms.claim_denied"


def test_agentos_escalates_to_the_owner_on_its_own(seeded, project, task):
    mid = comms.escalate_from_agentos(seeded, project.id, "retry limit reached token=abcd1234efgh5678abcd",
                                      "t", task_id=task.id)
    esc = comms.open_escalations(seeded, project.id)
    assert [e["id"] for e in esc] == [mid] and esc[0]["sender"] == comms.SYSTEM
    assert "abcd1234efgh5678" not in esc[0]["body"]
    assert observe.dashboard(seeded, project.id)["open_escalations"] == 1
    comms.inbox(seeded, project.id, comms.OWNER, mark_read=True, actor="owner")
    assert comms.open_escalations(seeded, project.id) == []
