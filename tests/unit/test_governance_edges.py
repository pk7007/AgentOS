"""Edge cases for governance: deny only pending approvals, missing ids, the real-console check."""

import io
import os
import sys

import pytest

from agentos import audit, governance
from agentos.errors import NotFound, PolicyDenied


def _events(conn, kind):
    return [e for e in audit.list_events(conn, limit=500) if e["kind"] == kind]


def test_deny_granted_approval_is_refused_and_not_audited(conn, owner):
    a = governance.request_approval(conn, "deploy", {"env": "prod"}, "agent")
    governance.grant(conn, a.id, owner, "owner")
    with pytest.raises(PolicyDenied) as e:
        governance.deny(conn, a.id, "someone")
    assert "approval_not_pending" in e.value.reasons
    assert governance.get_approval(conn, a.id).status == "granted"
    assert _events(conn, "approval.denied") == []


def test_deny_pending(conn):
    a = governance.request_approval(conn, "deploy", {}, "agent")
    assert governance.deny(conn, a.id, "owner").status == "denied"
    assert len(_events(conn, "approval.denied")) == 1
    assert governance.check(conn, "deploy", {}) is None


def test_grant_twice_refused(conn, owner):
    a = governance.request_approval(conn, "deploy", {}, "agent")
    governance.grant(conn, a.id, owner, "owner")
    with pytest.raises(PolicyDenied) as e:
        governance.grant(conn, a.id, owner, "owner")
    assert "approval_not_pending" in e.value.reasons


def test_unknown_approval(conn):
    with pytest.raises(NotFound):
        governance.get_approval(conn, "apr_000000000000")


def test_list_approvals_by_status(conn):
    a = governance.request_approval(conn, "x", {}, "agent")
    governance.request_approval(conn, "y", {}, "agent")
    governance.deny(conn, a.id, "owner")
    assert [x.action for x in governance.list_approvals(conn, "pending")] == ["y"]
    assert len(governance.list_approvals(conn)) == 2


def test_isatty_false_without_stdin(monkeypatch):
    monkeypatch.setattr(sys, "stdin", None)
    assert governance._default_isatty() is False


def test_isatty_false_for_pipe(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert governance._default_isatty() is False


@pytest.mark.skipif(os.name != "nt", reason="Windows console check")
def test_isatty_false_for_nul_device(monkeypatch):
    # On Windows, NUL claims isatty() is True; the console-mode check must still say no.
    with open(os.devnull) as nul:
        assert nul.isatty() is True
        monkeypatch.setattr(sys, "stdin", nul)
        assert governance._default_isatty() is False


@pytest.mark.skipif(os.name != "nt", reason="Windows console check")
def test_isatty_false_when_fileno_unavailable(monkeypatch):
    class Fake:
        def isatty(self):
            return True

        def fileno(self):
            raise ValueError("no fd")

    monkeypatch.setattr(sys, "stdin", Fake())
    assert governance._default_isatty() is False


def test_default_prompt_reads_one_line(monkeypatch):
    err = io.StringIO()
    monkeypatch.setattr(sys, "stderr", err)
    monkeypatch.setattr(sys, "stdin", io.StringIO("I APPROVE x\nmore\n"))
    assert governance._default_prompt("ask> ") == "I APPROVE x\n"
    assert err.getvalue() == "ask> "
