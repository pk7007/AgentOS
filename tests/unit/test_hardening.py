"""Refusals and failure paths added in the third fix round: the external-action boundary of `evidence run`,
the automatic stale-worker check in the hook, memory provenance, termination without a handover note,
backup to an unwritable place, doctor on a damaged database or a bad host models table, and CLI input
that must never end in a traceback."""

import json
import sys
from datetime import UTC, datetime, timedelta

import pytest

from agentos import admission, evidence, lifecycle, memory, runtime, tasks, workforce
from agentos.errors import PolicyDenied
from tests.conftest import add_instance

LATER = datetime.now(UTC) + timedelta(days=2)


# --- evidence run: commands that reach outside this machine ---------------------------------------

@pytest.mark.parametrize("argv, found", [
    (["curl", "https://example.invalid"], "curl"),
    (["C:\\tools\\curl.exe", "-s", "x"], "curl"),
    (["git", "push", "origin", "main"], "git push"),
    (["git", "-C", "repo", "fetch"], "git fetch"),
    (["npm", "publish"], "npm publish"),
    (["gh", "pr", "create"], "gh"),
    (["Invoke-WebRequest", "x"], "invoke-webrequest"),
    (["cmd", "/c", "curl", "x"], "curl"),
    (["bash", "-c", "cd repo && git push origin main"], "git push"),
    (["powershell", "-c", "iwr https://example.invalid"], "iwr"),
    (["pip", "install", "requests"], "pip install"),
    ([sys.executable, "-m", "pip", "download", "x"], "pip download"),
    (["npm", "install"], "npm install"),
    (["env", "A=1", "wget", "x"], "wget"),
    (["npx", "some-tool"], "npx"), (["uvx", "tool"], "uvx"), (["poetry", "install"], "poetry install"),
    (["conda", "install", "numpy"], "conda install"), (["winget", "install", "x"], "winget install"),
    (["go", "get", "example.com/x"], "go get"), (["pip3.12", "install", "x"], "pip install"),
    (["python3.11", "-m", "pip", "install", "x"], "pip install"), (["git", "ls-remote", "origin"], "git ls-remote"),
])
def test_external_commands_are_recognised(argv, found):
    assert evidence.external_action(argv) == found


@pytest.mark.parametrize("argv", [["pytest", "-q"], [sys.executable, "-c", "print(1)"], ["git", "status"],
                                  ["git", "log", "-1"], ["npm", "test"], ["pip", "list"], [],
                                  [sys.executable, "-m", "pytest", "-q"], ["bash", "-c", "pytest -q && ruff check"],
                                  ["cmd", "/c", "echo", "done"]])
def test_local_checks_are_not_flagged(argv):
    assert evidence.external_action(argv) is None


def test_an_external_command_is_refused_without_the_owner_and_the_refusal_is_kept(conn, project):
    with pytest.raises(PolicyDenied) as e:
        evidence.run(conn, project.id, ["git", "push", "origin", "main"], actor="t")
    assert e.value.reasons == ["external_action"]
    row = conn.execute("SELECT payload FROM events WHERE kind='evidence.refused'").fetchone()
    assert row and json.loads(row[0])["external"] == "git push"
    assert conn.execute("SELECT count(*) FROM evidence").fetchone()[0] == 0


def test_the_owner_can_allow_an_external_command(conn, project, owner, monkeypatch):
    monkeypatch.setattr(evidence, "external_action", lambda argv: "curl")  # a harmless command stands in
    ev = evidence.run(conn, project.id, [sys.executable, "-c", "print('ok')"], actor="t", owner=owner)
    assert ev.exit_code == 0


def test_the_cli_asks_the_owner_before_an_external_command(cli, conn, project, repo, monkeypatch, owner_tty):
    monkeypatch.chdir(repo)
    monkeypatch.setattr(evidence, "external_action", lambda argv: "curl")  # a harmless command stands in
    code, out, err = cli(["evidence", "run", "--json", "--", sys.executable, "-c", "print('ok')"])
    assert code == 0, err
    assert json.loads(out)["exit_code"] == 0


def test_without_a_terminal_the_cli_refuses_and_records_it(cli, conn, project, repo, monkeypatch):
    monkeypatch.chdir(repo)
    code, _, err = cli(["evidence", "run", "--json", "--", "git", "push", "origin", "main"])
    assert code == 3 and json.loads(err)["reasons"] == ["external_action"]
    assert conn.execute("SELECT count(*) FROM events WHERE kind='evidence.refused'").fetchone()[0] == 1


# --- the hook finds crashed workers on its own ---------------------------------------------------

def _running(conn, project, task):
    d = admission.admit(conn, admission.AdmitRequest(project_id=project.id, task_id=task.id,
                                                      template_id="implementer", host="t"), "t")
    assert d.allowed, d.reasons
    lifecycle.transition(conn, d.instance_id, "RUNNING", "t")
    return d.instance_id


def _reaped_events(conn):
    return conn.execute("SELECT count(*) FROM events WHERE kind='health.reaped'").fetchone()[0]


def test_the_hook_reaps_stale_workers_at_most_every_five_minutes(seeded, project, task, repo):
    from agentos import health

    tasks.set_state(seeded, task.id, "running", "t")
    iid = _running(seeded, project, task)
    health.heartbeat(seeded, iid, project.id)  # heard from once, then silent for two days
    event = {"hook_event_name": "PreToolUse", "cwd": str(repo), "tool_name": "Read"}
    first = runtime.auto_reap(seeded, event, "t", now=LATER)
    assert [s["instance_id"] for s in first["reaped"]] == [iid]
    assert lifecycle.get_instance(seeded, iid).state.value == "FAILED"
    assert runtime.auto_reap(seeded, event, "t", now=LATER + timedelta(minutes=1)) is None
    assert runtime.auto_reap(seeded, event, "t", now=LATER + timedelta(minutes=6)) == {
        "after_minutes": runtime.AUTO_REAP_AFTER_MIN, "reaped": []}
    assert _reaped_events(seeded) == 1  # the empty check left no event


def test_the_hook_never_fails_a_worker_it_never_heard_from(seeded, project, task, repo):
    tasks.set_state(seeded, task.id, "running", "t")
    iid = _running(seeded, project, task)  # busy, but the host sends no heartbeats
    event = {"hook_event_name": "PreToolUse", "cwd": str(repo), "tool_name": "Read"}
    assert runtime.auto_reap(seeded, event, "t", now=LATER)["reaped"] == []
    assert lifecycle.get_instance(seeded, iid).state.value == "RUNNING"
    assert tasks.get_task(seeded, task.id).state.value == "running"
    assert _reaped_events(seeded) == 0


def test_a_worker_heard_from_within_the_hour_is_left_alone(seeded, project, task, repo):
    from agentos import health

    iid = _running(seeded, project, task)
    health.heartbeat(seeded, iid, project.id)
    soon = datetime.now(UTC) + timedelta(minutes=runtime.AUTO_REAP_AFTER_MIN - 5)
    event = {"hook_event_name": "PreToolUse", "cwd": str(repo), "tool_name": "Read"}
    assert runtime.auto_reap(seeded, event, "t", now=soon)["reaped"] == []
    assert lifecycle.get_instance(seeded, iid).state.value == "RUNNING"


def test_start_and_stop_events_do_not_run_the_check(seeded, project, repo, monkeypatch):
    calls = []
    monkeypatch.setattr(runtime, "auto_reap", lambda *a, **k: calls.append(a))
    runtime.handle(seeded, "codex", {"hook_event_name": "SubagentStop", "cwd": str(repo), "agent_id": "x"})
    runtime.handle(seeded, "codex", {"hook_event_name": "PreToolUse", "cwd": str(repo), "tool_name": "Read"})
    assert len(calls) == 1


def test_the_check_ignores_directories_that_are_not_projects(seeded, tmp_path):
    assert runtime.auto_reap(seeded, {"cwd": str(tmp_path)}, "t") is None


def test_a_failing_check_never_changes_the_hooks_answer(seeded, project, repo, monkeypatch, capsys):
    from agentos import health

    event = {"hook_event_name": "PreToolUse", "cwd": str(repo), "tool_name": "Read"}
    expected = runtime.handle(seeded, "codex", dict(event))

    def boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(health, "reap", boom)
    monkeypatch.setattr(runtime, "AUTO_REAP_EVERY_S", 0)
    assert runtime.handle(seeded, "codex", dict(event)) == expected
    assert "stale-worker check skipped" in capsys.readouterr().err


# --- knowledge keeps its provenance --------------------------------------------------------------

@pytest.mark.parametrize("source, author", [("", "a"), ("s", ""), ("  ", "a"), (None, "a")])
def test_memory_without_its_source_or_author_is_refused(conn, project, source, author):
    with pytest.raises(PolicyDenied) as e:
        memory.add(conn, project.id, memory.Layer.semantic, "a fact", source=source, author=author)
    assert e.value.reasons == ["no_provenance"]


def test_a_correction_without_its_author_is_refused(conn, project):
    rec = memory.add(conn, project.id, memory.Layer.semantic, "a fact", source="s", author="a")
    with pytest.raises(PolicyDenied) as e:
        memory.correct(conn, rec.id, "a better fact", author=" ", project_id=project.id)
    assert e.value.reasons == ["no_provenance"]
    assert memory.inspect(conn, rec.id).content == "a fact"


def test_the_cli_warns_when_a_worker_is_terminated_without_a_note(cli, seeded, project, task, repo, monkeypatch):
    monkeypatch.chdir(repo)
    iid = add_instance(seeded, project, task, template="implementer", state="COMPLETED")
    seeded.commit()
    code, out, _ = cli(["workforce", "terminate", iid, "--reason", "done", "--json"])
    assert code == 0
    result = json.loads(out)
    assert result["knowledge_kept"] is False and result["warnings"][0].startswith("no_handover_note")


def test_terminating_without_a_note_says_the_knowledge_was_not_kept(seeded, project, task):
    iid = add_instance(seeded, project, task, template="implementer", state="COMPLETED")
    r = workforce.terminate(seeded, iid, "done", "t")
    assert r["knowledge_kept"] is False and r["warnings"][0].startswith("no_handover_note")
    other = add_instance(seeded, project, task, template="implementer", state="COMPLETED")
    kept = workforce.terminate(seeded, other, "done", "t", note="the fixture is slow")
    assert kept["knowledge_kept"] is True and kept["warnings"] == []


# --- backup and doctor on bad ground -------------------------------------------------------------

def test_backup_to_an_unwritable_place_is_a_clean_refusal(cli, home, tmp_path):
    cli(["init"])
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    code, _, err = cli(["backup", "--dest", str(blocker / "sub")])
    assert code == 2 and "cannot write a backup" in err and "Traceback" not in err
    assert not (blocker / "sub").exists()


def test_a_failed_copy_leaves_no_half_written_backup(conn, tmp_path):
    import sqlite3

    from agentos import db
    from agentos.errors import UsageError

    class Failing:
        def backup(self, target):
            target.execute("CREATE TABLE half(x)")  # something was written before it failed
            raise sqlite3.OperationalError("disk I/O error")

    with pytest.raises(UsageError, match="failed and was removed"):
        db.backup(Failing(), tmp_path / "bk")
    assert list((tmp_path / "bk").iterdir()) == []


def test_a_file_error_is_exit_2_without_a_traceback(cli, home, monkeypatch):
    from agentos import db

    cli(["init"])

    def denied(*a, **k):
        raise PermissionError(13, "Access is denied", "agentos-backup.db")

    monkeypatch.setattr(db, "backup", denied)
    code, _, err = cli(["backup"])
    assert code == 2 and "Access is denied" in err and "agentos-backup.db" in err and "Traceback" not in err


@pytest.mark.parametrize("exc, code, says, not_says", [
    (lambda s: s.OperationalError("database is locked"), 2, "busy", "restore"),
    (lambda s: s.DatabaseError("file is not a database"), 5, "agentos restore", "busy"),
    (lambda s: s.DatabaseError("database disk image is malformed"), 5, "agentos restore", "busy"),
    (lambda s: s.IntegrityError("UNIQUE constraint failed: tasks.id"), 5, "database error", "restore"),
])
def test_database_errors_are_told_apart(capsys, exc, code, says, not_says):
    import sqlite3

    from agentos import cli as cli_module

    assert cli_module._database_error(exc(sqlite3)) == code
    err = capsys.readouterr().err
    assert says in err and not_says not in err


def test_a_refusal_prints_what_to_do(cli, conn, project, repo, monkeypatch):
    monkeypatch.chdir(repo)
    code, _, err = cli(["health", "stale", "--after-minutes", "-5"])
    assert code == 3 and "reasons: bad_threshold" in err
    assert "bad_threshold: pass a positive number of minutes" in err


def test_doctor_reports_a_database_with_damaged_pages(cli, home):
    import sqlite3

    from agentos import paths

    cli(["init"])
    con = sqlite3.connect(paths.db_path())
    con.execute("PRAGMA journal_mode=DELETE")
    con.execute("CREATE TABLE filler(x)")
    con.executemany("INSERT INTO filler VALUES (?)", [("x" * 500,)] * 400)
    con.commit()
    con.close()
    for suffix in ("-wal", "-shm"):
        paths.db_path().with_name("agentos.db" + suffix).unlink(missing_ok=True)
    data = bytearray(paths.db_path().read_bytes())
    page = 4096
    for start in range(page * 3, len(data) - page, page * 7):  # scribble over some pages, keep the header
        data[start + 8:start + 200] = b"\xff" * 192
    paths.db_path().write_bytes(bytes(data))
    code, out, err = cli(["doctor", "--json"])
    assert code == 5 and "Traceback" not in err
    db_check = next(c for c in json.loads(out)["checks"] if c["name"] == "database")
    assert db_check["status"] == "UNSUPPORTED"


def test_doctor_reports_what_integrity_check_finds_in_a_readable_database(cli, home):
    import sqlite3

    from agentos import paths

    cli(["init"])
    con = sqlite3.connect(paths.db_path())
    con.execute("CREATE TABLE filler(a, b)")
    con.execute("CREATE INDEX filler_a ON filler(a)")
    con.executemany("INSERT INTO filler VALUES (?, ?)", [(i, -i) for i in range(50)])
    con.commit()
    con.execute("PRAGMA writable_schema=ON")  # the index now claims a column it does not hold
    con.execute("UPDATE sqlite_master SET sql='CREATE INDEX filler_a ON filler(b)' WHERE name='filler_a'")
    con.commit()
    con.close()
    code, out, err = cli(["doctor", "--json"])
    assert code == 5 and "Traceback" not in err
    db_check = next(c for c in json.loads(out)["checks"] if c["name"] == "database")
    assert db_check["status"] == "UNSUPPORTED" and "missing from index filler_a" in db_check["detail"]


def test_the_json_refusal_carries_the_remedy(cli, conn, project, repo, monkeypatch):
    monkeypatch.chdir(repo)
    code, _, err = cli(["health", "stale", "--after-minutes", "-5", "--json"])
    body = json.loads(err)
    assert code == 3 and body["remedies"] == {"bad_threshold": "pass a positive number of minutes"}


def _damage(paths, data):
    for suffix in ("-wal", "-shm"):
        paths.db_path().with_name("agentos.db" + suffix).unlink(missing_ok=True)
    paths.db_path().write_bytes(data)


def test_doctor_reports_a_damaged_database_instead_of_crashing(cli, home):
    from agentos import paths

    cli(["init"])
    _damage(paths, b"this is not a database" * 200)
    code, out, err = cli(["doctor", "--json"])
    assert code == 5 and "Traceback" not in err
    db_check = next(c for c in json.loads(out)["checks"] if c["name"] == "database")
    assert db_check["status"] == "UNSUPPORTED" and "agentos restore" in db_check["detail"]


def test_other_commands_on_a_damaged_database_point_to_doctor(cli, home):
    from agentos import paths

    cli(["init"])
    _damage(paths, b"garbage" * 500)
    code, _, err = cli(["status"])
    assert code == 5 and "agentos doctor" in err and "Traceback" not in err


def test_doctor_checks_the_host_models_tables(cli, home):
    hosts = home / "hosts"
    hosts.mkdir(parents=True)
    (hosts / "good.toml").write_text('[models]\nsmall = "m-small"\nlarge = "m-large"\n')
    (hosts / "bad.toml").write_text('[models]\nhuge = "m"\nsmall = 3\n')
    (hosts / "broken.toml").write_text("[models\n")
    (hosts / "none.toml").write_text('name = "x"\n')
    cli(["init"])
    _, out, _ = cli(["doctor", "--json"])
    checks = {c["name"]: c for c in json.loads(out)["checks"]}
    good, bad = checks["host_models:good"], checks["host_models:bad"]
    assert good["status"] == "VERIFIED" and "small, large" in good["detail"]
    assert bad["status"] == "UNSUPPORTED" and "huge" in bad["detail"] and "small" in bad["detail"]
    assert checks["host_models:broken"]["status"] == "UNSUPPORTED"
    assert "host_models:none" not in checks


# --- the CLI never answers bad input with a traceback --------------------------------------------

def test_a_mistyped_command_gets_a_suggestion(cli, home):
    code, _, err = cli(["stauts"])
    assert code == 2 and "did you mean: status" in err


def test_a_mistyped_command_far_from_any_gets_no_guess(cli, home):
    code, _, err = cli(["qqqqqq"])
    assert code == 2 and "did you mean" not in err


@pytest.mark.parametrize("argv", [
    [], ["--json"], ["nonsense"], ["task", "add"], ["task", "show", "tk_missing"], ["memory", "search"],
    ["evidence", "run"], ["evidence", "run", "--"], ["backup", "--dest"], ["restore", "no-such-file.db"],
    ["retention", "plan", "--days", "1"], ["retention", "plan", "--days", "abc"], ["x" * 5000],
    ["status", "--project", "../../etc"], ["health", "reap", "--after", "-5"],
])
def test_bad_input_never_ends_in_a_traceback(cli, home, argv):
    cli(["init"])
    code, _, err = cli(argv)
    assert "Traceback" not in err
    assert code in {2, 3, 4, 5}  # bad input is never a success
