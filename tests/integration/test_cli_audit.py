import json
import sqlite3


def test_init_writes_audit_event_and_verify_ok(cli, home):
    cli(["init"])
    code, out, _ = cli(["audit", "verify", "--json"])
    data = json.loads(out)
    assert code == 0 and data["ok"] is True and data["checked"] >= 1


def test_audit_verify_exit_5_on_tamper(cli, home):
    cli(["init"])
    cli(["init"])
    c = sqlite3.connect(home / "state" / "agentos.db")
    c.execute("UPDATE events SET actor='mallory' WHERE seq=(SELECT min(seq) FROM events)")
    c.commit()
    c.close()
    code, _, _ = cli(["audit", "verify"])
    assert code == 5


def test_audit_log_lists_events(cli, home):
    cli(["init"])
    code, out, _ = cli(["audit", "log", "--json", "--kind", "system.init"])
    assert code == 0 and json.loads(out)[0]["kind"] == "system.init"


def test_doctor_checks_audit_chain(cli, home):
    cli(["init"])
    _, out, _ = cli(["doctor", "--json"])
    names = {c["name"]: c["status"] for c in json.loads(out)["checks"]}
    assert names["audit_chain"] == "VERIFIED"
