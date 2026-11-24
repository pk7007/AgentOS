import pytest

from agentos import audit, db


def _append(conn, n):
    with db.write_tx(conn):
        for i in range(n):
            audit.append_event(conn, "test.event", "tester", {"i": i})


def test_chain_verifies(conn):
    _append(conn, 3)
    r = audit.verify_chain(conn)
    assert r.ok and r.checked >= 3 and r.first_bad_seq is None


def test_tamper_detected(conn):
    _append(conn, 3)
    seqs = [row[0] for row in conn.execute("SELECT seq FROM events ORDER BY seq")]
    conn.execute("UPDATE events SET payload='{\"i\":99}' WHERE seq=?", (seqs[1],))
    r = audit.verify_chain(conn)
    assert not r.ok and r.first_bad_seq == seqs[1]


def test_deleted_row_detected(conn):
    _append(conn, 3)
    seqs = [row[0] for row in conn.execute("SELECT seq FROM events ORDER BY seq")]
    conn.execute("DELETE FROM events WHERE seq=?", (seqs[1],))
    assert not audit.verify_chain(conn).ok


def test_append_outside_tx_raises(conn):
    with pytest.raises(AssertionError):
        audit.append_event(conn, "x", "y", {})


def test_audit_payload_is_redacted(conn):
    with db.write_tx(conn):
        audit.append_event(conn, "note", "tester", {"note": "token=abc123secret"})
    ev = audit.list_events(conn, kind="note")[0]
    assert "abc123secret" not in str(ev["payload"])


def test_list_events_filters(conn):
    _append(conn, 2)
    with db.write_tx(conn):
        audit.append_event(conn, "other", "tester", {}, project_id="prj_x")
    assert len(audit.list_events(conn, kind="other")) == 1
    assert len(audit.list_events(conn, project_id="prj_x")) == 1
