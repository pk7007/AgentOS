"""Resilience: a failure part-way through a write leaves nothing half-written, a busy database is waited
for rather than failed, a process killed mid-write corrupts nothing, and a backup restores real data."""

import subprocess
import sys
import threading
import time

import pytest

from agentos import admission, audit, db, memory, tasks
from agentos.memory import Layer


def test_an_error_inside_a_transaction_leaves_no_partial_write(seeded, project):
    before = seeded.execute("SELECT count(*) FROM events").fetchone()[0]
    with pytest.raises(RuntimeError), db.write_tx(seeded):
        seeded.execute("INSERT INTO tasks(id, project_id, title, created_at, updated_at) "
                       "VALUES ('task_half', ?, 'half', 'x', 'x')", (project.id,))
        audit.append_event(seeded, "task.added", "t", {"task_id": "task_half"}, project.id)
        raise RuntimeError("power cut")
    assert seeded.execute("SELECT count(*) FROM tasks WHERE id='task_half'").fetchone()[0] == 0
    assert seeded.execute("SELECT count(*) FROM events").fetchone()[0] == before
    assert audit.verify_chain(seeded).ok


def test_a_busy_database_is_waited_for_not_failed(seeded, project, home):
    t = tasks.add_task(seeded, project.id, "contended", actor="t")
    locked = threading.Event()

    def hold_the_lock():
        blocker = db.connect()  # its own connection, as another process would have
        blocker.execute("BEGIN IMMEDIATE")
        locked.set()
        time.sleep(1.0)
        blocker.execute("COMMIT")
        blocker.close()

    th = threading.Thread(target=hold_the_lock)
    th.start()
    assert locked.wait(10)
    started = time.monotonic()
    d = admission.admit(seeded, admission.AdmitRequest(project_id=project.id, task_id=t.id,
                                                       template_id="implementer", host="t"), "t")
    th.join(10)
    assert d.allowed and time.monotonic() - started >= 0.5


_KILL_MID_WRITE = """
import os, sys
os.environ["AGENTOS_HOME"] = sys.argv[1]
from agentos import db
conn = db.connect()
conn.execute("BEGIN IMMEDIATE")
conn.execute("INSERT INTO settings VALUES ('half.written', '1')")
conn.execute("UPDATE events SET payload='{}'")
os._exit(9)  # killed before COMMIT
"""


def test_a_process_killed_mid_write_corrupts_nothing(seeded, project, home):
    memory.add(seeded, project.id, Layer.semantic, "survives the crash", "t", "t")
    r = subprocess.run([sys.executable, "-c", _KILL_MID_WRITE, str(home)], check=False, timeout=60)
    assert r.returncode == 9
    fresh = db.connect()
    try:
        assert fresh.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert fresh.execute("SELECT count(*) FROM settings WHERE key='half.written'").fetchone()[0] == 0
        assert audit.verify_chain(fresh).ok
        assert memory.search(fresh, project.id, "survives")[0].content == "survives the crash"
    finally:
        fresh.close()


def test_backup_restores_real_work_and_keeps_a_safety_copy(seeded, project, home):
    t = tasks.add_task(seeded, project.id, "before the backup", actor="t")
    memory.add(seeded, project.id, Layer.semantic, "kept in the backup", "t", "t")
    other = db.connect()  # an open reader must not stop a consistent backup
    other.execute("SELECT count(*) FROM tasks").fetchone()
    snap = db.backup(seeded)
    events = seeded.execute("SELECT count(*) FROM events").fetchone()[0]
    tasks.add_task(seeded, project.id, "after the backup", actor="t")
    other.close()
    safety = db.restore(snap)
    back = db.connect()
    try:
        titles = {r[0] for r in back.execute("SELECT title FROM tasks")}
        assert t.title in titles and "after the backup" not in titles
        assert back.execute("SELECT count(*) FROM events").fetchone()[0] == events
        assert audit.verify_chain(back).ok and memory.search(back, project.id, "kept")
    finally:
        back.close()
    assert safety and safety.exists()
    old = db.connect(safety)
    try:
        assert "after the backup" in {r[0] for r in old.execute("SELECT title FROM tasks")}
    finally:
        old.close()
