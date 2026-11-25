import hashlib
import json
import sqlite3


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_command_before_init_exits_2(cli, home):
    code, _, err = cli(["status"])
    assert code == 2 and "agentos init" in err


def test_init_is_idempotent(cli, home):
    assert cli(["init"])[0] == 0
    code, out, _ = cli(["init", "--json"])
    assert code == 0 and json.loads(out)["schema_version"] == 1


def test_status_after_init(cli, home):
    cli(["init"])
    code, out, _ = cli(["status", "--json"])
    data = json.loads(out)
    assert code == 0 and data["emergency_stop"] is False


def _set(home, key, value):
    c = sqlite3.connect(home / "state" / "agentos.db")
    c.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, value))
    c.commit()
    c.close()


def _get(home, key):
    c = sqlite3.connect(home / "state" / "agentos.db")
    v = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()[0]
    c.close()
    return v


def test_restore_without_owner_denied(cli, home):
    cli(["init"])
    _, out, _ = cli(["backup", "--json"])
    assert cli(["restore", json.loads(out)["path"]])[0] == 3


def test_backup_then_restore_roundtrip(cli, home, owner_tty):
    cli(["init"])
    _set(home, "x", '"before"')
    code, out, _ = cli(["backup", "--json"])
    assert code == 0
    backup_file = json.loads(out)["path"]
    _set(home, "x", '"after"')
    code, _, err = cli(["restore", backup_file])
    assert code == 0, err
    assert _get(home, "x") == '"before"'


def test_restore_rejects_non_sqlite(cli, home, tmp_path, owner_tty):
    cli(["init"])
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a db at all" * 100)
    before = _sha(home / "state" / "agentos.db")
    code, _, _ = cli(["restore", str(bad)])
    assert code == 5
    assert _sha(home / "state" / "agentos.db") == before


def test_restore_rejects_newer_schema(cli, home, tmp_path, owner_tty):
    cli(["init"])
    code, out, _ = cli(["backup", "--json"])
    newer = json.loads(out)["path"]
    c = sqlite3.connect(newer)
    c.execute("INSERT INTO schema_migrations VALUES (99, '2099-01-01T00:00:00Z')")
    c.commit()
    c.close()
    code, _, _ = cli(["restore", newer])
    assert code == 5


def test_doctor_reports_statuses(cli, home):
    cli(["init"])
    code, out, _ = cli(["doctor", "--json"])
    data = json.loads(out)
    assert code == 0
    assert data["checks"] and all(
        c["status"] in {"VERIFIED", "UNSUPPORTED", "UNKNOWN"} for c in data["checks"]
    )
